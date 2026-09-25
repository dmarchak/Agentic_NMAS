"""A new secret store is NOTICED, not discovered later.

Four times a store existed that `nmas-check-secret-storage` did not know
about -- netbox_modified.json, netbox_created_ids.json, and (2026-09-25)
credential_profiles.json and secret.key, both 0664, beneath a run that
printed "every file holding a secret is owner-only". Now every file under
data/ must match a declared class, and one that matches none fails the run.
"""

import importlib.machinery
import importlib.util
import os
import stat

import pytest


def _checker():
    loader = importlib.machinery.SourceFileLoader(
        "secret_checker_under_test", "scripts/nmas-check-secret-storage")
    spec = importlib.util.spec_from_loader("secret_checker_under_test", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


C = _checker()

#: The live data/ inventory, measured on the NMAS host 2026-09-25 (one
#: representative per group). The table must classify every one.
LIVE = ["agent_activity.json", "agent_timers.json", "ai_debug.log",
        "ai_usage_log.jsonl", "chat_histories/main.json", "checkpoints/main.json",
        "config_cache/10_255_1_24.json", "credential_profiles.json",
        "device_lists.json", "drift_state.json", "jenkins_checks.json", "key.key",
        "lists/default/config_repo/golden/r1.cfg",
        "lists/default/approval_queue.json", "lists/default/change_log.json",
        "lists/default/compliance_policy.json", "lists/default/devices.csv",
        "lists/default/devices.csv.bak-20260920T211420",
        "lists/default/devices.csv.pre-platform", "lists/default/drift_state.json",
        "lists/default/network_kb.json", "lists/default/pipeline_commits.json",
        "lists/default/playbooks/index.json", "lists/default/pre_change/r1.cfg",
        "lists/default/proto_topology_cache.json", "lists/default/remote.json",
        "lists/default/topology_positions.json", "lists/default/variables.json",
        "lists/default/golden_configs/r1.cfg", "netbox_created_ids.json",
        "netbox_modified.json", "netbox_sync_status.json",
        "pipeline_audit/tpl-s4.json", "provider_config.json", "quick_actions.json",
        "reveal_audit.jsonl", "secret.key", "user_settings.json",
        "user_settings.json.bak-2026-09-24-070743"]


def _tree(tmp_path, files):
    for rel, mode in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x")
        p.chmod(mode)
    return C.classify_data_tree(str(tmp_path))


def test_the_live_inventory_is_fully_classified(tmp_path):
    got = _tree(tmp_path, {rel: 0o600 for rel in LIVE})
    assert got["unclassified"] == [], got["unclassified"]
    assert sum(got["counts"].values()) == len(LIVE)
    assert got["counts"]["secret"] >= 9, "floor: the secret class is populated"


def test_a_new_file_is_UNCLASSIFIED_until_declared(tmp_path):
    got = _tree(tmp_path, {"key.key": 0o600, "new_store.json": 0o600,
                           "lists/default/tokens.db": 0o600})
    assert got["unclassified"] == ["lists/default/tokens.db", "new_store.json"]


@pytest.mark.parametrize("rel", ["credential_profiles.json", "secret.key",
                                 "lists/default/devices.csv"])
def test_a_loose_secret_store_fails(tmp_path, rel):
    got = _tree(tmp_path, {rel: 0o664})
    assert [r for r, _ in got["loose"]] == [rel]


def test_config_bearing_files_are_reported_not_failed_on_mode(tmp_path):
    got = _tree(tmp_path, {"config_cache/a.json": 0o664,
                           "lists/default/config_repo/golden/r1.cfg": 0o664})
    assert got["loose"] == [] and got["counts"]["config"] == 2


def test_the_credential_store_is_written_owner_only(tmp_path, monkeypatch):
    """The main credential store was 0664: written by a plain open()."""
    from modules import credentials
    target = tmp_path / "credential_profiles.json"
    monkeypatch.setattr(credentials, "_FILE", str(target))
    old = os.umask(0o002)
    try:
        credentials._save({"profiles": {}, "device_overrides": {}})
    finally:
        os.umask(old)
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_the_session_key_is_created_owner_only():
    src = open("app.py", encoding="utf-8").read()
    block = src[src.index("# Generate new secret key and persist it"):][:600]
    assert "open_secure(SECRET_KEY_FILE" in block


def test_the_device_csv_is_written_owner_only(tmp_path):
    """devices.csv holds every device's encrypted credentials; it was 0664."""
    from modules import device
    path = tmp_path / "devices.csv"
    path.write_text("")
    path.chmod(0o664)
    old = os.umask(0o002)
    try:
        device.write_devices_csv([], str(path))
    finally:
        os.umask(old)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
