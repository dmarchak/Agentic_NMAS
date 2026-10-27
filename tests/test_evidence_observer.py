"""The monitoring side over an alert's window (C1896, the first slice of C1722): the evidence
pack's `observer` section. modules/evidence_observer.py, modules/evidence_pack.py
(`observer_section`), modules/ai/explain.py (`vocabulary`, `as_sent`).

**The captures** (tests/fixtures/prometheus/observer/), the lab's Prometheus asked the module's
OWN six questions read-only on the NMAS host via LAN (`scripts/nmas-host nmas`), 2026-10-27
~05:3x UTC, each answer kept as Prometheus gave it:
- ``walk2_r1/``: Walk 2's alert, r1's "Device unreachable (SNMP)" fired 2026-10-22 18:01:50Z,
  its onset 17:59:50Z (the window 17:44:50 to 18:01:50), for the devices of its rebuilt pack's
  health section (r1, r2, r3, r4, s1, s3, s4, r6, r8, s2). Seven jobs poll them; every target of
  `cisco_8000v` (6 of 6) and `cisco_vios_l2` (4 of 4) failed in the window, each failure
  running to (or near) its timeout, none refused; the host Prometheus runs on at its usual CPU
  and load (C1485's contention was on the lab host, beneath the devices, not here).
- ``quiet_s5/``: case 20's healthy baseline, s5's window of 2026-10-25 15:35 to 16:00 (s5, r8,
  r2): six jobs, no scrape failed.
- ``status_config.json``: Prometheus's configuration as it is (the jobs' intervals and
  timeouts; it holds no secret: its only addresses are loopback ones).
A planted case is said where it is made, each a minimal edit of a capture.

The fake (`Observed`) answers each question from its capture only when the question is the
module's own for the captured window (its time, its range, its bound), so a capture never
answers a question it was not the answer to.
"""
import copy
import json
import os
import re

import pytest

from modules import evidence_observer as O
from modules import evidence_pack as EP
from tests.test_ai_explain import _answer, world  # noqa: F401 (the fixture)
from tests.test_device_v2 import lab  # noqa: F401 (the fixture)
from tests.test_evidence_pack import V6, _alerts, _build, _section, pack_lab  # noqa: F401
from tests.test_history_ask_logs import NOW

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAPTURES = os.path.join(ROOT, "tests", "fixtures", "prometheus", "observer")
#: The two windows captured: (folder, onset, the alert's time, the health section's devices).
WALK = ("walk2_r1", 1792691990.0, 1792692110.0,
        ["r1", "r2", "r3", "r4", "s1", "s3", "s4", "r6", "r8", "s2"])
QUIET = ("quiet_s5", 1792943400.0, 1792944000.0, ["s5", "r8", "r2"])
#: The jobs polling Walk 2's devices, as Prometheus named them.
WALK_JOBS = ["bgp", "cisco_8000v", "cisco_ipsla", "cisco_vios_l2", "lldp", "ospf", "ospfv3"]


def _load(folder, name):
    with open(os.path.join(CAPTURES, folder, name) if folder else os.path.join(CAPTURES, name),
              encoding="utf-8") as fh:
        return json.load(fh)


class _Resp:
    def __init__(self, body):
        self._b = body

    def json(self):
        return self._b


def kind(path: str, q: str) -> str:
    """Which of the observer's questions *q* is, or "" for any other."""
    if path.endswith("status/config"):
        return "config"
    if q.startswith("count by (job) (count_over_time(up{device"):
        return "jobs"
    if '"targets_failed"' in q:
        return "figures"
    if '"failing"' in q:
        return "minutes"
    if "node_load1" in q:
        return "host" if path.endswith("query_range") else "hostnow"
    return ""


class Observed:
    """Prometheus answering the observer's questions from one window's captures. *window* the
    captured one (folder, onset, at, names); *strict* checks each question is the module's own
    for it. *edit* {question: fn(body) -> body} plants a case; *fail* {question: error}."""

    def __init__(self, window=WALK, strict=True, edit=None, fail=None, configured=True):
        self.folder, self.onset, self.at, self.names = window
        self.strict, self.edit, self.fail = strict, edit or {}, fail or {}
        self.configured, self.asked = configured, []
        self.url = "http://prometheus.test"

    def is_configured(self):
        return self.configured

    def expected(self, k, params):
        from modules import evidence_health as H
        win = H.window(self.onset, self.at)
        jobs = sorted({r["metric"]["job"] for r in _load(self.folder, "jobs.json")["data"][
            "result"]})
        q = O.job_queries(jobs, win["seconds"])
        h = O.host_queries(win["seconds"])
        at = {"time": f"{win['end']:.3f}", "timeout": f"{O.QUERY_TIMEOUT_S}s"}
        rng = {"start": f"{win['start']:.3f}", "end": f"{win['end']:.3f}", "step": "60",
               "timeout": f"{O.QUERY_TIMEOUT_S}s"}
        return {"jobs": dict(at, query=O.jobs_query(self.names, win["seconds"])),
                "figures": dict(at, query=q["figures"]),
                "minutes": dict(rng, query=q["minutes"]),
                "host": dict(rng, query=h["range"]),
                "hostnow": dict(at, query=h["now"]), "config": {}}[k]

    def _get(self, path, **params):
        k = kind(path, params.get("query", ""))
        assert k, (path, params.get("query", "")[:80])
        self.asked.append(dict(params, path=path, kind=k))
        if self.strict:
            assert params == self.expected(k, params), k
        if k in self.fail:
            return {"ok": False, "error": self.fail[k]}
        body = _load("" if k == "config" else self.folder,
                     "status_config.json" if k == "config" else f"{k}.json")
        if k in self.edit:
            body = self.edit[k](copy.deepcopy(body))
        return {"ok": True, "response": _Resp(body)}


def _read(window=WALK, **kw):
    prom = Observed(window, **kw)
    _f, onset, at, names = window
    return O.read("Lab", names, onset, at, prom=prom), prom


def _by(got):
    return {p["ref"]: p for p in got["pieces"]}


# ------------------------------------------------------------------- the pieces, measured

class TestTheCollectorsSide:
    def test_a_fleet_wide_failure_every_target_failing_and_the_host_as_usual(self):
        """Walk 2's window: every target of both SNMP device jobs failed, each failure ran to
        its timeout (none refused), while the collector's host was at its usual CPU and load."""
        got, _p = _read()
        by = _by(got)
        assert sorted(r for r in by if r.startswith("observer:job:")) == [
            f"observer:job:{j}" for j in WALK_JOBS]
        for job, n in (("cisco_8000v", 6), ("cisco_vios_l2", 4)):
            p = by[f"observer:job:{job}"]
            assert p["state"] == "ok" and p["targets"] == n and p["targets_failed"] == n, p
            assert p["failed"] > 0 and p["refused_targets"] == 0
            assert p["quickest_failed_s"] >= O.REFUSED_UNDER_S
            assert p["slowest_s"] == p["timeout_s"], "the slowest scrape ran to its timeout"
            assert p["first_failing_at"] and p["minutes_half_failing"] >= 2
        r8k = by["observer:job:cisco_8000v"]
        assert (r8k["failed"], r8k["scrapes"], r8k["timeout_s"], r8k["quickest_failed_s"]) == (
            34, 204, 30.0, 30.0)
        assert (r8k["most_failing"], r8k["most_failing_of"]) == (5, 6)
        assert r8k["timeout_from"] == "Prometheus's configuration as it is now"
        # The jobs that walk less failed nothing: the trouble is the big walks, not the poller.
        for job in ("bgp", "cisco_ipsla", "lldp", "ospf", "ospfv3"):
            assert by[f"observer:job:{job}"]["failed"] == 0, job
        ex = by["observer:exporter"]
        assert ex["state"] == "ok" and ex["jobs"] == WALK_JOBS and ex["refused_targets"] == 0
        assert (ex["packets_sent"], ex["packets_retried"]) == (9372, 354)
        assert "not collected" in ex["self_why"]
        cpu, load, mem = (by[f"observer:host:{k}"] for k in ("cpu", "load", "memory"))
        assert cpu["instance"] == load["instance"] == mem["instance"] == "localhost:9100"
        assert cpu["avg"] <= cpu["usual"] and load["avg"] <= load["usual"], (cpu, load)
        assert load["max"] < load["cpus"] == 4, "never a CPU's worth of load per CPU"
        assert mem["min"] > 50 and mem["unit"] == "percent"

    def test_a_quiet_window_shows_no_target_failing(self):
        got, _p = _read(QUIET)
        jobs = [p for p in got["pieces"] if p["what"].startswith("job:")]
        assert len(jobs) == 6 and all(p["state"] == "ok" for p in jobs)
        assert all(p["failed"] == 0 and p["targets_failed"] == 0 for p in jobs)
        assert all(p["minutes_failing"] == 0 and p["quickest_failed_s"] is None for p in jobs)
        assert _by(got)["observer:exporter"]["packets_retried"] == 1

    def test_each_piece_names_its_reference_its_read_state_and_its_read_time(self):
        got, _p = _read()
        assert [p["ref"] for p in got["pieces"]][-4:] == [
            "observer:exporter", "observer:host:cpu", "observer:host:load",
            "observer:host:memory"]
        for p in got["pieces"]:
            assert p["ref"] == f"observer:{p['what']}" and p["state"] in EP.STATES
            assert p["read_at"] == "2026-10-22T18:01:50Z"
        assert got["window"]["from"] == "2026-10-22T17:44:50Z"
        assert got["errors"] == [] and got["jobs_total"] == 7

    def test_six_bounded_questions_at_the_alerts_time_aggregated_by_job(self):
        """The strict fake already holds each question to the module's own for the window; here
        their count, their bound, and that none asks per target."""
        got, prom = _read()
        assert got["asked"] == 6 and [a["kind"] for a in prom.asked] == [
            "jobs", "config", "figures", "minutes", "host", "hostnow"]
        for a in prom.asked:
            if a["kind"] != "config":
                assert a["timeout"] == "5s", a
        figures = next(a for a in prom.asked if a["kind"] == "figures")["query"]
        assert all(re.search(r"\b(?:count|sum|max|min) by \(job\)", part)
                   for part in figures.split(" or ")), "every part aggregated by job"
        assert 'job=~"bgp|cisco_8000v|cisco_ipsla|cisco_vios_l2|lldp|ospf|ospfv3"' in figures


# ------------------------------------------------------------------- the states, said

class TestEachStateIsSaid:
    def test_a_refusing_exporter_is_told_from_a_timeout(self):
        """Planted (a minimal edit of Walk 2's figures): cisco_8000v's quickest failure 0.4 s and
        one target counted refused, as Prometheus answers a failure under 5 s."""
        def refused(body):
            for r in body["data"]["result"]:
                if r["metric"] == {"job": "cisco_8000v", "q": "quickest_failed"}:
                    r["value"][1] = "0.4"
            body["data"]["result"].append({"metric": {"job": "cisco_8000v", "q": "refused"},
                                           "value": [1792692110, "1"]})
            return body
        got, _p = _read(edit={"figures": refused})
        p = _by(got)["observer:job:cisco_8000v"]
        assert (p["quickest_failed_s"], p["refused_targets"]) == (0.4, 1)
        assert _by(got)["observer:exporter"]["refused_targets"] == 1
        assert "1 targets refused (a failure under 5s)" in O.line(p)
        assert "refused" not in O.line(_by(_read()[0])["observer:job:cisco_8000v"])

    def test_the_exporter_s_own_scrape_is_read_when_prometheus_scrapes_it(self):
        got, _p = _read(edit={"figures": with_self_scrape})
        ex = _by(got)["observer:exporter"]
        assert ex["self"] == {"snmp_exporter": {"scrapes": 17, "failed": 2}}
        assert "self_why" not in ex
        assert O.line(ex).endswith("; its own scrape snmp_exporter 2/17 failed")
        assert "its own scrape not collected" in O.line(_by(_read()[0])["observer:exporter"])

    def test_a_question_that_fails_is_said_on_each_of_its_pieces(self):
        got, _p = _read(fail={"figures": "Timed out after 5.0s", "host": "HTTP 503"})
        by = _by(got)
        for job in WALK_JOBS:
            assert by[f"observer:job:{job}"]["state"] == "unreadable"
            assert by[f"observer:job:{job}"]["why"].startswith("Prometheus could not be asked")
        assert by["observer:exporter"]["state"] == "unreadable"
        for k in ("cpu", "load", "memory"):
            assert by[f"observer:host:{k}"]["state"] == "unreadable"
        assert "figures: Prometheus could not be asked (Timed out after 5.0s)" in got["errors"]

    def test_no_prometheus_is_not_configured_and_nothing_is_asked(self):
        got, prom = _read(configured=False)
        assert {p["state"] for p in got["pieces"]} == {"not_configured"}
        assert prom.asked == [] and got["asked"] == 0

    def test_devices_no_job_polls_and_a_host_with_no_node_exporter_are_absent(self):
        """Planted: Prometheus holding no up series for the devices, and no node exporter on its
        own host (both answers emptied)."""
        def empty(body):
            body["data"]["result"] = []
            return body
        got, prom = _read(edit={"jobs": empty, "host": empty})
        by = _by(got)
        assert by["observer:jobs"]["state"] == "absent"
        assert "Prometheus holds no up series for r1, r2" in by["observer:jobs"]["why"]
        assert by["observer:exporter"]["state"] == "absent"
        for k in ("cpu", "load", "memory"):
            assert by[f"observer:host:{k}"]["state"] == "absent"
            assert "localhost, 127.0.0.1 or [::1]" in by[f"observer:host:{k}"]["why"]
        assert [a["kind"] for a in prom.asked] == ["jobs", "host", "hostnow"]

    def test_a_timeout_the_configuration_cannot_give_is_said(self):
        got, _p = _read(fail={"config": "HTTP 404"})
        p = _by(got)["observer:job:cisco_8000v"]
        assert p["timeout_s"] is None and "could not be read (HTTP 404)" in p["timeout_from"]
        assert "timeout -s" in O.line(p)


# ------------------------------------------------------------------- IPv6 beside IPv4

class TestTheCollectorsHostByAddress:
    @pytest.mark.parametrize("instance,local", [
        ("localhost:9100", True), ("127.0.0.1:9100", True), ("[::1]:9100", True),
        ("192.0.2.10:9100", False), ("[2001:db8::10]:9100", False), ("[::1]", False)])
    def test_the_node_exporter_on_prometheus_s_own_host_is_a_loopback_instance(self, instance,
                                                                               local):
        assert bool(re.fullmatch(O.LOCAL_INSTANCE, instance)) is local

    def test_an_ipv6_loopback_instance_is_read_as_the_host(self):
        """Planted: the host's answers with the instance [::1]:9100 (a node exporter reached over
        IPv6 loopback) in place of localhost:9100."""
        def v6(body):
            for r in body["data"]["result"]:
                r["metric"]["instance"] = "[::1]:9100"
            return body
        got, _p = _read(edit={"host": v6, "hostnow": v6})
        cpu = _by(got)["observer:host:cpu"]
        assert cpu["instance"] == "[::1]:9100" and cpu["cpus"] == 4 and cpu["usual"] is not None
        assert O.line(cpu).startswith("observer:host:cpu ([::1]:9100): busy ")


# ------------------------------------------------------------------- as a model reads it

def test_one_line_per_piece_its_reference_first():
    got, _p = _read()
    lines = O.lines(got["pieces"])
    assert len(lines) == len(got["pieces"])
    assert [ln.split()[0].rstrip(":") for ln in lines] == [p["ref"] for p in got["pieces"]]
    by = dict(zip([p["ref"] for p in got["pieces"]], lines))
    assert by["observer:job:cisco_8000v"] == (
        "observer:job:cisco_8000v (6 targets, every 30s, timeout 30s): 34/204 scrapes failed "
        "on 6 of 6 targets; failing 17:47:50-18:01:50, most at once 5 of 6 at 17:47:50, 5 of "
        "18 minutes failing, 2 with half or more; slowest 30s, quickest failure 30s")
    assert by["observer:host:load"].endswith("usual 1.4 on 4 CPUs")


# ------------------------------------------------------------------- in the pack

def with_self_scrape(body):
    """Planted (a minimal edit of the figures' answer): an SNMP exporter Prometheus scrapes on
    its own, job `snmp_exporter`, 17 scrapes of which 2 failed, as the figures' question would
    answer for a target exposing snmp_exporter_build_info (the lab's Prometheus scrapes none)."""
    body["data"]["result"] += [
        {"metric": {"job": "snmp_exporter", "q": "self_scrapes"}, "value": [1792692110, "17"]},
        {"metric": {"job": "snmp_exporter", "q": "self_failed"}, "value": [1792692110, "2"]}]
    return body


def _install(monkeypatch, window=WALK, **kw):
    """The observer's questions answered from *window*'s captures (not held to the pack's own
    window: the pack lab's alert is of 2026-10-15), every other question by the pack lab's own
    fake. tests/v2_context.py's alert evidence provider installs it too."""
    from modules.integrations.prometheus import PrometheusIntegration
    inner = PrometheusIntegration._get
    fake = Observed(window, strict=False, **kw)

    def get(prom, path, **params):
        if kind(path, params.get("query", "")):
            return fake._get(path, **params)
        return inner(prom, path, **params)
    monkeypatch.setattr(PrometheusIntegration, "_get", get)
    return fake


@pytest.fixture
def observed_lab(pack_lab, monkeypatch):  # noqa: F811
    _install(monkeypatch)
    return pack_lab


class TestInThePack:
    def _packs(self, monkeypatch):
        inst = EP.firing(_alerts(V6))[0]
        live = _build(_alerts(V6))
        with monkeypatch.context() as m:
            m.setattr(EP, "_now", lambda: NOW + 3600)
            replay = _build(_alerts(V6))
        history = EP.build(inst, store="grafana-alerts", value_at="", now=NOW, mode="history")
        return {"live": live, "replay": replay, "history": history}

    def test_live_replayed_and_rebuilt_packs_hold_it_marked(self, observed_lab, monkeypatch):
        packs = self._packs(monkeypatch)
        for k, pack in packs.items():
            sec = _section(pack, "observer")
            assert pack["schema"] == EP.SCHEMA == 6 and EP.intact(pack), k
            assert [s["name"] for s in pack["sections"]] == list(EP.SECTIONS), k
            assert sec["state"] == "ok" and sec["window"]["to"] == pack["built_at"], k
            assert "observer:job:cisco_8000v" in {p["ref"] for p in sec["pieces"]}, k
            assert EP.read_state(pack, "observer:host:load") == "ok", k
            assert EP.resolve(pack, "observer:exporter")["what"] == "exporter", k
            assert "as it is now" in sec["timeouts_from"]
        assert _section(packs["live"], "observer")["provenance"] == "captured"
        for k in ("replay", "history"):
            sec = _section(packs[k], "observer")
            assert sec["provenance"] == "rebuilt", k
            assert "Prometheus asked over the alert's window" in sec["provenance_words"], k

    def test_a_piece_not_measured_is_not_read(self, pack_lab, monkeypatch):
        """Its read state is its own, as a health figure's: a host piece Prometheus could not
        answer is not evidence, though the section was read."""
        from modules.integrations.prometheus import PrometheusIntegration
        inner = PrometheusIntegration._get
        fake = Observed(WALK, strict=False, fail={"host": "HTTP 503"})
        monkeypatch.setattr(PrometheusIntegration, "_get", lambda p, path, **kw: (
            fake._get(path, **kw) if kind(path, kw.get("query", "")) else inner(p, path, **kw)))
        pack = _build(_alerts(V6))
        assert _section(pack, "observer")["state"] == "ok"
        assert EP.read_state(pack, "observer:host:cpu") == "unreadable"
        assert EP.read_state(pack, "observer:job:cisco_8000v") == "ok"

    def test_a_pack_with_no_device_says_so(self, pack_lab):
        pack = _build(_alerts("192.0.2.250"))
        sec = _section(pack, "observer")
        assert sec["state"] == "absent" and sec["pieces"] == []


# ------------------------------------------------------------------- what Explain sends

class TestExplainReadsIt:
    def _pack(self, world, monkeypatch):
        _install(monkeypatch)
        pack = _build(_alerts(V6))
        assert EP.record(pack)["ok"]
        return pack

    def _ask(self, world, pack):
        from modules.ai import explain, triggers
        from tests.ai_person import pressed_by
        # A person's press (C1843): the trigger names the request's own verified actor.
        with pressed_by("operator@example.com"):
            return explain.explain(pack["id"], actor="operator@example.com",
                                   trigger=triggers.person("operator@example.com"),
                                   send=world.send, today="2026-10-27")

    def test_the_card_draws_each_piece(self, world, monkeypatch):
        from html import unescape
        pack = self._pack(world, monkeypatch)
        c = world.lab["client"]
        page = unescape(c.get(f"/v2/monitoring/alerts/pack/{pack['id']}").get_data(as_text=True))
        assert "The monitoring side over the window" in page
        assert f'id="{pack["id"]}-observer:job:cisco_8000v"' in page
        assert "cisco_8000v</strong> job: 34 of 204 scrapes failed, on 6 of its 6 targets" in page
        assert "slowest 30.0 s of a 30 s timeout, quickest failure 30.0 s" in page
        assert ("<strong>SNMP exporter</strong> <span class=\"muted small\">(bgp, cisco_8000v, "
                "cisco_ipsla, cisco_vios_l2, lldp, ospf, ospfv3)</span>: 354 of 9372 packets "
                "retried") in page
        assert "at most 5 of 6 at once at" in page and "5 of 18 minutes failing" in page
        assert "not collected: Prometheus scrapes no SNMP exporter of its own" in page
        assert "load (1 min): min 0.6, avg 1.2, max 2.7" in page and "usual 1.4 on 4 CPUs" in page
        assert "each across all its targets; the SNMP exporter; the host Prometheus runs on" in page

    def test_it_goes_as_one_line_per_piece_and_its_format_is_in_the_prefix(self, world,
                                                                          monkeypatch):
        pack = self._pack(world, monkeypatch)
        world.answer = _answer(pack)
        assert self._ask(world, pack)["ok"] is True
        body = world.sent[-1]["body"]
        user = body["messages"][0]["content"]
        sent = json.loads(re.search(r'<data name="pack">(.*?)</data>', user, re.S).group(1))
        obs = next(s for s in sent if s["name"] == "observer")
        assert "pieces" not in obs and "what" not in obs
        assert obs["lines"] == O.lines(_section(pack, "observer")["pieces"])
        system = json.dumps(body["system"])
        assert "observer is the monitoring side over the health section" in system
        assert ("When several devices fail at once from one collector, the collector and what "
                "is beneath the devices are candidate causes") in system

    def test_a_cited_piece_is_accepted_and_an_unknown_one_is_couldnt_analyse(self, world,
                                                                             monkeypatch):
        pack = self._pack(world, monkeypatch)
        world.answer = _answer(pack, hypotheses=[{
            "claim": "The polling of r1 timed out with every target of its job.",
            "evidence_refs": ["observer:job:cisco_8000v", "observer:host:load", "alert"],
            "confirm_with": "show logging"}])
        got = self._ask(world, pack)
        assert got["ok"] is True, got
        assert [c["ref"] for c in got["answer"]["hypotheses"][0]["cites"]][:2] == [
            "observer:job:cisco_8000v", "observer:host:load"]
        world.answer = _answer(pack, hypotheses=[{
            "claim": "x", "evidence_refs": ["observer:job:nope"],
            "confirm_with": "show logging"}])
        got = self._ask(world, pack)
        assert got["error"] == "couldnt_analyse"
        assert "cites 'observer:job:nope', which is not in the pack" in got["detail"]
