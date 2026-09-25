"""OPEN_FINDINGS C11: retire, the whole exit -- against a real repo, CSV,
manifest, template binding and credential store in a temp tree."""

import json
import os

import pytest

from modules.nsot import retire as RT

PW = "rotated-only-here-9f3a"


@pytest.fixture
def world(tmp_path, monkeypatch):
    from modules import device
    from modules.nsot import hostvars, manifest, repo as R, templates_repo

    monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path / "lists"))
    monkeypatch.setattr("modules.device.get_device_lists",
                        lambda: [{"name": "Lab", "filename": "lab"}])
    monkeypatch.setattr("modules.nsot.retire._netbox_facts", lambda l, h: {
        "checked": True, "exists": True, "id": 9, "tags": ["bgp"],
        "created_by_nmas": False})
    monkeypatch.setattr("modules.credentials.has_device_override", lambda ip: False)
    # One approved template, so the withdrawal branch RUNS: the bound set is
    # still computed for real from the manifest.
    monkeypatch.setattr("modules.nsot.approval.approved_templates",
                        lambda repo: ["cisco_iosxe/base.j2"])
    settings = {"nsot_git_author_name": "NMAS",
                "nsot_git_author_email": "n@l", "nsot_device_tag_retention": 50,
                "clab_declared_unmapped": {}}
    import modules.settings_schema as ss
    monkeypatch.setattr(ss, "get_setting",
                        lambda k, d=None: settings.get(k, ss.DEFAULTS.get(k, d)))
    monkeypatch.setattr(ss, "write_settings", lambda updates, actor="": (
        settings.update(updates) or {"ok": True}))
    monkeypatch.setattr("modules.nsot.credential_rotation.clab_target_for",
                        lambda l, h: {"lab": "default", "configs_dir": "labs/lab/configs",
                                      "launch_patch": "p", "host": "u@c"})
    list_dir = tmp_path / "lists" / "lab"
    list_dir.mkdir(parents=True)
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda n: str(list_dir))
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda c: None)
    repo = str(list_dir / "config_repo")
    R.init_repo(repo)
    templates_repo.seed_templates(repo)
    # The module's own Fernet, built at import: patching KEY_FILE afterwards
    # would encrypt with one key and decrypt with another.
    f = device.fernet
    rows = [{"hostname": h, "device_type": "cisco_xe", "ip": ip,
             "username": "admin", "password": f.encrypt(pw.encode()).decode(),
             "secret": "", "platform": "cisco_iosxe"}
            for h, ip, pw in (("r4", "192.0.2.14", "other-pw-1234567"),
                              ("r5", "192.0.2.15", PW))]
    csv_path = str(list_dir / "devices.csv")
    device.write_devices_csv(rows, csv_path)
    for h, ip in (("r4", "192.0.2.14"), ("r5", "192.0.2.15")):
        ident = manifest.new_identity() if hasattr(manifest, "new_identity") else f"uid:{h}"
        manifest.upsert_device(repo, ident, h, mgmt_ip=ip, platform="cisco_iosxe")
        hostvars.write_committed(repo, {"hostname": h, "platform": "cisco_iosxe"})
        with open(os.path.join(repo, "golden", f"{h}.cfg"), "w") as fh:
            fh.write(f"hostname {h}\nevent manager applet NMAS-HEARTBEAT\n"
                     if h == "r5" else f"hostname {h}\n")
    R._commit_paths("Lab", ["host_vars", "golden", ".nsot"], "seed", [], "test")
    return {"repo": repo, "csv": csv_path, "settings": settings, "R": R}


def _bg(pw=PW, host="r5", user="admin"):
    return {"list_name": "Lab", "devices": [
        {"hostname": host, "list_name": "Lab", "username": user, "password": pw}]}


def test_the_plan_names_every_step_and_everything_it_will_not_do(world):
    p = RT.plan("Lab", "r5", "ISP PE, outside our boundary")
    assert p["ok"], p["refusals"]
    keys = [s["key"] for s in p["steps"] if not s["done"]]
    assert keys == ["declare", "commit", "approval", "row"], keys
    approval = next(s["what"] for s in p["steps"] if s["key"] == "approval")
    assert "cisco_iosxe/base.j2" in approval and "against r4" in approval
    joined = " ".join(p["not_doing"])
    for claim in ("NetBox device 9 is KEPT", "Remove cannot touch it",
                  "Oxidized keeps polling", "freezes at its last sync",
                  "running configuration is not changed"):
        assert claim in joined, claim
    assert any("NMAS-HEARTBEAT" in a for a in p["advisories"])


def test_no_breakglass_is_a_refusal_and_nothing_happens(world):
    p = RT.plan("Lab", "r5", "retired")
    out = RT.apply("Lab", "r5", reason="retired", actor="op",
                   confirmed_hash=p["hash"], breakglass=None)
    assert out["ok"] is False and "break-glass" in out["error"]
    assert RT.plan("Lab", "r5", "retired")["hash"] == p["hash"], "nothing moved"


@pytest.mark.parametrize("record,why", [
    (lambda: _bg(host="r4"), "no entry for r5"),
    (lambda: _bg(pw="an-older-password"), "OLDER credential"),
])
def test_a_record_without_the_CURRENT_credential_refuses(world, record, why):
    p = RT.plan("Lab", "r5", "retired")
    out = RT.apply("Lab", "r5", reason="retired", actor="op",
                   confirmed_hash=p["hash"], breakglass=record())
    assert out["ok"] is False and why in out["error"]


def test_retire_does_the_whole_exit_in_one_commit(world):
    from modules.device import load_saved_devices
    from modules.nsot import manifest, templates_repo
    R, repo = world["R"], world["repo"]
    p = RT.plan("Lab", "r5", "ISP PE, outside our boundary")
    out = RT.apply("Lab", "r5", reason="ISP PE, outside our boundary",
                   actor="op@example.com", confirmed_hash=p["hash"],
                   breakglass=_bg())
    assert out["ok"], out
    # ONE commit removed both files and released the identity, history kept
    _rc, files, _e = R.git(repo, "show", "--name-status", "--format=", "HEAD")
    assert "D\tgolden/r5.cfg" in files and "D\thost_vars/r5.yml" in files
    assert ".nsot/manifest.json" in files
    _rc, body, _e = R.git(repo, "log", "-1", "--format=%B")
    assert "Retired-Device: r5" in body and "Not-Done: NetBox device 9" in body
    assert R.git(repo, "show", "HEAD~1:golden/r5.cfg")[0] == 0, "history keeps it"
    assert manifest.find_by_name(repo, "r5")[0] is None
    assert "r5" not in [b["device"] for b in
                        templates_repo.devices_for_template(repo, "cisco_iosxe/base.j2")]
    # the row went LAST, and only r5's
    assert [d["hostname"] for d in load_saved_devices(world["csv"])] == ["r4"]
    # declared, with who and why
    d = world["settings"]["clab_declared_unmapped"]["Lab"]["r5"]
    assert d["by"] == "op@example.com" and "ISP PE" in d["reason"]
    # and now there is nothing left to do
    again = RT.plan("Lab", "r5", "ISP PE, outside our boundary")
    assert any("nothing to retire" in r for r in again["refusals"]), \
        again["refusals"]


def test_a_partial_retire_is_finished_by_running_it_again(world, monkeypatch):
    from modules.device import load_saved_devices
    p = RT.plan("Lab", "r5", "retired")
    import modules.device as dev
    real = dev.delete_device
    monkeypatch.setattr(dev, "delete_device",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    out = RT.apply("Lab", "r5", reason="retired", actor="op",
                   confirmed_hash=p["hash"], breakglass=_bg())
    assert out["ok"] is False and out["failed_at"] == "row"
    assert "commit" in out["done"]
    monkeypatch.setattr(dev, "delete_device", real)
    p2 = RT.plan("Lab", "r5", "retired")
    assert [s["key"] for s in p2["steps"] if not s["done"]] == ["row"]
    assert RT.apply("Lab", "r5", reason="retired", actor="op",
                    confirmed_hash=p2["hash"], breakglass=_bg())["ok"]
    assert [d["hostname"] for d in load_saved_devices(world["csv"])] == ["r4"]


def test_a_failed_commit_puts_the_tree_back(world, monkeypatch):
    R, repo = world["R"], world["repo"]
    p = RT.plan("Lab", "r5", "retired")
    monkeypatch.setattr(R, "_commit_paths",
                        lambda *a, **k: {"ok": False, "error": "boom"})
    out = RT.apply("Lab", "r5", reason="retired", actor="op",
                   confirmed_hash=p["hash"], breakglass=_bg())
    assert out["ok"] is False and out["failed_at"] == "commit"
    assert R.git(repo, "status", "--porcelain", "--", "host_vars", "golden",
                 ".nsot/manifest.json")[1].strip() == ""
    assert os.path.exists(os.path.join(repo, "golden", "r5.cfg"))


def test_refusals(world):
    assert "reason is required" in RT.plan("Lab", "r5", "")["refusals"][0]
    assert "nothing to retire" in RT.plan("Lab", "zz", "x")["refusals"][0]
    assert "no device list" in RT.plan("Nope", "r5", "x")["refusals"][0]
