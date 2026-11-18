"""The proposal's preflight reuses the investigation's device reads (55c8a8eb, the operator,
2026-11-16: "time to a ready plan toward 45 s"; `modules/nsot/command_plan_run.py` `Reused`,
`Sources.read`). The debt pass, 2026-11-18 (docs/FAST_LANE_DEBT.md's row for 55c8a8eb).

A kept read answers a later preflight's same command on the same device while at most
`REUSE_S` old, keyed by its words with each interface name canonical; only a read that signed
in as Mercury's account is kept; the rest are read live through the read engine and kept for
a later preflight of the same job (the alternative's). The approved run never takes kept reads
(held in tests/test_command_plan.py `TestTheRunReadsLive`). No device, no network: the read
engine's records and its run are planted as `reads.get` and `reads.run` return them.
"""
from modules.nsot import command_plan_run as CR

T = 1_790_000_000.0
CMD = "show interfaces GigabitEthernet1/0/5 status"


def kept(at=T, now=T):
    clock = {"now": now}
    r = CR.Reused(clock=lambda: clock["now"])
    r.keep("s1", CMD, "Gi1/0/5  err-disabled", at)
    return r, clock


class TestTheBound:
    def test_within_its_bound_it_answers_with_its_age(self):
        r, clock = kept()
        clock["now"] = T + CR.REUSE_S
        got = r.take("s1", CMD)
        assert got["answer"] == "Gi1/0/5  err-disabled" and got["age_s"] == CR.REUSE_S
        assert CR.reused_words(got) == f"read {int(CR.REUSE_S)} s ago, {CR.FROM_PREFLIGHT}"

    def test_past_its_bound_or_from_the_future_it_is_read_again(self):
        r, clock = kept()
        clock["now"] = T + CR.REUSE_S + 1
        assert r.take("s1", CMD) is None
        clock["now"] = T - 5
        assert r.take("s1", CMD) is None, "a clock that moved back is no young read"

    def test_another_device_is_not_this_ones(self):
        r, _ = kept()
        assert r.take("s2", CMD) is None


class TestTheKey:
    def test_one_read_whatever_its_interface_spelling_and_spacing(self):
        r, _ = kept()
        assert r.take("s1", "show interfaces  Gi1/0/5   status")["answer"].startswith("Gi1/0/5")
        assert r.take("s1", "SHOW interfaces gigabitethernet1/0/5 status") is not None

    def test_a_younger_read_is_never_replaced_by_an_older_one(self):
        r, _clock = kept(at=T, now=T + 2)
        r.keep("s1", CMD, "an older answer", T - 30)
        assert r.take("s1", CMD)["answer"] == "Gi1/0/5  err-disabled"
        r.keep("s1", CMD, "a younger answer", T + 1)
        assert r.take("s1", CMD)["answer"] == "a younger answer"


class TestTheInvestigationsRuns:
    def records(self, monkeypatch, signs_in_as):
        from modules.nsot import reads

        rec = {"signs_in_as": signs_in_as, "results": {"s1": {"answers": [
            {"command": CMD, "state": reads.ANSWERED, "answer": "up", "at": T},
            {"command": "show clock", "state": "failed", "answer": "", "at": T}]}}}
        monkeypatch.setattr(reads, "get", lambda network, rid: rec)

    def test_each_answered_read_of_mercurys_account_is_kept(self, monkeypatch):
        self.records(monkeypatch, "mercury")
        r = CR.Reused(clock=lambda: T + 10)
        assert r.add_runs("Default", ["rr-1", "rr-1", ""]) == 1, "each run once, answered only"
        got = r.take("s1", CMD)
        assert (got["answer"], got["run"], got["from"]) == ("up", "rr-1",
                                                            CR.FROM_INVESTIGATION)

    def test_a_read_only_accounts_record_is_never_reused(self, monkeypatch):
        self.records(monkeypatch, "read_only")
        r = CR.Reused(clock=lambda: T + 10)
        assert r.add_runs("Default", ["rr-1"]) == 0 and r.take("s1", CMD) is None


class TestTheSourcesRead:
    def test_a_kept_read_answers_and_the_rest_are_read_live_and_kept(self, monkeypatch):
        from modules.nsot import reads

        asked = []

        def run(network, hosts, commands, label, **kw):
            asked.append(list(commands))
            return {"id": "rr-9", "results": {"s1": {"answers": [
                {"command": c, "state": reads.ANSWERED, "answer": f"live {c}", "at": T + 20}
                for c in commands]}}}
        monkeypatch.setattr(reads, "run", run)
        r, clock = kept()
        clock["now"] = T + 20
        src = CR.Sources("Default", reuse=r)
        got = src.read("s1", [CMD, "show clock"])
        assert got == {CMD: "Gi1/0/5  err-disabled", "show clock": "live show clock"}, got
        assert asked == [["show clock"]], "only what was not kept is read"
        assert [x["command"] for x in src.reused_log] == [CMD]
        assert (r.stats["reused"], r.stats["live"]) == (1, 1)
        assert r.take("s1", "show clock")["run"] == "rr-9", "kept for the alternative's preflight"
