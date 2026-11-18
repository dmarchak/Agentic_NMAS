"""An incident closes on its fix's own verified device check, never on an alert clearing, and an
alert that does not clear after it is its own finding (the operator's items 4 and 6, 2026-11-15;
`modules/heal/act.py` `alert_firing`, `modules/heal/detect.py` `_fixed`, `modules/heal/triggers.py`
`from_alerts`, `modules/attention.py` `_heal_alert_after_fix_rows` and `_incidents_agree`,
`modules/incident_page.py`'s severity).

Measured on the host, 2026-11-15: s1's incident (BPDU guard err-disabled Gi1/0) had an AI plan
approved, run and verified on the device at 21:29:21Z, yet it stayed open ("its fix passed; it
closes when its symptom clears") and drew Critical again. Two causes: s2's Interface down on its
own GigabitEthernet1/0 (an instance naming no device, kept by its polled address) kept s1's
symptom present, and the C3792 severity applied only while a person was needed.

The world is tests/test_command_plan.py's (s1's committed intent and golden, a fake switch
answering from s1's real captures, the errdisable-recover plan run end to end through the deploy
pipeline's real stages); the incident is opened from the alerts by the triggers' own step,
classified by its own step, and stood on its can't-fix by the incidents and decisions stores'
own writers; the fix-it lines by their own writers. The alert instances are the grafana-alerts
reader's shape for the captured rules (tests/fixtures/grafana/ruler.json: Interface down,
uid bfy1zttkzn8xsa, interval 1m, for 1m, its labels those of its query's series,
tests/fixtures/topology/ifOperStatus.json), not a capture of an instance. No device, no network.

- **The address-only match:** another switch's instance on a port of the same name does not keep
  this device present; this device's own does, by the address its trigger was placed by and, for
  a trigger without one, by the inventory's address; an inventory not read keeps the old
  answer. IPv4 and IPv6.
- **Closed on its verified fix:** a standing can't-fix whose approved plan passed closes at the
  next detect pass with its alert still firing, in words naming the run, its device and when.
- **The alert after it:** still firing within `waits.HEAL_BOUNDS["alert-after-fix"]`, nothing; past
  it, one Needs attention row of its own kind, and never a new incident.
- **Its severity survives the run and the verify:** Warning on its page and on its Needs
  attention row, titled by the problem.
"""
import time

import pytest

from tests import test_errdisable as T
from tests.test_command_plan import ACTOR, KEY, NET, PORT, go
from tests.test_command_plan import lab  # noqa: F401 (the fixture)

#: s1's and s2's polled addresses, IPv4 and IPv6 (test addresses).
ADDRESSES = {"ipv4": {"s1": "192.0.2.11", "s2": "192.0.2.22"},
             "ipv6": {"s1": "2001:db8::11", "s2": "2001:db8::22"}}


def iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def ifdown(address: str, iface: str = PORT, active: float = T.AT + 20) -> dict:
    """An Interface down instance as the grafana-alerts reader stores it: the rule names no
    device, so its polled address alone (`grafana_alerts._instance_device`)."""
    polled = f"[{address}]:161" if ":" in address else address
    return {"rule_uid": "bfy1zttkzn8xsa", "rule": "Interface down", "kind": "condition",
            "state": "Alerting", "active_at": iso(active), "address": polled,
            "device_from": "address",
            "labels": {"alertname": "Interface down", "grafana_folder": "RCN Lab",
                       "ifDescr": iface, "ifIndex": "2", "ifName": "Gi1/0",
                       "instance": polled, "job": "cisco_vios_l2"}}


def critical(active: float = T.AT + 2) -> dict:
    """"Critical syslog received" on s1: its device extracted from the line (`from: line`)."""
    return {"rule_uid": "cfy1critical", "rule": "Critical syslog received", "kind": "condition",
            "state": "Alerting", "active_at": iso(active), "device": "s1",
            "device_from": "line",
            "labels": {"alertname": "Critical syslog received", "device": "s1"}}


def stored(instances, read_started: float) -> dict:
    """The reader's stored document, read at *read_started*."""
    return {"state": "ok", "doc": {"last_good": {"read_started": read_started,
                                                 "value": {"instances": list(instances)}}}}


@pytest.fixture(params=["ipv4", "ipv6"])
def world(lab, monkeypatch, request):  # noqa: F811
    """test_command_plan's lab with s1 known by its NetBox id (its troubleshooting record is
    kept by identity), s1 and s2 polled at their *family*'s addresses, Default in dry run."""
    from modules import attention as A
    from modules import neighbours as N
    from modules.nsot import blast_radius as BR
    from tests.test_heal_policy import confirm

    family = ADDRESSES[request.param]
    monkeypatch.setattr("modules.device.load_saved_devices", lambda *_a, **_k: [
        {"hostname": "s1", "ip": "192.0.2.11", "device_type": "cisco_ios", "_netbox_id": 11}])
    monkeypatch.setattr(A, "_device_networks", lambda: {"s1": [NET]})
    monkeypatch.setattr(A, "_inventory", lambda: (({"s1", "s2"}, {
        family["s1"]: {"s1"}, family["s2"]: {"s2"}}), ""))
    monkeypatch.setattr(A, "_page_network", lambda: NET)
    monkeypatch.setattr(N, "committed_intents", lambda repo: ({"s1": T.s1_intent()}, ""))
    monkeypatch.setattr(BR, "host_networks", lambda: ["192.0.2.0/30"])
    monkeypatch.setattr("modules.nsot.scheduled_rotation.committed_rotations",
                        lambda network: {})
    monkeypatch.setattr("modules.heal.detect.wake", lambda: None)
    confirm(NET, heal_mode="dry_run")
    lab["family"] = family
    return lab


def opened(world) -> dict:
    """s1's incident, opened from its two alerts by the triggers' own step and classified."""
    from modules.heal import incidents as I
    from modules.heal import triggers

    got = triggers.from_alerts("grafana-alerts", {"instances": [
        critical(), ifdown(world["family"]["s1"])]}, now=T.AT + 20)
    assert got["sighted"] == 2, got
    T.E.reclassify_step(NET, sources=T.Src(), now=T.AT + 600)
    (inc,) = I.read(NET)["incidents"]
    return inc


def stood(iid: str) -> dict:
    """The incident stood on a can't-fix at its golden, by the stores' own writers: settled
    at its golden, claimed, the decision recorded and logged, standing on its symptom."""
    from modules.heal import decisions as DS
    from modules.heal import incidents as I
    from modules.heal import steplog as SL

    I.settle(NET, iid, {"state": "at_golden", "words": "read at its golden twice"},
             T.AT + 650)
    I.claim(NET, iid, by="the decision", now=T.AT + 651)
    d = DS.record(NET, {"incident": iid, "device": "s1", "outcome": "cant_fix",
                        "mode": "dry_run", "kind": "", "tier": 3,
                        "words": "s1 is at its golden: its symptom is no departure to heal"},
                  T.AT + 652)
    SL.record_decision(NET, d, T.AT + 652)
    inc = I.stand(NET, iid, d, now=T.AT + 652)
    assert inc["state"] == "standing" and inc["standing"]["on"] == "symptom", inc
    return d


def fixed(world, iid: str) -> dict:
    """A person's proposal of the recovery, run through the real plan (verified), and their
    approval of it: the troubleshooting record's newest step is the passed attempt."""
    from modules import incident_page
    from modules.fixit import incident as F
    from modules.fixit import section

    inc = section.incident_of(NET, incident_page.resolve(NET, iid))["incident"]
    line = F.record_proposal(inc, "person", KEY, {"interface": "Gi1/0", "cause": "bpduguard"},
                             by=ACTOR, verified="access", now=T.AT + 700)
    F.record_approve(inc, ACTOR, "access", proposal=line["proposal"],
                     plan_hash="0123456789abcdef", run="", now=T.AT + 710)
    rec = go(world, incident=iid, fixit={"incident": iid, "proposal": line["proposal"]})
    assert (rec["outcome"], rec["state"]) == ("done", "done"), rec["why"]
    return rec


def detect_pass(now: float, symptom: str = "present") -> dict:
    """One detect pass of Default, its symptoms read as *symptom* (the alert still firing)."""
    from modules.heal import detect

    return detect.run(NET, now=now, check=lambda *a: {}, clock=lambda: now,
                      symptom=lambda device, triggers: symptom)


# ── The address-only match ──────────────────────────────────────────────────────────────────

class TestTheAddressOnlyMatch:
    def trigger(self, world, address=True) -> dict:
        t = {"kind": "alert", "key": "alert:k", "rule": "Interface down", "interface": PORT,
             "source": "grafana-alerts", "epoch": T.AT + 20}
        if address:
            t["address"] = world["family"]["s1"]
        return t

    def judge(self, trigger, *instances) -> str:
        from modules.heal import act
        return act.judge(trigger, stored(instances, T.AT + 900)["doc"], NET, "s1", T.AT + 20)

    def test_another_switchs_instance_on_its_own_port_of_that_name_is_not_this_ones(
            self, world):
        s2 = ifdown(world["family"]["s2"])
        assert self.judge(self.trigger(world), s2) == "gone"
        assert self.judge(self.trigger(world), s2, ifdown(world["family"]["s1"])) == "present"

    def test_the_address_the_trigger_was_placed_by_is_kept_on_it(self, world):
        inc = opened(world)
        (down,) = [t for t in inc["triggers"] if t["rule"] == "Interface down"]
        assert down["address"] == world["family"]["s1"]
        (crit,) = [t for t in inc["triggers"] if t["rule"] != "Interface down"]
        assert "address" not in crit, "placed by its label: no address kept"

    def test_a_trigger_without_one_reads_the_devices_own_from_the_inventory(self, world):
        bare = self.trigger(world, address=False)
        assert self.judge(bare, ifdown(world["family"]["s2"])) == "gone"
        assert self.judge(bare, ifdown(world["family"]["s1"])) == "present"

    def test_an_inventory_not_read_keeps_the_old_answer(self, world, monkeypatch):
        from modules import attention as A
        monkeypatch.setattr(A, "_inventory", lambda: (None, "the inventory could not be read"))
        assert self.judge(self.trigger(world, address=False),
                          ifdown(world["family"]["s2"])) == "present"


# ── Closed on its verified fix ──────────────────────────────────────────────────────────────

class TestClosedOnItsVerifiedFix:
    def test_the_next_pass_closes_it_naming_the_run_with_its_alert_still_firing(self, world):
        from modules.heal import decisions as DS
        from modules.heal import incidents as I

        iid = opened(world)["id"]
        stood(iid)
        assert detect_pass(T.AT + 800)["fixed"] == [], "no fix yet: it stands"
        assert I.read(NET)["incidents"][0]["state"] == "standing"
        rec = fixed(world, iid)
        now = time.time()
        got = detect_pass(now)
        assert [f["incident"] for f in got["fixed"]] == [iid], got
        inc = I.read(NET)["incidents"][0]
        assert inc["state"] == "closed" and inc["fixed"]["run"] == rec["id"], inc
        finished = float(inc["fixed"]["epoch"])
        hhmm = time.strftime("%H:%M", time.gmtime(finished))
        last = DS.decisions(NET)[-1]
        assert last["outcome"] == "nothing" and last["fixed"]["run"] == rec["id"]
        assert (f"fixed: the plan's run {rec['id'][-8:]} verified on s1 at {hhmm} UTC"
                in last["words"]), last["words"]

    def test_a_trigger_after_the_fixs_check_is_the_problem_back(self, world):
        from modules.heal import incidents as I

        iid = opened(world)["id"]
        stood(iid)
        fixed(world, iid)
        later = time.time() + 60
        # An err-disable again: the same rule re-fired, a new episode joining the incident.
        I.sight(NET, "s1", {"kind": "alert", "key": "alert:again", "epoch": later,
                            "at": iso(later), "source": "grafana-alerts",
                            "rule": "Interface down", "interface": PORT,
                            "words": "the alert Interface down fired on s1"}, now=later)
        assert detect_pass(later + 1)["fixed"] == []
        assert I.read(NET)["incidents"][0]["state"] == "standing"


# ── The alert after a verified fix ──────────────────────────────────────────────────────────

class TestTheAlertAfterAVerifiedFix:
    def closed(self, world):
        from modules.heal import incidents as I

        iid = opened(world)["id"]
        stood(iid)
        fixed(world, iid)
        detect_pass(time.time())
        inc = I.read(NET)["incidents"][0]
        assert inc["state"] == "closed"
        return inc, float(inc["fixed"]["epoch"])

    def rows(self, at, read_started, instances):
        from modules import attention as A
        said = []
        got = A._heal_alert_after_fix_rows(NET, at, said, cached={
            "grafana-alerts": stored(instances, read_started)})
        return got, said

    def test_still_firing_reopens_nothing_and_past_its_bound_is_one_row(self, world):
        from modules import waits
        from modules.heal import incidents as I
        from modules.heal import triggers

        inc, at = self.closed(world)
        bound = waits.HEAL_BOUNDS["alert-after-fix"]["seconds"]
        still = [critical(), ifdown(world["family"]["s1"])]
        for after in (60, bound + 60):
            got = triggers.from_alerts("grafana-alerts", {"instances": still}, now=at + after)
            assert got["sighted"] == 0, got
            assert len(I.read(NET)["incidents"]) == 1, "no new incident"
        assert self.rows(at + 60, at + 50, still) == ([], []), \
            "within its bound: no row, and no store is said to be unread"
        (r,) = self.rows(at + bound + 60, at + bound + 50, still)[0]
        assert (r["source"], r["kind"], r["level"]) == ("heal", "alert_after_fix", "warning")
        assert r["what"].startswith("s1: the alert didn't clear after a verified fix")
        assert "Interface down on GigabitEthernet1/0" in r["what"]
        assert inc["fixed"]["run"][-8:] in r["cause"]
        assert r["action"]["href"] == "/v2/device/s1?tab=monitoring"
        assert r["clears"]["ways"] == ["resolves"]

    def test_resolved_or_not_read_since_its_bound_is_no_row(self, world):
        from modules import waits

        _inc, at = self.closed(world)
        past = at + waits.HEAL_BOUNDS["alert-after-fix"]["seconds"] + 60
        assert self.rows(past, past - 10, [ifdown(world["family"]["s2"])])[0] == []
        got, said = self.rows(past, at + 10, [critical(), ifdown(world["family"]["s1"])])
        assert got == [] and "not read since" in said[0], said


# ── Its severity survives the run and the verify ────────────────────────────────────────────

class TestItsSeveritySurvivesTheRun:
    TITLE = "s1 Gi1/0 err-disabled by BPDU guard: h1 is offline"

    def test_warning_on_its_page_and_on_its_row_titled_by_the_problem(self, world):
        from modules import attention as A
        from modules import incident_page as IP

        iid = opened(world)["id"]
        stood(iid)
        fixed(world, iid)
        page = IP.page(NET, iid, attention={"rows": []})
        assert (page["state"], page["fixit"]["state"]) == ("open", "passed"), page["state"]
        assert page["severity"]["words"] == "Warning", page["severity"]
        rows = A._incidents_agree(A.heal_source()["rows"], lst=NET)
        rows = A._fold_signals_into_problems(rows, NET)
        (r,) = [x for x in rows if (x.get("incident_page") or {}).get("id") == iid]
        assert (r["kind"], r["level"], r["what"]) == ("cant_fix", "warning", self.TITLE), r
