"""Every Needs attention row says how it clears; a person acknowledges an EVENT row (the
operator, 2026-10-02).

"Add 'Acknowledge…' to event rows: a required reason, recorded with who and when; the row
leaves Needs attention; the device's History keeps the restart marked unplanned +
acknowledged, by whom, why. A NEW restart is a new row… Then for EVERY row kind in the
40-kind declaration, state how it clears — the condition resolving, a person acknowledging,
or time — and show that on the row ('clears when…')."

On s3's REAL reboot (the restarts tests' capture) and a repeated authorisation shaped as
`receipts.authorisations_by_device` returns it:

- CLEARS covers every declared kind, both ways, each with known ways and words; the kinds
  acknowledged here are exactly the ones whose ways say so and need an event;
- every row carries "Clears when …", and both pages draw it;
- an acknowledgement goes through the real route as the verified person, refuses a reason
  without the shape of one, a row not on the page, a different event and a kind that clears
  by itself; the row leaves the list and is named under what was checked;
- it covers THAT event: a new restart is a new row, the same line authorised once more
  raises its row again;
- History keeps the restart unexpected, marked acknowledged, by whom and why;
- an unreadable acknowledgement record hides nothing and says so.
"""

import json
import os
import re
import time

import pytest

from tests.test_restarts import _cached, _expected_boot, _read, _series

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
    return tmp_path


def _client():
    from app import app
    app.config["TESTING"] = True
    return app.test_client()


def _restarts_cached(monkeypatch, value):
    from modules import reader_job
    real = reader_job.read_cached
    monkeypatch.setattr(reader_job, "read_cached",
                        lambda name: _cached(value) if name == "restarts" else real(name))


def _only(monkeypatch, *names):
    """Needs attention with only the named sources, so the test reads its own rows."""
    from modules import attention
    monkeypatch.setattr(attention, "SOURCES", [getattr(attention, n) for n in names])


def _ack(row, event, why):
    return _client().post("/attention/acknowledge", json={"row": row, "event": event, "why": why})


class TestEveryKindSaysHowItClears:
    def test_clears_covers_every_declared_kind_both_ways(self):
        from modules.attention import CLEAR_WAYS, CLEARS, ROW_KINDS
        assert len(ROW_KINDS) >= 40
        assert set(CLEARS) == set(ROW_KINDS)
        for kind, (ways, words) in CLEARS.items():
            assert ways and set(ways) <= set(CLEAR_WAYS), kind
            assert len(words.split()) >= 3 and not words.endswith("."), kind

    def test_the_kinds_acknowledged_here_say_so(self):
        from modules.attention import ACKNOWLEDGED_HERE, CLEARS
        assert ACKNOWLEDGED_HERE == {("restarts", "unplanned"), ("authorisations", "repeated")}
        for kind in ACKNOWLEDGED_HERE:
            assert "acknowledge" in CLEARS[kind][0], kind
        # Every other kind naming acknowledge does it through its OWN control, named.
        for kind, (ways, words) in CLEARS.items():
            if "acknowledge" in ways and kind not in ACKNOWLEDGED_HERE:
                assert re.search(r"on the (Update page|Remote card)|authorises", words), kind

    def test_a_row_carries_how_it_clears(self):
        from modules.attention import CLEARS, row
        r = row(source="drift", kind="disabled", key="x", what="w", cause="c",
                action={"label": "switch it on"}, level="warning")
        assert r["clears"] == {"ways": list(CLEARS[("drift", "disabled")][0]),
                               "when": "drift checking is switched back on"}
        assert r["acknowledge"] is False

    def test_an_event_row_without_its_event_is_refused(self):
        from modules.attention import RowRefused, row
        with pytest.raises(RowRefused, match="acknowledged per event"):
            row(source="restarts", kind="unplanned", key="k", what="w", cause="c",
                action={"label": "read its reason"}, level="warning")

    def test_both_pages_draw_it(self, store, monkeypatch):
        _restarts_cached(monkeypatch, _read(now=time.time()))
        _only(monkeypatch, "restart_source")
        html = _client().get("/v2/attention").get_data(as_text=True)
        assert "Clears when a person acknowledges it with a reason, or 7 days after the " \
               "restart; History keeps it either way." in html
        # Today's panel, the SHIPPED renderer executed against the real payload.
        import dukpy
        payload = _client().get("/attention").get_json()
        src = open(os.path.join(ROOT, "static", "js", "nmas_attention.js"), encoding="utf-8").read()
        drawn = dukpy.evaljs("var window = {};\n" + src
                             + f"\nwindow.attentionPanelHtml({json.dumps(payload)});")
        assert "Clears when a person acknowledges it with a reason" in drawn


class TestAcknowledgingARestart:
    def test_through_the_real_route_the_row_leaves_and_is_named(self, store, monkeypatch):
        from modules.acknowledgements import read
        _restarts_cached(monkeypatch, _read(now=time.time()))
        _only(monkeypatch, "restart_source")
        before = _client().get("/attention").get_json()
        r = before["rows"][0]
        assert r["acknowledge"] is True and r["event"]
        html = _client().get("/v2/attention").get_data(as_text=True)
        assert 'x-data="acknowledge"' in html and f'data-row="{r["id"]}"' in html
        assert 'data-op="needs-attention"' in html

        got = _ack(r["id"], r["event"], "expected: the backup stalled the host, see C289")
        assert got.status_code == 200, got.get_json()
        assert "acknowledgements" in got.headers.get("X-NMAS-Invalidates", "")
        rec = read()["rows"][0]
        assert rec["by"] == "test-person@example.invalid" and rec["verified"] == "access"
        assert rec["why"] == "expected: the backup stalled the host, see C289"
        assert rec["row"] == r["id"] and rec["event"] == r["event"] and rec["at"]

        after = _client().get("/attention").get_json()
        assert after["rows"] == []
        assert after["acknowledged"][0]["by"] == "test-person@example.invalid"
        page = _client().get("/v2/attention").get_data(as_text=True)
        assert "Acknowledged, so not listed" in page and "see C289" in page

    @pytest.mark.parametrize("why", ["", "ok", "fine ok"])
    def test_a_reason_without_the_shape_of_one_is_refused(self, store, monkeypatch, why):
        from modules.acknowledgements import read
        _restarts_cached(monkeypatch, _read(now=time.time()))
        _only(monkeypatch, "restart_source")
        r = _client().get("/attention").get_json()["rows"][0]
        got = _ack(r["id"], r["event"], why)
        assert got.status_code == 409 and "needs a reason" in got.get_json()["error"]
        assert read()["state"] == "absent"

    def test_a_row_not_on_the_page_another_event_and_a_condition_are_refused(
            self, store, monkeypatch):
        _restarts_cached(monkeypatch, _read(now=time.time()))
        r = _client().get("/attention").get_json()
        row = next(x for x in r["rows"] if x["source"] == "restarts")
        why = "looked at it and it was expected"
        gone = _ack("restarts:Lab|s9|2026-10-01T00:00:00Z", "2026-10-01T00:00:00Z", why)
        assert gone.status_code == 409 and "not on Needs attention now" in gone.get_json()["error"]
        later = _ack(row["id"], "2026-10-03T00:00:00Z", why)
        assert later.status_code == 409 and "a later event" in later.get_json()["error"]
        cond = _ack("drift:Default:disabled", "x", why)
        assert cond.status_code == 409 and "clears when its condition resolves" \
            in cond.get_json()["error"]

    def test_a_new_restart_is_a_new_row(self, store, monkeypatch):
        """The acknowledgement names the restart's time: the device's next restart is
        another event, never covered by it."""
        v = _read(now=time.time())
        _restarts_cached(monkeypatch, v)
        _only(monkeypatch, "restart_source")
        r = _client().get("/attention").get_json()["rows"][0]
        assert _ack(r["id"], r["event"], "expected during the backup window").status_code == 200
        nxt = dict(v["recent_unplanned"][0], at="2026-10-02T09:00:00Z",
                   seen_at="2026-10-02T09:01:00Z", recorded_at="2026-10-02T09:01:30Z")
        v2 = dict(v, recent_unplanned=[nxt] + v["recent_unplanned"])
        _restarts_cached(monkeypatch, v2)
        rows = _client().get("/attention").get_json()["rows"]
        assert [x["event"] for x in rows] == ["2026-10-02T09:00:00Z"]

    def test_history_keeps_it_unexpected_and_says_who_acknowledged(self, store, monkeypatch):
        from modules import device_page
        from modules.nsot import listref
        _restarts_cached(monkeypatch, _read(now=time.time()))
        _only(monkeypatch, "restart_source")
        r = _client().get("/attention").get_json()["rows"][0]
        _ack(r["id"], r["event"], "expected during the backup window")
        monkeypatch.setattr("modules.nsot.repo.golden_history", lambda *a, **k: [])
        monkeypatch.setattr("modules.nsot.hostvars.intent_commits", lambda *a, **k: [])
        monkeypatch.setattr("modules.nsot.receipts.read",
                            lambda *a, **k: {"state": "absent", "rows": []})
        ref = listref.ListRef(name="Lab", slug="lab", data_dir=str(store), repo_dir=str(store),
                              csv_path="")
        ev = [e for e in device_page.history(ref, {"hostname": "s3"})["events"]
              if e["kind"] == "restart"][0]
        assert ev["what"] == "Restarted unexpectedly" and "acknowledged" in ev["marks"]
        assert ev["outcome"] == "crash", "acknowledging never makes it planned"
        assert ev["acknowledged"]["by"] == "test-person@example.invalid"
        assert ev["acknowledged"]["why"] == "expected during the backup window"

    def test_an_unreadable_record_hides_nothing_and_says_so(self, store, monkeypatch):
        _restarts_cached(monkeypatch, _read(now=time.time()))
        _only(monkeypatch, "restart_source")
        r = _client().get("/attention").get_json()["rows"][0]
        (store / "acknowledgements.jsonl").write_text(json.dumps(
            {"row": r["id"], "event": r["event"], "by": "x", "why": "y"}) + "\n{torn")
        got = _client().get("/attention").get_json()
        assert [x["id"] for x in got["rows"]] == [r["id"]]
        assert "Acknowledgements" in got["unreadable"]
        refused = _ack(r["id"], r["event"], "expected during the backup window")
        assert refused.status_code == 409 and "could not be read" in refused.get_json()["error"]


class TestARepeatedAuthorisation:
    def _counts(self, monkeypatch, count, last_at):
        monkeypatch.setattr("modules.nsot.receipts.authorisations_by_device", lambda lst: {
            "state": "ok", "devices": {"r2": {"shutdown": {
                "count": count, "first_at": "2026-10-01T10:00:00Z", "last_at": last_at,
                "last_actor": "a@example.com", "last_reason": "the lab link is down"}}}})

    def test_acknowledged_it_leaves_and_one_more_authorisation_raises_it(self, store, monkeypatch):
        _only(monkeypatch, "authorisation_source")
        self._counts(monkeypatch, 3, "2026-10-02T08:00:00Z")
        r = _client().get("/attention").get_json()["rows"][0]
        assert r["kind"] == "repeated" and r["acknowledge"]
        assert "Clears when" not in r["what"] and r["clears"]["ways"] == ["acknowledge"]
        assert _ack(r["id"], r["event"], "the lab link flaps, tracked in C289").status_code == 200
        assert _client().get("/attention").get_json()["rows"] == []
        self._counts(monkeypatch, 4, "2026-10-02T11:00:00Z")
        again = _client().get("/attention").get_json()["rows"]
        assert len(again) == 1 and again[0]["event"].startswith("4 authorisations")


def test_the_series_reaches_the_case():
    """The capture holds a reboot, so the restart rows above are real ones."""
    assert _expected_boot()[0] > _series()[0][0]


class TestThePlannedWindowAPI:
    """The operator, 2026-10-02: the redeploy script declares its planned-restart window
    "through the product's API, after the typed confirmation and before it touches the
    lab". POST /restarts/planned: the one writer (`record_planned`), the VERIFIED caller as
    who, and the late-window rule."""

    def _post(self, **body):
        return _client().post("/restarts/planned", json=body)

    def test_a_window_is_recorded_as_the_verified_person(self, store):
        from modules.restarts import _data, _read_jsonl
        got = self._post(list="Default", devices=["*"], minutes=45, why="lab redeploy",
                         by="somebody-else@example.com")
        assert got.status_code == 200, got.get_json()
        assert "restarts" in got.headers.get("X-NMAS-Invalidates", "")
        row = _read_jsonl(_data("planned_restarts.jsonl"))["rows"][0]
        assert row["by"] == "test-person@example.invalid", "never a name from the body"
        assert row["via"] == "api" and row["devices"] == ["*"] and row["list"] == "Default"

    def test_a_late_window_is_refused_and_a_correction_accepted(self, store):
        _read(now=time.time())
        boot, _seen = _expected_boot()
        start = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(boot - 600))
        late = self._post(list="Default", devices=["s3"], minutes=11, why="the redeploy",
                          **{"from": start})
        assert late.status_code == 409 and "already seen (s3 at" in late.get_json()["error"]
        ok = self._post(list="Default", devices=["s3"], minutes=11, why="the redeploy",
                        correction="planned before the tool could record it", **{"from": start})
        assert ok.status_code == 200 and ok.get_json()["covered"] == 1

    @pytest.mark.parametrize("body,words", [
        ({"list": "Nope", "devices": ["*"], "minutes": 5, "why": "x y z"}, "no device list"),
        ({"list": "Default", "devices": [], "minutes": 5, "why": "x y z"}, "devices is a list"),
        ({"list": "Default", "devices": ["*"], "minutes": 0, "why": "x y z"}, "minutes is"),
        ({"list": "Default", "devices": ["*"], "minutes": 5, "why": "x y z", "from": "soon"},
         "is not a UTC time"),
    ])
    def test_malformed_requests_are_refused_by_name(self, store, body, words):
        got = self._post(**body)
        assert got.status_code == 400 and words in got.get_json()["error"]

    def test_a_service_needs_the_operation_granted(self):
        from modules.route_gates import GATES
        g = GATES["restarts.planned"]
        assert g.kind == "configure" and g.operation == "planned_restart"


class TestTheToolsOwnReloadRefusesUnrecorded:
    def test_a_window_that_cannot_be_recorded_stops_the_reload(self):
        src = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
        body = src[src.index("def bulk_reload("):]
        body = body[:body.index("outcome = reload_device(conn)")]
        assert 'if not _planned["ok"]:' in body and "raise RuntimeError(\"not reloaded" in body
