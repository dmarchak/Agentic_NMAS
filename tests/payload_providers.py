"""Real responses, one per declared renderer (Stage 7.0 (3)).

**Not a test module.** Each provider takes a `pytest.MonkeyPatch` and
returns what the route RETURNS, through the test client. Where the default
test store would return a thin payload that cannot carry the keys that
failed before (a fixture that cannot exhibit the case), the provider reuses
the fixture an existing test already built for that route:

* `/deploy/plan` and `/deploy/apply`: test_p3_wizard_draws_the_program's
  artifact and intent, with the real merge, dangerous-line and attribution
  code, so `commands`, `dangerous` and `attribution` are present;
* `/golden/restore/preview`: test_p3_restore_is_guarded's two targets, one
  deployable and one blocked, so `commands` is present (C27);
* `/onboard/pending`: a ztp row and a static row, so the list echo and the
  per-row progress are present.
"""


def _client():
    import app as A

    return A.app.test_client()


def _ok(r):
    """A refusal is a broken fixture, never a payload (see _answer in the
    test module)."""
    assert 200 <= r.status_code < 300, (r.status_code, r.get_json(silent=True))
    return r.get_json()


def deploy_plan(mp):
    import routes.deploy as rd
    from modules.nsot.render_artifact import build_artifact
    from tests import test_p3_wizard_draws_the_program as w

    def _fake(list_name, hostname, cache=None):
        artifact = build_artifact(hostname, w.CAPTURE, "cisco_ios", template_approved=True)
        return (artifact, w.CAPTURE, {"hostname": hostname, "ip": "203.0.113.24"}), ""

    mp.setattr(rd, "_artifact_for", _fake)
    mp.setattr("modules.nsot.deploy.prepare_device", lambda a: {"config": w.INTENT})
    mp.setattr(rd, "_attribute_additions", lambda *a, **k: dict(w.ATTRIBUTION))
    return _ok(_client().post("/deploy/plan", json={"devices": ["s4"]}))


def deploy_plan_with_residue(mp):
    """The same device, carrying a stanza its intent does not have: merge-only
    will NOT remove it, so the plan's `what_not` holds a real residue item.
    The provider above has none, which is right for the "nothing is left out"
    sentence and left the items' fields unexamined (EMPTY_IN_FIXTURE)."""
    import routes.deploy as rd
    from modules.nsot.render_artifact import build_artifact
    from tests import test_p3_wizard_draws_the_program as w

    capture = w.CAPTURE.replace("end\n", "interface GigabitEthernet0/3\n"
                                          " description retired uplink\nend\n")
    assert capture != w.CAPTURE

    def _fake(list_name, hostname, cache=None):
        artifact = build_artifact(hostname, capture, "cisco_ios", template_approved=True)
        return (artifact, capture, {"hostname": hostname, "ip": "203.0.113.24"}), ""

    mp.setattr(rd, "_artifact_for", _fake)
    mp.setattr("modules.nsot.deploy.prepare_device", lambda a: {"config": w.INTENT})
    mp.setattr(rd, "_attribute_additions", lambda *a, **k: dict(w.ATTRIBUTION))
    return _ok(_client().post("/deploy/plan", json={"devices": ["s4"]}))


def deploy_apply(mp):
    """A plan, then its apply, authorised: one deployed row and its report.

    The plan carries the authorisation, as the wizard's re-plan does. Until
    2026-09-27 this planned WITHOUT it and applied WITH it, so the hashes
    differed and the "deployed row" was a refusal: the payload check had only
    ever examined a refusal's keys, never a deployed row's (a fixture that
    could not exhibit the case, inside the checker)."""
    import routes.deploy as rd

    deploy_plan(mp)          # installs the artifact stubs
    plan = _ok(_client().post("/deploy/plan", json={
        "devices": ["s4"], "authorise": {"s4": ["shutdown"]}}))
    device = plan["devices"][0]
    assert device["authorisation_ok"] is True, device

    def _deploy_one(entry, list_name, device_rows, authorise=None, source_ref=""):
        """Shaped as the REAL `_deploy_one` returns a pushed, verified device
        (the first version invented a `verified` key it never returns)."""
        from modules.nsot.deploy import DEPLOYED
        return {"device": entry["artifact"].device, "outcome": DEPLOYED, "stage": "",
                "reason": "", "commands": device["commands"], "authorised": ["shutdown"],
                "program_hash": device["command_hash"], "rolled_back": False,
                "pending_convergence": [], "golden_commit": "",
                "verify": {"ok": True, "issues": [], "checked_protocols": ["ospf"],
                           "pre": {"routing_protocol": "ospf", "routing_neighbors": 5,
                                   "routing_protocols": {"ospf": 5}, "routes": 13,
                                   "interfaces_up": 7},
                           "post": {"routing_protocol": "ospf", "routing_neighbors": 5,
                                    "routing_protocols": {"ospf": 5}, "routes": 13,
                                    "interfaces_up": 7}}}

    mp.setattr(rd, "_deploy_one", _deploy_one)
    mp.setattr(rd, "_commit_batch_golden", lambda *a, **k: {"commit": ""})
    # s4 deploys; s3 is refused because the program moved since it was
    # confirmed, so the payload carries BOTH a deployed row and a refusal's
    # operands, and the check can examine each.
    return _ok(_client().post("/deploy/apply", json={
        "confirmations": {"s4": device["capture_hash"], "s3": device["capture_hash"]},
        "command_hashes": {"s4": device["command_hash"], "s3": "0000000000000000"},
        "authorise": {"s4": ["shutdown"], "s3": ["shutdown"]},
    }))


def restore_preview(mp):
    from tests.test_p3_restore_is_guarded import _real_payload

    return _real_payload(mp)


def onboard_pending(mp, tmp_path):
    from tests.test_ztp_onboarding import ENTRY

    mp.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / name))
    mp.setattr("modules.config.LISTS_DIR", str(tmp_path))
    (tmp_path / "probe").mkdir(exist_ok=True)
    rows = [dict(ENTRY, age_seconds=10, state="in_flight", onboarded_at="x",
                 credential_findable=True),
            {"name": "r7", "address_source": "static", "mgmt_ip": "192.0.2.7",
             "age_seconds": 90000, "state": "overdue", "onboarded_at": "x",
             "credential_findable": True}]
    mp.setattr("modules.nsot.manifest.pending_devices", lambda repo: rows)
    mp.setattr("modules.nsot.ztp.progress",
               lambda row: {"stage": "reserved_not_leased", "summary": "reserved"})
    return _ok(_client().get("/onboard/pending?list_name=probe"))
