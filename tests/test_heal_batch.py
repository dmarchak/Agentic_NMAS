"""G6, the one-button batch, and C3748's control strip (the operator's design, 2026-11-14 and
2026-11-15; modules/heal/batch.py, modules/control_strip.py, routes/control_v2.py).

What is held here:
- the preview: its real counts and words, its hash binding every program, the held devices it
  cannot fix and the incidents the AI starts on (its own incidents never among them);
- guard 6's hold carries the decision past it (``beyond``), and a person's approval of the
  batch resolves guard 6 and drops the grace for that batch only;
- the heal runner leaves a batch's decisions to its job, and refuses one its job left untaken;
- the job: Auto turned on through the policy's own write, the approval recorded, one device
  first, the rest only once it healed, none started after a failure, a moved program refused;
- the press: refused before anything starts unless a verified person who may, and the hash is
  the batch's now; the AI started on each incident with no fix as a person's press;
- the strip: both toggles drawn with the live state, the Self-healing toggle's on (Auto for
  the default duration) and off (Dry run), recorded as the person's change, read-only for
  anyone who may not, and the chip's link to it.
"""

import time

import pytest

from modules import fanout
from modules.heal import batch as B
from tests.test_heal_decide import GOLDEN, ROUTE4, Fake, lab, settle  # noqa: F401
from tests.test_heal_policy import T0, auto, iso
from tests.test_sdn_connections import networks  # noqa: F401  (the fixture `lab` builds on)
from tests.v2_context import batch_fixture


def _p(**kw):
    decisions, doc, ai = batch_fixture(T0)
    return B.preview("Lab", decisions, ai_items=kw.get("ai", ai), incidents_doc=doc)


class TestThePreview:
    def test_it_leads_with_the_real_counts_and_guard_6_s_words(self):
        p = _p()
        assert p["on"] and (p["n"], p["fixable"]) == (4, 2), p
        assert p["lead"] == "4 devices have faults. Mercury can fix 2."
        # Gate 2's review: approving drops the grace too (`decide.BATCH_RESOLVES`), said.
        assert p["hold"] == ("Held by guard 6: 3 devices changed at once. Approve to fix them "
                             "all. Approving fixes them all now, without the usual grace.")
        assert [i["device"] for i in p["items"]] == ["r1", "r3"]
        assert p["items"][0]["program"] == ["interface GigabitEthernet2", " description to-r2"]
        assert [o["device"] for o in p["others"]] == ["r6"] and "2 units" in p["others"][0]["why"]
        assert [a["device"] for a in p["ai"]] == ["s5"]

    def test_its_hash_binds_every_program_and_every_ai_incident(self):
        decisions, doc, ai = batch_fixture(T0)
        h = B.preview("Lab", decisions, ai_items=ai, incidents_doc=doc)["hash"]
        decisions[0]["beyond"] = dict(decisions[0]["beyond"], program_hash="c" * 64)
        assert B.preview("Lab", decisions, ai_items=ai, incidents_doc=doc)["hash"] != h
        assert B.preview("Lab", batch_fixture(T0)[0], ai_items=[], incidents_doc=doc)[
            "hash"] != h

    def test_its_own_incidents_are_never_the_ai_s(self):
        decisions, doc, ai = batch_fixture(T0)
        mine = dict(ai[0], id=decisions[0]["incident"], device="r1")
        p = B.preview("Lab", decisions, ai_items=ai + [mine], incidents_doc=doc)
        assert [a["id"] for a in p["ai"]] == [ai[0]["id"]]

    def test_no_guard_6_hold_is_no_batch(self):
        decisions, doc, ai = batch_fixture(T0)
        for d in decisions:
            d["guard"] = dict(d["guard"], guard=4)
        assert B.preview("Lab", decisions, ai_items=ai, incidents_doc=doc)["on"] is False

    def test_a_hold_its_incident_no_longer_stands_on_is_left_out(self):
        decisions, doc, ai = batch_fixture(T0)
        doc["incidents"][0]["state"] = "closed"
        p = B.preview("Lab", decisions, ai_items=ai, incidents_doc=doc)
        assert [i["device"] for i in p["items"]] == ["r3"]


class TestGuard6AndTheApproval:
    def _many(self):
        from modules.heal import incidents as I
        for n in ("a-1", "a-2", "a-3", "a-4"):
            I.sight("Default", n, {"kind": "drift", "key": f"d:{n}", "epoch": T0 - 30},
                    now=T0 - 30)

    def test_the_hold_carries_what_the_batch_would_send(self, lab):  # noqa: F811
        from modules.heal import decide as DC
        auto("Default", now=T0 - 60, kinds=("added_line",))
        self._many()
        inc = settle(GOLDEN + ROUTE4)
        d = DC.decide_one("Default", inc, now=T0, sources=Fake(GOLDEN + ROUTE4))
        assert (d["outcome"], d["guard"]["guard"]) == ("held", 6), d["words"]
        b = d["beyond"]
        assert b["outcome"] == "heal" and b["program"] == [
            "no ip route 192.0.2.128 255.255.255.128 192.0.2.10"] and b["program_hash"]

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

    def test_without_it_guard_6_still_holds(self, lab):  # noqa: F811
        from modules.heal import decide as DC
        auto("Default", now=T0 - 60, kinds=("added_line",))
        self._many()
        d = DC.decide_one("Default", settle(GOLDEN + ROUTE4), now=T0,
                          sources=Fake(GOLDEN + ROUTE4))
        assert d["guard"]["guard"] == 6 and "batch" not in d

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


class TestTheJob:
    """`batch.run` with the device's heal job replaced: its steps, the order, the stop."""

    @pytest.fixture
    def run(self, monkeypatch):
        calls = {"one": [], "auto": []}

        def one(network, item, approval, **kw):
            calls["one"].append(item["device"])
            return {"device": item["device"], "outcome": calls["outcomes"].get(
                item["device"], "healed"), "words": "w"}
        monkeypatch.setattr(B, "_one", one)
        monkeypatch.setattr(B, "turn_on_auto", lambda network, **kw: calls["auto"].append(
            kw["reason"]) or {"ok": True, "nothing": False, "until": "x",
                              "words": "turned on"})
        rows = []
        monkeypatch.setattr(B, "_record_row", lambda network, row: rows.append(row) or row)
        calls["rows"], calls["outcomes"] = rows, {}
        return calls

    def _items(self, n):
        p = _p()
        p["items"] = [dict(p["items"][0], device=f"r{i}") for i in range(1, n + 1)]
        return p

    def test_one_first_then_the_rest_and_the_record(self, run):
        out = B.run("Lab", self._items(4), actor="op@example.com", verified="access",
                    person=True)
        assert out["outcome"] == "fixed", out["words"]
        assert run["one"][0] == "r1" and sorted(run["one"]) == ["r1", "r2", "r3", "r4"]
        assert run["auto"] == ["Turn on self-healing and fix all, pressed on Needs attention"]
        kinds = [r["row"] for r in run["rows"]]
        assert kinds == ["batch", "batch_done"]
        assert run["rows"][0]["by"] == "op@example.com" and len(run["rows"][0]["items"]) == 4
        assert [s["step"] for s in out["steps"] if s["result"] == "ok"] == [
            "auto", "approve", "first", "rest", "record"]

    def test_a_first_that_does_not_heal_starts_nothing_else(self, run):
        run["outcomes"]["r1"] = "rolled_back"
        out = B.run("Lab", self._items(3), actor="op@example.com", verified="access",
                    person=True)
        assert out["outcome"] == "stopped" and run["one"] == ["r1"], out["words"]
        assert [d["outcome"] for d in out["devices"]] == ["rolled_back", "not_started",
                                                          "not_started"]

    def test_auto_refused_sends_nothing(self, run, monkeypatch):
        from modules.heal import policy

        def refuse(network, **kw):
            raise policy.PolicyRefused("AUTO only on a network marked lab")
        monkeypatch.setattr(B, "turn_on_auto", refuse)
        out = B.run("Lab", self._items(2), actor="op@example.com", verified="access",
                    person=True)
        assert out["outcome"] == "refused" and run["one"] == [] and \
            "marked lab" in out["words"]


class TestThePress:
    @pytest.fixture
    def held(self, monkeypatch):
        p = _p()
        monkeypatch.setattr(B, "preview", lambda network, *a, **k: p)
        return p

    class _Who:
        is_identified, kind, actor = True, "person", "op@example.com"

    def test_a_moved_hash_starts_nothing_naming_both(self, held, monkeypatch):
        monkeypatch.setattr("modules.identity.may", lambda ident, action, op="": (True, ""))
        with pytest.raises(B.Refused) as exc:
            B.press("Lab", "0" * 64, actor="op@example.com", verified="access",
                    ident=self._Who(), starter=lambda *a, **k: pytest.fail("started"))
        assert "000000000000" in str(exc.value) and held["hash"][:12] in str(exc.value)

    def test_a_service_is_refused(self, held):
        class Svc(self._Who):
            kind, actor = "service", "svc:ci"
        with pytest.raises(B.Refused, match="not a person"):
            B.press("Lab", held["hash"], actor="svc:ci", verified="service", ident=Svc())

    def test_auto_not_confirmable_starts_no_ai_and_no_job(self, held, monkeypatch):
        """Gate 2's review: Auto's turn-on is judged before anything starts or spends; the
        lab here is not marked lab, so the press is refused naming the gates, no AI started
        and no job."""
        monkeypatch.setattr("modules.identity.may", lambda ident, action, op="": (True, ""))
        started, jobs = [], []
        with pytest.raises(B.Refused, match="marked lab"):
            B.press("Lab", held["hash"], actor="op@example.com", verified="access",
                    ident=self._Who(), start_ai=lambda *a, **k: started.append(a),
                    starter=lambda *a, **k: jobs.append(k) or "job-1")
        assert started == [] and jobs == []

    def test_the_press_starts_the_ai_on_the_no_fix_incidents_and_the_job(self, held,
                                                                          monkeypatch):
        monkeypatch.setattr("modules.identity.may", lambda ident, action, op="": (True, ""))
        # Auto confirmable here (its gates are policy.plan's own tests'): the press goes on.
        monkeypatch.setattr("modules.heal.policy.plan",
                            lambda *a, **k: {"confirmable": True, "gates": []})
        seen = {}

        def catch_up(network, ticked, **kw):
            seen.update(ticked=list(ticked), **kw)
            return {"started": list(ticked), "capped": [], "off": [], "skipped": [],
                    "failed": []}
        jobs = []
        # The AI's starts are handed in by the caller (`control_strip.fix_all`): the heal
        # loop's modules never import the notifier (tests/test_heal_analysis_never_read.py).
        got = B.press("Lab", held["hash"], actor="op@example.com", verified="access",
                      ident=self._Who(), start_ai=catch_up,
                      starter=lambda *a, **k: jobs.append(k) or "job-1")
        assert got["job"] == "job-1" and jobs[0]["kind"] == B.KIND
        assert seen["ticked"] == ["hi-50000000005"] and seen["press"], seen


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

    def test_the_strip_draws_both_toggles_with_the_live_state(self, app_client):
        import re

        from modules.ai import background
        from modules.fixit import auto as A
        from modules.heal import policy
        body = app_client.get("/v2/control/strip?list=Default").get_data(as_text=True)
        assert 'data-ctl="heal" data-state="dry_run"' in body and ">Dry run<" in body
        assert 'data-ctl="ai" data-state="off"' in body
        # Gate 2 (C3769; the operator's minimal design, 2026-11-15): the switch's words.
        assert "AI troubleshooting: Automatic" in body
        # Pressed as drawn (its own form's action and fields): with no limits acknowledged
        # it is refused, and neither the switch nor self-healing moved.
        form = re.search(r'<form class="ctl-item" id="ctl-ai" method="post" action="([^"]+)"'
                         r'.*?name="level" value="([a-z]+)">.*?name="line_digest" '
                         r'value="([0-9a-f]*)"', body, re.S)
        r = app_client.post(form.group(1).replace("&amp;", "&"),
                            data={"level": form.group(2), "line_digest": form.group(3)})
        assert r.status_code == 409 and form.group(2) == "automatic"
        assert not A.switch("Default")["on"] and background.switches() == {}
        assert policy.current("Default")["mode"] == "dry_run"

    def test_on_is_auto_for_the_default_duration_and_off_is_dry_run(self, app_client):
        from modules import list_settings as L
        from modules.heal import policy
        auto("Default", now=time.time() - 60, kinds=("added_line",))
        policy.apply_planned("Default", {policy.MODE_KEY: "dry_run"}, actor="a@example.com",
                             actor_verified="access", person=True, reason="back to dry run")
        r = app_client.post("/v2/control/Default/heal", data={"on": "1"})
        assert r.status_code == 200, r.get_data(as_text=True)
        cur = policy.current("Default")
        assert cur["mode"] == "auto"
        left = policy.parse_until(cur["until"]) - time.time()
        assert 3500 < left <= 3600, left
        assert "Auto until" in r.get_data(as_text=True)
        r = app_client.post("/v2/control/Default/heal", data={"on": "0"})
        assert r.status_code == 200 and policy.current("Default")["mode"] == "dry_run"
        rec = [e for e in L.records("Default") if e.get("kind") == "heal_policy"] \
            if hasattr(L, "records") else None
        if rec is not None:
            assert "Self-healing toggle" in rec[-1]["reason"]

    def test_eight_hours_when_the_network_says_so(self, app_client):
        from modules import list_settings as L
        from modules.heal import policy
        auto("Default", now=time.time() - 60, kinds=("added_line",))
        policy.apply_planned("Default", {policy.MODE_KEY: "dry_run"}, actor="a@example.com",
                             actor_verified="access", person=True, reason="back to dry run")
        assert L.write("Default", {"heal_auto_default_hours": 8}, actor="a@example.com")["ok"]
        # The strip says the duration its press will ask for (one read, `batch.default_hours`).
        drawn = app_client.get("/v2/control/strip?list=Default").get_data(as_text=True)
        assert "Turn on: Auto for 8 hours" in drawn
        app_client.post("/v2/control/Default/heal", data={"on": "1"})
        left = policy.parse_until(policy.current("Default")["until"]) - time.time()
        assert 8 * 3600 - 100 < left <= 8 * 3600, left

    def test_a_refused_auto_says_why_and_changes_nothing(self, app_client):
        from modules.heal import policy
        r = app_client.post("/v2/control/Default/heal", data={"on": "1"})
        assert r.status_code == 409, r.status_code
        assert "Self-healing was not changed" in r.get_data(as_text=True)
        assert policy.current("Default")["mode"] == "dry_run"

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

    def test_fix_all_answers_in_needs_attentions_run_part(self, app_client):
        """The batch card is on Needs attention, so its press's answer is the run part drawn
        there in place (`#control-strip`, the card's ``hx-target``), never the switches."""
        from modules.heal import policy
        from modules.nsot import capture_job
        r = app_client.post("/v2/control/Default/fix-all", data={"hash": "x"})
        body = r.get_data(as_text=True)
        assert r.status_code == 409 and "Nothing was started" in body
        assert 'id="control-strip"' in body and 'data-part="run"' in body
        assert 'data-ctl="heal"' not in body and 'class="ctl-run-only card"' in body
        # And what it said is so: no batch job, self-healing as it was.
        assert not [j for j in capture_job.card_jobs() if j["kind"] == B.KIND]
        assert policy.current("Default")["mode"] == "dry_run"

    def test_a_moved_batch_is_refused_on_the_strip(self, app_client):
        from modules.heal import policy
        from modules.nsot import capture_job
        r = app_client.post("/v2/control/Default/fix-all", data={"hash": "x"})
        assert r.status_code == 409 and "Nothing was started" in r.get_data(as_text=True)
        assert not [j for j in capture_job.card_jobs() if j["kind"] == B.KIND]
        assert policy.current("Default")["mode"] == "dry_run"


SETTLED = "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')"
SWITCH = "#control-strip [data-ctl=heal] button.ctl-switch"


def test_a_real_browser_toggles_self_healing_busy_on_itself_and_hears_a_change(lab,  # noqa: F811
                                                                              monkeypatch):
    """The strip in a real browser: the Self-healing toggle pressed is busy on itself (its busy
    words, the control disabled) until its answer, which draws Auto until HH:MM in place; then
    a change made elsewhere (another person's Dry run, announced) redraws the strip with no
    reload. Premise corrected (C3789, the operator, 2026-11-15: "keep it only on Incidents"):
    it was Needs attention's strip; it is Troubleshoot › Incidents'."""
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why})")
    import threading

    import app as A
    from modules import control_strip, invalidation
    from modules.heal import policy
    auto("Default", now=time.time() - 60, kinds=("added_line",))
    policy.apply_planned("Default", {policy.MODE_KEY: "dry_run"}, actor="a@example.com",
                         actor_verified="access", person=True, reason="back to dry run")
    gate, real = threading.Event(), control_strip.set_heal

    def slow(*a, **k):
        gate.wait(10)                         # held until the test has seen the busy state
        return real(*a, **k)
    monkeypatch.setattr(control_strip, "set_heal", slow)
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            b.go(srv.url("/v2/incidents?list=Default"))
            b.wait_for("return !!window.htmx && window.NMAS && "
                       "NMAS.live().state === 'connected' && !!document.querySelector("
                       "arguments[0]) && " + SETTLED, 20, SWITCH)
            b.js("window.__notReloaded = 1; return 1")
            assert b.js(f"return document.querySelector('{SWITCH}').innerText") == "Dry run"
            b.click(SWITCH)
            b.wait_for(f"var e = document.querySelector('{SWITCH}'); return e.disabled && "
                       "getComputedStyle(e.querySelector('.op-busy')).display !== 'none'", 10)
            assert "Turning on Auto" in b.js(
                f"return document.querySelector('{SWITCH}').innerText")
            gate.set()
            b.wait_for(f"var e = document.querySelector('{SWITCH}'); return !!e && "
                       "e.getAttribute('aria-checked') === 'true' && "
                       "e.innerText.indexOf('Auto until') === 0 && " + SETTLED, 15)
            assert policy.current("Default")["mode"] == "auto"
            # Another person turns it to Dry run a moment later (the press's own announcement
            # heard first); the change is announced, the strip redrawn.
            b.wait_for("return !document.querySelector('.htmx-request')", 10)
            policy.apply_planned("Default", {policy.MODE_KEY: "dry_run"},
                                 actor="b@example.com", actor_verified="access", person=True,
                                 reason="elsewhere")
            # The pointer is still on the switch it pressed: a switch is never held stale.
            invalidation.announce(("settings",), by="heal-batch")
            b.wait_for("var f = document.querySelector('#control-strip [data-ctl=heal]'); "
                       "return !!f && f.getAttribute('data-state') === 'dry_run' && "
                       "f.querySelector('button').getAttribute('aria-checked') === 'false'",
                       15)
            assert b.js(f"return document.querySelector('{SWITCH}').innerText.trim()") == \
                "Dry run"
            assert b.js("return window.__notReloaded") == 1, "no reload"
        finally:
            gate.set()
            b.go("about:blank")
            browser.close_socketio_sessions()


def test_the_batch_card_is_drawn_with_its_preview_and_one_button():
    """The card's template from the provider's state (tests/v2_context.py `_attention_batch`)."""
    import app as nmas_app
    from flask import render_template

    from modules import attention
    decisions, doc, ai = batch_fixture(T0)
    p = B.preview("Lab", decisions, ai_items=ai, incidents_doc=doc)
    r = attention.row(source="heal", kind="held", key="hd-1", level="warning", event="hd-1",
                      devices=["r1"], what=p["lead"], cause=p["hold"],
                      action={"label": B.BUTTON, "open": "heal_batch", "list": "Lab"})
    r["batch"], r["batch_folded"] = p, []
    with nmas_app.app.test_request_context("/v2/"):
        html = render_template("v2/_heal_batch.html", r=r)
    assert "4 devices have faults. Mercury can fix 2." in html
    assert "Held by guard 6: 3 devices changed at once." in html
    assert " description to-r2" in html and "banner motd" in html
    assert html.count("Turn on self-healing and fix all") >= 1
    assert f'value="{p["hash"]}"' in html


def test_the_default_duration_is_one_hour_and_n8_still_bounds_it():
    from modules.settings_schema import DEFAULTS, validate
    assert DEFAULTS["heal_auto_default_hours"] == 1
    assert not validate(dict(DEFAULTS, heal_auto_default_hours=24))[0]
    assert validate(dict(DEFAULTS, heal_auto_default_hours=8))[0]
    assert iso  # the shared clock's helper (imported for the policy fixtures)
