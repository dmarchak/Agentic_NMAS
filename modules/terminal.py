"""
terminal.py
Live terminal and session management for DeviceManager.
"""

import time
import threading
import logging
import paramiko
from flask_socketio import SocketIO
from modules.device import decrypt_field, load_saved_devices

logger = logging.getLogger(__name__)


def ensure_terminal_session(ip: str, terminal_sessions: dict) -> paramiko.Channel:
    """Ensures a live Paramiko SSH session/channel exists for the device IP."""
    # Reuse an existing channel if present and healthy; otherwise create
    # a new Paramiko SSH connection and shell channel and store it in
    # the `terminal_sessions` mapping for later reuse (and cleanup).
    sess = terminal_sessions.get(ip)
    if sess and sess.get("chan") and not sess["chan"].closed:
        return sess["chan"]
    terminal_sessions.pop(ip, None)
    dev = next((d for d in load_saved_devices() if d["ip"] == ip), None)
    if not dev:
        raise RuntimeError(f"Device {ip} not found for terminal session")
    username, password = dev["username"], decrypt_field(dev["password"])
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(ip, username=username, password=password)
    chan = ssh.invoke_shell()
    chan.setblocking(0)
    terminal_sessions[ip] = {"ssh": ssh, "chan": chan, "reader_running": False}
    chan.send("enable\n")
    time.sleep(0.2)
    chan.send(decrypt_field(dev["secret"]) + "\n")
    time.sleep(0.2)
    chan.send("\n")
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
