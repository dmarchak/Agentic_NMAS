"""AI troubleshooting builds its request and runs the standard reads at once, and reads the
plan's preconditions ahead beside the first call (5653c025, the operator, 2026-11-16: "target
45 s or less"; `modules/ai/fixit_troubleshoot.py` `_at_once`, `_behind`, `read_ahead_for`). The
debt pass, 2026-11-18 (docs/FAST_LANE_DEBT.md's row for 5653c025).

- **At once:** each named part starts before any ends (two parts held at one barrier, so the
  call returns only if both are live together), each its result and its seconds; a part that
  raises is its own failure and the other's result stands.
- **Behind:** a read ahead starts at once and is joined later; one that raises joins as None.
- **The read ahead per problem kind:** an err-disable's are the errdisable-recover plan's
  precondition reads (the built-in plans' own), less a read the standard reads already hold;
  a kind no plan fixes reads nothing ahead.
No AI call, no device: the parts are planted functions, the classification planted.
"""
import threading
import types

from modules import fanout
from modules import problem as P
from modules.ai import fixit_troubleshoot as FT


class TestAtOnce:
    def test_each_part_starts_before_any_ends_with_its_result_and_seconds(self):
        both = threading.Barrier(2, timeout=10)

        def part(value):
            def fn():
                both.wait()                           # passes only with the other part live
                return value
            return fn
        got = FT._at_once([("request", part("the request")), ("reads", part("the reads"))])
        assert {k: v[0] for k, v in got.items()} == {"request": "the request",
                                                      "reads": "the reads"}, got
        assert all(isinstance(v[1], float) for v in got.values())

    def test_a_part_that_raises_is_its_own_failure_and_the_other_stands(self):
        def broken():
            raise RuntimeError("the pack could not be built")
        got = FT._at_once([("request", broken), ("reads", lambda: "the reads")])
        assert isinstance(got["request"][0], fanout.Failed), got
        assert got["reads"][0] == "the reads"


class TestBehind:
    def test_started_at_once_and_joined_later(self):
        started, go = threading.Event(), threading.Event()

        def ahead():
            started.set()
            go.wait(10)
            return "read ahead"
        join = FT._behind(ahead)
        assert started.wait(10), "started before its join"
        go.set()
        got, seconds = join()
        assert got == "read ahead" and isinstance(seconds, float)

    def test_one_that_raises_joins_as_none(self):
        def ahead():
            raise RuntimeError("refused")
        got, _s = FT._behind(ahead)()
        assert got is None


class TestTheReadAhead:
    def found(self, monkeypatch, condition):
        from modules.heal import errdisable as ED

        monkeypatch.setattr(P, "classify", lambda found: P.Problem(
            device="s1", object="Gi1/0", condition=condition))
        return {"incident": {ED.FIELD: {"port": "Gi1/0"}}}

    def test_an_err_disables_are_its_plans_preconditions_less_those_held(self, monkeypatch):
        from modules.nsot import command_plan

        found = self.found(monkeypatch, "err_disabled")
        inc = types.SimpleNamespace(device="s1")
        reads = [p["read"] for p in command_plan.builtin()["errdisable-recover"].preconditions
                 if p.get("read")]
        assert len(reads) >= 2, "floor: the plan reads at least two preconditions"
        assert FT.read_ahead_for(found, inc, []) == reads
        held = [{"args": {"words": reads[0][len("show "):]}}]
        assert FT.read_ahead_for(found, inc, held) == reads[1:], "a read held is not read again"

    def test_a_kind_no_plan_fixes_reads_nothing_ahead(self, monkeypatch):
        found = self.found(monkeypatch, "no_plan_fixes_this")
        assert FT.read_ahead_for(found, types.SimpleNamespace(device="s1"), []) == []


class TestTheReadAheadIsTheAIs:
    """C4060: the read ahead is one of the investigation's reads, so it honours "AI device
    reads sign in as": read as the AI's kind for the investigation's actor under Mercury's
    account, and not read at all under the read-only account (a preflight takes only Mercury's
    account's answers, so it reads live). The engine is a stand-in: no device."""

    def engine(self, monkeypatch, reads_as):
        from modules.nsot import reads

        calls = []
        monkeypatch.setattr(reads, "ai_reads_as", lambda: reads_as)
        monkeypatch.setattr(reads, "run", lambda network, hosts, commands, actor, **kw: (
            calls.append(dict(kw, network=network, hosts=hosts, commands=commands,
                              actor=actor)) or {"id": "run-1"}))
        return calls

    def test_under_mercury_s_account_it_reads_as_the_ai_for_its_actor(self, monkeypatch):
        calls = self.engine(monkeypatch, "mercury")
        inc = types.SimpleNamespace(device="s1", id="inc-1")
        got = FT.read_ahead("Lab", inc, ["show interfaces status err-disabled"], pool="p1",
                            actor="person@example.invalid")
        assert got == "run-1"
        assert [(c["by"], c["actor"], c["pool"], c["hosts"]) for c in calls] == [
            ("ai_analysis", "person@example.invalid", "p1", ["s1"])], calls

    def test_under_the_read_only_account_nothing_is_read_ahead(self, monkeypatch):
        calls = self.engine(monkeypatch, "read_only")
        inc = types.SimpleNamespace(device="s1", id="inc-1")
        assert FT.read_ahead("Lab", inc, ["show interfaces status err-disabled"],
                             actor="person@example.invalid") == ""
        assert calls == [], "the read-only account's answers would never be taken"
