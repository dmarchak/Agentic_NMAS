"""A REAL browser for the tests that must click what ships (not a test
module). Headless Firefox driven through geckodriver's WebDriver HTTP API,
with no client library: a POST per command over loopback.

Why it exists (the operator, 2026-09-30): the Update button's first real run
did nothing. Its component read its attributes through `$el`, the button,
and disabled itself. Every test had built the pieces without clicking the
shipped button, and duktape cannot run Alpine. Where a browser is available
(the laptop), a test serves the real app on loopback, loads the real page,
and clicks. Where none is, the test SKIPS and says why, and the static wiring
rule in tests/test_update_button.py still runs. CI's runner HAS one (Firefox,
and a geckodriver outside any snap), so they run there: run #241's thread dump
showed this module's live server in a worker (2026-10-01). This file said CI
skipped them until then. The confined runner on the laptop skips them, since
snap Firefox cannot start in its namespace.

geckodriver is launched from its own binary, never through /snap/bin: a
snap-confined process cannot be stopped by the test that started it.
"""

import io
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

from tests import home_guard

GECKODRIVER_CANDIDATES = ("/snap/firefox/current/usr/lib/firefox/geckodriver",)
#: The session's watcher (C775): it leads the browser's process group and stops it when the
#: test process that started it ends, however it ends.
WATCHER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "browser_watch.py")


def _geckodriver():
    for path in GECKODRIVER_CANDIDATES:
        if os.access(path, os.X_OK):
            return path
    found = shutil.which("geckodriver")
    if found and not found.startswith("/snap/bin/"):
        return found
    return ""


def _snap_firefox() -> bool:
    """Whether the `firefox` on PATH is the snap's (itself, or the shell wrapper that runs it)."""
    found = shutil.which("firefox") or ""
    real = os.path.realpath(found) if found else ""
    if real.startswith("/snap/"):
        return True
    try:
        with open(real, "rb") as fh:
            head = fh.read(4096)
    except OSError:
        return False
    return not head.startswith(b"\x7fELF") and b"/snap/bin/firefox" in head


def _profile_parent() -> str:
    """Where a session's own folder goes: the system's temporary directory, except for snap
    Firefox, whose private /tmp cannot see it (so the snap's common directory, in the home).
    C392: it was the home's whenever that directory EXISTED, whichever Firefox ran."""
    snap = os.path.expanduser("~/snap/firefox/common")
    return snap if _snap_firefox() and os.path.isdir(snap) else tempfile.gettempdir()


#: Folders a session could not remove (C392): the session-end guard names them.
LEFT_BEHIND = []


def remove_folder(path: str) -> bool:
    """Remove *path*, and say whether it is gone: an `ignore_errors` removal said nothing."""
    shutil.rmtree(path, ignore_errors=True)
    return not os.path.exists(path)


_PROBED = []


def available() -> tuple:
    """``(True, "")`` or ``(False, why)``, measured once per run by STARTING a
    session: a browser that is installed and cannot start here is not
    available. Measured 2026-09-30: inside `scripts/nmas-test`'s loopback-only
    namespace, snap Firefox exits with status 1, so there these tests skip
    saying so, and run under plain `pytest` on the laptop."""
    if not _geckodriver():
        return False, "no geckodriver outside a snap wrapper on this machine"
    if not shutil.which("firefox"):
        return False, "no firefox on this machine"
    if not _PROBED:
        try:
            with Browser():
                pass
            _PROBED.append((True, ""))
        except Exception as exc:                        # noqa: BLE001
            detail = exc.read().decode(errors="replace")[:300] if hasattr(exc, "read") else str(exc)
            _PROBED.append((False, f"Firefox could not start in this runner: {detail}"))
    return _PROBED[0]


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


#: Every server this module serves now, so a test's teardown can wait for each one's requests.
_LIVE: list = []


class Served:
    """The Flask app served on loopback on a thread, for the browser.

    **It knows which requests it is handling** (CI #850): a server is shared by a module's
    tests, and a request the page sent before the test ended (a fetch the page makes on load)
    was still running when the test's patches were undone. It resolved the network's folder
    through the real `get_list_data_dir` and committed into the SHARED store, which the next
    test's store guard reported as its own. :func:`wait_for_requests` waits for them."""

    def __init__(self, app):
        from werkzeug.serving import make_server

        self.port = free_port()
        self._lock = threading.Lock()
        self._in_flight: dict = {}          # a request -> "METHOD /path"
        self._threads: dict = {}            # a request -> the thread handling it
        self._changed = time.monotonic()    # when a request last began or ended
        self.server = make_server("127.0.0.1", self.port, app, threaded=True,
                                  request_handler=self._handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def _handler(self):
        """werkzeug's request handler, recording each request for as long as werkzeug runs
        it (`run_wsgi`: the view, its body written, and however it ends). Not the body's
        `close()`: werkzeug 3.0.1 skips it when the client has gone (its drain of the socket
        raises first, `serving.py`), and a page left at once had gone."""
        from werkzeug.serving import WSGIRequestHandler

        served = self

        class Handler(WSGIRequestHandler):
            def run_wsgi(self):
                key = object()
                with served._lock:
                    served._in_flight[key] = f"{self.command} {self.path.split('?', 1)[0]}"
                    served._threads[key] = threading.get_ident()
                    served._changed = time.monotonic()
                try:
                    super().run_wsgi()
                finally:
                    with served._lock:
                        served._in_flight.pop(key, None)
                        served._threads.pop(key, None)
                        served._changed = time.monotonic()
        return Handler

    def in_flight(self) -> list:
        """The requests this server is handling now, as "METHOD /path"."""
        with self._lock:
            return sorted(self._in_flight.values())

    def wait_idle(self, deadline: float) -> None:
        """Return once no request has been in flight for :data:`QUIET_SECONDS`; raise,
        naming each one, if any is still running at *deadline* (`time.monotonic()`)."""
        import traceback

        while True:
            with self._lock:
                running = sorted(self._in_flight.values())
                where = [(self._in_flight[k], t) for k, t in self._threads.items()]
                quiet = time.monotonic() - self._changed
            if not running and quiet >= QUIET_SECONDS:
                return
            if time.monotonic() >= deadline:
                frames = sys._current_frames()
                stacks = "".join(f"\n--- {what}, where it is now ---\n"
                                 + "".join(traceback.format_stack(frames[t])[-12:])
                                 for what, t in where if t in frames)
                raise AssertionError(
                    f"the served app was still handling {running} {REQUESTS_SECONDS} s after "
                    "the test's page was left: its work would outlive the test's patches and "
                    "write where they no longer point (CI #850)" + stacks)
            time.sleep(0.02)

    def __enter__(self):
        self.thread.start()
        _LIVE.append(self)
        return self

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def __exit__(self, *exc):
        """Down for certain, and bounded (the operator, 2026-10-01: run #241
        timed out with this server's long-poll threads alive in a worker).
        The page's socket.io sessions are closed server-side first, so no
        request thread stays blocked in a long poll; then the server stops,
        its socket closes, and its thread is joined with a limit."""
        try:
            close_socketio_sessions()
        finally:
            if self in _LIVE:
                _LIVE.remove(self)
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=SHUTDOWN_SECONDS)


#: The teardown's bound: a server that does not stop within it is a leak the
#: session-end guard names.
SHUTDOWN_SECONDS = 5

#: How long a test's teardown waits for the requests its page left running: 2.5x the slowest
#: request any browser test's page made, 4.7 s (`GET /v2/monitoring/apply`, measured
#: 2026-10-16 over the four shards at once on the laptop, 8,530 requests), rounded up.
REQUESTS_SECONDS = 12
#: No request may begin within this long of the last one ending before the server counts as
#: idle: a request the page sent before it was left reaches the app one read and one parse
#: after its bytes arrive, far inside it.
QUIET_SECONDS = 0.2


def wait_for_requests() -> None:
    """Wait until every served app has finished each request in flight (CI #850). Called
    from :func:`close_socketio_sessions`, which every served page's teardown runs once the
    page is left, so the work a request does ends while the test's patches still hold."""
    deadline = time.monotonic() + REQUESTS_SECONDS
    for srv in list(_LIVE):
        srv.wait_idle(deadline)


def close_socketio_sessions() -> int:
    """Disconnect every engine.io session the app's socket.io server holds,
    each long poll answered and ended, then wait for every request the served
    apps are still handling (:func:`wait_for_requests`). Returns how many
    sessions were closed."""
    closed = _close_socketio_sessions()
    wait_for_requests()
    return closed


def _close_socketio_sessions() -> int:
    try:
        import app as A
        eio = A.socketio.server.eio
    except Exception:                                   # noqa: BLE001
        return 0
    # NOT `eio.disconnect(sid)`: it waits for a client to drain the session's
    # queue, and once the page is gone there is none, so it blocks for ever
    # (measured 2026-10-01 building this teardown: the hang in miniature).
    # Closed without waiting, aborted: the long poll's request thread is woken
    # by the close's sentinel and returns. `wait`/`abort` exist in the host's
    # pinned 4.3.4 and in later releases alike.
    sockets = getattr(eio, "sockets", {}) or {}
    sids = list(sockets)
    for sid in sids:
        try:
            sockets[sid].close(wait=False, abort=True)
        except Exception:                               # noqa: BLE001
            pass
        sockets.pop(sid, None)
    return len(sids)


def stop_group(pgid: int, wait_s: float = 5.0) -> bool:
    """Stop every process left in the process group *pgid* (a session's geckodriver's, made
    for it with `start_new_session`): TERM, then KILL after *wait_s*. True when none is left.
    By the group this module made, never by a name (CLAUDE.md: identity, not pattern)."""
    import signal

    for sig, wait in ((signal.SIGTERM, wait_s), (signal.SIGKILL, wait_s)):
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            return True
        deadline = time.time() + wait
        while time.time() < deadline:
            try:
                os.killpg(pgid, 0)
            except ProcessLookupError:
                return True
            time.sleep(0.05)
    return False


class Browser:
    """One headless Firefox session; stopped on exit, geckodriver with it."""

    #: The new-session call's bound, the 60 s every call had (not re-measured here); a session
    #: not started in it is one that will not start, and its Firefox is stopped with its group
    #: (C521). A test lowers it to plant a session that never answers.
    START_TIMEOUT_S = 60
    #: Calls to any session's driver in this process: the test tiers (tests/conftest.py) call a
    #: test that made one a browser test, by what it did rather than by what its file imports
    #: (a module's browser is often started before its first test).
    calls = 0

    def __init__(self, prefs: dict = None, page_load: str = "normal"):
        #: WebDriver's pageLoadStrategy: "none" returns from a navigation at once, so a test can
        #: act on a page before its deferred scripts have run (C399), as a person can.
        self.page_load = page_load
        """*prefs* are Firefox preferences for the session: a phone's width is
        `{"layout.css.devPixelsPerPx": "2.0"}` in a window twice as wide, because
        geckodriver will not make a window narrower than about 500 px."""
        self.port = free_port()
        # The profile geckodriver writes must be readable by Firefox: snap
        # Firefox has a PRIVATE /tmp, so a profile in the host's /tmp is
        # invisible to it and it exits with status 1 (measured 2026-09-30).
        # The snap's own common directory is readable by both.
        self.tmp = tempfile.mkdtemp(prefix=home_guard.session_prefix("browser"),
                                    dir=_profile_parent())
        # C391: a download lands in this session's own folder, never the person's Downloads
        # (the export tests had saved 45 test records there). Not overridable by *prefs*.
        self.downloads = os.path.join(self.tmp, "downloads")
        os.mkdir(self.downloads)
        self.prefs = dict(prefs or {}, **{"browser.download.folderList": 2,
                                          "browser.download.dir": self.downloads,
                                          "browser.download.useDownloadDir": True})
        env = dict(os.environ, TMPDIR=self.tmp)
        if not _snap_firefox():
            # And nothing else of Firefox's in the person's home (its caches, its default
            # Downloads); the snap's own wrapper decides its HOME, so it is left alone.
            env.update(HOME=self.tmp, XDG_DOWNLOAD_DIR=self.downloads)
        # The browser on the REAL clock: under libfaketime (C353's survey, the suite with the
        # clock moved forward) Firefox does not start with the preload, and the survey asks
        # what the SERVER's code does at a later date. Nothing here otherwise.
        for key in [k for k in env if k == "LD_PRELOAD" or k.startswith("FAKETIME")]:
            env.pop(key)
        # Its own process group (C521): the Firefox it starts is in it, so stopping the group
        # stops that Firefox too, by identity. Terminating geckodriver alone orphaned a Firefox
        # whose session never answered (CI #473), and it kept writing into the folder.
        # The group's leader is tests/browser_watch.py (C775), which starts geckodriver and
        # stops the group when THIS process ends however it ends: a test process ended by a
        # SIGTERM, a SIGKILL or a lost xdist worker never ran __exit__, and its browser ran on
        # for days. `self.proc` is the watcher; the group is its pid.
        self.proc = subprocess.Popen(
            [sys.executable, WATCHER, str(os.getpid()), self.tmp, _geckodriver(), "--port",
             str(self.port)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)
        self.session = ""

    def _call(self, method, path, body=None, timeout=60):
        Browser.calls += 1
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())["value"]
        except urllib.error.HTTPError as exc:
            # WebDriver answers every command error (a script's TypeError, a stale element, a
            # script timeout) as an HTTP error whose JSON names it; urllib's own message drops
            # that JSON, so a failure read only "HTTP Error 500" (C2127, wrongly taken as the
            # app's 500). The same type is raised, its body still readable, with the error named.
            body = exc.read()
            try:
                value = json.loads(body).get("value") or {}
            except ValueError:
                value = {}
            said = (f"{method} {path}: WebDriver {value.get('error') or 'error'}: "
                    f"{(value.get('message') or body[:300].decode(errors='replace')).strip()}")
            raise urllib.error.HTTPError(exc.url, exc.code, said, exc.headers,
                                         io.BytesIO(body)) from exc

    def __enter__(self):
        # C392: a session that cannot start (snap Firefox inside the confined suite, where
        # `available()` probes once per process) never reaches __exit__, so it stops its own
        # geckodriver and removes its folder here. It had not: 442 geckodriver processes
        # (2.9 GB) and 442 folders were left, one per confined test process since 2026-09-30.
        try:
            deadline = time.time() + 20
            while True:
                try:
                    self._call("GET", "/status", timeout=2)
                    break
                except OSError:
                    if time.time() > deadline:
                        raise
                    time.sleep(0.2)
            self.session = self._call("POST", "/session", {"capabilities": {"alwaysMatch": {
                "pageLoadStrategy": self.page_load,
                "moz:firefoxOptions": {"args": ["-headless"], "prefs": self.prefs}}}},
                timeout=self.START_TIMEOUT_S)["sessionId"]
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def go(self, url: str) -> None:
        self._call("POST", f"/session/{self.session}/url", {"url": url})

    def js(self, script: str, *args):
        return self._call("POST", f"/session/{self.session}/execute/sync",
                          {"script": script, "args": list(args)})

    def wait_for(self, script: str, timeout: float = 10.0, *args):
        """Poll *script* until it returns a truthy value; return it, or raise
        naming the script."""
        deadline = time.time() + timeout
        while True:
            value = self.js(script, *args)
            if value:
                return value
            if time.time() > deadline:
                raise AssertionError(f"not true within {timeout} s: {script}")
            time.sleep(0.1)

    def click(self, css: str) -> None:
        """A real click through WebDriver: the element must be visible and
        enabled, which is exactly what the first run's button was not."""
        el = self._call("POST", f"/session/{self.session}/element",
                        {"using": "css selector", "value": css})
        key = next(iter(el.values()))
        self._call("POST", f"/session/{self.session}/element/{key}/click", {})

    def type(self, css: str, text: str, pause: float = 0.0) -> None:
        """Real key events into the element, one character at a time, as a person types
        (WebDriver's element send-keys), each *pause* seconds apart. A paste is one event; a
        bug that only typing shows (a redraw stealing focus mid-word) needs this."""
        el = self._call("POST", f"/session/{self.session}/element",
                        {"using": "css selector", "value": css})
        key = next(iter(el.values()))
        for ch in text:
            self._call("POST", f"/session/{self.session}/element/{key}/value", {"text": ch})
            if pause:
                time.sleep(pause)

    def screenshot(self, path: str) -> None:
        import base64

        png = self._call("GET", f"/session/{self.session}/screenshot")
        with open(path, "wb") as fh:
            fh.write(base64.b64decode(png))

    def __exit__(self, *exc):
        try:
            if self.session:
                self._call("DELETE", f"/session/{self.session}", timeout=20)
        finally:
            # The group, not the watcher alone: geckodriver and Firefox get the SIGTERM, the
            # watcher (which ignores it) sees geckodriver end, sweeps the rest and exits.
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            stop_group(self.proc.pid)
            if not remove_folder(self.tmp):
                LEFT_BEHIND.append(self.tmp)
