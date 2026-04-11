# Dustin Marchak
# CSCI 5020 - Final Project
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
    set_user_setting
)
from modules.connection import ping_worker, get_persistent_connection, close_persistent_connection, with_temp_connection
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
from modules.topology import discover_topology

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

    return render_template(
        "index.html",
        devices=devices,
        device_lists=device_lists,
        current_list=current_list_name,
        tftp_server=TFTP_SERVER_IP
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

        save_device(
            {
                "device_type": "cisco_ios",
                "ip": ip,
                "username": username,
                "password": password,
                "secret": secret,
                "hostname": hostname,
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
    """Delete a device list."""
    try:
        success, message = delete_device_list_func(list_name)

        if success:
            app.logger.info(f"Deleted device list: {list_name}")
            flash(message, "success")
            return jsonify({"status": "success", "message": message})
        else:
            return jsonify({"status": "error", "message": message}), 400

    except Exception as e:
        app.logger.error(f"Failed to delete device list: {e}")
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


@app.route("/device/<ip>/restore_golden_config", methods=["POST"])
def restore_golden_config(ip):
    """Restore golden config from flash:golden_config.txt to startup-config."""
    try:
        _, current_list_file = get_current_device_list()
        devices = load_saved_devices(current_list_file)
        dev = next((d for d in devices if d["ip"] == ip), None)

        if not dev:
            flash("Device not found", "danger")
            return redirect(url_for("index"))

        app.logger.info(f"Restoring golden config on device: {ip}")

        def execute_restore(conn):
            # Use copy command to restore golden config to startup
            output = conn.send_command_timing("copy flash:golden_config.txt startup-config")
            # Handle confirmation prompts
            if "Destination filename" in output or "?" in output:
                output += conn.send_command_timing("")  # Accept default filename
            if "[confirm]" in output.lower() or "confirm" in output.lower():
                output += conn.send_command_timing("")  # Confirm
            return output

        output = with_temp_connection(dev, execute_restore)

        app.logger.info(f"Golden config restored on {ip}")
        flash(f"Golden config restored to startup-config on {dev['hostname']}", "success")

        # Get active tab from form
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

        return jsonify({"status": "success", "topology": topology})

    except Exception as e:
        app.logger.error(f"Topology discovery failed: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


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


def _run_subnet_discovery(op_id: str, hosts: list, username: str,
                          password: str, secret: str, device_type: str,
                          max_workers: int) -> None:
    """Background thread: probe every IP in `hosts` via SSH and record results."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from modules.connection import verify_device_connection

    op = _discovery_ops[op_id]

    def probe(ip: str):
        try:
            hostname = verify_device_connection(ip, username, password, secret, device_type)
            return {"ip": ip, "hostname": hostname, "success": True}
        except Exception as exc:
            return {"ip": ip, "success": False, "error": str(exc)}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(probe, ip): ip for ip in hosts}
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
            "total":     len(hosts),
            "completed": 0,
            "found":     [],
            "status":    "running",
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
        run_playbook_id    = data.get("run_playbook_id") or None    # direct playbook execution
        skip_playbook_match = bool(data.get("skip_playbook_match"))  # bypass matching (auto-fix path)

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
        # Priority: explicit run_playbook_id > keyword match on message.
        # skip_playbook_match bypasses matching so auto-troubleshoot messages go to Claude,
        # not back into the playbook runner (which would cause an infinite loop).
        matched_playbook = None
        if run_playbook_id:
            idx = _ai._load_playbook_index()
            matched_playbook = next((p for p in idx if p["id"] == run_playbook_id), None)
        elif message and not skip_playbook_match:
            matched_playbook = _ai.match_playbook(message)

        # Run the agent (or playbook) in a background thread and drain events via a queue.
        # This lets us send SSE keepalive pings while SSH tool calls block,
        # preventing browsers from closing the connection on long-running tasks.
        _SENTINEL = object()
        event_queue = _queue.Queue()

        def _agent_thread():
            try:
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


@app.route("/jenkins/results")
def jenkins_results():
    """Return the latest local CI check results."""
    from modules.jenkins_runner import load_results
    results = load_results()
    if results is None:
        return jsonify({"ok": None, "message": "No checks have been run yet."})
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

    # Try to enrich with live Jenkins data; fall back to local cache on error
    try:
        cfg = _jcfg()
        for job in jobs:
            try:
                xml    = get_job_config(cfg, job)
                cron   = extract_schedule_from_xml(xml)
                # Sync live value back to local cache
                save_pipeline_schedule(job, cron)
                local_sch[job] = cron
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

    xml_updated = _re.sub(
        r"<triggers\s*/>|<triggers>.*?</triggers>",
        new_triggers, xml_str, flags=_re.DOTALL,
    )
    if xml_updated == xml_str:
        xml_updated = xml_str.replace("</flow-definition>", new_triggers + "\n</flow-definition>")

    try:
        update_jenkins_job(cfg, job_name, xml_updated)
        save_pipeline_schedule(job_name, cron)
    except Exception as exc:
        return jsonify({"error": f"Could not update job: {exc}"}), 500

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
    import os as _os
    yml = _os.path.join(_ai._PLAYBOOKS_DIR, pb.get("file", ""))
    try:
        _os.remove(yml)
    except FileNotFoundError:
        pass
    idx = [p for p in idx if p["id"] != playbook_id]
    _ai._save_playbook_index(idx)
    return jsonify({"status": "deleted", "id": playbook_id})


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


# ---------------------------------------------------------------------------
# Golden configs
# ---------------------------------------------------------------------------

@app.route("/list/golden_configs")
def list_golden_configs_route():
    return jsonify({"golden_configs": _ai._list_golden_configs()})


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
    from modules.agent_runner import get_activity_log, get_status
    limit = min(int(request.args.get("limit", 50)), 200)
    return jsonify({
        "status": get_status(),
        "entries": get_activity_log()[:limit],
    })


@app.route("/ai/agent_run", methods=["POST"])
def ai_agent_run():
    """Manually trigger a background agent task."""
    from modules.agent_runner import trigger_task
    data = request.get_json(silent=True) or {}
    task = (data.get("task") or "").strip()
    if not task:
        return jsonify({"error": "task is required"}), 400
    return jsonify(trigger_task(task))


@app.route("/ai/agent_pause", methods=["POST"])
def ai_agent_pause():
    """Pause autonomous background processing."""
    from modules.agent_runner import pause_agent
    pause_agent()
    return jsonify({"ok": True, "paused": True})


@app.route("/ai/agent_resume", methods=["POST"])
def ai_agent_resume():
    """Resume autonomous background processing."""
    from modules.agent_runner import resume_agent
    resume_agent()
    return jsonify({"ok": True, "paused": False})


# ---------------------------------------------------------------------------
# Approval queue routes
# ---------------------------------------------------------------------------

@app.route("/ai/approvals")
def ai_approvals_list():
    """Return pending approval requests (or all if ?all=1)."""
    from modules.approval_queue import get_pending, get_all, get_pending_count
    show_all = request.args.get("all") == "1"
    limit    = min(int(request.args.get("limit", 50)), 200)
    entries  = get_all(limit) if show_all else get_pending()
    return jsonify({
        "pending_count": get_pending_count(),
        "entries":       entries,
    })


@app.route("/ai/approvals/<entry_id>/approve", methods=["POST"])
def ai_approval_approve(entry_id: str):
    """Approve a queued action and execute it immediately."""
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
    limit = int(request.args.get("limit", 50))
    return jsonify({"traps": get_recent_traps(limit)})


@app.route("/monitoring/netflow")
def monitoring_netflow():
    from modules.netflow_collector import get_flow_stats, get_recent_flows
    include_flows = int(request.args.get("flows", 0))
    stats = get_flow_stats()
    result = {"stats": stats}
    if include_flows:
        result["recent_flows"] = get_recent_flows(include_flows)
    return jsonify(result)


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
    from modules.event_monitor import start_monitor as _start_event_monitor
    _start_event_monitor()

    from modules.agent_runner import start_agent_loop as _start_agent_loop
    _start_agent_loop(
        devices_loader   = _load_current_devices,
        status_cache     = device_status_cache,
        connections_pool = {},
        pool_lock        = threading.Lock(),
    )

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
