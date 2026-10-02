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
        plan = P._client().post("/deploy/plan", json={
            "devices": ["s4"], "authorise": {"s4": [{"line": "shutdown", "reason": "planned maintenance, port unused"}]}}).get_json()
        device = plan["devices"][0]
        assert device["authorisation_ok"] is True
        mp.setattr(rd, "_deploy_one", deploy_one)
        if commit is not None:
            mp.setattr(rd, "_commit_batch_golden", commit)
        return plan, P._client().post("/deploy/apply", json={
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
    """The shipped renderer, executed against the real /deploy/apply payload
    (a deployed row and a refusal, from `payload_providers.deploy_apply`)."""

    def _render(self, monkeypatch):
        """7.1 step 2: the result is the component's, built from the receipt
        rows the apply wrote."""
        from tests import payload_providers as P
        from tests.payload_render import render_result

        report = P.deploy_apply(monkeypatch)
        return report, render_result(report["result"], {"repreview": "openDeployPlan"})

    def test_each_row_names_its_checks_and_the_receipt_is_reported(self, monkeypatch):
        report, html = self._render(monkeypatch)
        assert {r["device"]: r["outcome"] for r in report["results"]} == \
            {"s3": "refused", "s4": "deployed"}, "the fixture must exhibit both"
        s4 = html[html.index('data-pr-target="s4"'):]
        s3 = html[html.index('data-pr-target="s3"'):html.index('data-pr-target="s4"')]
        assert 'data-pr-checked="' in s4 and "ospf" in s4.split("data-pr-checked=")[1][:80]
        assert "Nothing was checked: refused before anything was sent" in s3
        assert 'data-pr-receipt="ok"' in html and "2 row(s) written" in html
        s4_hash = next(r for r in report["results"] if r["device"] == "s4")["program_hash"]
        assert "line(s) sent, program" in s4 and s4_hash[:12] in s4
        assert "matches the program you confirmed" in s4


class TestEveryCheckListIsDrawnWithContent:
    """C315 (2026-10-02): the payload check hid five of a row's check lists
    as reached, because the fixture's refused row carries none of them and
    its deployed row holds each EMPTY. Two (`issues`, `pending_convergence`)
    had never been drawn with content by any test. One row holding all five,
    through the receipt and the SHIPPED renderer."""

    LISTS = {"issues": "ospf neighbours dropped from 6 to 5 on r3",
             "intent_unmet": "ospfv3 is declared by intent and was not up after",
             "unreadable": "bgp at its 180 s hold time could not be read",
             "pending_convergence": "rip has not converged yet (settle window 90 s)"}

    def test_each_list_reaches_the_screen(self):
        from modules.preview_confirm import operation_result
        from tests.payload_render import render_result

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
        html = render_result(operation_result(rows, {"results": []}, {"ok": True, "path": "x"},
                                              "deploy"))
        for k, v in self.LISTS.items():
            assert v in html, f"{k} was carried and not drawn"
        assert "data-pr-from-intent" in html and "not running before: ospfv3" in html


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
    """7.1 step 3: the result can be read again LATER, from the receipt
    store, drawn by the same component as at apply. None of the 41 gated
    actions had that (the result survey, 2026-09-27)."""

    def _draw(self, payload):
        import json as _json

        import dukpy

        from tests.payload_render import shipped

        component = shipped("nmas_preview_confirm.js")
        page = shipped("partials__device_changes.1.js")
        return dukpy.evaljs(
            "var window = {}; var document = {addEventListener: function () {}};\n"
            + component + "\nvar previewConfirmResultHtml = window.previewConfirmResultHtml;\n"
            + page + f"\ndeviceChangesHtml({_json.dumps(payload)})")

    def test_a_deploy_reads_back_as_that_devices_row(self, monkeypatch):
        from tests import payload_providers as P

        P.deploy_apply(monkeypatch)
        d = P._ok(P._client().get("/deploy/receipts?device=s4"))
        assert d["state"] == "ok" and len(d["changes"]) == 1
        result = d["changes"][0]["result"]
        # One device's row: never "every device in the batch appears here".
        assert result["happened"]["summary"].startswith("s4: done. One row of batch")
        assert "every device in the batch" not in result["happened"]["summary"]
        assert result["record"]["statement"].startswith("Read back from the receipt recorded")
        html = self._draw(d)
        assert 'data-pr-target="s4"' in html and "matches the program you confirmed" in html
        assert "s3" not in html.split("data-pr-result")[1], "filtered to the device"

    def test_a_secret_in_the_store_is_masked_on_the_way_out(self, monkeypatch, tmp_path):
        """A row written before masking, or by hand: the reader is the second
        layer, so a planted community never leaves."""
        import json as _json

        from modules.nsot import receipts
        from tests import payload_providers as P

        path = tmp_path / "planted.jsonl"
        monkeypatch.setattr(receipts, "path_for", lambda list_name: str(path))
        row = {"device": "s4", "action": "deploy", "batch_id": "b1", "at": "t", "actor": "a",
               "outcome": "deployed", "sent": True, "program_hash": "x", "matches_confirmed": None,
               "program": ["snmp-server community PLANTEDREC99 RO"],
               "checks": {"ran": False, "why": "planted"}, "rollback": {}}
        path.write_text(_json.dumps(row) + "\n", encoding="utf-8")
        body = P._client().get("/deploy/receipts?device=s4").get_data(as_text=True)
        assert "PLANTEDREC99" not in body and "snmp-server community <redacted" in body

    def test_absent_and_unreadable_are_different_sentences(self, monkeypatch, tmp_path):
        from modules.nsot import receipts
        from tests import payload_providers as P

        path = tmp_path / "r.jsonl"
        monkeypatch.setattr(receipts, "path_for", lambda list_name: str(path))
        absent = P._client().get("/deploy/receipts?device=s4").get_json()
        assert absent["ok"] is True and absent["state"] == "absent"
        assert 'data-changes-state="none"' in self._draw(absent)
        path.write_text("{not json\n", encoding="utf-8")
        resp = P._client().get("/deploy/receipts?device=s4")
        bad = resp.get_json()
        assert resp.status_code == 500 and bad["ok"] is False and bad["state"] == "unreadable"
        html = self._draw(bad)
        assert 'data-changes-state="unreadable"' in html and "not the same as no change" in html
