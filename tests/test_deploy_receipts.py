"""C60, the receipt: what each deploy SENT, and what it was checked against.

Before this, "what did we push before this broke" had no answer. The
pipeline's audit omits the program, the golden commit holds the capture
after the push, and the confirmed hash lived only in the request. The rows
are built against a verify that reads real output (C62, C64-C68), which is
why they can name the checks that ran without recording "verified" for a
device checked against nothing.
"""

import json
import os
import re
import stat

import pytest

from modules.nsot import receipts
from modules.nsot.deploy import command_fingerprint
from tests.test_device_v2 import lab  # noqa: F401 (the fixture, for the History read-back)
from tests import deploy_core

PROGRAM = ["interface GigabitEthernet0/2", " shutdown", "exit",
           "snmp-server community Sup3rS3cretCommunity RO"]
AUTHORISED = [{"line": "shutdown", "reason": "planned maintenance, port unused"}]


def _sent(**over):
    """A result shaped as `_deploy_one` returns it for a device that was
    pushed and verified, with the routing protocols r3 runs."""
    r = {"device": "r3", "outcome": "deployed", "stage": "", "reason": "",
         "commands": PROGRAM, "authorised": AUTHORISED,
         "program_hash": command_fingerprint(PROGRAM, AUTHORISED),
         "verify": {"ok": True, "issues": [], "checked_protocols": ["bgp", "ospf"],
                    "pre": {"routing_protocols": {"bgp": 1, "ospf": 6}, "routes": 30,
                            "interfaces_up": 5},
                    "post": {"routing_protocols": {"bgp": 1, "ospf": 6}, "routes": 30,
                             "interfaces_up": 5}},
         "rolled_back": False, "rollback_commands": [], "rollback_not_undone": [],
         "pending_convergence": []}
    r.update(over)
    return r


def _rows(results, **kw):
    report = {"results": results,
              "golden": {"commit": "abc123", "batch_id": "b-1",
                         "devices": [r["device"] for r in results
                                     if r.get("outcome") == "deployed"]}}
    return receipts.rows_for(report, list_name="Default", action="deploy",
                             actor="test-person@example.invalid", actor_kind="person",
                             **kw)


class TestARow:
    def test_what_was_sent_masked_and_hashed(self):
        row = _rows([_sent()], command_hashes={"r3": command_fingerprint(PROGRAM, AUTHORISED)})[0]
        assert row["sent"] is True and row["program_lines"] == 4
        assert "Sup3rS3cretCommunity" not in json.dumps(row), "the program is masked"
        assert row["program"][0] == "interface GigabitEthernet0/2"
        assert row["matches_confirmed"] is True
        assert row["golden_commit"] == "abc123" and row["batch_id"] == "b-1"

    def test_a_hash_that_differs_from_the_confirmed_one_says_so(self):
        row = _rows([_sent()], command_hashes={"r3": "0000000000000000"})[0]
        assert row["matches_confirmed"] is False

    def test_it_names_the_checks_that_ran(self):
        checks = _rows([_sent()])[0]["checks"]
        assert checks["ran"] is True and checks["checked_protocols"] == ["bgp", "ospf"]
        assert checks["neighbours"] == {"bgp": [1, 1], "ospf": [6, 6]}
        assert checks["routes"] == [30, 30]

    def test_no_routing_protocol_is_a_real_state_not_a_skipped_check(self):
        """r6: static only. Verify ran; the neighbour check does not apply."""
        verify = {"ok": True, "issues": [], "checked_protocols": [],
                  "pre": {"routing_protocols": {}, "routes": 3, "interfaces_up": 3},
                  "post": {"routing_protocols": {}, "routes": 3, "interfaces_up": 3}}
        checks = _rows([_sent(device="r6", verify=verify)])[0]["checks"]
        assert checks["ran"] is True and checks["checked_protocols"] == []
        assert "no routing protocol" in checks["neighbours_note"]

    @pytest.mark.parametrize("result,why", [
        ({"device": "s4", "outcome": "refused", "reason": "not confirmed"}, "refused before"),
        ({"device": "s4", "outcome": "deployed", "reason": "nothing to change",
          "commands": []}, "nothing to change"),
        ({"device": "s4", "outcome": "failed", "stage": "deploy",
          "commands": PROGRAM, "verify": {}}, "stopped at: deploy"),
    ])
    def test_a_device_where_verify_did_not_run_says_why(self, result, why):
        row = _rows([result])[0]
        assert row["checks"]["ran"] is False and why in row["checks"]["why"]

    def test_a_refused_device_has_a_row_and_was_not_sent(self):
        rows = _rows([_sent(), {"device": "s4", "outcome": "refused", "reason": "x"}])
        assert [(r["device"], r["sent"]) for r in rows] == [("r3", True), ("s4", False)]

    def test_what_is_not_built_says_so(self):
        row = _rows([_sent()])[0]
        assert row["follow_up"]["state"] == "not_run"
        assert row["second_reading"]["state"] == "not_built"


class TestARunThatStoppedBeforeTheSendSentNothing:
    """C1540 (Lab 9, 2026-10-22): r7's deploy failed at pre_snapshot ("Authentication to device
    failed") with its program in hand, and its receipt read "It received 8 line(s)" though
    nothing landed. A run that stopped at a stage before the send sent nothing, and says where
    it stopped and why; one that stopped at the send or after it sent its program."""

    def _failed(self, stage, reason="Authentication to device failed"):
        return _sent(outcome="failed", stage=stage, reason=reason, verify=None)

    @pytest.mark.parametrize("stage", receipts.stages_before_send())
    def test_a_stop_before_the_send_is_not_sent(self, stage):
        (row,) = _rows([self._failed(stage)])
        assert row["sent"] is False and row["program_lines"] == len(PROGRAM), row

    @pytest.mark.parametrize("stage", ["deploy", "post_snapshot", "verify"])
    def test_a_stop_at_the_send_or_after_it_was_sent(self, stage):
        (row,) = _rows([self._failed(stage)])
        assert row["sent"] is True

    def test_the_stages_before_the_send_are_the_pipeline_s_up_to_deploy(self):
        from modules.pipeline import STAGE_NAMES
        assert receipts.stages_before_send() == (
            "netbox_query", "template_render", "ci_gate", "pre_snapshot", "config_diff")
        assert set(receipts.stages_before_send()) < set(STAGE_NAMES)

    def test_every_stage_before_the_send_has_words_to_name_it(self):
        """`_nothing_sent` names the stage by its words with no fallback, so each stage before
        the send must have them."""
        from modules.pipeline import STAGE_WORDS
        assert set(receipts.stages_before_send()) <= set(STAGE_WORDS)
        assert all(isinstance(STAGE_WORDS[s][0], str) and STAGE_WORDS[s][0]
                   for s in receipts.stages_before_send())

    def test_the_result_says_where_it_stopped_and_why_and_counts_no_line(self):
        from modules.preview_confirm import operation_result
        from tests.payload_render import render_operation_result_v2

        rows = _rows([self._failed("pre_snapshot")])
        out = operation_result(rows, {"results": []}, {"ok": True, "path": "x"}, "deploy")
        (target,) = out["targets"]
        assert target["sent"]["lines"] == [] and target["sent"]["none"] == (
            "Nothing was sent: it stopped at Read before, Authentication to device failed")
        html = render_operation_result_v2(out)
        assert "It received" not in html and "it stopped at Read before" in html, html

    def test_a_stop_before_the_send_with_no_reason_still_says_where(self):
        from modules.preview_confirm import _nothing_sent
        assert _nothing_sent({"stage": "config_diff", "reason": ""}) == (
            "Nothing was sent: it stopped at Compare")
        assert _nothing_sent({"stage": "", "reason": ""}) == "Nothing was sent."
        assert _nothing_sent({"reason": ""}) == "Nothing was sent."
        assert _nothing_sent({"stage": "removal", "reason": "a unit moved"}) == "a unit moved"


class TestTheFile:
    def test_append_only_0600_and_newest_first(self):
        receipts.write("Default", _rows([_sent()]))
        receipts.write("Default", _rows([_sent(device="s3")]))
        path = receipts.path_for("Default")
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
        got = receipts.read("Default")
        assert got["state"] == "ok" and [r["device"] for r in got["rows"]] == ["s3", "r3"]
        assert [r["device"] for r in receipts.read("Default", device="r3")["rows"]] == ["r3"]

    def test_absent_is_not_empty_and_unreadable_is_neither(self):
        assert receipts.read("Default")["state"] == "absent"
        with open(receipts.path_for("Default"), "w") as fh:
            fh.write('{"device": "r3"}\nnot json\n')
        assert receipts.read("Default")["state"] == "unreadable"

    def test_a_failed_write_is_loud_and_never_raises(self, monkeypatch):
        import modules.config as config

        def boom(*_a, **_k):
            raise OSError("disk full")
        monkeypatch.setattr(config, "open_secure", boom)
        out = receipts.write("Default", _rows([_sent()]))
        assert out["ok"] is False and "could not be written" in out["error"]

    @pytest.mark.real_receipts_path
    def test_the_real_path_is_in_the_lists_directory_and_resolving_creates_nothing(self):
        from modules.config import list_data_path
        path = receipts.path_for("No Such List 7f3")
        assert path == os.path.join(list_data_path("No Such List 7f3"), receipts.FILENAME)
        assert not os.path.exists(os.path.dirname(path))


class TestTheApplyWritesIt:
    def _apply(self, mp, deploy_one, commit=None):
        import routes.deploy as rd
        from tests import payload_providers as P

        P.deploy_plan(mp)       # installs the artifact stubs
        # The fixture's program holds `shutdown`, so the plan the operator
        # confirms carries its authorisation, as the wizard's re-plan does.
        plan = deploy_core.post_plan(json={
            "devices": ["s4"], "authorise": {"s4": [{"line": "shutdown", "reason": "planned maintenance, port unused"}]}}).get_json()
        device = plan["devices"][0]
        assert device["authorisation_ok"] is True
        mp.setattr(rd, "_deploy_one", deploy_one)
        if commit is not None:
            mp.setattr(rd, "_commit_batch_golden", commit)
        return plan, deploy_core.post_apply(json={
            "confirmations": {"s4": device["capture_hash"]},
            "command_hashes": {"s4": device["command_hash"]},
            "authorise": {"s4": [{"line": "shutdown", "reason": "planned maintenance, port unused"}]},
        }).get_json()

    def test_a_row_per_device_after_the_commit_by_the_verified_person(self, monkeypatch):
        def deploy_one(entry, list_name, device_rows, authorise=None, source_ref=""):
            return _sent(device=entry["artifact"].device)

        _plan, out = self._apply(monkeypatch, deploy_one,
                                 commit=lambda *a, **k: {"commit": "c0ffee", "batch_id": "b-9",
                                                         "devices": ["s4"]})
        assert out["receipts"] == {"ok": True, "written": 1, "error": ""}
        row = receipts.read(out["list"])["rows"][0]
        assert (row["device"], row["golden_commit"], row["batch_id"]) == ("s4", "c0ffee", "b-9")
        assert row["actor"] == "test-person@example.invalid" and row["actor_kind"] == "person"
        assert row["checks"].get("checked_protocols") == ["bgp", "ospf"], row["checks"]

    def test_the_commit_names_each_program_by_hash(self, monkeypatch):
        """The golden commit is the capture AFTER the push; the trailer names
        the program that produced it."""
        import routes.deploy as rd

        seen = {}

        def save_golden(*_a, **kw):
            seen["trailers"] = kw.get("extra_trailers")
            return {"ok": True, "commit": "c0ffee"}

        monkeypatch.setattr("modules.nsot.repo.save_golden", save_golden)
        monkeypatch.setattr("modules.nsot.repo.clear_post_deploy_staging", lambda *a, **k: None)
        monkeypatch.setattr(rd, "_baseline_earned", lambda *a, **k: {"baseline": False})
        result = _sent(device="s4", golden_pending=[{
            "hostname": "s4", "config_text": "hostname s4\n", "mgmt_ip": "203.0.113.4",
            "netbox_id": None, "device_uid": "uid:x"}])
        rd._commit_batch_golden("Default", {"results": [result]})
        assert f"Program-Hash: s4={result['program_hash']}" in seen["trailers"]


class TestTheResultScreenSaysWhatWasChecked:
    """v2's drawing of the result, the batch's card once its job has ended
    (`templates/v2/_apply_job.html`), executed against the real apply's result (a deployed
    row and a refusal, from `payload_providers.deploy_apply`). Today's renderer drew it until it
    left with today's index at 7.8 (P7-27)."""

    def _render(self, monkeypatch):
        """7.1 step 2: the result is the component's, built from the receipt
        rows the apply wrote."""
        from tests import payload_providers as P
        from tests.payload_render import render_operation_result_v2

        report = P.deploy_apply(monkeypatch)
        return report, render_operation_result_v2(report["result"])

    def test_each_row_names_its_checks_and_the_receipt_is_reported(self, monkeypatch):
        report, html = self._render(monkeypatch)
        assert {r["device"]: r["outcome"] for r in report["results"]} == \
            {"s3": "refused", "s4": "deployed"}, "the fixture must exhibit both"
        s4 = html[html.index("<summary>s4:"):]
        s3 = html[html.index("<summary>s3:"):html.index("<summary>s4:")]
        assert "Verify passed, checking ospf." in s4
        assert "Nothing was verified: refused before anything was sent" in s3
        assert "Receipt: 2 device row(s) recorded" in html
        assert "matches the program you confirmed" in s4
        # Today's renderer also drew each program's hash ("line(s) sent, program <hash>");
        # v2's card does not (the register row named in the P7-27 commit).


#: A row's check lists carried and not drawn by v2's batch card, measured 2026-10-17 (P7-27);
#: only shrinks. The register row named in that commit; today's renderer drew it, and the row's
#: `from_intent` ("not running before"), which v2's card does not draw either.
UNDRAWN_ON_V2 = ("pending_convergence",)


class TestEveryCheckListIsDrawnWithContent:
    """C315 (2026-10-02): the payload check hid five of a row's check lists
    as reached, because the fixture's refused row carries none of them and
    its deployed row holds each EMPTY. Two (`issues`, `pending_convergence`)
    had never been drawn with content by any test. One row holding all five,
    through the receipt and v2's drawing of the result (the batch's card; today's renderer
    until P7-27)."""

    LISTS = {"issues": "ospf neighbours dropped from 6 to 5 on r3",
             "intent_unmet": "ospfv3 is declared by intent and was not up after",
             "unreadable": "bgp at its 180 s hold time could not be read",
             "pending_convergence": "rip has not converged yet (settle window 90 s)"}

    def test_each_list_reaches_the_screen(self):
        from modules.preview_confirm import operation_result
        from tests.payload_render import render_operation_result_v2

        verify = {"ok": False, "checked_protocols": ["bgp", "ospf", "ospfv3"],
                  "from_intent": ["ospfv3"], "declared_protocols": ["bgp", "ospf", "ospfv3"],
                  "pre": {"routing_protocols": {"bgp": 1, "ospf": 6}, "routes": 30,
                          "interfaces_up": 5},
                  "post": {"routing_protocols": {"bgp": 1, "ospf": 5}, "routes": 30,
                           "interfaces_up": 5},
                  **{k: [v] for k, v in self.LISTS.items() if k != "pending_convergence"}}
        rows = _rows([_sent(verify=verify,
                            pending_convergence=[self.LISTS["pending_convergence"]])])
        checks = rows[0]["checks"]
        assert all(checks[k] == [v] for k, v in self.LISTS.items()), checks
        assert checks["from_intent"] == ["ospfv3"]
        html = render_operation_result_v2(operation_result(rows, {"results": []},
                                                           {"ok": True, "path": "x"}, "deploy"))
        for k, v in self.LISTS.items():
            if k not in UNDRAWN_ON_V2:
                assert v in html, f"{k} was carried and not drawn"
        for k in UNDRAWN_ON_V2:
            assert self.LISTS[k] not in html, f"{k} is drawn now: leave UNDRAWN_ON_V2"


class TestTheRestorePathWritesThemToo:
    def test_run_targets_writes_receipts_after_its_commit(self):
        """Both apply paths, from the start (the operator: the receipt lands
        before the restore retrofit so both write it)."""
        import ast

        src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "routes", "deploy.py"), encoding="utf-8").read()
        fn = next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef) and n.name == "run_targets")
        body = ast.unparse(fn)
        assert "_write_receipts(" in body and "'restore'" in body
        assert body.index("_commit_batch_golden(") < body.index("_write_receipts(")


class TestTheReceiptsReadBack:
    """7.1 step 3: a deploy's receipt is read again LATER, on the device's v2 History tab
    (`history_sources.receipts`), on test_device_v2's lab. Today's device page's Changes tab
    read it through GET /deploy/receipts until both left at 7.8 (P7-22, 2026-10-17). That an
    unreadable store is said, and an absent one is not an error, is
    tests/test_device_history_v2.py's (an unreadable record, nothing recorded)."""

    def test_a_deploy_reads_back_as_that_devices_row(self, lab):  # noqa: F811
        from tests.test_device_v2 import _get, _text
        fp = command_fingerprint(PROGRAM, AUTHORISED)
        rows = _rows([_sent(), _sent(device="r9")], command_hashes={"r3": fp, "r9": fp})
        assert receipts.write("Lab", rows)["ok"]
        _r, html = _get(lab, "/v2/device/r3/history")
        text = _text(html)
        assert "Deployed: deployed" in text and "Matches what was confirmed yes" in text
        assert "shutdown: planned maintenance, port unused" in text
        devices = re.findall(r'<span class="hist-dev[^"]*">([^<]*)</span>', html)
        assert devices and "r9" not in devices, devices        # filtered to the device

    def test_a_secret_in_the_store_is_masked_on_the_way_out(self, lab):  # noqa: F811
        """A row written before masking, or by hand: the History tab is the second layer, as
        GET /deploy/receipts was (its `mask_payload`), so a planted community never leaves in
        the fields it draws: the reason, an authorised line and its reason, a removed line."""
        from tests.test_device_v2 import _get
        line = "snmp-server community PLANTEDREC99 RO"
        row = {"id": "p1", "device": "r3", "action": "deploy", "batch_id": "b1",
               "at": "2026-10-17T00:00:00Z", "actor": "a", "outcome": "failed",
               "reason": f"verify failed after {line}", "program_lines": 1,
               "program_hash": "x", "matches_confirmed": None, "program": [line],
               "authorised": [{"line": line, "reason": f"because {line}"}],
               "removals": [{"id": "u1", "chain": [], "line": line}],
               "checks": {"ran": False, "why": "planted"}, "rollback": {}}
        assert receipts.write("Lab", [row])["ok"]
        _r, html = _get(lab, "/v2/device/r3/history")
        assert "verify failed after snmp-server community" in html, "the row is drawn"
        assert "PLANTEDREC99" not in html
        assert "snmp-server community &lt;redacted:snmp_community&gt; RO" in html

    def test_needs_attention_s_recent_changes_mask_on_the_way_out_too(self, lab):  # noqa: F811
        """C1128 (found 2026-10-17 with P7-22): Needs attention's Recent changes drew the
        receipts' reasons as stored, with no second layer; a planted community never leaves."""
        from tests.test_device_v2 import _get
        line = "snmp-server community PLANTEDREC98 RO"
        row = {"id": "p2", "device": "r3", "action": "deploy", "batch_id": "b2",
               "at": "2026-10-17T00:00:00Z", "actor": "a", "outcome": "failed",
               "reason": f"verify failed after {line}", "program_lines": 1,
               "program_hash": "x", "matches_confirmed": None, "program": [line],
               "checks": {"ran": False, "why": "planted"}, "rollback": {}}
        assert receipts.write("Lab", [row])["ok"]
        _r, html = _get(lab, "/v2/?list=Lab")
        assert "verify failed after snmp-server community" in html, "the row is drawn"
        assert "PLANTEDREC98" not in html


class TestRecentChangesShowsTheDeployItMissed:
    """C1189 (the operator, W4, 2026-10-17): Recent changes on W4 walk read "No deploy or restore
    recorded" after two deploys to s5, while the list above it drew the failed deploy from the
    same receipts (W4's step 55 capture). Both read `receipts.read` of the page's network; the
    list re-fetches when a reader announces and Recent changes was drawn once, when the page
    opened, before the deploys. A page open before a deploy now redraws it when the deploy
    announces (`deploy_job`), and the redraw holds the receipt the deploy path wrote."""

    @staticmethod
    def _deploy():
        """The deploy path's own writers: the device's row as it finishes, commit pending,
        then its completion after the batch's commit (`routes.deploy`)."""
        from routes.deploy import _pending_receipts, _write_receipts
        hashes = {"r3": command_fingerprint(PROGRAM, AUTHORISED)}
        record, pending = _pending_receipts("Lab", "deploy", {}, hashes,
                                            actor="test-person@example.invalid",
                                            actor_kind="person")
        result = record(_sent())
        report = {"results": [result], "golden": {"commit": "abc123", "batch_id": "b-1",
                                                  "devices": ["r3"]}}
        assert _write_receipts("Lab", report, "deploy", {}, hashes,
                               actor="test-person@example.invalid", actor_kind="person",
                               pending=pending)["ok"]

    def test_a_page_open_before_a_deploy_redraws_recent_changes_when_it_announces(self, lab):  # noqa: F811
        from tests.test_device_v2 import _get, _text
        _r, html = _get(lab, "/v2/?list=Lab")
        assert "No deploy or restore recorded for Lab yet" in _text(html)
        card = re.search(r'<section\b[^>]*\bid="recent"[^>]*>', html)
        assert card, "Recent changes is a part the page can redraw"
        assert 'hx-trigger="nmas:deploy_job from:body"' in card.group(0), card.group(0)
        url = re.search(r'hx-get="([^"]+)"', card.group(0)).group(1).replace("&amp;", "&")
        self._deploy()
        _r, part = _get(lab, url)
        assert "Deploy r3 · deployed · 4 lines" in _text(part), _text(part)
        assert "by test-person@example.invalid" in _text(part)
        assert "No deploy or restore recorded" not in part

    def test_a_page_opened_after_the_deploy_draws_it(self, lab):  # noqa: F811
        """The control: the read itself was right (a fresh page draws the deploy path's
        receipt, as Needs attention's list did on W4)."""
        from tests.test_device_v2 import _get, _text
        self._deploy()
        _r, html = _get(lab, "/v2/?list=Lab")
        assert "Deploy r3 · deployed · 4 lines" in _text(html)


#: Words that send a person to a device's Changes tab, which no page has since today's device
#: page left at 7.8 (P7-22, 2026-10-17; v2 never had one, C908): the receipts are its History.
CHANGES_TAB = re.compile(r"device(?:'|\\')s (?:page, )?Changes\b|each device's Changes\b")


def _shipped_text_files():
    from tests.source_index import tracked
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return [p for p in tracked(*(os.path.join(root, d) for d in
                                 ("modules", "routes", "templates", "static/js")), root=root)
            if p.endswith((".py", ".html", ".js")) and "/vendor/" not in p]


#: Each sentence still naming one, by its file, with why it waits. Only shrinks, compared
#: exactly both ways.
STILL_NAMED = {
    # The batch Apply's "no record of that batch" notice: its template is compared with its
    # boards (docs/fidelity/apply.md, C650), so its words change with that record's next
    # comparison, not here.
    ("_apply_job.html", "each device's Changes"): "awaits docs/fidelity/apply.md's next compare",
}


class TestNothingSendsAPersonToAChangesTab:
    def test_no_shipped_text_names_one(self):
        files = _shipped_text_files()
        assert len(files) >= 400, len(files)            # 497 measured 2026-10-17
        named = {(os.path.basename(p), m.group(0)) for p in files
                 for m in CHANGES_TAB.finditer(open(p, encoding="utf-8").read())}
        assert named == set(STILL_NAMED), sorted(named ^ set(STILL_NAMED))

    def test_the_words_it_found_are_found(self):
        """The control: the three sentences it found on 2026-10-17, as they were written."""
        for old in ("Read the stated reasons on the device's Changes tab: a line",
                    " min</strong>. Each receipt is on its device\\'s page, Changes tab:",
                    "is in its receipts (each device's Changes) and in the golden history."):
            assert CHANGES_TAB.search(old), old
        assert not CHANGES_TAB.search("today's device page's Changes tab left at 7.8")
