"""C1778: the endpoint layer captured into an alert's evidence pack (PHASE8_PLAN 15.15), as the
pack captures the Topology read (C1712): who was attached to the alert's device and those one hop
from it, from the endpoint store's read made as of the alert's time, never a later read.

- Captured: a read inside the alert's window keeps the endpoints on the named devices alone,
  each with its last-seen in words; a read locating none there is empty; an unreadable store
  says so.
- Not the alert's: the store keeps only its latest read (no endpoint history yet, C1793), so a
  replay of an older alert, or a read too long before it, is absent, saying why.
- The pack: the section sits after `observed`; the schema is 3.
- Explain: the endpoints ride as the coverage header's endpoints layer (present when captured,
  not_collected with the section's why otherwise), and are sent only with the topology class.
"""
from modules import evidence_pack as EP
from modules.ai import explain
from tests.test_ai_explain import world  # noqa: F401 (the fixtures)
from tests.test_device_v2 import lab  # noqa: F401
from tests.test_evidence_pack import NOW, V6, _alerts, _build, _section
from tests.test_evidence_pack import pack_lab  # noqa: F401
from tests.test_evidence_pack_context import ctx  # noqa: F401

AT = 1_793_030_000.0                                  # the alert's time
H1 = {"mac": "aac1ab99f6e2", "addresses": ["192.0.2.100"], "hostname": "desk7",
      "device": "edge1", "interface": "GigabitEthernet1/0", "vlan": "10",
      "last_seen": "2026-10-26T17:00:00Z"}
FAR = dict(H1, mac="aac1ab99f6e3", hostname="desk9", device="core9")


def _read(at_iso, endpoints=(H1, FAR)):
    return {"state": "read", "why": "", "read_at": at_iso, "endpoints": list(endpoints),
            "devices": {}}


def test_a_read_inside_the_alert_s_window_is_captured_for_the_devices_near_it():
    sec = EP.endpoints_section("Lab", ["edge1", "edge2"], AT, AT,
                               stored=_read(EP._iso(AT - 600)))
    assert sec["state"] == "ok" and sec["endpoints_read_at"] == EP._iso(AT - 600)
    (p,) = sec["pieces"]
    assert (p["hostname"], p["device"], p["interface"], p["ref"]) == (
        "desk7", "edge1", "GigabitEthernet1/0", "endpoints:1")
    assert p["seen"].startswith("last seen edge1 GigabitEthernet1/0, ")


def test_a_replay_of_an_older_alert_is_not_given_today_s_read():
    """The store keeps only its latest read: a read made after the alert's time is never the
    alert's (C1712's rule), so the section says so and names the history it lacks."""
    sec = EP.endpoints_section("Lab", ["edge1"], AT, AT + 86400,
                               stored=_read(EP._iso(AT + 86400)))
    assert sec["state"] == "absent" and sec["pieces"] == []
    assert "not as of this alert's time" in sec["why"] and "C1793" in sec["why"]


def test_a_read_too_long_before_the_alert_is_not_the_alert_s_either():
    sec = EP.endpoints_section("Lab", ["edge1"], AT, AT,
                               stored=_read(EP._iso(AT - EP.ENDPOINTS_BEFORE_S - 60)))
    assert sec["state"] == "absent"


def test_a_read_locating_nothing_there_is_empty_and_an_unreadable_store_says_so():
    sec = EP.endpoints_section("Lab", ["edge2"], AT, AT, stored=_read(EP._iso(AT)))
    assert sec["state"] == "empty" and "locates no endpoint on edge2" in sec["why"]
    bad = EP.endpoints_section("Lab", ["edge1"], AT, AT,
                               stored={"state": "unreadable", "why": "torn file"})
    assert (bad["state"], bad["why"]) == ("unreadable", "torn file")


def test_build_captures_the_alert_s_device_and_those_one_hop_from_it(ctx):  # noqa: F811
    """Through the real builder, on test_evidence_pack_context's network (C1547's planted
    shape): an endpoint on the alert's device and one on a device one hop away are kept, one
    two hops away is not."""
    health = _section(ctx.pack, "health")["pieces"]
    alert_dev = next(p["device"] for p in health if p["hop"] == 0)
    one = next(p["device"] for p in health if p["hop"] == 1)
    two = next(p["device"] for p in health if p["hop"] == 2)
    planted = [dict(H1, mac=f"aac1ab99f6e{i}", hostname=f"desk{i}", device=d)
               for i, d in enumerate((alert_dev, one, two))]
    pack = _build(_alerts(V6), endpoints_read=_read(EP._iso(NOW - 300), planted))
    sec = _section(pack, "endpoints")
    assert sec["state"] == "ok"
    assert sorted(p["device"] for p in sec["pieces"]) == sorted([alert_dev, one])
    assert pack["schema"] == 5   # 3 brought the endpoints; 4 (the marks) and 5 keep them


def test_the_pack_holds_it_after_observed_on_schema_3():
    # 3 brought the endpoints; 4, the sections' marks, and 5, the other alerts and one id
    # per device (C1849 to C1851), keep them.
    assert EP.SCHEMA == 5
    assert EP.SECTIONS.index("endpoints") == EP.SECTIONS.index("observed") + 1


def _pack(section):
    return {"sections": [section]}


def test_explain_carries_it_as_the_endpoints_layer():
    got = explain.carried_layers(_pack(EP.endpoints_section(
        "Lab", ["edge1"], AT, AT, stored=_read(EP._iso(AT)))))
    assert got["endpoints"]["state"] == "present"
    absent = EP.endpoints_section("Lab", ["edge1"], AT, AT, stored=_read(EP._iso(AT + 86400)))
    got = explain.carried_layers(_pack(absent))
    assert got["endpoints"]["state"] == "not_collected"
    assert got["endpoints"]["why"] == f"absent: {absent['why']}"


def test_the_endpoints_are_sent_only_with_the_topology_class():
    sec = EP.endpoints_section("Lab", ["edge1"], AT, AT, stored=_read(EP._iso(AT)))
    (sent,) = explain.sent_sections(_pack(sec), {"sent": True})
    assert sent["pieces"] and "withheld" not in sent
    (held,) = explain.sent_sections(_pack(sec), {"sent": False})
    assert held["pieces"] == [] and "topology class" in held["withheld"]
