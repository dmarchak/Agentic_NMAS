"""The evidence pack's network context, captured when the pack is built (the operator's ruling
of 2026-10-25, built as part of P1): the observed overlay kept with the pack and Explain's only
source of it (C1712), and the health figures of every device within two hops as of the alert's
time (C1714). modules/evidence_pack.py (`observed_section`, `overlay_of`, `health_section`),
modules/evidence_health.py, modules/network_model.py (`capture`), modules/ai/explain.py.

On test_ai_explain's world (the pack built by the real builder from the real captures: r1 by
IPv6 firing `Interface error rate elevated`, an instruction planted in an interface
description) with the network's intent the eight REAL fleet configs committed
(tests/test_network_model.py's `commit_fleet`), an inventory naming each with a NetBox id, and
the Topology reader's value built by the real reader from the real captures (read at 08:20:00,
the pack built at 08:25:00, the Loki capture's end).

- **Heartbeats** are the Loki capture's own (tests/fixtures/loki/ask_lines_labelled.json,
  2026-10-15: s3's two in the window, 08:14:55 and 08:24:41, a 586 s gap).
- **CPU, scrapes and discards** are PLANTED series in Prometheus's matrix shape, a sample a
  minute over the window with spikes at stated times: no capture holds their values. Which
  metric each platform answers is measured (tests/fixtures/prometheus/ask_device_names_s1.json:
  s1, an IOS switch, carries cpuAvgBusy5 and no cpmCPUTotal; the fleet's names carry
  cpmCPUTotal5minRev); the values are C1547's shape (s3's CPU peaking at 57% at 08:13 and its
  discards at 10.9/s at 08:12 while its scrapes fail, all back down by the alert at 08:25), s2
  given no CPU series and s4 no discard counters, so absent is drawn. The fake answers each
  question as Prometheus would: only the devices its selector names, inside its window.

The tests: the overlay captured at build, "as of" the alert's time, its items within two hops;
a read the store does not have, or later than the alert, said; Explain overlaying the capture
with every live read planted to fail; a pack without the overlay saying so; health figures
for hops 0 to 2 through the shared segment, each with its read time and its id; an unreadable,
an unconfigured and an absent figure said, never omitted; four questions in all, at the
alert's time; the hash covering both sections; a planted secret in a scrape job's label never
in the pack or the bytes sent; the request's blocks in order with the overlay never as pack
data; the check resolving a cited figure and failing an unknown one, and, with the topology
class off, only the alert's device's figures sent and a neighbour's not citable; a 900-device
fleet captured within its bound, asking four questions, at most `MAX_DEVICES` devices kept.
"""
import copy
import json
import re
import time

import pytest
import yaml

from modules import evidence_health as H
from modules import evidence_pack as EP
from modules import network_model as NM
from tests.test_ai_explain import _answer, _explain, world  # noqa: F401 (fixtures)
from tests.test_device_v2 import _store, _unstore, lab  # noqa: F401 (the fixture)
from tests.test_evidence_pack import (DEVICES, INJECTION, V6, _alerts, _build,  # noqa: F401
                                      _section, pack_lab)
from tests.test_history_ask_logs import NOW, go_unquote
from tests.test_network_model import READ_AT, commit_fleet, scale_fleet, store_observed
from tests.test_topology_graph import _graph

HOSTS = ["r1", "r2", "r3", "r4", "s1", "s2", "s3", "s4"]
AT = "2026-10-15T08:25:00Z"
#: A secret's shape planted in a scrape job's label (Prometheus's labels reach Mercury as
#: the exporter's configuration wrote them).
SECRET = "Pl4ntedJobS3cret"
PLANTED_JOB = f"snmp-server community {SECRET} RO"
#: The incident's window for the planted alert: its onset 08:15:00 less 15 minutes, to 08:25.
FROM = NOW - 1500


def _t(hhmm):
    """2026-10-15 at *hhmm* UTC, as epoch seconds."""
    import calendar
    return float(calendar.timegm(time.strptime(f"2026-10-15T{hhmm}:00Z", "%Y-%m-%dT%H:%M:%SZ")))


#: The planted answers (the module's docstring says what is measured and what is planted): a
#: series a minute apart over the window, a base value with spikes at stated times. s3's CPU
#: and discards spike DURING the incident and are back down by the alert's time (C1547's shape:
#: a spike that has passed is the max, with its time).
CPU = {"r1": ("cpmCPUTotal5minRev", 9.0, {"08:16": 14.0}),
       "r2": ("cpmCPUTotal5minRev", 8.0, {}), "r3": ("cpmCPUTotal5minRev", 10.0, {}),
       "r4": ("cpmCPUTotal5minRev", 7.0, {}), "s1": ("cpuAvgBusy5", 18.0, {}),
       "s3": ("cpuAvgBusy5", 41.0, {"08:12": 50.0, "08:13": 57.0}),
       "s4": ("cpuAvgBusy5", 17.0, {})}
#: {device: {job: [the minutes a scrape failed]}}.
SCRAPES = {**{h: {"snmp": []} for h in HOSTS},
           "s3": {"cisco_vios_l2": ["08:12", "08:13", "08:14"], "lldp": ["08:13"],
                  PLANTED_JOB: ["08:20"]}}
DISCARDS = {"r1": (0.0, {}), "r2": (0.1, {}), "r3": (0.0, {}), "r4": (0.0, {}),
            "s1": (0.2, {}), "s2": (0.0, {}), "s3": (0.5, {"08:12": 10.9})}


def _series(start, end, base, spikes, step=60):
    """``[[t, "v"]]`` *step* seconds apart from *start* to *end*, *spikes* by minute (a point
    the step does not land on is not answered, as a range query's evaluation misses it)."""
    out, t = [], start
    by = {_t(k): v for k, v in spikes.items()}
    while t <= end:
        out.append([t, str(by.get(t, base))])
        t += step
    return out


class _Resp:
    def __init__(self, body):
        self._b = body

    def json(self):
        return self._b


class Health:
    """Prometheus's answers to the health questions (the rest go to the pack's own fake), and
    a record of each question asked."""

    def __init__(self, monkeypatch):
        from modules.integrations.prometheus import PrometheusIntegration

        self.asked, self.fail = [], ""
        inner = PrometheusIntegration._get
        me = self

        def get(prom, path, **params):
            q = params.get("query", "")
            # The Neighbours view's `up` names its routing jobs; the health figures' does not.
            if not any(w in q for w in ("cpuAvgBusy5", "ifInDiscards")) and \
                    not (q.startswith("up{") and "job=~" not in q):
                return inner(prom, path, **params)
            me.asked.append(dict(params, path=path))
            if me.fail:
                return {"ok": False, "error": me.fail}
            return {"ok": True, "response": _Resp({"status": "success", "data": {
                "resultType": "matrix", "result": me.rows(q, path, params)}})}
        monkeypatch.setattr(PrometheusIntegration, "_get", get)

    @staticmethod
    def rows(q, path, params):
        """As Prometheus answers: only the devices the selector names; a range vector's raw
        samples (an instant query of `x[Ns]`) or a range query's points, inside the window."""
        m = re.search(r'device(=~?)"', q)
        want, _end = go_unquote(q, m.end() - 1)
        named = [h for h in HOSTS if (re.fullmatch(want, h) if m.group(1) == "=~"
                                      else h == want)]
        if path.endswith("query_range"):
            start, end = float(params["start"]), float(params["end"])
        else:
            end = float(params["time"])
            start = end - int(re.search(r"\[(\d+)s\]", q).group(1))
        out = []
        for h in named:
            if "cpuAvgBusy5" in q and h in CPU:
                metric, base, spikes = CPU[h]
                out.append({"metric": {"__name__": metric, "device": h},
                            "values": _series(start, end, base, spikes)})
            elif q.startswith("up{"):
                for job, fails in SCRAPES.get(h, {}).items():
                    out.append({"metric": {"__name__": "up", "device": h, "job": job},
                                "values": _series(start, end, 1, {k: 0 for k in fails})})
            elif "ifInDiscards" in q and h in DISCARDS:
                base, spikes = DISCARDS[h]
                out.append({"metric": {"device": h},
                            "values": _series(start, end, base, spikes,
                                              int(float(params.get("step") or 60)))})
        return out


@pytest.fixture
def ctx(world, monkeypatch):  # noqa: F811
    ips = {"r1": V6, "r2": DEVICES[0]["ip"], "r3": DEVICES[2]["ip"]}
    rows = [{"hostname": h, "ip": ips.get(h, f"192.0.2.{40 + i}"), "_netbox_id": 300 + i,
             "_site": "site-a", "role": "router" if h.startswith("r") else "switch",
             "platform": "cisco_iosxe" if h.startswith("r") else "cisco_ios",
             "device_type": "cisco_xe" if h.startswith("r") else "cisco_ios",
             "username": "nmas"} for i, h in enumerate(HOSTS)]
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda path=None: [dict(r) for r in rows])
    commit_fleet(world.lab["repo"])
    store_observed()
    NM.forget()
    world.health = Health(monkeypatch)
    world.ids = {r["hostname"]: f"dev:{r['_netbox_id']}" for r in rows}
    world.pack = _build(_alerts(V6, extra_labels={"ifAlias": INJECTION}))
    assert EP.record(world.pack)["ok"]
    yield world
    NM.forget()
    _unstore(NM.OBSERVED_READER)


def _fig(pack, host_id, fig):
    return EP.resolve(pack, f"health:{host_id}:{fig}")


def _no_live_read(monkeypatch):
    """Every way to the observed state now planted to fail: the overlay is the pack's."""
    from modules import reader_job

    real = reader_job.read_cached

    def guarded(name):
        if name == NM.OBSERVED_READER:
            raise AssertionError("Explain read the Topology reader's store")
        return real(name)

    def boom(*a, **k):
        raise AssertionError("Explain read the observed state")
    monkeypatch.setattr(reader_job, "read_cached", guarded)
    monkeypatch.setattr(NM, "observed", boom)


def _sub(w):
    user = w.sent[-1]["body"]["messages"][0]["content"]
    return yaml.safe_load(re.search(r'<data name="network_topology">\n(.*?)\n</data>', user,
                                    re.S).group(1))


def _pack_sent(w):
    user = w.sent[-1]["body"]["messages"][0]["content"]
    return json.loads(re.search(r'<data name="pack">\n(.*?)\n</data>', user, re.S).group(1))


# ------------------------------------------------------------------- the observed overlay

class TestTheCapturedOverlay:
    def test_captured_at_build_as_of_the_alerts_time(self, ctx):
        sec = _section(ctx.pack, "observed")
        assert sec["state"] == "ok", sec
        assert sec["as_of"] == AT and sec["as_of_words"] == f"as of {AT}, the alert's time"
        assert sec["observed_at"] == READ_AT and sec["subject"] == ctx.ids["r1"]
        assert sec["hops"] == 2
        ids = [p["id"] for p in sec["pieces"]]
        assert any(i.startswith("cable:") and ctx.ids["s3"] in i for i in ids)
        assert any(i.startswith("adj:ospf:") and ctx.ids["r1"] in i for i in ids)
        assert all(p["read_at"] == READ_AT for p in sec["pieces"])
        assert [p["ref"] for p in sec["pieces"]] == [f"observed:{n}" for n in
                                                     range(1, len(ids) + 1)]

    @pytest.mark.parametrize("case,state,words", [
        ("absent", "absent", "the Topology reader has not read yet"),
        ("later", "unreadable", "is later than 2026-10-15T08:25:00Z, the time it is asked for"),
    ])
    def test_a_read_that_cannot_be_used_is_said(self, ctx, case, state, words):
        if case == "absent":
            _unstore(NM.OBSERVED_READER)
        else:
            store_observed(at="2026-10-15T08:40:00Z")
        sec = _section(_build(_alerts(V6)), "observed")
        assert (sec["state"], sec["pieces"]) == (state, [])
        assert words in sec["why"] and sec["as_of"] == AT

    def test_explain_overlays_the_capture_and_reads_nothing_live(self, ctx, monkeypatch):
        """The network moves on after the alert: r1's adjacency to r3 goes down in a later
        read. Explain says what the pack captured, as of the alert, and asks no store."""
        graph = _graph()
        for link in graph["layers"]["ospf"]:
            if {link["a"], link["b"]} == {"r1", "r3"}:
                link.update(state="down", words="init")
        store_observed(at="2026-10-15T08:30:00Z", graph=graph)
        _no_live_read(monkeypatch)
        ctx.answer = _answer(ctx.pack)
        got = _explain(ctx)
        assert got["ok"] is True, got
        assert got["topology"]["observed"] == f"as of {AT}"
        sub = _sub(ctx)
        assert sub["observed"]["as_of"] == AT and sub["observed"]["read_at"] == READ_AT
        aid = NM._adj_id("ospf", ctx.ids["r1"], ctx.ids["r3"], "10.255.3.0/24")
        assert sub["adjacencies"][aid]["observed"]["state"] == "up"
        assert "2026-10-15T08:30:00Z" not in ctx.sent[-1]["bytes"]

    def test_a_pack_without_the_overlay_says_so(self, ctx, monkeypatch):
        """A pack built before overlays were captured (schema 1): no live read in its place."""
        old = copy.deepcopy(ctx.pack)
        old["sections"] = [s for s in old["sections"] if s["name"] not in ("observed",
                                                                            "health")]
        old["schema"] = 1
        old["hash"] = EP.digest(old)
        assert EP.record(old)["ok"]
        _no_live_read(monkeypatch)
        ctx.pack = old
        ctx.answer = _answer(old)
        got = _explain(ctx)
        assert got["ok"] is True, got
        words = "could not read (observed state not captured with this pack)"
        sub = _sub(ctx)
        assert sub["observed"]["state"] == words and sub["cables"] == words
        assert sub["adjacencies"] and all(a["observed"] == words
                                          for a in sub["adjacencies"].values())
        assert got["topology"]["observed"] == "could not read (observed state not captured " \
                                              "with this pack)"


# ------------------------------------------------------------------- the health figures

class TestTheHealthFigures:
    def test_every_device_within_two_hops_through_the_shared_segment(self, ctx):
        sec = _section(ctx.pack, "health")
        assert sec["state"] == "ok", sec
        hops = {p["device"]: p["hop"] for p in sec["pieces"]}
        assert hops == {"r1": 0, "r2": 1, "r3": 1, "r4": 1, "s1": 1, "s3": 1, "s4": 1,
                        "s2": 2}
        assert sec["devices_total"] == sec["devices_kept"] == 8
        for host in HOSTS:
            for fig in H.FIGURES:
                p = _fig(ctx.pack, ctx.ids[host], fig)
                assert p is not None, (host, fig)
                assert p["read_at"] == AT and p["state"] in EP.STATES and p["dev"] == \
                    ctx.ids[host]
        assert sec["as_of"] == AT and sec["pieces"][0]["device"] == "r1", \
            "the alert's device first"

    def test_the_window_is_from_15_minutes_before_the_onset_to_the_alert(self, ctx):
        """The planted alert's onset is 08:15:00 (its condition first held), found at 08:25."""
        w = _section(ctx.pack, "health")["window"]
        assert (w["from"], w["to"]) == ("2026-10-15T08:00:00Z", AT)
        assert w["basis"] == ("from 15 minutes before the onset (2026-10-15T08:15:00Z) to "
                              "the alert's time") and "bounded" not in w
        assert H.window(None, NOW)["start"] == NOW - 900
        assert "the onset is not recorded" in H.window(None, NOW)["basis"]
        long = H.window(NOW - 3 * 3600, NOW)
        assert long["start"] == NOW - H.MAX_WINDOW_SECONDS and "its last 70 minutes" in \
            long["bounded"]

    def test_a_spike_that_passed_by_the_alert_is_the_max_with_its_time(self, ctx):
        """C1547's shape: s3's CPU and discards peak during the incident and are back down by
        the alert's time; the line keeps the peak and when."""
        s3 = ctx.ids["s3"]
        cpu = _fig(ctx.pack, s3, "cpu")
        assert (cpu["metric"], cpu["min"], cpu["max"], cpu["peak_at"]) == (
            "cpuAvgBusy5", 41.0, 57.0, "2026-10-15T08:13:00Z")
        assert cpu["samples"] == 26 and cpu["avg"] == round((41 * 24 + 50 + 57) / 26, 1)
        dis = _fig(ctx.pack, s3, "discards")
        assert (dis["min"], dis["max"], dis["peak_at"], dis["unit"]) == (
            0.5, 10.9, "2026-10-15T08:12:00Z", "packets/s")
        assert dis["avg"] == round((0.5 * 25 + 10.9) / 26, 1)
        scr = _fig(ctx.pack, s3, "scrapes")
        assert (scr["scrapes"], scr["failed"]) == (78, 5)
        assert (scr["first_failed_at"], scr["last_failed_at"]) == (
            "2026-10-15T08:12:00Z", "2026-10-15T08:20:00Z")
        assert "cisco_vios_l2" in scr["jobs_failing"] and "lldp" in scr["jobs_failing"]

    def test_the_alerts_own_device_is_summarised_the_same_way(self, ctx):
        r1 = ctx.ids["r1"]
        cpu = _fig(ctx.pack, r1, "cpu")
        assert (cpu["metric"], cpu["min"], cpu["max"], cpu["peak_at"]) == (
            "cpmCPUTotal5minRev", 9.0, 14.0, "2026-10-15T08:16:00Z")
        assert _fig(ctx.pack, r1, "scrapes")["failed"] == 0
        assert _fig(ctx.pack, r1, "scrapes")["first_failed_at"] is None
        assert set(_fig(ctx.pack, r1, "discards")) >= {"min", "avg", "max", "peak_at"}

    def test_the_captured_heartbeats_their_longest_gap_and_when_it_ended(self, ctx):
        beat = _fig(ctx.pack, ctx.ids["s3"], "heartbeat")
        assert (beat["beats"], beat["max_gap_s"], beat["since_last_s"]) == (2, 586, 19)
        assert beat["max_gap_ended_at"] == beat["last_at"] == "2026-10-15T08:24:41Z"
        r1 = _fig(ctx.pack, ctx.ids["r1"], "heartbeat")
        assert (r1["beats"], r1["max_gap_s"], r1["max_gap_ended_at"]) == (
            3, 300, "2026-10-15T08:15:40Z")

    def test_each_figure_is_one_small_line(self, ctx):
        for p in _section(ctx.pack, "health")["pieces"]:
            assert not any(isinstance(v, (list, dict)) and k != "jobs_failing"
                           for k, v in p.items()), p
            assert len(json.dumps(p)) < 400, p

    def test_a_figure_nobody_holds_is_said_absent(self, ctx):
        cpu = _fig(ctx.pack, ctx.ids["s2"], "cpu")
        assert cpu["state"] == "absent"
        assert "Prometheus holds no CPU series for s2" in cpu["why"]
        assert "between 2026-10-15T08:00:00Z and 2026-10-15T08:25:00Z" in cpu["why"]
        assert _fig(ctx.pack, ctx.ids["s4"], "discards")["state"] == "absent"
        assert not {"min", "avg", "max", "peak_at"} & set(cpu), "nothing invented"

    def test_a_source_that_fails_is_said_on_each_figure(self, ctx, monkeypatch):
        ctx.health.fail = "Timed out after 10s"

        class Unset:
            url = ""

            def is_configured(self):
                return False
        pack = _build(_alerts(V6), loki=Unset())
        sec = _section(pack, "health")
        for host in HOSTS:
            for fig in ("cpu", "scrapes", "discards"):
                p = _fig(pack, ctx.ids[host], fig)
                assert p["state"] == "unreadable", p
                assert p["why"] == "Prometheus could not be asked (Timed out after 10s)"
            hb = _fig(pack, ctx.ids[host], "heartbeat")
            assert hb["state"] == "not_configured" and "no log store" in hb["why"]
        assert sec["state"] == "unreadable" and len(sec["pieces"]) == 4 * len(HOSTS)

    def test_four_questions_in_all_at_the_alerts_time(self, ctx):
        ctx.health.asked.clear()
        ctx.lab["loki"].asked.clear()
        _build(_alerts(V6))
        asked = ctx.health.asked
        assert len(asked) == 3, [a["query"][:60] for a in asked]
        # Each evaluated at the alert's time over the window: two raw range vectors at it,
        # one range query ending at it a point a minute.
        assert [a.get("time") or a["end"] for a in asked] == [f"{NOW:.3f}"] * 3
        assert all("[1500s]" in a["query"] for a in asked if a["path"].endswith("/query"))
        (rng,) = [a for a in asked if a["path"].endswith("query_range")]
        assert (rng["start"], rng["step"]) == (f"{FROM:.3f}", "60")
        # Nearest first: the alert's device, its hop 1 by name, then s2 at two.
        order = ["r1", "r2", "r3", "r4", "s1", "s3", "s4", "s2"]
        beats = [p for _path, p in ctx.lab["loki"].asked
                 if p.get("query", "") == H.heartbeat_query(order)]
        assert len(beats) == 1 and beats[0]["end"] == str(int(NOW * 1e9))
        assert beats[0]["start"] == str(int(FROM * 1e9))
        for a in asked:
            assert "device=~" in a["query"] and "s2" in a["query"]

    def test_the_hash_covers_both_sections(self, ctx):
        for name, key in (("health", "max"), ("observed", "state")):
            sec = _section(ctx.pack, name)
            i = next(n for n, p in enumerate(sec["pieces"]) if key in p)
            moved = copy.deepcopy(ctx.pack)
            s = next(x for x in moved["sections"] if x["name"] == name)
            s["pieces"][i][key] = "changed"
            assert EP.digest(moved) != ctx.pack["hash"] and not EP.intact(moved), name

    def test_a_planted_secret_in_a_label_never_reaches_the_pack_or_the_bytes_sent(self, ctx):
        scr = _fig(ctx.pack, ctx.ids["s3"], "scrapes")
        assert any("<redacted:snmp_community>" in j for j in scr["jobs_failing"])
        assert SECRET not in json.dumps(ctx.pack)
        ctx.answer = _answer(ctx.pack)
        assert _explain(ctx)["ok"] is True
        assert SECRET not in ctx.sent[-1]["bytes"]


# ------------------------------------------------------------------- Explain

def _citing(w, refs):
    a = _answer(w.pack)
    a["hypotheses"][0]["evidence_refs"] = refs
    return a


class TestExplainWithTheContext:
    def test_the_blocks_in_order_and_the_overlay_never_as_pack_data(self, ctx):
        ctx.answer = _answer(ctx.pack)
        assert _explain(ctx)["ok"] is True
        body = ctx.sent[-1]["body"]
        user, system = body["messages"][0]["content"], json.dumps(body["system"])
        assert re.findall(r'<data name="([^"]+)">', user) == ["network_topology", "pack",
                                                               "the_alert"]
        assert re.findall(r'<context name="([^"]+)">', body["system"][1]["text"]) == [
            "network", "pack_format", "topology_format"]
        names = [s["name"] for s in _pack_sent(ctx)]
        assert names == [n for n in EP.SECTIONS if n != "observed"]
        assert "health:<device id>:<figure>" in system
        assert not re.search(r"\d{4}-\d\d-\d\dT\d\d:\d\d", system)

    def test_a_cited_figure_resolves_and_an_unknown_one_is_couldnt_analyse(self, ctx):
        from html import unescape
        ref = f"health:{ctx.ids['s3']}:cpu"
        ctx.answer = _citing(ctx, [ref, ctx.ids["s3"]])
        got = _explain(ctx)
        assert got["ok"] is True, got
        assert got["answer"]["hypotheses"][0]["cites"][0] == {"ref": ref, "in_pack": True}
        r = ctx.lab["client"].post(f"/v2/monitoring/alerts/pack/{ctx.pack['id']}/explain",
                                   headers={"HX-Request": "true"})
        assert f'href="#{ctx.pack["id"]}-{ref}"' in unescape(r.get_data(as_text=True))
        for bad in (f"health:{ctx.ids['s3']}:memory", "health:dev:999:cpu"):
            ctx.answer = _citing(ctx, [bad])
            got = _explain(ctx)
            assert got["error"] == "couldnt_analyse", got
            assert f"cites {bad!r}, which is not in the pack" in got["detail"]

    def test_with_the_topology_class_off_only_the_alerts_device_figures_go(self, ctx,
                                                                           monkeypatch):
        from modules.ai import egress_classes
        monkeypatch.setattr(egress_classes, "topology_allowed", lambda net: {
            "allowed": False, "why": "the topology class is off for Lab"})
        ctx.answer = _citing(ctx, [f"health:{ctx.ids['r1']}:cpu"])
        assert _explain(ctx)["ok"] is True
        health = next(s for s in _pack_sent(ctx) if s["name"] == "health")
        assert {p["hop"] for p in health["pieces"]} == {0} and len(health["pieces"]) == 4
        assert "the topology class" in health["withheld"]
        ref = f"health:{ctx.ids['s3']}:cpu"
        ctx.answer = _citing(ctx, [ref])
        got = _explain(ctx)
        assert got["error"] == "couldnt_analyse"
        assert f"cites {ref!r}, which is not in the pack as sent" in got["detail"]


# ------------------------------------------------------------------- scale

def _captured(routers, monkeypatch):
    """The scale fleet of ``routers * 3`` devices, every adjacency observed up with its cable;
    r7's capture and its health read: ``(capture, devices, read, questions, expanded,
    observed adjacencies)``, the work counted (tests/test_network_model.py's `Expanded`)."""
    from tests.test_network_model import Expanded
    intents, inventory = scale_fleet(routers=routers)
    m = NM.build("Big", inventory, intents, {}, version={"key": "nm-scale"})
    m["edges"] = Expanded(m["edges"])
    monkeypatch.setattr(NM, "model_for", lambda net: (m, ""))
    names = {v: k for k, v in m["names"].items()}
    ospf, phys = [], []
    for a in m["adjacencies"].values():
        x, y = a["between"]
        ospf.append({"a": names[x], "b": names[y], "state": "up", "intended": True,
                     "network": a["id"].split(y + ":", 1)[1]})
        phys.append({"a": names[x], "b": names[y], "port_a": "Gi1", "port_b": "Gi2",
                     "state": "up", "kind": "both"})
    stored = {"value": {"configured": True, "networks": {"Big": {"layers": {
        "ospfv3": ospf, "physical": phys}}}}, "value_at": "2026-10-15T08:20:00Z"}
    asked = []

    class Fake:
        url = ""

        def is_configured(self):
            return True

        def _get(self, path, **params):
            asked.append(path)
            return {"ok": True, "response": _Resp({"status": "success",
                                                   "data": {"result": []}})}
    cap = NM.capture("Big", "r7", now=1792052460.0, stored=stored)
    devices, total = H.devices_of(cap, "r7")
    got = H.read("Big", devices, None, 1792052460.0, prom=Fake(), loki=Fake())
    return cap, devices, total, got, list(asked), list(m["edges"].asked), len(ospf)


def test_a_fleet_of_900_is_captured_by_work_that_does_not_grow_with_it(monkeypatch):
    """Machine-independent (the operator, 2026-10-25; CI #1177, C1741): the work counted at 90
    devices and at 900, never a wall-clock bound."""
    small = _captured(30, monkeypatch)
    cap, devices, total, got, asked, expanded, observed = _captured(300, monkeypatch)
    # Four questions for the whole set, at 90 devices and at 900.
    assert len(asked) == len(small[4]) == 4 and got["asked"] == 4
    # The two-hop walk expands the subject and its one-hop devices only, the same at both.
    assert len(expanded) == len(small[5]) == 1 + sum(
        1 for r in cap["reached"].values() if r["hop"] == 1)
    assert total == small[2] == len(devices) and len(got["pieces"]) == 4 * total
    # The overlay kept is the devices reached, not the fleet: the same at 900 as at 90, while
    # the read it is taken from holds ten times as much.
    assert observed == 10 * small[6]
    assert len(cap["overlay"]["routing"]) == len(small[0]["overlay"]["routing"])
    assert len(cap["overlay"]["cables"]) == len(small[0]["overlay"]["cables"])
    assert len(cap["overlay"]["routing"]) < observed / 50


def test_at_most_max_devices_nearest_first():
    reached = {f"dev:{n}": {"hop": 0 if n == 0 else 1 + n % 2, "via": ""} for n in range(900)}
    cap = {"ok": True, "reached": reached,
           "nodes": {d: {"name": f"d{d[4:]:0>4}"} for d in reached}}
    devices, total = H.devices_of(cap, "d0000")
    assert total == 900 and len(devices) == H.MAX_DEVICES
    assert devices[0] == ("dev:0", "d0000", 0)
    assert [h for _d, _n, h in devices] == sorted(h for _d, _n, h in devices)
    assert {h for _d, _n, h in devices} == {0, 1}
