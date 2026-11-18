"""G6, the one-button batch, and C3748's control strip (the operator's design, 2026-11-14 and
2026-11-15; modules/heal/batch.py, modules/control_strip.py, routes/control_v2.py).

What is held here:
- the preview: no guard 6 hold, no batch;
- a person's approval of the batch resolves guard 6, and the grace is dropped for that batch
  only (an unreadable one kept);
- the heal runner leaves a batch's decisions to its job, and refuses one its job left untaken;
- the batch's devices all at once, none started after the first failure;
- the press: refused before anything starts unless a verified person who may;
- the strip: read-only for anyone who may not; on Incidents alone, Needs attention keeping
  the run; the default duration.

Retired (the operator's decision 8, 2026-11-18, C3971): the 18 tests of G6's guard-6 batch
card and its old strip toggle, whose subject 70e89a47, C3909 and C3823 removed (its preview's
counts and hash, guard 6's hold, the one-device-first job, the card's press, the old toggle's
Auto for a duration). The Self-healing switch's batch, which replaced them, gets its own
tests where it had none (the decision's second half).
"""

import time

import pytest

from modules import fanout
from modules.heal import batch as B
from tests.test_heal_decide import GOLDEN, ROUTE4, Fake, lab, settle  # noqa: F401
from tests.test_heal_policy import T0, auto, confirm, iso
from tests.test_sdn_connections import networks  # noqa: F401  (the fixture `lab` builds on)
from tests.v2_context import batch_fixture


def _p(**kw):
    decisions, doc, ai = batch_fixture(T0)
    return B.preview("Lab", decisions, ai_items=kw.get("ai", ai), incidents_doc=doc)


class TestThePreview:

    def test_no_guard_6_hold_is_no_batch(self):
        decisions, doc, ai = batch_fixture(T0)
        for d in decisions:
            d["guard"] = dict(d["guard"], guard=4)
        assert B.preview("Lab", decisions, ai_items=ai, incidents_doc=doc)["on"] is False



class TestGuard6AndTheApproval:
    def _many(self):
        from modules.heal import incidents as I
        for n in ("a-1", "a-2", "a-3", "a-4"):
            I.sight("Default", n, {"kind": "drift", "key": f"d:{n}", "epoch": T0 - 30},
                    now=T0 - 30)


    def test_the_approval_resolves_guard_6_for_its_batch(self, lab):  # noqa: F811
        from modules.heal import decide as DC
        auto("Default", now=T0 - 60, kinds=("added_line",))
        self._many()
        inc = settle(GOLDEN + ROUTE4)
        d = DC.decide_one("Default", inc, now=T0, sources=Fake(GOLDEN + ROUTE4),
                          batch={"id": "hb-1", "by": "op@example.com", "by_shown": "Op",
                                 "hash": "h" * 64})
        assert d["outcome"] == "heal", d["words"]
        assert d["batch"] == {"id": "hb-1", "by": "op@example.com", "hash": "h" * 64}


    def test_the_grace_is_dropped_but_an_unreadable_one_is_kept(self):
        from modules.heal import decide as DC
        g8 = {"guard": 8}
        assert DC._resolves({"id": "x"}, g8, {"settled": {"how": "pending"}})
        assert not DC._resolves({"id": "x"}, g8, {"settled": {"how": "unreadable"}})
        assert not DC._resolves(None, {"guard": 6}, {})
        assert not DC._resolves({"id": "x"}, {"guard": 10}, {}), "guard 10 still counts"


class TestTheRunnerLeavesABatchToItsJob:
    def _decision(self, network, epoch):
        from modules.heal import decisions
        return decisions.record(network, {"incident": "hi-1", "device": "r1", "outcome": "heal",
                                          "batch": {"id": "hb-1"}, "program_hash": "a"},
                                epoch)

    def test_a_young_one_is_not_started(self, lab):  # noqa: F811
        from modules.heal import act
        self._decision("Default", T0)
        started = []
        out = act.run("Default", now=T0 + 5, starter=lambda n, d: started.append(d) or "j")
        assert started == [] and out["refused"] == []

    def test_one_its_job_left_is_refused_with_nothing_sent(self, lab):  # noqa: F811
        from modules.heal import act, decisions
        d = self._decision("Default", T0)
        started = []
        out = act.run("Default", now=T0 + B.UNTAKEN_S + 1,
                      starter=lambda n, x: started.append(x) or "j")
        assert started == [] and out["refused"], out
        got = decisions.find("Default", d["id"])
        assert got["applied"]["outcome"] == "refused" and "Nothing was sent" in got[
            "applied"]["words"]


class TestEachUntilFailure:
    def test_none_is_started_after_the_first_failure(self):
        seen = []

        def fn(i):
            seen.append(i)
            return {"ok": i != 1}
        got = fanout.each_until_failure(fn, [1, 2, 3, 4], lambda x: x["ok"], max_workers=1)
        assert seen == [1] and got[1:] == [fanout.NOT_STARTED] * 3

    def test_all_run_at_once_when_none_fails(self):
        import threading
        live, most, lock = [0], [0], threading.Lock()

        def fn(i):
            with lock:
                live[0] += 1
                most[0] = max(most[0], live[0])
            time.sleep(0.05)
            with lock:
                live[0] -= 1
            return True
        assert fanout.each_until_failure(fn, range(4), bool) == [True] * 4
        assert most[0] == 4, "the rest run at once"


class TestEveryDeviceAtOnce:
    """c4948c2c (the operator, 2026-11-16; CLAUDE.md's heal-batch clause): the batch's job
    (`batch.run`) fixes every device at once, each through its own act, and a failure stops no
    other; each device's outcome is recorded on its own incident (``batches``) and the batch
    says how many were fixed. Three would-heals decided by the real decision in dry run, Auto
    then turned on (the batch's own step done, as the switch's request does it: *pre*); each
    act a stand-in (`act_start`) that waits at a barrier of three, so the run passes only if
    all three acts are live at once, and its outcome read by the stand-in *wait*. The debt
    pass, 2026-11-18 (docs/FAST_LANE_DEBT.md's row for c4948c2c)."""

    DEVICES = ("edge-a", "edge-b", "edge-c")

    def test_every_device_at_once_and_a_failure_stops_none(self, lab, monkeypatch):  # noqa: F811
        import threading

        from modules.heal import decide, decisions, incidents, retry

        monkeypatch.setattr(retry, "run_soon", lambda *a, **k: None)
        # The three devices' rows, as guard 4's judgement at the batch reads them (managed).
        monkeypatch.setattr("modules.device.load_saved_devices", lambda path=None: [
            {"hostname": d, "ip": f"192.0.2.{n + 1}", "device_type": "cisco_ios"}
            for n, d in enumerate(self.DEVICES)])
        items = []
        for device in self.DEVICES:
            inc = settle(GOLDEN + ROUTE4, device=device, claim=False)
            (d,) = decide.run("Default", now=T0, sources=Fake(GOLDEN + ROUTE4))["decided"]
            assert d["outcome"] == "would_heal", d
            items.append({"device": device, "incident": inc["id"], "decision": d["decision"],
                          "from": "would_heal",
                          "program_hash": decisions.find("Default", d["decision"])[
                              "program_hash"]})
        # On until turned off (C3750): the batch's devices are judged at the real clock.
        confirm("Default", now=T0 + 5, heal_mode="auto", heal_kinds_auto=["added_line"])
        barrier, started = threading.Barrier(len(items), timeout=10), []

        def act_start(network, taken):
            started.append(taken["device"])
            barrier.wait()                            # all three live at once, or it breaks
            return f"job-{taken['device']}"

        def wait(job, bound):
            outcome = "failed" if job == "job-edge-b" else "healed"
            return True, {"state": "done", "payload": {"result": {"outcome": outcome}}}
        out = B.run("Default", {"items": items}, actor="op@example.com", verified="access",
                    person=True, act_start=act_start, wait=wait,
                    pre={"steps": [], "batch": "hb-1", "devices": [], "scripts": [],
                         "claims": {}, "approval": {"id": "hb-1", "by": "op@example.com",
                                                    "named": ""}})
        assert sorted(started) == list(self.DEVICES), (started, out)
        got = {d["device"]: d["outcome"] for d in out["devices"]}
        assert got == {"edge-a": "healed", "edge-b": "failed", "edge-c": "healed"}, out
        assert out["outcome"] == "partial" and out["words"].startswith(
            "2 of 3 fixed and verified; did not: edge-b"), out["words"]
        held = {i["id"]: i for i in incidents.read("Default")["incidents"]}
        for item in items:
            (entry,) = held[item["incident"]]["batches"]
            assert entry["batch"] == "hb-1" and entry["outcome"] == got[item["device"]]


class TestThePress:
    @pytest.fixture
    def held(self, monkeypatch):
        p = _p()
        monkeypatch.setattr(B, "preview", lambda network, *a, **k: p)
        return p

    class _Who:
        is_identified, kind, actor = True, "person", "op@example.com"


    def test_a_service_is_refused(self, held):
        class Svc(self._Who):
            kind, actor = "service", "svc:ci"
        with pytest.raises(B.Refused, match="not a person"):
            B.press("Lab", held["hash"], actor="svc:ci", verified="service", ident=Svc())



def test_guard_10_s_recount_and_decide_s_record_share_one_cross_process_lock():
    """Gate 2's review: the batch's guard-10 re-count and record (`batch._one`) and decide's
    record step (`decide.run`) each hold `filestore.PathLock(decisions.rate_lock_path(...))`
    around `decisions.record`, one lock across processes, never a thread lock alone. Parsed:
    a `with` whose item is that call, and the record inside it."""
    import ast
    import inspect

    from modules.heal import decide

    def holds(fn) -> bool:
        tree = ast.parse(inspect.getsource(fn).replace("\n    ", "\n")
                         if inspect.getsource(fn).startswith("    ") else inspect.getsource(fn))
        for node in ast.walk(tree):
            if not isinstance(node, ast.With):
                continue
            locked = any(isinstance(i.context_expr, ast.Call)
                         and getattr(i.context_expr.func, "attr", "") == "PathLock"
                         and "rate_lock_path" in ast.dump(i.context_expr) for i in node.items)
            records = any(isinstance(c, ast.Call) and getattr(c.func, "attr", "") == "record"
                          for c in ast.walk(node))
            if locked and records:
                return True
        return False
    assert holds(B._one) and holds(decide.run)
    assert "threading" not in inspect.getsource(B)


def test_the_batch_s_approval_and_outcome_reach_history(lab):  # noqa: F811
    """Gate 2's review: the batch's ``batch`` and ``batch_done`` rows are History's (the heal
    source), each naming the batch, who approved it and its devices, and its outcome."""
    import types

    from modules import history_sources as HS
    from modules.heal import decisions
    decisions._append("Default", {"row": "batch", "id": "hb-000000000001-1", "by": "op@example.com",
                              "actor_verified": "access", "hash": "a" * 64,
                              "at": "2026-11-15T07:00:00Z", "epoch": 1,
                              "items": [{"device": "r1", "incident": "hi-1", "decision": "hd-1",
                                         "program_hash": "b" * 64}], "ai": ["hi-2"]})
    decisions._append("Default", {"row": "batch_done", "batch": "hb-000000000001-1",
                              "outcome": "fixed", "words": "1 device fixed",
                              "at": "2026-11-15T07:05:00Z",
                              "devices": [{"device": "r1", "outcome": "healed"}]})
    ctx = {"ref": types.SimpleNamespace(name="Default"), "device": "", "members": None,
           "since": None, "until": None, "limit": 50}
    # Through the heal source History reads (`history_sources.heal`), its batch rows.
    got = [e for e in HS.heal(ctx)["events"] if e["what"].startswith("Turn on self-healing")]
    assert [e["kind"] for e in got] == ["heal", "heal"], got
    assert got[0]["what"].startswith("Turn on self-healing and fix all approved: 1 device")
    assert ("Batch", "hb-000000000001-1") in got[0]["record"] and got[0]["devices"] == ["r1"]
    assert got[1]["outcome"] == "fixed" and "1 device fixed" in got[1]["what"]
    assert HS._heal_batches(dict(ctx, device="r9")) == [], "another device's History"


class TestTheStripRoutes:
    """Through the real app: the strip drawn, the Self-healing toggle on and off."""

    @pytest.fixture
    def app_client(self, lab, monkeypatch):  # noqa: F811
        import app as nmas_app
        return nmas_app.app.test_client()


    @pytest.mark.real_identity
    def test_an_unverified_viewer_sees_it_read_only(self, app_client):
        body = app_client.get("/v2/control/strip?list=Default").get_data(as_text=True)
        from modules.heal import policy
        assert "Read only:" in body and body.count(" disabled") >= 2
        r = app_client.post("/v2/control/Default/heal", data={"on": "1"})
        assert r.status_code in (401, 403)
        assert policy.current("Default")["mode"] == "dry_run", "the press changed nothing"

    def test_the_strip_is_on_incidents_alone_and_needs_attention_keeps_the_run(self, app_client):
        """C3789 (the operator, 2026-11-15: "The control strip: remove it from Needs attention;
        keep it only on Incidents"): Needs attention draws no Self-healing or AI switch, only
        the strip's run part, empty while nothing was pressed and nothing runs, under the id
        G6's card answers into; Incidents draws both switches, and its Self-healing switch,
        pressed as drawn there, turns Auto on."""
        import re

        from modules.heal import policy
        auto("Default", now=time.time() - 60, kinds=("added_line",))
        policy.apply_planned("Default", {policy.MODE_KEY: "dry_run"}, actor="a@example.com",
                             actor_verified="access", person=True, reason="back to dry run")
        landing = app_client.get("/v2/?list=Default").get_data(as_text=True)
        assert 'data-ctl="heal"' not in landing and 'data-ctl="ai"' not in landing
        assert "ctl-strip" not in landing and "AI troubleshooting: Automatic" not in landing
        part = re.search(r'<section class="ctl-run-only" id="control-strip"[^>]*'
                         r'data-part="run"[^>]*>(.*?)</section>', landing, re.S)
        assert part and not part.group(1).strip(), "nothing pressed, nothing running: empty"
        assert 'hx-get="/v2/control/strip?list=Default&amp;part=run"' in part.group(0)
        incidents = app_client.get("/v2/incidents?list=Default").get_data(as_text=True)
        assert 'data-ctl="ai"' in incidents
        form = re.search(r'<form class="ctl-item" id="ctl-heal" method="post" action="([^"]+)"'
                         r'.*?name="on" value="([01])">', incidents, re.S)
        assert form and form.group(2) == "1", "the Self-healing switch is on Incidents"
        r = app_client.post(form.group(1), data={"on": form.group(2)})
        assert r.status_code == 200 and policy.current("Default")["mode"] == "auto"
        # The run part re-reads itself as the run part, never as the whole strip.
        again = app_client.get("/v2/control/strip?list=Default&part=run").get_data(as_text=True)
        assert 'data-part="run"' in again and 'data-ctl="heal"' not in again



def test_the_default_duration_is_one_hour_and_n8_still_bounds_it():
    from modules.settings_schema import DEFAULTS, validate
    assert DEFAULTS["heal_auto_default_hours"] == 1
    assert not validate(dict(DEFAULTS, heal_auto_default_hours=24))[0]
    assert validate(dict(DEFAULTS, heal_auto_default_hours=8))[0]
    assert iso  # the shared clock's helper (imported for the policy fixtures)
