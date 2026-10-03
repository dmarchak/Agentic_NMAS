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

import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request

GECKODRIVER_CANDIDATES = ("/snap/firefox/current/usr/lib/firefox/geckodriver",)


def _geckodriver():
    for path in GECKODRIVER_CANDIDATES:
        if os.access(path, os.X_OK):
            return path
    found = shutil.which("geckodriver")
    if found and not found.startswith("/snap/bin/"):
        return found
    return ""


def _profile_parent() -> str:
    snap = os.path.expanduser("~/snap/firefox/common")
    return snap if os.path.isdir(snap) else tempfile.gettempdir()


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


class Served:
    """The Flask app served on loopback on a thread, for the browser."""

    def __init__(self, app):
        from werkzeug.serving import make_server

        self.port = free_port()
        self.server = make_server("127.0.0.1", self.port, app, threaded=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def __exit__(self, *exc):
        """Down for certain, and bounded (the operator, 2026-10-01: run #241
        timed out with this server's long-poll threads alive in a worker).
        The page's socket.io sessions are closed server-side first, so no
        request thread stays blocked in a long poll; then the server stops,
        its socket closes, and its thread is joined with a limit."""
        close_socketio_sessions()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=SHUTDOWN_SECONDS)


#: The teardown's bound: a server that does not stop within it is a leak the
#: session-end guard names.
SHUTDOWN_SECONDS = 5


def close_socketio_sessions() -> int:
    """Disconnect every engine.io session the app's socket.io server holds,
    each long poll answered and ended. Returns how many."""
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


class Browser:
    """One headless Firefox session; stopped on exit, geckodriver with it."""

    def __init__(self, prefs: dict = None):
        """*prefs* are Firefox preferences for the session: a phone's width is
        `{"layout.css.devPixelsPerPx": "2.0"}` in a window twice as wide, because
        geckodriver will not make a window narrower than about 500 px."""
        self.prefs = dict(prefs or {})
        self.port = free_port()
        # The profile geckodriver writes must be readable by Firefox: snap
        # Firefox has a PRIVATE /tmp, so a profile in the host's /tmp is
        # invisible to it and it exits with status 1 (measured 2026-09-30).
        # The snap's own common directory is readable by both.
        self.tmp = tempfile.mkdtemp(prefix="nmas-browser-", dir=_profile_parent())
        env = dict(os.environ, TMPDIR=self.tmp)
        # The browser on the REAL clock: under libfaketime (C353's survey, the suite with the
        # clock moved forward) Firefox does not start with the preload, and the survey asks
        # what the SERVER's code does at a later date. Nothing here otherwise.
        for key in [k for k in env if k == "LD_PRELOAD" or k.startswith("FAKETIME")]:
            env.pop(key)
        self.proc = subprocess.Popen([_geckodriver(), "--port", str(self.port)], env=env,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.session = ""

    def _call(self, method, path, body=None, timeout=60):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())["value"]

    def __enter__(self):
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
            "moz:firefoxOptions": {"args": ["-headless"], "prefs": self.prefs}}}})["sessionId"]
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
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            shutil.rmtree(self.tmp, ignore_errors=True)
