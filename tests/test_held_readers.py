"""The device header, Devices and Neighbours draw what two readers hold (C3166's slice 3, the
operator's plan, 2026-11-12: "a new drained reader: the device header (every tab) and Devices";
"Neighbours: from the `adjacencies` reader").

Counted, never timed (CLAUDE.md: performance tests assert on work or growth), each through the
real reader and the real scheduler's waits (`reader_job.run_once`, `reader_job.next_wait`) on
the reader's own clock:

- **The drained reader** (modules/readers/drained_state.py): switched off (C552), ten idle
  minutes ask nothing at all (no network listed, no measurement) and announce only its
  keepalive; switched on, each run measures each network once, so the work over N intervals is
  N times the networks, bounded by the cadence and never by the pages; a network that fails
  keeps its last good verdicts, said, and every network failing is the read failing.
- **The adjacencies reader's views** (modules/readers/adjacencies.py `views`): its Prometheus
  queries do not grow with the fleet (four at 9 devices and at 90), and its comparisons are one
  per device per read; the tab's read (`neighbours.held_view`) compares and asks nothing.
- **Display only** (CLAUDE.md, the rule's Display only clause): no module of the heal pipeline
  or a deploy names either held value, by parsing (tests/test_attention_display_only.py's
  population and scan).
"""

import collections
import copy
from types import SimpleNamespace

import pytest

from modules import drained as D
from modules import reader_job as R
from modules.readers import adjacencies as ADJ
from modules.readers import drained_state as DS

T0 = 1_790_000_000.0
#: Ten idle minutes: ten of the drained reader's intervals, two of its keepalives, ten of the
#: adjacencies reader's.
IDLE_S = 600.0


@pytest.fixture
def store(monkeypatch, tmp_path):
    monkeypatch.setattr(R, "store_path", lambda name: str(tmp_path / f"{name}.json"))
    monkeypatch.setattr(R, "_AFTER_ANY_STORE", [])
    monkeypatch.setattr(R, "_LAST_ANNOUNCED", {})
    # Two registered networks; the reader keys each by its one id (C1903).
    monkeypatch.setattr("modules.nsot.listref._registry",
                        lambda: {"Lab": "lab", "Branch": "branch"})
    return tmp_path


def _idle(reader, seconds=IDLE_S):
    """Run *reader* on its own schedule over *seconds* of its clock: ``(runs, announced)``."""
    announced, runs, now = [], 0, T0
    while now < T0 + seconds:
        doc = R.run_once(reader, announce=lambda keys, by, ok: announced.append(keys),
                         clock=lambda: now)
        runs += 1
        now += R.next_wait(reader, doc)
    return runs, announced


class TestTheDrainedReaderIdle:
    def test_switched_off_ten_idle_minutes_ask_nothing(self, store, monkeypatch):
        asked = collections.Counter()

        def lists():
            asked["networks listed"] += 1
            return ["Lab"]

        def measure(name, now):
            asked["measured"] += 1
            return {}
        monkeypatch.setattr(DS, "_lists", lists)
        monkeypatch.setattr(D, "measure", measure)
        assert D.ENABLED is False
        runs, announced = _idle(DS.READER)
        assert runs == IDLE_S / DS.INTERVAL_SECONDS
        assert asked == {}, asked
        # Its value never moves: the first run and each keepalive announce, nothing else.
        assert len(announced) == 1 + int((IDLE_S - DS.INTERVAL_SECONDS) // DS.KEEPALIVE_SECONDS)

    def test_the_control_switched_on_each_run_measures_each_network_once(self, store,
                                                                         monkeypatch):
        measured = collections.Counter()

        def measure(name, now):
            measured[name] += 1
            return {"r2": {"drained": True, "judged": ["Gi3"]}, "s1": {"drained": False}}
        monkeypatch.setattr(D, "ENABLED", True)
        monkeypatch.setattr(DS, "_lists", lambda: ["Lab", "Branch"])
        monkeypatch.setattr(D, "measure", measure)
        runs, announced = _idle(DS.READER)
        assert runs == IDLE_S / DS.INTERVAL_SECONDS
        assert measured == {"Lab": runs, "Branch": runs}
        # The verdicts do not move after the first run: only the keepalive announces.
        assert len(announced) == 1 + int((IDLE_S - DS.INTERVAL_SECONDS) // DS.KEEPALIVE_SECONDS)
        assert D.current("Lab") == {"r2": {"drained": True, "judged": ["Gi3"]}}

    def test_a_page_read_measures_nothing(self, store, monkeypatch):
        monkeypatch.setattr(D, "ENABLED", True)
        monkeypatch.setattr(DS, "_lists", lambda: ["Lab"])
        monkeypatch.setattr(D, "measure", lambda name, now: {"r2": {"drained": True}})
        R.run_once(DS.READER, announce=None)

        def on_a_read(*a, **k):
            raise AssertionError("a held read measured")
        monkeypatch.setattr(D, "measure", on_a_read)
        for _ in range(100):
            assert D.state_of("Lab", "r2")["drained"] is True
            assert D.held("Lab")["verdicts"] == {"r2": {"drained": True}}


class TestTheDrainedReadersValue:
    def test_a_failed_network_keeps_its_last_good_verdicts_and_says_so(self, store,
                                                                       monkeypatch):
        monkeypatch.setattr(D, "ENABLED", True)
        monkeypatch.setattr(DS, "_lists", lambda: ["Lab", "Branch"])
        monkeypatch.setattr(D, "measure", lambda name, now: {"r2": {"drained": True}})
        R.run_once(DS.READER, announce=None, clock=lambda: T0)

        def measure(name, now):
            if name == "Branch":
                raise RuntimeError("Prometheus could not be asked for interface states: refused")
            return {}
        monkeypatch.setattr(D, "measure", measure)
        R.run_once(DS.READER, announce=None, clock=lambda: T0 + 60)
        branch = D.held("Branch")
        assert branch["verdicts"] == {"r2": {"drained": True}}
        assert "interface states: refused" in branch["error"] and branch["at"]
        assert D.held("Lab") == dict(D.held("Lab"), verdicts={}, error="")

    def test_every_network_failing_is_the_read_failing_its_last_good_kept(self, store,
                                                                          monkeypatch):
        monkeypatch.setattr(D, "ENABLED", True)
        monkeypatch.setattr(DS, "_lists", lambda: ["Lab"])
        monkeypatch.setattr(D, "measure", lambda name, now: {"r2": {"drained": True}})
        R.run_once(DS.READER, announce=None)
        monkeypatch.setattr(D, "measure", lambda name, now: (_ for _ in ()).throw(
            RuntimeError("refused")))
        doc = R.run_once(DS.READER, announce=None)
        assert doc["last_attempt"]["ok"] is False
        got = D.held("Lab")
        assert got["verdicts"] == {"r2": {"drained": True}}
        assert "the drained reader's read failed" in got["error"] and "refused" in got["error"]

    def test_never_read_is_said_never_drawn_as_nothing_drained(self, store, monkeypatch):
        monkeypatch.setattr(D, "ENABLED", True)
        got = D.held("Lab")
        assert got == {"verdicts": {}, "at": "", "error": got["error"]} and got["error"]
        with pytest.raises(RuntimeError):
            D.current("Lab")
        assert D.state_of("Lab", "r2") is None

    def test_each_network_is_keyed_by_its_one_id(self, store, monkeypatch):
        """C1903: the value is keyed by the network's id; either spelling reads it, and a name
        no network answers to is not measured."""
        measured = []
        monkeypatch.setattr(D, "ENABLED", True)
        monkeypatch.setattr(DS, "_lists", lambda: ["Lab", "Gone"])
        monkeypatch.setattr(D, "measure", lambda name, now: measured.append(name) or {
            "r2": {"drained": True}})
        R.run_once(DS.READER, announce=None)
        doc = R.read_cached(DS.NAME)["doc"]
        assert set(doc["last_good"]["value"]["networks"]) == {"lab"} and measured == ["Lab"]
        assert D.held("Lab") == D.held("lab") and D.held("Lab")["verdicts"]

    def test_the_reader_is_declared_woken_and_heard(self):
        from modules import invalidation, reader_wakes
        assert "modules.readers.drained_state" in R.DECLARED_MODULES
        assert DS.READER in R.readers()
        assert "drained" in invalidation.VOCABULARY
        assert set(reader_wakes.WOKEN_BY["drained"]) == {"goldens", "inventory", "settings"}


def _source(cap, hosts, asked):
    """The reader's fleet read of *cap*, its answer copied to each of *hosts* by name, each
    query counted."""
    from tests.test_neighbours import METRICS, UP

    def src():
        results, up = {}, {}
        for m in list(METRICS) + [UP]:
            asked.append(m)
        for host in hosts:
            real = host.split("-")[0]
            for m in METRICS:
                for r in cap[m]["data"]["result"]:
                    if r["metric"]["device"] == real:
                        results.setdefault(host, {}).setdefault(m, []).append(copy.deepcopy(r))
            for r in cap[UP]["data"]["result"]:
                if r["metric"]["device"] == real:
                    up.setdefault(host, {})[r["metric"]["job"]] = int(r["value"][1])
        return True, results, up
    return src


class TestTheAdjacencyViews:
    @pytest.fixture
    def fleet(self, monkeypatch):
        from modules import neighbours as N
        from tests.test_neighbours import _capture, _intents
        intents = _intents()
        compared = []
        real = N.compare

        def compare(*a, **k):
            compared.append(a[1])
            return real(*a, **k)
        monkeypatch.setattr(N, "committed_intents", lambda repo: (intents, ""))
        monkeypatch.setattr(N, "compare", compare)
        return SimpleNamespace(intents=intents, cap=_capture(), compared=compared)

    def _read(self, fleet, copies, asked):
        hosts = sorted(f"{h}-{i}" if i else h for h in fleet.intents for i in range(copies))
        return ADJ.read(previous={}, clock=lambda: T0, rip=lambda: ({}, ""),
                        source=_source(fleet.cap, hosts, asked),
                        population=lambda: [("Lab", SimpleNamespace(repo_dir="/nowhere"),
                                             hosts)]), hosts

    def test_the_queries_do_not_grow_with_the_fleet_and_each_device_is_compared_once(
            self, fleet):
        small_asked, big_asked = [], []
        small, hosts = self._read(fleet, 1, small_asked)
        n_small = len(fleet.compared)
        big, big_hosts = self._read(fleet, 10, big_asked)
        assert len(small_asked) == len(big_asked) == 4
        assert n_small == len(hosts) and len(fleet.compared) - n_small == len(big_hosts)
        assert set(small["views"]) == {f"Lab:{h}" for h in hosts}
        assert set(big["views"]) == {f"Lab:{h}" for h in big_hosts}

    def test_the_view_is_what_the_tab_drew_before(self, fleet):
        """The stored view is what the tab drew from the same answer: each protocol's words,
        why, as-of and measured, each row's drawn keys, the two counts the head adds up, and
        no_intent; nothing the tab does not draw is carried."""
        from modules import neighbours as N
        from tests.test_neighbours import _for
        value, _hosts = self._read(fleet, 1, [])
        res, up = _for(fleet.cap, "r3")
        want = N.compare(fleet.intents, "r3", res, up, now=T0)
        got = value["views"]["Lab:r3"]
        drawn_p = {"words", "why", "as_of", "measured"}
        drawn_r = {"managed", "peer", "address", "rid", "via", "state", "words", "as_of",
                   "at_iso"}
        assert [p["words"] for p in got["protocols"]] == [p["words"] for p in want["protocols"]]
        for g, w in zip(got["protocols"], want["protocols"]):
            assert set(g) == ({k for k in w if k in drawn_p} | {"rows"})
            assert g["rows"] == [{k: r[k] for k in r if k in drawn_r} for r in w["rows"]]
            assert all(set(r) <= drawn_r for r in g["rows"]) and g["rows"]
        assert got["counts"] == {s: want["counts"][s] for s in ("down", "not_seen")}
        assert got["no_intent"] is False

    def test_the_tabs_read_compares_nothing_and_asks_nothing(self, fleet, store, monkeypatch):
        from modules import neighbours as N
        asked = []
        hosts = sorted(fleet.intents)
        monkeypatch.setattr(ADJ, "lists", lambda: [
            ("Lab", SimpleNamespace(repo_dir="/nowhere", name="Lab"), hosts)])
        monkeypatch.setattr("modules.integration_groups.merged",
                            lambda group, fetch: _source(fleet.cap, hosts, asked)())
        monkeypatch.setattr(ADJ, "_rip_answer", lambda: ({}, ""))
        R.run_once(ADJ.READER, announce=None)
        before_q, before_c = len(asked), len(fleet.compared)
        ref = SimpleNamespace(name="Lab", repo_dir="/nowhere")
        for _ in range(50):
            view = N.held_view(ref, {"hostname": "r3"})
        assert view["held"]["state"] == "held" and view["protocols"]
        assert len(asked) == before_q and len(fleet.compared) == before_c


class TestDisplayOnly:
    """No path that must read live (the heal pipeline, a deploy's) names either held value."""

    NAMES = ("drained_state", "held_view", "drained")

    def test_the_scan_finds_a_planted_read(self):
        assert _names("from modules import neighbours\nneighbours.for_device(r, d)\n") == []
        for name in self.NAMES:
            assert _names(f"from modules import x\nx.{name}('Lab')\n") == [2], name
            assert _names(f"from modules import {name}\n") == [1], name

    def test_no_live_path_names_a_held_value(self):
        from tests.test_attention_display_only import LIVE_PATHS, ROOT
        import os
        assert len(LIVE_PATHS) >= 40
        found = {os.path.relpath(p, ROOT): lines for p in LIVE_PATHS
                 if (lines := _names(open(p, encoding="utf-8").read()))}
        assert not found, ("a path that must read live names the drained or the adjacencies "
                           f"reader's held view (C3166, display only): {found}")


def _names(source: str) -> list:
    """Each line of *source* that imports or names one of `TestDisplayOnly.NAMES`."""
    import ast
    out = []
    for node in ast.walk(ast.parse(source)):
        names = []
        if isinstance(node, ast.ImportFrom):
            names = [(node.module or "").rsplit(".", 1)[-1]] + [a.name for a in node.names]
        elif isinstance(node, ast.Import):
            names = [a.name.rsplit(".", 1)[-1] for a in node.names]
        elif isinstance(node, ast.Attribute):
            names = [node.attr]
        elif isinstance(node, ast.Name):
            names = [node.id]
        if any(n in TestDisplayOnly.NAMES for n in names):
            out.append(node.lineno)
    return sorted(set(out))
