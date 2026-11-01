"""The attribution rule's acceptance test (PHASE8_PLAN 20.2 and 20.4; the operator's brief of
2026-11-01, item 4, queue item b): 2026-10-30's B2, Mercury's planned Reload of r8, replayed
through the Needs attention sources.

**B2 as it was** (`blind-runs/blind-sdn-session-notes.md`): Needs attention rose to 11 for one
planned reload: OSPF and OSPFv3 r2–r8 not up (critical), Device unreachable on s5 (Grafana,
critical) and s5 not answering (reachability, critical), r2's OSPF and OSPFv3 adjacency to r8's
router id logged down "outside any planned restart or deploy" (two warnings), r8's protocols
cannot be judged, r8 and s5 could not be checked for drift, beside the standing heartbeat-check
row. The Reload's preview had said "Mercury loses reach to 1 other device: s5".

**Here, on the suite's captured lab** (tests/test_grafana_reader.py's inventory and Grafana
capture, the rules view's real `Device unreachable (SNMP)` instances): r2 reloads as r8 did,
s2 is the device its preview predicts unreachable (s5's part: reached only through it), and r1
is the peer (r2's part in B2). Each source's input is the reader's stored shape with those
devices; the Grafana instances are the capture's, set Alerting. The window is the Reload's own
record (`restarts.record_planned` with the preview's cut).

**The acceptance:** inside the window and its settle time, the nine rows these sources raised
become none, each said under What was checked as the operation's expected effect; the standing
heartbeat row is another source's and stays (it is not driven here). Controls: with no window
all nine are rows; with the window but no predicted device, s2's two rows and nothing else
return; past the settle time every row returns ("overdue").
"""
import time

import pytest

from modules import attention as A
from modules import restarts as R
from tests.test_grafana_reader import INVENTORY, cached, load, parse, rule

NOW = time.time()
T0 = NOW - 480                      # the Reload pressed 8 minutes ago
UNTIL = T0 + 1295                   # B2's window: 01:04:14 to 01:25:49
ROUTER_ID = "10.255.0.2"            # r2's router id, as r1's log names its peer


def _window(unreachable=("s2",)):
    row = {"devices": ["r2"], "list": "Lab", "from": R._iso(T0), "until": R._iso(UNTIL),
           "by": "operator@example.com", "why": "planned maintenance: reload r2",
           "via": "reload"}
    if unreachable:
        row["expected"] = {"unreachable": list(unreachable)}
    return row


@pytest.fixture
def b2(monkeypatch):
    from modules import device
    monkeypatch.setattr(device, "load_saved_devices", lambda *a, **k: list(INVENTORY))
    monkeypatch.setattr(device, "get_device_lists", lambda: [{"name": "Lab", "filename": "lab"}])
    monkeypatch.setattr(A, "_device_networks",
                        lambda: {d["hostname"]: ["Lab"] for d in INVENTORY})
    monkeypatch.setattr(A, "_peer_names", lambda list_name, cache: {ROUTER_ID: "r2"})
    state = {"planned": [_window()]}
    monkeypatch.setattr(R, "planned_rows", lambda: state["planned"])
    monkeypatch.setattr(R, "ends", lambda: {})
    return state


def _grafana():
    view = load("rules_view")
    for inst in rule(view, "Device unreachable (SNMP)")["alerts"]:
        if inst["labels"]["instance"] in ("10.255.1.12", "10.255.1.22"):     # r2, s2
            inst["state"], inst["activeAt"] = "Alerting", R._iso(T0 + 220)
    return A.grafana_source(cached=cached(parse(view)))


def _reachability():
    at = R._iso(T0 + 30)
    devs = {h: {"hostname": h, "list": "Lab", "address": ip, "answering": False, "since": at,
                "consecutive_misses": 3, "threshold": 3, "claim": "TCP 22"}
            for h, ip in (("r2", "10.255.1.12"), ("s2", "10.255.1.22"))}
    return A.reachability_source({"state": "ok", "doc": {"last_good": {
        "value_at": R._iso(NOW), "value": {"devices": devs, "counts": {"not_answering": 2}}}}})


def _adjacencies():
    side = lambda dev, state: {"device": dev, "state": state, "words": "down"}  # noqa: E731
    adj = {f"Lab|{p}|r1|r2": {"protocol": p, "devices": ["r1", "r2"], "managed": True,
                              "reads": 5, "since": R._iso(T0 + 60), "list": "Lab",
                              "network": "10.255.3.0/24",
                              "sides": [side("r1", "down"), side("r2", "absent")]}
           for p in ("OSPF", "OSPFv3")}
    value = {"configured": True, "adjacencies": adj, "checked": 14, "devices": 9,
             "unmeasured": [{"device": "r2", "protocol": p, "why": "no series for r2"}
                            for p in ("OSPF", "OSPFv3")]}
    return A.adjacency_source(cached={"state": "ok", "doc": {
        "last_good": {"value": value, "value_at": R._iso(NOW)}, "stale_after_seconds": 180}})


def _adjacency_log():
    at = T0 + 40
    adj = {f"Lab|r1|{p}|{ROUTER_ID}": {
        "device": "r1", "list": "Lab", "protocol": p, "neighbor": ROUTER_ID,
        "interface": "GigabitEthernet2", "band": 1,
        "drops": [{"at": R._iso(at), "epoch": at, "reason": "Dead timer expired"}]}
        for p in ("OSPF", "OSPFv3")}
    value = {"adjacencies": adj, "lines": 2, "devices": 9, "window_days": 7}
    return A.adjacency_log_source(
        cached={"state": "ok", "doc": {"last_good": {"value": value,
                                                     "value_at": R._iso(NOW)}}},
        receipts=lambda ln, dev: [])


def _drift(now=NOW):
    last = {"ok": True, "checked": 9, "drifted_devices": [], "no_golden": [], "skipped": [],
            "errors": [{"hostname": h, "reason": "TCP connection to device failed"}
                       for h in ("r2", "s2")]}
    status = {"list": "Lab", "state": "idle", "disabled": False, "last_run": last,
              "last_ts": T0 + 300}
    return A.drift_source(status=lambda: status, now=now)


def _all():
    return [_grafana(), _reachability(), _adjacencies(), _adjacency_log(), _drift()]


def _rows(results):
    return [r for res in results for r in res["rows"]]


def test_b2_replayed_inside_its_window_raises_nothing(b2):
    results = _all()
    assert _rows(results) == [], [r["what"] for r in _rows(results)]
    checked = " | ".join(res.get("checked") or "" for res in results)
    assert "s2 is out of Mercury's reach as expected while r2 restarts as planned" in checked
    assert "OSPF r1 and r2 (" in checked and "r2's adjacencies cannot be judged (" in checked
    assert "not read during a planned operation, read again by the next run: r2" in checked
    assert "2 drop(s) inside a planned restart or a deploy, not raised" in checked


def test_the_control_with_no_window_raises_b2_s_nine(b2):
    b2["planned"] = []
    rows = _rows(_all())
    whats = sorted(r["what"] for r in rows)
    assert len(rows) == 9, whats
    # The peer is named by its device (the brief's item 3), its router id beside it.
    assert "r1's OSPF adjacency to r2 (10.255.0.2) went down 1 time in the last day" in whats


def test_the_control_with_no_predicted_device_raises_s2_alone(b2):
    b2["planned"] = [_window(unreachable=())]
    rows = _rows(_all())
    assert sorted({d for r in rows for d in r.get("devices") or []}) == ["s2"], \
        [r["what"] for r in rows]
    assert len(rows) == 3, [r["what"] for r in rows]     # Grafana, reachability, drift


def test_past_the_settle_time_it_is_raised(b2, monkeypatch):
    """A signal that outlasts the window and its settle time is no longer explained."""
    late = UNTIL + R.SETTLE_SECONDS + 60
    monkeypatch.setattr(A.time, "time", lambda: late)
    assert R.explained_by("s2", "Lab", late) is None
    assert R.explained_by("s2", "Lab", UNTIL + R.SETTLE_SECONDS - 60)["how"] == "unreachable"
    assert _rows([_reachability()]), "s2 not answering is raised again"


def test_the_reload_records_its_predicted_devices_on_its_window(monkeypatch):
    """The window the Reload declares carries the preview's cut (`record_planned`'s
    *unreachable*), never the reloaded device itself, and never as a device the window
    restarts (so no new host key of it is kept)."""
    written = []
    monkeypatch.setattr(R, "events", lambda: {"state": "ok", "rows": []})
    monkeypatch.setattr(R, "silence_window", lambda row: {})
    monkeypatch.setattr(R, "_append", lambda name, row: written.append(row))
    got = R.record_planned(["r2"], T0, UNTIL, "operator@example.com", "reload r2", "reload",
                           list_name="Lab", unreachable=["s2", "r2", ""])
    assert got["ok"] and written[0]["expected"] == {"unreachable": ["s2"]}
    assert written[0]["devices"] == ["r2"]
    assert not R._names(written[0], "s2", "Lab")
