# [Author]
# Agentic Network Management
# Device Manager web application

# Load .env file if present (sets ANTHROPIC_API_KEY etc. without needing system env vars).
# Use an absolute path (matching where /settings writes it) instead of relying on
# load_dotenv()'s cwd-based search — under systemd, the process's working directory
# isn't necessarily the repo root, so the auto-search can silently miss the file.
try:
    import os as _os
    from dotenv import load_dotenv
    load_dotenv(_os.path.join(_os.path.dirname(__file__), ".env"))
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
    AUTO_OPEN_BROWSER,
    ensure_tftp_root,
    set_user_setting,
    get_user_setting,
    load_user_settings,
    save_user_settings,
)
from modules.connection import session_reaper, get_persistent_connection, close_persistent_connection, with_temp_connection, get_device_send_lock
from modules import route_gates
from modules.identity import request_actor
from modules.quick_actions import load_quick_actions, save_quick_actions
from modules.utils import make_device_filename
from modules.commands import run_device_command
from modules.backups import (
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
# `device_status_cache` is the reachability reader's `STATUS` (C92): address
# -> answering, judged over consecutive probes of every list's devices, never
# one probe. The web handlers and every action that asks "is it online" read
# it without network I/O; the reader keeps it current.
from modules.readers.reachability import STATUS as device_status_cache  # noqa: E402

def _get_current_devices_file():
    """The current device list's file (the reader probes every list)."""
    _, filepath = get_current_device_list()
    return filepath

# The ping worker is started by `_start_background_daemons()`, when the
# program RUNS, never by importing this module (see below).

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

# Load or generate the persistent session key: owner-only AT CREATION (it signs every
# session; measured 2026-09-25, the live file was 0664) and created ONCE across processes
# (CONCURRENCY_AUDIT R30: two workers starting on a fresh install each wrote their own).
from modules.config import read_or_create_key
app.secret_key = read_or_create_key(SECRET_KEY_FILE, lambda: os.urandom(24))


# manage_session=False: none of this app's SocketIO handlers use flask.session
# (the break-glass terminal, removed in R39, kept its own state), and on some
# Flask/Flask-SocketIO version combos manage_session=True's internal session
# copy hits `AttributeError: property 'session' of 'RequestContext' object
# has no setter`, crashing every socket event before the handler even runs.
socketio = SocketIO(
    app, async_mode="threading", cors_allowed_origins="*", manage_session=False
)

# Background jobs announce what they changed over this socket (C58,
# modules/invalidation.announce). Handing over the emit starts nothing.
from modules import invalidation as _invalidation  # noqa: E402
_invalidation.set_emitter(lambda event, msg: socketio.emit(event, msg))

# ---------------------------------------------------------------------------
# Cache policy. Stage 7 6c, measured 2026-09-24.
# ---------------------------------------------------------------------------
# The Baselines panel drew a bare "9 device(s)" while /golden/baselines
# returned `partial: true`: Cloudflare was serving stale HTML while the JSON
# came through fresh, and a browser hard-reload does NOT bypass the edge. It
# cost an hour and a wrong diagnosis on a page somebody knew well, and the
# state it produces -- "the page is wrong and the API is right" -- reads as
# a code defect to everyone who meets it.
#
# THE HEADER RATHER THAN A CACHE RULE AT THE ZONE. A purge-per-deploy is a
# human step in an external system, invisible when skipped, and what it
# protects against is silent. This project refuses that shape everywhere
# else.
#
# `no-cache`, NOT `no-store`: no-store forbids keeping a copy at all, so
# every navigation re-downloads. no-cache keeps the copy and requires
# revalidation -- which is only cheap with a validator, so an ETag is added
# below. Measured before it was: the rendered page carried no ETag, no
# Last-Modified and no Cache-Control at all, so a bare `no-cache` would have
# been a full re-download every time.
_STATIC_MAX_AGE = 60 * 60 * 24 * 30           # 30 days


@app.url_defaults
def _static_cache_bust(endpoint, values):
    """Put the file's mtime in every `url_for('static', ...)`.

    **A long cache lifetime without versioned URLs is the HTML problem
    again, one layer down**: a deploy would change the file and every
    browser would keep the old one for a month. With the mtime in the
    query, a changed file is a different URL and the old one is simply
    never requested. Nothing to purge, and nothing to remember.

    Two files in `base.html` reference `/static/...` literally rather than
    through `url_for`, so they never get a version and fall to the
    `no-cache` branch above -- correct, and visible rather than assumed.
    """
    if endpoint != "static" or "filename" not in values:
        return
    try:
        full = os.path.join(app.static_folder, values["filename"])
        values["v"] = int(os.stat(full).st_mtime)
    except OSError:
        pass                                   # a missing file is the
                                               # route's problem, not ours


@app.after_request
def _cache_policy(resp):
    """Uncacheable HTML, long-lived static assets.

    **The two halves are opposites and both are required.** Stage 7 0b moved
    275 KB of script out of the HTML precisely so they could differ: the
    page carries live inventory, drift state and identity and is never safe
    to reuse, while the vendored libraries and the extracted script change
    only on deploy. A blanket no-cache over `/static/` would undo 0b in the
    same commit that depends on it.
    """
    try:
        path = request.path or ""
        if path.startswith("/static/"):
            # ASSIGNED, not `setdefault`. Flask's static handler already
            # sets `Cache-Control: no-cache`, so a setdefault did nothing
            # and measured as no-cache on a 27 KB extracted script -- which
            # would have undone 0b in the commit that depends on it. The
            # long lifetime is only safe because `_static_cache_bust()`
            # below puts the file's mtime in the URL, so a deploy changes
            # the URL rather than needing anybody to purge anything.
            if "v" in request.args:
                resp.headers["Cache-Control"] = (
                    f"public, max-age={_STATIC_MAX_AGE}, immutable")
            else:
                # Unversioned: revalidate. Flask's ETag still makes an
                # unchanged file a 304 and zero bytes, so this is safe
                # rather than expensive -- and a URL nobody versioned must
                # never be cached for a month.
                resp.headers["Cache-Control"] = "no-cache"
            return resp

        if resp.mimetype == "text/html":
            # `no-transform` (C389): an intermediary must not change the
            # body. A proxy injected scripts into the pages (an email
            # decoder and an analytics beacon), so what was served was not
            # what the tests see. The page also checks itself
            # (nmas_v2.js, `injectedScripts`), whatever the proxy does.
            resp.headers["Cache-Control"] = "no-cache, must-revalidate, no-transform"
            # The validator that makes revalidation a 304 instead of a
            # re-download. Only for complete, non-streamed responses.
            if not resp.direct_passthrough and resp.status_code == 200:
                resp.add_etag()
                return resp.make_conditional(request)

        elif resp.mimetype == "application/json":
            # MEASURED before deciding: JSON responses carried no
            # Cache-Control, no ETag and no Last-Modified, and the edge did
            # not cache them -- which is why the API stayed fresh while the
            # page went stale. **That freshness was somebody else's
            # default, not our policy**, and the whole argument for putting
            # this in the app rather than in a Cache Rule is not to depend
            # on one. So it is stated.
            #
            # `no-store` rather than `no-cache`: these are per-request reads
            # of live state, several of them identity-scoped, and none is
            # ever reusable -- so there is nothing for a validator to save
            # and a copy retained by an intermediary is a small exposure
            # rather than a small saving. Harmless to the client: a `fetch`
            # of an uncacheable response behaves exactly as it did when the
            # header was absent.
            resp.headers.setdefault("Cache-Control", "no-store")
    except Exception as exc:                  # noqa: BLE001
        # A cache header is not worth failing a response over, and a
        # silently unheadered page is the state this exists to prevent --
        # so it is logged rather than swallowed.
        app.logger.warning("cache policy not applied to %s: %s",
                           getattr(request, "path", "?"), exc)
    return resp


# New routes live in Flask blueprints under routes/ rather than growing this
# file further. Registered here, immediately after the app exists.
# The ping cache, for a blueprint that redraws the device list (Stage 7.0).
# A registration, not a route: importing `app` from a blueprint would load a
# second copy when this file runs as __main__.
app.extensions["nmas_device_status"] = device_status_cache
# A getter, not the value: save_tftp_server rebinds the global at run time.
app.extensions["nmas_tftp_server"] = lambda: TFTP_SERVER_IP
try:
    from routes import register_blueprints
    register_blueprints(app)
except Exception as _bp_exc:                  # noqa: BLE001
    app.logger.error("Could not register blueprints: %s", _bp_exc)

# Post-commit hooks for the NSoT repo (git push, S3 archive). They run on a
# background thread and never block a commit.
try:
    from modules.nsot.archive import register_default_hooks
    register_default_hooks()
except Exception as _hook_exc:                # noqa: BLE001
    app.logger.error("Could not register NSoT post-commit hooks: %s", _hook_exc)

# Bring user_settings.json up to the current schema and encrypt any secret that
# an older build wrote in plaintext (the NetBox token).
try:
    from modules.settings_schema import migrate as _migrate_settings
    _migrate_settings()
except Exception as _mig_exc:                 # noqa: BLE001
    app.logger.error("Settings migration failed: %s", _mig_exc)

# Template secrets predating list scoping are keyed <host>:<ref> in one
# installation-wide store, so two lists holding a device of the same name
# shared a key and the second silently replaced the first. Every such key
# belongs to whichever list was the only one, which is unambiguous because
# there has only ever been one. Idempotent; re-running skips scoped keys.
try:
    from modules.config import get_current_list_name as _cur_list
    from modules.credentials import migrate_template_secrets_to_list_scope
    _sec_mig = migrate_template_secrets_to_list_scope(_cur_list(), dry_run=False)
    if _sec_mig.get("count"):
        app.logger.warning("Migrated %d template secret(s) into list scope",
                           _sec_mig["count"])
except Exception as _sec_exc:                 # noqa: BLE001
    app.logger.error("Template-secret scope migration failed: %s", _sec_exc)

# Background daemons are started after all routes/functions are defined.
# See _start_background_daemons() called at the bottom of this file.

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------
if not app.debug:
    # Create logs directory if it doesn't exist (use BASE_DIR for frozen executable)
    logs_dir = os.path.join(BASE_DIR, 'logs')
    # exist_ok, never check-then-create (C119): two processes importing the
    # app at once (the suite's parallel workers on a fresh checkout, which has
    # no logs/) both passed the check and the second mkdir raised.
    os.makedirs(logs_dir, exist_ok=True)

    # Configure rotating file handler (10MB per file, keep 10 backups)
    file_handler = RotatingFileHandler(
        os.path.join(logs_dir, 'device_manager.log'),
        maxBytes=10240000,
        backupCount=10
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s %(name)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    # Attach at the ROOT logger, not just app.logger. Every module uses its own
    # logging.getLogger(__name__) (modules.config_git, modules.ai_assistant, ...)
    # which only propagates up to root, not to app.logger specifically -- without
    # this, every "check server logs" error message pointed at a file that never
    # actually contained the module's log.error() call. app.logger still
    # propagates to root by default, so this also keeps capturing its messages
    # without needing a second handler on it directly.
    logging.getLogger().addHandler(file_handler)
    logging.getLogger().setLevel(logging.INFO)

    app.logger.setLevel(logging.INFO)
    app.logger.info('Device Manager startup')

# The third place secrets leave this process, after the model API and the HTTP
# API — and the easiest to forget, because nobody logs a password on purpose.
# It arrives inside a config dump, an exception message, a Netmiko echo, or a
# diff.
#
# EVERY handler, not just the file one. A filter on the root *logger* would not
# do: a record from a child logger reaches ancestor handlers without ancestor
# logger filters being consulted. And the file handler exists only when
# app.debug is false — a StreamHandler to stdout is the systemd journal, which
# is where an operator greps first.
#
# guard_new_handlers() covers handlers attached after this point, because
# coverage established once at startup decays.
try:
    from modules.redact import guard_new_handlers, redact_all_handlers
    guard_new_handlers()
    _redacted = redact_all_handlers()
    logging.getLogger(__name__).info(
        "redact: log redaction installed on %d handler(s)", _redacted)
except Exception as _red_exc:                 # noqa: BLE001
    logging.getLogger(__name__).error(
        "redact: COULD NOT install log redaction (%s) — records may be written "
        "unredacted", _red_exc)

# ---------------------------------------------------------------------------
# Flask Error Handlers
# ---------------------------------------------------------------------------

@app.route("/favicon.ico")
def favicon():
    """Return empty response for favicon to avoid 404 warnings."""
    return "", 204

def _client_wants_html() -> bool:
    """Is this a browser NAVIGATION, or a fetch() from the page?

    Decided on the literal `Accept` header rather than on werkzeug's
    `accept_mimetypes`, which cannot tell `*/*` from an explicit preference:
    for `Accept: */*` both `accept_html` and `accept_json` are true with equal
    quality, so any comparison between them picks a winner by tie-break. A
    browser navigating sends `text/html,...`; `fetch()` with no Accept header
    sends `*/*`. The literal test separates them and nothing else does.
    """
    return "text/html" in (request.headers.get("Accept", "") or "")


def _error_response(error, status: int, message):
    """Redirect a navigation; answer a fetch() with JSON and a real status.

    **An unhandled exception must never present as a successful redirect.**
    These handlers redirected everything to the index, so every JSON endpoint
    in the app answered a crash with `302 /` — the fetch followed it, got a
    page of HTML, and the caller either failed to parse it or swallowed it in
    a `catch`. Measured on `POST /drift/settings`: a `TypeError` reached the
    operator as a toggle that flicked back to its previous position, with
    nothing on screen and the real error in the log.

    That is the failure mode this project treats as the dominant one, wired
    in at the framework level and applying to every route at once.

    The message is redacted: it can quote a config line or an exception
    carrying a credential, and unlike the log this goes out over HTTP.
    """
    from modules import redact
    from modules.utils import error_text

    detail = error_text(error)
    try:
        detail = redact.redact_text(detail)
    except Exception:                          # noqa: BLE001
        detail = error.__class__.__name__      # never the raw text on failure
    if message is None:
        # WHAT was being done and WHAT failed, in the sentence the screen
        # draws (C154). "An unexpected error occurred. Please check the logs"
        # named neither, and the log is not something the interface can open:
        # the reason was carried as `detail` and drawn by nothing.
        message = (f"{request.method} {request.path} failed with an unexpected "
                   f"error: {detail}")
    if _client_wants_html():
        if request.path.startswith("/v2/"):
            from routes.v2_failure import answer
            return answer(message, status)
        flash(message, 'warning' if status == 404 else 'danger')
        return redirect(url_for('index'))
    return jsonify({"ok": False, "error": message, "detail": detail,
                    "status": status}), status


@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 Not Found errors."""
    app.logger.warning(f'Page not found: {request.url}')
    return _error_response(error, 404, 'Page not found')

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 Internal Server errors."""
    app.logger.error(f'Server Error: {error}', exc_info=True)
    return _error_response(error, 500, None)

@app.errorhandler(Exception)
def handle_exception(error):
    """Handle all uncaught exceptions.

    An HTTP error is NOT an unexpected exception, and keeps its own status
    (register C29, 2026-09-26). Only 404 had a handler, so every 405, 400,
    413 and 415 reached this one and went out as a 500 "An unexpected error
    occurred. Please check the logs", with an ERROR line in the log a person
    reads. A request with the wrong method read as a server crash. Found when
    `/run_command` became POST-only (B16) and a GET to it answered 500.
    """
    from werkzeug.exceptions import HTTPException

    if isinstance(error, HTTPException):
        app.logger.warning("HTTP %s for %s %s", error.code, request.method,
                           request.path)
        return _error_response(error, error.code or 500,
                               error.description or error.name)
    app.logger.error(f'Unhandled Exception: {error}', exc_info=True)
    return _error_response(error, 500, None)

# Reintroduce persistent connections container for status checks
# QUICK_ACTIONS_FILE provided by modules.config

connections = {}  # ip -> Netmiko connection (status-only)
lock = threading.Lock()
_device_lock = get_device_send_lock  # serialises SSH commands per device


# The break-glass terminal's socket handlers were removed (R39, the operator,
# 2026-10-05), after the console drill proved the emergency path without it
# (docs/CONSOLE_DRILL.md). Its past sessions stay readable in its audit log.


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
@app.route("/run_command/<ip>", methods=["POST"])
def run_command(ip):
    # Run a command on the device and show output.
    #
    # POST, and gated `confirm` (register B16, 2026-09-26). It was a GET: any
    # exec-mode command (reload, delete, copy, clear) from a URL, with no
    # identity check, because the gate table covers mutating METHODS, and a
    # link an operator logged in to Access followed would have run it. The
    # Access cookie is not sent on a cross-site POST, so a link cannot.
    command = request.form.get("command")
    filesystem = request.form.get("filesystem")

    _, current_list_file = get_current_device_list()
    devices = load_saved_devices(current_list_file)
    dev = next((d for d in devices if d["ip"] == ip), None)
    if not dev:
        flash("Device not found", "danger")
        return redirect(url_for("index"))

    if not command:
        flash("No command provided.", "warning")
        return redirect(url_for("manage_device", ip=ip))

    # READS ONLY (C570, the operator, 2026-10-08): this route ran ANY exec command (reload,
    # write erase, delete, copy), holding the device first so the session guard let it
    # through. A change to a device is an operation with a preview, a confirm and a record,
    # never free text here: anything the read-only allowlist refuses is refused, naming why,
    # before any device is asked.
    from modules.readonly_commands import refusal as _read_refusal
    _why = _read_refusal(command)
    if _why:
        app.logger.warning("run_command: refused for %s: %s", dev["hostname"], _why)
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"ok": False, "error": f"Not run on {dev['hostname']}: {_why}"}), 400
        flash(f"Not run on {dev['hostname']}: {_why}", "danger")
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
    # C570: the name is spliced into the copy's prompts and joined to the TFTP root, so it is
    # one token (no path: "../x" wrote outside the root); the filesystem and server likewise.
    from modules.cli_tokens import first_refusal as _token_refusal
    _why = _token_refusal(filename=(file.filename, "filename"),
                          filesystem=(filesystem, "filesystem"),
                          tftp_server=(tftp_server, "server"))
    if _why:
        flash(_why, "danger")
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

                from modules.nsot import device_ops as _device_ops
                with _device_ops.hold_device(dev, "file", detail="upload (scp)"):
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

            # Save to local TFTP root (configured in Settings; created on first use)
            local_path = os.path.join(ensure_tftp_root(), file.filename)
            file.save(local_path)

            def execute_tftp(conn):
                # IOS expects just the destination filesystem here; filenames are prompted interactively
                output = conn.send_command_timing(f"copy tftp: {filesystem}")
                output += conn.send_command_timing(tftp_server)
                output += conn.send_command_timing(file.filename)
                output += conn.send_command_timing(file.filename)
                output += conn.send_command_timing("\n")
                return output

            from modules.nsot import device_ops as _device_ops
            with _device_ops.hold_device(dev, "file", detail="upload (tftp)"):
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
    # C570: each field is spliced into the command, so each is one token of its shape.
    from modules.cli_tokens import first_refusal as _token_refusal
    _why = _token_refusal(filename=(filename, "filename"), filesystem=(filesystem, "filesystem"))
    if _why:
        flash(_why, "danger")
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

        from modules.nsot import device_ops as _device_ops
        with _device_ops.hold_device(dev, "file", detail="delete"):
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
    # C570: each field is spliced into the copy and its prompts, so each is one token.
    from modules.cli_tokens import first_refusal as _token_refusal
    _why = _token_refusal(filename=(filename, "filename"), filesystem=(filesystem, "filesystem"),
                          tftp_server=(tftp_server, "server"))
    if _why:
        flash(_why, "danger")
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

        from modules.nsot import device_ops as _device_ops
        with _device_ops.hold_device(dev, "file", detail="download"):
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
# Device status (from cache)
@app.route("/status/<ip>")
def device_status(ip):
    # Return online status for a device
    online = device_status_cache.get(ip, False)
    return {"ip": ip, "online": online}


# Reorder devices (CSV rewrite)
@app.route("/reorder", methods=["POST"])
def reorder_devices():
    # Reorder devices in current device list based on new order
    new_order = request.get_json()
    if not new_order:
        return {"status": "error", "message": "No order received"}, 400

    from modules.device import devices_csv_lock

    _, current_list_file = get_current_device_list()
    with devices_csv_lock(current_list_file):
        devices = load_saved_devices(current_list_file)
        ip_to_device = {d["ip"]: d for d in devices}
        reordered = [ip_to_device[ip] for ip in new_order if ip in ip_to_device]
        # A device the order does not name is KEPT, at the end (C160). The
        # order is the browser's view from when the page loaded; a device
        # added since (onboarding's promotion, another tab) was DROPPED, and
        # with it the only stored copy of its credential.
        named = set(new_order)
        reordered += [d for d in devices if d["ip"] not in named]
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
    # Optional body: {"acknowledge_credential_dependents": true} (step 0). The
    # NetBox cascade and its `remove_from_netbox` flag are gone (C155, step 2).
    data = request.get_json(silent=True) or {}

    # ── 0. Warn if NetBox lists inherit credentials from this one ──────────
    # Amendment 2: credentials are inherited from ONE designated list, so
    # deleting it strands every NetBox list pointing at it. Refuse unless the
    # caller acknowledges, and point at the "copy into overrides" escape hatch.
    try:
        from modules.inventory.source_config import lists_depending_on
        dependents = lists_depending_on(list_name)
        if dependents and not data.get("acknowledge_credential_dependents"):
            return jsonify({
                "status": "error",
                "needs_acknowledgement": True,
                "dependents": dependents,
                "message": (
                    f"{len(dependents)} NetBox-sourced list(s) inherit credentials from "
                    f"'{list_name}': {', '.join(dependents)}. Deleting it will leave those "
                    "devices without credentials. Use 'Copy inherited credentials into "
                    "device overrides' on each list first, or confirm to delete anyway."
                ),
            }), 409
        if dependents:
            cleanup_log.append(
                f"Credential dependents acknowledged: {', '.join(dependents)}")
    except Exception as exc:
        app.logger.warning("list delete: dependent check failed: %s", exc)

    # ── 2. NetBox: NEVER touched from here (C155, the operator's decision) ──
    # This branch deleted NMAS-created objects with no preview and no
    # confirmation when a setting was on (the one-shot token is consumed by
    # the NetBox tab's routes, not at the write), and its "forget" branch
    # dropped the record while the objects stayed, leaving them tagged but
    # unrecorded, out of Remove's reach for good (C59's class). Removal has
    # ONE home: the NetBox tab's previewed, confirmed Remove. So a list that
    # still owns recorded objects is refused, naming them; nothing here writes
    # to NetBox, and the record is dropped only when it holds nothing.
    from modules import netbox_guard as _nbg
    held, why = _nbg.recorded_objects(list_name)
    if why:
        return jsonify({"status": "error", "message": (
            f"'{list_name}' was not deleted: {why}, so whether it still owns "
            "NetBox objects is unknown. Nothing was changed.")}), 409
    if held:
        named = ", ".join(f"{ep}/{oid} {name}".strip() for ep, oid, name in held[:8])
        more = f" and {len(held) - 8} more" if len(held) > 8 else ""
        return jsonify({"status": "error", "held": [
            {"endpoint": ep, "id": oid, "name": name} for ep, oid, name in held],
            "message": (
                f"'{list_name}' was not deleted: Mercury's record says it created "
                f"{len(held)} NetBox object(s) for this list ({named}{more}). Deleting a "
                "list never deletes NetBox objects, and forgetting them would leave them "
                "out of Remove's reach. Remove them first from the NetBox tab (previewed "
                "and confirmed), then delete the list. Nothing was changed.")}), 409
    _nbg.forget_created(list_name)          # an empty entry, if any
    cleanup_log.append("NetBox: nothing recorded for this list; NetBox not touched")

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
    return jsonify(_settings_payload())


def _settings_payload() -> dict:
    """What the Settings form loads, and what its save is compared against (R17)."""
    from modules.netbox_client import get_netbox_config as _get_nb_cfg
    nbcfg = _get_nb_cfg()
    # SECRETS ARE WRITE-ONLY: a flag, never the value (register B11, P.3
    # step 6). This returned the Anthropic key and both Jenkins secrets in
    # cleartext, ungated, to every opening of the Settings modal since
    # e729267 (2026-04-12). The NetBox token beside them was always a flag.
    from modules.settings_schema import DEFAULTS as _SETTING_DEFAULTS
    payload = {
        "anthropic_api_key_set": bool(os.environ.get("ANTHROPIC_API_KEY", "")),
        "tftp_server_ip":    TFTP_SERVER_IP,
        # NetBox — token never returned in cleartext; UI uses token_set flag.
        "netbox_url":         nbcfg.get("url", ""),
        "netbox_token_set":   bool(nbcfg.get("token")),
        "netbox_verify_tls":  bool(nbcfg.get("verify_tls", True)),
        "netbox_auth_scheme": nbcfg.get("auth_scheme", "Bearer"),
        "netbox_allow_writes": bool(nbcfg.get("allow_writes", False)),
        "ai_enabled":              _ai_enabled(),
        "background_agent_enabled": bool(load_user_settings().get(
            "background_agent_enabled", _SETTING_DEFAULTS["background_agent_enabled"])),
    }
    payload.update(_load_workflow_flags())
    return payload


@app.route("/settings", methods=["POST"])
def save_settings():
    """Save the settings the person CHANGED in the Settings modal (CONCURRENCY_AUDIT R17).

    The form sends only its changed fields, with the values it loaded (`loaded`). Under the
    settings lock, a changed field whose stored value moved since is refused, naming both
    values, and the rest are saved: a stale tab can no longer revert another person's decision
    (it turned NetBox writes back on by saving an unrelated field)."""
    from modules.config import settings_lock
    from modules.settings_schema import moved_since, moved_words

    data = request.get_json(silent=True) or {}
    loaded = data.pop("loaded", None)
    if not isinstance(loaded, dict):
        return jsonify({"status": "error", "errors": [
            "Not saved: this form did not say what it loaded, so a field nobody changed could "
            "revert another person's decision. Reopen Settings and save again."]}), 400
    with settings_lock():
        moved = moved_since(data, loaded, _settings_payload())
        for key in moved:
            data.pop(key)
        return _save_settings(data, moved_words(moved))


def _save_settings(data: dict, errors: list):
    global TFTP_SERVER_IP
    import modules.config as config_module


    # ── Anthropic API key ─────────────────────────────────────────────────
    api_key = data.get("anthropic_api_key", "").strip()
    if api_key:
        os.environ["ANTHROPIC_API_KEY"] = api_key
        # Persist to .env so it survives restarts
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        try:
            from modules.config import set_env_line

            set_env_line(env_path, "ANTHROPIC_API_KEY", api_key)
            # Reset cached Anthropic client so it picks up the new key
            import modules.ai_assistant as _ai_mod
            _ai_mod._anthropic_client = None
        except Exception as exc:
            errors.append(f"API key saved to env but .env write failed: {exc}")

    # ── Jenkins: REMOVED (P.4) ────────────────────────────────────────────
    # A page older than the server (the edge caches HTML) can still send these.
    # Refused by name rather than dropped, so the save says why nothing stored.
    if any(k in data for k in ("jenkins_url", "jenkins_user",
                               "jenkins_api_key", "jenkins_token")):
        errors.append("Jenkins was removed (P.4, docs/NSOT_CI.md); its settings "
                      "are no longer stored. Reload the page.")

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
    # Any NetBox field, alone: the form sends only what changed (R17), so the write switch
    # can arrive without the URL beside it.
    if any(k in data for k in ("netbox_url", "netbox_token", "netbox_verify_tls",
                               "netbox_allow_writes")):
        try:
            from modules.netbox_client import save_netbox_config, get_netbox_config
            existing = get_netbox_config()
            url   = (data.get("netbox_url",   existing.get("url",   "")) or "").strip()
            token = (data.get("netbox_token", "") or "").strip()
            # Blank token = keep the one on file (matches other secret fields).
            if not token:
                token = existing.get("token", "")
            verify_tls = data.get("netbox_verify_tls", existing.get("verify_tls", True))
            # Fail-closed write gate; absent from the payload means "leave as is".
            allow_writes = data.get("netbox_allow_writes")
            if url and not token:
                errors.append("NetBox token is required the first time you save a URL.")
            else:
                save_netbox_config(url, token, bool(verify_tls),
                                   allow_writes=None if allow_writes is None
                                   else bool(allow_writes))
        except Exception as exc:
            errors.append(f"NetBox settings failed: {exc}")

    # ── AI master switch + background agent + workflow flags ──────────────
    # Through `write_settings()`, the one path into user_settings.json: it
    # refuses a key the schema has never heard of rather than storing it. All
    # eight keys here were undeclared until 3.2a, which is how they came to be
    # written by a hand-built dict in this function and known to nothing else.
    try:
        from modules.settings_schema import write_settings

        updates = {}
        if "ai_enabled" in data:
            updates["ai_enabled"] = bool(data["ai_enabled"])
        if "background_agent_enabled" in data:
            updates["background_agent_enabled"] = bool(data["background_agent_enabled"])
        for flag in _WF_DEFAULTS:
            if flag in data:
                updates[flag] = bool(data[flag])

        if updates:
            result = write_settings(updates)
            if not result["ok"]:
                errors.append(result["error"])
            elif "background_agent_enabled" in updates:
                # Pause/resume the running thread immediately, and only once
                # the write succeeded — a thread resumed against a setting
                # that did not persist comes back paused on the next restart.
                try:
                    from modules.agent_runner import pause_agent, resume_agent
                    (resume_agent if updates["background_agent_enabled"]
                     else pause_agent)()
                except Exception as exc:       # noqa: BLE001
                    errors.append(f"Background agent state not applied: {exc}")
    except Exception as exc:
        errors.append(f"Workflow flags failed: {exc}")

    if errors:
        return jsonify({"status": "partial", "errors": errors}), 207
    return jsonify({"status": "ok"})




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
        pending_renames, rename_failures = [], []

        def get_hostname(conn):
            prompt = conn.find_prompt()
            return prompt.rstrip("#>").strip()

        # Every online device read AT ONCE (the concurrency rule, C199): a
        # session each, one after another, for no stated reason. The loop
        # below keeps the list's order and its per-device results.
        from modules.fanout import Failed, read_each
        online = [d for d in devices if device_status_cache.get(d.get("ip"), False)]
        prompts = dict(zip((d.get("ip") for d in online),
                           read_each(lambda d: with_temp_connection(d, get_hostname),
                                     online, name="refresh-hostnames")))

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
                # The current hostname, read above with the others.
                new_hostname = prompts.get(ip)
                if isinstance(new_hostname, Failed):
                    raise new_hostname.error

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
            # RE-READ under the lock and apply only the renames, by address
            # (C160). The list read above is minutes old by now (a session per
            # device), and writing it back erased whatever changed meanwhile: a
            # rotation's new credential, a promoted device, a reorder.
            from modules.device import devices_csv_lock
            renamed = {r["ip"]: r["new_hostname"] for r in results
                       if r["status"] == "updated"}
            with devices_csv_lock(current_list_file):
                fresh = load_saved_devices(current_list_file)
                for row in fresh:
                    if row.get("ip") in renamed:
                        row["hostname"] = renamed[row["ip"]]
                write_devices_csv(fresh, current_list_file)

            # Propagate hostname changes everywhere else the old name is stored.
            changed = [(r["ip"], r["old_hostname"], r["new_hostname"])
                       for r in results if r["status"] == "updated"]

            from modules.ai_assistant import (
                _load_variables, _save_variables,
                _nsot_repo_dir as _nsot_repo_dir_for_rename,
            )

            for ip, old_hn, new_hn in changed:
                # ── Golden config: a PENDING RENAME, never a re-save ────────
                # This re-saved the old golden under the new name through
                # _save_golden_config_file (recorded as ai-agent), bypassing the
                # designed rename, so the device's history broke at every rename
                # through here (git log --follow). Removed 2026-09-27 (C102, the
                # operator's decision). A rename has one home: the manifest
                # records it, and the next save, or "Sync device names to repo"
                # on the Git tab, commits the git mv ALONE.
                try:
                    from modules.nsot import manifest as _manifest
                    _repo_dir = _nsot_repo_dir_for_rename()
                    _ident, _entry = _manifest.find_by_ip(_repo_dir, ip)
                    if _ident:
                        _manifest.record_pending_rename(_repo_dir, _ident, new_hn)
                        pending_renames.append(f"{old_hn} -> {new_hn}")
                except Exception as exc:
                    app.logger.warning("Could not record the rename for %s: %s", ip, exc)
                    rename_failures.append(f"{old_hn}: {exc}")

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

                # NetBox's device name is NOT changed here (C465, 2026-10-05): this renamed it
                # by a direct PATCH, outside the write switch, the declared authority and the
                # modification record. The sync matches a device by serial before name, so the
                # next NetBox sync (gated and recorded) carries the new name.

        # What happened AND what is left to do (the standing rule): the golden
        # keeps its old name until the rename is committed on its own.
        message = f"Refreshed {updated_count} hostname(s), {failed_count} failed"
        if pending_renames:
            message = (f"{len(pending_renames)} golden rename(s) PENDING "
                       f"({', '.join(pending_renames)}): commit them with "
                       f"'Sync device names to repo' on the Git tab. " + message)
        if rename_failures:
            message = (f"{len(rename_failures)} rename(s) could not be recorded "
                       f"({'; '.join(rename_failures)}). " + message)
        if updated_count:
            message += " NetBox keeps the old name until its next sync (gated and recorded)."
        return jsonify({
            "status": "warning" if (rename_failures or failed_count) else "success",
            "message": message,
            "updated": updated_count,
            "failed": failed_count,
            "pending_renames": pending_renames,
            "rename_failures": rename_failures,
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
    """Download a backup file: MASKED unless a person reveals it (C56).

    It returned the stored backup raw, secrets included, to anyone who
    reached the URL. Now it is the golden path's pattern
    (`modules/outbound.py`): masked by default, and `?reveal=1` requires a
    person and is recorded. The page's Download button asks for the reveal,
    so a raw backup always has a person and a record behind it.
    """
    from modules import outbound

    try:
        content = get_backup_content(filename)

        if content is None:
            flash("Backup file not found", "danger")
            return redirect(url_for("index"))

        payload, status = outbound.config_text(
            request, content, what="backup", target=filename)
        if status != 200:
            return jsonify(payload), status
        content = payload["text"]

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

        # Masked on the way out (C77's sweep, 2026-09-27): the diff carries
        # both backups' secrets on its -/+ lines, and this returned them
        # verbatim. Reading a backup unmasked is the download's reveal.
        from modules.outbound import mask_payload
        return jsonify(mask_payload({
            "status": "success",
            "diff": diff,
            "file1": file1,
            "file2": file2
        }))

    except Exception as e:
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
    """Discover and return network topology as JSON.

    Query params: cdp=1/0, lldp=1/0 — which discovery protocols to query
    (default both). Each additional protocol adds a sequential SSH command
    per device, so letting the caller opt out keeps discovery fast — with
    enough devices, querying both can push total discovery time past a
    reverse proxy's request timeout.
    """
    try:
        _, current_list_file = get_current_device_list()
        devices = load_saved_devices(current_list_file)

        if not devices:
            return jsonify({"status": "success", "topology": {"nodes": [], "edges": []}})

        protocols = tuple(
            p for p in ("cdp", "lldp") if request.args.get(p, "1") != "0"
        )
        if not protocols:
            return jsonify({"status": "error", "message": "Select at least one of CDP or LLDP"}), 400

        topology = discover_topology(
            devices=devices,
            connection_factory=get_persistent_connection,
            connections_pool=connections,
            pool_lock=lock,
            status_cache=device_status_cache,
            max_workers=5,
            protocols=protocols,
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
            # run_device_command: one read, never re-sent, its reply checked (C272).
            # A bare send_command skips the NUL-prompt re-read and the shape check.
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
                # run_device_command: one read, never re-sent, its reply checked (C272).
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

        # Config mode is CUT (NSOT_PLAN P.3 step 2): a free-form command list
        # pushed to many devices with no plan, no hash and no rollback. It is
        # REFUSED by name rather than downgraded, so a stale page asking for it
        # learns why instead of silently running its commands in enable mode.
        # Configuration changes go through intent: edit, plan, confirm.
        if command_mode == "config":
            return jsonify({"status": "error", "message": (
                "Config mode was removed (P.3): a configuration change goes "
                "through intent (edit, plan, confirm), which previews exactly "
                "what is sent and can roll it back. Enable mode is still "
                "available and needs a person.")}), 400
        if command_mode != "enable":
            command_mode = "enable"
        # READS ONLY (C570): enable mode ran any command on every selected device, holding
        # each so the session guard let it through, and answered `reload`'s and `write
        # erase`'s prompts itself. Every `;`-separated command must pass the read-only
        # allowlist, or none runs on any device.
        from modules.readonly_commands import refusal_for as _reads_refusal
        _why = _reads_refusal([c.strip() for c in command.split(";") if c.strip()])
        if _why:
            return jsonify({"status": "error", "message": f"Not run on any device: {_why}"}), 400

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
        # Read here, in the request: the reload threads have no request.
        from modules import identity as _identity
        _actor = _identity.request_actor()
        _list_name, _ = get_current_device_list()
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
                from modules.nsot import device_ops as _device_ops
                with _device_ops.hold(_list_name, dev["hostname"], "reload", _actor,
                                      ip=dev["ip"]):
                    conn = get_persistent_connection(dev, connections, lock)
                    if conn is None:
                        raise RuntimeError("Could not open SSH connection")
                    # SEND, READ, DECIDE; success is the session DROPPING, which
                    # every other command would call a failure (C153).
                    from modules.device_reload import reload_device
                    # The tool's own reload is a PLANNED restart (the restarts reader
                    # tells planned from unplanned by this record), written before the
                    # reload is sent, so a fast boot is never read as unexpected.
                    from modules import restarts as _restarts
                    _t = _time.time()
                    _planned = _restarts.record_planned(
                        [dev["hostname"]], _t, _t + 1200, _actor,
                        "reloaded from the tool's Reload action", "bulk_reload",
                        list_name=_list_name)
                    if not _planned["ok"]:
                        # Not reloaded: a reload the tool cannot record as planned would
                        # read as an unexpected restart.
                        raise RuntimeError("not reloaded: the planned restart could not be "
                                           "recorded: " + _planned["error"])
                    with _device_lock(dev["ip"]):
                        outcome = reload_device(conn)
                try:
                    conn.disconnect()
                except Exception:
                    pass
                with lock:
                    connections.pop(dev["ip"], None)
                result["outcome"] = outcome["outcome"]
                result["dropped_after"] = outcome["dropped_after"]
                if outcome["ok"]:
                    result["status"] = "success"
                    result["output"] = outcome["detail"]
                    with _bm.lock:
                        _bm.active_operations[operation_id]["completed"] += 1
                else:
                    result["status"] = "failed"
                    result["error"] = outcome["detail"]
                    app.logger.warning("bulk_reload: %s (%s): %s", dev.get("hostname"),
                                       dev.get("ip"), outcome["detail"])
                    with _bm.lock:
                        _bm.active_operations[operation_id]["failed"] += 1
            except Exception as exc:
                from modules.utils import error_text as _error_text
                result["status"] = "failed"
                result["error"]  = _error_text(exc)
                # In the log as well as in memory: the in-memory result is read
                # only by a poll nobody may make (C152).
                app.logger.warning("bulk_reload: %s (%s) failed: %s", dev.get("hostname"),
                                   dev.get("ip"), result["error"])
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
            # Requested, not sent: no device has been contacted yet (C152).
            "message": f"Reload requested for {len(selected)} device(s); "
                       "each device's result follows",
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
        # C570: the name joins the TFTP root and the copy's prompts; one token each.
        from modules.cli_tokens import first_refusal as _token_refusal
        _why = _token_refusal(filename=(file.filename, "filename"), tftp_server=(tftp_server, "server"))
        if _why:
            return jsonify({"status": "error", "message": _why}), 400

        # Save file to TFTP root (created on first use)
        local_path = os.path.join(ensure_tftp_root(), file.filename)
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
        # C570: spliced into the copy and its prompts; one token each.
        from modules.cli_tokens import first_refusal as _token_refusal
        _why = _token_refusal(filename=(filename, "filename"), tftp_server=(tftp_server, "server"))
        if _why:
            return jsonify({"status": "error", "message": _why}), 400

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
        # C570: the server answers the copy's prompt; one token.
        from modules.cli_tokens import first_refusal as _token_refusal
        _why = _token_refusal(tftp_server=(tftp_server, "server"))
        if _why:
            return jsonify({"status": "error", "message": _why}), 400

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
        # C570: spliced into `delete flash:<name>`; one token.
        from modules.cli_tokens import first_refusal as _token_refusal
        _why = _token_refusal(filename=(filename, "filename"))
        if _why:
            return jsonify({"status": "error", "message": _why}), 400

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


@app.route("/ai/usage_summary")
def ai_usage_summary():
    """Aggregated spend/token totals from the persistent server-side usage
    log (data/ai_usage_log.jsonl) -- durable across page reloads and
    sessions, unlike the per-turn cost badge in the chat UI."""
    from modules.ai_usage_log import summarize
    days_param = request.args.get("days", "30")
    try:
        days = min(max(int(days_param), 1), 365)
    except ValueError:
        days = 30
    return jsonify(summarize(days=days))


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
            "device_type": d.get("device_type") or "unknown",
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
        # Playbook replay is CUT (P.3 step 2): it pushed stored command lists
        # over Netmiko in config mode, even with AI disabled. A request still
        # naming one (a cached page) is REFUSED, never passed to the model as
        # a message: the model still holds run_ansible_playbook until step 8.
        if data.get("run_playbook_id"):
            return jsonify({"error": (
                "Running a playbook was removed (P.3). A configuration change "
                "goes through intent: edit, plan, confirm.")}), 410
        # Block AI chat when disabled.
        if not _ai_enabled():
            return jsonify({"error": "AI is disabled. Re-enable it in Settings."}), 503

        if not message:
            return jsonify({"error": "Message is required"}), 400

        # Tell the background agent the user is active so it defers tasks
        try:
            from modules.agent_runner import notify_user_active
            notify_user_active()
        except Exception:
            pass

        import queue as _queue

        # Run the agent in a background thread and drain events via a queue.
        # This lets us send SSE keepalive pings while SSH tool calls block,
        # preventing browsers from closing the connection on long-running tasks.
        _SENTINEL = object()
        event_queue = _queue.Queue()
        # The person the turn acts for and their network, read HERE in the request: the read
        # tools ask the reads engine as "the agent, for <person>" (C548, R5).
        from modules import identity as _identity
        from modules.config import get_current_list_name as _current_list
        _chat_actor, _chat_list = _identity.request_actor(), _current_list()

        def _agent_thread():
            try:
                if not _ai_enabled():
                    event_queue.put({"type": "error",
                                     "content": "AI disabled — re-enable in Settings."})
                    event_queue.put(_SENTINEL)
                    return
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
                    actor=_chat_actor,
                    list_name=_chat_list,
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
    # Masked on the way out (register C56's sixth route, found 2026-09-27 by
    # test order). The cache holds tool output BEFORE the provider boundary
    # redacts it, and `get_running_config` is cached for 300 s, so for five
    # minutes after the agent read a device this served its config raw to any
    # GET, and the page copied it into localStorage.
    from modules.redact import known_secret_values, redact_text
    table = known_secret_values()
    snapshot = {}
    now = __import__("time").monotonic()
    for key, (result, expires_at) in list(_ai._tool_cache.items()):
        if expires_at > now:
            snapshot[key] = {
                "result":     redact_text(result[:2000], table),   # cap per-entry size
                "expires_in": int(expires_at - now),
            }
    return jsonify({"cache": snapshot, "count": len(snapshot)})


@app.route("/ai/history", methods=["GET"])
def ai_history():
    """Return the conversation history as simplified display items.

    Items are either {"role": "user"|"assistant", "text": ...} or
    {"role": "action", "id": ..., "label": ..., "content": ...} for a
    tool call — reconstructed from the tool_use block (assistant message)
    paired with its matching tool_result block (the following user
    message), same label logic as the live tool_start event.
    """
    session_id = request.args.get("session_id") or "main"
    raw = _ai.get_history(session_id)
    out = []
    pending_actions = {}  # tool_use_id -> action dict in `out`, mutated once its result arrives
    for msg in raw:
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue
        content = msg.get("content", "")
        if isinstance(content, str):
            text = content.strip()
            if text:
                out.append({"role": role, "text": text})
            continue
        if not isinstance(content, list):
            text = str(content).strip()
            if text:
                out.append({"role": role, "text": text})
            continue

        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                parts.append(block.get("text", ""))
            elif btype == "tool_use" and role == "assistant":
                text = "\n".join(parts).strip()
                if text:
                    out.append({"role": "assistant", "text": text})
                parts = []
                action = {
                    "role":    "action",
                    "id":      block.get("id"),
                    "label":   _ai._tool_label(block.get("name", ""), block.get("input") or {}),
                    "content": None,
                }
                out.append(action)
                if action["id"]:
                    pending_actions[action["id"]] = action
            elif btype == "tool_result" and role == "user":
                action = pending_actions.pop(block.get("tool_use_id"), None)
                if action is not None:
                    action["content"] = block.get("content", "")
        text = "\n".join(parts).strip()
        if text:
            out.append({"role": role, "text": text})
    # Masked on the way out (register C56): a tool result carries whatever
    # the tool read, `show running-config` included, and this returned it raw
    # to any caller. It is the text the model saw, since the provider
    # boundary redacts the same way.
    from modules.redact import redact_payload
    return jsonify(redact_payload(out))


@app.route("/ai/clear", methods=["POST"])
def ai_clear():
    """Clear the AI conversation history for a session."""
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id") or "default"
    _ai.clear_history(session_id)
    return jsonify({"status": "cleared"})


# `/ai/restart` and `/server/restart` are REMOVED (CONCURRENCY_AUDIT R5, 2026-10-02): each
# ended the process seconds after answering, checking no held device, running job or
# commit in progress, so one person could cut off another's deploy half-applied. Neither
# had a caller (measured 2026-09-27); the Update button restarts, gated on held devices.


# ---------------------------------------------------------------------------
# Drift check routes — pure Python, no AI required
# ---------------------------------------------------------------------------

@app.route("/drift/status")
def drift_status():
    """Return drift checker status and last-run result, for the network named."""
    from modules.drift_check import get_checker
    from modules.approval_queue import get_pending_count
    from modules.filestore import StoreUnreadable
    from modules.drift_check import network_for
    name = network_for(request)
    status = get_checker().status(name)
    try:
        status["pending_approvals"] = get_pending_count(name)
    except StoreUnreadable as exc:
        status["pending_approvals"] = None
        status["pending_approvals_error"] = str(exc)
    return jsonify(status)


@app.route("/drift/check", methods=["POST"])
def drift_check_trigger():
    """Trigger an immediate drift check of the network named.  Returns immediately; the
    check runs async."""
    from modules.drift_check import get_checker
    checker = get_checker()
    from modules.drift_check import network_for
    name = network_for(request, request.get_json(silent=True))
    if checker.is_running(name):
        return jsonify({"ok": False, "message": f"A drift check of {name} is already in progress"}), 409
    checker.trigger(name)
    return jsonify({"ok": True, "message": f"Drift check of {name} triggered", "list": name})


@app.route("/drift/check/sync", methods=["POST"])
def drift_check_sync():
    """Run a drift check of the network named synchronously and return the result.
    Suitable for manual 'Check Now' button clicks where the user wants to see results."""
    from modules.drift_check import (DriftRunning, DriftStateUnreadable, get_checker,
                                     run_drift_check)
    checker = get_checker()
    from modules.drift_check import network_for
    name = network_for(request, request.get_json(silent=True))
    if checker.is_running(name):
        return jsonify({"ok": False, "message": f"A drift check of {name} is already in progress"}), 409
    try:
        result = run_drift_check(triggered_by="manual", list_name=name)
    except DriftRunning as exc:
        # One run per list across processes (CONCURRENCY_AUDIT R19), named, never run twice.
        return jsonify({"ok": False, "running_run": exc.holder, "error": str(exc)}), 409
    except Exception as exc:
        app.logger.error("drift check sync error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500
    try:
        # Persisted in THAT network's state, and its next scheduled run counts from now.
        checker.record(name, result)
        return jsonify(result)
    except DriftStateUnreadable as exc:
        return jsonify({**result, "ok": False,
                        "error": f"The check ran; its result was not recorded: {exc}"}), 500
    except Exception as exc:
        app.logger.error("drift check sync error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/drift/settings", methods=["GET"])
def drift_settings_get():
    """Return the drift check interval (one, every network) and the named network's switch."""
    from modules.drift_check import _is_disabled, _get_interval
    from modules.drift_check import network_for
    name = network_for(request)
    return jsonify({
        "ok":        True,
        "list":      name,
        "interval_s": int(_get_interval()),
        "disabled":  _is_disabled(name),
    })


@app.route("/drift/settings", methods=["POST"])
def drift_settings_post():
    """Update drift check interval and/or the named network's disabled flag.

    Wrapped, and the outcome is **read back from the state file** rather than
    echoed from the request. Echoing the input reports what was asked for; the
    panel then refetches `/drift/status`, sees the opposite, and silently
    reverts the control. That is what the operator saw when the toggle could
    not be saved at all.
    """
    from modules.drift_check import _is_disabled, get_checker
    from modules.agent_timers import save as save_timers
    data     = request.get_json(silent=True) or {}
    checker  = get_checker()
    from modules.drift_check import network_for
    name     = network_for(request, data)
    saved    = {"list": name}

    try:
        if "interval_s" in data:
            interval_s = int(data["interval_s"])
            save_timers({"drift_check_interval": interval_s})
            saved["interval_s"] = interval_s
            # Every network's next run is rebuilt from its last run and the new interval.
            checker.rearm()

        if "disabled" in data:
            # Who switched it off is part of the record. See `set_disabled`.
            # Not gated -- disabling drift is not a reveal and not a device
            # change -- but the actor is recorded when one is verifiable.
            from modules.identity import identify
            try:
                ident = identify(request)
                actor = ident.actor if ident.is_identified else ""
            except Exception:                  # noqa: BLE001
                actor = ""
            checker.set_disabled(bool(data["disabled"]), actor=actor, list_name=name)
            # What is stored, not what was asked for.
            saved["disabled"] = _is_disabled(name)
    except Exception as exc:                   # noqa: BLE001
        app.logger.error("drift settings save failed: %s", exc, exc_info=True)
        return jsonify({"ok": False,
                        "error": f"Could not save drift settings: {exc}",
                        "disabled": _is_disabled(name)}), 500

    return jsonify({"ok": True, **saved})


@app.route("/session/pending-restart")
def session_pending_restart():
    """
    Return pending restart info so the frontend can auto-resume the AI session.
    The file is deleted after reading (one-shot) and expires after 120 seconds.
    """
    import time as _time
    from modules.config import DATA_DIR
    path = os.path.join(DATA_DIR, "pending_restart.json")
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
    # WRITE-ONLY (register C56): the CSV-era variable store returned every
    # value it held, whatever an operator had put there, to any caller. The
    # page never reads it (reachability group c; the store is CUT in 7.8),
    # and the agent reads variables in-process, not through this route. The
    # names are kept; each value says it is withheld.
    return jsonify({k: "<redacted:variable>" for k in _ai._load_variables()})


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
    from modules.netbox_client import sync_status_with_results, get_netbox_config
    cfg = get_netbox_config()
    return jsonify({
        "configured": bool(cfg["url"] and cfg["token"]),
        "url":        cfg["url"],
        "status":     sync_status_with_results(),
        "lists":      get_device_lists(),
    })








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
    """Return the background agent's activity log (newest first).

    **"AI is disabled" is a STATE, not an error, and it must not suppress the
    history that explains why.**

    This route used to return `{"entries": [], "status": {}}` with a 503 the
    moment AI was off — so switching the agent off hid the 26 recorded
    failures and the workspace-id error that were the reason for switching it
    off. The health surface built specifically so a dead component could not
    look quiet went silent exactly when its history mattered most, and an
    operator finding it disabled next month would have learned nothing.

    A **read** reports. Only an **action** refuses: `/ai/agent_run`,
    `/ai/agent_pause`, `/ai/agent_resume` and the timer POST still return 503,
    because a disabled agent must not be made to act.
    """
    from modules.agent_runner import get_activity_log, get_status

    limit = min(int(request.args.get("limit", 50)), 200)
    # `get_status()` reports both switches; this route does not compute a
    # second copy. One producer.
    status = get_status()
    return jsonify({
        "ok": True,
        "status": status,
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
    # A read: report the state, do not withhold the configuration because of
    # it. See `ai_agent_log` for the reasoning.
    from modules.agent_timers import get_ui_config
    return jsonify({"ok": True, "ai_enabled": _ai_enabled(),
                    "timers": get_ui_config()})


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
    from modules.filestore import StoreUnreadable
    show_all = request.args.get("all") == "1"
    limit    = min(int(request.args.get("limit", 50)), 200)
    try:
        entries = get_all(limit) if show_all else get_pending()
    except StoreUnreadable as exc:
        # Never an empty list: "nothing is waiting" and "the queue could not be read"
        # are different answers (CONCURRENCY_AUDIT R4).
        return jsonify({"ok": False, "error": str(exc)}), 503
    # Masked on the way out (register C56): a queued diff is device config,
    # and this returned it raw. The diff is advisory context, never what is
    # sent, so masking it costs the approver nothing.
    from modules.redact import redact_payload
    return jsonify({
        "pending_count": get_pending_count(),
        "entries":       redact_payload(entries),
        "ai_enabled":    _ai_enabled(),
    })


@app.route("/ai/approvals/<entry_id>/approve", methods=["POST"])
def ai_approval_approve(entry_id: str):
    """Approve a queued action and execute it immediately.

    Drift-check approvals execute via Python SSH — no AI needed.
    """
    from modules.approval_queue import resolve
    from modules.identity import request_actor
    # The VERIFIED person, so what the approval commits names them (C81).
    result = resolve(entry_id, "approve", actor=request_actor())
    if not result.get("ok"):
        return jsonify(result), (503 if result.get("unreadable") else 404)
    # Masked like the list's GET (C327): the entry carries the queued diff and the
    # execution its `advisory_diff`, device config both, and these went out raw.
    from modules.redact import redact_payload
    return jsonify(redact_payload(result))


@app.route("/ai/approvals/<entry_id>/reject", methods=["POST"])
def ai_approval_reject(entry_id: str):
    """Reject a queued action without executing it."""
    from modules.approval_queue import resolve
    from modules.identity import request_actor
    result = resolve(entry_id, "reject", actor=request_actor())
    if not result.get("ok"):
        return jsonify(result), (503 if result.get("unreadable") else 404)
    from modules.redact import redact_payload
    return jsonify(redact_payload(result))         # the entry's diff, masked (C327)


@app.route("/ai/approvals/approve_all", methods=["POST"])
def ai_approval_approve_all():
    """Hand every pending drift item to ONE capture preview (register C105).

    Approve-all resolved every item at once, and each drift item read its
    device and committed with no preview: many goldens changed by one click.
    Every queued kind now ends in a confirmation, so this approves nothing by
    itself. The drift items' devices go to the capture operation together,
    where each device's capture is previewed and confirmed by its hash, and
    an item closes only when its device is recorded. A revert is a restore
    of one device, previewed per device, so it is named for individual review.
    """
    from modules.approval_queue import get_pending

    from modules.filestore import StoreUnreadable
    devices, approvals, individual = [], {}, []
    try:
        pending = get_pending()
    except StoreUnreadable as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503
    for entry in pending:
        host = entry.get("device_hostname") or entry.get("device_ip", "")
        if entry.get("action_type") == "update_golden_config" and host:
            if host not in approvals:
                devices.append(host)
            approvals.setdefault(host, []).append(entry["id"])
        else:
            individual.append({"id": entry["id"], "device": host,
                               "action_type": entry.get("action_type", ""),
                               "reason": "requires individual review"})
    message = (f"{len(devices)} device(s) to capture from {sum(map(len, approvals.values()))} "
               "drift item(s): nothing is recorded until you confirm each"
               if devices else "No drift items to capture")
    if individual:
        message += f"; {len(individual)} item(s) require individual review"
    return jsonify({"ok": True, "capture": {"devices": devices, "approvals": approvals},
                    "individual": individual, "message": message})


# ---------------------------------------------------------------------------
# Configure tab — push IOS config, create Jenkins verification pipeline
# ---------------------------------------------------------------------------



@app.route("/configure/audit_latest", methods=["GET"])
def configure_audit_latest():
    """Return the most recent pipeline audit entry."""
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


# /golden_configs/auto_create was REMOVED (2026-09-27, register C102): one
# click committed a first golden for every device without one, with no
# preview, attributed to the agent (`Source: ai`, `Actor: ai-agent`), and it
# decided "has a golden" from the working tree. It is now a SCOPE of the one
# capture operation (`/golden/capture/preview` with `scope: no_golden`),
# previewed, confirmed, and recorded as the person who confirmed it.


# /golden_configs/save_all was REMOVED in 7.1 step 4 (register C89): one click
# promoted every device's running config to its golden, a baseline tag and the
# remote, and nothing asked whether the state was the one intended. Save All is
# now the whole-fleet form of the capture operation (routes/golden.py:
# /golden/capture/preview and /golden/capture/apply), previewed and confirmed.


# ---------------------------------------------------------------------------
# Git configuration versioning routes
# ---------------------------------------------------------------------------

@app.route("/git/status")
def git_status():
    """Return the git repo status for the current device list."""
    from modules.config_git import get_repo_status
    list_name, _ = get_current_device_list()
    return jsonify(get_repo_status(list_name))


@app.route("/git/log")
def git_log():
    """Return the commit log for the current device list."""
    from modules.config_git import get_commit_log
    list_name, _ = get_current_device_list()
    limit = min(int(request.args.get("limit", 30)), 100)
    return jsonify({"ok": True, "commits": get_commit_log(list_name, limit)})


@app.route("/git/commit/<commit_hash>")
def git_commit_diff(commit_hash):
    """Return the changed-file list and full diff for one commit."""
    from modules.config_git import get_commit_diff
    list_name, _ = get_current_device_list()
    result = get_commit_diff(list_name, commit_hash)
    if result is None:
        return jsonify({"ok": False, "error": "Commit not found"}), 404
    return jsonify({"ok": True, **result})


@app.route("/monitoring/config", methods=["GET", "POST"])
def monitoring_config():
    """GET: return collector config. POST: update one or more fields."""
    # The communities are WRITE-ONLY (register C55): no response carries a
    # value, and an empty field saves nothing (B11's rule).
    from modules.collector_config import (
        COMMUNITY_OWNER, public_config, set_collector_ip,
        set_netflow_port, set_snmp_trap_port,
    )
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        # The community has ONE owner, each device's own secret (C139). This
        # form was a second, which nothing on the host ever set, so the code's
        # literal default was the configuration. A request still carrying
        # one is refused by name rather than stored where nothing reads it.
        if any(data.get(k) for k in ("snmp_community_ro", "snmp_community_rw")):
            return jsonify({"ok": False, "error": "The SNMP community is not set here: it is "
                            + COMMUNITY_OWNER + "."}), 400
        if "collector_ip" in data:
            set_collector_ip(data["collector_ip"])
        if "netflow_port" in data:
            set_netflow_port(int(data["netflow_port"]))
        if "snmp_trap_port" in data:
            set_snmp_trap_port(int(data["snmp_trap_port"]))
        return jsonify({"ok": True, "config": public_config()})
    return jsonify(public_config())


@app.route("/monitoring/interfaces")
def monitoring_interfaces():
    """Return local network interfaces (to help user choose collector IP)."""
    from modules.collector_config import list_local_interfaces
    return jsonify(list_local_interfaces())


@app.route("/monitoring/snmp/poll", methods=["POST"])
def monitoring_snmp_poll():
    """Poll a device OID via SNMP."""
    from modules.snmp_collector import snmp_get
    from modules.collector_config import NoCommunity, community_for_address
    data      = request.get_json(silent=True) or {}
    device_ip = data.get("device_ip", "").strip()
    oids      = data.get("oids", ["sysDescr", "sysName", "sysUpTime"])
    version   = int(data.get("version", 2))
    if not device_ip:
        return jsonify({"error": "device_ip required"}), 400
    # The DEVICE's own community, never one from the request and never a
    # default (C139: the literal default was the fleet's real value, C141).
    try:
        _host, community = community_for_address(get_current_device_list()[0], device_ip)
    except NoCommunity as exc:
        return jsonify({"error": str(exc)}), 409
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
    # A received trap carries its community, and the buffer stores it; this
    # returned it with every trap (found 2026-09-27 by deriving the stores
    # from the code's writers, after C56). The field is masked, not dropped,
    # so the page and a reader can see a community was there.
    traps = [dict(t, community="<redacted:snmp_community>") if t.get("community") else t
             for t in get_recent_traps(limit, device_ips=device_ips)]
    return jsonify({"traps": traps})


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
    from modules.config import DATA_DIR
    log_path = os.path.join(DATA_DIR, "ai_debug.log")
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


@app.route("/logs/server")
def server_log():
    """Return the last N lines of logs/device_manager.log for in-browser
    diagnostics -- this is the file every "check server logs" error message
    refers to. Captures app.py plus every modules/*.py logger (see the root
    logger handler set up above)."""
    from modules import app_log

    got = app_log.tail(app_log.lines_asked(request.args.get("lines", "500")))
    text = {"Content-Type": "text/plain; charset=utf-8"}
    if got["state"] == "absent":
        return "logs/device_manager.log not yet created.\n", 404, text
    if got["state"] != "ok":
        return f"logs/device_manager.log could not be read: {got['error']}\n", 500, text
    return "".join(line + "\n" for line in got["lines"]), 200, text


# ---------------------------------------------------------------------------
# Start background daemons — must be here so _load_current_devices is defined
# ---------------------------------------------------------------------------
def _start_background_daemons():
    """Start every background service. Called ONLY when app.py runs as a
    program (`if __name__ == "__main__"`), never by importing it.

    Importing used to start six threads (the ping worker, the event monitor,
    the agent loop, the drift scheduler, and the SNMP and NetFlow listeners
    on UDP 1162 and 9996). So the test suite, `nmas-verify-runbook` and
    `nmas-scale-report` each ran a second copy of the services: the tests'
    per-test guard blamed whichever test was running when a thread wrote,
    and a script run on the host would contend for the service's ports. A
    service starts because a program runs, not because a module is imported.
    """
    session_reaper(interval=PING_INTERVAL)

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

    # The channel's heartbeat (the live-data contract, 7.2 step 13): a page
    # that stops hearing it marks every live panel as not updating.
    try:
        socketio.start_background_task(_invalidation.heartbeat_loop, socketio.sleep)
    except Exception as _e:
        app.logger.error("Heartbeat did not start: %s", _e)

    # The reader jobs (modules/reader_job.py): each reads one outside service
    # on its own thread and stores the result for every consumer. A reader
    # that did not start is a `not_run` or `stale` job-health row as well.
    try:
        from modules import reader_job as _reader_job
        _reader_job.start(announce=_reader_job.announce_via_page)
    except Exception as _e:
        app.logger.error("Reader jobs did not start: %s", _e)

    # Prometheus's generated SNMP targets, kept current with the inventory
    # (C232): regenerated when it changes, and a backstop for other processes.
    try:
        from modules import prometheus_targets as _prometheus_targets
        _prometheus_targets.start_keeper()
    except Exception as _e:
        app.logger.error("Prometheus targets keeper did not start: %s", _e)

    # Start SNMP trap receiver and NetFlow collector using per-list config
    try:
        from modules.collector_config import get_snmp_trap_port, get_netflow_port
        from modules.snmp_collector import start_trap_receiver
        from modules.netflow_collector import start_netflow_receiver
        start_trap_receiver(port=get_snmp_trap_port())
        start_netflow_receiver(port=get_netflow_port())
    except Exception as _e:
        app.logger.warning("Monitoring daemons: %s", _e)

# Run the Flask app with Socket.IO
if __name__ == "__main__":
    import sys
    _start_background_daemons()
    try:
        url = f"http://{'127.0.0.1' if FLASK_HOST == '0.0.0.0' else FLASK_HOST}:{FLASK_PORT}"
        # Off for a headless deployment (NMAS_HEADLESS=1 or the setting).
        if AUTO_OPEN_BROWSER:
            threading.Timer(1.2, lambda: webbrowser.open(url)).start()
        else:
            print(f"NMAS listening on {url}")
        socketio.run(app, host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG, use_reloader=False, allow_unsafe_werkzeug=True)
    except Exception as e:
        print(f"\n{'='*60}")
        print(f"ERROR: {e}")
        print(f"{'='*60}")
        import traceback
        traceback.print_exc()
        if getattr(sys, 'frozen', False):
            input("\nPress Enter to exit...")
        sys.exit(1)
