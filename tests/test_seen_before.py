"""The fix-it path's first step on a lost telemetry stream's Needs attention row, and its
second step's fallback, with no AI (docs/MERCURY_CHARTER.md, "The fix-it path"; board
recurring-fixes; modules/heal/seen_before.py, attention.stream_fix, templates/v2/_attention.html).
No device, no network.

On real captures, each edit said where it is made:
- **the alerts:** the rules view of 2026-10-26 (tests/fixtures/grafana/alert_history/), which
  holds r7's and r2's real lost-stream instances (subscriptions 101 and 102), each set to the
  state and the time a case needs, parsed by the real reader (`grafana_alerts.parse`) against
  the captured ruler with the telemetry generator's own rules for that device;
- **the alert history:** written by the reader's own writer (`alert_history.from_reader`,
  `record`) from those values, never typed;
- **Mercury's diagnosis:** a real run of the stream runbook on the fleet's real intent (r2,
  tests/test_heal_diagnose_stream.py's), with r7's real receiver captures of 2026-11-10
  (Connected on connection 496 while it was not streaming) and the collector's captured socket
  tables and diagnostics; kept in the step log by its own writer, at the time a case needs;
- **a Mercury operation:** a real re-subscribe on tests/test_heal_resubscribe.py's box;
- **the device's log:** s3's real Loki lines (tests/fixtures/loki/lines_s3.json) as r2's,
  moved in time by one offset so that its configuration line of 04:07:16 lands at 20:59:41 on
  2026-11-08, behind a Loki that applies the query sent (its stages, its window, its device).

The times are the worked example's (board recurring-fixes): lost 2026-11-08 20:04:50, back
21:02:00 (the alert's clear, after the data at 21:01:37), lost again 21:30:50, read 37 hours
later.
"""
import copy
import json
import os
import re
from html import unescape

import pytest

from modules import alert_history as H
from modules import telemetry_rules
from modules.heal import seen_before as SB
from modules.readers import grafana_alerts as G
from tests import test_grafana_reader as GR
from tests.test_alert_history import load as history_load
from tests.test_heal_diagnose import ACTOR, Fleet, fleet, quiet
from tests.test_heal_diagnose_stream import (COLLECTOR, PING6_OK, PING_NONE, V4_RECEIVER,
                                             V6_RECEIVER, answers, at_collector, proc, target)
from tests.test_heal_resubscribe import Clock, Src as OpSrc, run as resubscribe

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE = "grafana-alerts"
NET = "Default"
FIRING, NORMAL = "Alerting (NoData)", "Normal"
SUBS = ("101", "102")
LOST_1, BACK_1, LOST_2 = "2026-11-08T20:04:50Z", "2026-11-08T21:02:00Z", "2026-11-08T21:30:50Z"
NOW = H.epoch("2026-11-10T10:30:50Z")                 # 37 hours after LOST_2
S3_LINES = os.path.join(ROOT, "tests", "fixtures", "loki", "lines_s3.json")
#: s3's configuration line, received 2026-10-09 04:07:16 UTC, lands here.
CHANGED = "2026-11-08T20:59:41Z"
VTY = "Configured from console by <user> on vty0 (192.0.2.1)"
#: The form a console session's own change takes (tests/fixtures/console/, a real console).
CONSOLE = "Configured from console by console"
NO_CAUSE = {"state": "none", "why": "no change on another device is in the heal records"}


def e(text) -> float:
    return float(H.epoch(text))


def iso(epoch) -> str:
    return H.iso(epoch)


# ── The alerts, through the real reader ─────────────────────────────────────────────────────

def ruler_for(device, subs=SUBS):
    """The captured ruler with the telemetry generator's own rule for each of *device*'s
    *subs* (tests/test_no_data_is_the_fault.py's edit, for a device and its subscriptions)."""
    T = telemetry_rules._script()
    ruler = GR.load("ruler")
    hb = next(r for groups in ruler.values() for g in groups for r in g.get("rules") or []
              if r["grafana_alert"]["uid"] == "nmas-hb-r1")
    rules = []
    for sub in subs:
        want = T.rule_for(device, sub, "efwpn8hr7sfeob")
        tel = copy.deepcopy(hb)
        ga = tel["grafana_alert"]
        ga.update(uid=want["uid"], title=want["title"], rule_group=T.GROUP,
                  no_data_state=want["noDataState"], exec_err_state=want["execErrState"])
        ga["data"][0]["datasourceUid"] = want["data"][0]["datasourceUid"]
        ga["data"][0]["model"]["expr"] = want["data"][0]["model"]["expr"]
        ga["data"][0]["relativeTimeRange"] = dict(want["data"][0]["relativeTimeRange"])
        tel["labels"], tel["annotations"] = dict(want["labels"]), dict(want["annotations"])
        rules.append(tel)
    ruler.setdefault("NMAS", []).append({"name": T.GROUP, "interval": "1m", "rules": rules})
    return ruler


def value(states: dict, read_at: float, device="r2", ruled=SUBS) -> dict:
    """The reader's value at *read_at*: the 2026-10-26 rules view with *device*'s real
    instances set to *states* (``{subscription: (state, when it began)}``)."""
    view = history_load("rules_view")
    for sub, (state, at) in states.items():
        inst = GR.rule(view, f"NMAS telemetry stream lost: {device} subscription {sub}")
        inst["alerts"][0]["state"], inst["alerts"][0]["activeAt"] = state, at
    return G.parse(ruler_for(device, ruled), view, [], read_at)


def lost(at=LOST_2, read_at=NOW, device="r2", subs=SUBS, ruled=SUBS) -> dict:
    return value({s: (FIRING, at) for s in subs}, read_at, device, ruled)


def keep(v, now) -> None:
    got = H.record(H.from_reader(v, STORE, [NET], now=now))
    assert got["ok"], got


def past_loss(began=LOST_1, back=BACK_1, device="r2") -> None:
    """One loss in the alert history, as the reader recorded it: both streams lost at *began*
    and normal again at *back*."""
    keep(lost(began, e(began) + 120, device), e(began) + 120)
    keep(value({s: (NORMAL, back) for s in SUBS}, e(back) + 60, device), e(back) + 60)


class Src(SB.Sources):
    """Mercury's own stores as they are in this test's folder; the networks said (the labs'
    inventory answers every network with the same devices), the clock fixed."""

    def __init__(self, now=NOW, nets=None):
        super().__init__(clock=lambda: now)
        self.nets = {"r2": [NET], "r7": [NET]} if nets is None else nets
        self.history_reads = 0

    def networks(self):
        return self.nets

    def history(self):
        self.history_reads += 1
        return super().history()


DEVICES = [{"hostname": h, "ip": f"192.0.2.{n}", "device_type": "cisco_xe"}
           for h, n in (("r1", 11), ("r2", 12), ("r7", 17))]


def make_world(tmp_path, monkeypatch):
    """The three networks' store under *tmp_path*, every network's inventory answering the
    same three routers, a device's reads answered by the test's box, and nothing held from
    another test (the `world` fixture's body, for a caller that is not a test of this module:
    tests/test_grafana_reader.py's test of the reader's own read)."""
    from tests.test_sdn_connections import make_networks

    root = make_networks(tmp_path, monkeypatch)
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda path=None: [dict(d) for d in DEVICES])
    monkeypatch.setattr("modules.commands.run_device_command",
                        lambda conn, c, read_timeout=None: conn.answer(c))
    SB.forget()
    H._LAST_SEEN.clear()
    return root


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def answer(v, src=None, device="r2") -> dict:
    got = SB.context(v, STORE, sources=src or Src())
    assert got["state"] == "read", got
    return got["devices"][device]


# ── Mercury's diagnosis, a real run kept at a chosen time ───────────────────────────────────

R7_101 = open(os.path.join(ROOT, "tests", "fixtures", "diagnose",
                           "r7__show_telemetry_ietf_subscription_101_receiver.txt"),
              encoding="utf-8").read()
R7_102 = R7_101.replace("Subscription ID: 101", "Subscription ID: 102")
SS4 = open(os.path.join(COLLECTOR, "ss_tni_4.txt"), encoding="utf-8").read()
SS6 = open(os.path.join(COLLECTOR, "ss_tni_6.txt"), encoding="utf-8").read()


def diagnosed(folder, finished: float, *, cause=None, receiver=V4_RECEIVER, got_answers=None,
              ss=SS4, tgt=None, **pk) -> dict:
    """A real run of the stream runbook on r2, with r7's receiver captures and the collector's
    tables and diagnostics, kept in the step log as read at *finished* (the edit: its time)."""
    from modules.heal import diagnose as D
    from modules.heal import diagnose_stream as S
    from modules.heal import steplog

    model, intents = fleet(at_collector(receiver))
    ans = dict(got_answers or answers())
    ans[("r2", "show telemetry ietf subscription 101 receiver")] = R7_101
    ans[("r2", "show telemetry ietf subscription 102 receiver")] = R7_102
    folder.mkdir(parents=True, exist_ok=True)
    root = proc(folder, **pk)
    d = D.run(NET, "stream_lost", tgt or target(cause=cause or NO_CAUSE), ACTOR,
              session=Fleet(ans), logs=quiet, model=model, intents=intents, now=finished,
              series=lambda _d, _s: {"state": "absent", "count": 0,
                                     "why": "no sample in the last 90 s"},
              collector=lambda a, p, s: S.read_collector(a, p, s, proc=root,
                                                         ss=lambda _p: (ss, "")),
              record=False)
    d["finished_at"] = iso(finished)
    steplog.record_diagnosis(NET, d, now=finished)
    return d


def test_the_r7_capture_reads_the_same_but_for_its_subscription():
    """r7's 102 receiver capture is its 101 capture with the subscription id (the file)."""
    real = open(os.path.join(ROOT, "tests", "fixtures", "diagnose",
                             "r7__show_telemetry_ietf_subscription_102_receiver.txt"),
                encoding="utf-8").read()
    assert R7_102 == real and "Connection: 496" in real and "State: Connected" in real


# ── The device's log, behind a Loki that applies the query ──────────────────────────────────

def r2_log(change=VTY, others=True) -> list:
    """s3's real lines as r2's, moved by one offset; its configuration line's words *change*
    (None drops that line); *others* False keeps only that line."""
    cap = json.load(open(S3_LINES, encoding="utf-8"))
    rows = [(int(ns), line) for s in cap["answer"]["data"]["result"] for ns, line in s["values"]]
    anchor = next(ns for ns, line in rows if "Oct  9 04:07:16 s3 1267:" in line)
    shift = int(e(CHANGED) * 1e9) - anchor
    out = []
    for ns, line in rows:
        line = line.replace(" s3 ", " r2 ").replace(" s3: ", " r2: ")
        if ns == anchor:
            if change is None:
                continue
            assert VTY in line
            line = line.replace(VTY, change)
        elif not others:
            continue
        out.append((ns + shift, line))
    return out


def _stages(query):
    return re.findall(r'(\|=|\|~|!~)\s*(?:"([^"]*)"|`([^`]*)`)', query)


def _kept(line, query):
    dev = re.search(r'device="([^"]+)"', query)
    if dev and f" {dev.group(1)}: " not in line:
        return False
    for op, quoted, raw in _stages(query):
        pat = quoted if quoted else raw
        if (op == "|=" and pat not in line) or (op == "|~" and not re.search(pat, line)) \
                or (op == "!~" and re.search(pat, line)):
            return False
    return True


class _Resp:
    def __init__(self, body):
        self._b = body

    def json(self):
        return self._b


@pytest.fixture
def loki(monkeypatch):
    """A Loki holding `r2_log`, answering a range query by the query's own device, stages and
    window, and a count by its own window; or failing when told to."""
    from modules.integrations.loki import LokiIntegration

    state = {"corpus": r2_log(), "fail": "", "asked": []}

    def fake_get(self, path, **params):
        state["asked"].append((path, dict(params)))
        if state["fail"]:
            return {"ok": False, "error": state["fail"]}
        q = params["query"]
        if path.endswith("/query"):
            m = re.fullmatch(r"sum\(count_over_time\((.*) \[(\d+)s\]\)\)", q)
            assert m, q
            end = int(params["time"])
            n = sum(1 for ns, line in state["corpus"]
                    if end - int(m.group(2)) * 10 ** 9 <= ns <= end and _kept(line, m.group(1)))
            body = {"status": "success", "data": {"result": [
                {"metric": {}, "value": [end / 1e9, str(n)]}] if n else []}}
            return {"ok": True, "response": _Resp(body)}
        rows = sorted((x for x in state["corpus"] if _kept(x[1], q)
                       and int(params["start"]) <= x[0] <= int(params["end"])), reverse=True)
        rows = rows[:params["limit"]]
        if params.get("direction") == "forward":
            rows = rows[::-1]
        body = {"status": "success", "data": {"result": [
            {"stream": {"job": "network_syslog"},
             "values": [[str(ns), line] for ns, line in rows]}] if rows else []}}
        return {"ok": True, "response": _Resp(body)}

    monkeypatch.setattr(LokiIntegration, "is_configured", lambda self: True)
    monkeypatch.setattr(LokiIntegration, "_get", fake_get)
    return state


# ── Seen before: the match ──────────────────────────────────────────────────────────────────

class TestSeenBefore:
    def test_a_past_loss_of_the_same_device_is_found_with_its_times(self, world):
        past_loss()
        seen = answer(lost())["seen"]
        assert seen["state"] == "match"
        assert (seen["from"], seen["to"]) == (LOST_1, BACK_1)
        assert seen["what"] == "Telemetry subscriptions 101 and 102 were lost for 57 min."
        assert seen["held"] == {"words": "It held 28 min, until this loss began.", "at": "",
                                "tail": ""}
        assert seen["range"] == "7d"
        assert "matched on the device and the symptom (a telemetry stream lost), the " \
               "nearest in time: its cause then is not recorded" in seen["record"]
        assert "1 earlier incident(s) of this kind on r2" in seen["record"]

    def test_it_is_the_same_whether_or_not_this_loss_is_in_the_history_yet(self, world):
        """The reader records a read's transitions after it stores the value: the first read
        of a loss searches a history that does not hold it."""
        past_loss()
        before = answer(lost())["seen"]
        keep(lost(), NOW)
        SB.forget()
        after = answer(lost())["seen"]
        assert before["held"]["words"] == "It held 28 min, until this loss began."
        # All but the record's count of what was searched (two more transitions now).
        assert {k: v for k, v in after.items() if k != "record"} == {
            k: v for k, v in before.items() if k != "record"}

    def test_no_past_loss_is_none_and_says_what_was_searched(self, world):
        seen = answer(lost())["seen"]
        assert seen["state"] == "none"
        assert seen["record"] == ("not found: no earlier lost telemetry on r2 in the alert "
                                  "history holds nothing yet, so nothing earlier can be found")
        keep(lost(), NOW)                              # this loss alone is no earlier one
        SB.forget()
        seen = answer(lost())["seen"]
        assert seen["state"] == "none" and "the alert history kept: " in seen["record"]

    def test_another_devices_loss_is_never_this_devices(self, world):
        past_loss(device="r7")
        assert answer(lost())["seen"]["state"] == "none"
        assert answer(lost(device="r7"), device="r7")["seen"]["state"] == "match"

    def test_a_loss_that_never_cleared_is_no_past_incident(self, world):
        """An episode with no recorded end (the reader missed its resolve) is not one that
        ended: nothing is said to have held."""
        keep(lost(LOST_1, e(LOST_1) + 120), e(LOST_1) + 120)
        assert answer(lost())["seen"]["state"] == "none"

    def test_a_loss_inside_a_planned_restart_is_no_past_incident(self, world):
        """Its alerts were held then, never raised (the window's own rule): the device
        restarting is not a loss a person saw, and nothing is said to have been seen before."""
        from modules import restarts as R
        past_loss()
        assert answer(lost())["seen"]["state"] == "match"
        R.record_planned(["r2"], e(LOST_1) - 120, e(LOST_1) + 900, ACTOR,
                         "a planned reload of the router", "reload", list_name=NET)
        SB.forget()
        seen = answer(lost())["seen"]
        assert seen["state"] == "none"
        assert seen["record"].endswith("; 1 loss(es) that began inside a planned window left "
                                       "out (held then, never raised)")

    def test_a_planned_record_that_cannot_be_read_leaves_nothing_out_and_says_so(self, world):
        from modules import config
        past_loss()
        with open(os.path.join(config.DATA_DIR, "planned_restarts.jsonl"), "w",
                  encoding="utf-8") as fh:
            fh.write("{torn\n")
        seen = answer(lost())["seen"]
        assert seen["state"] == "match"
        assert "; the planned-restart record could not be read (" in seen["record"]

    def test_an_unreadable_alert_history_is_said_never_read_as_never_seen(self, world):
        os.mkdir(H._path())                            # the store is there and is no file
        seen = answer(lost())["seen"]
        assert seen["state"] == "unreadable"
        assert seen["why"].startswith("the alert history could not be read (IsADirectoryError")

    def test_a_later_loss_before_this_one_is_when_it_returned(self, world):
        """Three losses: the first is matched only when it shares this loss's cause; how long
        its end held is to the SECOND loss, at its time, never to this one."""
        past_loss("2026-11-07T10:00:00Z", "2026-11-07T10:20:00Z")
        past_loss()
        groups = SB.incidents_of(H.read()["rows"], STORE, "r2")
        first = groups[0]
        held = SB.held_for(first, groups, e(LOST_2))
        assert held == {"seconds": e(LOST_1) - e("2026-11-07T10:20:00Z"),
                        "returned": e(LOST_1), "now": False}


class TestTheNearestMatch:
    """The same signature first (the device, the symptom, the cause class), then the nearest."""

    def _three(self, tmp_path):
        """An older loss diagnosed half-open, a newer one diagnosed as the device not
        reaching its collector (r2's real ping with no answer)."""
        past_loss("2026-11-07T10:00:00Z", "2026-11-07T10:20:00Z")
        diagnosed(tmp_path / "a", e("2026-11-07T10:10:00Z"))
        past_loss()
        diagnosed(tmp_path / "b", e("2026-11-08T20:45:00Z"), got_answers=answers(ping=PING_NONE))

    def test_the_same_cause_wins_over_a_nearer_loss(self, world, tmp_path):
        self._three(tmp_path)
        diagnosed(tmp_path / "c", NOW - 60)            # this loss: half-open
        seen = answer(lost())["seen"]
        assert (seen["from"], seen["to"]) == ("2026-11-07T10:00:00Z", "2026-11-07T10:20:00Z")
        assert seen["cause"] == ("Mercury's diagnosis then: a session that carries nothing "
                                 "(half-open).")
        assert "matched on the device, the symptom (a telemetry stream lost) and the cause " \
               "(a session that carries nothing (half-open))" in seen["record"]
        assert seen["held"]["words"] == "It held 1 d 9 h: telemetry was lost again at"
        assert seen["held"]["at"] == LOST_1

    def test_with_no_diagnosis_of_this_loss_the_nearest_in_time_is_taken(self, world, tmp_path):
        self._three(tmp_path)
        seen = answer(lost())["seen"]
        assert (seen["from"], seen["to"]) == (LOST_1, BACK_1)
        assert seen["cause"] == "Mercury's diagnosis then: r2 does not reach its collector."
        assert "the nearest in time: this loss's cause is not recorded" in seen["record"]

    def test_a_different_cause_is_the_nearest_and_says_so(self, world, tmp_path):
        past_loss()
        diagnosed(tmp_path / "b", e("2026-11-08T20:45:00Z"), got_answers=answers(ping=PING_NONE))
        diagnosed(tmp_path / "c", NOW - 60)
        seen = answer(lost())["seen"]
        assert seen["state"] == "match" and "its cause then was another (r2 does not reach " \
                                            "its collector)" in seen["record"]

    def test_pick_by_itself(self):
        a, b = {"started": 1.0, "ended": 2.0}, {"started": 5.0, "ended": 6.0}
        assert SB.pick([], "half_open", {}) == (None, "")
        assert SB.pick([a, b], "half_open", {1.0: "half_open", 5.0: "no_session"}) == (
            a, "signature")
        assert SB.pick([a, b], "half_open", {1.0: "no_session"}) == (b, "nearest")
        assert SB.pick([a, b], "", {1.0: "", 5.0: ""}) == (b, "nearest")


# ── How it ended, from what a record shows ──────────────────────────────────────────────────

class TestHowItEnded:
    def test_by_a_mercury_operation_whose_own_verify_read_the_stream_back(self, world):
        past_loss()
        rec = resubscribe(OpSrc(clock=Clock(e("2026-11-08T20:58:00Z"))))
        assert rec["outcome"] == "resubscribed", rec["why"]
        end = answer(lost())["seen"]["ended"]
        assert end == {"how": "fixed", "list": NET, "at": "2026-11-08T20:58:00Z",
                       "words": ("It was fixed by a Mercury operation: re-subscribe r2's "
                                 f"telemetry subscriptions 101 and 102 by {ACTOR}, at"),
                       "tail": " (re-subscribed; the stream is back)."}

    def test_an_operation_that_did_not_read_the_stream_back_is_not_called_the_fix(self, world):
        from tests.test_heal_resubscribe import ABSENT, seq
        past_loss()
        rec = resubscribe(OpSrc(clock=Clock(e("2026-11-08T20:40:00Z")), series=seq([ABSENT])))
        assert rec["outcome"] == "not_back", rec["outcome"]
        end = answer(lost())["seen"]["ended"]
        assert end["how"] == "operation" and end["list"] == NET
        assert end["words"] == ("It cleared after a Mercury operation on r2 (re-subscribe r2's "
                                f"telemetry subscriptions 101 and 102 by {ACTOR}), at")
        assert end["tail"] == ("; its record says \"re-subscribed; the stream did not come "
                               "back\", and no record says that operation cleared it.")

    def test_an_operation_outside_the_loss_or_refused_is_none(self, world, loki):
        past_loss()
        resubscribe(OpSrc(clock=Clock(e(BACK_1) + 600)))             # after it cleared
        refused = resubscribe(OpSrc(clock=Clock(e("2026-11-08T20:40:00Z"))), reason="no")
        assert refused["outcome"] == "refused"
        assert answer(lost())["seen"]["ended"]["how"] == "changed"

    def test_a_console_change_in_the_devices_log_is_said_with_its_time(self, world, loki):
        loki["corpus"] = r2_log(CONSOLE)
        past_loss()
        seen = answer(lost())["seen"]
        assert seen["ended"] == {
            "how": "console", "list": "", "at": CHANGED, "tail": ".",
            "words": ("It cleared with no Mercury operation recorded. A configuration change "
                      "was made on its console at")}
        assert "1 configuration-change line(s) not Mercury's own in r2's log during it; the " \
               "last: made on the console, no account named" in seen["record"]
        # The log was asked for the incident's own window, of this device, and nothing wider.
        asked = [p for path, p in loki["asked"] if path.endswith("query_range")
                 and "CONFIG_I" in p["query"]]
        assert [(p["start"], p["end"]) for p in asked] == [
            (int(e(LOST_1) * 1e9), int(e(BACK_1) * 1e9))]

    @pytest.mark.parametrize("address", ["192.0.2.1", "2001:db8::1"])
    def test_a_change_from_an_address_names_it_ipv4_or_ipv6(self, world, loki, address):
        loki["corpus"] = r2_log(VTY.replace("192.0.2.1", address).replace("<user>", "admin"))
        past_loss()
        end = answer(lost())["seen"]["ended"]
        assert end["how"] == "changed" and end["at"] == CHANGED
        assert end["words"] == ("It cleared with no Mercury operation recorded. A "
                                "configuration change was made on r2 at")
        assert end["tail"] == (f" (the line names the account admin on vty0 from {address}).")

    def test_by_itself_only_when_the_log_holds_lines_from_then_and_no_change(self, world, loki):
        loki["corpus"] = r2_log(None)
        past_loss()
        seen = answer(lost())["seen"]
        assert seen["ended"]["how"] == "itself" and seen["ended"]["at"] == ""
        assert seen["ended"]["words"] == (
            "It cleared by itself: no Mercury operation on r2 is recorded during it, and r2's "
            "log holds no configuration change from then.")
        assert "r2's log holds 6 line(s) from then, none a configuration change" \
            in seen["record"]

    def test_a_log_that_holds_nothing_from_then_cannot_say_nothing_changed(self, world, loki):
        loki["corpus"] = []
        past_loss()
        end = answer(lost())["seen"]["ended"]
        assert end["how"] == "no_operation"
        assert end["words"] == ("It cleared with no Mercury operation recorded; whether r2's "
                                "configuration was changed during it is not known (its log "
                                "holds nothing from then).")

    def test_a_log_that_cannot_be_asked_is_said(self, world, loki):
        loki["fail"] = "HTTP 503"
        past_loss()
        end = answer(lost())["seen"]["ended"]
        assert end["how"] == "no_operation"
        assert end["words"] == ("It cleared with no Mercury operation recorded; whether r2's "
                                "configuration was changed during it could not be read (Loki "
                                "could not be asked: HTTP 503).")

    def test_with_no_log_configured_it_never_says_by_itself(self, world):
        past_loss()
        end = answer(lost())["seen"]["ended"]
        assert end["how"] == "no_operation" and "(Loki is not configured)" in end["words"]

    def test_operation_records_that_cannot_be_read_are_said(self, world, loki):
        from modules.config import get_list_data_dir
        past_loss()
        folder = os.path.join(get_list_data_dir(NET), "privileged")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "torn.json"), "w", encoding="utf-8") as fh:
            fh.write("{not json")
        end = answer(lost())["seen"]["ended"]
        assert end["how"] == "unread"
        assert end["words"] == ("How it ended could not be read: 1 of Default's operation "
                                "records cannot be read (torn.json).")
        assert not [p for path, p in loki["asked"] if "CONFIG_I" in p["query"]], \
            "the log is not asked while a Mercury operation cannot be ruled out"

    def test_a_device_two_networks_hold_reads_no_networks_records(self, world):
        past_loss()
        got = answer(lost(), Src(nets={"r2": [NET, "Branch"]}))
        why = ("2 networks hold a device named r2 (Default and Branch), so which one's "
               "records are its own is not decided")
        assert got["seen"]["ended"]["words"] == f"How it ended could not be read: {why}."
        assert got["diagnosis"]["state"] == "unreadable" and got["diagnosis"]["why"] == why


class TestTheLogsCount:
    def test_it_counts_the_devices_lines_in_the_window_asked(self, world, loki):
        from modules import device_logs
        got = device_logs.lines_held({"hostname": "r2"}, e(LOST_1), e(BACK_1))
        assert got == {"configured": True, "error": "", "count": 7}
        path, params = loki["asked"][-1]
        assert path == "loki/api/v1/query" and params["time"] == int(e(BACK_1) * 1e9)
        assert params["query"].endswith(f" [{int(e(BACK_1) - e(LOST_1))}s]))")
        assert device_logs.lines_held({"hostname": "r7"}, e(LOST_1), e(BACK_1))["count"] == 0

    def test_unasked_is_none_never_zero(self, world, loki):
        from modules import device_logs
        loki["fail"] = "HTTP 503"
        got = device_logs.lines_held({"hostname": "r2"}, e(LOST_1), e(BACK_1))
        assert got["count"] is None and got["error"] == "Loki could not be asked: HTTP 503"
        bad = device_logs.lines_held({"hostname": "r2;x"}, 1.0, 2.0)
        assert bad["count"] is None and "cannot be matched safely" in bad["error"]


# ── Mercury's diagnosis ─────────────────────────────────────────────────────────────────────

HALF_OPEN = ("A session that carries nothing (half-open). r2 reads Connected on connection "
             "496, the collector holds r2's session (192.0.2.6 port 60235), and no data has "
             "arrived on it for 99 minutes.")


class TestMercurysDiagnosis:
    def test_read_the_finding_in_words_with_when_it_was_read(self, world, tmp_path):
        d = diagnosed(tmp_path / "now", NOW - 60, tcp6=False)
        got = answer(lost())["diagnosis"]
        assert got["state"] == "read" and got["words"] == HALF_OPEN
        assert (got["at"], got["by"], got["list"], got["cause"]) == (
            iso(NOW - 60), ACTOR, NET, "half_open")
        assert got["next"].startswith("Re-subscribe r2's streams from the lost stream's row")
        assert got["record"].startswith(f"diagnosis {d['id']} (\"a telemetry stream lost\"), "
                                        f"read {iso(NOW - 60)}; the first of 1 hypotheses, "
                                        "strong")

    def test_the_session_is_named_as_the_record_holds_it_over_ipv6_too(self, world, tmp_path):
        # The IPv6 session's last receive written as the host's measured stale value, as
        # ss_tni_4's device row carries it (the capture's own was 312 ms: a live session).
        stale6 = re.sub(r"lastrcv:\d+", "lastrcv:5966281", SS6, count=1)
        assert stale6 != SS6 and stale6.index("lastrcv:5966281") < stale6.index("::ffff:")
        diagnosed(tmp_path / "v6", NOW - 60, receiver=V6_RECEIVER, ss=stale6, tcp=False,
                  got_answers=answers(ping=None, ping6=PING6_OK))
        got = answer(lost())["diagnosis"]
        assert got["state"] == "read", got
        assert "the collector holds r2's session (2001:db8:4::6 port 41714)" in got["words"]

    def test_absent_none_recorded_for_this_loss(self, world):
        got = answer(lost())["diagnosis"]
        assert got["state"] == "absent" and got["words"] == ""
        assert got["why"] == ("no \"a telemetry stream lost\" diagnosis of r2 is recorded "
                              "since this loss began")

    def test_one_read_before_this_loss_is_never_drawn_as_this_losss(self, world, tmp_path):
        diagnosed(tmp_path / "then", e("2026-11-08T20:45:00Z"), tcp6=False)
        got = answer(lost())["diagnosis"]
        assert got["state"] == "absent" and got["words"] == ""
        assert got["why"].endswith("; the last one, at 2026-11-08T20:45:00Z, was read before "
                                   "it")

    def test_unreadable_is_not_absent(self, world):
        from modules.config import get_list_data_dir
        with open(os.path.join(get_list_data_dir(NET), "heal_steps.jsonl"), "w",
                  encoding="utf-8") as fh:
            fh.write("{torn\n")
        got = answer(lost())["diagnosis"]
        assert got["state"] == "unreadable"
        assert got["why"].startswith("Default's heal step log could not be read (")

    def test_one_asked_for_and_refused_is_not_made(self, world, tmp_path):
        """A subscription intent does not hold: refused at its plan, with nothing read. It
        names no device it read, so it is found by the device it was asked of."""
        d = diagnosed(tmp_path / "no", NOW - 30, tgt=target(cause=NO_CAUSE, subs=("999",)))
        assert d["state"] == "refused" and not d["devices"], d
        got = answer(lost())["diagnosis"]
        assert got["state"] == "not_made" and got["why"] == d["words"]
        assert (got["at"], got["by"], got["words"]) == (iso(NOW - 30), ACTOR, "")
        assert got["why"].startswith("not diagnosed: ")

    def test_every_cause_a_rule_can_find_has_its_words(self):
        from modules.heal.diagnose_stream import STREAM_RULES
        assert set(SB.CAUSE_WORDS) == {r.name for r in STREAM_RULES} - {"stream_flowing"}

    def test_a_cause_with_no_kept_facts_is_said_in_the_diagnosiss_own_claim(self):
        d = {"hypotheses": [{"rule": "collector_unreached",
                             "claim": "r2 does not reach the collector 192.0.2.10 (0 of 5 "
                                      "answered)"}]}
        assert SB.finding_words(d, "r2") == (
            "collector_unreached", "R2 does not reach its collector. R2 does not reach the "
                                   "collector 192.0.2.10 (0 of 5 answered).")
        assert SB.finding_words({"hypotheses": [], "words": "no cause found in what Mercury "
                                                           "reads"}, "r2") == (
            "", "No cause found in what Mercury reads.")


# ── Where it is computed, and its bound ─────────────────────────────────────────────────────

class TestTheBound:
    def test_nothing_is_read_while_no_stream_is_lost(self, world):
        src = Src()
        got = SB.context(value({}, NOW), STORE, sources=src)
        assert got == {"state": "read", "at": iso(NOW), "why": "", "devices": {}}
        assert src.history_reads == 0

    def test_an_answer_is_held_so_the_history_is_not_read_on_every_read(self, world, loki):
        past_loss()
        src = Src()
        first = answer(lost(), src)
        assert answer(lost(), src) == first and src.history_reads == 1
        later = Src(now=NOW + SB.HELD_S + 1)
        assert answer(lost(read_at=NOW + SB.HELD_S + 1), later)["seen"] == first["seen"]
        assert later.history_reads == 1

    def test_an_answer_with_a_store_unread_is_asked_again_sooner(self, world, loki):
        loki["fail"] = "HTTP 503"
        past_loss()
        src = Src()
        assert answer(lost(), src)["seen"]["ended"]["how"] == "no_operation"
        loki["fail"] = ""
        soon = Src(now=NOW + SB.RETRY_S + 1)
        assert answer(lost(), soon)["seen"]["ended"]["how"] == "changed"
        assert SB.RETRY_S < SB.HELD_S

    def test_more_devices_than_the_bound_say_they_were_not_searched(self, world):
        """Two routers lost and a read that searches one (`context`'s *limit*): the one lost
        longest is searched, the other says it was not, naming the number used."""
        v = lost()
        both = lost(at="2026-11-09T00:00:00Z", device="r7")
        v["instances"] += [i for i in both["instances"] if i.get("device") == "r7"
                           and i.get("kind") != "pending" and "telemetry" in i["rule"]]
        got = SB.context(v, STORE, sources=Src(), limit=1)["devices"]
        assert got["r2"]["seen"]["state"] == "none"     # lost longest: searched
        why = ("not searched in this read: 2 devices have lost telemetry at once, and one "
               "read searches the 1 lost longest")
        assert got["r7"]["seen"] == {"state": "unreadable", "why": why, "record": why}
        assert got["r7"]["diagnosis"]["state"] == "unreadable"
        # With no limit given both are within the module's own bound, and both are searched.
        SB.forget()
        whole = SB.context(v, STORE, sources=Src())["devices"]
        assert whole["r2"]["seen"]["state"] == whole["r7"]["seen"]["state"] == "none"

    def test_the_default_bound_is_the_modules_and_its_words_name_it(self, world):
        """Twenty-one devices lost at once (r2's real instances, each copied under another
        name): a read given no limit searches `MAX_DEVICES`, twenty, and the twenty-first
        says the number that was used."""
        v = lost()
        mine = [i for i in v["instances"] if i.get("device") == "r2"
                and i.get("kind") != "pending" and "telemetry stream lost" in i["rule"]]
        assert len(mine) == 2
        for n in range(1, 21):
            for i in mine:
                c = copy.deepcopy(i)
                c["device"] = f"edge{n}"
                c["rule"] = c["rule"].replace(": r2 ", f": edge{n} ")
                c["labels"] = dict(c["labels"], device=f"edge{n}")
                v["instances"].append(c)
        src = Src()
        got = SB.context(v, STORE, sources=src)["devices"]
        assert SB.MAX_DEVICES == 20 and len(got) == 21
        left = [d for d, a in got.items()
                if a["seen"]["why"].startswith("not searched in this read")]
        assert left == ["r2"]                          # the same start: the last by name
        assert got["r2"]["seen"]["why"] == (
            "not searched in this read: 21 devices have lost telemetry at once, and one read "
            "searches the 20 lost longest")
        assert src.history_reads == 1, "one read of the alert history for the whole read"

    def test_a_failure_is_said_and_never_raised_into_the_read(self, world, monkeypatch):
        class Broken(Src):
            def networks(self):
                raise OSError("the inventories are gone")
        got = SB.context(lost(), STORE, sources=Broken())
        assert got["state"] == "unreadable" and got["devices"] == {}
        assert got["why"] == "OSError: the inventories are gone"

    def test_what_the_reader_is_handed_is_this_answer_for_its_store(self, world, monkeypatch):
        """`grafana_alerts.lost_streams`, with nothing of this module stood in: Mercury's own
        sources and clock, the inventory answering the routers in Default alone (so each is
        one network's). It hands the reader what `context` answers for the reader's store.
        The reader's own read keeping it in its value is tests/test_grafana_reader.py's."""
        monkeypatch.setattr(
            "modules.device.load_saved_devices",
            lambda path=None: ([dict(d) for d in DEVICES]
                               if f"{os.sep}default{os.sep}" in str(path) else []))
        past_loss()
        v = lost()
        got = G.lost_streams(v)
        assert got["state"] == "read", got
        seen = got["devices"]["r2"]["seen"]
        assert seen["state"] == "match" and (seen["from"], seen["to"]) == (LOST_1, BACK_1)
        assert seen["ended"]["how"] == "no_operation"   # Default's own records were read
        assert got["devices"]["r2"]["diagnosis"]["state"] == "absent"
        assert got["devices"]["r2"]["diagnosis"]["list"] == NET
        assert got["devices"] == SB.context(v, G.store_name())["devices"]
        assert G.store_name() == STORE == G.READER.name


# ── The row, drawn through the real app ─────────────────────────────────────────────────────

def rows_of(v, value_at=NOW, promise=None, src=None, streams=True):
    from modules import attention
    if streams:
        v["streams"] = SB.context(v, STORE, sources=src or Src())
    cached = {"state": "ok", "doc": {"stale_after_seconds": promise, "last_good": {
        "value_at": iso(value_at), "value": v}}}
    # C2970: the row reads whether its device answers from the reachability reader's stored
    # value; here every router answers (the reader's own read, tests/test_lost_stream_severity.py).
    from tests.test_lost_stream_severity import probed
    return [r for r in attention.grafana_source(cached, reachability=probed())["rows"]
            if r.get("fix")]


def drawn(rows, nets=None) -> str:
    """The list as the real app draws it, as text (tags dropped, spaces folded)."""
    import app as A
    from flask import render_template
    for r in rows:
        r["networks"] = nets or {d: [NET] for d in r["devices"]}
    with A.app.test_request_context("/v2/"):
        page = render_template("v2/_attention.html", a={"rows": rows, "sources": [],
                                                         "badge": {"n": len(rows)}},
                               attention_trigger="nmas:attention from:body")
    return page


def text_of(page: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", page)))


LEAD = ("r2 has sent no telemetry to the collector for 37 hours. Monitoring for r2 is blind "
        "until it does.")
NEEDS = ("Does it need you? Yes: the fix changes r2's configuration, so a person approves it. "
         "If you don't, r2's telemetry stays lost.")


class TestTheRow:
    def test_the_worked_example_opened(self, world, loki, tmp_path):
        """A past loss a console change ended, this loss diagnosed: the lead sentence and Does
        it need you? above the action the row still names; Seen before and Mercury's
        diagnosis, in that order, one level down under the row's Details.

        Premise corrected (the operator, 2026-11-13; the GUI review's item 1, C3449: opened, a
        row is a summary): all four were above What to do; a lost stream's row has no incident
        page, so Seen before and the diagnosis stay in the row, under Details."""
        loki["corpus"] = r2_log(CONSOLE)
        past_loss()
        diagnosed(tmp_path / "now", NOW - 60, tcp6=False)
        (row,) = rows_of(lost())
        assert row["what"] == "r2: 2 telemetry streams lost (101, 102)"
        assert row["action"]["open"] == "resubscribe" and row["action"]["subs"] == ["101", "102"]
        # The times in the viewer's kept zone (the one clock; here UTC), the zone named once.
        from tests.test_local_times import kept_zone
        with kept_zone("UTC"):
            page = drawn([row])
        said = text_of(page)
        seen = re.search(
            r"Seen before on r2 \( Nov 8 20:04( UTC)? to Nov 8 21:02( UTC)? \): Telemetry "
            r"subscriptions 101 and 102 were lost for 57 min\. It cleared with no Mercury "
            r"operation recorded\. A configuration change was made on its console at "
            r"Nov 8 20:59( UTC)? \. It held 28 min, until this loss began\. Open that "
            r"incident", said)
        assert seen, said
        seen = seen.group(0)
        assert seen.count("UTC") <= 1, ("the zone is named once", seen)
        diag = "Mercury's diagnosis: " + HALF_OPEN + " Read "
        for line in (LEAD, seen, NEEDS, diag, "What to do"):
            assert line in said, line
        order = [said.index(x) for x in (LEAD, NEEDS, "What to do", " Details ", seen, diag)]
        assert order == sorted(order), order
        more = page.split('<details class="att-more"', 1)[1].split("</details>", 1)[0]
        assert "Seen before on r2" in more and "Mercury's diagnosis:" in unescape(more)
        assert "Next, as the diagnosis says: Re-subscribe r2's streams" in said
        # The times are the records', drawn in the viewer's zone, their UTC on the hover.
        assert ('<time class="clock" datetime="2026-11-08T20:59:41Z" data-clock="date" '
                'title="2026-11-08 20:59:41 UTC">Nov 8 20:59') in page
        # Open that incident: Monitoring › Alerts › History, this device, a range reaching it.
        assert ('href="/v2/monitoring/alerts/history?device=r2&amp;q=telemetry+stream+lost'
                '&amp;range=7d">Open that incident</a>') in page
        # The action is still the row's, on its line and as its card's slot.
        assert 'href="#resub-r2">Re-subscribe r2\'s telemetry (101, 102)…</a>' in unescape(page)
        assert f'id="resub-r2" hx-get="/v2/device/r2/resubscribe?list={NET}&amp;subs=101,102"' \
            in page
        # No control that does nothing: there is no Explain button yet.
        assert not re.search(r"<button[^>]*>\s*Explain", page)
        # Under Details for the record: what matched, and how each line was measured.
        ops = row["operands"]
        assert ops["seen_before"].startswith("matched on the device and the symptom")
        assert ops["diagnosis"].startswith("diagnosis dg-")
        assert ops["silence_measured"] == (
            f"measured from the alert's onset to the reading at {iso(NOW)}; every lost-stream "
            "rule Grafana holds for r2 is firing (101, 102)")
        assert "seen_before" in said and "silence_measured" in said

    def test_every_field_the_row_carries_is_drawn(self, world, loki, tmp_path):
        import app as A
        from tests import v2_context as V
        past_loss()
        resubscribe(OpSrc(clock=Clock(e("2026-11-08T20:58:00Z"))))
        diagnosed(tmp_path / "now", NOW - 60, tcp6=False)
        (row,) = rows_of(lost())
        assert row["fix"]["seen"]["ended"]["list"] == NET and row["fix"]["seen"]["held"]
        reads = V.template_reads(A.app.jinja_env, "v2/_attention.html")
        carried, undrawn = V.carried({"fix": row["fix"]}, reads)
        assert not undrawn, sorted(undrawn)
        assert {"lead", "needs", "seen", "diagnosis", "ended", "held", "range", "next",
                "more"} <= carried
        page = drawn([row])
        assert (f'href="/v2/device/r2?list={NET}&amp;tab=history">Open that operation\'s '
                'record</a>') in unescape(page).replace("&", "&amp;")

    def test_no_match_draws_no_seen_before_line(self, world, tmp_path):
        (row,) = rows_of(lost())
        assert row["fix"]["seen"] is None
        said = text_of(drawn([row]))
        assert "Seen before" not in said and LEAD in said and NEEDS in said
        assert ("Mercury's diagnosis: not read for this loss: no \"a telemetry stream lost\" "
                "diagnosis of r2 is recorded since this loss began. Self-healing reads it by "
                "itself, where it is on for the device's network, before it tells the team "
                "about a lost stream; no control on this row reads it yet.") in said
        assert "not found: no earlier lost telemetry on r2" in row["operands"]["seen_before"]

    def test_an_unreadable_store_is_said_on_the_row(self, world):
        os.mkdir(H._path())
        from modules.config import get_list_data_dir
        with open(os.path.join(get_list_data_dir(NET), "heal_steps.jsonl"), "w",
                  encoding="utf-8") as fh:
            fh.write("{torn\n")
        (row,) = rows_of(lost())
        said = text_of(drawn([row]))
        assert ("Seen before on r2: couldn't be checked: the alert history could not be read "
                "(IsADirectoryError") in said
        assert "Whether r2 lost telemetry before is not known." in said
        assert "Mercury's diagnosis: couldn't be read: Default's heal step log could not be " \
               "read (" in said

    def test_a_diagnosis_not_made_is_said_as_that(self, world, tmp_path):
        d = diagnosed(tmp_path / "no", NOW - 30, tgt=target(cause=NO_CAUSE, subs=("999",)))
        assert d["state"] == "refused", d["state"]
        said = text_of(drawn(rows_of(lost())))
        assert "Mercury's diagnosis: not made. It was asked for " in said
        # Board E2a: who asked, by display name (the part before the "@").
        assert f"by {ACTOR.split('@')[0]}, and answered: {d['words']}." in said
        assert ACTOR not in said

    def test_a_value_stored_before_the_search_says_not_searched_yet(self, world):
        (row,) = rows_of(lost(), streams=False)
        said = text_of(drawn([row]))
        assert ("Seen before on r2: couldn't be checked: not searched yet: this reading of "
                "Grafana's alerts was stored before Mercury's records were read beside it; "
                "the next read searches them.") in said

    def test_one_of_two_streams_lost_is_not_said_as_no_telemetry(self, world):
        (row,) = rows_of(lost(subs=("101",)))
        assert row["fix"]["lead"] == (
            "r2's telemetry subscription 101 has sent nothing to the collector for 37 hours. "
            "What it carries is missing from monitoring until it does.")
        assert row["operands"]["silence_measured"].endswith(
            "; Grafana holds lost-stream rules for r2's subscriptions 101, 102, and 101 fire")

    def test_the_age_is_the_readings_never_the_requests_clock(self, world):
        """Measured to the reading the row stands on: a reading inside its promise is the
        present; one past it is said as the past, with how old it is."""
        (row,) = rows_of(lost(), promise=10 ** 9)
        assert row["fix"]["lead"] == LEAD
        (row,) = rows_of(lost(), promise=180)
        lead = row["fix"]["lead"]
        assert lead.startswith("When Grafana's alerts were last read, ")
        assert (" ago, r2 had sent no telemetry to the collector for 37 hours. That reading "
                "is older than its promise (3 min), so this may no longer be true.") in lead
        assert "is blind" not in lead

    def test_a_loss_with_no_recorded_start_says_so(self, world):
        from modules import attention
        fix, record = attention.stream_fix(
            {"device": "r2", "subs": ["101", "102"]}, None,
            {"rules": [], "streams": {"state": "read", "devices": {}}}, NOW, None, NOW)
        assert fix["lead"] == ("r2's telemetry subscriptions 101 and 102 have sent nothing to "
                               "the collector; when it stopped is not recorded. What they "
                               "carry is missing from monitoring until they do.")
        assert record["silence_measured"].startswith("the alert records no onset")

    def test_a_device_two_networks_hold_is_offered_nothing_and_says_so(self, world):
        (row,) = rows_of(lost())
        said = text_of(drawn([row], nets={"r2": [NET, "Branch"]}))
        assert ("Does it need you? Yes: r2's telemetry stays lost until a person acts, and no "
                "operation is offered for it here: the reason is under What to do.") in said
        assert "Re-subscribe is not offered: 2 of the networks" in said

    def test_r7s_own_alerts_draw_its_row(self, world):
        """r7's real instances (the capture's): its row, its lead and its lines."""
        past_loss(device="r7")
        (row,) = rows_of(lost(device="r7"))
        assert row["what"] == "r7: 2 telemetry streams lost (101, 102)"
        from tests.test_local_times import kept_zone
        with kept_zone("UTC"):
            said = text_of(drawn([row]))
        assert LEAD.replace("r2", "r7") in said
        assert re.search(r"Seen before on r7 \( Nov 8 20:04( UTC)? to Nov 8 21:02 \):", said), said
        assert "Re-subscribe r7's telemetry (101, 102)…" in said

    def test_another_alerts_row_carries_none_of_it(self, world):
        from modules import attention
        v = lost()
        v["streams"] = SB.context(v, STORE, sources=Src())
        cached = {"state": "ok", "doc": {"last_good": {"value_at": iso(NOW), "value": v}}}
        others = [r for r in attention.grafana_source(cached)["rows"] if not r.get("fix")]
        assert all("seen_before" not in (r.get("operands") or {}) for r in others)
