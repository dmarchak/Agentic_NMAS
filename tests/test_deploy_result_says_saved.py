"""C511 (the operator, 2026-10-05, the throwaway session's Part 6): since C501 a deploy saves to
startup only once verify passes (`pipeline._stage_save_startup`, per device in
`ctx.saved_startup`), and neither the receipt nor the result card said so, so "saved" and
"running and not saved" read alike. Every carried field is drawn.

The receipt row carries `saved_startup` (`receipts._saved_startup`: saved, not saved with why,
or not run with why); the result names it per device, a not-saved device is never green and is
said once on the device page's card, with Persist as the way on; coverage's apply-job card
draws it in each device's evidence.
"""

import pytest

from modules.nsot.receipts import rows_for


def _result(**over):
    """One device's result as `routes/deploy._deploy_one` returns it."""
    base = {"device": "r2", "outcome": "deployed", "commands": ["ntp server 192.0.2.5"],
            "stage": "", "reason": "", "rolled_back": False, "program_hash": "h",
            "verify": {}, "saved_startup": {"ok": True}}
    base.update(over)
    return base


def _row(**over):
    (row,) = rows_for({"results": [_result(**over)], "golden": {}}, list_name="Lab",
                      command_hashes={"r2": "h"},
                      action="deploy", actor="op@example.invalid", actor_kind="person")
    return row


class TestTheReceiptRow:

    def test_saved(self):
        assert _row()["saved_startup"] == {"state": "saved", "detail": ""}

    def test_not_saved_carries_why(self):
        row = _row(saved_startup={"ok": False, "error": "after write memory the startup "
                                                        "config still lacks the change"})
        assert row["saved_startup"]["state"] == "not_saved"
        assert "still lacks the change" in row["saved_startup"]["detail"]

    @pytest.mark.parametrize("over, why", [
        ({"outcome": "failed", "rolled_back": True, "stage": "verify"}, "rolled back"),
        ({"outcome": "refused", "commands": []}, "nothing was sent"),
        ({"outcome": "failed", "stage": "deploy"}, "stopped at deploy"),
        ({}, "the save did not run"),
    ])
    def test_not_run_says_why(self, over, why):
        row = _row(**dict(over, saved_startup={}))
        assert row["saved_startup"]["state"] == "not_run" and why in row["saved_startup"][
            "detail"], row["saved_startup"]

    def test_the_pipelines_own_field_reaches_the_result(self):
        """`_deploy_one` reads `saved_startup` off the pipeline's result by the device's
        address: the field name is the pipeline's (a parse of the route, never a substring)."""
        import ast
        import inspect

        import routes.deploy as D
        from modules.pipeline import PipelineContext

        tree = ast.parse(inspect.getsource(D._deploy_one))
        keys = {k.value for n in ast.walk(tree) if isinstance(n, ast.Dict)
                for k in n.keys if isinstance(k, ast.Constant)}
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert "saved_startup" in keys and "saved_startup" in attrs
        assert "saved_startup" in PipelineContext.__dataclass_fields__


class TestTheResult:

    def _out(self, **over):
        from modules.preview_confirm import operation_result
        return operation_result([_row(**over)], {}, {"ok": True, "written": 1}, "deploy")

    def test_saved_is_said_and_green(self):
        out = self._out()
        assert out["level"] == "success"
        assert out["targets"][0]["saved"]["words"] == "Saved to startup after verify"

    def test_not_saved_is_never_green_and_is_a_thing_not_done(self):
        out = self._out(saved_startup={"ok": False, "error": "timed out"})
        assert out["level"] == "partial"
        (item,) = [i for i in out["did_not"]["items"] if i["kind"] == "not_saved"]
        assert "NOT saved to startup" in item["text"] and "timed out" in item["text"]
        assert "Persist" in item["text"]

    def test_a_receipt_from_before_says_so(self):
        from modules.preview_confirm import operation_result
        row = _row()
        row.pop("saved_startup")
        out = operation_result([row], {}, {"ok": True}, "deploy")
        assert out["targets"][0]["saved"]["state"] == "unrecorded"


def _render(template, **ctx):
    from flask import render_template

    import app as APP
    with APP.app.test_request_context("/v2/"):
        return render_template(template, **ctx)


class TestTheCardsDrawIt:

    class Ref:
        name = "Lab"

    def _card(self, **over):
        from modules import device_actions
        from modules.preview_confirm import operation_result

        result = operation_result([_row(**over)], {}, {"ok": True, "written": 1}, "deploy")
        got = {"state": "done", "payload": {"result": result}}
        c = device_actions.deploy_job_card(self.Ref(), "r2", "job1", got)
        return _render("v2/_deploy.html", c=dict(c, back=""))

    def test_the_device_card_says_saved(self):
        assert "Saved to startup after verify." in self._card()

    def test_the_device_card_says_not_saved_once_with_its_way_on(self):
        html = self._card(saved_startup={"ok": False, "error": "timed out"})
        assert html.count("NOT saved to startup") == 1, "said once"
        assert "timed out" in html and "Save it with Persist" in html

    def test_the_device_card_says_why_nothing_was_saved(self):
        html = self._card(outcome="failed", rolled_back=True, stage="verify", saved_startup={})
        assert "Not saved to startup: the change was rolled back" in html

    def test_the_apply_job_card_draws_it_in_the_evidence(self):
        from modules.preview_confirm import operation_result

        result = operation_result([_row(saved_startup={"ok": False, "error": "timed out"})],
                                  {}, {"ok": True, "written": 1}, "deploy")
        html = _render("v2/_apply_job.html", j={"state": "done", "payload": {"result": result}},
                       job="job1", arrivals=None)
        evidence = html.split('class="apply-evidence"')[1].split("</details>")[0]
        assert "NOT saved to startup" in evidence and "timed out" in evidence
