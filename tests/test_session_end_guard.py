"""The session's end names what keeps a process alive (the operator,
2026-10-01: CI run #241 timed out after every test had passed, with a live
server's threads in a worker and nothing named).

A NON-DAEMON thread alive at the session's end keeps the process from exiting,
so it is named and fails the run; a daemon thread cannot, so it is not. And
the live server the browser tests use is stopped for certain: its socket.io
sessions closed, its thread joined, bounded.
"""
import threading

from tests.conftest import leaked_threads


def _hold(event):
    event.wait(10)


class TestTheGuard:
    def test_a_non_daemon_thread_still_alive_is_named(self):
        release = threading.Event()
        t = threading.Thread(target=_hold, args=(release,), name="planted-server", daemon=False)
        t.start()
        try:
            got = leaked_threads(grace=0.2)
            assert any("planted-server" in g and "_hold" in g for g in got), got
        finally:
            release.set()
            t.join(5)

    def test_a_daemon_thread_is_not_a_leak(self):
        release = threading.Event()
        t = threading.Thread(target=_hold, args=(release,), name="planted-daemon", daemon=True)
        t.start()
        try:
            assert not any("planted-daemon" in g for g in leaked_threads(grace=0.2))
        finally:
            release.set()
            t.join(5)

    def test_a_thread_finishing_within_the_grace_is_not_a_leak(self):
        release = threading.Event()
        t = threading.Thread(target=_hold, args=(release,), name="finishing", daemon=False)
        t.start()
        threading.Timer(0.1, release.set).start()
        assert not any("finishing" in g for g in leaked_threads(grace=2))


class TestTheLiveServerStops:
    def test_the_served_app_stops_bounded_with_its_sessions_closed(self, monkeypatch):
        """Without a browser: the server is started, a socket.io session is
        opened against it over long-polling, and the teardown ends both."""
        import json
        import urllib.request

        import app as A
        from tests import browser

        with browser.Served(A.app) as srv:
            body = urllib.request.urlopen(srv.url("/socket.io/?EIO=4&transport=polling"),
                                          timeout=5).read().decode()
            sid = json.loads(body[body.index("{"):])["sid"]
            assert sid in A.socketio.server.eio.sockets
        assert sid not in A.socketio.server.eio.sockets
        assert not srv.thread.is_alive()
