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
        "devices": ["s4"], "authorise": {"s4": [{"line": "shutdown", "reason": "planned maintenance, port unused"}]}}))
    device = plan["devices"][0]
    assert device["authorisation_ok"] is True, device

    def _deploy_one(entry, list_name, device_rows, authorise=None, source_ref=""):
        """Shaped as the REAL `_deploy_one` returns a pushed, verified device
        (the first version invented a `verified` key it never returns)."""
        from modules.nsot.deploy import DEPLOYED
        return {"device": entry["artifact"].device, "outcome": DEPLOYED, "stage": "",
                "reason": "", "commands": device["commands"], "authorised": [{"line": "shutdown", "reason": "planned maintenance, port unused"}],
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
    # A golden commit with its tags, so the result's record part is reached
    # (the fixture used to return an empty commit, and `record.tags` could
    # never be examined).
    mp.setattr(rd, "_commit_batch_golden", lambda *a, **k: {
        "ok": True, "commit": "0123456789abcdef0123", "devices": ["s4"],
        "tags": ["golden/s4/20260927T000000Z"], "baseline": False,
        "baseline_reasons": ["the batch targeted 1 of 9 inventory devices"]})
    # s4 deploys; s3 is refused because the program moved since it was
    # confirmed, so the payload carries BOTH a deployed row and a refusal's
    # operands, and the check can examine each.
    return _ok(_client().post("/deploy/apply", json={
        "confirmations": {"s4": device["capture_hash"], "s3": device["capture_hash"]},
        "command_hashes": {"s4": device["command_hash"], "s3": "0000000000000000"},
        "authorise": {"s4": [{"line": "shutdown", "reason": "planned maintenance, port unused"}], "s3": [{"line": "shutdown", "reason": "planned maintenance, port unused"}]},
    }))


def restore_preview(mp):
    """test_p3_restore_is_guarded's targets, with r1's ref also holding an SNMP
    community the device lacks: C79's case, authorised by its masked line with
    a reason, so `secret_readded` and the program's `secret` are REACHED."""
    from tests.test_p3_restore_is_guarded import TARGET, _preview_for, _target

    return _preview_for(
        mp, [_target("r1", target_config=TARGET + "snmp-server community RESTORECOMM1 RO\n"),
             _target("r2", target_config="")],
        [{"hostname": "r9", "reason": "stale"}],
        {"ref": "HEAD", "devices": ["r1", "r2"], "authorise": {"r1": [
            {"line": "shutdown", "reason": "new interface, left down for now"},
            {"line": "snmp-server community <redacted:snmp_community> RO",
             "reason": "restoring the pre-rotation community on purpose"}]}})


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
    # 7.1: runs in the REAL record, through the real recorder, so a pending
    # row carries its last run and the finished list is not empty: r7 did
    # not answer (still pending), r9 was onboarded and r8 abandoned (both
    # off the list, so read back only under "finished").
    from modules.nsot.onboard import PHASE_TWO_STEPS, record_run

    repo = str(tmp_path / "probe" / "config_repo")
    record_run(repo, "verify", "probe", "r7", "p@example.com", {
        "ok": False, "reason": "did not answer", "mgmt_ip": "192.0.2.7",
        "steps": [{"step": "verify", "ok": False, "detail": "did_not_answer"}]
        + [{"step": st, "ok": False, "detail": "did not run"} for st in PHASE_TWO_STEPS[1:]],
        "verify": {"state": "did_not_answer", "error": "tcp/22 refused",
                   "credential_source": "override",
                   "causes": [{"cause": "the device has not booted", "why": "nothing answers",
                               "where": "console", "command": "show version"}],
                   "recovery": {"available": False, "note": "no recovery is needed"}}})
    record_run(repo, "verify", "probe", "r9", "p@example.com", {
        "ok": True, "reason": "", "mgmt_ip": "192.0.2.9", "promoted": True,
        "golden": {"ok": True, "commit": "0123456789abcdef"},
        "steps": [{"step": st, "ok": True, "detail": ""} for st in PHASE_TWO_STEPS],
        "verify": {"state": "answered", "credential_source": "override"}})
    record_run(repo, "abandon", "probe", "r8", "p@example.com", {
        "ok": True, "released": "r8", "remaining": [],
        "steps": [{"step": "intent", "ok": True, "detail": "removed host_vars/r8.yml"},
                  {"step": "identity", "ok": True, "detail": "released 'r8'"}]})
    return _ok(_client().get("/onboard/pending?list_name=probe"))


def deploy_receipts(mp):
    """The receipt store read back (7.1 step 3): a real apply writes the
    receipts (into this test's own file, conftest), then the reader answers
    for s4. The deployed row, not a hand-built one."""
    deploy_apply(mp)
    # Unfiltered, so the batch carries the refused s3 as well as the deployed
    # s4 and "what did not happen" has an item to examine. The Device page
    # filters by device; the filtered summary is tested in test_deploy_receipts.
    return _ok(_client().get("/deploy/receipts"))


def netbox_status(mp, tmp):
    """The NetBox tab's read, with a stored PARTIAL import (C85): one device
    fully written, one with a write that did not land, one not imported."""
    import json

    from modules import netbox_client as nb

    path = tmp / "netbox_sync_status.json"
    path.write_text(json.dumps({"last_sync": "2026-09-27 12:00:00", "lists": {"Default": {
        "ok": True, "list": "Default", "region": "rcn", "site": "lab", "total": 3, "synced": 2,
        "created": 1, "updated": 1,
        "failed": [{"hostname": "s9", "error": "400 bad request"}],
        "write_failures": [{"device": "r2", "write": "cable Gi2 -> s4:Gi1/0", "error": "400"}],
        "partial": ["r2"], "complete": False, "config_template_id": 7,
        "ipam": {"interfaces": 12, "prefixes": 4, "ips": 9, "vrfs": 1, "vlans": 2,
                 "cables": 3, "tunnels": 0},
        "notes": ["site adopted, not re-parented"], "timestamp": "2026-09-27 12:00:00",
        "netbox_url": "https://netbox.example.invalid/dcim/sites/1/",
        "ipam_url": "https://netbox.example.invalid/ipam/prefixes/"}}}), encoding="utf-8")
    mp.setattr(nb, "_SYNC_STATUS_FILE", str(path))
    return _client().get("/netbox/status").get_json()


def capture_preview(mp, tmp):
    """7.1 step 4: r2's real config with the host's exact break, so the
    preview carries a golden diff AND a departure from committed intent."""
    from tests.test_capture import build_capture_lab
    from tests.test_intent_match import _broken

    lab = build_capture_lab(mp, tmp)
    lab["running"]["r2"] = _broken(lab["captured"])
    return _ok(lab["client"].post("/golden/capture/preview", json={"devices": ["r2"]}))


def golden_panel(mp, tmp, path):
    """The golden panel's reads against a repository with baselines in every
    state and a legacy store holding a retired device and an unknown one."""
    from tests.test_golden_panel_says_what_to_do import build_golden_panel_lab

    lab = build_golden_panel_lab(mp, tmp)
    return _ok(lab["client"].get(path))


def seed_preview(mp, tmp):
    """C148: r2's real golden with only onboarding's bootstrap committed as
    its intent, so the preview carries a whole document against it, and one
    line the parser does not model, so what the template misses is carried."""
    from tests.test_seed_intent import LIST, UNMODELLED, build_seed_lab

    lab = build_seed_lab(mp, tmp, unmodelled=UNMODELLED)
    return _ok(lab["client"].post("/templatize/seed/preview",
                                  json={"list_name": LIST, "devices": ["r2"]}))


def seed_apply(mp, tmp):
    """The same, confirmed and committed: a seed's result, partial."""
    from tests.test_seed_intent import LIST, UNMODELLED, build_seed_lab

    lab = build_seed_lab(mp, tmp, unmodelled=UNMODELLED)
    d = _ok(lab["client"].post("/templatize/seed/preview",
                               json={"list_name": LIST, "devices": ["r2"]}))
    h = d["preview"]["what"]["targets"][0]["select_data"]["hash"]
    return _ok(lab["client"].post("/templatize/seed/apply",
                                  json={"list_name": LIST, "confirmations": {"r2": h}}))


def restore_points(mp, tmp):
    """7.1 step 5 (C80): r2's restore points, from a real repository holding
    its onboarding golden, its own golden tag and a baseline earned by a
    whole-fleet capture at intent. Not a hand-built list."""
    from tests.test_capture import build_capture_lab

    lab = build_capture_lab(mp, tmp)
    d = _ok(lab["client"].post("/golden/capture/preview", json={"devices": []}))
    h = d["preview"]["what"]["targets"][0]["select_data"]["hash"]
    _ok(lab["client"].post("/golden/capture/apply",
                           json={"confirmations": {"r2": h}, "fleet": True}))
    return _ok(lab["client"].get("/golden/restore_points/r2"))


def capture_apply(mp, tmp):
    """The same, confirmed and recorded: a departing capture's result."""
    from tests.test_capture import build_capture_lab
    from tests.test_intent_match import _broken

    lab = build_capture_lab(mp, tmp)
    lab["running"]["r2"] = _broken(lab["captured"])
    d = _ok(lab["client"].post("/golden/capture/preview", json={"devices": ["r2"]}))
    h = d["preview"]["what"]["targets"][0]["select_data"]["hash"]
    # Two handed-off drift items (C105): r2's is closed by the capture, and
    # one for a device this capture does not record stays pending, so both
    # lists carry something real.
    from modules import approval_queue
    ids = [approval_queue.add_approval("update_golden_config", f"drift on {h_}",
                                       ip_, h_, "", {}, "fixture")
           for h_, ip_ in (("r2", "203.0.113.12"), ("s9", "203.0.113.19"))]
    ids = [i["id"] if isinstance(i, dict) else i for i in ids]
    return _ok(lab["client"].post("/golden/capture/apply", json={
        "confirmations": {"r2": h}, "approvals": {"r2": [ids[0]], "s9": [ids[1]]}}))


def _netbox_behind(mp):
    """A FakeNetBox behind a URL nothing answers, configured, with the
    managed-tag cache cleared (it is keyed on the base URL)."""
    from tests.fake_netbox import FakeNetBox
    import modules.netbox_client as nbc

    nb = FakeNetBox()
    mp.setattr(nbc, "get_netbox_config", lambda: {"url": "http://127.0.0.1:9", "token": "t"})
    mp.setattr(nbc, "_session_from_config", lambda cfg: nb)
    mp.setattr(nbc, "_managed_tag_ids", {})
    return nb


def _import_dry_run(nb, hosts):
    """The REAL dry run of the device upsert (the import's own code), for r1
    already in NetBox (an update) and r2 new (creates)."""
    from modules import netbox_guard
    from modules.netbox_client import _upsert_device

    site = nb.seed("dcim/sites", {"name": "Lab", "slug": "lab"})
    role = nb.seed("dcim/device-roles", {"name": "Router", "slug": "router"})
    nb.seed("dcim/devices", {"name": "r1", "serial": "SER0001", "site": {"id": site["id"]}})
    with netbox_guard.dry_run() as plan, netbox_guard.for_list("Default"):
        for i, host in enumerate(hosts, start=1):
            _upsert_device(nb, "http://127.0.0.1:9", hostname=host, ip=f"203.0.113.{i}",
                           facts={"manufacturer": "Cisco", "model": "C8000v",
                                  "platform": "IOS-XE", "serial": f"SER{i:04d}",
                                  "sw_version": "17.6"},
                           interfaces=[{"name": f"GigabitEthernet{i}", "ip": f"203.0.113.{i}",
                                        "prefix_len": 24, "enabled": True}],
                           site_id=site["id"], role_id=role["id"], ipam_stats={})
    return {"ok": True, "plan": plan.summary()}


def netbox_import_preview(mp, tmp):
    """7.1: the import preview on the component. The list's devices and the
    sync are stood in for by the real device upsert run dry, so the plan
    carries a real update (r1, already in NetBox) and real creates (r2)."""
    import modules.netbox_client as nbc
    import routes.netbox_safety as ns

    nb = _netbox_behind(mp)
    devices = [{"hostname": "r1", "ip": "203.0.113.1"}, {"hostname": "r2", "ip": "203.0.113.2"}]
    mp.setattr(ns, "_load_list_devices", lambda name: ("Default", devices))
    mp.setattr(nbc, "sync_list_to_netbox",
               lambda name, devs, dry_run=False, **k: _import_dry_run(nb, ["r1", "r2"]))
    return _ok(_client().post("/netbox/safety/import/preview", json={"list_name": "Default"}))


def netbox_import_all_preview(mp, tmp):
    import modules.netbox_client as nbc
    import routes.netbox_safety as ns

    nb = _netbox_behind(mp)
    mp.setattr(ns, "_all_lists_with_devices",
               lambda: [("Default", [{"hostname": "r1"}, {"hostname": "r2"}])])
    mp.setattr(nbc, "sync_all_lists_to_netbox",
               lambda items, dry_run=False, **k: _import_dry_run(nb, ["r1", "r2"]))
    return _ok(_client().post("/netbox/safety/import_all/preview", json={}))


def netbox_remove_preview(mp, tmp):
    """7.1: the removal preview on the component, through the REAL removal
    dry run and cascade query. NMAS created and tagged a device; the
    database would take its interface and that interface's address with it,
    neither of which NMAS created (the 2026-09-24 incident's shape); and a
    site NMAS recorded carries no tag, so it is left alone."""
    from modules import netbox_guard

    nb = _netbox_behind(mp)
    tag = [{"slug": netbox_guard.MANAGED_TAG_SLUG, "name": netbox_guard.MANAGED_TAG}]
    dev = nb.seed("dcim/devices", {"name": "r6", "tags": tag})
    site = nb.seed("dcim/sites", {"name": "branch", "slug": "branch", "tags": []})
    iface = nb.seed("dcim/interfaces", {"name": "Gi2", "device": {"id": dev["id"]}})
    nb.seed("ipam/ip-addresses", {"address": "10.0.0.15/24",
                                  "assigned_object_type": "dcim.interface",
                                  "assigned_object_id": iface["id"]})
    netbox_guard.record_created("Default", "dcim/devices", dev["id"], "r6")
    netbox_guard.record_created("Default", "dcim/sites", site["id"], "branch")
    try:
        return _ok(_client().post("/netbox/safety/remove/preview",
                                  json={"list_name": "Default"}))
    finally:
        netbox_guard.forget_created("Default")


def integration_status(mp, tmp):
    """7.2: the integration-health reader stores a value (the real reader,
    the real registry, nothing configured in the test store), then the REAL
    route serves it."""
    from modules import config, reader_job
    from modules.readers import integration_health

    mp.setattr(config, "DATA_DIR", str(tmp))
    reader_job.run_once(integration_health.READER)
    return _client().get("/settings/integrations/status")


def needs_attention(mp, tmp):
    """7.2: the landing list through the REAL route, from job health over
    the systemd and journal shapes measured on the host: a failing job, a
    rotation row naming its device, and a source that could not be read."""
    from modules import attention as A
    from modules import job_health as J
    from modules.nsot import credential_rotation as cr
    from tests.test_job_health import LOADED, NOW, _fail, _runner
    from tests.test_job_health import _ok as _succeeded

    journal = "\n".join([_succeeded(NOW - 3600), _fail(NOW - 60)])
    rot = J.rotation_rows([{"device": "r2", "state": cr.ROTATED_UNVERIFIED,
                            "failed_stage": "device_startup_config",
                            "at": "2026-09-28T10:00:00Z"}], known=({"r2"}, ""))

    def health():
        return J.health(NOW, _runner(LOADED, journal), images=[], settings=[],
                        rotations=rot, owner=[], ztp=[], responder=[], startup=[],
                        sessions=[], version=[])

    def unreadable():
        raise OSError("the store could not be opened")

    _drift_run(mp, tmp)
    from modules.config import get_current_list_name
    lst = get_current_list_name()

    def item(host):
        return {"id": f"q-{host}", "status": "pending", "action_type": "update_golden_config",
                "device_hostname": host, "description": f"Config drift detected on {host}",
                "context": "Detected by scheduled drift check", "created_ts": NOW - 50}

    # r2's drift item FOLDS into its drift row; r9's has no drift row and
    # stands alone saying so.
    queue = lambda: ([item("r2"), item("r9")], None)                 # noqa: E731
    pending = lambda: [{"identity": "uid:bp-a", "name": "bp-a", "state": "overdue",  # noqa: E731
                        "onboarded_at": "2026-09-27T10:00:00Z", "age_seconds": 30 * 3600,
                        "address_source": "static", "credential_findable": True}]
    assert lst                                   # the rows are keyed on the active list
    mp.setattr(A, "SOURCES", (lambda: A.job_health_source(health), A.drift_source,
                              lambda: A.approvals_source(queue),
                              lambda: A.pending_onboarding_source(pending),
                              lambda: A.rollback_source(lambda: {
                                  "applies": {"r5": {"at": "2026-09-28T09:00:00Z",
                                                     "reason": "verify failed",
                                                     "commands": [" shutdown"],
                                                     "intent_commit": "abc1234def",
                                                     "applicability": "blocking"}},
                                  "stale": {}, "unreadable": ""}),
                              lambda: A.deploy_source(lambda: {"state": "ok", "rows": [
                                  {"device": "r6", "outcome": "failed", "sent": True,
                                   "at": "2026-09-28T11:00:00Z", "action": "deploy",
                                   "stage": "verify", "reason": "verify failed",
                                   "program_lines": 3, "matches_confirmed": True,
                                   "actor": "ops@example.com",
                                   "checks": {"ran": True, "ok": False,
                                              "issues": ["ospf: 1 -> 0 neighbours"]},
                                   "rollback": {"performed": True, "state": "restored"}}]}),
                              lambda: A.baseline_source(lambda: (
                                  "0123456789abcdef\x1f1790600000\x1fgolden: 9 device(s) via "
                                  "save_all\n\nSource: save_all\nBaseline: denied: r2 does not "
                                  "match its committed intent (+1 -1)\n")),
                              lambda: A.authorisation_source(lambda: {"state": "ok", "error": "",
                                  "devices": {"s4": {" shutdown": {
                                      "count": 3, "first_at": "2026-09-20T10:00:00Z",
                                      "last_at": "2026-09-25T10:00:00Z",
                                      "last_actor": "p@example.invalid",
                                      "last_reason": "still the same port"}}}}),
                              unreadable))
    return _ok(_client().get("/attention"))


def _drift_run(mp, tmp):
    """A REAL drift run through `run_drift_check()` (C96: the fixture never
    reached one): r1 clean, r2 drifted, r3 with no golden, r4 unreachable.
    Device I/O is faked as the population test fakes it; the run's result is
    stored the way the scheduler stores it."""
    import time as _time

    from modules import drift_check as D
    from modules.config import get_current_list_name

    def dev(name, ip):
        return {"hostname": name, "ip": ip, "username": "u", "password": "p",
                "device_type": "cisco_ios"}

    devices = [dev("r1", "203.0.113.1"), dev("r2", "203.0.113.2"),
               dev("r3", "203.0.113.3"), dev("r4", "203.0.113.4")]
    golden = {"203.0.113.1": "hostname r1\n!\nend\n",
              "203.0.113.2": "hostname r2\n!\nend\n",
              "203.0.113.4": "hostname r4\n!\nend\n"}
    running = {"203.0.113.1": "hostname r1\n!\nend\n",
               "203.0.113.2": "hostname r2\n!\nip route 0.0.0.0 0.0.0.0 Null0\nend\n"}

    def connect(d, pool, lock):
        if d["ip"] == "203.0.113.4":
            raise OSError("timed out")
        return d["ip"]

    csv_path = str(tmp / "drift-devices.csv")
    mp.setattr("modules.device.get_current_device_list", lambda: ("lab", csv_path))
    mp.setattr("modules.device.load_saved_devices", lambda path=None: list(devices))
    mp.setattr("modules.ai_assistant._golden_record",
               lambda ip: {"text": golden.get(ip), "path": "", "commit": "",
                           "source": "", "refused": ""})
    mp.setattr("modules.connection.get_persistent_connection", connect)
    mp.setattr("modules.commands.run_device_command", lambda conn, cmd: running[conn])
    mp.setattr("modules.approval_queue.add_approval", lambda **kw: {"ok": True})
    # The run's record goes to THIS provider's directory, never the shared
    # test store (whose guard refuses a file a test left there).
    state = str(tmp / "drift_state.json")
    mp.setattr(D, "_state_file", lambda list_name="": state)
    result = D.run_drift_check(triggered_by="manual")
    D._save_state({"last_check_ts": _time.time(), "last_result": result},
                  get_current_list_name())
    return result


def drift_status(mp, tmp):
    _drift_run(mp, tmp)
    return _ok(_client().get("/drift/status"))
