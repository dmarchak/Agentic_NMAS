"""terminal.py

Live interactive SSH terminal sessions via Paramiko and Flask-SocketIO.

`ensure_terminal_session` opens (or reuses) a Paramiko shell channel to a
device, enters enable mode, and stores the session in a caller-managed dict.
`start_terminal_reader` spawns a daemon thread that continuously reads from
the channel and emits data to the SocketIO room for that device IP, feeding the
xterm.js terminal in the browser in real time.
"""

import logging
import re
import threading
import time
import paramiko
from flask_socketio import SocketIO
from modules.device import decrypt_field, load_saved_devices, get_current_device_list
from modules.config import SSH_PORT, SSH_TIMEOUT

logger = logging.getLogger(__name__)


def ensure_terminal_session(ip: str, terminal_sessions: dict,
                            key: str = "") -> paramiko.Channel:
    """Ensures a live Paramiko SSH session/channel exists for *key*.

    *key* identifies ONE connection's shell (the caller passes
    ``"<socket sid>|<ip>"``, register D12); it defaults to the address for a
    caller that has no connection.
    """
    key = key or ip
    # Reuse an existing channel if present and healthy; otherwise create
    # a new Paramiko SSH connection and shell channel and store it in
    # the `terminal_sessions` mapping for later reuse (and cleanup).
    sess = terminal_sessions.get(key)
    if sess and sess.get("chan") and not sess["chan"].closed:
        logger.debug(f"Reusing existing terminal session for {ip}")
        return sess["chan"]

    # Clean up any stale session
    terminal_sessions.pop(key, None)

    # Get the current device list file and load devices from it
    _, current_list_file = get_current_device_list()
    dev = next((d for d in load_saved_devices(current_list_file) if d["ip"] == ip), None)
    if not dev:
        raise RuntimeError(f"Device {ip} not found for terminal session")

    username = dev["username"]
    password = decrypt_field(dev["password"])
    # Netmiko's semantics: the enable secret, or the login password when none
    # is stored. It is sent ONLY in answer to a password prompt (below).
    try:
        secret = decrypt_field(dev["secret"]) if dev.get("secret") else ""
    except Exception:                                  # noqa: BLE001
        secret = ""
    enable_secret = secret or password

    logger.info(f"Creating new terminal session for {ip} (user: {username})")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(
            ip,
            port=SSH_PORT,
            username=username,
            password=password,
            timeout=SSH_TIMEOUT,
            look_for_keys=False,
            allow_agent=False
        )
        logger.info(f"SSH connection established to {ip}")
    except paramiko.AuthenticationException as e:
        logger.error(f"Authentication failed for {ip}: {e}")
        raise RuntimeError(f"Authentication failed for {ip}: {e}")
    except paramiko.SSHException as e:
        logger.error(f"SSH error connecting to {ip}: {e}")
        raise RuntimeError(f"SSH connection error for {ip}: {e}")
    except Exception as e:
        logger.error(f"Connection failed for {ip}: {e}")
        raise RuntimeError(f"Failed to connect to {ip}: {e}")

    chan = ssh.invoke_shell()
    chan.setblocking(0)
    terminal_sessions[key] = {"ssh": ssh, "chan": chan, "reader_running": False}

    # Send, READ, decide (register B13). This used to send `enable`, the
    # secret and a newline on fixed 0.3 s sleeps without reading anything, so
    # on a device already at `#` (every device here: no enable secret is
    # configured and a privilege-15 user lands privileged) the secret arrived
    # as a COMMAND, was echoed to the browser, and was rejected as an unknown
    # host. The stored secret is the login password, so every terminal ever
    # opened put the device's login credential on screen.
    preamble, outcome = privilege_step(chan, enable_secret)
    terminal_sessions[key]["preamble"] = preamble
    logger.info("Terminal session ready for %s (privilege: %s)", ip, outcome)
    return chan


#: The last line of the buffer, as IOS draws a prompt: `s1>`, `r1#`,
#: `r1(config)#`. Anchored to the WHOLE last line: a banner can contain `#`.
_PROMPT = re.compile(r"^[\w.\-/:()]+([>#])\s*$")
_PASSWORD_PROMPT = re.compile(r"(?i)password:\s*$")


def _last_line(text: str) -> str:
    lines = text.replace("\r", "\n").rstrip().split("\n")
    return lines[-1].strip() if lines else ""


def _read_until(chan, want, timeout: float) -> tuple:
    """Read until *want* (a function of the last line) is true, or time out.

    Returns (text, matched). Reads as it goes, so a slow device is waited for
    and a fast one is not: the fixed sleeps this replaced were a guess about a
    network.
    """
    buf, deadline = "", time.monotonic() + timeout
    while time.monotonic() < deadline:
        if chan.recv_ready():
            buf += chan.recv(4096).decode("utf-8", errors="ignore")
            if want(_last_line(buf)):
                return buf, True
        else:
            time.sleep(0.05)
    return buf, False


def privilege_step(chan, enable_secret: str, timeout: float = 10.0) -> tuple:
    """Bring the shell to privileged EXEC, sending the secret ONLY if asked.

    Returns (everything read, outcome). Outcomes, all safe to log:

    - ``already_privileged``: a `#` prompt; NOTHING is sent;
    - ``enabled_without_prompt``: `enable` was sent and `#` came back;
    - ``enabled_with_secret``: a password prompt came back and the secret was
      sent, once;
    - ``secret_not_accepted``: sent once, and the device did not reach `#`;
      nothing more is sent, and the person sees the device's answer;
    - ``prompt_not_seen`` / ``enable_unanswered``: no recognisable prompt;
      nothing more is sent.

    The secret is never sent in any other state. A device that does not ask
    for it does not receive it.
    """
    is_prompt = lambda line: bool(_PROMPT.match(line))
    text, ok = _read_until(chan, is_prompt, timeout)
    if not ok:
        return text, "prompt_not_seen"
    if _PROMPT.match(_last_line(text)).group(1) == "#":
        return text, "already_privileged"

    chan.send("enable\n")
    more, ok = _read_until(
        chan, lambda line: bool(_PASSWORD_PROMPT.search(line) or _PROMPT.match(line)),
        timeout)
    text += more
    if not ok:
        return text, "enable_unanswered"
    last = _last_line(more)
    if not _PASSWORD_PROMPT.search(last):
        m = _PROMPT.match(last)
        return text, ("enabled_without_prompt" if m and m.group(1) == "#"
                      else "enable_unanswered")

    chan.send(enable_secret + "\n")
    more, ok = _read_until(
        chan, lambda line: bool(_PASSWORD_PROMPT.search(line) or _PROMPT.match(line)),
        timeout)
    text += more
    m = _PROMPT.match(_last_line(more)) if ok else None
    return text, ("enabled_with_secret" if m and m.group(1) == "#"
                  else "secret_not_accepted")


def start_terminal_reader(ip: str, terminal_sessions: dict, socketio: SocketIO,
                          key: str = "", room: str = "") -> None:
    """Starts a background thread reading ONE shell's output and emitting it to
    ONE room: the connection that owns the shell (D12). Both default to the
    address for a caller with no connection."""
    room = room or ip
    sess = terminal_sessions.get(key or ip)
    if not sess or not sess.get("chan"):
        return
    if sess.get("reader_running") and not sess["chan"].closed:
        return
    sess["reader_running"] = True

    def reader_loop():
        chan = sess["chan"]
        # What the privilege step read (banner, prompt) is the start of the
        # session; without this the browser would open on a blank screen.
        preamble = sess.pop("preamble", "")
        if preamble:
            socketio.emit("terminal_output", {"output": preamble}, room=room)
        while not chan.closed:
            try:
                if chan.recv_ready():
                    data = chan.recv(4096).decode("utf-8", errors="ignore")
                    # Emit data read from the remote shell to any clients
                    # currently subscribed to the terminal room; clients
                    # handle streaming output in the browser UI.
                    socketio.emit("terminal_output", {"output": data}, room=room)
                time.sleep(0.05)
            except Exception:
                logger.exception("Terminal reader error for %s", ip)
                break
        sess["reader_running"] = False

    threading.Thread(target=reader_loop, daemon=True).start()
