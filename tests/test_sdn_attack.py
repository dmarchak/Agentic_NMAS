"""One attack on one target (C2279, PHASE8_PLAN 17.10; `loop.attacks`, `loop.member_verdict`,
`attention._one_row_per_attack`), on the operator's recorded capture RC-UDP (three senders to
h2, tests/fixtures/sdn/recorded/) replayed through the rules and the loop, its classify step
counted.

- **One call:** RC-UDP's four flood incidents at pass 13 (h1's, h3's and h4's ports and s1's
  link port) send to 192.0.2.2: one attack, classified once on its first incident.
- **Each source its own response:** each member's response carries its own source and the
  attack's target, and is a person's to confirm (its parameters were checked on the first).
- **Seen once:** Needs attention draws the attack as one row naming the target, its sources and
  its incidents; SDN › Responses says on each member what it is part of.
- **Not an attack:** RC-ICMP's pair (each other's destination) and RC-TCP's transfer make none.
"""
from html import unescape

from modules import attention as A
from modules.sdn import detect as D
from modules.sdn import loop as LP
from tests import sdn_series as S
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_incidents import NET, NO_DRIVER, calls, collected  # noqa: F401
from tests.test_sdn_ops_v2 import lab  # noqa: F401 - the fixture

DIR = "tests/fixtures/sdn/recorded"


def through_the_loop(label: str) -> list:
    """The capture's passes through `loop.run_pass`, each detection fired when new."""
    before, outs = set(), []
    for r in S.replay(S.load(f"{DIR}/{label}.jsonl")):
        now = {d["key"]: d for d in r["detections"]}
        fired = [d for k, d in now.items() if k not in before]
        at = D._epoch(r["at"])
        observe = lambda n, c, r=r, f=fired, now=now: {  # noqa: E731
            "ok": True, "fired": [d["key"] for d in f], "resolved": [],
            "detections": list(now.values()),
            "thresholds": {"sdn_flood_window_seconds": 30, "sdn_scan_window_seconds": 60},
            "collected_at": r["at"]}
        outs.append((r["n"], LP.run_pass(NET, collect=collected, observe=observe,
                                         now=lambda at=at: at, driver=NO_DRIVER)))
        before = set(now)
    return outs


def test_rc_udp_s_four_incidents_are_one_attack_classified_once(calls):  # noqa: F811
    outs = dict(through_the_loop("RC-UDP"))
    assert len(outs[13]["proposed"]) == 4
    assert [d["rule"] for d in calls] == ["flood"], "one call for the attack"
    rows = LP.awaiting(NET)["rows"]
    attacks = {(r.get("incident") or {}).get("attack", {}).get("key") for r in rows}
    assert attacks == {"attack|192.0.2.2"}
    by_port = {(r["detection"]["dpid"], r["detection"]["port"]): r for r in rows}
    assert {k: r["detection"].get("source") for k, r in by_port.items()} == {
        (1, 1): "192.0.2.1", (1, 3): None, (2, 1): "192.0.2.3", (2, 2): "192.0.2.4"}
    att = rows[0]["incident"]["attack"]
    assert att["sources"] == ["192.0.2.1", "192.0.2.3", "192.0.2.4"]
    assert len(att["incidents"]) == 4
    lead = next(r for r in rows if r["incident"]["key"] == att["lead"])
    for r in rows:
        if r is lead:
            continue
        assert r["classified"].startswith("classified with the attack on 192.0.2.2"), r["id"]
        src = r["detection"].get("source")
        assert r["params"].get("source") == src if src else "source" not in r["params"]
    said = [x["words"] for x in outs[13]["lines"] if x["step"] == "classify"]
    assert sum("no call of its own" in w for w in said) == 3


def test_the_attack_is_one_row_on_needs_attention_and_said_on_each_member(lab):  # noqa: F811
    through_the_loop("RC-UDP")
    rows = A.sdn_responses_source(found={NET: LP.awaiting(NET)}, watched={})["rows"]
    (row,) = [r for r in rows if r["kind"] == "awaiting"]
    assert row["what"] == ("SDN flood on 192.0.2.2 on Default, from 3 sources (192.0.2.1, "
                           "192.0.2.3, 192.0.2.4), one attack in 4 incidents, awaits a person")
    assert len(row["operands"]["incidents"]) == 4
    page = unescape(lab["client"].get("/v2/sdn/responses?list=Default").get_data(as_text=True))
    assert page.count('Part of the attack on <span class="mono">192.0.2.2</span> with 3 other '
                      "incidents (3 sources: ") == 4


def test_a_reply_pair_and_a_transfer_make_no_attack(calls):  # noqa: F811
    for label in ("RC-ICMP", "RC-TCP"):
        through_the_loop(label)
    assert not [r for r in LP.awaiting(NET)["rows"] if (r.get("incident") or {}).get("attack")]
