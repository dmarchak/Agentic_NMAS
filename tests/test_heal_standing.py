"""A heal incident that stands on its decision while its cause stands (C2813), and a can't-fix
whose symptom cleared by itself (C2825), each case reproduced from H11's walks (2026-11-08,
~/Documents/nmas-reports/2026-11-08T2057Z-H11-walk-summary.md; `modules/heal/incidents.py`,
`decide.py`, `detect.py`, `triggers.py`, `modules/heal_notice.py`, `modules/drift_check.py`).
No device, no network, a fake clock; the decision's sources are tests/test_heal_decide.py's
`Fake`, the fold's world tests/test_heal_triggers.py's.

- **W2:** r8's would-heal stands, so s5's alert 64 s after it folds into r8's incident (by its
  label, its IPv4 and its IPv6 polled address), and the drift check's trigger of the same
  departure 154 s after it joins it: no second incident, no second decision.
- **W3:** r4's own IP SLA alert 57 s and 89 s after its decision joins r4's incident, its
  decision a would-heal or guard 4's hold (the first run).
- **W7:** r7's lost telemetry 99 s after r6's guard 12 can't-fix folds into r6's incident:
  one incident, one notice.
- **A revert ends nothing to heal (C2840):** the person's revert sends the standing incident
  back to watching; read at its golden, it is nothing to heal, never a guard 9 hold, and never
  a can't-fix on the symptom the reverted change caused.
- **Standing, joined, judged again, standing again, ended:** a drift record of another
  departure judges it again; read again with the same departure it stands again (no second
  decision); a drift run that READ the device at its golden after the decision ends it, and
  one that names no clean read ends nothing; guard 4's hold is not ended by a clean read.
- **W5 (C2825):** a symptom read gone inside the flap window is checked again, never a can't
  fix; past it, cleared by itself; a can't-fix whose diagnosis reads the symptom gone ends
  cleared, no message, no analysis; a new trigger in the window, and it is told; told once per
  incident however often a standing incident is judged again.
"""
import time

import pytest

from tests.test_drift_population import fleet  # noqa: F401 (the fixture)
from tests.test_heal_analysis import ACL_RUNNING, ai, cant_fix  # noqa: F401 (the fixture)
from tests.test_heal_decide import (DC, DS, GOLDEN, I, ROUTE4, Fake, changed, iso, lab,
                                    settle)
from tests.test_heal_policy import T0, confirm
from tests.test_heal_triggers import DEVICES, INTENTS, T, _Lazy, alert, line
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `lab` builds on)

DT, AD, SL = _Lazy("detect"), _Lazy("auto_diagnose"), _Lazy("steplog")
#: W2's r8: an OSPF `network` statement removed (missing line, Tier 1).
R8 = changed((" network 192.0.2.8 0.0.0.3 area 0\n", ""))
#: W7's r6: two removal units, so guard 12 can't fix it ("would remove 2 units, more than 1").
TWO = GOLDEN + ROUTE4 + "ip route 192.0.2.64 255.255.255.192 192.0.2.10\n"
#: Each device's IPv6 polled address beside its IPv4 one (the fold's world holds IPv4 only).
V6 = {"core-b": "2001:db8:0:6::1", "leaf-c": "2001:db8:0:7::1"}


@pytest.fixture(autouse=True)
def no_host_addresses(monkeypatch):
    """This host's addresses, for the manager's routes: outside every test route."""
    monkeypatch.setattr("modules.nsot.removal.host_addresses", lambda: ["192.0.2.60"])


@pytest.fixture
def fold(lab, monkeypatch):
    """Default marked lab, in dry run (tests/test_heal_decide.py's `lab`), with the fold's world
    (tests/test_heal_triggers.py's `world`): edge-a, core-b and leaf-c in a chain from Mercury's
    subnet, each polled at its IPv4 address and core-b and leaf-c at an IPv6 one too."""
    from modules import attention as A
    from modules import neighbours as N
    from modules.nsot import blast_radius as BR

    held = {d: ["Default"] for d in DEVICES}
    addresses = {ip: {d} for d, ip in DEVICES.items()}
    addresses.update({ip: {d} for d, ip in V6.items()})
    monkeypatch.setattr(A, "_device_networks", lambda: dict(held))
    monkeypatch.setattr(A, "_inventory", lambda: ((set(DEVICES), dict(addresses)), ""))
    monkeypatch.setattr(N, "committed_intents", lambda repo: (INTENTS, ""))
    monkeypatch.setattr(BR, "host_networks", lambda: ["192.0.2.0/30"])
    monkeypatch.setattr("modules.nsot.scheduled_rotation.committed_rotations",
                        lambda network: {})
    return lab


def dep(running, device):
    from modules.drift_check import departure, drift_diff

    return departure(drift_diff(GOLDEN, running, device))


def change(device, ts):
    """A CONFIG_I from outside Mercury on *device* at *ts* (the logs-tail step)."""
    return T.from_logs_tail("logs-tail", {"lines": [line(dev=device, ts=ts)]}, now=ts)


def alerted(device, ts, *, by="label", rule="IP SLA probe failing"):
    """A firing alert on *device* at *ts*, placed by its label, or by its polled IPv4 or IPv6
    address (`triggers.from_alerts`)."""
    if by == "label":
        inst = alert(rule=rule, labels={"device": device, "n": str(ts)}, device=device,
                     active_at=iso(ts))
    else:
        addr = DEVICES[device] if by == "ipv4" else V6[device]
        inst = alert(rule=rule, labels={"instance": addr, "n": str(ts)}, device=None,
                     address=addr, device_from="address", active_at=iso(ts))
    return T.from_alerts("grafana-alerts", {"instances": [inst]}, now=ts)


def drifted(device, ts, departure):
    return T.after_drift_record("Default", {"triggered_by": "scheduled", "drifted_devices": [
        {"hostname": device, "changed_lines": 1, "read_at": ts, "departure": departure}]},
        now=ts)


def the(device):
    """*device*'s one open incident (as its device)."""
    (inc,) = [i for i in I.read("Default")["incidents"]
              if i["state"] in I.OPEN_STATES and i["device"] == device]
    return inc


def decide(device, running, now, **fake):
    """Settle *device*'s watching incident on *running*'s departure and run the decision."""
    I.settle("Default", the(device)["id"], {"state": "persisted", "words": "two reads",
                                            "operands": {"departure": dep(running, device)}},
             now - 5)
    (d,) = DC.run("Default", now=now, sources=Fake(running, **fake))["decided"]
    return d


def open_devices():
    got = [i for i in I.read("Default")["incidents"] if i["state"] in I.OPEN_STATES]
    return sorted(d for i in got for d in [i["device"]] + [m["device"] for m in i["attached"]])


# ── C2813: the walks' fold-in cases ─────────────────────────────────────────────────────────

class TestTheWalks:
    @pytest.mark.parametrize("by", ["label", "ipv4", "ipv6"])
    def test_w2_s5_folds_into_r8s_would_heal_and_the_drift_check_joins_it(self, fold, by):
        # W2: r8's would-heal at 18:53:46 UTC, s5's alert at 18:54:50 (64 s), the drift
        # check's trigger of the same unhealed change at 18:56:20 (154 s).
        change("core-b", T0)
        d = decide("core-b", R8, T0 + 150)
        assert d["outcome"] == "would_heal", d
        inc = the("core-b")
        assert inc["state"] == "standing" and inc["standing"]["decision"] == d["decision"]
        assert inc["standing"]["departure"] == dep(R8, "core-b")
        alerted("leaf-c", T0 + 214, by=by)
        (m,) = the("core-b")["attached"]
        assert m["device"] == "leaf-c" and "inside core-b's blast radius" in m["why"], m
        got = drifted("core-b", T0 + 304, dep(R8, "core-b"))
        assert got["incidents"][0]["action"] == "joined", got
        assert DC.run("Default", now=T0 + 310, sources=Fake(R8))["decided"] == [], \
            "no second decision"
        assert [x["outcome"] for x in DS.decisions("Default")] == ["would_heal"]
        assert open_devices() == ["core-b", "leaf-c"], "one incident per device, one per cause"
        (entry,) = SL.incidents("Default")["entries"]
        assert entry["incident"] == inc["id"], "one row per incident on History"

    @pytest.mark.parametrize("state,outcome", [("at_intent", "would_heal"),
                                               ("departs", "held")])
    @pytest.mark.parametrize("by", ["label", "ipv4", "ipv6"])
    def test_w3_r4s_ip_sla_alert_after_its_decision_joins_r4s_incident(self, fold, state,
                                                                      outcome, by):
        # W3: r4's decision at 19:15:21 UTC (guard 4's hold on the first run, a would-heal on
        # the re-run); the IP SLA alert on r4 reached Alerting 89 s, then 57 s, after it.
        change("core-b", T0)
        d = decide("core-b", GOLDEN + ROUTE4, T0 + 150, state=state)
        assert d["outcome"] == outcome, d
        assert the("core-b")["state"] == "standing"
        for after in (57, 89):
            got = alerted("core-b", T0 + 150 + after, by=by)
            assert got["incidents"][0]["action"] == "added", got
        inc = the("core-b")
        assert [t["kind"] for t in inc["triggers"]] == ["config_change", "alert", "alert"]
        assert open_devices() == ["core-b"] and len(I.read("Default")["incidents"]) == 1

    @pytest.mark.parametrize("by", ["label", "ipv4", "ipv6"])
    def test_w7_r7s_lost_telemetry_folds_into_r6s_guard_12_cant_fix(self, fold, by):
        from modules import heal_notice

        # W7: r6's guard 12 can't-fix at 20:03:11 UTC; r7's telemetry streams lost at 20:04:50
        # (99 s), r7's path to the collector running through r6.
        change("core-b", T0)
        d = decide("core-b", TWO, T0 + 150)
        assert d["outcome"] == "cant_fix" and "would remove 2 units" in DS.find(
            "Default", d["decision"])["words"], d
        alerted("leaf-c", T0 + 249, by=by, rule="Telemetry stream lost")
        assert [m["device"] for m in the("core-b")["attached"]] == ["leaf-c"]
        assert open_devices() == ["core-b", "leaf-c"]
        due = heal_notice.due("Default", now=T0 + 300)
        assert [e["incident"] for e in due] == [the("core-b")["id"]], "one notice"

    @pytest.mark.parametrize("by", ["label", "ipv4", "ipv6"])
    def test_a_symptom_long_after_the_decision_is_judged_on_its_own(self, fold, by):
        # A decision that stands for days never swallows an unrelated fault: past
        # FOLD_STANDING_S (2.5 times W7's 99 s), a symptom on another device is its own.
        change("core-b", T0)
        decide("core-b", R8, T0 + 150)
        alerted("leaf-c", T0 + 150 + 251, by=by)
        assert the("core-b")["attached"] == []
        mine = the("leaf-c")
        assert "more than 250 s before this symptom" in mine["fold"]["why"], mine["fold"]
        assert alerted("core-b", T0 + 9000)["incidents"][0]["action"] == "added", \
            "its own device's symptom still joins it"


# ── C2813 and C2840: a revert, and what judges a standing incident again ───────────────────

def read_as(state, departure=""):
    def check(network, device, by):
        return {"state": state, "departure": departure, "changed_lines": 0 if state == "clean"
                else 1, "read_at": None, "skipped": False}
    return check


def pass_at(t, check, **kw):
    return DT.run("Default", now=t, check=check, clock=lambda: t, **kw)


class TestJudgedAgain:
    def test_a_revert_ends_nothing_to_heal_never_a_rate_hold_or_a_cant_fix(self, fold):
        # C2840: r2, r3, r4 and r8 each held by guard 9 after the person's revert; and the
        # symptom the change caused (r4's IP SLA alert) is the reverted change's.
        change("core-b", T0)
        assert decide("core-b", GOLDEN + ROUTE4, T0 + 150)["outcome"] == "would_heal"
        alerted("core-b", T0 + 207)
        got = change("core-b", T0 + 400)                     # the person's revert
        assert got["incidents"][0]["action"] == "rejudged", got
        inc = the("core-b")
        assert inc["state"] == "watching" and inc["judged_from"] == T0 + 400
        pass_at(T0 + 410, read_as("clean"))
        assert the("core-b")["state"] == "ready"
        (d,) = DC.run("Default", now=T0 + 411, sources=Fake(GOLDEN))["decided"]
        assert d["outcome"] == "nothing", DS.find("Default", d["decision"])
        assert [x["outcome"] for x in DS.decisions("Default")] == ["would_heal", "nothing"]
        assert I.read("Default")["incidents"][0]["state"] == "closed"
        (entry,) = SL.incidents("Default")["entries"]
        assert entry["outcome"] == "nothing", "its History row ends nothing to heal"

    def test_rates_are_not_counted_for_an_incident_settled_at_its_golden(self, lab):
        # C2840's shape on a NEW incident: a would-heal of the device in the last hour, then a
        # change read at its golden.
        DS.record("Default", {"incident": "hi-earlier", "device": "edge-b",
                              "outcome": "would_heal", "mode": "dry_run", "units": []}, T0 - 600)
        inc = settle(GOLDEN, how="at_golden")
        d = DC.decide_one("Default", inc, now=T0, sources=Fake(GOLDEN))
        assert d["outcome"] == "nothing" and d["guard"] is None, d
        assert "no rate counted" in d["steps"][-1]["words"], d["steps"]

    def test_another_departure_judges_it_again_and_the_same_one_stands_again(self, fold):
        change("core-b", T0)
        first = decide("core-b", R8, T0 + 150)
        got = drifted("core-b", T0 + 300, "another")
        assert got["incidents"][0]["action"] == "rejudged"
        assert the("core-b")["state"] == "watching"
        change("core-b", T0 + 400)                          # a person's change, nothing moved
        same = dep(R8, "core-b")
        pass_at(T0 + 410, read_as("drifted", same))
        out = pass_at(T0 + 531, read_as("drifted", same))
        assert [s["decision"] for s in out["stood"]] == [first["decision"]], out
        inc = the("core-b")
        assert inc["state"] == "standing" and inc["standing"]["decision"] == first["decision"]
        assert DC.run("Default", now=T0 + 532, sources=Fake(R8))["decided"] == []
        assert [x["outcome"] for x in DS.decisions("Default")] == ["would_heal"]

    def test_a_person_working_counts_a_standing_incidents_changes(self, fold):
        from modules.heal import actions

        change("core-b", T0)
        decide("core-b", R8, T0 + 150)
        assert actions.outside_changes_on("Default", "core-b", T0 + 200, 10) == [T0]


# ── C2813: what ends a standing incident ───────────────────────────────────────────────────

class TestEnded:
    def standing(self, running=R8, **fake):
        change("core-b", T0)
        d = decide("core-b", running, T0 + 150, **fake)
        assert the("core-b")["state"] == "standing", d
        return d

    def test_a_drift_run_that_read_it_at_its_golden_ends_it(self, fold):
        d = self.standing()
        got = T.after_drift_record("Default", {"triggered_by": "scheduled", "drifted_devices": [],
                                               "clean_devices": [{"hostname": "core-b",
                                                                  "read_at": T0 + 3600}]},
                                   now=T0 + 3601)
        (ended,) = got["ended"]
        (inc,) = I.read("Default")["incidents"]
        assert inc["state"] == "closed" and ended in inc["closed_why"]
        last = DS.find("Default", ended)
        assert last["outcome"] == "nothing" and last["ends"] == d["decision"]
        assert "read core-b at its golden at" in last["words"], last["words"]
        assert SL.incidents("Default")["entries"][0]["outcome"] == "nothing"

    @pytest.mark.parametrize("result", [
        {"triggered_by": "scheduled", "drifted_devices": [], "clean": 1},
        {"triggered_by": "scheduled", "drifted_devices": [],
         "clean_devices": [{"hostname": "core-b", "read_at": T0 + 100}]},
        {"triggered_by": "scheduled", "drifted_devices": [],
         "clean_devices": [{"hostname": "core-b"}]}],
        ids=["no-clean-devices", "read-before-its-decision", "no-read-time"])
    def test_absence_or_an_older_read_ends_nothing(self, fold, result):
        self.standing()
        T.after_drift_record("Default", result, now=T0 + 3601)
        assert the("core-b")["state"] == "standing"

    def test_guard_4s_hold_is_not_ended_by_a_read_at_its_golden(self, fold):
        assert self.standing(state="departs")["outcome"] == "held"
        T.after_drift_record("Default", {"triggered_by": "scheduled", "drifted_devices": [],
                                         "clean_devices": [{"hostname": "core-b",
                                                            "read_at": T0 + 3600}]},
                             now=T0 + 3601)
        assert the("core-b")["state"] == "standing", "its cause is a golden departing intent"

    def test_turned_off_closes_it(self, fold):
        self.standing()
        confirm("Default", now=T0 + 200, heal_mode="off")
        got = pass_at(T0 + 210, read_as("clean"))
        assert got["closed"] == [I.read("Default")["incidents"][0]["id"]]
        assert I.read("Default")["incidents"][0]["state"] == "closed"


class TestTheDriftRun:
    def test_a_run_names_each_device_it_read_at_its_golden(self, fleet):
        r = fleet["module"].run_drift_check("test")
        assert [c["hostname"] for c in r["clean_devices"]] == ["r1"]
        assert r["clean_devices"][0]["read_at"] > 0
        assert "r2" in [d["hostname"] for d in r["drifted_devices"]]

    def test_one_devices_check_keeps_the_runs_clean_reads(self):
        from modules import drift_check as D

        run = {"checked": 2, "drifted": 1, "drifted_devices": [{"hostname": "r2"}],
               "clean_devices": [{"hostname": "r1", "read_at": 10.0}]}
        one = {"drifted_devices": [], "clean_devices": [{"hostname": "r2", "read_at": 20.0}]}
        got = D.merged(run, one, "r2", "op@example.invalid")
        assert sorted(c["hostname"] for c in got["clean_devices"]) == ["r1", "r2"]
        assert "clean_devices" not in D.merged({"checked": 0}, {}, "r2", "x"), \
            "a run recorded before the field stays as it was"



# ── C2825: W5's can't-fix after its symptom cleared ────────────────────────────────────────

ADJ_LOG = {"kind": "adjacency_log", "key": "adjlog:1", "source": "adjacency-log",
           "protocol": "OSPF", "related": ["edge-c"],
           "words": "edge-b logged its OSPF adjacency to 192.0.2.10 (edge-c) down"}


def adj(epoch):
    return dict(ADJ_LOG, epoch=epoch, at=iso(epoch))


class TestW5:
    def test_read_gone_inside_the_window_is_checked_again_then_cleared(self, lab):
        from modules import heal_notice

        # W5: the revert's OSPF reset logged at 19:47:18 UTC; decided ~90 s later, the
        # adjacency read up again. Nothing is a can't-fix, nothing is told.
        drop = T0 - 90
        settle(GOLDEN, how="at_golden", triggers=[adj(drop)], claim=False)
        src = Fake(GOLDEN)
        src.symptom_now = lambda device, triggers: "gone"
        (d,) = DC.run("Default", now=T0, sources=src)["decided"]
        assert d["outcome"] == "deferred", d
        assert heal_notice.due("Default", now=T0 + 1) == [], "no could-not-fix message"
        assert [e["outcome"] for e in SL.incidents("Default")["entries"]] == ["deferred"]
        later = drop + 601
        pass_at(later, read_as("clean"))
        (d,) = DC.run("Default", now=later, sources=src)["decided"]
        got = DS.find("Default", d["decision"])
        assert got["outcome"] == "nothing", got
        # C2813's wording (the operator): "at HH:MM" for a time Mercury measured.
        assert f"cleared by itself at {time.strftime('%H:%M', time.gmtime(later))} UTC, " \
               "nothing to do" in got["words"], got["words"]
        assert "itself by" not in got["words"], "never 'by' for a time Mercury read"
        assert I.read("Default")["incidents"][0]["state"] == "closed"

    def standing_cant_fix(self, epoch):
        settle(GOLDEN, how="at_golden", triggers=[adj(epoch)], claim=False)
        src = Fake(GOLDEN)
        src.symptom_now = lambda device, triggers: "stale"     # not read since the drop
        (d,) = DC.run("Default", now=T0, sources=src)["decided"]
        assert d["outcome"] == "cant_fix", d
        inc = I.read("Default")["incidents"][0]
        assert inc["state"] == "standing" and inc["standing"]["on"] == "symptom"
        return inc

    def diagnosis(self, monkeypatch, ruled_out=("the adjacency is up now at both ends",
                                                 "one_way"), hypotheses=()):
        monkeypatch.setattr("modules.heal.auto_diagnose.target_for",
                            lambda network, incident, **kw: {
                                "runbook": "adjacency_down",
                                "target": {"device": "edge-b", "neighbour": "edge-c"}})

        def run(network, runbook, target, actor, *, incident=""):
            d = {"id": "dg-w5", "network": network, "runbook": runbook, "target": target,
                 "incident": incident, "actor": actor, "state": "done", "words": "",
                 "steps": [], "hypotheses": list(hypotheses), "more": 0,
                 "ruled_out": [{"check": ruled_out[0], "rule": ruled_out[1]}],
                 "not_checked": [], "commands": 20, "cap": 70, "runs": [], "stopped": "",
                 "devices": ["edge-b", "edge-c"], "started_at": iso(T0),
                 "finished_at": iso(T0 + 30)}
            SL.record_diagnosis(network, d)
            return d
        return run

    def test_its_diagnosis_reads_it_gone_so_it_ends_cleared_and_nothing_is_sent(
            self, ai, monkeypatch):
        from modules import attention, heal_notice

        from modules.ai import heal_analysis as HA

        inc = self.standing_cant_fix(time.time() - 60)       # hi-2be00d44ca90's shape
        events, waited, analysed = [], [], []
        monkeypatch.setattr(HA, "analyse", lambda *a, **k: analysed.append(a) or {})
        got = heal_notice.notice(
            "Default", inc["id"], deliver=lambda n, e: events.append(e) or {"ok": True},
            wait_s=5, now=T0 + 1, diagnose=self.diagnosis(monkeypatch), diagnosis_wait_s=5,
            quiet_wait=waited.append, symptom=lambda device, triggers: "gone")
        assert events == [] and analysed == [], "no could-not-fix message, no analysis"
        assert 0 < waited[0] <= 600, "the flap window waited out, never longer"
        d = got["cleared"]
        assert d["outcome"] == "nothing" and "cleared by itself at" in d["words"], d
        assert "the adjacency is up now at both ends" in d["words"]
        assert I.read("Default")["incidents"][0]["state"] == "closed"
        assert attention._later_done(DS.decisions("Default"))["edge-b"] >= T0, \
            "its Critical row leaves"

    @pytest.mark.parametrize("case", ["a-new-trigger", "a-cause-found", "store-present"])
    def test_otherwise_it_is_told(self, ai, monkeypatch, case):
        from modules import heal_notice

        last = time.time() - 60
        inc = self.standing_cant_fix(last)
        events = []

        def wait(seconds):
            if case == "a-new-trigger":                      # it dropped again: flapping
                I.sight("Default", "edge-b", dict(adj(last + 30), key="adjlog:2"),
                        now=last + 30)
        hyp = ([{"rule": "mtu", "layer": "link", "strength": "decisive", "incomplete": [],
                 "agree": 2, "claim": "the MTU differs", "evidence": []}]
               if case == "a-cause-found" else ())
        heal_notice.notice(
            "Default", inc["id"], deliver=lambda n, e: events.append(e) or {"ok": True},
            wait_s=5, now=T0 + 1, diagnose=self.diagnosis(monkeypatch, hypotheses=hyp),
            diagnosis_wait_s=5, quiet_wait=wait,
            symptom=lambda device, t: "present" if case == "store-present" else "gone")
        assert [e["event"] for e in events] == ["cant_fix"], case

    def test_the_detect_pass_ends_a_standing_cant_fix_whose_symptom_cleared(self, lab):
        inc = self.standing_cant_fix(T0 - 900)
        for t, state in ((T0 - 900 + 599, "gone"), (T0 + 60, "present"), (T0 + 61, "stale")):
            assert pass_at(t, read_as("clean"), symptom=lambda d, tr, s=state: s)["cleared"] \
                == [], (t, state)
        got = pass_at(T0 + 62, read_as("clean"), symptom=lambda d, tr: "gone")
        assert [c["incident"] for c in got["cleared"]] == [inc["id"]]
        assert I.read("Default")["incidents"][0]["state"] == "closed"
        assert DS.decisions("Default")[-1]["outcome"] == "nothing"

    def test_a_standing_cant_fix_judged_again_is_told_once(self, lab):
        from modules import heal_notice
        from modules.ai import heal_analysis as HA

        inc = cant_fix()                                     # Tier 4: it stands
        assert I.read("Default")["incidents"][0]["state"] == "standing"
        started = []
        heal_notice.run("Default", now=T0 + 1, starter=lambda *a, **k: started.append(a[1]))
        assert started == [inc]
        I.sight("Default", "edge-b", {"kind": "config_change", "key": "cfg:2",
                                      "epoch": T0 + 10, "at": iso(T0 + 10),
                                      "attribution": {"by": "outside"}, "words": "CONFIG_I"},
                now=T0 + 10)
        again = ACL_RUNNING + ROUTE4
        I.settle("Default", inc, {"state": "persisted", "words": "two reads",
                                  "operands": {"departure": dep(again, "edge-b")}}, T0 + 200)
        (d,) = DC.run("Default", now=T0 + 201, sources=Fake(again))["decided"]
        assert d["outcome"] == "cant_fix" and d["incident"] == inc
        assert heal_notice.due("Default", now=T0 + 202) == [], "not due: told already"
        heal_notice.run("Default", now=T0 + 202, starter=lambda *a, **k: started.append(a[1]))
        assert started == [inc], "an incident already told is not told again"
        assert [r["incident"] for r in HA.read("Default")["rows"] if r["row"] == "asked"] \
            == [inc]

    def test_one_ended_before_its_notice_goes_is_not_told(self, lab):
        from modules import heal_notice

        inc = cant_fix()
        assert DC.end_standing("Default", inc, "nothing to heal: read back at its golden",
                               now=T0 + 5, by="the drift check (scheduled)",
                               read_words="at its golden")["outcome"] == "nothing"
        events = []
        got = heal_notice.notice("Default", inc, deliver=lambda n, e: events.append(e) or {},
                                 wait_s=1, now=T0 + 6)
        assert events == [] and "found nothing to heal" in got["first"]["withheld"], got

    def test_the_symptom_gone_check_is_the_runbooks_own(self):
        done = {"state": "done", "runbook": "adjacency_down", "hypotheses": [], "stopped": "",
                "ruled_out": [{"check": "the adjacency is up now at both ends",
                               "rule": "one_way"}]}
        assert AD.symptom_gone(done) == "the adjacency is up now at both ends"
        reach = dict(done, runbook="cant_reach", ruled_out=[{
            "check": "r3 reaches 2001:db8::4: 5 of 5 probes answered", "rule": "reach"}])
        assert AD.symptom_gone(reach).startswith("r3 reaches 2001:db8::4")
        for not_gone in (dict(done, hypotheses=[{"rule": "mtu"}]), dict(done, stopped="cap"),
                         dict(done, state="busy"), dict(done, runbook="cant_reach"),
                         dict(done, ruled_out=[{"check": "each end is up",
                                                "rule": "down_admin_up"}])):
            assert AD.symptom_gone(not_gone) == "", not_gone
