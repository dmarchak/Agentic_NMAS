"""A pass's reads of one device run one after another; reads of different devices, and reads
that reach no device, still run at once (C3422; `modules/ai/read_loop.py` `run_reads`).

Measured on the NMAS host, 2026-11-13 05:32 UTC: AI troubleshooting's preview ran its pass's
three device reads of one router at once, and two were refused by Mercury's own
one-operation-per-device hold ("skipped: ... is being read (show commands) by the AI analysis"),
since each read through the reads engine holds its device (`device_ops.hold`, operation
``read``) and a second hold from another thread is refused.

Every read here goes through the real executor of AI troubleshooting's family
(`fixit_reads.FAMILY`: the router read set's `router_reads.run`, then THE reads engine,
`reads.run`, which takes the real `device_ops` hold) on an inventory and a credential store in
this test's own folder; only the session is faked at the engine's seam
(`connection.with_plain_connection`), and it stays inside the device for `DWELL` seconds,
stamping when it went in and came out, so two reads of one device at once would collide on the
hold exactly as they did on the host. No device, no network, no provider.

- **(a)** three reads of one device all run, in the pass's order, their sessions never
  overlapping;
- **(b)** reads of two devices still overlap in time;
- **(c)** a device another operation holds is refused by name, never waited for (the hold
  still the other operation's when the pass returns), and the pass's other reads run;
- **(d)** a read that reaches no device (the stream's series, a ``local`` read) runs beside a
  device's reads.
"""
import os
import threading
import time

import pytest

from modules import credentials
from modules.ai import read_loop as RL
from modules.nsot import device_ops
from tests.test_sdn_connections import make_networks

NETWORK = "Branch"
RO_PW = "ReadOnly-Pass-4417"
#: How long each faked session stays inside its device: long enough that reads started at
#: once overlap by a wide margin (a thread starts in well under a millisecond here).
DWELL = 0.3
DEVICES = [{"hostname": "edge1", "ip": "192.0.2.21", "device_type": "cisco_xe",
            "role": "router", "_platform": "cisco-ios-xe", "_site": "lab"},
           {"hostname": "edge2", "ip": "2001:db8::22", "device_type": "cisco_xe",
            "role": "router", "_platform": "cisco-ios-xe", "_site": "lab"}]


class Session:
    """The reads engine's session seam: each session's device, commands, and when it went in
    and came out."""

    def __init__(self):
        self.mu = threading.Lock()
        self.sessions, self.deploy = [], []

    def plain(self, dev, fn):
        start = time.monotonic()
        time.sleep(DWELL)
        got = fn(self)
        with self.mu:
            self.sessions.append({"host": dev["hostname"], "username": dev.get("username"),
                                  "start": start, "end": time.monotonic()})
        return got

    def temp(self, dev, fn):
        self.deploy.append(dev["hostname"])
        return fn(self)

    def answer(self, command):
        return f"{command}: answered"

    def of(self, host):
        return sorted((s for s in self.sessions if s["host"] == host), key=lambda s: s["start"])


@pytest.fixture
def engine(tmp_path, monkeypatch):
    """The networks' store, the inventory (edge1 and edge2), a read-only account on the default
    profile, the device state class on, and the engine's session seams."""
    from modules import config
    from modules.ai import egress_classes
    root = make_networks(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "get_list_data_dir",
                        lambda name: str(root / "lists" / config.list_slug(name)))
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda path: [dict(d) for d in DEVICES])
    monkeypatch.setattr("modules.commands.run_device_command", lambda conn, c: conn.answer(c))
    session = Session()
    monkeypatch.setattr("modules.connection.with_plain_connection", session.plain)
    monkeypatch.setattr("modules.connection.with_temp_connection", session.temp)
    monkeypatch.setattr(egress_classes, "device_state_allowed",
                        lambda network: {"allowed": True, "why": ""})
    monkeypatch.setattr(egress_classes, "classification_marking", lambda network: "")
    credentials.save_profile("default", username="netops", password="Deploy-Pass-7723")
    credentials.set_read_account("default","mercury-ro", RO_PW, actor="op@example.com",
                                 verified="access")
    yield session
    with device_ops._mu:
        stale = list(device_ops._held.items())
        device_ops._held.clear()
    for _key, info in stale:
        if info["fd"] is not None:
            os.close(info["fd"])


class Series:
    """The stream's series read (`fixit_reads`' ``stream_series``, a read reaching no device),
    stamped as the session is."""

    def __init__(self):
        self.stamps = []

    def __call__(self, device, sub):
        start = time.monotonic()
        time.sleep(DWELL)
        self.stamps.append({"start": start, "end": time.monotonic()})
        return {"state": "absent", "count": 0, "why": "no sample in the last 90 s"}


def scope(series=None) -> dict:
    """AI troubleshooting's scope (`fixit_reads.scope_for`'s shape) for edge1's incident, with
    edge2 named too, each with a read-only account."""
    def device():
        return {"interfaces": [], "peers": [], "dialect": "cisco_iosxe",
                "subscriptions": ["101"], "read_account": True, "read_account_why": ""}
    return {"network": NETWORK, "addresses": [], "prefixes": [],
            "devices": {"edge1": device(), "edge2": device()}, "subscriptions": ["101"],
            "actor": "AI troubleshooting of incident hi-1, pressed by op@example.com",
            "fixit": {"device": "edge1", "streams": {"101": {"address": "192.0.2.10",
                                                             "port": 57000}},
                      "sources": [], "collector": None, "series": series}}


def ask(op, device="edge1", **args):
    return {"op": op, "args": dict({"device": device}, **args), "why": "to see the stream",
            "hypothesis": "the stream stopped"}


def passed(requests, sc):
    """The pass's requests judged by the real check, then run by the real runner."""
    from modules.ai import fixit_reads as FR
    verdicts = RL.check(FR.FAMILY, requests, network=NETWORK, scope=sc)
    assert [v["verdict"] for v in verdicts] == ["allowed"] * len(requests), verdicts
    return RL.run_reads(FR.FAMILY, verdicts, sc)


def overlap(a, b) -> bool:
    return a["start"] < b["end"] and b["start"] < a["end"]


def test_a_passs_three_reads_of_one_device_all_run_in_order(engine):
    """(a) The host's case: three device reads of the incident's device. Each runs, in the
    pass's order, each session after the last one's end, and none is refused by the pass's own
    hold."""
    recs = passed([ask("telemetry_brief"), ask("bgp_summary"), ask("bgp_summary6")], scope())
    assert [r["verdict"] for r in recs] == ["run"] * 3, [r.get("reason") for r in recs]
    assert [r["id"] for r in recs] == ["read:1", "read:2", "read:3"]
    assert [r["answer"] for r in recs] == [
        "show telemetry ietf subscription all: answered", "show ip bgp summary: answered",
        "show bgp ipv6 unicast summary: answered"]
    edge1 = engine.of("edge1")
    assert len(edge1) == 3 and all(s["username"] == "mercury-ro" for s in edge1)
    for before, after in zip(edge1, edge1[1:]):
        assert after["start"] >= before["end"], "one device's reads one after another"
    assert engine.deploy == [], "never the deploy account's session"
    assert device_ops.holder(NETWORK, "edge1") is None, "no hold left behind"


def test_reads_of_two_devices_still_run_at_once(engine):
    """(b) edge1's read and edge2's overlap in time: the grouping is per device, never every
    read one after another."""
    recs = passed([ask("bgp_summary"), ask("bgp_summary", device="edge2")], scope())
    assert [r["verdict"] for r in recs] == ["run", "run"], [r.get("reason") for r in recs]
    (one,), (two,) = engine.of("edge1"), engine.of("edge2")
    assert overlap(one, two), (one, two)


def test_a_device_another_operation_holds_is_refused_by_name_and_the_rest_run(engine):
    """(c) edge2 held by a deploy in another thread: its read is refused by name and never
    waited for (the deploy still holds it when the pass returns); edge1's two reads both run,
    in order."""
    held, done = threading.Event(), threading.Event()

    def deploy():
        with device_ops.hold(NETWORK, "edge2", "deploy", "admin@example.invalid"):
            held.set()
            done.wait(30)

    other = threading.Thread(target=deploy)
    other.start()
    try:
        assert held.wait(30)
        recs = passed([ask("bgp_summary"), ask("bgp_summary", device="edge2"),
                       ask("bgp_summary6")], scope())
        still = device_ops.holder(NETWORK, "edge2")
    finally:
        done.set()
        other.join(30)
    assert [r["verdict"] for r in recs] == ["run", "failed", "run"], recs
    assert recs[1]["reason"].startswith("the read failed: RuntimeError: skipped: edge2 is "
                                        "being deployed to by admin@example.invalid"), recs[1]
    assert still and still["operation"] == "deploy", "refused, never queued behind it"
    assert engine.of("edge2") == [], "no session opened on the held device"
    assert [r["answer"] for r in (recs[0], recs[2])] == [
        "show ip bgp summary: answered", "show bgp ipv6 unicast summary: answered"]


def test_a_read_reaching_no_device_runs_beside_a_devices_reads(engine):
    """(d) The stream's series (a ``local`` read) overlaps edge1's first read, while edge1's
    two reads run one after another."""
    series = Series()
    recs = passed([ask("bgp_summary"), ask("stream_series", subscription="101"),
                   ask("bgp_summary6")], scope(series=series))
    assert [r["verdict"] for r in recs] == ["run"] * 3, [r.get("reason") for r in recs]
    first, second = engine.of("edge1")
    assert second["start"] >= first["end"]
    (local,) = series.stamps
    assert overlap(local, first), (local, first)


def test_the_device_a_read_reaches_is_its_cli_operations_device_argument():
    """`device_of`, the one place a read names its device: a ``cli`` operation's ``device``
    argument; a ``local`` read of the same device reaches none."""
    from modules.ai import fixit_reads as FR
    assert RL.device_of(FR.FAMILY, {"op": "bgp_summary", "args": {"device": "edge1"}}) == \
        "edge1"
    assert RL.device_of(FR.FAMILY, {"op": "stream_series",
                                    "args": {"device": "edge1", "subscription": "101"}}) is None
