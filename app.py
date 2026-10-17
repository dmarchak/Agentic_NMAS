# [Author]
# Agentic Network Management
# Device Manager web application

# Load .env file if present (an install's environment variables, without needing system env vars;
# the AI key it once held left with the AI family, D15).
# Use an absolute path (where /settings once wrote it) instead of relying on
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

# Import Project modules
from modules.device import (
    load_saved_devices,
    save_device,
    write_devices_csv,
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
    FILE_TRANSFER_METHOD,
    FLASK_HOST,
    FLASK_PORT,
    FLASK_DEBUG,
    AUTO_OPEN_BROWSER,
    set_user_setting,
    get_user_setting,
    save_user_settings,
)
from modules.connection import session_reaper
from modules import route_gates
from modules.identity import request_actor
from modules.utils import make_device_filename

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

        if resp.mimetype == "text/html" and "Cache-Control" in resp.headers:
            # A DEFAULT, never an overwrite (C840): a route that set its own
            # Cache-Control has thought harder than this rule. The reveals
            # say `no-store` (modules/outbound.py, `no_store`); overwriting
            # it made every revealed secret a page a browser may keep.
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
    # logging.getLogger(__name__) (modules.config_git, modules.drift_check, ...)
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
    """Answer a navigation with v2's failure page; a fetch() with JSON; both with a real status.

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
        # Every navigation that failed is answered ON v2, in place, with its status (C569's
        # rule, for every path since P7-19, 2026-10-15): a redirect to today's index made a
        # failure look like a page load, and that index goes at cutover.
        from routes.v2_failure import answer
        return answer(message, status)
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

    return render_template(
        "index.html",
        devices=devices,
        device_lists=device_lists,
        current_list=current_list_name,
    )


# Today's device page (GET /device/<ip>) and its command box (POST /run_command/<ip>) left at
# 7.8 on 2026-10-17 (P7-22): a device's page is v2's /v2/device/<name>, and a read a person
# types is its Ask tab, from the same allowlist. The app's own session pool went with them:
# /run_command was its only user.


# ---------------------------------------------------------------------------
# Device List Management Routes
# ---------------------------------------------------------------------------

# GET /device_lists (the list of lists as JSON) left at 7.8 on 2026-10-15: no page called it;
# today's page renders the lists server-side and v2's Network picker draws its own.

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
            return jsonify({"status": "success", "message": f"Switched to '{list_name}'"})
        else:
            return jsonify({"status": "error", "message": f"List '{list_name}' not found"}), 404

    except Exception as e:
        app.logger.error(f"Failed to select device list: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# Today's Settings modal's routes (GET and POST /settings, and its NetBox Test,
# POST /netbox/test_connection) left with the modal at 7.8 (2026-10-15). NetBox's connection is
# Settings › Installation › Connections, the NetBox connection card (its Test is the same
# netbox_client.test_connection, C468); NetBox writes are turned on by an authorised NetBox
# confirm (C619) and off on that card.

# Today's bulk commands (POST /bulk_execute, GET /bulk_status/<id>, and the worker,
# modules/bulk_ops.py) left at 7.8 on 2026-10-15: Show commands (/v2/show-commands) runs
# allowlisted reads across devices. POST /bulk_clear/<id> had left the same day.


# `/ai/restart` and `/server/restart` are REMOVED (CONCURRENCY_AUDIT R5, 2026-10-02): each
# ended the process seconds after answering, checking no held device, running job or
# commit in progress, so one person could cut off another's deploy half-applied. Neither
# had a caller (measured 2026-09-27); the Update button restarts, gated on held devices.

# Today's drift routes (/drift/status, POST /drift/check/sync, POST /drift/settings) left with
# today's Drift tab at 7.8 (2026-10-15). The schedule, each network's switch and Check now are
# Settings › Installation › Diagnostics (routes/settings_v2.py); the results are Needs attention
# rows; the checker (modules/drift_check.py) is unchanged.


# Today's NetBox tab and its routes (GET /netbox/status, and the /netbox/safety/* blueprint,
# routes/netbox_safety.py) left at 7.8 (2026-10-17). Source of truth › NetBox (/v2/netbox,
# routes/netbox_v2.py) draws each network's last import and its removals, and previews and
# confirms Import, Import every network, Remove and Stop tracking through the same core,
# modules/netbox_ops.py.


# ---------------------------------------------------------------------------
# Background agent routes
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Approval queue routes
# ---------------------------------------------------------------------------


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


# Today's Logs tab's route (/logs/server) left with the tab at 7.8 (2026-10-15): the app's log is
# Settings › Installation › Diagnostics (routes/settings_v2.diag_log, over modules/app_log).


# ---------------------------------------------------------------------------
# Start background daemons
# ---------------------------------------------------------------------------
def _start_background_daemons():
    """Start every background service. Called ONLY when app.py runs as a
    program (`if __name__ == "__main__"`), never by importing it.

    Importing used to start six threads (the ping worker, the AI family's
    event monitor and agent loop, the drift scheduler, and its SNMP and
    NetFlow listeners on UDP 1162 and 9996, removed with it). So the test suite, `nmas-verify-runbook` and
    `nmas-scale-report` each ran a second copy of the services: the tests'
    per-test guard blamed whichever test was running when a thread wrote,
    and a script run on the host would contend for the service's ports. A
    service starts because a program runs, not because a module is imported.
    """
    session_reaper(interval=PING_INTERVAL)

    # The device holds' markers (C987): a network's lock folder written before them is read
    # in full by every page's In progress chip until it is indexed, once, here.
    try:
        from modules.nsot import device_ops as _device_ops
        _device_ops.index_all()
    except Exception as _e:
        app.logger.error("Device holds were not indexed: %s", _e)

    # The drift checker
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

    # The scheduled credential rotation's timer (C724): a run only when a policy is on.
    try:
        from modules.nsot import scheduled_rotation as _scheduled_rotation
        _scheduled_rotation.start()
    except Exception as _e:
        app.logger.error("Scheduled rotation timer did not start: %s", _e)


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
