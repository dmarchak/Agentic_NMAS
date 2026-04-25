# Dustin Marchak
# Agentic Network Management
# Device Manager web application

# Load .env file if present (sets ANTHROPIC_API_KEY etc. without needing system env vars)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed; rely on system environment variables

# import libraries
from flask import (
    Flask, # core Flask class
    render_template, # for rendering HTML templates
    request, # to handle incoming requests
    redirect, # for HTTP redirects
    url_for, # to build URLs for routes
    flash, # to show one-time messages to users
    send_file, # to send files for download
    session, # for user session management
    jsonify # to return JSON responses
)

from flask_socketio import SocketIO, join_room, leave_room # for WebSocket support
import threading # for thread-safe connection pool
import os # for os operations
import json # for JSON serialization
import uuid # for generating unique operation IDs
import time # for sleep
import webbrowser # to open browser on start
import ipaddress # for IP address validation
import logging # for application logging
from logging.handlers import RotatingFileHandler # for log file rotation
from io import BytesIO # for in-memory file downloads

# Import Project modules
from modules.device import (
    load_saved_devices,
    save_device,
    write_devices_csv,
    get_device_context,
    get_device_lists,
    get_current_device_list,
    set_current_device_list,
    create_device_list,
    delete_device_list as delete_device_list_func
)
import modules.device as device_module
from modules.config import (
    BASE_DIR,
    PING_INTERVAL,
    SECRET_KEY_FILE,
    TFTP_ROOT,
    TFTP_SERVER_IP,
    FILE_TRANSFER_METHOD,
    FLASK_HOST,
    FLASK_PORT,
    FLASK_DEBUG,
    set_user_setting,
    get_user_setting,
    load_user_settings,
    save_user_settings,
)
from modules.connection import ping_worker, get_persistent_connection, close_persistent_connection, with_temp_connection, get_device_send_lock
from modules.terminal import ensure_terminal_session, start_terminal_reader
from modules.quick_actions import load_quick_actions, save_quick_actions
from modules.utils import make_device_filename
from modules.commands import run_device_command
from modules.backups import (
    save_running_to_startup,
    get_running_config,
    get_startup_config,
    save_config_backup,
    get_backup_history,
    get_backup_content,
    compare_configs,
    delete_backup,
    get_backup_stats
)
from modules.bulk_ops import bulk_manager
from modules.topology import discover_topology, shorten_interface

# Device status cache and ping worker setup
#
# `device_status_cache` is a lightweight in-memory mapping kept up to
# date by the background `ping_worker` thread. The web handlers read
# this cache to show online/offline state without performing blocking
# network I/O on each web request. `ping_worker` monitors the current
# device list file and re-reads the inventory when it changes.
device_status_cache = {}

def _get_current_devices_file():
    """Helper for ping_worker to get the current device list file."""
    _, filepath = get_current_device_list()
    return filepath

ping_worker(device_status_cache, filename=_get_current_devices_file, interval=PING_INTERVAL)

# Flask application and Socket.IO initialization
# Handle paths for both normal Python and PyInstaller frozen executable
import sys
if getattr(sys, 'frozen', False):
    # Running as compiled executable - use _MEIPASS for bundled resources
    bundle_dir = sys._MEIPASS
    template_folder = os.path.join(bundle_dir, 'templates')
    static_folder = os.path.join(bundle_dir, 'static')
    app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
else:
    # Running as normal Python script
    app = Flask(__name__)

# Load or generate persistent secret key
if os.path.exists(SECRET_KEY_FILE):
    with open(SECRET_KEY_FILE, "rb") as f:
        app.secret_key = f.read()
else:
    # Generate new secret key and persist it
    app.secret_key = os.urandom(24)
    with open(SECRET_KEY_FILE, "wb") as f:
        f.write(app.secret_key)

socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")

# Background daemons are started after all routes/functions are defined.
# See _start_background_daemons() called at the bottom of this file.

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------
if not app.debug:
    # Create logs directory if it doesn't exist (use BASE_DIR for frozen executable)
    logs_dir = os.path.join(BASE_DIR, 'logs')
    if not os.path.exists(logs_dir):
        os.mkdir(logs_dir)

    # Configure rotating file handler (10MB per file, keep 10 backups)
    file_handler = RotatingFileHandler(
        os.path.join(logs_dir, 'device_manager.log'),
        maxBytes=10240000,
        backupCount=10
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)

    app.logger.setLevel(logging.INFO)
    app.logger.info('Device Manager startup')

# ---------------------------------------------------------------------------
# Flask Error Handlers
# ---------------------------------------------------------------------------

@app.route("/favicon.ico")
def favicon():
    """Return empty response for favicon to avoid 404 warnings."""
    return "", 204

@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 Not Found errors."""
    app.logger.warning(f'Page not found: {request.url}')
    flash('Page not found', 'warning')
    return redirect(url_for('index'))

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 Internal Server errors."""
    app.logger.error(f'Server Error: {error}', exc_info=True)
    flash('An unexpected error occurred. Please try again.', 'danger')
    return redirect(url_for('index'))

@app.errorhandler(Exception)
def handle_exception(error):
    """Handle all uncaught exceptions."""
    app.logger.error(f'Unhandled Exception: {error}', exc_info=True)
    flash('An unexpected error occurred. Please check the logs.', 'danger')
    return redirect(url_for('index'))

# Reintroduce persistent connections container for status checks
# QUICK_ACTIONS_FILE provided by modules.config

connections = {}  # ip -> Netmiko connection (status-only)
terminal_sessions = {}
lock = threading.Lock()
_device_lock = get_device_send_lock  # serialises SSH commands per device


# ---------------------------------------------------------------------------
# Socket.IO event handlers (live terminal sessions)
#
# These handlers manage client requests to open/close live terminal
# sessions and to send typed input. They rely on the `terminal_sessions`
# container (a mapping of IP -> session objects) and the `modules.terminal`
# helpers which encapsulate Paramiko usage and background readers.
# ---------------------------------------------------------------------------


@socketio.on("connect_terminal")
def socket_connect_terminal(data):
    ip = data.get("ip")
    if not ip:
        return
    try:
        join_room(ip)

        # Ensure session is alive or recreate
        ensure_terminal_session(ip, terminal_sessions)
        start_terminal_reader(ip, terminal_sessions, socketio)

        socketio.emit(
            "terminal_output", {"output": f"\r\n[connected to {ip}]\r\n"}, room=ip
        )
    except Exception as e:
        socketio.emit(
            "terminal_output", {"output": f"\r\n[terminal error: {e}]\r\n"}, room=ip
        )


@socketio.on("terminal_input")
def socket_terminal_input(data):
    ip = data.get("ip")
    raw = data.get("input", "")
    if not ip:
        return
    try:
        sess = terminal_sessions.get(ip)
        if not sess:
            ensure_terminal_session(ip, terminal_sessions)
            sess = terminal_sessions.get(ip)
        if raw and sess and sess.get("chan"):
            sess["chan"].sendall(raw)
    except Exception as e:
        socketio.emit(
            "terminal_output", {"output": f"\r\n[input error: {e}]\r\n"}, room=ip
        )


@socketio.on("disconnect_terminal")
def socket_disconnect_terminal(data):
    ip = data.get("ip")
    try:
        leave_room(ip)
    except Exception:
        pass
    sess = terminal_sessions.pop(ip, None)
    if sess:
        try:
            if sess.get("chan"):
                sess["chan"].close()
            if sess.get("ssh"):
                sess["ssh"].close()
        except Exception:
            pass
    socketio.emit(
        "terminal_output", {"output": f"\r\n[disconnected from {ip}]\r\n"}, room=ip
    )


# ---------------------------------------------------------------------------
# Flask HTTP routes
#
# The following route handlers implement the web UI and REST endpoints.
# Each route is kept deliberately thin: heavy lifting (connections,
# inventory management, quick actions) is performed by functions in
# the `modules/` package so the web layer stays easy to test and
# reason about.
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    # Home page: show all devices and their online status
    current_list_name, current_list_file = get_current_device_list()
    devices = load_saved_devices(current_list_file)
    for d in devices:
        d["online"] = device_status_cache.get(d["ip"], False)

    # Get all device lists for the dropdown
    device_lists = get_device_lists()

    no_api_key = not bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())

    return render_template(
        "index.html",
        devices=devices,
        device_lists=device_lists,
        current_list=current_list_name,
        tftp_server=TFTP_SERVER_IP,
        no_api_key=no_api_key
    )


# Add device
@app.route("/add", methods=["POST"])
def add_device():
    # Add a new device to inventory after verifying connection
    ip = request.form["ip"].strip()
    username = request.form["username"].strip()
    password = request.form["password"]
    secret = request.form["secret"]

    # Get current device list
    current_list_name, current_list_file = get_current_device_list()

    app.logger.info(f'Attempting to add device: {ip} with username: {username} to list: {current_list_name}')

    # Validate IP address format
    try:
        ip_obj = ipaddress.ip_address(ip)

        # Reject invalid IP types
        if ip_obj.is_unspecified:
            app.logger.warning(f'Rejected unspecified IP address: {ip}')
            flash("Invalid IP: Cannot use unspecified address (0.0.0.0 or ::)", "danger")
            return redirect(url_for("index"))
        if ip_obj.is_loopback:
            app.logger.warning(f'Rejected loopback IP address: {ip}')
            flash("Invalid IP: Cannot use loopback address (127.0.0.0/8 or ::1)", "danger")
            return redirect(url_for("index"))
        if ip_obj.is_multicast:
            app.logger.warning(f'Rejected multicast IP address: {ip}')
            flash("Invalid IP: Cannot use multicast address", "danger")
            return redirect(url_for("index"))
        if ip_obj.is_reserved:
            app.logger.warning(f'Rejected reserved IP address: {ip}')
            flash("Invalid IP: Cannot use reserved address", "danger")
            return redirect(url_for("index"))

    except ValueError as e:
        app.logger.warning(f'Invalid IP address format: {ip} - {e}')
        flash(f"Invalid IP address format: {ip}", "danger")
        return redirect(url_for("index"))

    # Validate username and password are not empty
    if not username:
        app.logger.warning(f'Empty username provided for IP: {ip}')
        flash("Username cannot be empty", "danger")
        return redirect(url_for("index"))
    if not password:
        app.logger.warning(f'Empty password provided for IP: {ip}')
        flash("Password cannot be empty", "danger")
        return redirect(url_for("index"))

    # Check for duplicate IP in current list
    devices = load_saved_devices(current_list_file)
    if any(d["ip"] == ip for d in devices):
        app.logger.warning(f'Duplicate device IP detected: {ip}')
        flash(f"Device with IP {ip} already exists in '{current_list_name}'", "warning")
        return redirect(url_for("index"))

    try:
        from modules.connection import verify_device_connection

        app.logger.info(f'Verifying connection to device: {ip}')
        hostname = verify_device_connection(ip, username, password, secret)

        role = request.form.get("role", "router").strip() or "router"
        if role not in ("router", "switch", "firewall"):
            role = "router"
        save_device(
            {
                "device_type": "cisco_ios",
                "ip": ip,
                "username": username,
                "password": password,
                "secret": secret,
                "hostname": hostname,
                "role": role,
            },
            current_list_file,
        )
        app.logger.info(f'Device added successfully: {hostname} ({ip})')
        flash(f"Device {hostname} ({ip}) added successfully!", "success")
    except Exception as e:
        app.logger.error(f'Failed to add device {ip}: {e}', exc_info=True)
        flash(f"Error connecting to {ip}: {e}", "danger")
    return redirect(url_for("index"))


# Manage device (no persistent use; only builds context via temp connection)
@app.route("/device/<ip>")
def manage_device(ip):
    # Device management page: show filesystems, files, quick actions
    _, current_list_file = get_current_device_list()
    devices = load_saved_devices(current_list_file)
    dev = next((d for d in devices if d["ip"] == ip), None)
    if not dev:
        flash("Device not found", "danger")
        return redirect(url_for("index"))

    # Get active tab from query parameter
    active_tab = request.args.get("active_tab", "utilities")

    try:
        filesystems, file_list, selected_fs = get_device_context(dev)
        return render_template(
            "device.html",
            device=dev,
            filesystems=filesystems,
            files=file_list,
            selected_fs=selected_fs,
            quick_actions=load_quick_actions().get("global", []),
            active_tab=active_tab,
            tftp_server=TFTP_SERVER_IP,
            no_api_key=not bool(os.environ.get("ANTHROPIC_API_KEY", "").strip()),
        )
    except Exception as e:
        flash(f"Failed to connect to {dev.get('hostname', ip)} ({ip}): {e}", "danger")
        return redirect(url_for("index"))


# Run command (temporary connection)
@app.route("/run_command/<ip>")
def run_command(ip):
    # Run a command on the device and show output
    command = request.args.get("command")
    filesystem = request.args.get("filesystem")

    _, current_list_file = get_current_device_list()
    devices = load_saved_devices(current_list_file)
    dev = next((d for d in devices if d["ip"] == ip), None)
    if not dev:
        flash("Device not found", "danger")
        return redirect(url_for("index"))

    if not command:
        flash("No command provided.", "warning")
        return redirect(url_for("manage_device", ip=ip))

    try:
        output = None

        # Attempt persistent connection first
        try:
            conn = get_persistent_connection(dev, connections, lock)
            output = run_device_command(conn, command)
        except Exception:
            # Fallback to temporary connection
            output = with_temp_connection(dev, lambda conn: run_device_command(conn, command))

        # Save output for download
        session["last_output"] = output
        session["last_filename"] = f"{dev['hostname']}_{command.replace(' ', '_')}.txt"

        # If AJAX request, return JSON with output only to avoid full page render
        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        if is_ajax:
            return jsonify({"output": output, "filename": session["last_filename"]})

        # Non-AJAX: refresh device context and render template as before
        filesystems, file_list, selected_fs = get_device_context(dev, filesystem)

        return render_template(
            "device.html",
            device=dev,
            filesystems=filesystems,
            files=file_list,
            selected_fs=selected_fs,
            output=output,
            filename=session["last_filename"],
            active_tab="utilities",
            quick_actions=load_quick_actions().get("global", []),
            tftp_server=TFTP_SERVER_IP,
        )
    except Exception as e:
        flash(
            f"Failed to run command on {dev.get('hostname', ip)} ({dev['ip']}): {e}",
            "danger",
        )
        return redirect(url_for("index"))


# JSON API: execute a single command on a device (used by Jenkins pipelines)
@app.route("/execute_command", methods=["POST"])
def api_execute_command():
    """Execute a single IOS command and return JSON output.

    Expects JSON body: {"ip": "...", "command": "...", "mode": "enable|config"}
    Returns: {"output": "...", "error": null} or {"output": null, "error": "..."}
    """
    data = request.get_json(silent=True) or {}
    ip = data.get("ip")
    command = data.get("command")
    mode = data.get("mode", "enable")

    if not ip or not command:
        return jsonify({"output": None, "error": "ip and command are required"}), 400

    _, current_list_file = get_current_device_list()
    devices = load_saved_devices(current_list_file)
    dev = next((d for d in devices if d["ip"] == ip), None)
    if not dev:
        return jsonify({"output": None, "error": f"Device {ip} not found"}), 404

    try:
        if mode == "config":
            def execute_config(conn):
                conn.config_mode()
                result = run_device_command(conn, command)
                try:
                    conn.exit_config_mode()
                except Exception:
                    pass
                return result
            output = with_temp_connection(dev, execute_config)
        else:
            try:
                conn = get_persistent_connection(dev, connections, lock)
                output = run_device_command(conn, command)
            except Exception:
                output = with_temp_connection(dev, lambda c: run_device_command(c, command))

        return jsonify({"output": output, "error": None})
    except Exception as e:
        return jsonify({"output": None, "error": str(e)}), 500


# Run script (temporary connection for each command or config mode block)
@app.route("/run_script/<ip>", methods=["POST"])
def run_script(ip):
    # Run a multi-line script on the device
    script = request.form.get("script")
    mode = request.form.get("mode")
    filesystem = request.form.get("filesystem")

    _, current_list_file = get_current_device_list()
    devices = load_saved_devices(current_list_file)
    dev = next((d for d in devices if d["ip"] == ip), None)
    if not dev:
        flash("Device not found", "danger")
        return redirect(url_for("index"))

    if not script:
        flash("No script provided.", "warning")
        return redirect(url_for("manage_device", ip=ip))

    try:
        # If config mode, run all commands in a single temp connection with config mode entered
        if mode == "config":

            def execute_config(conn):
                conn.config_mode()
                collected = []
                for line in script.splitlines():
                    cmd = line.strip()
                    if not cmd:
                        continue
                    result = run_device_command(conn, cmd)
                    collected.append(f"{cmd}:\n{result}\n")
                try:
                    conn.exit_config_mode()
                except Exception:
                    pass
                return "".join(collected)

            output = with_temp_connection(dev, execute_config)

        else:
            # Reuse a single temporary connection for the entire script to
            # avoid reconnecting for each line. This greatly speeds up
            # multi-line scripts where creating a new SSH session per line
            # is the dominant cost.
            lines = [line.strip() for line in script.splitlines() if line.strip()]

            def execute_all(conn):
                collected = []
                for cmd in lines:
                    try:
                        result = run_device_command(conn, cmd)
                    except Exception as e:
                        result = f"ERROR: {e}"
                    collected.append(f"{cmd}:\n{result}\n")
                return "\n".join(collected)

            output = with_temp_connection(dev, execute_all)

        # Save output for download
        session["last_output"] = output
        session["last_filename"] = f"{dev['hostname']}_script_output.txt"

        filesystems, file_list, selected_fs = get_device_context(dev, filesystem)

        return render_template(
            "device.html",
            device=dev,
            filesystems=filesystems,
            files=file_list,
            selected_fs=selected_fs,
            output=output,
            filename=session["last_filename"],
            active_tab="scripts",
            quick_actions=load_quick_actions().get("global", []),
            tftp_server=TFTP_SERVER_IP,
        )
    except Exception as e:
        flash(
            f"Failed to run script on {dev.get('hostname', ip)} ({dev['ip']}): {e}",
            "danger",
        )
        return redirect(url_for("index"))


# Download last output
@app.route("/download")
def download_file():
    # Download the last command/script output
    output = session.get("last_output")
    filename = session.get("last_filename", "Device_Output.txt")

    if not output:
        flash("No output available to download", "warning")
        return redirect(url_for("index"))

    buffer = BytesIO(output.encode())
    return send_file(
        buffer, as_attachment=True, download_name=filename, mimetype="text/plain"
    )


# File upload (TFTP or SCP based on configuration)
@app.route("/device/<ip>/upload", methods=["POST"])
def upload_file(ip):
    """Upload a file to the device via TFTP or SCP."""
    app.logger.info(f'File upload requested for device: {ip}')

    _, current_list_file = get_current_device_list()
    devices = load_saved_devices(current_list_file)
    dev = next((d for d in devices if d["ip"] == ip), None)
    if not dev:
        flash("Device not found", "danger")
        return redirect(url_for("index"))

    file = request.files.get("file")
    filesystem = request.form.get("filesystem")
    tftp_server = request.form.get("tftp_server", TFTP_SERVER_IP) or TFTP_SERVER_IP

    if not file:
        flash("No file selected", "danger")
        return redirect(url_for("manage_device", ip=ip))

    try:
        if FILE_TRANSFER_METHOD.lower() == "scp":
            # SCP transfer - more reliable and secure
            app.logger.info(f'Using SCP to upload {file.filename} to {ip}')

            # Save file temporarily
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                file.save(tmp.name)
                local_path = tmp.name

            try:
                def execute_scp(conn):
                    # Use Netmiko's built-in SCP support
                    from netmiko import file_transfer

                    transfer_dict = file_transfer(
                        conn,
                        source_file=local_path,
                        dest_file=file.filename,
                        file_system=filesystem,
                        direction='put',
                        overwrite_file=True
                    )

                    if transfer_dict['file_verified']:
                        return f"SCP transfer successful: {file.filename}\n{transfer_dict}"
                    else:
                        raise Exception("File verification failed after transfer")

                output = with_temp_connection(dev, execute_scp)
                app.logger.info(f'SCP upload successful: {file.filename} to {ip}')
                flash(f"File {file.filename} uploaded via SCP to {filesystem}", "success")

            finally:
                # Clean up temporary file
                if os.path.exists(local_path):
                    os.remove(local_path)

        else:
            # TFTP transfer - requires external TFTP server
            app.logger.info(f'Using TFTP to upload {file.filename} to {ip}')

            # Save to local TFTP root (configured in modules.config)
            local_path = os.path.join(TFTP_ROOT, file.filename)
            file.save(local_path)

            def execute_tftp(conn):
                # IOS expects just the destination filesystem here; filenames are prompted interactively
                output = conn.send_command_timing(f"copy tftp: {filesystem}")
                output += conn.send_command_timing(tftp_server)
                output += conn.send_command_timing(file.filename)
                output += conn.send_command_timing(file.filename)
                output += conn.send_command_timing("\n")
                return output

            output = with_temp_connection(dev, execute_tftp)
            app.logger.info(f'TFTP upload successful: {file.filename} to {ip}')
            flash(f"File {file.filename} uploaded via TFTP to {filesystem}", "success")

        # Give IOS a moment before re-listing files
        time.sleep(3)
        filesystems, file_list, selected_fs = get_device_context(dev, filesystem)

        return render_template(
            "device.html",
            device=dev,
            filesystems=filesystems,
            files=file_list,
            selected_fs=selected_fs,
            output=output,
            filename=None,
            active_tab="files",
            quick_actions=load_quick_actions().get("global", []),
            tftp_server=TFTP_SERVER_IP,
        )
    except Exception as e:
        app.logger.error(f'File upload failed for {ip}: {e}', exc_info=True)

        # Provide helpful error message for SCP privilege issues
        error_msg = str(e)
        if "Privilege denied" in error_msg or "scp" in error_msg.lower():
            flash(
                f"SCP upload failed: {error_msg}. "
                "Please ensure SCP is enabled on the device with 'ip scp server enable'. "
                "Alternatively, switch to TFTP in modules/config.py by setting FILE_TRANSFER_METHOD = 'tftp'",
                "danger"
            )
        else:
            flash(f"File upload failed: {e}", "danger")
        return redirect(url_for("manage_device", ip=ip))


# Delete file (temporary connection)
@app.route("/device/<ip>/delete_file", methods=["POST"])
def delete_file(ip):
    # Delete a file from the device filesystem
    filename = request.form.get("filename")
    filesystem = request.form.get("filesystem")

    _, current_list_file = get_current_device_list()
    devices = load_saved_devices(current_list_file)
    dev = next((d for d in devices if d["ip"] == ip), None)
    if not dev:
        flash("Device not found", "danger")
        return redirect(url_for("index"))

    if not filename:
        flash("No filename provided", "warning")
        return redirect(url_for("manage_device", ip=ip))

    try:

        def execute(conn):
            command = f"delete {filesystem}{filename}"
            output = conn.send_command_timing(command)
            output += conn.send_command_timing("")  # confirm deletion
            time.sleep(1)
            # Show updated dir output in the card
            output += "\n" + conn.send_command(f"dir {filesystem}")
            return output

        output = with_temp_connection(dev, execute)

        filesystems, file_list, selected_fs = get_device_context(dev, filesystem)

        flash(f"File {filename} deleted from {filesystem}", "success")
        return render_template(
            "device.html",
            device=dev,
            filesystems=filesystems,
            files=file_list,
            selected_fs=selected_fs,
            output=output,
            filename=None,
            active_tab="files",
            quick_actions=load_quick_actions().get("global", []),
            tftp_server=TFTP_SERVER_IP,
        )
    except Exception as e:
        flash(f"Delete failed: {e}", "danger")
        return redirect(url_for("manage_device", ip=ip))


# Download file to TFTP server (temporary connection)
@app.route("/device/<ip>/download_file", methods=["POST"])
def download_device_file(ip):
    """Download a file from the device to TFTP server."""
    filename = request.form.get("filename")
    filesystem = request.form.get("filesystem")
    tftp_server = request.form.get("tftp_server", TFTP_SERVER_IP) or TFTP_SERVER_IP

    _, current_list_file = get_current_device_list()
    devices = load_saved_devices(current_list_file)
    dev = next((d for d in devices if d["ip"] == ip), None)
    if not dev:
        flash("Device not found", "danger")
        return redirect(url_for("index"))

    if not filename:
        flash("No filename provided", "warning")
        return redirect(url_for("manage_device", ip=ip))

    try:
        hostname = dev.get("hostname", dev.get("ip", "device"))
        remote_filename = f"{hostname}_{filename}"

        def execute(conn):
            # copy flash:filename tftp://server/remote_filename
            output = conn.send_command_timing(f"copy {filesystem}{filename} tftp:")
            output += conn.send_command_timing(tftp_server)
            output += conn.send_command_timing(remote_filename)
            output += conn.send_command_timing("\n")
            return output

        output = with_temp_connection(dev, execute)

        filesystems, file_list, selected_fs = get_device_context(dev, filesystem)

        flash(f"File {filename} downloaded to TFTP server as {remote_filename}", "success")
        return render_template(
            "device.html",
            device=dev,
            filesystems=filesystems,
            files=file_list,
            selected_fs=selected_fs,
            output=output,
            filename=None,
            active_tab="files",
            quick_actions=load_quick_actions().get("global", []),
            tftp_server=TFTP_SERVER_IP,
        )
    except Exception as e:
        flash(f"Download failed: {e}", "danger")
        return redirect(url_for("manage_device", ip=ip))


# Refresh files (temporary connection via get_device_context)
@app.route("/device/<ip>/refresh_files", methods=["POST"])
def refresh_files(ip):
    # Refresh the file list for the device filesystem
    filesystem = request.form.get("filesystem")

    _, current_list_file = get_current_device_list()
    devices = load_saved_devices(current_list_file)
    dev = next((d for d in devices if d["ip"] == ip), None)
    if not dev:
        flash("Device not found", "danger")
        return redirect(url_for("index"))

    try:
        filesystems, file_list, selected_fs = get_device_context(dev, filesystem)
        flash(f"File list refreshed for {selected_fs}", "info")
        return render_template(
            "device.html",
            device=dev,
            filesystems=filesystems,
            files=file_list,
            selected_fs=selected_fs,
            output="",
            filename=None,
            active_tab="files",
            quick_actions=load_quick_actions().get("global", []),
            tftp_server=TFTP_SERVER_IP,
        )
    except Exception as e:
        flash(f"Failed to refresh files: {e}", "danger")
        return redirect(url_for("manage_device", ip=ip))


# Delete device (CSV)
@app.route("/device/<ip>/delete", methods=["POST"])
def delete_device(ip):
    app.logger.info(f'Attempting to delete device: {ip}')
    _, current_list_file = get_current_device_list()
    try:
        # Delete from CSV using the device module helper
        device_module.delete_device(ip, current_list_file)
        # Also close any persistent connection for this IP (status-only pool)
        close_persistent_connection(ip, connections, lock)
        # Close any live terminal session (Paramiko)
        sess = terminal_sessions.get(ip)
        if sess:
            try:
                if sess.get("chan"):
                    sess["chan"].close()
                if sess.get("ssh"):
                    sess["ssh"].close()
            except Exception as e:
                app.logger.warning(f'Error closing terminal session for {ip}: {e}')
            terminal_sessions.pop(ip, None)
        # Purge the deleted device from the cached topologies so it stops
        # appearing in the topology map without needing a full rediscovery.
        try:
            _ai.invalidate_topology_cache()
        except Exception:
            pass
        for _cache_file in (_proto_cache_file(), _proto_pos_file(), _proto_hidden_file()):
            try:
                if os.path.exists(_cache_file):
                    os.remove(_cache_file)
            except Exception:
                pass
        app.logger.info(f'Device deleted successfully: {ip}')
        flash(f"Device {ip} deleted successfully.", "success")
    except Exception as e:
        app.logger.error(f'Failed to delete device {ip}: {e}', exc_info=True)
        flash(f"Error deleting device {ip}: {e}", "danger")
    return redirect(url_for("index"))


# Device status (from cache)
@app.route("/status/<ip>")
def device_status(ip):
    # Return online status for a device
    online = device_status_cache.get(ip, False)
    return {"ip": ip, "online": online}


# Save running config (temporary connection)
@app.route("/device/<ip>/save_config", methods=["POST"])
def save_config(ip):
    # Save the running config on the device
    active_tab = request.form.get("active_tab", "utilities")

    _, current_list_file = get_current_device_list()
    devices = load_saved_devices(current_list_file)
    dev = next((d for d in devices if d["ip"] == ip), None)
    if not dev:
        flash("Device not found", "danger")
        return redirect(url_for("index"))

    try:

        def execute(conn):
            # Ensure not stuck in config mode
            if conn.check_config_mode():
                conn.exit_config_mode()
            output = conn.send_command_timing("write memory")
            if "[confirm]" in output.lower() or "confirm?" in output.lower():
                output += conn.send_command_timing("\n")
            return output

        output = with_temp_connection(dev, execute)

        filename = make_device_filename(dev["hostname"])
        filesystems, file_list, selected_fs = get_device_context(dev)

        return render_template(
            "device.html",
            device=dev,
            output=output,
            filename=filename,
            filesystems=filesystems,
            files=file_list,
            selected_fs=selected_fs,
            active_tab=active_tab,
            quick_actions=load_quick_actions().get("global", []),
            tftp_server=TFTP_SERVER_IP,
        )
    except Exception as e:
        flash(f"Error saving config: {e}", "danger")
        return redirect(url_for("manage_device", ip=ip))


# Reorder devices (CSV rewrite)
@app.route("/reorder", methods=["POST"])
def reorder_devices():
    # Reorder devices in current device list based on new order
    new_order = request.get_json()
    if not new_order:
        return {"status": "error", "message": "No order received"}, 400

    _, current_list_file = get_current_device_list()
    devices = load_saved_devices(current_list_file)
    ip_to_device = {d["ip"]: d for d in devices}
    reordered = [ip_to_device[ip] for ip in new_order if ip in ip_to_device]

    write_devices_csv(reordered, current_list_file)
    return {"status": "success"}


# ---------------------------------------------------------------------------
# Device List Management Routes
# ---------------------------------------------------------------------------

@app.route("/device_lists", methods=["GET"])
def get_device_lists_route():
    """Get all device lists."""
    try:
        lists = get_device_lists()
        current_name, _ = get_current_device_list()
        return jsonify({
            "status": "success",
            "lists": lists,
            "current": current_name
        })
    except Exception as e:
        app.logger.error(f"Failed to get device lists: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/device_lists", methods=["POST"])
def create_device_list_route():
    """Create a new device list."""
    try:
        data = request.get_json()
        list_name = data.get("name", "").strip() if data else ""

        if not list_name:
            return jsonify({"status": "error", "message": "List name is required"}), 400

        success, message = create_device_list(list_name)

        if success:
            app.logger.info(f"Created device list: {list_name}")
            return jsonify({"status": "success", "message": message})
        else:
            return jsonify({"status": "error", "message": message}), 400

    except Exception as e:
        app.logger.error(f"Failed to create device list: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/device_lists/<list_name>", methods=["DELETE"])
def delete_device_list_route(list_name):
    """Delete a device list and all associated external data."""
    cleanup_log = []

    # ── 1. Delete Jenkins pipelines ────────────────────────────────────────
    try:
        from modules.config import get_list_data_dir
        from modules.jenkins_runner import load_config as _jcfg, delete_jenkins_job

        list_dir       = get_list_data_dir(list_name)
        pipelines_path = os.path.join(list_dir, "jenkins_pipelines.json")
        job_names: list = []
        if os.path.exists(pipelines_path):
            with open(pipelines_path, encoding="utf-8") as _fh:
                job_names = json.load(_fh).get("pipelines", [])

        if job_names:
            jcfg = _jcfg()
            deleted_jobs, failed_jobs = [], []
            for job in job_names:
                try:
                    delete_jenkins_job(jcfg, job)
                    deleted_jobs.append(job)
                    app.logger.info("list delete: removed Jenkins job '%s'", job)
                except Exception as exc:
                    failed_jobs.append(job)
                    app.logger.warning("list delete: could not remove Jenkins job '%s': %s", job, exc)
            msg = f"Jenkins: deleted {len(deleted_jobs)} job(s)"
            if failed_jobs:
                msg += f", {len(failed_jobs)} could not be reached ({', '.join(failed_jobs)})"
            cleanup_log.append(msg)
    except Exception as exc:
        app.logger.warning("list delete: Jenkins cleanup failed: %s", exc)
        cleanup_log.append(f"Jenkins cleanup skipped: {exc}")

    # ── 2. Remove from NetBox ──────────────────────────────────────────────
    try:
        from modules.netbox_client import remove_list_from_netbox, get_netbox_config
        nbcfg = get_netbox_config()
        if nbcfg.get("url") and nbcfg.get("token"):
            nb_result = remove_list_from_netbox(list_name)
            if nb_result.get("ok"):
                cleanup_log.append(
                    f"NetBox: removed {nb_result.get('deleted_devices', 0)} device(s), "
                    f"site={nb_result.get('deleted_site')}, region={nb_result.get('deleted_region')}"
                )
            else:
                cleanup_log.append(f"NetBox removal partial: {nb_result.get('error', 'unknown')}")
        else:
            cleanup_log.append("NetBox: not configured — skipped")
    except Exception as exc:
        app.logger.warning("list delete: NetBox cleanup failed: %s", exc)
        cleanup_log.append(f"NetBox cleanup skipped: {exc}")

    # ── 3. Delete the list directory and config entry ──────────────────────
    try:
        success, message = delete_device_list_func(list_name)
        if success:
            app.logger.info("Deleted device list '%s'. Cleanup: %s", list_name,
                            " | ".join(cleanup_log))
            flash(message, "success")
            return jsonify({
                "status":  "success",
                "message": message,
                "cleanup": cleanup_log,
            })
        else:
            return jsonify({"status": "error", "message": message}), 400
    except Exception as e:
        app.logger.error("Failed to delete device list '%s': %s", list_name, e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/select_device_list", methods=["POST"])
def select_device_list_route():
    """Select a device list as the current list."""
    try:
        data = request.get_json()
        list_name = data.get("name", "").strip() if data else ""

        if not list_name:
            return jsonify({"status": "error", "message": "List name is required"}), 400

        success = set_current_device_list(list_name)

        if success:
            app.logger.info(f"Selected device list: {list_name}")
            # Reset the event monitor's build-state cache so the new list
            # starts fresh and doesn't inherit stale Jenkins state from the
            # previous list.
            from modules.event_monitor import clear_events
            clear_events()
            # Reload per-list collector buffers so the monitoring tab shows
            # only traps and flows belonging to the newly selected list.
            try:
                from modules.snmp_collector import switch_list as snmp_switch
                snmp_switch()
            except Exception as _e:
                app.logger.debug("snmp switch_list: %s", _e)
            try:
                from modules.netflow_collector import switch_list as nf_switch
                nf_switch()
            except Exception as _e:
                app.logger.debug("netflow switch_list: %s", _e)
            return jsonify({"status": "success", "message": f"Switched to '{list_name}'"})
        else:
            return jsonify({"status": "error", "message": f"List '{list_name}' not found"}), 404

    except Exception as e:
        app.logger.error(f"Failed to select device list: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/save_tftp_server", methods=["POST"])
def save_tftp_server():
    """Save TFTP server address to user settings."""
    global TFTP_SERVER_IP
    try:
        data = request.get_json()
        tftp_server = data.get("tftp_server", "").strip() if data else ""

        if not tftp_server:
            return jsonify({"status": "error", "message": "TFTP server address is required"}), 400

        # Validate IP address format (basic check)
        try:
            parts = tftp_server.split(".")
            if len(parts) == 4 and all(0 <= int(p) <= 255 for p in parts):
                pass  # Valid IPv4
            else:
                return jsonify({"status": "error", "message": "Invalid IP address format"}), 400
        except (ValueError, AttributeError):
            return jsonify({"status": "error", "message": "Invalid IP address format"}), 400

        # Save to user settings
        if set_user_setting("tftp_server_ip", tftp_server):
            # Update the module-level variable for current session
            import modules.config as config_module
            config_module.TFTP_SERVER_IP = tftp_server
            TFTP_SERVER_IP = tftp_server

            app.logger.info(f"TFTP server address saved: {tftp_server}")
            return jsonify({
                "status": "success",
                "message": f"TFTP server address saved: {tftp_server}"
            })
        else:
            return jsonify({"status": "error", "message": "Failed to save settings"}), 500

    except Exception as e:
        app.logger.error(f"Failed to save TFTP server: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# Default values for all workflow flags (all on, except require_approval)
_WF_DEFAULTS = {
    "wf_read_first":       True,
    "wf_auto_backup":      True,
    "wf_run_jenkins":      True,
    "wf_save_golden":      True,
    "wf_update_vars":      True,
    "wf_require_approval": False,
}

def _load_workflow_flags() -> dict:
    """Return workflow flags from user settings, falling back to defaults."""
    s = load_user_settings()
    return {k: s.get(k, v) for k, v in _WF_DEFAULTS.items()}


def _ai_enabled() -> bool:
    """Master switch for AI — when False, chat and agent endpoints are blocked."""
    return bool(load_user_settings().get("ai_enabled", True))


@app.context_processor
def _inject_ai_enabled():
    """Inject ai_enabled into every template so it can be server-rendered."""
    return {"ai_enabled": _ai_enabled()}


@app.route("/settings", methods=["GET"])
def get_settings():
    """Return all configurable global settings in one payload."""
    import modules.jenkins_runner as _jr
    from modules.netbox_client import get_netbox_config as _get_nb_cfg
    jcfg  = _jr.load_config()
    nbcfg = _get_nb_cfg()
    payload = {
        "anthropic_api_key": os.environ.get("ANTHROPIC_API_KEY", ""),
        "jenkins_url":       jcfg.get("jenkins_url", ""),
        "jenkins_user":      jcfg.get("jenkins_user", ""),
        "jenkins_api_key":   jcfg.get("jenkins_api_key", ""),
        "jenkins_token":     jcfg.get("jenkins_token", ""),
        "tftp_server_ip":    TFTP_SERVER_IP,
        # NetBox — token never returned in cleartext; UI uses token_set flag.
        "netbox_url":         nbcfg.get("url", ""),
        "netbox_token_set":   bool(nbcfg.get("token")),
        "netbox_verify_tls":  bool(nbcfg.get("verify_tls", True)),
        "netbox_auth_scheme": nbcfg.get("auth_scheme", "Bearer"),
        "ai_enabled":              _ai_enabled(),
        "background_agent_enabled": bool(load_user_settings().get("background_agent_enabled", True)),
    }
    payload.update(_load_workflow_flags())
    return jsonify(payload)


@app.route("/settings", methods=["POST"])
def save_settings():
    """Save all global settings submitted from the Settings modal."""
    global TFTP_SERVER_IP
    import modules.config as config_module
    import modules.jenkins_runner as _jr

    data = request.get_json(silent=True) or {}
    errors = []

    # ── Anthropic API key ─────────────────────────────────────────────────
    api_key = data.get("anthropic_api_key", "").strip()
    if api_key:
        os.environ["ANTHROPIC_API_KEY"] = api_key
        # Persist to .env so it survives restarts
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        try:
            lines = []
            replaced = False
            if os.path.exists(env_path):
                with open(env_path, "r", encoding="utf-8") as fh:
                    lines = fh.readlines()
                for i, line in enumerate(lines):
                    if line.startswith("ANTHROPIC_API_KEY="):
                        lines[i] = f"ANTHROPIC_API_KEY={api_key}\n"
                        replaced = True
            if not replaced:
                lines.append(f"ANTHROPIC_API_KEY={api_key}\n")
            with open(env_path, "w", encoding="utf-8") as fh:
                fh.writelines(lines)
            # Reset cached Anthropic client so it picks up the new key
            import modules.ai_assistant as _ai_mod
            _ai_mod._anthropic_client = None
        except Exception as exc:
            errors.append(f"API key saved to env but .env write failed: {exc}")

    # ── Jenkins settings ──────────────────────────────────────────────────
    jenkins_fields = ("jenkins_url", "jenkins_user", "jenkins_api_key", "jenkins_token")
    if any(k in data for k in jenkins_fields):
        try:
            jcfg = _jr.load_config()
            for field in jenkins_fields:
                if field in data:
                    jcfg[field] = data[field].strip()
            _jr.save_config(jcfg)
        except Exception as exc:
            errors.append(f"Jenkins settings failed: {exc}")

    # ── TFTP server IP ────────────────────────────────────────────────────
    tftp = data.get("tftp_server_ip", "").strip()
    if tftp:
        try:
            parts = tftp.split(".")
            if not (len(parts) == 4 and all(0 <= int(p) <= 255 for p in parts)):
                errors.append("Invalid TFTP server IP address format.")
            else:
                set_user_setting("tftp_server_ip", tftp)
                config_module.TFTP_SERVER_IP = tftp
                TFTP_SERVER_IP = tftp
        except Exception as exc:
            errors.append(f"TFTP setting failed: {exc}")

    # ── NetBox ────────────────────────────────────────────────────────────
    if any(k in data for k in ("netbox_url", "netbox_token", "netbox_verify_tls")):
        try:
            from modules.netbox_client import save_netbox_config, get_netbox_config
            existing = get_netbox_config()
            url   = (data.get("netbox_url",   existing.get("url",   "")) or "").strip()
            token = (data.get("netbox_token", "") or "").strip()
            # Blank token = keep the one on file (matches other secret fields).
            if not token:
                token = existing.get("token", "")
            verify_tls = data.get("netbox_verify_tls", existing.get("verify_tls", True))
            if url and not token:
                errors.append("NetBox token is required the first time you save a URL.")
            else:
                save_netbox_config(url, token, bool(verify_tls))
        except Exception as exc:
            errors.append(f"NetBox settings failed: {exc}")

    # ── AI master switch + background agent + workflow flags ──────────────
    try:
        s = load_user_settings()
        if "ai_enabled" in data:
            s["ai_enabled"] = bool(data["ai_enabled"])
        if "background_agent_enabled" in data:
            s["background_agent_enabled"] = bool(data["background_agent_enabled"])
            # Pause/resume the running thread immediately without a restart.
            try:
                from modules.agent_runner import pause_agent, resume_agent
                if s["background_agent_enabled"]:
                    resume_agent()
                else:
                    pause_agent()
            except Exception:
                pass
        for flag in _WF_DEFAULTS:
            if flag in data:
                s[flag] = bool(data[flag])
        save_user_settings(s)
    except Exception as exc:
        errors.append(f"Workflow flags failed: {exc}")

    if errors:
        return jsonify({"status": "partial", "errors": errors}), 207
    return jsonify({"status": "ok"})


@app.route("/device/<ip>/restore_golden_config", methods=["POST"])
def restore_golden_config(ip):
    """Restore the AI's stored golden config for this device by pushing it line-by-line via SSH."""
    try:
        _, current_list_file = get_current_device_list()
        devices = load_saved_devices(current_list_file)
        dev = next((d for d in devices if d["ip"] == ip), None)

        if not dev:
            flash("Device not found", "danger")
            return redirect(url_for("index"))

        # Load the golden config from the app's file store (same source the AI uses)
        cfg_text = _ai._load_golden_config_file(ip)
        if not cfg_text:
            flash(f"No golden config saved for {dev.get('hostname', ip)} — save one via the AI first.", "warning")
            return redirect(url_for("manage_device", ip=ip))

        # Strip comment header lines the app adds (lines starting with !)
        config_lines = [l for l in cfg_text.splitlines() if not l.startswith("!") and l.strip()]

        app.logger.info(f"Restoring golden config on {ip} ({len(config_lines)} lines)")

        lines_applied = []
        def execute_restore(conn):
            conn.config_mode()
            try:
                for line in config_lines:
                    run_device_command(conn, line)
                    lines_applied.append(line)
            finally:
                conn.exit_config_mode()
            return f"Applied {len(lines_applied)} configuration lines from stored golden config."

        output = with_temp_connection(dev, execute_restore)

        app.logger.info(f"Golden config restored on {ip}")
        flash(f"Golden config restored on {dev['hostname']} ({len(lines_applied)} lines applied)", "success")

        active_tab = request.form.get("active_tab", "utilities")
        filesystems, file_list, selected_fs = get_device_context(dev)
        return render_template(
            "device.html",
            device=dev,
            filesystems=filesystems,
            files=file_list,
            selected_fs=selected_fs,
            output=output,
            filename=f"{dev['hostname']}_golden_restore.txt",
            active_tab=active_tab,
            quick_actions=load_quick_actions().get("global", []),
            tftp_server=TFTP_SERVER_IP,
        )

    except Exception as e:
        app.logger.error(f"Failed to restore golden config on {ip}: {e}")
        flash(f"Failed to restore golden config: {e}", "danger")
        return redirect(url_for("manage_device", ip=ip))


@app.route("/refresh_hostnames", methods=["POST"])
def refresh_hostnames():
    """Refresh hostnames for all online devices by querying them."""
    try:
        _, current_list_file = get_current_device_list()
        devices = load_saved_devices(current_list_file)

        if not devices:
            return jsonify({"status": "error", "message": "No devices in current list"}), 400

        updated_count = 0
        failed_count = 0
        results = []

        for dev in devices:
            ip = dev.get("ip")
            old_hostname = dev.get("hostname", "")

            # Check if device is online
            if not device_status_cache.get(ip, False):
                results.append({
                    "ip": ip,
                    "old_hostname": old_hostname,
                    "new_hostname": old_hostname,
                    "status": "skipped",
                    "message": "Device offline"
                })
                continue

            try:
                # Get current hostname from device
                def get_hostname(conn):
                    prompt = conn.find_prompt()
                    return prompt.rstrip("#>").strip()

                new_hostname = with_temp_connection(dev, get_hostname)

                if new_hostname and new_hostname != old_hostname:
                    dev["hostname"] = new_hostname
                    updated_count += 1
                    results.append({
                        "ip": ip,
                        "old_hostname": old_hostname,
                        "new_hostname": new_hostname,
                        "status": "updated",
                        "message": f"Updated: {old_hostname} -> {new_hostname}"
                    })
                    app.logger.info(f"Hostname updated for {ip}: {old_hostname} -> {new_hostname}")
                else:
                    results.append({
                        "ip": ip,
                        "old_hostname": old_hostname,
                        "new_hostname": new_hostname or old_hostname,
                        "status": "unchanged",
                        "message": "No change"
                    })

            except Exception as e:
                failed_count += 1
                results.append({
                    "ip": ip,
                    "old_hostname": old_hostname,
                    "new_hostname": old_hostname,
                    "status": "failed",
                    "message": str(e)
                })
                app.logger.warning(f"Failed to refresh hostname for {ip}: {e}")

        # Save updated devices back to CSV if any changes
        if updated_count > 0:
            write_devices_csv(devices, current_list_file)

            # Propagate hostname changes everywhere else the old name is stored.
            changed = [(r["ip"], r["old_hostname"], r["new_hostname"])
                       for r in results if r["status"] == "updated"]

            from modules.ai_assistant import (
                _find_golden_config_file, _save_golden_config_file,
                _load_variables, _save_variables,
            )

            for ip, old_hn, new_hn in changed:
                # ── Golden config ──────────────────────────────────────────
                # _save_golden_config_file removes the old hostname-named file
                # and creates a new one with the updated header.
                try:
                    old_path = _find_golden_config_file(ip)
                    if old_path and os.path.exists(old_path):
                        with open(old_path, encoding="utf-8") as _f:
                            raw = _f.read()
                        # Strip the 4-line NMAS header so _save_golden_config_file
                        # can prepend a fresh header with the new hostname.
                        stripped_lines = []
                        in_header = True
                        for line in raw.splitlines():
                            if in_header and (
                                line.startswith("! Golden config")
                                or line.startswith("! Saved:")
                                or line.startswith("! Source:")
                                or line == "!"
                            ):
                                continue
                            in_header = False
                            stripped_lines.append(line)
                        _save_golden_config_file(ip, new_hn, "\n".join(stripped_lines))
                        app.logger.info("Golden config renamed %s→%s (%s)", old_hn, new_hn, ip)
                except Exception as exc:
                    app.logger.warning("Could not rename golden config for %s: %s", ip, exc)

                # ── Variable keys ──────────────────────────────────────────
                # Keys are conventionally prefixed "{hostname}_*".  Rename any
                # that begin with the old hostname so AI context stays accurate.
                try:
                    variables = _load_variables()
                    old_prefix = f"{old_hn}_"
                    new_prefix = f"{new_hn}_"
                    renamed_vars = {
                        (new_prefix + k[len(old_prefix):] if k.startswith(old_prefix) else k): v
                        for k, v in variables.items()
                    }
                    if renamed_vars != variables:
                        _save_variables(renamed_vars)
                        n = sum(1 for k in variables if k.startswith(old_prefix))
                        app.logger.info("Renamed %d variable key(s) %s→%s", n, old_hn, new_hn)
                except Exception as exc:
                    app.logger.warning("Could not rename variables for %s: %s", ip, exc)

                # ── NetBox device name ─────────────────────────────────────
                try:
                    from modules.netbox_client import (
                        get_netbox_config, _session_from_config, _nb_first,
                    )
                    nbcfg = get_netbox_config()
                    if nbcfg.get("url") and nbcfg.get("token"):
                        sess = _session_from_config(nbcfg)
                        base = nbcfg["url"]
                        nb_dev = (_nb_first(sess, base, "dcim/devices/", name=old_hn)
                                  or _nb_first(sess, base, "dcim/devices/", q=ip))
                        if nb_dev and nb_dev.get("name") == old_hn:
                            r = sess.patch(
                                f"{base}/api/dcim/devices/{nb_dev['id']}/",
                                json={"name": new_hn},
                                timeout=15,
                            )
                            if r.ok:
                                app.logger.info("NetBox device renamed %s→%s", old_hn, new_hn)
                            else:
                                app.logger.warning(
                                    "NetBox rename failed for %s: %s", ip, r.status_code
                                )
                except Exception as exc:
                    app.logger.warning("Could not update NetBox name for %s: %s", ip, exc)

        return jsonify({
            "status": "success",
            "message": f"Refreshed {updated_count} hostname(s), {failed_count} failed",
            "updated": updated_count,
            "failed": failed_count,
            "results": results
        })

    except Exception as e:
        app.logger.error(f"Failed to refresh hostnames: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# Quick actions: add/delete (GLOBAL, no IP param)
@app.route("/add_quick_action", methods=["POST"])
def add_quick_action():
    # Add a new quick action to quick_actions.json
    data = request.get_json()
    command = data.get("command")
    label = data.get("label")

    if not command or not label:
        return jsonify({"status": "error", "message": "Missing command or label"}), 400

    actions = load_quick_actions()
    if "global" not in actions:
        actions["global"] = []

    # prevent duplicates
    if not any(
        a["command"] == command and a["label"] == label for a in actions["global"]
    ):
        actions["global"].append({"command": command, "label": label})
        save_quick_actions(actions)

    return jsonify({"status": "success"})


@app.route("/delete_quick_action", methods=["POST"])
def delete_quick_action():
    # Delete a quick action from quick_actions.json
    data = request.get_json()
    command = data.get("command")
    label = data.get("label")

    actions = load_quick_actions()
    if "global" in actions:
        actions["global"] = [
            a
            for a in actions["global"]
            if not (a["command"] == command and a["label"] == label)
        ]
        save_quick_actions(actions)

    return jsonify({"status": "success"})


# Disconnect persistent session when leaving device page (only terminal)
@app.route("/disconnect/<ip>", methods=["POST"])
def disconnect(ip):
    # Close the live terminal session for the device
    # Only close the live terminal session
    sess = terminal_sessions.get(ip)
    if sess:
        try:
            if sess.get("chan"):
                sess["chan"].close()
            if sess.get("ssh"):
                sess["ssh"].close()
        except Exception:
            pass
        terminal_sessions.pop(ip, None)
    return jsonify({"status": "disconnected"})


@app.route("/connection_status/<ip>")
def connection_status(ip):
    # Return connection status for persistent Netmiko session
    status = "disconnected"
    # Use the persistent connection strictly for status checks
    _, current_list_file = get_current_device_list()
    devices = load_saved_devices(current_list_file)
    dev = next((d for d in devices if d["ip"] == ip), None)
    if dev:
        try:
            conn = get_persistent_connection(dev, connections, lock)
            conn.find_prompt()  # lightweight check
            status = "connected"
        except Exception:
            status = "disconnected"
    return jsonify({"status": status})


# ---------------------------------------------------------------------------
# Configuration Backup Routes
# ---------------------------------------------------------------------------

@app.route("/device/<ip>/backup_config", methods=["POST"])
def backup_config(ip):
    """Backup device configuration (running or startup)."""
    try:
        config_type = request.form.get("config_type", "running")

        _, current_list_file = get_current_device_list()
        devices = load_saved_devices(current_list_file)
        dev = next((d for d in devices if d["ip"] == ip), None)

        if not dev:
            flash("Device not found", "danger")
            return redirect(url_for("manage_device", ip=ip, active_tab="backups"))

        app.logger.info(f"Backing up {config_type} config for device: {ip}")

        # Get connection
        conn = get_persistent_connection(dev, connections, lock)

        # Get configuration
        if config_type == "running":
            config = get_running_config(conn)
        else:
            config = get_startup_config(conn)

        # Save backup
        backup_info = save_config_backup(ip, dev["hostname"], config, config_type)

        flash(f"Configuration backed up successfully: {backup_info['filename']}", "success")
        app.logger.info(f"Backup created: {backup_info['filename']}")

    except Exception as e:
        app.logger.error(f"Backup failed for {ip}: {str(e)}")
        flash(f"Backup failed: {str(e)}", "danger")

    return redirect(url_for("manage_device", ip=ip, active_tab="backups"))


@app.route("/device/<ip>/save_running_to_startup", methods=["POST"])
def save_to_startup(ip):
    """Save running-config to startup-config on device."""
    try:
        _, current_list_file = get_current_device_list()
        devices = load_saved_devices(current_list_file)
        dev = next((d for d in devices if d["ip"] == ip), None)

        if not dev:
            flash("Device not found", "danger")
            return redirect(url_for("manage_device", ip=ip, active_tab="backups"))

        app.logger.info(f"Saving running-config to startup-config on: {ip}")

        # Get connection
        conn = get_persistent_connection(dev, connections, lock)

        # Save config
        output = save_running_to_startup(conn)

        flash("Running configuration saved to startup-config", "success")
        app.logger.info(f"Config saved on {ip}: {output}")

    except Exception as e:
        app.logger.error(f"Failed to save config on {ip}: {str(e)}")
        flash(f"Failed to save configuration: {str(e)}", "danger")

    return redirect(url_for("manage_device", ip=ip, active_tab="backups"))


@app.route("/device/<ip>/backup_history")
def backup_history_route(ip):
    """Get backup history for a device."""
    try:
        backups = get_backup_history(ip=ip, limit=50)
        return jsonify({"status": "success", "backups": backups})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/download_backup/<filename>")
def download_backup(filename):
    """Download a backup file."""
    try:
        content = get_backup_content(filename)

        if content is None:
            flash("Backup file not found", "danger")
            return redirect(url_for("index"))

        # Create in-memory file
        file_obj = BytesIO(content.encode("utf-8"))
        file_obj.seek(0)

        return send_file(
            file_obj,
            mimetype="text/plain",
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        app.logger.error(f"Download backup failed: {str(e)}")
        flash(f"Download failed: {str(e)}", "danger")
        return redirect(url_for("index"))


@app.route("/delete_backup/<filename>", methods=["POST"])
def delete_backup_route(filename):
    """Delete a backup file."""
    device_ip = None

    try:
        # Try to extract IP from filename (format: hostname_ip_type_timestamp.cfg)
        parts = filename.rsplit('_', 3)
        if len(parts) >= 4:
            device_ip = parts[1]

        success = delete_backup(filename)

        if success:
            flash(f"Backup deleted: {filename}", "success")
        else:
            flash("Failed to delete backup", "danger")

    except Exception as e:
        app.logger.error(f"Delete backup failed: {str(e)}")
        flash(f"Delete failed: {str(e)}", "danger")

    # Redirect back to backups tab if we know the device IP
    if device_ip:
        return redirect(url_for("manage_device", ip=device_ip, active_tab="backups"))
    else:
        return redirect(request.referrer or url_for("index"))


@app.route("/compare_backups", methods=["POST"])
def compare_backups_route():
    """Compare two backup configurations."""
    try:
        file1 = request.form.get("file1")
        file2 = request.form.get("file2")

        if not file1 or not file2:
            return jsonify({"status": "error", "message": "Two files required"}), 400

        config1 = get_backup_content(file1)
        config2 = get_backup_content(file2)

        if config1 is None or config2 is None:
            return jsonify({"status": "error", "message": "Backup file not found"}), 404

        diff = compare_configs(config1, config2)

        return jsonify({
            "status": "success",
            "diff": diff,
            "file1": file1,
            "file2": file2
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/device/<ip>/restore_backup", methods=["POST"])
def restore_backup(ip):
    """Restore a device configuration from a backup file."""
    try:
        filename = request.form.get("filename")
        save_to_startup = request.form.get("save_to_startup", "false") == "true"

        if not filename:
            return jsonify({"status": "error", "message": "No backup filename provided"}), 400

        # Get backup content
        config_content = get_backup_content(filename)
        if config_content is None:
            return jsonify({"status": "error", "message": "Backup file not found"}), 404

        # Get device
        _, current_list_file = get_current_device_list()
        devices = load_saved_devices(current_list_file)
        dev = next((d for d in devices if d["ip"] == ip), None)

        if not dev:
            return jsonify({"status": "error", "message": "Device not found"}), 404

        app.logger.info(f"Restoring backup {filename} to device {ip}")

        # Parse config lines - skip lines that shouldn't be sent
        config_lines = []
        skip_patterns = [
            "Building configuration",
            "Current configuration",
            "Last configuration change",
            "NVRAM config last updated",
            "!",
            "end",
            "version ",
        ]

        for line in config_content.splitlines():
            line_stripped = line.strip()
            # Skip empty lines and comment lines
            if not line_stripped:
                continue
            # Skip metadata/comment lines
            if any(line_stripped.startswith(pattern) for pattern in skip_patterns):
                continue
            config_lines.append(line)

        if not config_lines:
            return jsonify({"status": "error", "message": "No valid configuration lines in backup"}), 400

        def execute_restore(conn):
            output_lines = []

            # Enter config mode
            conn.config_mode()
            output_lines.append("Entered configuration mode")

            # Send each config line
            for line in config_lines:
                try:
                    result = conn.send_command_timing(line, strip_prompt=False, strip_command=False)
                    # Check for common error patterns
                    if "% Invalid" in result or "% Incomplete" in result:
                        output_lines.append(f"WARNING: {line} -> {result.strip()}")
                    else:
                        output_lines.append(f"OK: {line}")
                except Exception as e:
                    output_lines.append(f"ERROR: {line} -> {str(e)}")

            # Exit config mode
            try:
                conn.exit_config_mode()
                output_lines.append("Exited configuration mode")
            except Exception:
                pass

            # Optionally save to startup
            if save_to_startup:
                try:
                    save_result = conn.send_command_timing("write memory")
                    output_lines.append(f"Saved to startup-config: {save_result.strip()}")
                except Exception as e:
                    output_lines.append(f"WARNING: Failed to save to startup: {str(e)}")

            return "\n".join(output_lines)

        output = with_temp_connection(dev, execute_restore)

        app.logger.info(f"Restore completed for {ip} from {filename}")

        return jsonify({
            "status": "success",
            "message": f"Configuration restored from {filename}",
            "output": output,
            "lines_sent": len(config_lines)
        })

    except Exception as e:
        app.logger.error(f"Restore backup failed for {ip}: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/backup_stats")
def backup_stats_route():
    """Get backup statistics."""
    try:
        stats = get_backup_stats()
        return jsonify({"status": "success", "stats": stats})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ---------------------------------------------------------------------------
# Topology Route
# ---------------------------------------------------------------------------

@app.route("/topology_data")
def topology_data():
    """Discover and return network topology as JSON."""
    try:
        _, current_list_file = get_current_device_list()
        devices = load_saved_devices(current_list_file)

        if not devices:
            return jsonify({"status": "success", "topology": {"nodes": [], "edges": []}})

        topology = discover_topology(
            devices=devices,
            connection_factory=get_persistent_connection,
            connections_pool=connections,
            pool_lock=lock,
            status_cache=device_status_cache,
            max_workers=5
        )

        # Persist so the diagram survives server restarts.
        _ai._topology_cache_save(topology)

        # Prune positions and hidden-node lists so stale nodes are removed from
        # disk, not just filtered in memory on every topology_state() call.
        current_ids = {n["id"] for n in topology.get("nodes", [])}
        layout = _load_topo_layout()
        cleaned_positions = {k: v for k, v in layout.get("positions", {}).items()
                             if k in current_ids}
        cleaned_hidden    = [h for h in layout.get("hidden", []) if h in current_ids]
        if cleaned_positions != layout.get("positions") or cleaned_hidden != layout.get("hidden"):
            _save_topo_layout({"positions": cleaned_positions, "hidden": cleaned_hidden})

        return jsonify({"status": "success", "topology": topology})

    except Exception as e:
        app.logger.error(f"Topology discovery failed: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


def _topo_positions_file() -> str:
    from modules.config import get_current_list_data_dir
    return os.path.join(get_current_list_data_dir(), "topology_positions.json")


def _load_topo_layout() -> dict:
    """Load persisted topology layout (positions + hidden list)."""
    try:
        path = _topo_positions_file()
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
    except Exception:
        pass
    return {"positions": {}, "hidden": []}


def _save_topo_layout(layout: dict) -> None:
    """Atomically persist topology layout."""
    path = _topo_positions_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(layout, fh)
    os.replace(tmp, path)


@app.route("/topology/state")
def topology_state():
    """Return the last-saved topology + user layout (positions + hidden nodes).
    Uses raw cache load (ignores TTL) so topology persists across restarts.
    Managed nodes that no longer exist in the device list are stripped so
    deleted devices don't keep appearing on the map."""
    topology = _ai._topology_cache_load_raw()
    layout   = _load_topo_layout()

    # Build the set of node IDs that actually exist in the current topology.
    # We do NOT filter topology nodes here — CDP neighbors that were once managed
    # should still appear on the map after deletion (they'll be re-typed on next
    # discovery).  The cache is invalidated on delete so fresh discovery fixes types.
    existing_ids: set = {n["id"] for n in (topology or {}).get("nodes", [])}

    # Strip hidden/position entries for nodes that no longer exist in the topology.
    raw_hidden    = [h for h in layout.get("hidden", [])    if h in existing_ids]
    raw_positions = {k: v for k, v in layout.get("positions", {}).items() if k in existing_ids}

    return jsonify({
        "topology":  topology,
        "positions": raw_positions,
        "hidden":    raw_hidden,
    })


@app.route("/topology/positions", methods=["POST"])
def topology_save_positions():
    """Persist node positions (x/y) so user layout survives server restarts."""
    data = request.get_json(silent=True) or {}
    positions = data.get("positions", {})
    try:
        layout = _load_topo_layout()
        layout["positions"] = positions
        _save_topo_layout(layout)
    except Exception as exc:
        app.logger.warning("topology_save_positions: %s", exc)
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": True, "saved": len(positions)})


@app.route("/topology/hidden", methods=["POST"])
def topology_save_hidden():
    """Persist the list of node IDs hidden from the topology diagram."""
    data = request.get_json(silent=True) or {}
    hidden = data.get("hidden", [])
    try:
        layout = _load_topo_layout()
        layout["hidden"] = hidden
        _save_topo_layout(layout)
    except Exception as exc:
        app.logger.warning("topology_save_hidden: %s", exc)
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": True, "hidden": hidden})


@app.route("/topology/link_status")
def topology_link_status():
    """Return up/down status for each link in the cached CDP topology.

    Queries 'show ip interface brief' on all online managed devices that
    appear in the cached topology, then maps each edge to 'up', 'down',
    or 'unknown'.  Uses the same persistent connections pool as normal
    device queries so this doesn't open extra SSH sessions.
    """
    from concurrent.futures import ThreadPoolExecutor

    topology = _ai._topology_cache_load_raw()
    if not topology or not topology.get("edges"):
        return jsonify({"status": "ok", "links": {}})

    edges = topology["edges"]

    edge_device_ids = set()
    for edge in edges:
        edge_device_ids.add(edge["from"])
        edge_device_ids.add(edge["to"])

    _, current_list_file = get_current_device_list()
    devices = load_saved_devices(current_list_file)
    device_map = {d.get("hostname", "").lower(): d for d in devices}

    intf_status: dict = {}

    def _check_device(device_id):
        device = device_map.get(device_id)
        if not device:
            return device_id, None
        ip = device.get("ip", "")
        if not device_status_cache.get(ip, False):
            return device_id, None
        try:
            conn = get_persistent_connection(device, connections, lock)
            # Must use run_device_command — 'show ip interface' is in _TIMING_PREFIXES
            # and will timeout/return bad output with send_command directly.
            output = run_device_command(conn, "show ip interface brief")
            statuses: dict = {}
            # Parse ALL interfaces (including unassigned) since CDP links may use
            # interfaces that carry no IP address.
            for line in output.splitlines():
                parts = line.split()
                # Need at least: Interface  IP  OK?  Method  Status  Protocol
                if len(parts) < 6 or parts[0] in ("Interface", ""):
                    continue
                name  = parts[0]
                # Protocol is the last column; handle "administratively down" (7+ cols)
                protocol = parts[-1].lower().rstrip("*")
                short    = shorten_interface(name)
                is_up    = protocol == "up"
                statuses[name]  = is_up
                statuses[short] = is_up
            return device_id, statuses
        except Exception:
            return device_id, None

    devices_to_query = [d for d in edge_device_ids if d in device_map]
    with ThreadPoolExecutor(max_workers=5) as ex:
        for device_id, statuses in ex.map(_check_device, devices_to_query):
            if statuses is not None:
                intf_status[device_id] = statuses

    links: dict = {}
    for edge in edges:
        key = f"{edge['from']}|{edge.get('from_intf', '')}|{edge['to']}|{edge.get('to_intf', '')}"
        from_up = intf_status.get(edge["from"], {}).get(edge.get("from_intf", ""))
        to_up   = intf_status.get(edge["to"],   {}).get(edge.get("to_intf",   ""))
        if from_up is None and to_up is None:
            status = "unknown"
        elif from_up is False or to_up is False:
            status = "down"
        else:
            status = "up"
        links[key] = status

    return jsonify({"status": "ok", "links": links})


@app.route("/topology/proto_link_status")
def topology_proto_link_status():
    """Return live up/down status for OSPF adjacencies, BGP sessions, or tunnel interfaces.

    Runs a single targeted command per device (ospf neighbor detail / bgp summary /
    interface brief) and compares against the cached proto topology edges.
    Query param: ?view=ospf|bgp|tunnel
    """
    from modules.topology import (
        parse_ospf_neighbors, parse_bgp_summary, parse_ip_interfaces,
        build_ospf_topology, build_bgp_topology,
    )
    from concurrent.futures import ThreadPoolExecutor

    view = request.args.get("view", "")
    if view not in ("ospf", "bgp", "tunnel"):
        return jsonify({"status": "error", "message": "invalid view"}), 400

    cached = _load_proto_cache()
    topology = cached.get(view)
    if not topology or not topology.get("edges"):
        return jsonify({"status": "ok", "links": {}})

    managed_node_ids = {
        n["id"] for n in topology.get("nodes", []) if n.get("type") == "managed"
    }
    _, current_list_file = get_current_device_list()
    devices = load_saved_devices(current_list_file)
    device_map = {d.get("hostname", "").lower(): d for d in devices}
    devices_to_check = [device_map[did] for did in managed_node_ids if did in device_map]

    def _collect(device):
        ip = device.get("ip", "")
        if not device_status_cache.get(ip, False):
            return None
        try:
            conn = get_persistent_connection(device, connections, lock)
            result = {
                "hostname":   device["hostname"],
                "interfaces": [],
                "ospf":       [],
                "bgp":        {"local_as": "", "peers": []},
                "tunnels":    [],
            }
            with _device_lock(device["ip"]):
                # All these commands are in _TIMING_PREFIXES — must use run_device_command.
                out = run_device_command(conn, "show ip interface brief")
                result["interfaces"] = parse_ip_interfaces(out)

                if view == "ospf":
                    out = run_device_command(conn, "show ip ospf neighbor detail")
                    result["ospf"] = parse_ospf_neighbors(out)
                elif view == "bgp":
                    out = run_device_command(conn, "show ip bgp summary")
                    result["bgp"] = parse_bgp_summary(out)
            # For "tunnel" interface brief is sufficient to check Tunnel interface state.
            return result
        except Exception:
            return None

    devices_data: list = []
    with ThreadPoolExecutor(max_workers=5) as ex:
        for r in ex.map(_collect, devices_to_check):
            if r:
                devices_data.append(r)

    links: dict = {}

    if view in ("ospf", "bgp"):
        if not devices_data:
            for edge in topology["edges"]:
                links[f"{edge['from']}|{edge['to']}"] = "unknown"
            return jsonify({"status": "ok", "links": links})

        build_fn = build_ospf_topology if view == "ospf" else build_bgp_topology
        fresh = build_fn(devices_data)
        # Index fresh edges by both orderings of from/to so cache ordering doesn't matter
        fresh_map: dict = {}
        for e in fresh["edges"]:
            est = e.get("established", False)
            fresh_map[f"{e['from']}|{e['to']}"] = est
            fresh_map[f"{e['to']}|{e['from']}"] = est

        for edge in topology["edges"]:
            key = f"{edge['from']}|{edge['to']}"
            est = fresh_map.get(key, fresh_map.get(f"{edge['to']}|{edge['from']}"))
            if est is None:
                links[key] = "unknown"
            else:
                links[key] = "up" if est else "down"

    else:  # tunnel — check Tunnel interface protocol status on 'from' device
        tun_up: dict = {}  # device_id → {intf_name: bool}
        for dev in devices_data:
            did = dev["hostname"].lower()
            tun_up[did] = {}
            for iface in dev.get("interfaces", []):
                name = iface.get("interface", "")
                if name.lower().startswith("tunnel"):
                    is_up = iface.get("protocol", "").lower() == "up"
                    tun_up[did][name]                    = is_up
                    tun_up[did][shorten_interface(name)] = is_up

        for edge in topology["edges"]:
            tun_name = edge.get("tunnel", "")
            key = f"{edge['from']}|{tun_name}|{edge['to']}"
            dev_statuses = tun_up.get(edge["from"], {})
            is_up = dev_statuses.get(tun_name)
            if is_up is None:
                links[key] = "unknown"
            elif is_up:
                links[key] = "up"
            else:
                links[key] = "down"

    return jsonify({"status": "ok", "links": links})


# Protocol topology (OSPF / BGP / Tunnels) -----------------------------------

def _proto_cache_file() -> str:
    from modules.config import get_current_list_data_dir
    return os.path.join(get_current_list_data_dir(), "proto_topology_cache.json")

def _proto_pos_file() -> str:
    from modules.config import get_current_list_data_dir
    return os.path.join(get_current_list_data_dir(), "proto_topology_positions.json")

def _proto_hidden_file() -> str:
    from modules.config import get_current_list_data_dir
    return os.path.join(get_current_list_data_dir(), "proto_topology_hidden.json")


def _load_proto_cache():
    try:
        path = _proto_cache_file()
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
    except Exception:
        pass
    return {}


def _save_proto_cache(data: dict) -> None:
    path = _proto_cache_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    os.replace(tmp, path)


def _load_proto_positions() -> dict:
    try:
        path = _proto_pos_file()
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
    except Exception:
        pass
    return {}


def _save_proto_positions(data: dict) -> None:
    path = _proto_pos_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    os.replace(tmp, path)


def _load_proto_hidden() -> dict:
    try:
        path = _proto_hidden_file()
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
    except Exception:
        pass
    return {}


def _save_proto_hidden(data: dict) -> None:
    path = _proto_hidden_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    os.replace(tmp, path)


@app.route("/topology/protocol_data")
def topology_protocol_data():
    """Discover and return OSPF, BGP, and tunnel topology graphs."""
    try:
        from modules.topology import discover_protocol_topologies
        _, current_list_file = get_current_device_list()
        devices = load_saved_devices(current_list_file)
        if not devices:
            empty = {"nodes": [], "edges": []}
            return jsonify({"status": "success",
                            "ospf": empty, "bgp": empty, "tunnel": empty})

        result = discover_protocol_topologies(
            devices           = devices,
            connection_factory= get_persistent_connection,
            connections_pool  = connections,
            pool_lock         = lock,
            status_cache      = device_status_cache,
            max_workers       = 5,
        )
        _save_proto_cache(result)
        return jsonify({"status": "success", **result})
    except Exception as e:
        app.logger.error("Protocol topology discovery failed: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/topology/protocol_state")
def topology_protocol_state():
    """Return cached protocol topologies + persisted positions + hidden sets."""
    cache     = _load_proto_cache()
    positions = _load_proto_positions()
    hidden    = _load_proto_hidden()

    # Strip position/hidden entries for nodes that no longer exist.
    # positions is {view: {node_id: {x,y}}} — filter per-view, not at the top level.
    clean_positions: dict = {}
    clean_hidden:    dict = {}
    for view in ("ospf", "bgp", "tunnel"):
        view_ids = {n["id"] for n in cache.get(view, {}).get("nodes", [])}
        clean_positions[view] = {
            nid: pos for nid, pos in positions.get(view, {}).items()
            if nid in view_ids
        }
        clean_hidden[view] = [
            h for h in hidden.get(view, []) if h in view_ids
        ]

    return jsonify({
        "ospf":      cache.get("ospf",   {"nodes": [], "edges": []}),
        "bgp":       cache.get("bgp",    {"nodes": [], "edges": []}),
        "tunnel":    cache.get("tunnel", {"nodes": [], "edges": []}),
        "positions": clean_positions,
        "hidden":    clean_hidden,
    })


@app.route("/topology/proto_hidden", methods=["POST"])
def topology_save_proto_hidden():
    """Persist per-view hidden node list for OSPF/BGP/Tunnel views.
    Body: {view: "ospf"|"bgp"|"tunnel", hidden: [id, ...]}
    """
    data = request.get_json(silent=True) or {}
    view = data.get("view", "")
    hidden = data.get("hidden", [])
    if view not in ("ospf", "bgp", "tunnel"):
        return jsonify({"ok": False, "error": "invalid view"}), 400
    try:
        all_hidden = _load_proto_hidden()
        all_hidden[view] = hidden
        _save_proto_hidden(all_hidden)
    except Exception as exc:
        app.logger.warning("topology_save_proto_hidden: %s", exc)
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": True})


@app.route("/topology/proto_positions", methods=["POST"])
def topology_save_proto_positions():
    """Persist per-view node positions for OSPF/BGP/Tunnel views.
    Body: {view: "ospf"|"bgp"|"tunnel", positions: {id: {x, y}}}
    """
    data = request.get_json(silent=True) or {}
    view = data.get("view", "")
    positions = data.get("positions", {})
    if view not in ("ospf", "bgp", "tunnel"):
        return jsonify({"ok": False, "error": "invalid view"}), 400
    try:
        all_pos = _load_proto_positions()
        all_pos[view] = positions
        _save_proto_positions(all_pos)
    except Exception as exc:
        app.logger.warning("topology_save_proto_positions: %s", exc)
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Bulk Operations Routes
# ---------------------------------------------------------------------------

@app.route("/bulk_execute", methods=["POST"])
def bulk_execute():
    """Execute a command on multiple devices."""
    try:
        device_ips = request.form.getlist("device_ips[]")
        command = request.form.get("command", "").strip()
        command_mode = request.form.get("command_mode", "enable").strip()

        if not device_ips:
            return jsonify({"status": "error", "message": "No devices selected"}), 400

        if not command:
            return jsonify({"status": "error", "message": "No command provided"}), 400

        # Validate command mode
        if command_mode not in ("enable", "config"):
            command_mode = "enable"

        # Load devices from current list
        _, current_list_file = get_current_device_list()
        all_devices = load_saved_devices(current_list_file)
        selected_devices = [d for d in all_devices if d["ip"] in device_ips]

        if not selected_devices:
            return jsonify({"status": "error", "message": "No valid devices found"}), 400

        mode_text = "config" if command_mode == "config" else "enable"
        app.logger.info(f"Bulk execute ({mode_text} mode) on {len(selected_devices)} devices: {command}")

        # Start bulk operation
        operation_id = bulk_manager.execute_bulk_command(
            devices=selected_devices,
            command=command,
            connection_factory=get_persistent_connection,
            connections_pool=connections,
            pool_lock=lock,
            max_workers=5,
            command_mode=command_mode
        )

        return jsonify({
            "status": "success",
            "operation_id": operation_id,
            "message": f"Executing ({mode_text} mode) on {len(selected_devices)} device(s)"
        })

    except Exception as e:
        app.logger.error(f"Bulk execute failed: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/bulk_status/<operation_id>")
def bulk_status(operation_id):
    """Get status of a bulk operation."""
    try:
        status = bulk_manager.get_operation_status(operation_id)
        return jsonify({"status": "success", "operation": status})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/bulk_clear/<operation_id>", methods=["POST"])
def bulk_clear(operation_id):
    """Clear a completed bulk operation."""
    try:
        bulk_manager.clear_operation(operation_id)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/bulk_reload", methods=["POST"])
def bulk_reload():
    """Send reload to multiple devices.  Fire-and-forget per device — the SSH
    session is closed immediately after confirming so the reboot doesn't hang
    the worker."""
    import threading as _t

    try:
        device_ips = request.form.getlist("device_ips[]")
        if not device_ips:
            return jsonify({"status": "error", "message": "No devices selected"}), 400

        _, current_list_file = get_current_device_list()
        all_devices = load_saved_devices(current_list_file)
        selected = [d for d in all_devices if d["ip"] in device_ips]
        if not selected:
            return jsonify({"status": "error", "message": "No valid devices found"}), 400

        operation_id = f"reload_{int(__import__('time').time()*1000)}"
        with lock:
            pass  # just ensure lock is available

        from modules.bulk_ops import bulk_manager as _bm
        import time as _time

        # Seed the tracking entry so the UI can poll immediately
        _bm.active_operations[operation_id] = {
            "status": "running",
            "total": len(selected),
            "completed": 0,
            "failed": 0,
            "results": [],
        }

        def _reload_one(dev):
            """Send reload to a single device. Runs in its own thread."""
            result = {
                "ip":       dev["ip"],
                "hostname": dev["hostname"],
                "status":   "pending",
                "output":   "",
                "error":    None,
            }
            try:
                conn = get_persistent_connection(dev, connections, lock)
                if conn is None:
                    raise RuntimeError("Could not open SSH connection")
                # Hold the per-device lock for the reload+confirm sequence so
                # no concurrent command slips in between the two sends.
                with _device_lock(dev["ip"]):
                    conn.send_command_timing("reload", delay_factor=2)
                    conn.send_command_timing("\n", delay_factor=1)
                # Drop the connection immediately — the device is rebooting.
                try:
                    conn.disconnect()
                except Exception:
                    pass
                with lock:
                    connections.pop(dev["ip"], None)
                result["status"] = "success"
                result["output"] = "Reload command sent — device is rebooting."
                with _bm.lock:
                    _bm.active_operations[operation_id]["completed"] += 1
            except Exception as exc:
                result["status"] = "failed"
                result["error"]  = str(exc)
                with _bm.lock:
                    _bm.active_operations[operation_id]["failed"] += 1
            finally:
                with _bm.lock:
                    _bm.active_operations[operation_id]["results"].append(result)

        def _reload_worker():
            # Spawn one thread per device so every reload fires simultaneously,
            # not sequentially. Each device's SSH session is independent.
            threads = [
                _t.Thread(target=_reload_one, args=(dev,), daemon=True)
                for dev in selected
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            with _bm.lock:
                _bm.active_operations[operation_id]["status"] = "completed"

        _t.Thread(target=_reload_worker, daemon=True).start()

        return jsonify({
            "status": "success",
            "operation_id": operation_id,
            "message": f"Reload sent to {len(selected)} device(s)",
        })

    except Exception as exc:
        app.logger.error("bulk_reload: %s", exc)
        return jsonify({"status": "error", "message": str(exc)}), 500


@app.route("/bulk_tftp_upload", methods=["POST"])
def bulk_tftp_upload():
    """Upload a file to multiple devices via TFTP."""
    try:
        device_ips = request.form.getlist("device_ips[]")
        file = request.files.get("file")
        tftp_server = request.form.get("tftp_server", TFTP_SERVER_IP) or TFTP_SERVER_IP

        if not device_ips:
            return jsonify({"status": "error", "message": "No devices selected"}), 400

        if not file or not file.filename:
            return jsonify({"status": "error", "message": "No file selected"}), 400

        # Save file to TFTP root
        local_path = os.path.join(TFTP_ROOT, file.filename)
        file.save(local_path)
        app.logger.info(f"Saved {file.filename} to TFTP root for bulk upload")

        # Load devices from current list
        _, current_list_file = get_current_device_list()
        all_devices = load_saved_devices(current_list_file)
        selected_devices = [d for d in all_devices if d["ip"] in device_ips]

        if not selected_devices:
            return jsonify({"status": "error", "message": "No valid devices found"}), 400

        # Command format for tftp_upload mode: "tftp_server|filename"
        tftp_command = f"{tftp_server}|{file.filename}"

        app.logger.info(f"Bulk TFTP upload to {len(selected_devices)} devices: {file.filename}")

        # Start bulk operation with the TFTP upload command mode
        operation_id = bulk_manager.execute_bulk_command(
            devices=selected_devices,
            command=tftp_command,
            connection_factory=get_persistent_connection,
            connections_pool=connections,
            pool_lock=lock,
            max_workers=3,  # Limit concurrent TFTP transfers
            command_mode="tftp_upload"
        )

        return jsonify({
            "status": "success",
            "operation_id": operation_id,
            "message": f"Uploading {file.filename} to {len(selected_devices)} device(s)"
        })

    except Exception as e:
        app.logger.error(f"Bulk TFTP upload failed: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/bulk_tftp_download", methods=["POST"])
def bulk_tftp_download():
    """Download a file from multiple devices via TFTP."""
    try:
        device_ips = request.form.getlist("device_ips[]")
        filename = request.form.get("filename", "").strip()
        tftp_server = request.form.get("tftp_server", TFTP_SERVER_IP) or TFTP_SERVER_IP

        if not device_ips:
            return jsonify({"status": "error", "message": "No devices selected"}), 400

        if not filename:
            return jsonify({"status": "error", "message": "No filename provided"}), 400

        # Load devices from current list
        _, current_list_file = get_current_device_list()
        all_devices = load_saved_devices(current_list_file)
        selected_devices = [d for d in all_devices if d["ip"] in device_ips]

        if not selected_devices:
            return jsonify({"status": "error", "message": "No valid devices found"}), 400

        # Command format for tftp_download mode: "tftp_server|filename|dest_filename"
        tftp_command = f"{tftp_server}|{filename}|{filename}"

        app.logger.info(f"Bulk TFTP download from {len(selected_devices)} devices: {filename}")

        # Start bulk operation with the TFTP download command mode
        operation_id = bulk_manager.execute_bulk_command(
            devices=selected_devices,
            command=tftp_command,
            connection_factory=get_persistent_connection,
            connections_pool=connections,
            pool_lock=lock,
            max_workers=3,  # Limit concurrent TFTP transfers
            command_mode="tftp_download"
        )

        return jsonify({
            "status": "success",
            "operation_id": operation_id,
            "message": f"Downloading {filename} from {len(selected_devices)} device(s)"
        })

    except Exception as e:
        app.logger.error(f"Bulk TFTP download failed: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/bulk_download_config", methods=["POST"])
def bulk_download_config():
    """Download startup or running config from multiple devices via TFTP."""
    try:
        device_ips = request.form.getlist("device_ips[]")
        config_type = request.form.get("config_type", "startup").strip()
        tftp_server = request.form.get("tftp_server", TFTP_SERVER_IP) or TFTP_SERVER_IP

        if not device_ips:
            return jsonify({"status": "error", "message": "No devices selected"}), 400

        if config_type not in ("startup", "running"):
            config_type = "startup"

        # Load devices from current list
        _, current_list_file = get_current_device_list()
        all_devices = load_saved_devices(current_list_file)
        selected_devices = [d for d in all_devices if d["ip"] in device_ips]

        if not selected_devices:
            return jsonify({"status": "error", "message": "No valid devices found"}), 400

        # Command format for config download: "tftp_server|config_type"
        tftp_command = f"{tftp_server}|{config_type}"
        config_name = "startup-config" if config_type == "startup" else "running-config"

        app.logger.info(f"Bulk {config_name} download from {len(selected_devices)} devices")

        # Start bulk operation with config download mode
        operation_id = bulk_manager.execute_bulk_command(
            devices=selected_devices,
            command=tftp_command,
            connection_factory=get_persistent_connection,
            connections_pool=connections,
            pool_lock=lock,
            max_workers=3,
            command_mode="config_download"
        )

        return jsonify({
            "status": "success",
            "operation_id": operation_id,
            "message": f"Downloading {config_name} from {len(selected_devices)} device(s)"
        })

    except Exception as e:
        app.logger.error(f"Bulk config download failed: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/bulk_remove_static_routes", methods=["POST"])
def bulk_remove_static_routes():
    """Remove all non-VRF static routes from selected devices."""
    try:
        device_ips = request.form.getlist("device_ips[]")

        if not device_ips:
            return jsonify({"status": "error", "message": "No devices selected"}), 400

        # Load devices from current list
        _, current_list_file = get_current_device_list()
        all_devices = load_saved_devices(current_list_file)
        selected_devices = [d for d in all_devices if d["ip"] in device_ips]

        if not selected_devices:
            return jsonify({"status": "error", "message": "No valid devices found"}), 400

        app.logger.info(f"Bulk remove static routes from {len(selected_devices)} devices")

        # Start bulk operation with remove_static_routes mode
        operation_id = bulk_manager.execute_bulk_command(
            devices=selected_devices,
            command="",
            connection_factory=get_persistent_connection,
            connections_pool=connections,
            pool_lock=lock,
            max_workers=5,
            command_mode="remove_static_routes"
        )

        return jsonify({
            "status": "success",
            "operation_id": operation_id,
            "message": f"Removing static routes from {len(selected_devices)} device(s)"
        })

    except Exception as e:
        app.logger.error(f"Bulk remove static routes failed: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/bulk_delete_file", methods=["POST"])
def bulk_delete_file():
    """Delete a file from flash: on multiple devices."""
    try:
        device_ips = request.form.getlist("device_ips[]")
        filename = request.form.get("filename", "").strip()

        if not device_ips:
            return jsonify({"status": "error", "message": "No devices selected"}), 400

        if not filename:
            return jsonify({"status": "error", "message": "No filename provided"}), 400

        # Load devices from current list
        _, current_list_file = get_current_device_list()
        all_devices = load_saved_devices(current_list_file)
        selected_devices = [d for d in all_devices if d["ip"] in device_ips]

        if not selected_devices:
            return jsonify({"status": "error", "message": "No valid devices found"}), 400

        app.logger.info(f"Bulk delete {filename} from {len(selected_devices)} devices")

        # Start bulk operation with delete mode
        operation_id = bulk_manager.execute_bulk_command(
            devices=selected_devices,
            command=filename,
            connection_factory=get_persistent_connection,
            connections_pool=connections,
            pool_lock=lock,
            max_workers=5,
            command_mode="delete_file"
        )

        return jsonify({
            "status": "success",
            "operation_id": operation_id,
            "message": f"Deleting {filename} from {len(selected_devices)} device(s)"
        })

    except Exception as e:
        app.logger.error(f"Bulk delete failed: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


# ---------------------------------------------------------------------------
# Subnet Discovery Routes
# ---------------------------------------------------------------------------

# In-memory store for running discovery operations  { op_id -> state dict }
_discovery_ops: dict = {}


def _ping_host(ip: str) -> bool:
    """Return True if `ip` responds to a single ICMP ping within ~500 ms."""
    import subprocess, sys
    if sys.platform.startswith("win"):
        cmd = ["ping", "-n", "1", "-w", "500", ip]
    else:
        cmd = ["ping", "-c", "1", "-W", "1", ip]
    try:
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=3)
        return result.returncode == 0
    except Exception:
        return False


def _run_subnet_discovery(op_id: str, hosts: list, username: str,
                          password: str, secret: str, device_type: str,
                          max_workers: int) -> None:
    """Background thread: ping sweep first, then SSH only reachable hosts."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from modules.connection import verify_device_connection

    op = _discovery_ops[op_id]

    # ── Phase 1: ping sweep ───────────────────────────────────────────────
    op["phase"] = "ping"
    reachable: list[str] = []

    # Use more workers for ICMP — it's fast and cheap
    ping_workers = min(len(hosts), max(max_workers * 2, 50))
    with ThreadPoolExecutor(max_workers=ping_workers) as executor:
        futures = {executor.submit(_ping_host, ip): ip for ip in hosts}
        for future in as_completed(futures):
            ip = futures[future]
            op["ping_completed"] += 1
            if future.result():
                reachable.append(ip)
                op["ping_reachable"] += 1

    op["phase"] = "ssh"
    op["ssh_total"] = len(reachable)

    # ── Phase 2: SSH only reachable hosts ────────────────────────────────
    def probe(ip: str):
        try:
            hostname = verify_device_connection(ip, username, password, secret, device_type)
            return {"ip": ip, "hostname": hostname, "success": True}
        except Exception as exc:
            return {"ip": ip, "success": False, "error": str(exc)}

    if reachable:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(probe, ip): ip for ip in reachable}
            for future in as_completed(futures):
                result = future.result()
                op["completed"] += 1
                if result["success"]:
                    op["found"].append(result)

    op["status"] = "done"


@app.route("/discover_subnet", methods=["POST"])
def discover_subnet():
    """Start a threaded SSH probe across all hosts in a given subnet."""
    try:
        data = request.get_json(silent=True) or {}
        network  = (data.get("network") or "").strip()
        prefix   = data.get("prefix", 24)
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        secret   = data.get("secret") or ""
        device_type = data.get("device_type") or "cisco_ios"
        max_workers = max(1, min(int(data.get("max_workers", 30)), 100))

        if not network or not username or not password:
            return jsonify({"error": "network, username, and password are required"}), 400

        try:
            net = ipaddress.IPv4Network(f"{network}/{prefix}", strict=False)
        except ValueError as exc:
            return jsonify({"error": f"Invalid network: {exc}"}), 400

        hosts = [str(h) for h in net.hosts()]
        if not hosts:
            return jsonify({"error": "Subnet contains no usable host addresses"}), 400

        op_id = uuid.uuid4().hex[:10]
        _discovery_ops[op_id] = {
            "total":          len(hosts),
            "phase":          "ping",
            "ping_completed": 0,
            "ping_reachable": 0,
            "ssh_total":      0,
            "completed":      0,
            "found":          [],
            "status":         "running",
        }

        t = threading.Thread(
            target=_run_subnet_discovery,
            args=(op_id, hosts, username, password, secret, device_type, max_workers),
            daemon=True,
        )
        t.start()

        return jsonify({"op_id": op_id, "total": len(hosts)})

    except Exception as exc:
        app.logger.error(f"discover_subnet error: {exc}", exc_info=True)
        return jsonify({"error": str(exc)}), 500


@app.route("/discover_status/<op_id>")
def discover_status(op_id: str):
    """Poll the progress and results of a running subnet discovery."""
    op = _discovery_ops.get(op_id)
    if not op:
        return jsonify({"error": "Operation not found"}), 404
    return jsonify(op)


@app.route("/add_discovered_devices", methods=["POST"])
def add_discovered_devices():
    """Add a list of discovered devices (returned by /discover_subnet) to the inventory."""
    try:
        data       = request.get_json(silent=True) or {}
        devices    = data.get("devices", [])
        username   = data.get("username", "")
        password   = data.get("password", "")
        secret     = data.get("secret", "")
        device_type = data.get("device_type", "cisco_ios")

        _, current_list_file = get_current_device_list()

        added = 0
        for dev in devices:
            try:
                save_device({
                    "hostname":    dev.get("hostname", dev["ip"]),
                    "device_type": device_type,
                    "ip":          dev["ip"],
                    "username":    username,
                    "password":    password,
                    "secret":      secret,
                }, current_list_file)
                added += 1
            except Exception as exc:
                app.logger.warning(f"Could not add {dev.get('ip')}: {exc}")

        return jsonify({"added": added})

    except Exception as exc:
        app.logger.error(f"add_discovered_devices error: {exc}", exc_info=True)
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# AI Assistant Routes
# ---------------------------------------------------------------------------

import json as _json
from flask import Response, stream_with_context as _swc
import modules.ai_assistant as _ai


def _load_current_devices():
    """Load devices from the currently active device list file."""
    _, filepath = get_current_device_list()
    return load_saved_devices(filepath)


@app.route("/ai/providers")
def ai_providers():
    """Return all provider configs and which is active."""
    return jsonify({"providers": _ai.list_providers()})


@app.route("/ai/provider", methods=["POST"])
def ai_set_provider():
    """Switch the active AI provider."""
    data     = request.get_json(silent=True) or {}
    provider = data.get("provider", "").strip()
    model    = data.get("model") or None
    if not provider:
        return jsonify({"error": "provider is required"}), 400
    try:
        _ai.set_active_provider(provider, model)
        return jsonify({"status": "ok", "active": provider,
                        "info": _ai.get_provider_info(provider)})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/ai/device_context")
def ai_device_context():
    """Return a lightweight device inventory + online status snapshot for browser caching.
    Also pre-warms SSH connections for all currently online devices in the background
    so the first AI tool call hits the persistent pool immediately.
    """
    devices = _load_current_devices()
    online_devices = [
        d for d in devices if device_status_cache.get(d.get("ip", ""), False)
    ]
    result = [
        {
            "hostname":    d.get("hostname", ""),
            "ip":          d.get("ip", ""),
            "device_type": d.get("device_type", "cisco_ios"),
            "online":      bool(device_status_cache.get(d.get("ip", ""), False)),
        }
        for d in devices
    ]

    def _warm():
        for dev in online_devices:
            try:
                get_persistent_connection(dev, connections, lock)
            except Exception:
                pass   # unreachable devices are skipped silently

    threading.Thread(target=_warm, daemon=True).start()

    return jsonify({"devices": result})


@app.route("/ai/chat", methods=["POST"])
def ai_chat():
    """Stream an AI assistant response via Server-Sent Events."""
    try:
        data = request.get_json(silent=True) or {}
        message           = (data.get("message") or "").strip()
        context_ip        = data.get("context_ip") or None
        session_id        = data.get("session_id") or "default"
        device_context    = data.get("device_context") or None    # browser-cached snapshot
        topology_context  = data.get("topology_context") or None  # browser-cached topology
        attached_files    = data.get("attached_files") or []       # [{name, content}] uploaded by user
        run_playbook_id    = data.get("run_playbook_id") or None    # direct playbook execution
        # Block AI chat when disabled — but allow direct playbook execution through
        # since run_ansible_direct makes no Claude API calls.
        if not _ai_enabled() and not run_playbook_id:
            return jsonify({"error": "AI is disabled. Re-enable it in Settings."}), 503

        if not message and not run_playbook_id:
            return jsonify({"error": "Message is required"}), 400

        # Tell the background agent the user is active so it defers tasks
        try:
            from modules.agent_runner import notify_user_active
            notify_user_active()
        except Exception:
            pass

        import queue as _queue

        # Determine which playbook to run (if any).
        # Only explicit run_playbook_id triggers playbook execution; keyword matching is disabled.
        matched_playbook = None
        confirm_playbook = False   # True when match came from keyword heuristic (needs user OK)
        if run_playbook_id:
            idx = _ai._load_playbook_index()
            matched_playbook = next((p for p in idx if p["id"] == run_playbook_id), None)
        # Keyword-based auto-suggest disabled: playbooks are run manually only.

        # Run the agent (or playbook) in a background thread and drain events via a queue.
        # This lets us send SSE keepalive pings while SSH tool calls block,
        # preventing browsers from closing the connection on long-running tasks.
        _SENTINEL = object()
        event_queue = _queue.Queue()

        def _agent_thread():
            try:
                # Re-check AI gate — but allow direct playbook runs since they
                # call run_ansible_direct which makes no Claude API calls.
                if not _ai_enabled() and not (matched_playbook and not confirm_playbook):
                    event_queue.put({"type": "error",
                                     "content": "AI disabled — re-enable in Settings."})
                    event_queue.put(_SENTINEL)
                    return
                if matched_playbook and confirm_playbook:
                    # Emit a confirmation prompt — let the user decide before we run anything.
                    event_queue.put({
                        "type":        "playbook_confirm",
                        "id":          matched_playbook.get("id", ""),
                        "name":        matched_playbook.get("name", ""),
                        "description": matched_playbook.get("description", ""),
                        "message":     message,
                    })
                    event_queue.put(_SENTINEL)
                    return
                if matched_playbook:
                    # Direct playbook execution — no Claude API call needed.
                    pb_msg = message or f"Run playbook: {matched_playbook.get('name', matched_playbook.get('id', ''))}"
                    gen = _ai.run_ansible_direct(
                        session_id=session_id,
                        user_message=pb_msg,
                        playbook=matched_playbook,
                        devices_loader=_load_current_devices,
                        status_cache=device_status_cache,
                        connections_pool=connections,
                        pool_lock=lock,
                    )
                else:
                    gen = _ai.run_chat(
                        session_id=session_id,
                        user_message=message,
                        devices_loader=_load_current_devices,
                        status_cache=device_status_cache,
                        connections_pool=connections,
                        pool_lock=lock,
                        context_ip=context_ip,
                        device_context=device_context,
                        topology_context=topology_context,
                        attached_files=attached_files if attached_files else None,
                        workflow_flags=_load_workflow_flags(),
                    )
                for event in gen:
                    event_queue.put(event)
            except Exception as e:
                app.logger.error(f"AI stream error: {e}", exc_info=True)
                event_queue.put({"type": "error", "content": str(e)})
                event_queue.put({"type": "done"})
            finally:
                event_queue.put(_SENTINEL)

        t = threading.Thread(target=_agent_thread, daemon=True)
        t.start()

        def generate():
            while True:
                try:
                    # Wait up to 15 s for the next event.  If nothing arrives,
                    # send a keepalive comment so the browser stays connected.
                    event = event_queue.get(timeout=15)
                except _queue.Empty:
                    yield ": keepalive\n\n"
                    continue

                if event is _SENTINEL:
                    break
                yield f"data: {_json.dumps(event)}\n\n"

        return Response(
            _swc(generate()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    except Exception as e:
        app.logger.error(f"AI chat route error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/ai/topology_context")
def ai_topology_context():
    """Return a compact topology snapshot for browser caching.
    Serves from the server-side topology cache when available so the browser
    gets a response without triggering a full CDP discovery round.
    """
    # Try the on-disk topology cache first (avoids SSH round-trips).
    topo = _ai._topology_cache_load()
    if topo is None:
        # Cache miss — run discovery now and store the result.
        from modules.topology import discover_topology
        from modules.connection import get_persistent_connection
        devices = _load_current_devices()
        topo = discover_topology(
            devices=devices,
            connection_factory=get_persistent_connection,
            connections_pool=connections,
            pool_lock=lock,
            status_cache=device_status_cache,
            max_workers=5,
        )
        _ai._topology_cache_save(topo)
    return jsonify({"topology": topo})


@app.route("/ai/stop", methods=["POST"])
def ai_stop():
    """Signal the AI agent loop for a session to stop after the current tool call."""
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id") or "default"
    _ai.stop_session(session_id)
    return jsonify({"status": "stopping"})


@app.route("/ai/tool_cache_snapshot")
def ai_tool_cache_snapshot():
    """Return a snapshot of recently cached tool results for browser-side storage.
    The browser caches these in localStorage so repeated questions about interface
    status, routing tables, etc. can be answered without SSH round-trips."""
    snapshot = {}
    now = __import__("time").monotonic()
    for key, (result, expires_at) in list(_ai._tool_cache.items()):
        if expires_at > now:
            snapshot[key] = {
                "result":     result[:2000],   # cap per-entry size
                "expires_in": int(expires_at - now),
            }
    return jsonify({"cache": snapshot, "count": len(snapshot)})


@app.route("/ai/history", methods=["GET"])
def ai_history():
    """Return the conversation history as simplified display pairs."""
    session_id = request.args.get("session_id") or "main"
    raw = _ai.get_history(session_id)
    out = []
    for msg in raw:
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue
        content = msg.get("content", "")
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block["text"])
            text = "\n".join(parts)
        else:
            text = str(content)
        text = text.strip()
        if text:
            out.append({"role": role, "text": text})
    return jsonify(out)


@app.route("/ai/clear", methods=["POST"])
def ai_clear():
    """Clear the AI conversation history for a session."""
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id") or "default"
    _ai.clear_history(session_id)
    return jsonify({"status": "cleared"})


@app.route("/ai/restart", methods=["POST"])
def ai_restart():
    """Restart the Flask server (used after patch_app_file to apply code changes)."""
    import threading, sys
    def _restart():
        time.sleep(2)
        os.execv(sys.executable, [sys.executable] + sys.argv)
    threading.Thread(target=_restart, daemon=True).start()
    return jsonify({"status": "restarting", "message": "Server restarting in ~2 seconds"})


# ---------------------------------------------------------------------------
# Drift check routes — pure Python, no AI required
# ---------------------------------------------------------------------------

@app.route("/drift/status")
def drift_status():
    """Return drift checker status and last-run result."""
    from modules.drift_check import get_checker
    from modules.approval_queue import get_pending_count
    status = get_checker().status()
    status["pending_approvals"] = get_pending_count()
    return jsonify(status)


@app.route("/drift/check", methods=["POST"])
def drift_check_trigger():
    """Trigger an immediate drift check.  Returns immediately; check runs async."""
    from modules.drift_check import get_checker
    checker = get_checker()
    if checker._running:
        return jsonify({"ok": False, "message": "Drift check already in progress"}), 409
    checker.trigger()
    return jsonify({"ok": True, "message": "Drift check triggered"})


@app.route("/drift/check/sync", methods=["POST"])
def drift_check_sync():
    """Run a drift check synchronously and return the result.
    Suitable for manual 'Check Now' button clicks where the user wants to see results."""
    from modules.drift_check import run_drift_check, get_checker
    checker = get_checker()
    if checker._running:
        return jsonify({"ok": False, "message": "Drift check already in progress"}), 409
    try:
        result = run_drift_check(triggered_by="manual")
        # Update checker state so /drift/status reflects the fresh result
        checker._last_result = result
        checker._last_ts     = __import__("time").time()
        return jsonify(result)
    except Exception as exc:
        app.logger.error("drift check sync error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/drift/settings", methods=["GET"])
def drift_settings_get():
    """Return current drift check interval and disabled flag."""
    from modules.drift_check import _is_disabled, _get_interval
    return jsonify({
        "ok":        True,
        "interval_s": int(_get_interval()),
        "disabled":  _is_disabled(),
    })


@app.route("/drift/settings", methods=["POST"])
def drift_settings_post():
    """Update drift check interval and/or disabled flag."""
    from modules.drift_check import get_checker
    from modules.agent_timers import save as save_timers
    data     = request.get_json(silent=True) or {}
    checker  = get_checker()
    saved    = {}

    if "interval_s" in data:
        interval_s = int(data["interval_s"])
        save_timers({"drift_check_interval": interval_s})
        saved["interval_s"] = interval_s
        # Re-arm the scheduler with the new interval
        import time as _time
        checker._next_ts = _time.time() + interval_s
        checker._trigger.set()

    if "disabled" in data:
        checker.set_disabled(bool(data["disabled"]))
        saved["disabled"] = bool(data["disabled"])

    return jsonify({"ok": True, **saved})


@app.route("/jenkins/results")
def jenkins_results():
    """Return the latest local CI check results."""
    from modules.jenkins_runner import load_results
    results = load_results()
    if results is None:
        return jsonify({"ok": None, "message": "No checks have been run yet."})
    return jsonify(results)


@app.route("/jenkins/sync")
def jenkins_sync():
    """Fetch the current build status of all registered pipelines from Jenkins,
    prune any pipelines deleted from Jenkins, and update the local cache.
    No AI required — pure Jenkins API calls."""
    from modules.jenkins_runner import (
        sync_scheduled_build_results, prune_deleted_pipelines, load_results
    )
    try:
        pruned  = prune_deleted_pipelines()
        updated = sync_scheduled_build_results()
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    results = load_results()
    if results is None:
        results = {"ok": None, "message": "No data yet"}
    results["_synced"]  = updated
    results["_pruned"]  = pruned
    return jsonify(results)


@app.route("/session/pending-restart")
def session_pending_restart():
    """
    Return pending restart info so the frontend can auto-resume the AI session.
    The file is deleted after reading (one-shot) and expires after 120 seconds.
    """
    import time as _time
    path = os.path.join(os.path.dirname(__file__), "data", "pending_restart.json")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        # Expire stale markers (> 120 s old)
        if _time.time() - data.get("timestamp", 0) > 120:
            os.remove(path)
            return jsonify({})
        os.remove(path)
        return jsonify(data)
    except (FileNotFoundError, Exception):
        return jsonify({})


@app.route("/server/restart", methods=["POST"])
def server_restart():
    """Signal the watchdog launcher to restart the server process."""
    import threading, os as _os
    def _do():
        import time
        time.sleep(1)
        _os._exit(3)   # exit code 3 → launcher.py restarts the subprocess
    threading.Thread(target=_do, daemon=True).start()
    return jsonify({"status": "restarting", "message": "Server will restart in ~1 second."})


@app.route("/jenkins/pipelines")
def jenkins_pipelines():
    """Return the pipelines registered to the current device list."""
    from modules.jenkins_runner import load_list_pipelines
    return jsonify({"pipelines": load_list_pipelines()})


@app.route("/jenkins/history/<job_name>")
def jenkins_job_history(job_name):
    """Return recent build history for a specific Jenkins job."""
    from modules.jenkins_runner import load_config, get_job_builds
    try:
        cfg    = load_config()
        limit  = int(request.args.get("limit", 20))
        builds = get_job_builds(cfg, job_name, limit=limit)
        return jsonify({"job_name": job_name, "builds": builds})
    except Exception as exc:
        return jsonify({"error": str(exc), "builds": []}), 200


@app.route("/jenkins/run", methods=["POST"])
def jenkins_run():
    """Trigger a Jenkins build — one specific job or all jobs for this list."""
    data      = request.get_json(silent=True) or {}
    delay     = float(data.get("startup_delay", 0))
    job_name  = (data.get("job_name") or "").strip()
    from modules.jenkins_runner import run_checks, load_config, _trigger_jenkins, load_results
    if job_name:
        # Trigger a single specific pipeline
        try:
            cfg = load_config()
            _trigger_jenkins(cfg, job_name)
            return jsonify({"triggered": True, "job": job_name})
        except Exception as exc:
            return jsonify({"triggered": False, "error": str(exc)}), 200
    summary = run_checks(startup_delay=delay)
    return jsonify(summary)


@app.route("/jenkins/schedules")
def jenkins_schedules_get():
    """
    Return the current cron schedule for every pipeline registered to this list.
    Merges the locally stored schedules with live data from Jenkins when available.
    Response: {"schedules": {"job_name": {"cron": "H 6 * * *", "description": "Daily at ~6am"}}}
    """
    from modules.jenkins_runner import (
        load_list_pipelines, load_pipeline_schedules,
        load_config as _jcfg, get_job_config, extract_schedule_from_xml,
        save_pipeline_schedule,
    )
    jobs      = load_list_pipelines()
    local_sch = load_pipeline_schedules()
    result    = {}

    # Try to enrich with live Jenkins data; fall back to local cache on error.
    # IMPORTANT: only overwrite local cache when Jenkins returns a non-empty schedule.
    # An empty live result (e.g. trigger not yet applied, or a new job) must never
    # wipe a schedule that was just saved locally — that would cause the UI to show
    # "Not scheduled" immediately after a successful save.
    try:
        cfg = _jcfg()
        for job in jobs:
            try:
                xml  = get_job_config(cfg, job)
                cron = extract_schedule_from_xml(xml)
                if cron:
                    # Jenkins has an authoritative schedule — sync it locally
                    save_pipeline_schedule(job, cron)
                    local_sch[job] = cron
                # If cron is empty, keep whatever is in local_sch (user's last save)
            except Exception:
                pass
    except Exception:
        pass

    for job in jobs:
        cron = local_sch.get(job, "")
        result[job] = {
            "cron":        cron,
            "description": _describe_cron(cron),
        }

    return jsonify({"schedules": result})


@app.route("/jenkins/schedules/<path:job_name>", methods=["POST"])
def jenkins_schedule_set(job_name: str):
    """
    Set or clear the cron schedule for a pipeline.
    Body: {"cron": "H/30 * * * *"}   — set schedule
    Body: {"cron": ""}                — remove schedule
    """
    from modules.jenkins_runner import (
        load_config as _jcfg, get_job_config, update_jenkins_job,
        save_pipeline_schedule, extract_schedule_from_xml,
    )
    import re as _re
    data = request.get_json(silent=True) or {}
    cron = data.get("cron", "").strip()

    try:
        cfg     = _jcfg()
        xml_str = get_job_config(cfg, job_name)
    except Exception as exc:
        return jsonify({"error": f"Could not fetch job config: {exc}"}), 500

    if cron:
        new_triggers = (
            "<triggers>\n"
            "  <hudson.triggers.TimerTrigger>\n"
            f"    <spec>{cron}</spec>\n"
            "  </hudson.triggers.TimerTrigger>\n"
            "</triggers>"
        )
    else:
        new_triggers = "<triggers/>"

    # ── Targeted XML trigger replacement ──────────────────────────────────
    # Jenkins pipeline config.xml can contain <triggers> in three places:
    #   1. Inside <DeclarativeJobPropertyTrackerAction> — DO NOT touch (declarative syntax)
    #   2. Inside <PipelineTriggersJobProperty>        — update this one
    #   3. Root-level, after </definition>             — update this one
    # Replacing all occurrences blindly corrupts the declarative action block
    # and causes Jenkins to return HTTP 500.

    _TRIG_PAT = r"<triggers\s*/>|<triggers>[\s\S]*?</triggers>"

    # Update PipelineTriggersJobProperty triggers specifically
    xml_updated = _re.sub(
        r"(<org\.jenkinsci\.plugins\.workflow\.job\.properties\.PipelineTriggersJobProperty>\s*)"
        r"(?:<triggers\s*/>|<triggers>[\s\S]*?</triggers>)",
        lambda m: m.group(1) + new_triggers,
        xml_str,
    )

    # Update root-level triggers: it's the <triggers> block that comes after </definition>
    # (i.e. the last occurrence in the document, outside <properties>).
    all_matches = list(_re.finditer(_TRIG_PAT, xml_updated))
    # Filter out any match that sits inside a known declarative-action element by
    # checking whether there is a <DeclarativeJobPropertyTrackerAction> open tag
    # between the start of the document and the match that has no corresponding
    # close tag before the match.
    _declarative_open  = r"<org\.jenkinsci\.plugins\.pipeline\.modeldefinition\.action\.DeclarativeJobPropertyTrackerAction"
    _declarative_close = r"</org\.jenkinsci\.plugins\.pipeline\.modeldefinition\.action\.DeclarativeJobPropertyTrackerAction>"
    root_match = None
    for m in reversed(all_matches):
        before = xml_updated[:m.start()]
        opens  = len(_re.findall(_declarative_open, before))
        closes = len(_re.findall(_declarative_close, before))
        if opens == closes:   # not inside declarative action
            root_match = m
            break

    if root_match:
        xml_updated = (
            xml_updated[:root_match.start()]
            + new_triggers
            + xml_updated[root_match.end():]
        )
    else:
        # No root-level triggers block found — insert one before the closing root tag
        root_close = _re.search(r"</[a-zA-Z][\w.-]*>\s*$", xml_updated)
        if root_close:
            xml_updated = xml_updated[:root_close.start()] + new_triggers + "\n" + xml_updated[root_close.start():]
        else:
            xml_updated = xml_updated.rstrip() + "\n" + new_triggers

    try:
        update_jenkins_job(cfg, job_name, xml_updated)
    except Exception as exc:
        app.logger.error("jenkins_schedule_set: %s", exc)
        return jsonify({"error": str(exc)}), 500

    # Verify the schedule is actually present in Jenkins now
    verified = False
    try:
        live_xml  = get_job_config(cfg, job_name)
        live_cron = extract_schedule_from_xml(live_xml)
        # Jenkins may wrap cron in CDATA; strip it for comparison
        import re as _re
        live_cron = _re.sub(r"<!\[CDATA\[(.*?)]]>", r"\1", live_cron).strip()
        verified = (live_cron == cron) or (not cron and not live_cron)
    except Exception:
        pass  # Verification is best-effort; don't block the response

    # Persist locally regardless — the schedule was accepted by Jenkins even if
    # the round-trip parse is ambiguous (CDATA, whitespace, etc.)
    save_pipeline_schedule(job_name, cron)

    if not verified and cron:
        app.logger.warning(
            "jenkins_schedule_set: schedule '%s' saved for '%s' but could not verify "
            "it is live in Jenkins (live_cron=%r)", cron, job_name, live_cron if 'live_cron' in dir() else '?'
        )
        return jsonify({
            "ok":          True,
            "job":         job_name,
            "cron":        cron,
            "description": _describe_cron(cron),
            "warning":     "Schedule saved but could not confirm Jenkins applied it. Try saving again.",
        })

    return jsonify({
        "ok":          True,
        "job":         job_name,
        "cron":        cron,
        "description": _describe_cron(cron),
    })


def _describe_cron(cron: str) -> str:
    """Return a human-readable description of a Jenkins cron expression."""
    if not cron:
        return "Not scheduled (manual only)"
    presets = {
        "H/5 * * * *":   "Every 5 minutes",
        "H/15 * * * *":  "Every 15 minutes",
        "H/30 * * * *":  "Every 30 minutes",
        "H * * * *":     "Hourly",
        "H H/4 * * *":   "Every 4 hours",
        "H H/6 * * *":   "Every 6 hours",
        "H H/12 * * *":  "Every 12 hours",
        "H 0 * * *":     "Daily at midnight",
        "H 6 * * *":     "Daily at ~6am",
        "H 8 * * *":     "Daily at ~8am",
        "H 0 * * 1":     "Weekly on Monday",
        "H 0 * * 0":     "Weekly on Sunday",
    }
    return presets.get(cron, f"Custom: {cron}")


@app.route("/jenkins/webhook", methods=["POST"])
def jenkins_webhook():
    """Receive a build result notification from a real Jenkins server."""
    data = request.get_json(silent=True) or {}
    # Merge Jenkins result with any local results on disk
    from modules.jenkins_runner import load_results, _save_results, _recompute_summary
    build  = data.get("build", {})
    job    = data.get("name") or data.get("job") or "unknown"
    result = build.get("status", "")
    existing = load_results() or {}
    existing.setdefault("pipelines", {})
    existing["pipelines"][job] = {
        "jenkins_build":   build.get("number"),
        "jenkins_result":  result,
        "jenkins_ok":      result == "SUCCESS",
        "jenkins_pending": False,
        "jenkins_url":     build.get("full_url"),
        "jenkins_ran_at":  build.get("timestamp"),
    }
    _recompute_summary(existing)
    _save_results(existing)
    app.logger.info("Jenkins webhook received for '%s': %s", job, result)
    return jsonify({"status": "received"})


@app.route("/ai/playbooks")
def ai_playbooks():
    """Return the list of saved Ansible playbooks."""
    return jsonify({"playbooks": _ai._load_playbook_index()})


@app.route("/ai/playbooks/<playbook_id>", methods=["DELETE"])
def ai_delete_playbook(playbook_id):
    """Delete a saved playbook by id."""
    idx = _ai._load_playbook_index()
    pb  = next((p for p in idx if p["id"] == playbook_id), None)
    if not pb:
        return jsonify({"error": "not found"}), 404
    # Remove YAML file
    yml = os.path.join(_ai._get_playbooks_dir(), pb.get("file", ""))
    try:
        os.remove(yml)
    except FileNotFoundError:
        pass
    idx = [p for p in idx if p["id"] != playbook_id]
    _ai._save_playbook_index(idx)
    return jsonify({"status": "deleted", "id": playbook_id})


@app.route("/ai/report/<path:filename>")
def ai_download_report(filename):
    """Serve a saved network report as a Markdown file download."""
    rpt_dir = _ai._get_reports_dir()
    rpt_path = os.path.join(rpt_dir, os.path.basename(filename))
    if not os.path.isfile(rpt_path):
        return jsonify({"error": "Report not found"}), 404
    return send_file(
        rpt_path,
        as_attachment=True,
        download_name=os.path.basename(filename),
        mimetype="text/markdown",
    )


@app.route("/ci/appdir")
def ci_appdir():
    """Return the Flask application's BASE_DIR so Jenkins can cd into it for syntax checks."""
    return jsonify({"appdir": BASE_DIR})


# ---------------------------------------------------------------------------
# Change audit log
# ---------------------------------------------------------------------------

@app.route("/list/change_log")
def list_change_log():
    limit = min(int(request.args.get("limit", 50)), 200)
    log   = _ai._load_change_log()
    return jsonify({"changes": list(reversed(log[-limit:]))})


# ---------------------------------------------------------------------------
# Compliance policy
# ---------------------------------------------------------------------------

@app.route("/list/compliance_policy")
def list_compliance_policy():
    return jsonify(_ai._load_compliance_policy())


@app.route("/list/compliance_policy", methods=["POST"])
def list_compliance_policy_update():
    data   = request.get_json(silent=True) or {}
    action = data.get("action", "upsert")
    rule   = data.get("rule", {})
    policy = _ai._load_compliance_policy()
    rules  = policy.setdefault("rules", [])
    rid    = (rule.get("id") or "").strip()
    if action == "delete":
        policy["rules"] = [r for r in rules if r.get("id") != rid]
        _ai._save_compliance_policy(policy)
        return jsonify({"status": "deleted", "id": rid})
    if not rid:
        return jsonify({"error": "rule.id required"}), 400
    idx = next((i for i, r in enumerate(rules) if r.get("id") == rid), None)
    if idx is not None:
        rules[idx] = rule
    else:
        rules.append(rule)
    _ai._save_compliance_policy(policy)
    return jsonify({"status": "ok", "rule_count": len(rules)})


# ---------------------------------------------------------------------------
# Variable store
# ---------------------------------------------------------------------------

@app.route("/list/variables")
def list_variables():
    return jsonify(_ai._load_variables())


@app.route("/list/variables", methods=["POST"])
def list_variables_set():
    data = request.get_json(silent=True) or {}
    key  = (data.get("key") or "").strip()
    if not key:
        return jsonify({"error": "key required"}), 400
    variables = _ai._load_variables()
    variables[key] = {
        "value":       data.get("value", ""),
        "description": data.get("description", ""),
        "updated":     __import__("time").strftime("%Y-%m-%d %H:%M"),
    }
    _ai._save_variables(variables)
    return jsonify({"status": "ok", "key": key})


@app.route("/list/variables/<key>", methods=["DELETE"])
def list_variables_delete(key):
    variables = _ai._load_variables()
    if key not in variables:
        return jsonify({"error": "not found"}), 404
    del variables[key]
    _ai._save_variables(variables)
    return jsonify({"status": "deleted", "key": key})


@app.route("/list/variables/discover", methods=["POST"])
def list_variables_discover():
    """Trigger direct variable discovery from running configs (no AI, no token cost)."""
    def _run():
        from modules.variable_discovery import discover_variables_for_list
        devices = _load_current_devices()
        discover_variables_for_list(devices, status_cache=device_status_cache)

    t = threading.Thread(target=_run, daemon=True, name="var-discovery-manual")
    t.start()
    return jsonify({"status": "started", "message": "Variable discovery running in background — refresh the Variables tab in ~30 seconds."})


# ---------------------------------------------------------------------------
# NetBox source-of-truth sync
# ---------------------------------------------------------------------------

@app.route("/netbox/test_connection", methods=["POST"])
def netbox_test_connection():
    """Verify the NetBox URL + token work.

    Accepts optional overrides in the request body (so the Settings modal can
    test a pending change before saving it). Falls back to stored config.
    """
    from modules.netbox_client import test_connection, get_netbox_config
    data  = request.get_json(silent=True) or {}
    cfg   = get_netbox_config()
    url   = (data.get("url")   or cfg["url"]   or "").strip()
    token = (data.get("token") or cfg["token"] or "").strip()
    verify_tls = bool(data.get("verify_tls", cfg["verify_tls"]))

    # Persist the working auth scheme only when using the stored token,
    # so "Test" in the modal with a not-yet-saved token doesn't overwrite it.
    persist = not data.get("token")
    ok, message = test_connection(url, token, verify_tls, persist_scheme=persist)
    return jsonify({"ok": ok, "message": message})


@app.route("/netbox/status", methods=["GET"])
def netbox_status():
    """Return the last-sync summary for every list (plus in-progress markers)."""
    from modules.netbox_client import load_sync_status, get_netbox_config
    cfg = get_netbox_config()
    return jsonify({
        "configured": bool(cfg["url"] and cfg["token"]),
        "url":        cfg["url"],
        "status":     load_sync_status(),
        "lists":      get_device_lists(),
    })


@app.route("/netbox/sync", methods=["POST"])
def netbox_sync():
    """Sync the current (or a named) device list to NetBox in a background thread."""
    from modules.netbox_client import (
        sync_list_to_netbox, set_sync_running, get_netbox_config,
    )
    from modules.config import LISTS_DIR

    cfg = get_netbox_config()
    if not cfg["url"] or not cfg["token"]:
        return jsonify({"status": "error",
                        "message": "NetBox is not configured — set URL and API token first."}), 400

    data = request.get_json(silent=True) or {}
    list_name = (data.get("list_name") or "").strip()

    if list_name:
        # Look up the list's CSV file by name.
        all_lists = get_device_lists()
        match = next((l for l in all_lists if l["name"] == list_name), None)
        if not match:
            return jsonify({"status": "error", "message": f"List '{list_name}' not found"}), 404
        csv_path = os.path.join(LISTS_DIR, match["filename"], "devices.csv")
        devices  = load_saved_devices(csv_path)
    else:
        list_name, csv_path = get_current_device_list()
        devices = load_saved_devices(csv_path)

    if not devices:
        return jsonify({"status": "error", "message": f"List '{list_name}' has no devices"}), 400

    def _run(name=list_name, devs=devices):
        try:
            set_sync_running(name, True)
            sync_list_to_netbox(name, devs, status_cache=device_status_cache)
        except Exception as exc:
            app.logger.error("netbox_sync thread failed: %s", exc, exc_info=True)
        finally:
            set_sync_running(name, False)

    threading.Thread(target=_run, daemon=True, name=f"netbox-sync-{list_name}").start()
    set_sync_running(list_name, True)
    return jsonify({
        "status":    "started",
        "list":      list_name,
        "device_count": len(devices),
        "message":   f"NetBox sync started for '{list_name}' ({len(devices)} device(s)). Refresh in ~15–30s.",
    })


@app.route("/netbox/sync_all", methods=["POST"])
def netbox_sync_all():
    """Sync every device list to NetBox (one region per list)."""
    from modules.netbox_client import (
        sync_all_lists_to_netbox, set_sync_running, get_netbox_config,
    )
    from modules.config import LISTS_DIR

    cfg = get_netbox_config()
    if not cfg["url"] or not cfg["token"]:
        return jsonify({"status": "error",
                        "message": "NetBox is not configured — set URL and API token first."}), 400

    all_lists = get_device_lists()
    if not all_lists:
        return jsonify({"status": "error", "message": "No device lists available"}), 400

    # Load each list's devices up front (cheap — just CSV reads).
    lists_with_devices = []
    for lst in all_lists:
        csv_path = os.path.join(LISTS_DIR, lst["filename"], "devices.csv")
        lists_with_devices.append((lst["name"], load_saved_devices(csv_path)))

    def _run(payload=lists_with_devices):
        for name, _ in payload:
            set_sync_running(name, True)
        try:
            sync_all_lists_to_netbox(payload, status_cache=device_status_cache)
        except Exception as exc:
            app.logger.error("netbox_sync_all thread failed: %s", exc, exc_info=True)
        finally:
            for name, _ in payload:
                set_sync_running(name, False)

    threading.Thread(target=_run, daemon=True, name="netbox-sync-all").start()
    return jsonify({
        "status":    "started",
        "list_count": len(lists_with_devices),
        "message":   f"NetBox sync started for {len(lists_with_devices)} list(s). Refresh in ~15–30s.",
    })


@app.route("/netbox/remove", methods=["POST"])
def netbox_remove():
    """Delete all NetBox objects for a device list (devices → site → region)."""
    from modules.netbox_client import remove_list_from_netbox, get_netbox_config
    cfg = get_netbox_config()
    if not cfg["url"] or not cfg["token"]:
        return jsonify({"ok": False, "error": "NetBox is not configured"}), 400

    data      = request.get_json(silent=True) or {}
    list_name = (data.get("list_name") or "").strip()
    if not list_name:
        _, current_list_file = get_current_device_list()
        list_name = os.path.basename(os.path.dirname(current_list_file))
    if not list_name:
        return jsonify({"ok": False, "error": "No list name provided"}), 400

    result = remove_list_from_netbox(list_name)
    return jsonify(result), (200 if result["ok"] else 500)


@app.route("/netbox/query/devices", methods=["GET"])
def netbox_query_devices_route():
    from modules.netbox_client import netbox_query_devices
    result = netbox_query_devices(
        search=request.args.get("search", ""),
        site=request.args.get("site", ""),
        role=request.args.get("role", ""),
        tag=request.args.get("tag", ""),
    )
    return jsonify(result), (200 if result["ok"] else 500)


@app.route("/netbox/query/device", methods=["GET"])
def netbox_get_device_route():
    from modules.netbox_client import netbox_get_device
    name_or_ip = request.args.get("name", "").strip()
    if not name_or_ip:
        return jsonify({"ok": False, "error": "name parameter required"}), 400
    result = netbox_get_device(name_or_ip)
    return jsonify(result), (200 if result["ok"] else 404)


@app.route("/netbox/query/interfaces", methods=["GET"])
def netbox_get_interfaces_route():
    from modules.netbox_client import netbox_get_interfaces
    name_or_ip = request.args.get("name", "").strip()
    if not name_or_ip:
        return jsonify({"ok": False, "error": "name parameter required"}), 400
    result = netbox_get_interfaces(name_or_ip)
    return jsonify(result), (200 if result["ok"] else 404)


@app.route("/netbox/query/ip", methods=["GET"])
def netbox_get_ip_route():
    from modules.netbox_client import netbox_get_ip
    address = request.args.get("address", "").strip()
    if not address:
        return jsonify({"ok": False, "error": "address parameter required"}), 400
    result = netbox_get_ip(address)
    return jsonify(result), (200 if result["ok"] else 500)


@app.route("/netbox/query/prefixes", methods=["GET"])
def netbox_get_prefixes_route():
    from modules.netbox_client import netbox_get_prefixes
    result = netbox_get_prefixes(
        vrf=request.args.get("vrf", ""),
        prefix=request.args.get("prefix", ""),
    )
    return jsonify(result), (200 if result["ok"] else 500)


@app.route("/netbox/query/tunnels", methods=["GET"])
def netbox_get_vpn_tunnels_route():
    from modules.netbox_client import netbox_get_vpn_tunnels
    result = netbox_get_vpn_tunnels(device_name=request.args.get("device", ""))
    return jsonify(result), (200 if result["ok"] else 500)


# ---------------------------------------------------------------------------
# Golden configs
# ---------------------------------------------------------------------------

@app.route("/list/golden_configs")
def list_golden_configs_route():
    return jsonify({"golden_configs": _ai._list_golden_configs()})


@app.route("/bulk_restore_golden_config", methods=["POST"])
def bulk_restore_golden_config():
    """
    Restore the AI's stored golden configs for one or more devices.
    Accepts JSON: {"device_ips": ["1.2.3.4", ...]}
    Same source as the AI restore_golden_config tool — pushes line-by-line via SSH.
    """
    data = request.get_json(force=True, silent=True) or {}
    requested_ips = data.get("device_ips", [])
    if not requested_ips:
        return jsonify({"status": "error", "message": "No device IPs provided"}), 400

    _, current_list_file = get_current_device_list()
    devices = load_saved_devices(current_list_file)
    dev_by_ip = {d["ip"]: d for d in devices}

    results = []
    for ip in requested_ips:
        dev = dev_by_ip.get(ip)
        if not dev:
            results.append({"ip": ip, "status": "error", "message": "Device not in inventory"})
            continue

        cfg_text = _ai._load_golden_config_file(ip)
        if not cfg_text:
            results.append({"ip": ip, "status": "error", "message": "No golden config saved — save one via the AI first"})
            continue

        config_lines = [l for l in cfg_text.splitlines() if not l.startswith("!") and l.strip()]
        try:
            def _push(conn, lines=config_lines):
                conn.config_mode()
                try:
                    for line in lines:
                        run_device_command(conn, line)
                finally:
                    conn.exit_config_mode()
                return len(lines)

            n = with_temp_connection(dev, _push)
            results.append({"ip": ip, "status": "ok", "message": f"Restored {n} lines on {dev.get('hostname', ip)}"})
            app.logger.info(f"bulk_restore_golden_config: restored {ip} ({n} lines)")
        except Exception as exc:
            results.append({"ip": ip, "status": "error", "message": str(exc)})
            app.logger.error(f"bulk_restore_golden_config: failed {ip}: {exc}")

    ok_count  = sum(1 for r in results if r["status"] == "ok")
    err_count = len(results) - ok_count
    return jsonify({
        "status":    "success" if ok_count else "error",
        "message":   f"Restored {ok_count} device(s)" + (f", {err_count} failed" if err_count else ""),
        "results":   results,
    })


# ---------------------------------------------------------------------------
# Drift detection (quick endpoint for UI)
# ---------------------------------------------------------------------------

@app.route("/list/drift_status")
def list_drift_status():
    """Return a quick drift status (has_golden, drift) per device without full diff."""
    import difflib as _dl
    devices = _load_current_devices()
    result  = []
    for dev in devices:
        dip  = dev.get("ip", "")
        host = dev.get("hostname") or dip
        golden = _ai._load_golden_config_file(dip)
        result.append({
            "device_ip":  dip,
            "hostname":   host,
            "has_golden": golden is not None,
        })
    return jsonify({"devices": result})


@app.route("/ai/events")
def ai_events():
    """Return pending agent events from the background event monitor.

    Query params:
      ack=id1,id2,...  — acknowledge (hide) specific event IDs before returning
    """
    from modules.event_monitor import get_pending_events
    ack_param = request.args.get("ack", "")
    ack_ids   = [x.strip() for x in ack_param.split(",") if x.strip()]
    events    = get_pending_events(ack_ids or None)
    return jsonify({"events": events})


@app.route("/ai/events/clear", methods=["POST"])
def ai_events_clear():
    """Clear all pending agent events (e.g. on list switch)."""
    from modules.event_monitor import clear_events
    clear_events()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Background agent routes
# ---------------------------------------------------------------------------

@app.route("/ai/agent_log")
def ai_agent_log():
    """Return the background agent's activity log (newest first)."""
    if not _ai_enabled():
        return jsonify({"error": "AI is disabled", "status": {}, "entries": []}), 503
    from modules.agent_runner import get_activity_log, get_status
    limit = min(int(request.args.get("limit", 50)), 200)
    return jsonify({
        "status": get_status(),
        "entries": get_activity_log()[:limit],
    })


@app.route("/ai/agent_run", methods=["POST"])
def ai_agent_run():
    """Manually trigger a background agent task."""
    if not _ai_enabled():
        return jsonify({"error": "AI is disabled. Re-enable it in Settings."}), 503
    from modules.agent_runner import trigger_task
    data = request.get_json(silent=True) or {}
    task = (data.get("task") or "").strip()
    if not task:
        return jsonify({"error": "task is required"}), 400
    return jsonify(trigger_task(task))


@app.route("/ai/agent_pause", methods=["POST"])
def ai_agent_pause():
    """Pause autonomous background processing."""
    if not _ai_enabled():
        return jsonify({"error": "AI is disabled"}), 503
    from modules.agent_runner import pause_agent
    pause_agent()
    return jsonify({"ok": True, "paused": True})


@app.route("/ai/agent_resume", methods=["POST"])
def ai_agent_resume():
    """Resume autonomous background processing."""
    if not _ai_enabled():
        return jsonify({"error": "AI is disabled"}), 503
    from modules.agent_runner import resume_agent
    resume_agent()
    return jsonify({"ok": True, "paused": False})


@app.route("/ai/agent_timers", methods=["GET"])
def ai_agent_timers_get():
    """Return current timer configuration for the UI."""
    if not _ai_enabled():
        return jsonify({"ok": False, "error": "AI is disabled", "timers": []}), 503
    from modules.agent_timers import get_ui_config
    return jsonify({"ok": True, "timers": get_ui_config()})


@app.route("/ai/agent_timers", methods=["POST"])
def ai_agent_timers_post():
    """Save updated timer values. Accepts {key: value, ...}."""
    if not _ai_enabled():
        return jsonify({"ok": False, "error": "AI is disabled", "timers": []}), 503
    from modules.agent_timers import save as save_timers
    data = request.get_json(force=True) or {}
    saved = save_timers(data)
    return jsonify({"ok": True, "timers": saved})


# ---------------------------------------------------------------------------
# Approval queue routes
# ---------------------------------------------------------------------------

@app.route("/ai/approvals")
def ai_approvals_list():
    """Return pending approval requests (or all if ?all=1).

    Drift-check approvals are Python-generated and must be accessible
    regardless of AI state so the user can approve/reject config drift.
    """
    from modules.approval_queue import get_pending, get_all, get_pending_count
    show_all = request.args.get("all") == "1"
    limit    = min(int(request.args.get("limit", 50)), 200)
    entries  = get_all(limit) if show_all else get_pending()
    return jsonify({
        "pending_count": get_pending_count(),
        "entries":       entries,
        "ai_enabled":    _ai_enabled(),
    })


@app.route("/ai/approvals/<entry_id>/approve", methods=["POST"])
def ai_approval_approve(entry_id: str):
    """Approve a queued action and execute it immediately.

    Drift-check approvals execute via Python SSH — no AI needed.
    """
    from modules.approval_queue import resolve
    result = resolve(entry_id, "approve")
    if not result.get("ok"):
        return jsonify(result), 404
    return jsonify(result)


@app.route("/ai/approvals/<entry_id>/reject", methods=["POST"])
def ai_approval_reject(entry_id: str):
    """Reject a queued action without executing it."""
    from modules.approval_queue import resolve
    result = resolve(entry_id, "reject")
    if not result.get("ok"):
        return jsonify(result), 404
    return jsonify(result)


@app.route("/ai/approvals/approve_all", methods=["POST"])
def ai_approval_approve_all():
    """Approve and execute every currently pending approval."""
    from modules.approval_queue import get_pending, resolve
    pending = get_pending()
    results = []
    for entry in pending:
        results.append(resolve(entry["id"], "approve"))
    ok_count   = sum(1 for r in results if r.get("ok"))
    fail_count = len(results) - ok_count
    return jsonify({"ok": True, "approved": ok_count, "failed": fail_count, "results": results})


# ---------------------------------------------------------------------------
# Configure tab — push IOS config, create Jenkins verification pipeline
# ---------------------------------------------------------------------------

@app.route("/configure/apply", methods=["POST"])
def configure_apply():
    """
    Apply a network configuration to one or more devices.

    Intentionally simple — the goal is to get config onto devices quickly:
      1. Generate IOS commands from the selected type and params
      2. Safety check  — block genuinely dangerous commands (no SSH yet)
      3. Pre-backup    — save running-config so rollback is always possible
      4. Push          — canary device first, then fleet; write memory after each
      5. Golden config — saved immediately for every successfully configured device
      6. Verification  — create/update the Jenkins function pipeline and trigger
                         it asynchronously; results appear in the CI tab, they
                         do NOT block this response
      7. Audit log     — written regardless of outcome

    Jenkins CI verifies that existing features still work after new config is
    added.  It is advisory, not a gate.  The configure tab never waits for it.
    """
    import secrets as _sec
    from modules.configure import generate_config_commands, save_config_job
    from modules.device import load_saved_devices, decrypt_field
    from modules.jenkins_runner import load_config as _jcfg, _trigger_jenkins

    data        = request.get_json(silent=True) or {}
    config_type = data.get("config_type", "")
    per_device  = data.get("per_device")
    params      = data.get("params", {})
    device_ips  = data.get("device_ips", [])

    if not config_type:
        return jsonify({"ok": False, "error": "config_type is required"}), 400

    if per_device:
        ip_params_map = {e["ip"]: e["params"] for e in per_device if "ip" in e}
        device_ips    = list(ip_params_map.keys())
    else:
        ip_params_map = {}

    if not device_ips:
        return jsonify({"ok": False, "error": "No devices specified"}), 400

    _, current_list_file = get_current_device_list()
    all_devices = load_saved_devices(current_list_file)
    device_map  = {d["ip"]: d for d in all_devices}
    selected    = [device_map[ip] for ip in device_ips if ip in device_map]
    if not selected:
        return jsonify({"ok": False, "error": "None of the selected IPs found in device list"}), 400

    # ── Step 1: Generate commands (local, no I/O) ────────────────────────────
    rendered: dict[str, list[str]] = {}
    for dev in selected:
        ip = dev["ip"]
        p  = ip_params_map.get(ip, params) if per_device else params
        try:
            rendered[ip] = generate_config_commands(config_type, p)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    # ── Step 2: Push to devices — canary first, then fleet ───────────────────
    push_results: list[dict] = []
    canary_ip = device_ips[0] if device_ips else None
    ordered   = [canary_ip] + [ip for ip in device_ips if ip != canary_ip]

    canary_failed = False
    for ip in ordered:
        dev = device_map.get(ip)
        if not dev:
            continue
        hn   = dev.get("hostname", ip)
        cmds = rendered.get(ip, [])
        r    = {"ip": ip, "hostname": hn, "ok": False,
                "output": "", "error": None, "commands": cmds}

        if canary_failed:
            r["error"] = "Skipped — canary device failed"
            push_results.append(r)
            continue

        try:
            conn = get_persistent_connection(dev, connections, lock)
            with _device_lock(ip):
                conn.enable()
                # Use send_command_timing throughout — no prompt pattern matching
                # at all, so IOS warning lines (e.g. /31 subnet, implicit ACE
                # denied, "% Incomplete command") never cause a timeout.
                # send_command_timing just waits a fixed delay and returns
                # whatever the device sent; it works on every IOS version.
                out_parts = []
                conn.send_command_timing("configure terminal",
                                         delay_factor=2, read_timeout=10)
                for cmd in cmds:
                    out = conn.send_command_timing(cmd,
                                                   delay_factor=1,
                                                   read_timeout=10)
                    if out.strip():
                        out_parts.append(out)
                conn.send_command_timing("end", delay_factor=2, read_timeout=10)
                conn.send_command_timing("write memory",
                                         delay_factor=3, read_timeout=30)
                r["output"] = "\n".join(out_parts)[:500]
            r["ok"] = True

        except Exception as exc:
            r["error"] = str(exc)
            app.logger.warning("configure: push failed for %s: %s", hn, exc)
            if ip == canary_ip:
                canary_failed = True

        push_results.append(r)

    # ── Step 6: Verification pipeline (async, non-blocking) ─────────────────
    succeeded_ips      = [r["ip"] for r in push_results if r["ok"]]
    config_id          = f"cfg-{int(time.time())}-{_sec.token_hex(4)}"
    pipeline_triggered = False
    pipeline_error     = None
    job_name           = ""

    if succeeded_ips:
        try:
            from modules.pipeline_builder import ensure_function_pipeline
            jenkins_cfg  = _jcfg()
            params_by_ip = {ip: (ip_params_map.get(ip, params) if per_device else params)
                            for ip in succeeded_ips}
            pr = ensure_function_pipeline(
                config_type     = config_type,
                newly_added_ips = succeeded_ips,
                params_by_ip    = params_by_ip,
                jenkins_cfg     = jenkins_cfg,
                nmas_base       = request.host_url.rstrip("/"),
            )
            job_name      = pr.get("job_name", "")
            pipeline_error = pr.get("error")
            if pr.get("ok") and job_name:
                try:
                    _trigger_jenkins(jenkins_cfg, job_name)
                    pipeline_triggered = True
                except Exception as exc:
                    pipeline_error = str(exc)
        except Exception as exc:
            pipeline_error = str(exc)
            app.logger.warning("configure: verification pipeline failed: %s", exc)

        # Persist job metadata for status tracking
        first_ip     = succeeded_ips[0]
        check_params = ip_params_map.get(first_ip, params) if per_device else params
        check_devices = []
        for dev in selected:
            if dev["ip"] not in succeeded_ips:
                continue
            try:
                pwd = decrypt_field(dev["password"])
            except Exception:
                pwd = dev.get("password", "")
            check_devices.append({
                "hostname": dev.get("hostname", dev["ip"]),
                "ip":       dev["ip"],
                "username": dev.get("username", ""),
                "password": pwd,
            })
        save_config_job(config_id, {
            "config_id":   config_id,
            "token":       _sec.token_hex(16),
            "config_type": config_type,
            "params":      check_params,
            "devices":     [{"ip": d["ip"], "hostname": d.get("hostname", d["ip"])}
                            for d in selected if d["ip"] in succeeded_ips],
            "job_name":    job_name,
            "created_at":  time.strftime("%Y-%m-%d %H:%M:%S"),
            "status":      "pipeline_running" if pipeline_triggered else "pipeline_skipped",
        })

    # ── Step 7: Audit log ────────────────────────────────────────────────────
    try:
        from modules.pipeline import _audit_dir
        import json as _json
        _audit_entry = {
            "schema_version":    1,
            "config_id":         config_id,
            "timestamp":         time.strftime("%Y-%m-%d %H:%M:%S"),
            "config_type":       config_type,
            "devices":           [{"ip": r["ip"], "hostname": r["hostname"]}
                                  for r in push_results],
            "push_results":      {r["ip"]: {"ok": r["ok"], "error": r["error"]}
                                  for r in push_results},
            "pipeline_job":      job_name,
            "pipeline_triggered": pipeline_triggered,
        }
        _ap = os.path.join(_audit_dir(), f"{config_id}.json")
        with open(_ap, "w", encoding="utf-8") as _fh:
            _json.dump(_audit_entry, _fh, indent=2)
    except Exception as exc:
        app.logger.warning("configure: audit log failed: %s", exc)

    all_ok = all(r["ok"] for r in push_results)
    return jsonify({
        "ok":                 all_ok,
        "config_id":          config_id,
        "commands":           list(dict.fromkeys(c for cs in rendered.values() for c in cs)),
        "push_results":       push_results,
        "pipeline_triggered": pipeline_triggered,
        "pipeline_job":       job_name,
        "pipeline_error":     pipeline_error,
    }), (200 if all_ok else 207)


@app.route("/configure/kb_schema")
def configure_kb_schema():
    """Return form-field schema for a CCIE KB topic/subtopic."""
    from modules.ccie_kb import get_fields, list_topics
    topic    = request.args.get("topic", "").strip()
    subtopic = request.args.get("subtopic", "").strip() or None
    if not topic:
        return jsonify({"ok": False, "error": "topic is required",
                        "available": list_topics()}), 400
    fields = get_fields(topic, subtopic)
    return jsonify({"ok": True, "topic": topic, "subtopic": subtopic, "fields": fields})


@app.route("/configure/build_pipelines", methods=["POST"])
def configure_build_pipelines():
    """
    Bootstrap or refresh all persistent function pipelines for the current list.
    Scans golden configs to detect active network functions and creates/updates
    a verification pipeline for each one.  Safe to call repeatedly.
    """
    from modules.pipeline_builder import bootstrap_all_pipelines
    from modules.device import load_saved_devices, decrypt_field
    from modules.jenkins_runner import load_config as _jcfg

    _, current_list_file = get_current_device_list()
    all_devices = load_saved_devices(current_list_file)
    check_devices = []
    for dev in all_devices:
        try:
            pwd = decrypt_field(dev["password"])
        except Exception:
            pwd = dev.get("password", "")
        check_devices.append({
            "hostname": dev.get("hostname", dev["ip"]),
            "ip":       dev["ip"],
            "username": dev.get("username", ""),
            "password": pwd,
        })

    jenkins_cfg = _jcfg()
    nmas_base   = request.host_url.rstrip("/")
    result      = bootstrap_all_pipelines(check_devices, jenkins_cfg, nmas_base)
    return jsonify(result), (200 if result.get("ok") else 500)


@app.route("/configure/audit_latest", methods=["GET"])
def configure_audit_latest():
    """Return the most recent pipeline audit entry (used by Jenkinsfile stage 4 health check)."""
    from modules.pipeline import list_audit_entries
    entries = list_audit_entries(limit=1)
    if not entries:
        return jsonify({"ok": True, "entry": None, "message": "No audit entries yet"}), 200
    return jsonify({"ok": True, "entry": entries[0]}), 200


@app.route("/configure/audit/<config_id>", methods=["GET"])
def configure_audit_entry(config_id: str):
    """Return the audit log entry for a specific config_id."""
    from modules.pipeline import load_audit_entry
    entry = load_audit_entry(config_id)
    if not entry:
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify({"ok": True, "entry": entry}), 200


@app.route("/configure/pipeline_success", methods=["POST"])
def configure_pipeline_success():
    """
    Called by Jenkins when a verification pipeline passes.

    Golden configs are already saved at push time, so this callback simply
    marks the job as verified.  No approval queue — the user already approved
    the change by clicking Apply; the pipeline confirms the change worked.
    """
    from modules.configure import load_config_job, update_config_job

    data      = request.get_json(silent=True) or {}
    config_id = data.get("config_id", "")
    token     = data.get("token", "")

    job = load_config_job(config_id)
    if not job:
        return jsonify({"ok": False, "error": "config_id not found"}), 404
    if job.get("token") != token:
        return jsonify({"ok": False, "error": "invalid token"}), 403

    update_config_job(config_id, status="verified",
                      verified_at=time.strftime("%Y-%m-%d %H:%M:%S"))
    devices = job.get("devices", [])
    app.logger.info(
        "configure: pipeline verified for %s — %s on %d device(s)",
        config_id, job.get("config_type", "?"), len(devices),
    )
    return jsonify({"ok": True, "verified": len(devices)})


@app.route("/configure/interfaces")
def configure_interfaces():
    """Return interface names for the given device IPs (query param: ips=ip1,ip2,...)."""
    from modules.topology import parse_ip_interfaces
    ips_param = request.args.get("ips", "")
    ips = [i.strip() for i in ips_param.split(",") if i.strip()]
    if not ips:
        return jsonify({"interfaces": []})

    _, current_list_file = get_current_device_list()
    from modules.device import load_saved_devices
    all_devices = load_saved_devices(current_list_file)
    device_map  = {d["ip"]: d for d in all_devices}

    seen: set[str] = set()
    interfaces: list[str] = []
    for ip in ips:
        dev = device_map.get(ip)
        if not dev:
            continue
        try:
            with _device_lock(ip):
                conn = get_persistent_connection(dev, connections, lock)
                if conn is None:
                    continue
                out  = conn.send_command("show ip interface brief")
            for entry in parse_ip_interfaces(out):
                name = entry["interface"]
                if name not in seen:
                    seen.add(name)
                    interfaces.append(name)
        except Exception as exc:
            app.logger.debug("configure_interfaces: %s: %s", ip, exc)

    interfaces.sort()
    return jsonify({"interfaces": interfaces})


@app.route("/configure/devices")
def configure_devices():
    """Return devices in the current list with their online status."""
    _, current_list_file = get_current_device_list()
    from modules.device import load_saved_devices
    devices = load_saved_devices(current_list_file)
    result = []
    for d in devices:
        ip = d.get("ip", "")
        result.append({
            "ip":       ip,
            "hostname": d.get("hostname", ip),
            "online":   bool(device_status_cache.get(ip, False)),
        })
    return jsonify({"devices": result})


@app.route("/jenkins/create_job", methods=["POST"])
def jenkins_create_job_route():
    """Create a Jenkins job from the wizard-generated pipeline XML."""
    from modules.jenkins_runner import load_config as _jcfg, create_jenkins_job, register_pipeline
    data = request.get_json(silent=True) or {}
    job_name     = data.get("job_name", "").strip()
    pipeline_xml = data.get("pipeline_xml", "").strip()
    if not job_name or not pipeline_xml:
        return jsonify({"ok": False, "error": "job_name and pipeline_xml are required"}), 400
    jenkins_cfg = _jcfg()
    if not jenkins_cfg.get("jenkins_url"):
        return jsonify({"ok": False, "error": "Jenkins not configured — set URL in Settings"}), 400
    try:
        create_jenkins_job(jenkins_cfg, job_name, pipeline_xml)
        register_pipeline(job_name)
        return jsonify({"ok": True, "job": job_name})
    except Exception as exc:
        app.logger.warning("jenkins_create_job: %s", exc)
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/configure/networks")
def configure_networks():
    """Return connected networks for selected devices (query param: ips=ip1,ip2,...).
    Used to auto-populate OSPF/EIGRP/BGP network tables."""
    import re as _re
    ips_param = request.args.get("ips", "")
    ips = [i.strip() for i in ips_param.split(",") if i.strip()]
    if not ips:
        return jsonify({"networks": []})

    _, current_list_file = get_current_device_list()
    from modules.device import load_saved_devices
    all_devices = load_saved_devices(current_list_file)
    device_map  = {d["ip"]: d for d in all_devices}

    seen: set = set()
    networks: list = []
    for ip in ips:
        dev = device_map.get(ip)
        if not dev:
            continue
        try:
            with _device_lock(ip):
                conn = get_persistent_connection(dev, connections, lock)
                if conn is None:
                    continue
                route_out = conn.send_command("show ip route connected")
                # Fallback: if no connected routes found (e.g. interfaces down/down),
                # parse interface addresses directly from show ip interface
                intf_out = ""
                if not _re.search(r'\bC\s+[\d.]+/[\d]+', route_out):
                    intf_out = conn.send_command("show ip interface")

            def _net_from_prefix(ip_addr, preflen):
                """Return (network, mask, wildcard) for an IP/preflen."""
                ip_int = sum(int(b) << (24 - 8 * i) for i, b in enumerate(ip_addr.split(".")))
                mask_bits = (0xFFFFFFFF << (32 - preflen)) & 0xFFFFFFFF
                net_int  = ip_int & mask_bits
                net  = ".".join(str((net_int  >> (8 * j)) & 0xFF) for j in (3, 2, 1, 0))
                mask = ".".join(str((mask_bits >> (8 * j)) & 0xFF) for j in (3, 2, 1, 0))
                wild = ".".join(str(255 - int(x)) for x in mask.split("."))
                return net, mask, wild

            # Parse "C  10.0.0.0/24 is directly connected, ..."
            for line in route_out.splitlines():
                m = _re.search(r'C\s+([\d.]+)/([\d]+)', line)
                if m:
                    prefix, preflen = m.group(1), int(m.group(2))
                    net, mask, wild = _net_from_prefix(prefix, preflen)
                    key = f"{net}/{preflen}"
                    if key not in seen:
                        seen.add(key)
                        networks.append({"network": net, "mask": mask, "wildcard": wild, "prefix": key})

            # Fallback: parse "Internet address is 10.0.1.1/30" from show ip interface
            for line in intf_out.splitlines():
                m = _re.search(r'Internet address is ([\d.]+)/([\d]+)', line)
                if m:
                    ip_addr, preflen = m.group(1), int(m.group(2))
                    net, mask, wild = _net_from_prefix(ip_addr, preflen)
                    key = f"{net}/{preflen}"
                    if key not in seen:
                        seen.add(key)
                        networks.append({"network": net, "mask": mask, "wildcard": wild, "prefix": key})
        except Exception as exc:
            app.logger.debug("configure_networks: %s: %s", ip, exc)

    networks.sort(key=lambda n: n["network"])
    return jsonify({"networks": networks})


@app.route("/golden_configs/auto_create", methods=["POST"])
def golden_configs_auto_create():
    """For each device in the current list that has no golden config, fetch
    show running-config and save it as the baseline golden config."""
    from modules.ai_assistant import (
        _find_golden_config_file, _save_golden_config_file,
        _get_running_config_for_golden,
    )
    _, current_list_file = get_current_device_list()
    from modules.device import load_saved_devices
    devices = load_saved_devices(current_list_file)

    created = []
    skipped = []
    failed  = []
    for dev in devices:
        ip       = dev.get("ip", "")
        hostname = dev.get("hostname", ip)
        if _find_golden_config_file(ip):
            skipped.append({"ip": ip, "hostname": hostname, "reason": "already exists"})
            continue
        if not device_status_cache.get(ip, False):
            failed.append({"ip": ip, "hostname": hostname, "reason": "offline"})
            continue
        try:
            cfg = _get_running_config_for_golden(ip, hostname)
            if cfg:
                _save_golden_config_file(ip, hostname, cfg)
                created.append({"ip": ip, "hostname": hostname})
            else:
                failed.append({"ip": ip, "hostname": hostname, "reason": "empty config"})
        except Exception as exc:
            app.logger.warning("auto_create golden config %s: %s", hostname, exc)
            failed.append({"ip": ip, "hostname": hostname, "reason": str(exc)})

    return jsonify({"ok": True, "created": created, "skipped": skipped, "failed": failed})


@app.route("/monitoring/config", methods=["GET", "POST"])
def monitoring_config():
    """GET: return collector config. POST: update one or more fields."""
    from modules.collector_config import (
        get_full_config, set_collector_ip, set_snmp_community,
        set_netflow_port, set_snmp_trap_port,
    )
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        if "collector_ip" in data:
            set_collector_ip(data["collector_ip"])
        if "snmp_community_ro" in data:
            set_snmp_community(data["snmp_community_ro"], "ro")
        if "snmp_community_rw" in data:
            set_snmp_community(data["snmp_community_rw"], "rw")
        if "netflow_port" in data:
            set_netflow_port(int(data["netflow_port"]))
        if "snmp_trap_port" in data:
            set_snmp_trap_port(int(data["snmp_trap_port"]))
        return jsonify({"ok": True, "config": get_full_config()})
    return jsonify(get_full_config())


@app.route("/monitoring/interfaces")
def monitoring_interfaces():
    """Return local network interfaces (to help user choose collector IP)."""
    from modules.collector_config import list_local_interfaces
    return jsonify(list_local_interfaces())


@app.route("/monitoring/snmp/poll", methods=["POST"])
def monitoring_snmp_poll():
    """Poll a device OID via SNMP."""
    from modules.snmp_collector import snmp_get
    from modules.collector_config import get_snmp_community
    data      = request.get_json(silent=True) or {}
    device_ip = data.get("device_ip", "").strip()
    oids      = data.get("oids", ["sysDescr", "sysName", "sysUpTime"])
    community = data.get("community") or get_snmp_community("ro")
    version   = int(data.get("version", 2))
    if not device_ip:
        return jsonify({"error": "device_ip required"}), 400
    try:
        rows = snmp_get(device_ip, oids, community, version)
        return jsonify({"device_ip": device_ip, "results": [{"oid": o, "value": v} for o, v in rows]})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/monitoring/snmp/traps")
def monitoring_snmp_traps():
    from modules.snmp_collector import get_recent_traps
    from modules.device import load_saved_devices
    limit = int(request.args.get("limit", 50))
    _, current_list_file = get_current_device_list()
    device_ips = {d["ip"] for d in load_saved_devices(current_list_file)}
    return jsonify({"traps": get_recent_traps(limit, device_ips=device_ips)})


@app.route("/monitoring/netflow")
def monitoring_netflow():
    from modules.netflow_collector import get_flow_stats, get_recent_flows
    from modules.device import load_saved_devices
    include_flows = int(request.args.get("flows", 0))
    _, current_list_file = get_current_device_list()
    device_ips = {d["ip"] for d in load_saved_devices(current_list_file)}
    stats = get_flow_stats(device_ips=device_ips)
    result = {"stats": stats}
    if include_flows:
        result["recent_flows"] = get_recent_flows(include_flows, device_ips=device_ips)
    return jsonify(result)


@app.route("/monitoring/snmp/traps/clear", methods=["POST"])
def clear_snmp_traps():
    from modules.snmp_collector import clear_traps
    clear_traps()
    return jsonify({"ok": True})


@app.route("/monitoring/netflow/clear", methods=["POST"])
def clear_netflow_flows():
    from modules.netflow_collector import clear_flows
    clear_flows()
    return jsonify({"ok": True})


@app.route("/ai/debug_log")
def ai_debug_log():
    """Return the last N lines of data/ai_debug.log for in-browser diagnostics."""
    log_path = os.path.join(os.path.dirname(__file__), "data", "ai_debug.log")
    lines_param = request.args.get("lines", "200")
    try:
        n = min(int(lines_param), 2000)
    except ValueError:
        n = 200
    try:
        with open(log_path, encoding="utf-8") as fh:
            all_lines = fh.readlines()
        tail = "".join(all_lines[-n:])
        return tail, 200, {"Content-Type": "text/plain; charset=utf-8"}
    except FileNotFoundError:
        return "ai_debug.log not yet created (no AI requests made yet).\n", 404, {
            "Content-Type": "text/plain; charset=utf-8"
        }


# ---------------------------------------------------------------------------
# Start background daemons — must be here so _load_current_devices is defined
# ---------------------------------------------------------------------------
def _start_background_daemons():
    # Repair any corrupted chat histories on startup (orphaned tool_use blocks
    # left by interrupted or max_tokens-truncated sessions cause 400 errors).
    try:
        from modules.ai_assistant import (
            _HISTORIES_DIR, _sanitize_trailing_tool_use, _compress_for_disk,
        )
        import glob, json as _json
        for _path in glob.glob(os.path.join(_HISTORIES_DIR, "*.json")):
            try:
                with open(_path, encoding="utf-8") as _fh:
                    _hist = _json.load(_fh)
                _repaired = _sanitize_trailing_tool_use(_hist)
                if len(_repaired) != len(_hist):
                    with open(_path, "w", encoding="utf-8") as _fh:
                        _json.dump(_repaired, _fh, ensure_ascii=False)
                    app.logger.info("Repaired chat history: %s", os.path.basename(_path))
            except Exception:
                pass
    except Exception as _repair_exc:
        app.logger.debug("History repair skipped: %s", _repair_exc)

    from modules.event_monitor import start_monitor as _start_event_monitor
    _start_event_monitor()

    from modules.agent_runner import start_agent_loop as _start_agent_loop
    _start_agent_loop(
        devices_loader   = _load_current_devices,
        status_cache     = device_status_cache,
        connections_pool = {},
        pool_lock        = threading.Lock(),
    )

    # Start standalone Python drift checker (independent of AI state)
    try:
        from modules.drift_check import get_checker as _get_drift_checker
        _get_drift_checker().start()
    except Exception as _e:
        app.logger.warning("Drift checker startup: %s", _e)

    # Start SNMP trap receiver and NetFlow collector using per-list config
    try:
        from modules.collector_config import get_snmp_trap_port, get_netflow_port
        from modules.snmp_collector import start_trap_receiver
        from modules.netflow_collector import start_netflow_receiver
        start_trap_receiver(port=get_snmp_trap_port())
        start_netflow_receiver(port=get_netflow_port())
    except Exception as _e:
        app.logger.warning("Monitoring daemons: %s", _e)

_start_background_daemons()


# Run the Flask app with Socket.IO
if __name__ == "__main__":
    import sys
    try:
        url = f"http://{'127.0.0.1' if FLASK_HOST == '0.0.0.0' else FLASK_HOST}:{FLASK_PORT}"
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
        socketio.run(app, host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG, use_reloader=False)
    except Exception as e:
        print(f"\n{'='*60}")
        print(f"ERROR: {e}")
        print(f"{'='*60}")
        import traceback
        traceback.print_exc()
        if getattr(sys, 'frozen', False):
            input("\nPress Enter to exit...")
        sys.exit(1)
