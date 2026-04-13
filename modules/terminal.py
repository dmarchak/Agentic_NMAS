"""terminal.py

Live interactive SSH terminal sessions via Paramiko and Flask-SocketIO.

`ensure_terminal_session` opens (or reuses) a Paramiko shell channel to a
device, enters enable mode, and stores the session in a caller-managed dict.
`start_terminal_reader` spawns a daemon thread that continuously reads from
the channel and emits data to the SocketIO room for that device IP, feeding the
xterm.js terminal in the browser in real time.
"""

import time
import threading
import logging
import paramiko
from flask_socketio import SocketIO
from modules.device import decrypt_field, load_saved_devices, get_current_device_list
from modules.config import SSH_PORT, SSH_TIMEOUT

logger = logging.getLogger(__name__)


def ensure_terminal_session(ip: str, terminal_sessions: dict) -> paramiko.Channel:
    """Ensures a live Paramiko SSH session/channel exists for the device IP."""
    # Reuse an existing channel if present and healthy; otherwise create
    # a new Paramiko SSH connection and shell channel and store it in
    # the `terminal_sessions` mapping for later reuse (and cleanup).
    sess = terminal_sessions.get(ip)
    if sess and sess.get("chan") and not sess["chan"].closed:
        logger.debug(f"Reusing existing terminal session for {ip}")
        return sess["chan"]

    # Clean up any stale session
    terminal_sessions.pop(ip, None)

    # Get the current device list file and load devices from it
    _, current_list_file = get_current_device_list()
    dev = next((d for d in load_saved_devices(current_list_file) if d["ip"] == ip), None)
    if not dev:
        raise RuntimeError(f"Device {ip} not found for terminal session")

    username = dev["username"]
    password = decrypt_field(dev["password"])
    secret = decrypt_field(dev["secret"])

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
    terminal_sessions[ip] = {"ssh": ssh, "chan": chan, "reader_running": False}

    # Send enable command and secret
    chan.send("enable\n")
    time.sleep(0.3)
    chan.send(secret + "\n")
    time.sleep(0.3)
    chan.send("\n")

    logger.info(f"Terminal session ready for {ip}")
    return chan


def start_terminal_reader(ip: str, terminal_sessions: dict, socketio: SocketIO) -> None:
    """Starts a background thread to read device terminal output and emit to Socket.IO client."""
    sess = terminal_sessions.get(ip)
    if not sess or not sess.get("chan"):
        return
    if sess.get("reader_running") and not sess["chan"].closed:
        return
    sess["reader_running"] = True

    def reader_loop():
        chan = sess["chan"]
        while not chan.closed:
            try:
                if chan.recv_ready():
                    data = chan.recv(4096).decode("utf-8", errors="ignore")
                    # Emit data read from the remote shell to any clients
                    # currently subscribed to the terminal room; clients
                    # handle streaming output in the browser UI.
                    socketio.emit("terminal_output", {"output": data}, room=ip)
                time.sleep(0.05)
            except Exception:
                logger.exception("Terminal reader error for %s", ip)
                break
        sess["reader_running"] = False

    threading.Thread(target=reader_loop, daemon=True).start()
