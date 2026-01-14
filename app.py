# Dustin Marchak
# CSCI 5020 - Final Project
# Device Manager web application

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
import time # for sleep
import webbrowser # to open browser on start
import ipaddress # for IP address validation
import logging # for application logging
from logging.handlers import RotatingFileHandler # for log file rotation
from io import BytesIO # for in-memory file downloads

# Import Project modules
from modules.device import load_saved_devices, save_device, write_devices_csv, get_device_context
import modules.device as device_module
from modules.config import (
    DEVICES_FILE,
    PING_INTERVAL,
    SECRET_KEY_FILE,
    TFTP_ROOT,
    TFTP_SERVER_IP,
    FILE_TRANSFER_METHOD,
    FLASK_HOST,
    FLASK_PORT,
    FLASK_DEBUG
)
from modules.connection import ping_worker, get_persistent_connection, close_persistent_connection, with_temp_connection
from modules.terminal import ensure_terminal_session, start_terminal_reader
from modules.quick_actions import load_quick_actions, save_quick_actions
from modules.utils import make_device_filename
from modules.commands import run_device_command

# Device status cache and ping worker setup
#
# `device_status_cache` is a lightweight in-memory mapping kept up to
# date by the background `ping_worker` thread. The web handlers read
# this cache to show online/offline state without performing blocking
# network I/O on each web request. `ping_worker` monitors the
# `DEVICES_FILE` and re-reads the inventory when it changes.
device_status_cache = {}
ping_worker(device_status_cache, filename=DEVICES_FILE, interval=PING_INTERVAL)

# Flask application and Socket.IO initialization
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

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------
if not app.debug:
    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.mkdir('logs')

    # Configure rotating file handler (10MB per file, keep 10 backups)
    file_handler = RotatingFileHandler(
        'logs/device_manager.log',
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
    devices = load_saved_devices(DEVICES_FILE)
    for d in devices:
        d["online"] = device_status_cache.get(d["ip"], False)
    return render_template("index.html", devices=devices)


# Add device
@app.route("/add", methods=["POST"])
def add_device():
    # Add a new device to inventory after verifying connection
    ip = request.form["ip"].strip()
    username = request.form["username"].strip()
    password = request.form["password"]
    secret = request.form["secret"]

    app.logger.info(f'Attempting to add device: {ip} with username: {username}')

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

    # Check for duplicate IP
    devices = load_saved_devices(DEVICES_FILE)
    if any(d["ip"] == ip for d in devices):
        app.logger.warning(f'Duplicate device IP detected: {ip}')
        flash(f"Device with IP {ip} already exists", "warning")
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
            DEVICES_FILE,
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
    devices = load_saved_devices(DEVICES_FILE)
    dev = next((d for d in devices if d["ip"] == ip), None)
    if not dev:
        flash("Device not found", "danger")
        return redirect(url_for("index"))

    try:
        filesystems, file_list, selected_fs = get_device_context(dev)
        return render_template(
            "device.html",
            device=dev,
            filesystems=filesystems,
            files=file_list,
            selected_fs=selected_fs,
            quick_actions=load_quick_actions().get("global", []),
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

    devices = load_saved_devices(DEVICES_FILE)
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
        )
    except Exception as e:
        flash(
            f"Failed to run command on {dev.get('hostname', ip)} ({dev['ip']}): {e}",
            "danger",
        )
        return redirect(url_for("index"))


# Run script (temporary connection for each command or config mode block)
@app.route("/run_script/<ip>", methods=["POST"])
def run_script(ip):
    # Run a multi-line script on the device
    script = request.form.get("script")
    mode = request.form.get("mode")
    filesystem = request.form.get("filesystem")

    devices = load_saved_devices(DEVICES_FILE)
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

    devices = load_saved_devices(DEVICES_FILE)
    dev = next((d for d in devices if d["ip"] == ip), None)
    if not dev:
        flash("Device not found", "danger")
        return redirect(url_for("index"))

    file = request.files.get("file")
    filesystem = request.form.get("filesystem")

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
                output += conn.send_command_timing(TFTP_SERVER_IP)
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

    devices = load_saved_devices(DEVICES_FILE)
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
        )
    except Exception as e:
        flash(f"Delete failed: {e}", "danger")
        return redirect(url_for("manage_device", ip=ip))


# Refresh files (temporary connection via get_device_context)
@app.route("/device/<ip>/refresh_files", methods=["POST"])
def refresh_files(ip):
    # Refresh the file list for the device filesystem
    filesystem = request.form.get("filesystem")

    devices = load_saved_devices(DEVICES_FILE)
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
        )
    except Exception as e:
        flash(f"Failed to refresh files: {e}", "danger")
        return redirect(url_for("manage_device", ip=ip))


# Delete device (CSV)
@app.route("/device/<ip>/delete", methods=["POST"])
def delete_device(ip):
    app.logger.info(f'Attempting to delete device: {ip}')
    try:
        # Delete from CSV using the device module helper
        device_module.delete_device(ip, DEVICES_FILE)
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

    devices = load_saved_devices(DEVICES_FILE)
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
        )
    except Exception as e:
        flash(f"Error saving config: {e}", "danger")
        return redirect(url_for("manage_device", ip=ip))


# Reorder devices (CSV rewrite)
@app.route("/reorder", methods=["POST"])
def reorder_devices():
    # Reorder devices in Devices.csv based on new order
    new_order = request.get_json()
    if not new_order:
        return {"status": "error", "message": "No order received"}, 400

    devices = load_saved_devices(DEVICES_FILE)
    ip_to_device = {d["ip"]: d for d in devices}
    reordered = [ip_to_device[ip] for ip in new_order if ip in ip_to_device]

    write_devices_csv(reordered, DEVICES_FILE)
    return {"status": "success"}


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
    devices = load_saved_devices(DEVICES_FILE)
    dev = next((d for d in devices if d["ip"] == ip), None)
    if dev:
        try:
            conn = get_persistent_connection(dev, connections, lock)
            conn.find_prompt()  # lightweight check
            status = "connected"
        except Exception:
            status = "disconnected"
    return jsonify({"status": status})

# Run the Flask app with Socket.IO
if __name__ == "__main__":
    webbrowser.open(f"http://{FLASK_HOST}:{FLASK_PORT}")
    socketio.run(app, host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG, use_reloader=False)
