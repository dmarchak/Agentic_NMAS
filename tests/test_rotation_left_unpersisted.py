"""C541 (the operator, 2026-10-06, re-sorted to bucket A): a rotation left "rotated,
persistence not attempted" is the most dangerous state (the device runs the new credential and
its startup config holds the old one, so a reload boots the old credential), and its guidance
was wrong twice: the card said "Persist it" with only an Export button, and the Needs attention
row advised `nmas-persist-credential`, the containerlab chain its own code forbids for a
device's startup config (C50).

Now, wherever the remedy is the device's OWN save (persistence not attempted, or failed at its
startup config): the words name the risk and the save; the card's one button is Persist, in
place (tests/test_device_rotate_v2.py, through the real job route); the row carries Persist as
its action and draws a button to the device's Persist card; the browser summary never says
"runs next" over a job that has ended. A containerlab chain stage keeps its own command.
"""

import os

from modules import attention as A
from modules import job_health as J
from modules.nsot import credential_rotation as cr

AT = "2026-10-06T19:00:00Z"


def _row(state, stage=""):
    rec = {"device": "s1", "state": state, "at": AT, **({"failed_stage": stage} if stage else {})}
    (row,) = J.rotation_rows(records=[rec], known=({"s1"}, ""), held=set())
    return row


class TestTheRow:
    def test_not_attempted_names_the_risk_and_the_device_s_own_save(self):
        row = _row(cr.ROTATED_PENDING_PERSIST)
        assert row["state"] == "not_safe_to_reboot"
        assert "a reload would boot the old credential" in row["detail"]
        act = row["action"]
        assert act["open"] == "persist" and act["device"] == "s1"
        assert act["command"] == "nmas-persist-native s1 --list <its list>"
        assert "nmas-persist-credential" not in row["detail"] + str(act)

    def test_failed_at_the_device_s_startup_config_is_its_own_save_too(self):
        act = _row(cr.ROTATED_UNVERIFIED, "device_startup_config")["action"]
        assert act["open"] == "persist" and "nmas-persist-native" in act["command"]

    def test_a_lab_chain_stage_keeps_the_chain_s_command(self):
        """The scope: `nmas-persist-credential` is right for a containerlab boot file."""
        row = _row(cr.ROTATED_UNVERIFIED, "lab_startup_file")
        assert "nmas-persist-credential s1" in row["detail"]

    def test_needs_attention_draws_the_persist_button(self):
        from flask import render_template

        import app as APP
        r = A.row(source="job_health", kind="job", key="rotation:s1", what="s1 not safe",
                  cause="c", action=_row(cr.ROTATED_PENDING_PERSIST)["action"],
                  level="danger", read_at=1_999_999_000.0)
        with APP.app.test_request_context("/v2/"):
            html = render_template("v2/_attention.html", a={
                "ok": True, "rows": [r], "sources": [], "headline": "1", "counts": {},
                "badge": {"n": 1, "level": "danger"}})
        action = html.split('class="att-action"')[1].split("</div>")[0]
        assert 'href="/v2/device/s1?op=persist"' in action and "Persist s1…" in action
        assert "is not on these pages yet" not in action


class TestTheWords:
    def _summary(self, state, stage="device_startup_config", where="browser"):
        return cr.summarise({"device": "s1", "state": state, "persistence": [
            {"name": stage, "ok": False, "error": "x"}]}, where=where)

    def test_a_browser_never_says_runs_next_over_a_job_that_ended(self):
        words = self._summary(cr.ROTATED_PENDING_PERSIST)
        assert "runs next" not in words and "a reload would boot it" in words

    def test_the_terminal_between_rotate_and_persist_still_says_it_runs_next(self):
        assert "runs next" in self._summary(cr.ROTATED_PENDING_PERSIST, where="cli")

    def test_failed_at_the_startup_config_names_the_device_s_own_save(self):
        words = self._summary(cr.ROTATED_UNVERIFIED)
        assert "nmas-persist-native s1" in words and "nmas-persist-credential" not in words

    def test_a_lab_chain_stage_still_names_the_chain(self):
        assert "nmas-persist-credential s1" in self._summary(cr.ROTATED_UNVERIFIED,
                                                              stage="lab_startup_file")

    def test_the_card_s_next_step_opens_persist(self):
        from modules.preview_confirm import rotate_result
        plan = {"device": "s1", "list_name": "Lab", "new_program": []}
        for state, stage, opens in ((cr.ROTATED_PENDING_PERSIST, "device_startup_config",
                                     "persist"),
                                    (cr.ROTATED_UNVERIFIED, "device_startup_config", "persist"),
                                    (cr.ROTATED_UNVERIFIED, "lab_startup_file", ""),
                                    (cr.ROTATED_PERSISTED, "", "breakglass_export")):
            got = rotate_result({"device": "s1", "state": state, "steps": [], "persistence": [
                {"name": stage, "ok": state != cr.ROTATED_UNVERIFIED and
                 state != cr.ROTATED_PENDING_PERSIST}] if stage else []}, plan)
            assert got["next"]["open"] == opens, (state, stage, got["next"])


def test_the_manual_names_persist_for_this_state():
    page = open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "manual",
                             "how-it-works", "rotate.md"), encoding="utf-8").read()
    assert "persistence not attempted" in page.lower() and "Persist" in page
