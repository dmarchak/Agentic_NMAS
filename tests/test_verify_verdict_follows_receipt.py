"""The verify verdict a result draws is the receipt's own decision, `checks.ok` (C1541's second
half), and Needs attention names a read-back miss (C1542).

r7's deploy of 2026-10-22 07:16:53Z sent 8 lines, matched the confirmed program and was saved;
verify could not read back its 3 vty lines (r7 prints `line vty 0 4` split, C1541's first half),
so the receipt records `checks.ok` false with no issue, nothing unmet and nothing unreadable: the
pipeline adds a read-back miss to `issues` only on Coverage's combined deploy (`read_back_all`).
The device card drew "done" with no verdict and "Saved to startup after verify", the batch
stepper drew its Verify step done, and Needs attention drew a red row whose cause was "its
receipt records deployed with no reason".

The receipt here is built by the real code (`receipts.rows_for`) from the pipeline's result as
r7's deploy returned it (the program is the one r7's receipt records,
tests/test_verify_read_back_line_ranges.py), and the floor holds it to the fields that receipt
records. No address is parsed, compared or stored by these checks, so the IPv6 parity rule has
no case here.
"""

import html as html_mod
import re
import time

from modules import attention as A
from modules.nsot.receipts import rows_for
from modules.preview_confirm import operation_result, verify_verdict
from tests.payload_render import render_device_deploy_result_v2, render_operation_result_v2
from tests.test_acknowledge import _ack, _attention, _only, store  # noqa: F401 (the fixture)
from tests.test_verify_read_back_line_ranges import R7_PROGRAM

AT = "2026-10-22T07:16:53Z"
R7_MISSING = ["line vty 0 4 > logging synchronous", "line vty 0 4 > login local",
              "line vty 0 4 > transport input ssh"]
R7_SKIPPED = [{"line": "interface GigabitEthernet3 > no shutdown",
               "why": "a `no` line reads back as an absence"}]
#: The sentence a read-back miss is said in, everywhere it is said.
R7_SENTENCE = "3 sent line(s) did not read back: " + "; ".join(R7_MISSING)


def _r7_result(**verify_over) -> dict:
    """r7's device result as `routes/deploy._deploy_one` returned it."""
    verify = {"ok": False, "issues": [], "unreadable": [], "intent_unmet": [],
              "checked_protocols": ["rip", "ripng"],
              "read_back": {"checked": 3, "missing": list(R7_MISSING),
                            "skipped": [dict(s) for s in R7_SKIPPED]}}
    verify.update(verify_over)
    return {"device": "r7", "outcome": "deployed", "commands": list(R7_PROGRAM), "stage": "",
            "reason": "", "rolled_back": False, "program_hash": "h7", "verify": verify,
            "saved_startup": {"ok": True}}


def r7_receipt(at: str = AT, **verify_over) -> dict:
    """r7's receipt row, written by the real `receipts.rows_for`."""
    (row,) = rows_for({"results": [_r7_result(**verify_over)], "golden": {}}, list_name="Lab",
                      command_hashes={"r7": "h7"}, action="deploy", actor="op@example.invalid",
                      actor_kind="person")
    return dict(row, at=at)


def r7_clean(at: str = AT) -> dict:
    """The control: the same deploy with every line read back (what O0's read-back answers)."""
    return r7_receipt(at, ok=True, read_back={"checked": 3, "missing": [],
                                              "skipped": [dict(s) for s in R7_SKIPPED]})


def _result(row):
    return operation_result([row], {}, {"ok": True, "written": 1}, "deploy")


def _text(page: str) -> str:
    return re.sub(r"\s+", " ", html_mod.unescape(re.sub(r"<[^>]+>", " ", page)))


def test_the_floor_the_receipt_is_r7s():
    r = r7_receipt()
    assert (r["outcome"], r["sent"], r["program_lines"], r["matches_confirmed"]) == \
        ("deployed", True, 8, True)
    assert r["saved_startup"]["state"] == "saved" and r["stage"] == "" and r["reason"] == ""
    c = r["checks"]
    assert (c["ran"], c["ok"], c["issues"], c["unreadable"], c["intent_unmet"]) == \
        (True, False, [], [], [])
    assert c["read_back"] == {"checked": 3, "missing": R7_MISSING, "skipped": R7_SKIPPED}
    assert r7_clean()["checks"]["ok"] is True


class TestTheVerdict:
    def test_r7s_receipt_did_not_pass_and_names_the_lines(self):
        v = verify_verdict(r7_receipt()["checks"])
        assert (v["ran"], v["ok"], v["words"]) == (True, False, "Verify did NOT pass")
        assert v["causes"] == [R7_SENTENCE]
        assert v["lines"] == [f"Verify did NOT pass: {R7_SENTENCE}"]

    def test_a_clean_receipt_passed(self):
        v = verify_verdict(r7_clean()["checks"])
        assert (v["ok"], v["words"], v["causes"], v["lines"]) == \
            (True, "Verify passed", [], ["Verify passed"])

    def test_ok_false_with_no_cause_recorded_never_reads_passed(self):
        v = verify_verdict({"ran": True, "ok": False})
        assert v["ok"] is False
        assert v["lines"] == ["Verify did NOT pass: its receipt records no cause for it"]

    def test_ok_absent_is_not_a_pass(self):
        assert verify_verdict({"ran": True})["ok"] is False

    def test_verify_that_did_not_run_has_no_verdict(self):
        assert verify_verdict({"ran": False, "why": "nothing was sent"})["words"] == ""

    def test_an_issue_that_already_says_it_is_not_said_twice(self):
        """Coverage's combined deploy puts the miss in its issues (`read_back_all`)."""
        v = verify_verdict(r7_receipt(issues=[R7_SENTENCE])["checks"])
        assert v["causes"] == [R7_SENTENCE]

    def test_each_cause_is_its_own_line_beside_the_others(self):
        v = verify_verdict(r7_receipt(intent_unmet=["rip is declared by intent and is not up"])
                           ["checks"])
        assert v["lines"] == ["Verify did NOT pass:", "rip is declared by intent and is not up",
                              R7_SENTENCE]

    def test_the_first_five_are_named_and_the_rest_marked(self):
        missing = [f"line vty 0 4 > exec-timeout {n} 0" for n in range(7)]
        v = verify_verdict(r7_receipt(read_back={"checked": 7, "missing": missing,
                                                 "skipped": []})["checks"])
        assert v["causes"] == ["7 sent line(s) did not read back: "
                               + "; ".join(missing[:5]) + " …"]

    def test_a_missed_line_is_masked(self):
        secret = "Zq8RtW3vLm"
        v = verify_verdict(r7_receipt(read_back={
            "checked": 1, "missing": [f"snmp-server community {secret} RO"],
            "skipped": []})["checks"])
        assert "snmp-server community" in v["causes"][0] and secret not in v["causes"][0], v


class TestTheDeviceCard:
    def test_r7s_card_says_verify_did_not_pass_naming_the_lines(self):
        page = render_device_deploy_result_v2(_result(r7_receipt()), "r7")
        text = _text(page)
        assert f"Verify did NOT pass: {R7_SENTENCE}" in text, text
        assert "Verify passed" not in text
        head = _text(re.search(r'<h2 id="op-title">(.*?)</h2>', page, re.S).group(1))
        assert head.strip() == "Deploy to r7 done, and its verify did not pass", head
        assert 'class="op-card op-warn"' in page and "op-ok" not in page
        assert "Saved to startup, although verify did not pass" in text
        assert "Saved to startup after verify" not in text

    def test_a_clean_deploy_still_reads_passed(self):
        page = render_device_deploy_result_v2(_result(r7_clean()), "r7")
        text = _text(page)
        assert "Verify passed" in text and "did NOT pass" not in text, text
        assert "Saved to startup after verify." in text
        assert 'class="op-card op-ok"' in page


class TestTheBatchCard:
    def _job(self, row):
        """The batch's job as `deploy_job.state` keeps it once ended, r7's trail noting each
        pipeline stage as it began."""
        from modules import pipeline
        t0 = time.time() - 60
        trail = [[name, t0 + i] for i, name in enumerate(pipeline.STAGE_NAMES)]
        return {"state": "done", "job": "t0", "list": "Lab", "elapsed_s": 60, "error": "",
                "steps": [{"device": "r7", "state": "done", "outcome": "deployed",
                           "trail": trail, "at": t0 + len(trail)}],
                "payload": {"result": _result(row)}}

    def _render(self, row):
        import app as nmas
        from flask import render_template
        from modules import deploy_job
        st = self._job(row)
        with nmas.app.test_request_context("/v2/monitoring/apply/job/t0"):
            return render_template("v2/_apply_job.html", j=st, job="t0",
                                   run=deploy_job.run_card(st, "Lab"), arrivals=None)

    def test_r7s_evidence_says_did_not_pass_and_names_the_lines(self):
        text = _text(render_operation_result_v2(_result(r7_receipt())))
        part = text[text.index("r7: what was sent"):]
        assert "Verify did NOT pass, checking rip, ripng." in part, part
        assert R7_SENTENCE in part and "Verify passed" not in part
        assert "Partly done" in text

    def test_the_verify_step_is_the_partial_one_never_done(self):
        page = self._render(r7_receipt())
        steps = {key: state for state, key in re.findall(
            r'<li class="run-step run-step-([a-z_]+)" data-step="([a-z_]+)"', page)}
        assert len(steps) >= 10, steps                 # the floor: every pipeline stage drawn
        assert steps["verify"] == "partial", steps
        assert [k for k, s in steps.items() if s != "done"] == ["verify"], steps

    def test_a_clean_batch_draws_every_step_done_and_verify_passed(self):
        page = self._render(r7_clean())
        assert "run-step-partial" not in page
        assert "Verify passed, checking rip, ripng." in _text(page)


class TestNeedsAttention:
    def _rows(self, *rows):
        return A.deploy_source(lambda: {"state": "ok", "rows": list(rows)})["rows"]

    def test_r7s_row_names_the_lines_and_what_failed(self):
        (r,) = self._rows(r7_receipt())
        assert (r["kind"], r["level"]) == ("read_back", "warning")
        assert r["what"] == "The last deploy to r7 landed; verify could not read back 3 line(s)"
        assert r["cause"].startswith(R7_SENTENCE + ". "), r["cause"]
        assert "with no reason" not in r["cause"]
        assert r["action"]["href"] == "/v2/device/r7?tab=history"
        assert "acknowledge" in r["action"]["label"] and "plan the deploy again" in \
            r["action"]["label"]
        assert r["acknowledge"] is True and r["event"] == AT
        assert r["clears"]["ways"] == ["resolves", "acknowledge"]
        assert r["operands"]["not_read_back"] == 3

    def test_a_clean_deploy_leaves_no_row(self):
        assert self._rows(r7_clean()) == []

    def test_a_later_clean_deploy_clears_it(self):
        assert self._rows(r7_clean("2026-10-22T08:00:00Z"), r7_receipt()) == []

    def test_a_miss_beside_another_finding_is_a_failed_row_naming_both(self):
        unmet = "rip is declared by intent and is not up after the change"
        (r,) = self._rows(r7_receipt(intent_unmet=[unmet]))
        assert r["kind"] == "failed" and r["level"] == "danger"
        assert r["what"] == "The last deploy to r7: done, and its verify did not pass"
        assert unmet in r["cause"] and R7_SENTENCE in r["cause"], r["cause"]

    def test_a_rolled_back_failure_keeps_its_words(self):
        row = r7_receipt(issues=["ospf: 5 -> 3 neighbours"],
                         read_back={"checked": 3, "missing": [], "skipped": []})
        row.update(outcome="failed", stage="verify", reason="verify failed",
                   rollback={"performed": True, "state": "restored"})
        (r,) = self._rows(row)
        assert r["kind"] == "failed" and r["level"] == "danger"
        assert r["what"] == "The last deploy to r7: failed"
        assert r["cause"] == ("verify failed; stopped at verify; verify found: ospf: 5 -> 3 "
                              "neighbours; rollback: restored")


class TestAcknowledgingIt:
    def _receipts(self, monkeypatch, *rows):
        monkeypatch.setattr("modules.nsot.receipts.read",
                            lambda *a, **k: {"state": "ok", "rows": list(rows)})

    def test_acknowledged_it_leaves_and_a_later_miss_raises_it(self, store, monkeypatch):  # noqa: F811
        _only(monkeypatch, "deploy_source")
        self._receipts(monkeypatch, r7_receipt())
        (r,) = _attention()["rows"]
        assert r["kind"] == "read_back" and r["acknowledge"]
        got = _ack(r["id"], r["event"], "r7 prints line vty 0 4 split; reseed after Lab 9")
        assert got.status_code == 200, got.get_json()
        assert _attention()["rows"] == []
        self._receipts(monkeypatch, r7_receipt("2026-10-22T09:00:00Z"), r7_receipt())
        again = _attention()["rows"]
        assert [x["event"] for x in again] == ["2026-10-22T09:00:00Z"]

    def test_a_failed_deploy_is_not_acknowledged(self, store, monkeypatch):  # noqa: F811
        _only(monkeypatch, "deploy_source")
        self._receipts(monkeypatch, r7_receipt(intent_unmet=["rip is not up"]))
        (r,) = _attention()["rows"]
        assert r["kind"] == "failed" and not r["acknowledge"]
        got = _ack(r["id"], AT, "looked at it and it was expected")
        assert got.status_code == 409 and "clears when its condition resolves" in \
            got.get_json()["error"]


def test_the_result_level_is_the_same_decision():
    """One decision: the level the card colours by and the verdict it says agree."""
    from modules.preview_confirm import result_level
    assert result_level([r7_clean()], True) == "success"
    assert verify_verdict(r7_clean()["checks"])["ok"] is True
    assert result_level([r7_receipt()], True) == "partial"
    assert verify_verdict(r7_receipt()["checks"])["ok"] is False
