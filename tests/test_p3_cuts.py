"""P.3 step 2: the direct-push paths the feature audit cut are gone.

Each was a way to put configuration on a device with no plan, no confirm
hash and no rollback. None of them had a test: this file is the first to
name them, and it names them to assert their absence.

- every cut route answers 404, by path (what a stale page or a script sends);
- nothing the browser loads, and no script, still refers to one;
- the two cuts that keep a route refuse BY NAME rather than degrade:
  bulk config mode (enable mode stays) and chat playbook replay;
- the Configure forms send nothing, and say so.
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CUT = [
    ("POST", "/execute_command"),
    ("POST", "/run_script/192.0.2.1"),
    ("POST", "/device/192.0.2.1/restore_backup"),
    ("POST", "/bulk_remove_static_routes"),
    ("POST", "/configure/apply"),
    ("POST", "/netbox/sync"),
    ("POST", "/netbox/sync_all"),
    ("POST", "/netbox/remove"),
    # P.3 step 3 (D5): the unguarded golden replay, behind two buttons.
    ("POST", "/device/192.0.2.1/restore_golden_config"),
    ("POST", "/bulk_restore_golden_config"),
]

#: What a caller would have written to reach each one.
#: Spelled as the removed callers spelled them (a fetch path, a `url_for`, a
#: JS name), never as a bare Python name, which would read as a use of the
#: removed function to `check_removed_definitions.py`.
NEEDLES = ["/execute_command", "url_for('run_script'", "/run_script",
           "/restore_backup", "/bulk_remove_static_routes",
           "bulkRemoveStaticRoutes", "/configure/apply", "/netbox/sync",
           "/netbox/remove", "run_playbook_id", "runPlaybook",
           "showRestoreModal", "/restore_golden_config",
           "url_for('restore_golden_config'"]


def _client():
    import app as A
    return A.app.test_client()


@pytest.mark.parametrize("method,path", CUT)
def test_each_cut_route_is_404(method, path):
    resp = _client().open(path, method=method, json={})
    assert resp.status_code == 404, (path, resp.status_code)


def test_the_404_check_can_see_a_route_that_exists():
    """Control: a live mutating route is not 404 for the same call."""
    assert _client().post("/deploy/plan", json={}).status_code != 404


def _shipped_files():
    out = []
    for base in ("templates", "static/js/gen", "scripts"):
        for dirpath, _dirs, names in os.walk(os.path.join(ROOT, base)):
            for n in names:
                out.append(os.path.join(dirpath, n))
    return out


def test_nothing_shipped_refers_to_a_cut_path():
    files = _shipped_files()
    assert len(files) >= 40, len(files)
    hits = {}
    for path in files:
        try:
            text = open(path, encoding="utf-8").read()
        except (UnicodeDecodeError, OSError):
            continue
        for needle in NEEDLES:
            if needle in text:
                hits.setdefault(os.path.relpath(path, ROOT), []).append(needle)
    assert not hits, hits


def test_the_scan_would_see_one():
    """Control: the needles are spelled as the removed callers spelled them."""
    old = "fetch('/bulk_remove_static_routes', { method: 'POST', body: formData })"
    assert any(n in old for n in NEEDLES)


def test_bulk_config_mode_is_refused_by_name():
    resp = _client().post("/bulk_execute", data={
        "device_ips[]": ["192.0.2.1"], "command": "hostname x",
        "command_mode": "config"})
    body = resp.get_json()
    assert resp.status_code == 400
    assert "Config mode was removed" in body["message"], body


def test_bulk_enable_mode_still_reaches_the_route(monkeypatch):
    """Control: the refusal is for config mode, not the route."""
    import app as A
    monkeypatch.setattr(A, "load_saved_devices", lambda _p: [])
    resp = _client().post("/bulk_execute", data={
        "device_ips[]": ["192.0.2.1"], "command": "show clock",
        "command_mode": "enable"})
    body = resp.get_json()
    assert "Config mode was removed" not in (body.get("message") or ""), body
    assert body.get("message") == "No valid devices found", body


def test_playbook_replay_is_refused_and_never_reaches_the_model(monkeypatch):
    import app as A
    called = []
    monkeypatch.setattr(A._ai, "run_chat", lambda **k: called.append(k) or iter(()))
    resp = _client().post("/ai/chat", json={
        "message": "▶ Run playbook: x", "run_playbook_id": "pb-1"})
    assert resp.status_code == 410, resp.status_code
    assert "Running a playbook was removed" in resp.get_json()["error"]
    assert called == []


def test_the_configure_tab_sends_nothing_and_says_so():
    from tests.js_source import read_shipped
    page = read_shipped("templates/index.html")
    assert "data-p3-configure-note" in page
    body = re.search(r"function _cfgShowParams\(payload\) \{(.*?)\n  \}", page, re.S)
    assert body, "_cfgShowParams not found"
    assert "fetch(" not in body.group(1)
    assert "Nothing was sent" in body.group(1)
