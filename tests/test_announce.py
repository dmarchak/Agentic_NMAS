"""C58: a change the server makes AFTER a response, or on its own schedule,
is ANNOUNCED over the page's socket and dispatched by the same registry as a
response header (modules/invalidation.announce, static/js/nmas_invalidation.js).

Driven end to end: a reader job finishes, the app's own emitter sends the
event, a connected Socket.IO test client receives it, and the SHIPPED client,
executed in duktape, re-fetches the panel subscribed to the key."""

import re

import dukpy
import pytest

from modules import config
from modules import invalidation as I
from modules import reader_job as R
from tests.test_invalidation_map import CLIENT, HARNESS


def _run(body, prelude="", **kwargs):
    client = open(CLIENT, encoding="utf-8").read()
    script = (HARNESS + prelude + "(function () {\n" + client.replace(
        "})(typeof window !== 'undefined' ? window : this);",
        "})(window);") + "\n})();\nvar NMAS = window.NMAS;\n" + body)
    return dukpy.evaljs(script, **kwargs)


# A socket.io stand-in: records the handlers the client registers, so a test
# can fire 'connect', 'disconnect' and the announcement as the server would.
FAKE_IO = """
var handlers = {};
window.io = function () { return {on: function (ev, f) { handlers[ev] = f; }}; };
"""


class TestTheServerSide:
    def test_a_key_outside_the_vocabulary_is_refused(self):
        with pytest.raises(ValueError, match="outside the vocabulary"):
            I.announce(["no_such_key"], "test")
        with pytest.raises(ValueError, match="none given"):
            I.announce([], "test")

    def test_no_emitter_raises_rather_than_pretending_it_was_heard(self, monkeypatch):
        monkeypatch.setattr(I, "_emitter", None)
        with pytest.raises(RuntimeError, match="no emitter"):
            I.announce(["drift"], "test")

    def test_the_message_carries_key_names_and_who_never_data(self, monkeypatch):
        sent = []
        monkeypatch.setattr(I, "_emitter", lambda ev, msg: sent.append((ev, msg)))
        msg = I.announce(["drift", "approvals"], "reader:x", ok=False)
        assert sent == [(I.ANNOUNCE_EVENT, msg)]
        assert set(msg) == {"keys", "by", "ok", "at"}
        assert msg["keys"] == ["drift", "approvals"] and msg["ok"] is False


class TestThroughTheAppsSocket:
    """The seam: the app hands its socket's emit to the invalidation module,
    and a reader's run reaches a CONNECTED client."""

    @pytest.fixture
    def sock(self, tmp_path, monkeypatch):
        import app as A
        monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
        client = A.socketio.test_client(A.app)
        assert client.is_connected()
        client.get_received()
        yield client
        client.disconnect()
        R.unregister("t-announce")

    def test_a_reader_finishing_reaches_a_connected_page(self, sock):
        r = R.register(R.Reader(
            name="t-announce", what="a test reader", endpoints=("api/test",),
            interval_seconds=60, interval_basis="test", read=lambda: {"n": 1},
            invalidates=("drift",)))
        R.run_once(r, announce=R.announce_via_page)
        got = [m for m in sock.get_received() if m["name"] == I.ANNOUNCE_EVENT]
        assert len(got) == 1
        msg = got[0]["args"][0]
        assert msg["keys"] == ["drift"] and msg["by"] == "reader:t-announce" and msg["ok"] is True

    def test_a_failed_read_is_announced_too(self, sock):
        def boom():
            raise ConnectionError("down")
        r = R.register(R.Reader(
            name="t-announce", what="a test reader", endpoints=("api/test",),
            interval_seconds=60, interval_basis="test", read=boom, invalidates=("drift",)))
        R.run_once(r, announce=R.announce_via_page)
        got = [m["args"][0] for m in sock.get_received() if m["name"] == I.ANNOUNCE_EVENT]
        assert got and got[0]["ok"] is False


class TestTheShippedClient:
    def test_it_listens_for_the_event_the_server_sends(self):
        src = open(CLIENT, encoding="utf-8").read()
        assert re.findall(r"sock\.on\('([a-z_]+)', onAnnounce\)", src) == [I.ANNOUNCE_EVENT]

    def test_an_announcement_re_fetches_the_subscribed_panel_only(self):
        out = _run("""
          var calls = 0;
          NMAS.subscribe('drift', 'badge', function () { calls++; return true; });
          NMAS.subscribe('topology', 'layout', function () { calls += 100; return true; });
          handlers['connect']();
          var names = handlers['nmas_invalidate']({keys: ['drift'], by: 'reader:x', ok: true});
          var last = NMAS.log()[NMAS.log().length - 1];
          [calls, names, last.event, last.by];
        """, prelude=FAKE_IO)
        assert out == [1, ["badge"], "announced", "reader:x"]

    def test_the_page_says_when_announcements_cannot_reach_it(self):
        out = _run("""
          var before = NMAS.liveNoteHtml();
          handlers['connect']();
          var up = NMAS.liveNoteHtml();
          handlers['disconnect']();
          [before, up, NMAS.liveNoteHtml(), NMAS.live().state];
        """, prelude=FAKE_IO)
        before, up, down, state = out
        assert "not connected" in before
        assert up == "", "a connected page draws nothing"
        assert "Live updates stopped at" in down and state == "disconnected"

    def test_the_note_is_drawn_in_the_one_place_every_page_has(self):
        out = _run("""
          var el = panel('nmasLiveNote');
          var loaded = el.innerHTML;
          handlers['connect']();
          var up = el.innerHTML;
          handlers['connect_error']();
          var failed = el.innerHTML;
          handlers['disconnect']();
          [loaded === undefined, up, failed, el.innerHTML];
        """, prelude=FAKE_IO)
        loaded_empty, up, failed, down = out
        assert loaded_empty, "nothing is drawn before the first connect"
        assert up == ""
        assert "could not connect" in failed
        assert "Live updates stopped at" in down

    def test_base_html_has_the_element_and_loads_the_client_before_the_registry(self):
        import os
        base = open(os.path.join(os.path.dirname(CLIENT), "..", "..", "templates", "base.html"),
                    encoding="utf-8").read()
        assert 'id="nmasLiveNote"' in base
        # Anchored on the tag's own form: the comment above the tag names the
        # registry file too (a pattern that can appear in English).
        assert (base.index("filename='js/vendor/socket.io-client/socket.io.min.js'")
                < base.index("filename='js/nmas_invalidation.js'"))

    def test_with_no_socket_client_the_registry_still_works(self):
        """The header path must not depend on the socket (the duktape
        harness has no `io`, like a page whose vendored client failed)."""
        out = _run("""
          var calls = 0;
          NMAS.subscribe('drift', 'badge', function () { calls++; return true; });
          NMAS.onAnnounce({keys: ['drift'], by: 'x', ok: true});
          [calls, NMAS.live().state];
        """)
        assert out == [1, "not_connected"]
