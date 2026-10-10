"""One NetBox writer per list at a time, across processes (CONCURRENCY_AUDIT R21; 2026-10-04).

Two people each holding a valid preview could import the same list at once, racing
get-then-create on its shared objects (site, region, VRF); onboarding's phase two, adopt and
retire's mask took nothing either. The confirm started its import on a thread with nothing
refusing a second, and the sync-status file was truncated in place by one writer while the
others shared a `.tmp`, under an in-process lock only.

Now each write operation (the import, both removals, retire's mask) holds
`netbox_guard.list_writer` for its list: a second writer, in any process, is refused naming
the first, never queued; re-entrant on the holding thread only. The import confirm refuses
before it starts its thread. The status file is locked across processes and replaced whole.
"""

import ast
import json
import os
import subprocess
import sys
import threading

import pytest

from modules import netbox_guard as G

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

HOLDER = '''
import sys
sys.path.insert(0, {root!r})
from modules import netbox_guard as G
with G.list_writer("Lab", "import", "operator@example.invalid"):
    print("held", flush=True)
    sys.stdin.readline()
'''


@pytest.fixture
def held_elsewhere():
    """Another PROCESS writes Lab's NetBox objects until released."""
    p = subprocess.Popen([sys.executable, "-c", HOLDER.format(root=ROOT)],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    assert p.stdout.readline().strip() == "held"
    yield
    p.communicate("\n", timeout=30)


def test_a_second_writer_in_another_process_is_refused_naming_the_first(held_elsewhere):
    with pytest.raises(G.NetBoxBusy) as got:
        with G.list_writer("Lab", "removal of r9", "b@example.invalid"):
            pytest.fail("two writers of one list")
    assert "import by operator@example.invalid is writing Lab's NetBox objects" in str(got.value)
    assert G.list_writer_now("Lab")["operation"] == "import"
    with G.list_writer("Other", "import", "b@example.invalid"):   # another list is free
        pass


def test_the_import_is_refused_and_writes_nothing(held_elsewhere, monkeypatch):
    from modules import netbox_client as N

    monkeypatch.setattr(G, "writes_allowed", lambda: True)
    monkeypatch.setattr(N, "_sync_list_to_netbox_impl",
                        lambda *a, **k: pytest.fail("imported under another writer"))
    out = N.sync_list_to_netbox("Lab", [{"hostname": "r1"}], actor="b@example.invalid",
                                authority="a test")
    assert out["ok"] is False and out["busy"] is True
    assert out["error"].startswith("Not imported: import by operator@example.invalid")


def test_the_import_confirm_refuses_before_starting_its_thread(held_elsewhere, monkeypatch):
    import app as nmas

    monkeypatch.setattr("modules.netbox_client.get_netbox_config",
                        lambda: {"url": "http://192.0.2.8", "token": "t"})
    monkeypatch.setattr("modules.netbox_ops.list_devices", lambda name: ("Lab", [{"hostname": "r1"}]))
    monkeypatch.setattr("modules.netbox_ops.authorize", lambda *a, **k: None)
    monkeypatch.setattr(threading, "Thread",
                        lambda *a, **k: pytest.fail("an import thread started"))
    r = nmas.app.test_client().post("/netbox/safety/import/apply", json={"list_name": "Lab"})
    body = r.get_json()
    assert r.status_code == 409 and body["busy"] is True, body
    assert "import by operator@example.invalid is writing Lab's NetBox objects" in body["error"]


def test_it_is_reentrant_on_its_own_thread_and_refuses_another_thread():
    with G.list_writer("Lab", "onboarding phase two", "a"):
        with G.list_writer("Lab", "import", "a"):          # phase two calling the import
            refused = []

            def other():
                try:
                    with G.list_writer("Lab", "import", "b"):
                        pass
                except G.NetBoxBusy as exc:
                    refused.append(str(exc))

            t = threading.Thread(target=other)
            t.start()
            t.join(10)
            assert refused and "onboarding phase two by a" in refused[0]
    assert G.list_writer_now("Lab") is None


def test_every_write_operation_takes_it():
    """Parsed: the import, both removals and retire's mask hold the list's writer lock."""
    sites = {("modules/netbox_client.py", "sync_list_to_netbox"),
             ("modules/netbox_client.py", "remove_device_from_netbox"),
             ("modules/netbox_client.py", "remove_list_from_netbox"),
             ("modules/nsot/retire.py", "apply")}
    for rel, fn in sites:
        tree = ast.parse(open(os.path.join(ROOT, rel), encoding="utf-8").read())
        node = next(n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef) and n.name == fn)
        assert "list_writer(" in ast.unparse(node), f"{rel} {fn} writes without the lock"


STATUS = '''
import sys
sys.path.insert(0, {root!r})
from modules import netbox_client as N
N._SYNC_STATUS_FILE = sys.argv[1]
for i in range(40):
    N.set_sync_running(f"{{sys.argv[2]}}{{i}}", True)
'''


def test_two_processes_writing_the_status_lose_no_entry(tmp_path):
    path = str(tmp_path / "netbox_sync_status.json")
    procs = [subprocess.Popen([sys.executable, "-c", STATUS.format(root=ROOT), path, who],
                              stderr=subprocess.PIPE, text=True) for who in ("a", "b")]
    for p in procs:
        _o, err = p.communicate(timeout=120)
        assert p.returncode == 0, err[-500:]
    with open(path, encoding="utf-8") as fh:
        running = json.load(fh)["running"]
    want = {f"{w}{i}" for w in "ab" for i in range(40)}
    assert want <= set(running), f"lost {len(want - set(running))} entr(ies)"
