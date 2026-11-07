"""C2701: the deploy's save to startup waits on verify's result, and a verify that did not pass
holds the save until a person decides.

The defect (the operator, 2026-11-07): `pipeline._stage_save_startup` saved every device whose
push succeeded and never read `ctx.verify_result`, so a verify that did not pass without failing
(a read-back miss, a protocol unmet, a read not trusted) was in startup anyway: "Saved to
startup, although verify did not pass" on r4's and s1's archive deploys, against the stage's own
words ("only once verify passed", C501). The operator's decision: "a failed read-back holds the
startup save until a person decides, naming why; a rollback trigger is separate."

Each state, from the save stage to the receipt, the result's words, Needs attention's row and
the cards:

- verify PASSED: saved (`saved`), the one save there is called;
- verify did NOT pass (a sent line not read back): HELD, nothing sent, verify's own words;
- verify UNREAD (no result recorded for the device): HELD, never a pass;
- verify FAILED: rolled back, the save never reached (unchanged; tests/
  test_rollback_undoes_what_landed.py), and a hold starts no rollback.

The receipts are the real route's (`deploy_core.apply` through the real `_deploy_one` and the
real pipeline runner, its save stage real), from tests/test_attention_actions_follow_outcome.py's
harness: only the device stages are stubbed, each recording what its real stage records.
"""

import pytest

from modules import attention as A
from tests.test_attention_actions_follow_outcome import (  # noqa: F401 (the fixture)
    IP, NO_STARTUP, VERIFY_OK, _apply, _drawn, _persist, _s4, _s4_rows, store)
#: A verify that did not pass without failing: one sent line not read back (the real stage's
#: shape, `verify_scope.read_back`: the line as sent, its leading space kept).
MISSED = dict(VERIFY_OK, ok=False,
              read_back={"checked": 2, "missing": [" shutdown"], "skipped": []})
#: Verify's own words for it (`preview_confirm.read_back_missed`).
MISSED_WORDS = "1 sent line(s) did not read back:  shutdown"


def _ctx():
    """test_rollback_undoes_what_landed's context (a real row's encrypted fields), at s4's IP."""
    from tests.test_rollback_undoes_what_landed import _ctx as ctx_of
    ctx = ctx_of()
    ctx.device_ips = [IP]
    ctx.selected_devices = [dict(ctx.selected_devices[0], ip=IP, hostname="s4")]
    ctx.rendered_commands = {}
    return ctx


@pytest.fixture
def saves(monkeypatch):
    """The one save there is, counted: what it was called for."""
    called = []
    monkeypatch.setattr("modules.nsot.onboard.persist_on_device",
                        lambda ip, *a, **k: (called.append(ip), {"ok": True})[1])
    return called


class TestTheSaveStage:
    def test_a_verify_that_passed_is_saved(self, saves):
        import modules.pipeline as P
        ctx = _ctx()
        ctx.push_results = {IP: {"ok": True}}
        ctx.verify_result = {IP: dict(VERIFY_OK)}
        P._stage_save_startup(ctx)
        assert saves == [IP] and ctx.saved_startup[IP] == {"ok": True}

    def test_a_verify_that_did_not_pass_is_held_and_nothing_is_sent(self, saves):
        import modules.pipeline as P
        ctx = _ctx()
        ctx.push_results = {IP: {"ok": True}}
        ctx.verify_result = {IP: dict(MISSED)}
        P._stage_save_startup(ctx)                     # a hold is no failed save: no raise
        assert saves == [], "a verify that did not pass is never saved"
        got = ctx.saved_startup[IP]
        assert got.get("ok") is False and got.get("held") is True, got
        assert got.get("why") == MISSED_WORDS, got

    def test_a_verify_that_recorded_nothing_is_held(self, saves):
        import modules.pipeline as P
        ctx = _ctx()
        ctx.push_results = {IP: {"ok": True}}
        P._stage_save_startup(ctx)
        got = ctx.saved_startup.get(IP) or {}
        assert saves == [] and got.get("held") is True, (saves, got)
        assert "verify recorded no result" in got.get("why", ""), got

    def test_the_paired_deploys_held_save_follows_the_same_rule(self, saves):
        import modules.pipeline as P
        ctx = _ctx()
        ctx.hold_save = True
        ctx.push_results = {IP: {"ok": True}}
        ctx.verify_result = {IP: dict(MISSED)}
        P._stage_save_startup(ctx)
        assert saves == [] and ctx.saved_startup == {}, "held for the link's verify first"
        got = P.save_held(ctx)
        assert saves == [] and (got.get(IP) or {}).get("held") is True, got

    def test_a_hold_starts_no_rollback(self, monkeypatch, saves):
        import modules.pipeline as P
        from modules.pipeline import STAGE_NAMES, PipelineRunner

        order = []
        for name in STAGE_NAMES:
            if name in ("save_startup", "audit_log"):
                continue

            def stage(ctx, _n=name):
                order.append(_n)
                if _n == "deploy":
                    ctx.push_results = {IP: {"ok": True}}
                if _n == "verify":
                    ctx.verify_result = {IP: dict(MISSED)}
            monkeypatch.setattr(P, f"_stage_{name}", stage)
        monkeypatch.setattr(P, "_stage_audit_log", lambda ctx: None)
        monkeypatch.setattr(P, "_stage_rollback", lambda ctx: order.append("rollback"))
        ctx = PipelineRunner(_ctx()).run()
        assert "rollback" not in order and ctx.final_status == "success", order
        assert "save_startup" in ctx.stages_completed and not ctx.stages_failed
        assert (ctx.saved_startup.get(IP) or {}).get("held") is True and saves == []


class TestTheReceiptAndItsWords:
    def test_passed_is_saved(self, monkeypatch, store):
        _out, row = _apply(monkeypatch, startup=_s4())
        assert row["saved_startup"] == {"state": "saved", "detail": ""}

    def test_not_passed_is_held_with_verifys_words(self, monkeypatch, store):
        _out, row = _apply(monkeypatch, startup=_s4(), verify=MISSED)
        assert row["outcome"] == "deployed" and row["stage"] == "", row
        assert row["saved_startup"] == {
            "state": "held", "detail": MISSED_WORDS}

    def test_the_held_words_name_verify_and_the_decision(self):
        from modules.preview_confirm import saved_startup_words
        w = saved_startup_words({"state": "held", "detail": "bgp"})
        assert w["state"] == "held"
        assert w["words"].startswith("Held, NOT saved to startup: verify did not pass (bgp); "
                                     "Persist… on its device page saves it, or roll back"), w
        assert "no control rolls back" in w["words"]

    def test_a_held_save_is_never_green_and_is_said_among_what_did_not_happen(
            self, monkeypatch, store):
        from modules.preview_confirm import operation_result, result_level
        _out, row = _apply(monkeypatch, startup=_s4(), verify=MISSED)
        assert result_level([row], receipt_ok=True) == "partial"
        # Even with verify's own verdict taken as passed, a held save is never green.
        assert result_level([dict(row, checks={"ran": True, "ok": True})],
                            receipt_ok=True) == "partial"
        got = operation_result([row], {}, {"ok": True}, "deploy")
        (t,) = got["targets"]
        assert t["saved"]["state"] == "held" and "Persist…" in t["saved"]["words"]
        held = [i for i in got["did_not"]["items"] if i["kind"] == "held"]
        assert len(held) == 1 and f"({MISSED_WORDS})" in held[0]["text"]

    def test_a_receipt_from_before_the_hold_keeps_its_words(self):
        from modules.preview_confirm import _saved_after
        old = {"saved_startup": {"state": "saved", "detail": ""},
               "checks": {"ran": True, "ok": False}}
        assert _saved_after(old)["words"].startswith(
            "Saved to startup, although verify did not pass")


class TestNeedsAttention:
    def test_a_held_save_is_its_row_with_persist(self, monkeypatch, store):
        _apply(monkeypatch, startup=_s4(), verify=MISSED)
        (r,) = _s4_rows(A.deploy_source())
        assert (r["kind"], r["level"]) == ("held", "warning"), r
        assert "HELD" in r["what"] and "verify did not pass" in r["what"]
        assert f"Held, NOT saved to startup: verify did not pass ({MISSED_WORDS})" in r["cause"]
        assert r["action"].get("open") == "persist" and r["action"]["device"] == "s4"
        assert "no control rolls back" in r["action"]["label"]
        assert "Persist" in r["clears"]["when"]
        assert ">Persist s4…</a>" in _drawn(r)

    def test_unread_verify_is_held_too(self, monkeypatch, store):
        unread = dict(VERIFY_OK, ok=False, unreadable=["new lines: `show running-config`: "
                                                       "timed out"])
        _out, row = _apply(monkeypatch, startup=_s4(), verify=unread)
        assert row["saved_startup"]["state"] == "held"
        (r,) = _s4_rows(A.deploy_source())
        assert r["kind"] == "held" and "timed out" in r["cause"]

    def test_a_persist_read_back_after_it_clears_it(self, monkeypatch, store):
        _apply(monkeypatch, startup=_s4(), verify=MISSED)
        assert _persist(_s4())["ok"] is True
        res = A.deploy_source()
        assert _s4_rows(res) == [], res["rows"]

    def test_a_persist_that_did_not_read_back_safe_leaves_it(self, monkeypatch, store):
        _apply(monkeypatch, startup=_s4(), verify=MISSED)
        assert _persist(NO_STARTUP)["ok"] is False
        assert [r["kind"] for r in _s4_rows(A.deploy_source())] == ["held"]

    def test_a_worse_fault_is_the_failed_row_saying_the_hold(self):
        row = {"device": "s4", "outcome": "deployed", "sent": True, "action": "deploy",
               "matches_confirmed": False, "at": "2026-11-07T00:00:00Z",
               "checks": {"ran": True, "ok": False},
               "saved_startup": {"state": "held", "detail": "bgp"}}
        res = A.deploy_source(read=lambda: {"state": "ok", "rows": [row]})
        (r,) = _s4_rows(res)
        assert r["kind"] == "failed" and "Held, NOT saved to startup" in r["cause"]
        assert r["action"].get("open") == "persist"


class TestTheCards:
    def test_the_restore_card_says_the_held_save(self):
        from modules import device_actions as D
        ref = type("Ref", (), {"name": "Lab"})()
        words = "Held, NOT saved to startup: verify did not pass (bgp); …"
        got = {"state": "done", "payload": {"ref": "HEAD", "result": {
            "level": "partial",
            "happened": {"targets": [{"name": "s4", "outcome": "deployed", "words": "done"}]},
            "targets": [{"name": "s4", "saved": {"state": "held", "words": words}}],
            "did_not": {"items": [{"target": "s4", "kind": "held", "text": words}]}}}}
        deploy = D.deploy_job_card(ref, "s4", "j1", got)
        assert deploy["saved"]["words"] == words and words not in deploy["did_not"], \
            "the deploy card says it once, as its saved line"
        restore = D.restore_job_card(ref, "s4", "j1", got)
        assert restore["did_not"][:1] == [words], "the restore card draws no saved line"

    def test_the_confirm_says_the_save_waits_on_verify(self):
        from modules import preview_confirm as PC
        assert "waits on verify" in PC.SAVE_WAITS_ON_VERIFY
        import app as APP
        with APP.app.test_request_context("/v2/"):
            from flask import request
            got = PC.restore_preview([], [], ref="HEAD", summary="", scope="", request=request)
        assert got["confirm"].get("effect") == PC.SAVE_WAITS_ON_VERIFY

    def test_the_deploy_preview_and_its_card_carry_it(self):
        from modules import device_actions as D
        from modules import preview_confirm as PC
        import app as APP
        with APP.app.test_request_context("/v2/"):
            from flask import request
            # One device, blocked: the confirm's words do not depend on the program.
            got = PC.deploy_preview([{"device": "r2", "deployable": False,
                                      "blocking_reasons": ["a planted block"]}], request)
        assert got["confirm"].get("effect") == PC.SAVE_WAITS_ON_VERIFY
        # The card's `effect`, drawn as the op-note before the confirm (`_deploy.html`).
        ref = type("Ref", (), {"name": "Lab"})()
        card = D.deploy_card(ref, "r2", {}, got, {"may": False, "statement": "nobody"})
        assert card["effect"] == PC.SAVE_WAITS_ON_VERIFY
