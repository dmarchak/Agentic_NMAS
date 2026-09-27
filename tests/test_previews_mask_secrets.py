"""C77: the deploy and restore previews mask secrets on the way out.

Both POSTs returned stored and rendered config lines verbatim: the program,
residue, and what a line replaces. Measured 2026-09-27 with a planted value
in each position. A community the program ADDS and one left as residue both
came back in `/deploy/plan` and in `/golden/restore/preview`. B11's sweep
planted every store and swept GETs, so a POST preview was outside its
population: defined by the method, where the property is "returns stored
config" (B16's lesson).

The mask is applied AFTER every hash is computed from the truthful program,
so the confirm is still bound to what is sent. The seam test drives a masked
plan into the apply and shows the hash it carries is accepted.
"""

import json

import pytest

ADDED = "ADDEDPLANT77"
RESIDUE = "RESIDUEPLANT77"


def _deploy_plan(monkeypatch):
    import routes.deploy as rd
    from modules.nsot.render_artifact import build_artifact
    from tests import payload_providers as P
    from tests import test_p3_wizard_draws_the_program as w

    capture = w.CAPTURE.replace("end\n", f"snmp-server community {RESIDUE} RO\nend\n")
    assert capture != w.CAPTURE
    intent = w.INTENT + f"snmp-server community {ADDED} RO\n"

    def _fake(list_name, hostname, cache=None):
        a = build_artifact(hostname, capture, "cisco_ios", template_approved=True)
        return (a, capture, {"hostname": hostname, "ip": "203.0.113.24"}), ""
    monkeypatch.setattr(rd, "_artifact_for", _fake)
    monkeypatch.setattr("modules.nsot.deploy.prepare_device", lambda a: {"config": intent})
    monkeypatch.setattr(rd, "_attribute_additions", lambda *a, **k: dict(w.ATTRIBUTION))
    # The fixture's program shuts an interface: authorised, so the only
    # refusal left open to the apply below is the command hash.
    plan = P._ok(P._client().post("/deploy/plan", json={
        "devices": ["s4"], "authorise": {"s4": ["shutdown"]}}))
    return plan, intent, capture


def _restore_preview(monkeypatch):
    from tests.test_p3_restore_is_guarded import _preview_for, _target

    target = f"hostname r1\nsnmp-server community {ADDED} RO\n"
    captured = f"hostname r1\nsnmp-server community {RESIDUE} RO\n"
    return _preview_for(monkeypatch, [_target("r1", target_config=target,
                                              captured=captured)]), target, captured


class TestNoPreviewCarriesASecret:
    @pytest.mark.parametrize("make", [_deploy_plan, _restore_preview],
                             ids=["deploy plan", "restore preview"])
    def test_neither_planted_value_comes_back(self, monkeypatch, make):
        payload, _intended, _captured = make(monkeypatch)
        text = json.dumps(payload)
        assert ADDED not in text and RESIDUE not in text

    @pytest.mark.parametrize("make", [_deploy_plan, _restore_preview],
                             ids=["deploy plan", "restore preview"])
    def test_the_line_is_still_drawn_with_its_slot_masked(self, monkeypatch, make):
        """Floor: the lines were reached. Masking a payload that never held
        them would pass the test above too."""
        payload, _i, _c = make(monkeypatch)
        text = json.dumps(payload)
        assert "snmp-server community <redacted" in text


class TestTheHashIsStillOfWhatIsSent:
    def test_the_deploy_command_hash_is_of_the_truthful_program(self, monkeypatch):
        from modules.nsot.deploy import command_fingerprint, merge_commands

        plan, intent, capture = _deploy_plan(monkeypatch)
        device = plan["devices"][0]
        truthful = merge_commands(intent, capture)
        assert any(ADDED in line for line in truthful), "the program adds the secret"
        assert device["command_hash"] == command_fingerprint(truthful, ["shutdown"])

    def test_the_restore_command_hash_is_of_the_truthful_program(self, monkeypatch):
        from modules.nsot.deploy import command_fingerprint, merge_commands

        payload, target, captured = _restore_preview(monkeypatch)
        device = payload["devices"][0]
        truthful = merge_commands(target, captured)
        assert any(ADDED in line for line in truthful)
        assert device["command_hash"] == command_fingerprint(truthful, [])

    def test_a_masked_plan_driven_into_the_apply_is_not_refused(self, monkeypatch):
        """The seam: the apply recomputes the program from the truthful render
        and compares it with the hash the MASKED plan carried."""
        from tests import payload_providers as P

        plan, _intent, _capture = _deploy_plan(monkeypatch)
        device = plan["devices"][0]
        body = P._client().post("/deploy/apply", json={
            "confirmations": {"s4": device["capture_hash"]},
            "command_hashes": {"s4": device["command_hash"]},
            "authorise": {"s4": ["shutdown"]}}).get_json()
        refused = [r for r in body.get("results") or []
                   if r.get("device") == "s4" and r.get("outcome") == "refused"]
        assert refused == [], refused
        assert "s4" not in (body.get("by_outcome") or {}).get("refused", [])

    def test_a_wrong_command_hash_is_refused(self, monkeypatch):
        """Control for the one above: the recompute does compare."""
        from tests import payload_providers as P

        plan, _intent, _capture = _deploy_plan(monkeypatch)
        device = plan["devices"][0]
        body = P._client().post("/deploy/apply", json={
            "confirmations": {"s4": device["capture_hash"]},
            "command_hashes": {"s4": "0" * 16},
            "authorise": {"s4": ["shutdown"]}}).get_json()
        assert "s4" in (body.get("by_outcome") or {}).get("refused", []), body.get("by_outcome")


class TestTheApplyResponsesAreMaskedToo:
    """C77's apply side, found tracing where C70's observation (b) is read:
    `/deploy/apply` returned the planted community in `results[].commands`.
    The restore apply returns through the same `run_targets`."""

    def test_the_deploy_apply_response_carries_no_planted_value(self, monkeypatch):
        from tests import payload_providers as P

        plan, _intent, _capture = _deploy_plan(monkeypatch)
        device = plan["devices"][0]
        body = P._client().post("/deploy/apply", json={
            "confirmations": {"s4": device["capture_hash"]},
            "command_hashes": {"s4": device["command_hash"]},
            "authorise": {"s4": ["shutdown"]}}).get_json()
        rows = [r for r in body.get("results") or [] if r.get("device") == "s4"]
        # Floor: the row that carried it is there, with its program drawn.
        assert rows and any("snmp-server community <redacted" in c
                            for c in rows[0].get("commands") or []), rows
        assert ADDED not in json.dumps(body)

    def test_the_restore_apply_masks_its_response(self):
        """The same one line, pinned at the route (it shares `run_targets`)."""
        import inspect

        import routes.golden as golden

        src = inspect.getsource(golden.restore_apply)
        assert "mask_payload(" in src and src.count("jsonify(") >= 1
