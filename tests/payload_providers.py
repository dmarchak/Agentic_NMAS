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


def deploy_apply(mp):
    """A plan, then its apply, authorised: one deployed row and its report."""
    import routes.deploy as rd

    plan = deploy_plan(mp)
    device = plan["devices"][0]

    def _deploy_one(entry, list_name, device_rows, authorise=None, source_ref=""):
        from modules.nsot.deploy import DEPLOYED
        return {"device": entry["artifact"].device, "outcome": DEPLOYED,
                "verified": True}

    mp.setattr(rd, "_deploy_one", _deploy_one)
    mp.setattr(rd, "_commit_batch_golden", lambda *a, **k: {"commit": ""})
    return _ok(_client().post("/deploy/apply", json={
        "confirmations": {"s4": device["capture_hash"]},
        "command_hashes": {"s4": device["command_hash"]},
        "authorise": {"s4": list(device.get("dangerous") or [])},
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
