"""P.3 step 2: the direct-push paths the feature audit cut are gone.

Each was a way to put configuration on a device with no plan, no confirm
hash and no rollback. None of them had a test: this file is the first to
name them, and it names them to assert their absence.

- every cut route answers 404, by path (what a stale page or a script sends);
- nothing the browser loads, and no script, still refers to one;
- the Configure forms send nothing, and say so.

Bulk config mode was refused by name on a route that stayed; that route,
/bulk_execute, left whole at 7.8 (2026-10-15), so its refusal's two tests went
with it. Chat playbook replay left with the AI family (D15).
"""

import os

import pytest

from tests.source_index import tracked

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
    # C103 (2026-09-29, the operator's decision): the two saves that could
    # report success without proving it. Persist is the one save now.
    ("POST", "/device/192.0.2.1/save_config"),
    ("POST", "/device/192.0.2.1/save_running_to_startup"),
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
           "url_for('restore_golden_config'", "url_for('save_to_startup'", "/save_running_to_startup"]


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
    return tracked("templates", "static/js/gen", "scripts")


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


