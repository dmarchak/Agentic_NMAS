"""A planned restart is quiet while it lasts, is recorded when it happens, and its record is
committed (the operator's W2 walk, 2026-10-17: B3, B4 and B5, all from r6's reload).

B3, "the planned-restart window silences nothing": inside r6's declared window Needs attention
raised "r6 is not answering" CRITICAL, then four Grafana alerts (SNMP unreachable, telemetry
101 and 102 no data, the boot's critical syslog), and the header said plain "Not answering".

- declaring a window sets a Grafana silence on its devices' alerts (the `device` label and
  the polled `instance` address), as the person, with the reason, until the window's end plus
  the settle margin; the ids are kept on the window. A fake Grafana on loopback answers as
  Grafana's Alertmanager does; a refusal is said on the result, never dropped;
- a device inside its window is no reachability row: What was checked says "r6 is restarting
  as planned (until ..., by ...)", and the header says so; still down when the window ends,
  it is a row naming the window;
- its Grafana alerts are held while the window and the settle margin last, and raised after;
- a reload that is back ends its window and moves the silence's end to then plus the margin.

B4, "Restarted as planned" missing from r6's History: s3's REAL capture
(`tests/fixtures/heartbeat/s3_reboot.json`) leaves a 720 s gap in the samples around its
reboot, and the reader, reading each minute over a 300 s window, never held a sample from
both sides of it. The fake Prometheus here answers each read as Prometheus would over that
capture, honouring the read's window; its control (one read whose window spans the gap)
finds the fall by `resets`, so the fake is faithful and the miss was the reader's.

B5, the reload's record left uncommitted and the header reading "in sync" beside it: the
record is committed through the one commit path, which publishes, and the header never says
"in sync" with a path no commit holds.
"""

import json
import os
import re
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from modules import restarts as R
from tests.test_device_capture_v2 import lab  # noqa: F401 (the fixture)

OPERATOR = "operator@example.invalid"


# --------------------------------------------------------------------------- a fake Grafana

class _Alertmanager(BaseHTTPRequestHandler):
    """Grafana's Alertmanager silences endpoint, as far as a silence needs: a POST creates a
    silence (or, with an id, moves it) and answers ``{"silenceID"}``; a set *status* refuses."""

    def log_message(self, *_a):                      # quiet
        pass

    def do_POST(self):                               # noqa: N802 (the handler's name)
        srv = self.server
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
        srv.calls.append({"path": self.path, "body": body,
                          "auth": self.headers.get("Authorization", "")})
        if srv.status != 200:
            self._answer(srv.status, {"message": "permissions to create silences"})
            return
        if self.path != "/api/alertmanager/grafana/api/v2/silences":
            self._answer(404, {"message": "not found"})
            return
        sid = body.get("id") or f"sil-{len(srv.silences) + 1}"
        srv.silences[sid] = body
        self._answer(202, {"silenceID": sid})

    _ONE = "/api/alertmanager/grafana/api/v2/silence/"

    def do_GET(self):                                # noqa: N802
        """One silence by its id, as Alertmanager's v2 API answers it (C1089's read)."""
        srv, sid = self.server, self.path[len(self._ONE):]
        if not self.path.startswith(self._ONE) or sid not in srv.silences:
            self._answer(404, {"message": "silence not found"})
            return
        body = srv.silences[sid]
        self._answer(200, dict(body, id=sid, status={
            "state": "expired" if sid in srv.expired else "active"}))

    def do_DELETE(self):                             # noqa: N802
        """Expire one silence by its id (C1089's second write); a set *status* refuses."""
        srv, sid = self.server, self.path[len(self._ONE):]
        srv.calls.append({"path": self.path, "method": "DELETE",
                          "auth": self.headers.get("Authorization", "")})
        if srv.status != 200:
            self._answer(srv.status, {"message": "permissions to expire silences"})
            return
        if not self.path.startswith(self._ONE) or sid not in srv.silences:
            self._answer(404, {"message": "silence not found"})
            return
        srv.expired.add(sid)
        self._answer(200, {})

    def _answer(self, status, doc):
        data = json.dumps(doc).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def grafana(monkeypatch, tmp_path):
    """A Grafana answering on loopback, the window's client pointed at it (the real
    `put_silence`, its real request), and the data folder this test's own."""
    from modules.integrations.grafana import GrafanaIntegration

    monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Alertmanager)
    srv.calls, srv.silences, srv.status, srv.expired = [], {}, 200, set()
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}"

    class Pointed(GrafanaIntegration):
        @property
        def url(self):
            return url

        def _secret(self, key, default=""):
            return "test-token"

    # raising=False: against code without the silence these name nothing, and the tests
    # then fail on what they assert, never on their setup.
    monkeypatch.setattr(R, "_grafana", lambda list_name: Pointed(list_name=""), raising=False)
    monkeypatch.setattr(R, "_inventory_of", lambda list_name: [
        {"hostname": "r6", "ip": "192.0.2.32"}, {"hostname": "r2", "ip": "192.0.2.12"}],
        raising=False)
    yield srv
    srv.shutdown()


def _declare(now, minutes=21, devices=("r6",), list_name="Default", via="reload"):
    return R.record_planned(list(devices), now, now + minutes * 60, OPERATOR,
                            "W2 walk: first reload of r6 through Mercury", via,
                            list_name=list_name)


class TestTheSilence:
    def test_the_silence_reads_the_networks_own_inventory_and_creates_nothing(
            self, tmp_path, monkeypatch):
        """The real `_inventory_of` (the fixture above replaces it): the window's network's
        devices.csv as the real CSV writer writes it, in a lists folder of the test's own; a
        network with no folder answers no devices and is not created by the asking."""
        from modules import config, device

        monkeypatch.setattr(config, "LISTS_DIR", str(tmp_path / "lists"))
        folder = os.path.join(config.LISTS_DIR, config.list_slug("Quiet net"))
        os.makedirs(folder)
        device.write_devices_csv(
            [{"hostname": "q1", "ip": "192.0.2.71", "platform": "cisco_iosxe",
              "device_type": "cisco_xe", "role": "router", "username": "u",
              "password": "enc-a", "secret": "enc-b"}],
            os.path.join(folder, "devices.csv"))
        got = R._inventory_of("Quiet net")
        assert [(d["hostname"], d["ip"]) for d in got] == [("q1", "192.0.2.71")]
        assert R._targets({"list": "Quiet net", "devices": ["*"]}) == (["q1"], ["192.0.2.71"])
        missing = os.path.join(config.LISTS_DIR, config.list_slug("Never made"))
        assert R._inventory_of("Never made") == []
        assert not os.path.exists(missing)

    def test_declaring_a_window_silences_its_devices_alerts_as_the_person(self, grafana):
        now = time.time()
        got = _declare(now)
        assert got["ok"], got
        posts = [c["body"] for c in grafana.calls]
        assert len(posts) == 2, posts
        by_label = {p["matchers"][0]["name"]: p for p in posts}
        assert set(by_label) == {"device", "instance"}
        assert by_label["device"]["matchers"][0]["value"] == "r6"
        assert by_label["instance"]["matchers"][0]["value"] == r"(192\.0\.2\.32)(:[0-9]+)?"
        for p in posts:
            assert p["createdBy"] == OPERATOR
            assert "W2 walk: first reload of r6 through Mercury" in p["comment"]
            assert p["endsAt"] == R._iso(now + 21 * 60 + R.SETTLE_SECONDS)
            assert p["matchers"][0]["isRegex"] is True and "id" not in p
        assert all(c["auth"] == "Bearer test-token" for c in grafana.calls)
        # The ids are on the window as it is recorded, and the result says so.
        (row,) = R.planned_rows()
        assert row["silence"]["state"] == "set"
        assert sorted(s["id"] for s in row["silence"]["silences"]) == ["sil-1", "sil-2"]
        assert got["silence_words"].startswith("Grafana's alerts on its devices are silenced "
                                               "until " + R._iso(now + 21 * 60
                                                                 + R.SETTLE_SECONDS))

    def test_a_silence_grafana_refuses_is_said_on_the_window(self, grafana):
        grafana.status = 403
        got = _declare(time.time())
        assert got["ok"], "the window is recorded whether or not Grafana took the silence"
        assert got["silence"]["state"] == "failed"
        assert got["silence_words"].startswith("Grafana's alerts are NOT silenced: ")
        assert "HTTP 403" in got["silence_words"]
        assert R.planned_rows()[0]["silence"]["state"] == "failed"

    def test_no_grafana_sets_nothing_and_says_so(self, grafana, monkeypatch):
        from modules.integrations.grafana import GrafanaIntegration

        class Unset(GrafanaIntegration):
            @property
            def url(self):
                return ""
        monkeypatch.setattr(R, "_grafana", lambda list_name: Unset(), raising=False)
        got = _declare(time.time())
        assert got["ok"] and grafana.calls == []
        assert got["silence"]["state"] == "not_configured"
        assert "Grafana is not configured" in got["silence_words"]

    def test_the_write_refuses_any_other_silence_before_sending(self, grafana):
        client = R._grafana("Default")
        bad = client.put_silence(matchers=[{"name": "alertname", "value": "x"}],
                                 starts_at="2026-10-17T00:00:00Z",
                                 ends_at="2026-10-17T01:00:00Z", created_by=OPERATOR,
                                 comment="why")
        assert not bad["ok"] and "matches only device, instance" in bad["error"]
        nobody = client.put_silence(matchers=[{"name": "device", "value": "r6"}],
                                    starts_at="2026-10-17T00:00:00Z",
                                    ends_at="2026-10-17T01:00:00Z", created_by=" ",
                                    comment="why")
        assert not nobody["ok"] and "no person" in nobody["error"]
        assert grafana.calls == [], "a refused silence reached Grafana"


# --------------------------------------------------------------------------- Needs attention

def _reach(*devices):
    return {"state": "ok", "why": "", "doc": {"stale_after_seconds": 150, "last_good": {
        "value": {"devices": {d["address"]: d for d in devices},
                  "counts": {"answering": 0, "not_answering": len(devices)}},
        "value_at": R._iso(time.time())}}}


def _down(name="r6", ip="192.0.2.32", since=None, list_name="Default"):
    return {"address": ip, "hostname": name, "list": list_name, "answering": False,
            "consecutive_misses": 8, "threshold": 3,
            "since": R._iso(since or time.time() - 60),
            "claim": "answered neither ICMP nor TCP 22 within 2 s each",
            "last_result": "missed", "checked_at": R._iso(time.time())}


class TestNeedsAttention:
    def test_inside_its_window_it_is_restarting_as_planned_and_no_row(self, grafana):
        from modules import attention as A
        now = time.time()
        _declare(now - 120)
        res = A.reachability_source(cached=_reach(_down(since=now - 60)))
        assert res["rows"] == [], res["rows"]
        until = R._iso(now - 120 + 21 * 60)
        assert (f"r6 is restarting as planned (until {until}, by {OPERATOR}): open its reload "
                "on its page") in res["checked"]

    def test_the_control_with_no_window_it_is_the_critical_row(self, grafana):
        from modules import attention as A
        (row,) = A.reachability_source(cached=_reach(_down()))["rows"]
        assert row["level"] == "danger" and row["what"] == "r6 is not answering"

    def test_still_down_when_its_window_ends_it_is_critical_naming_the_window(self, grafana):
        from modules import attention as A
        now = time.time()
        _declare(now - 30 * 60, minutes=20)              # ended ten minutes ago
        (row,) = A.reachability_source(cached=_reach(_down(since=now - 25 * 60)))["rows"]
        assert row["level"] == "danger"
        assert (f"its planned-restart window (by {OPERATOR}) ended at "
                f"{R._iso(now - 30 * 60 + 20 * 60)} and it is still not answering") \
            in row["cause"]

    def test_the_header_says_restarting_as_planned(self, grafana, monkeypatch):
        from modules import device_page
        now = time.time()
        _declare(now - 120)
        stored = _reach(_down())["doc"]["last_good"]
        monkeypatch.setattr(device_page, "_cached", lambda reader, list_name="": (
            stored["value"], stored["value_at"], ""))
        got = device_page.answering({"hostname": "r6", "ip": "192.0.2.32"})
        assert got["state"] == "planned", got
        assert got["text"] == (f"Restarting as planned (until {R._iso(now - 120 + 21 * 60)}, "
                               f"by {OPERATOR})")

    @pytest.fixture
    def alerting(self, monkeypatch):
        """One alert of the captured rules view made to fire: a rule naming its device by
        LABEL (r6's heartbeat, as telemetry and the syslog rule do) or by the polled ADDRESS
        (the SNMP rule's `instance`, r1's here: the capture holds none for r6)."""
        from modules import attention as A
        from modules import device
        from tests.test_grafana_reader import INVENTORY, cached, load, parse, rule
        monkeypatch.setattr(device, "load_saved_devices", lambda *a, **k: list(INVENTORY))
        monkeypatch.setattr(device, "get_device_lists",
                            lambda: [{"name": "Default", "filename": "default"}])

        def fire(title, match):
            view = load("rules_view")
            inst = next(a for a in rule(view, title)["alerts"] if match(a["labels"]))
            inst["state"], inst["activeAt"] = "Alerting", R._iso(time.time() - 300)
            return A.grafana_source(cached=cached(parse(view)))
        return fire

    def _r6(self, alerting):
        return alerting("NMAS heartbeat missing: r6", lambda labels: True)

    def test_its_alerts_are_held_while_the_window_and_the_margin_last(self, grafana,
                                                                    alerting):
        now = time.time()
        _declare(now - 30 * 60, minutes=20)          # ended 10 min ago, inside the margin
        res = self._r6(alerting)
        assert res["rows"] == [], res["rows"]
        assert ("restarting as planned, not raised: 1 alert(s) (NMAS heartbeat missing: r6) "
                "on r6: r6 is restarting as planned") in res["checked"]
        assert f"its alerts held {R.SETTLE_SECONDS // 60} min after it to settle" in res["checked"]

    def test_an_alert_by_its_polled_address_is_held_too(self, grafana, alerting):
        _declare(time.time() - 60, devices=("r1",))
        res = alerting("Device unreachable (SNMP)",
                       lambda labels: labels.get("instance") == "10.255.1.11")
        assert res["rows"] == [] and "(Device unreachable (SNMP)) on r1" in res["checked"]

    def test_the_control_after_the_margin_the_alert_is_a_row(self, grafana, alerting):
        _declare(time.time() - 3 * 3600, minutes=20)
        (row,) = self._r6(alerting)["rows"]
        assert row["devices"] == ["r6"]

    def test_the_control_another_device_s_window_holds_nothing(self, grafana, alerting):
        _declare(time.time() - 60, devices=("r2",))
        (row,) = self._r6(alerting)["rows"]
        assert row["devices"] == ["r6"]


# --------------------------------------------------------------------------- the reload's end

@pytest.fixture
def run_lab(grafana, lab, monkeypatch):  # noqa: F811
    """test_reload_v2's run, its device-facing parts replaced, beside the fake Grafana."""
    from modules.nsot import reload_op
    sent = []
    monkeypatch.setattr(reload_op, "_device", lambda l, h: {"hostname": "r2",
                                                            "ip": "192.0.2.12",
                                                            "platform": "cisco_iosxe"})
    return {**lab, "sent": sent, "grafana": grafana,
            "reloader": lambda d: sent.append("reload") or {"ok": True, "outcome": "reloading",
                                                            "detail": "dropped after 2 s"},
            "back": lambda ip, bound: {"ok": True, "after_s": 452, "attempts": 46}}


def _run(run_lab, **kw):
    from modules.nsot import reload_op
    from tests.test_reload_v2 import _fp, _reads
    return reload_op.run("Lab", "r2", actor=OPERATOR, fingerprint=_fp(run_lab),
                         reason="W2 walk: first reload of r2 through Mercury",
                         reader=lambda d: _reads(run_lab), reloader=run_lab["reloader"],
                         wait=run_lab["back"], **kw)


class TestTheReloadEndsItsWindow:
    def test_back_it_ends_the_window_and_moves_the_silence(self, run_lab):
        before = time.time()
        out = _run(run_lab)
        after = time.time()
        assert out["ok"], out
        window = next(s for s in out["steps"] if s["step"] == "window")
        assert "Grafana's alerts on its devices are silenced until" in window["detail"]
        moves = [c["body"] for c in run_lab["grafana"].calls]
        created, moved = moves[:2], moves[2:]
        assert len(created) == 2 and len(moved) == 2, moves
        assert {m["id"] for m in moved} == {"sil-1", "sil-2"}
        for m in moved:
            ends = R._epoch(m["endsAt"])
            assert before + R.SETTLE_SECONDS - 1 <= ends <= after + R.SETTLE_SECONDS + 1
        (p,) = R.planned_rows()
        assert R.window_end(p, R.ends()) <= after, "the window was not ended"
        # Ended: a fall now is raised at once; its alerts are held only for the margin.
        assert R.holding("r2", "Lab", after + 5) is None
        assert R.holding("r2", "Lab", after + 5, margin=R.SETTLE_SECONDS) is not None
        assert "window ended" in out["window"]["end_words"]

    def test_the_control_not_back_keeps_its_window_and_silence(self, run_lab):
        out = _run_not_back(run_lab)
        assert out["outcome"] == "not_back"
        assert len(run_lab["grafana"].calls) == 2, "a silence moved for a reload not back"
        (p,) = R.planned_rows()
        assert R.window_end(p, R.ends()) == R._epoch(p["until"])


class TestMercurysGrafanaWritesAreRecorded:
    """C1089 (the operator, 2026-10-17): every write Mercury sends to Grafana is recorded,
    whoever it was for and whatever Grafana answered, and History draws it under "Grafana
    writes"; a silence can be read back by its id and expired by it, as a person with a
    reason."""

    class Ref:
        name = "Default"

    def _drawn(self, network="Default"):
        from modules import history_sources as H
        ref = type("Ref", (), {"name": network})
        return H.grafana_writes({"ref": ref, "limit": 50, "device": "", "since": None})

    def test_a_windows_silences_are_recorded_as_its_person_and_drawn(self, grafana):
        from modules import grafana_writes as gw
        _declare(time.time())
        rows = gw.entries()["rows"]
        assert [r["action"] for r in rows] == ["silence_set", "silence_set"], rows
        assert all(r["by"] == OPERATOR and r["ok"] and r["silence_id"] for r in rows)
        assert all(r["via"] == "planned-restart window (reload)" for r in rows)
        assert sorted(r["matchers"][0] for r in rows) == [
            r"device=~r6", r"instance=~(192\.0\.2\.32)(:[0-9]+)?"]
        events = self._drawn()["events"]
        assert len(events) == 2 and all(e["kind"] == "grafana"
                                        and e["who"].startswith(OPERATOR)
                                        and e["outcome"] == "done" for e in events), events
        assert all(e["what"].startswith("Grafana silence set: ") for e in events)

    def test_a_refused_write_is_recorded_and_drawn_as_failed(self, grafana):
        from modules import grafana_writes as gw
        grafana.status = 403
        _declare(time.time())
        rows = gw.entries()["rows"]
        assert len(rows) == 2 and not any(r["ok"] for r in rows), rows
        assert all("HTTP 403" in r["error"] for r in rows)
        events = self._drawn()["events"]
        assert all(e["outcome"] == "failed" and e["what"].startswith("Grafana silence NOT set:")
                   for e in events), events

    def test_set_read_back_and_expired_by_its_id_each_recorded(self, grafana):
        """The C1089 probe's shape: a silence on a label value no alert carries, read back,
        expired, read again."""
        from modules import grafana_writes as gw
        client = R._grafana("")
        now = time.time()
        made = client.put_silence(
            matchers=[{"name": "device", "value": "nmas-probe-matches-no-device",
                       "isRegex": False}],
            starts_at=R._iso(now), ends_at=R._iso(now + 600), created_by=OPERATOR,
            comment="the token's write permission, checked", verified="instructed",
            via="the C1089 check")
        assert made["ok"], made
        read = client.get_silence(made["id"])
        assert read["ok"] and read["silence"]["state"] == "active", read
        assert read["silence"]["matchers"] == ["device=nmas-probe-matches-no-device"]
        gone = client.expire_silence(made["id"], by=OPERATOR, reason="the check is done",
                                     verified="instructed", via="the C1089 check")
        assert gone["ok"], gone
        assert client.get_silence(made["id"])["silence"]["state"] == "expired"
        rows = gw.entries()["rows"]
        assert [(r["action"], r["silence_id"], r["by"], r["ok"]) for r in rows] == [
            ("silence_set", made["id"], OPERATOR, True),
            ("silence_expired", made["id"], OPERATOR, True)]
        whats = [e["what"] for e in self._drawn("Any network")["events"]]
        assert whats[0].startswith("Grafana silence expired: ") and \
            whats[1].startswith("Grafana silence set: device=nmas-probe-matches-no-device"), \
            "the installation's own writes are drawn on every network"

    def test_an_expire_without_a_person_a_reason_or_an_id_sends_nothing(self, grafana):
        from modules import grafana_writes as gw
        client = R._grafana("")
        for kw in ({"by": "", "reason": "r"}, {"by": OPERATOR, "reason": " "}):
            got = client.expire_silence("sil-1", **kw)
            assert got["error"].startswith("refused before sending"), got
        got = client.expire_silence("../silences", by=OPERATOR, reason="r")
        assert got["error"].startswith("refused before sending"), got
        assert grafana.calls == [] and gw.entries()["rows"] == []

    def test_a_refused_expire_is_recorded_as_not_done(self, grafana):
        from modules import grafana_writes as gw
        grafana.status = 403
        got = R._grafana("").expire_silence("sil-9", by=OPERATOR, reason="the check is done")
        assert not got["ok"] and "HTTP 403" in got["error"]
        (row,) = gw.entries()["rows"]
        assert row["action"] == "silence_expired" and not row["ok"] and row["by"] == OPERATOR

    def test_a_window_of_another_network_is_not_drawn_here(self, grafana, monkeypatch):
        from modules import grafana_writes as gw
        gw.record(action="silence_set", by=OPERATOR, ok=True, silence_id="s-x",
                  network="Branch")
        assert self._drawn("Default")["events"] == []
        assert len(self._drawn("Branch")["events"]) == 1


class TestASilenceThatFailsNeverStopsTheReload:
    """The operator, 2026-10-17: if the silence cannot be set at a reload (the token revoked,
    Grafana down, its role lowered), the reload still goes ahead, and its card and its record
    say plainly that the alerts were not silenced and why. Never green over it."""

    def _down(self, monkeypatch):
        """Grafana not answering: the window's client pointed at a loopback port nothing
        listens on."""
        import socket

        from modules.integrations.grafana import GrafanaIntegration
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        url = f"http://127.0.0.1:{sock.getsockname()[1]}"
        sock.close()

        class Down(GrafanaIntegration):
            @property
            def url(self):
                return url

            def _secret(self, key, default=""):
                return "test-token"
        monkeypatch.setattr(R, "_grafana", lambda list_name: Down(list_name=""))

    @pytest.mark.parametrize("failure, why", [("refused", "HTTP 403"),
                                              ("down", "Grafana did not answer")])
    def test_the_reload_runs_and_its_card_and_record_say_the_alerts_were_not_silenced(
            self, run_lab, monkeypatch, failure, why):
        import flask

        import app as A
        from modules import device_actions
        from modules.nsot import listref, reload_op
        if failure == "refused":
            run_lab["grafana"].status = 403
        else:
            self._down(monkeypatch)
        out = _run(run_lab)
        assert run_lab["sent"] == ["reload"], "the reload did not go ahead"
        assert out["outcome"] == "reloaded", out
        # The record: the reload's row keeps the window's silence, failed, and why.
        rows = [json.loads(line) for line in open(reload_op.records_path(
            reload_op._repo("Lab")), encoding="utf-8")]
        assert rows[-1]["window"]["silence"]["state"] == "failed", rows[-1]
        assert rows[-1]["window"]["silence_words"].startswith(
            "Grafana's alerts are NOT silenced: ") and why in rows[-1]["window"]["silence_words"]
        # The card: never green over it, and it says so in words, with why.
        card = device_actions.reload_job_card(
            listref.resolve("Lab"), "r2", "job-1",
            {"state": "done", "kind": "reload", "payload": out})
        assert card["level"] == "warn", card
        with A.app.test_request_context("/v2/device/r2"):
            html = flask.render_template("v2/_reload.html", c=card)
        notice = re.search(r'<p class="notice notice-warn"[^>]*>.*?</p>', html, re.S)
        assert notice, html
        import html as html_mod
        words = html_mod.unescape(re.sub(r"<[^>]+>", "", notice.group(0)))
        assert "Grafana's alerts were NOT silenced during this reload" in words, words
        assert why in words, words

    def test_the_control_a_silence_set_keeps_the_card_green_and_says_nothing(self, run_lab):
        from modules import device_actions
        from modules.nsot import listref
        out = _run(run_lab)
        card = device_actions.reload_job_card(
            listref.resolve("Lab"), "r2", "job-1",
            {"state": "done", "kind": "reload", "payload": out})
        assert card["level"] == "ok" and not card.get("alerts"), card


def _run_not_back(run_lab):
    from modules.nsot import reload_op
    from tests.test_reload_v2 import _fp, _reads
    return reload_op.run("Lab", "r2", actor=OPERATOR, fingerprint=_fp(run_lab),
                         reason="W2 walk: first reload of r2 through Mercury",
                         reader=lambda d: _reads(run_lab), reloader=run_lab["reloader"],
                         wait=lambda ip, b: {"ok": False, "after_s": b, "attempts": 9,
                                             "detail": f"it did not answer within {b} s"})


# --------------------------------------------------------------------------- B4: the reader

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "heartbeat", "s3_reboot.json")


def _capture(start):
    """s3's REAL sysUpTime around its reboot, moved so its last sample before the gap falls
    at *start* (the shape, the values and the 720 s gap untouched)."""
    values = json.load(open(FIX))["sysUpTime"][0]["values"]
    i = next(i for i in range(1, len(values)) if float(values[i][1]) < float(values[i - 1][1]))
    shift = start - values[i - 1][0]
    return [[t + shift, float(u)] for t, u in values], i


def _prometheus(samples, newest=True):
    """Prometheus over *samples*, answering as it does: a range selector ``[w]`` evaluated at
    *now* holds the samples in ``(now - w, now]`` (a device not scraped has none), `resets`
    counts the falls among them, and the newest-sample query looks back 150 s
    (`LATEST_SECONDS`). *newest* False answers only what the reader asked before B4."""
    def source(window, now):
        held = [p for p in samples if now - window < p[0] <= now]
        falls = sum(1 for a, b in zip(held, held[1:]) if b[1] < a[1])
        recent = [p for p in samples if now - 150 < p[0] <= now]
        found = (True, {"s3": [held]} if falls else {})
        return found + ({"s3": list(recent[-1])} if recent else {},) if newest else found
    return source


def _reads_through(samples, gap_at, until, previous=None):
    from modules.readers import restarts as reader
    from modules.restarts import reason_from

    dev = {"hostname": "s3", "ip": "192.0.2.13"}
    # The fake answers what this version of the reader asks: the newest samples only when its
    # Prometheus read asks for them (`LATEST_SECONDS`).
    asks_newest = hasattr(reader, "LATEST_SECONDS")
    t, out, previous = gap_at - 300, [], previous
    while t <= until:
        previous = reader.read(previous=previous or {}, clock=lambda t=t: t,
                               source=_prometheus(samples, newest=asks_newest),
                               devices=lambda: {"s3": ("Lab", dev)},
                               reason=lambda d: dict(reason_from(
                                   "System returned to ROM by reload\n"
                                   "Last reload reason: Reload Command\n"), error=""))
        out += previous["new"]
        t += 60
    return out


class TestARestartLongerThanTheReadWindow:
    def test_the_capture_s_gap_is_longer_than_a_read_s_window(self):
        samples, i = _capture(1_000_000)
        assert samples[i][0] - samples[i - 1][0] == 720 > 300

    def test_a_planned_reload_is_recorded_and_drawn_as_restarted_as_planned(
            self, tmp_path, monkeypatch):
        from modules import device_page
        from modules.nsot import listref

        monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
        monkeypatch.setattr(R, "_grafana", lambda list_name: type(
            "Unset", (), {"is_configured": lambda self: False})(), raising=False)
        start = time.time() + 120                      # the reload, a moment from now
        samples, i = _capture(start)
        got = R.record_planned(["s3"], start - 30, samples[i][0] + 300, OPERATOR,
                               "a reload through Mercury", "reload", list_name="Lab")
        assert got["ok"], got
        new = _reads_through(samples, start, samples[i][0] + 600)
        assert len(new) == 1, new
        (row,) = new
        assert row["planned"] is True and row["planned_by"] == OPERATOR
        assert row["found_by"] == "sysUpTime fell between two reads"
        assert samples[i - 1][0] <= R._epoch(row["at"]) <= samples[i][0]
        # Drawn on the device's History, by the History reader's real path.
        monkeypatch.setattr("modules.nsot.repo.golden_history", lambda *a, **k: [])
        monkeypatch.setattr("modules.nsot.hostvars.intent_commits", lambda *a, **k: [])
        monkeypatch.setattr("modules.nsot.receipts.read",
                            lambda *a, **k: {"state": "absent", "rows": []})
        ref = listref.ListRef(name="Lab", slug="lab", data_dir=str(tmp_path),
                              repo_dir=str(tmp_path), csv_path="")
        h = device_page.history(ref, {"hostname": "s3"})
        (ev,) = [e for e in h["events"] if e["kind"] == "restart"]
        assert ev["what"] == "Restarted as planned" and ev["who"] == OPERATOR

    def test_the_control_one_read_spanning_the_gap_finds_it_by_resets(self, tmp_path,
                                                                     monkeypatch):
        """The fake is faithful: a window that holds both sides of the gap finds the fall by
        `resets`, as Prometheus would; the per-minute reads missed it for their window."""
        from modules.readers import restarts as reader
        from modules.restarts import reason_from

        monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
        samples, i = _capture(time.time() - 3600)
        v = reader.read(previous={}, clock=lambda: samples[i][0] + 60,
                        source=_prometheus(samples, newest=False),
                        devices=lambda: {"s3": ("Lab", {"hostname": "s3"})},
                        reason=lambda d: dict(reason_from(""), error="x"))
        assert [r["found_by"] for r in v["new"]] == ["sysUpTime reset"]

    def test_the_newest_sample_is_asked_and_read_per_device(self, monkeypatch):
        from modules.readers import restarts as reader

        asked = []

        class Answer:
            def __init__(self, doc):
                self.doc = doc

            def json(self):
                return self.doc

        class Prom:
            def __init__(self, *a, **k):
                pass

            def is_configured(self):
                return True

            def _get(self, path, **params):
                asked.append(params.get("query"))
                if params.get("query", "").startswith("sysUpTime["):
                    return {"ok": True, "response": Answer({"data": {"result": [
                        {"metric": {"device": "r6"}, "values": [[100, "500"], [160, "560"]]},
                        {"metric": {"device": "r6"}, "values": [[130, "530"]]},
                        {"metric": {"device": "bad name"}, "values": [[160, "1"]]}]}})}
                return {"ok": True, "response": Answer({"data": {"result": []}})}
        monkeypatch.setattr("modules.integrations.prometheus.PrometheusIntegration", Prom)
        got = reader.prometheus_series(300, 200)
        assert len(got) == 3, f"no newest samples in the answer: {got}"
        ok, series, latest = got
        assert ok and series == {} and latest == {"r6": [160.0, 560.0]}
        assert asked[0] == f"sysUpTime[{reader.LATEST_SECONDS}s]"


# --------------------------------------------------------------------------- B5: committed

class TestTheReloadRecordIsCommitted:
    def test_the_record_is_committed_through_the_one_path_and_published(self, run_lab,
                                                                        monkeypatch):
        from modules.nsot import repo as Repo
        published = []
        real = Repo.publish
        monkeypatch.setattr(Repo, "publish", lambda repo, sha, **k: published.append(sha)
                            or real(repo, sha, **k))
        out = _run(run_lab)
        assert out["record"]["ok"] and out["record"]["commit"], out["record"]
        repo = run_lab["repo"]

        def git(*a):
            return subprocess.run(["git", "-C", repo, *a], capture_output=True,
                                  text=True).stdout
        assert git("status", "--porcelain", "--", ".nsot/reloads.jsonl") == ""
        assert git("log", "-1", "--format=%H").strip() == out["record"]["commit"]
        body = git("log", "-1", "--format=%B")
        assert body.startswith("reload: r2 reloaded and verified")
        assert f"Actor: {OPERATOR}" in body and "Source: reload" in body
        assert published == [out["record"]["commit"]]
        assert git("show", "--name-only", "--format=", "HEAD").split() == [".nsot/reloads.jsonl"]

    def test_history_draws_it_once_as_its_reload(self, run_lab):
        from modules import history_sources as H
        from modules.nsot import listref
        _run(run_lab)
        ref = listref.ListRef(name="Lab", slug="lab", data_dir=os.path.dirname(run_lab["repo"]),
                              repo_dir=run_lab["repo"], csv_path="")
        events = H.timeline(ref)["events"]
        assert [e["kind"] for e in events if "reload" in (e.get("what") or "").lower()] \
            == ["reload"], [(e["kind"], e["what"]) for e in events]


class TestTheHeader:
    PUB = {"state": "in_sync", "remote": "example/nsot", "branch": "main", "head": "a" * 40,
           "remote_head": "a" * 40, "asked_at": time.time()}

    def test_uncommitted_paths_are_never_in_sync(self):
        from modules.readers import remote_publication as RP
        d = RP.describe(self.PUB, uncommitted=1)
        assert d["state"] == "uncommitted" and d["level"] == "warning"
        assert d["clause"] == ("its commits are on example/nsot, and what is not committed is "
                               "on this host only")

    def test_the_control_nothing_uncommitted_is_in_sync(self):
        from modules.readers import remote_publication as RP
        assert RP.describe(self.PUB)["state"] == "in_sync"

    def test_the_header_draws_not_committed_beside_the_path(self, monkeypatch, tmp_path):
        from flask import render_template_string

        import app as A
        from routes import v2
        monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path))
        repo = tmp_path / "config_repo"
        repo.mkdir()
        for args in (["init", "-q", "-b", "main"],
                     ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
                      "--allow-empty", "-m", "a"]):
            subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
        (repo / ".nsot").mkdir()
        (repo / ".nsot" / "reloads.jsonl").write_text("{}\n")
        monkeypatch.setattr("modules.readers.remote_publication.status_for",
                            lambda name: dict(self.PUB))
        ref = type("Ref", (), {"name": "Lab", "repo_dir": str(repo)})()
        out = v2._history_remote(ref)
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        src = open(os.path.join(root, "templates", "v2", "_history_remote.html"),
                   encoding="utf-8").read()
        with A.app.test_request_context("/"):
            html = render_template_string(src, remote=out)
        assert "not committed" in html and ".nsot/" in html
        assert "in sync" not in html, "the header reads in sync beside an uncommitted path"
