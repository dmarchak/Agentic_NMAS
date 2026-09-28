"""C158, C160: the stores the program read-modify-writes, fixed as C157 was.

The sweep after C157 found three more stores with the settings file's erasure
ingredients (an unreadable or torn read taken as empty or short, a save of
what was read, no cross-process lock):

- the NetBox created-object record: an erasure leaves every object NMAS made
  tagged and unrecorded, which Remove cannot act on;
- ``.nsot/rolled_back.json``: an erasure (or a torn read) lifts every
  rollback block, so the next plan offers the program that failed;
- ``devices.csv``: the inventory AND the only store of each device's
  encrypted credential, truncated in place, with five unlocked writers.

Neither of the first two destroys data anyone would notice. Each erases a
SAFETY MECHANISM (the operator's framing). One implementation now serves all
of them: ``modules/filestore.py``.
"""

import csv
import json
import multiprocessing
import os

import pytest


# ---------------------------------------------------------------------------
# The created-object record
# ---------------------------------------------------------------------------

@pytest.fixture
def created(tmp_path, monkeypatch):
    from modules import netbox_guard
    path = tmp_path / "netbox_created_ids.json"
    monkeypatch.setattr(netbox_guard, "_CREATED_IDS_FILE", str(path))
    return netbox_guard, path


def _record(prefix, n):
    from modules import netbox_guard
    for i in range(n):
        netbox_guard.record_created("lab", "dcim/devices", prefix * 1000 + i, f"d{i}")


def _run_two(target, args_a, args_b):
    ctx = multiprocessing.get_context("fork")
    procs = [ctx.Process(target=target, args=a) for a in (args_a, args_b)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
        assert p.exitcode == 0, p.exitcode


def test_two_processes_recording_creations_lose_nothing(created):
    netbox_guard, path = created
    _run_two(_record, (1, 40), (2, 40))
    rows = json.loads(path.read_text())["lab"]["dcim/devices"]
    assert len(rows) == 80, len(rows)


def test_an_unreadable_created_record_refuses_and_keeps_the_file(created):
    netbox_guard, path = created
    path.write_text('{"lab": {"dcim/devices": [{"id": 7, "na')     # a fragment
    before = path.read_bytes()
    with pytest.raises(netbox_guard.CreatedRecordUnreadable):
        netbox_guard.record_created("lab", "dcim/devices", 8, "r8")
    with pytest.raises(netbox_guard.CreatedRecordUnreadable):
        netbox_guard.forget_created("lab")
    assert path.read_bytes() == before, "the record was overwritten"
    assert [p for p in path.parent.iterdir() if ".corrupt-" in p.name]
    # A READ still reads (as nothing), and list deletion's reader still says
    # "cannot be read", which is not "owns nothing" (C155).
    assert netbox_guard.get_created("lab") == {}
    assert netbox_guard.recorded_objects("lab")[1]


def test_a_readable_record_still_records(created):
    """The floor: the refusal is for an unreadable file, not every file."""
    netbox_guard, path = created
    netbox_guard.record_created("lab", "dcim/sites", 3, "site")
    netbox_guard.record_created("lab", "dcim/sites", 4, "site2")
    assert [r["id"] for r in json.loads(path.read_text())["lab"]["dcim/sites"]] == [3, 4]


# ---------------------------------------------------------------------------
# rolled_back.json
# ---------------------------------------------------------------------------

@pytest.fixture
def repo(tmp_path):
    (tmp_path / ".nsot").mkdir()
    return str(tmp_path)


def _roll(repo, prefix, n):
    from modules.nsot import hostvars
    for i in range(n):
        hostvars.record_rolled_back(repo, f"{prefix}{i}", "abc", commands=[" shutdown"])


def test_two_processes_recording_rollbacks_lose_nothing(repo):
    _run_two(_roll, (repo, "a", 30), (repo, "b", 30))
    data = json.load(open(os.path.join(repo, ".nsot", "rolled_back.json")))
    assert len(data) == 60, len(data)


def test_an_unreadable_record_BLOCKS_every_plan_rather_than_lifting_every_block(repo):
    from modules.nsot import hostvars
    from modules.nsot.render_artifact import build_artifact

    hostvars.record_rolled_back(repo, "r1", "abc", commands=[" shutdown"])
    path = os.path.join(repo, ".nsot", "rolled_back.json")
    with open(path, "w") as fh:
        fh.write('{"r1": {"commands": [" shut')                    # torn
    before = open(path, "rb").read()

    for host in ("r1", "r2"):                   # r2 was never rolled back
        for program in (None, [" description x"]):
            note = hostvars.rolled_back_note(repo, host, program)
            assert note and note.get("unreadable"), (host, program, note)
    art = build_artifact("r2", "hostname r2\n", "cisco_ios", bootstrap=True,
                         rolled_back=hostvars.rolled_back_note(repo, "r2", []))
    assert any("could not be read" in r for r in art.blocking_reasons), art.blocking_reasons
    assert not any("was rolled back at" in r for r in art.blocking_reasons), \
        "the reason names the record, never a rollback nobody saw"

    with pytest.raises(hostvars.RolledBackRecordUnreadable):
        hostvars.record_rolled_back(repo, "r3", "abc", commands=["x"])
    with pytest.raises(hostvars.RolledBackRecordUnreadable):
        hostvars.clear_rolled_back(repo, "r1")
    assert hostvars.authorise_retry(repo, "r1", "p@x", "reason")["ok"] is False
    assert open(path, "rb").read() == before, "the record was overwritten"


def test_a_readable_record_still_lifts_for_another_program(repo):
    """The floor: a device whose program is not the failed one is not blocked."""
    from modules.nsot import hostvars
    hostvars.record_rolled_back(repo, "r1", "abc", commands=[" shutdown"])
    assert hostvars.rolled_back_note(repo, "r1", [" shutdown"])
    assert hostvars.rolled_back_note(repo, "r1", [" description x"]) is None
    assert hostvars.rolled_back_note(repo, "r2", [" shutdown"]) is None
    assert hostvars.clear_rolled_back(repo, "r1") is True


# ---------------------------------------------------------------------------
# devices.csv
# ---------------------------------------------------------------------------

def _dev(ip):
    return {"hostname": f"h{ip}", "ip": ip, "device_type": "cisco_ios",
            "username": "u", "password": "Pw123456", "secret": "", "role": "router"}


def _save(path, prefix, n):
    from modules import device
    for i in range(n):
        device.save_device(_dev(f"{prefix}.{i}"), path)


def test_two_processes_adding_devices_lose_nothing(tmp_path):
    path = str(tmp_path / "devices.csv")
    _run_two(_save, (path, "10.1", 40), (path, "10.2", 40))
    rows = list(csv.DictReader(open(path, newline="")))
    assert len(rows) == 80, len(rows)


def test_a_write_REPLACES_the_file_never_truncates_it(tmp_path):
    """A truncate in place keeps the inode, and a reader in the window gets
    a fragment that ``csv.DictReader`` returns as a shorter inventory."""
    from modules import device
    path = str(tmp_path / "devices.csv")
    device.write_devices_csv([_dev("10.0.0.1")], path)
    ino = os.stat(path).st_ino
    device.write_devices_csv([_dev("10.0.0.1"), _dev("10.0.0.2")], path)
    assert os.stat(path).st_ino != ino
    assert [n for n in os.listdir(tmp_path) if ".tmp" in n] == []


@pytest.fixture
def inventory(tmp_path, monkeypatch):
    import app as A
    from modules import device
    path = str(tmp_path / "devices.csv")
    device.write_devices_csv([_dev("192.0.2.1"), _dev("192.0.2.2")], path)
    monkeypatch.setattr(A, "get_current_device_list", lambda: ("lab", path))
    return A, path


def _ips(path):
    return [r["ip"] for r in csv.DictReader(open(path, newline=""))]


def test_reorder_keeps_a_device_the_order_does_not_name(inventory):
    """The order is the browser's view from page load; a device added since
    was dropped, with the only stored copy of its credential."""
    A, path = inventory
    from modules import device
    device.save_device(_dev("192.0.2.3"), path)        # added after page load
    r = A.app.test_client().post("/reorder", json=["192.0.2.2", "192.0.2.1"])
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    assert _ips(path) == ["192.0.2.2", "192.0.2.1", "192.0.2.3"]


def test_refresh_hostnames_keeps_a_change_made_while_it_ran(inventory, monkeypatch):
    """It read the list, opened a session per device, and wrote its minutes-old
    copy back: a rotation's new credential in between was erased."""
    A, path = inventory
    from modules import device

    def rotate_meanwhile(dev, fn):
        if dev["ip"] == "192.0.2.1":
            rows = device.load_saved_devices(path)
            for row in rows:
                if row["ip"] == "192.0.2.2":
                    row["password"] = "ROTATED-TOKEN"
            device.write_devices_csv(rows, path)
        return "renamed-" + dev["ip"].split(".")[-1]

    monkeypatch.setattr(A, "with_temp_connection", rotate_meanwhile)
    for ip in ("192.0.2.1", "192.0.2.2"):
        monkeypatch.setitem(A.device_status_cache, ip, True)
    monkeypatch.setattr("modules.ai_assistant._load_variables", lambda: {})
    monkeypatch.setattr("modules.ai_assistant._nsot_repo_dir", lambda: "")
    monkeypatch.setattr("modules.netbox_client.get_netbox_config", lambda: {})
    A.app.test_client().post("/refresh_hostnames")
    rows = {r["ip"]: r for r in csv.DictReader(open(path, newline=""))}
    assert rows["192.0.2.2"]["password"] == "ROTATED-TOKEN", "the rotation was written over"
    assert rows["192.0.2.1"]["hostname"] == "renamed-1"
    assert rows["192.0.2.2"]["hostname"] == "renamed-2"


def test_every_devices_csv_write_goes_through_the_one_writer():
    """No second writer: a CSV writer anywhere in the program is the atomic
    one. A floor, so a scan that found nothing cannot pass."""
    import pathlib
    roots = [pathlib.Path("modules"), pathlib.Path("routes"), pathlib.Path("app.py"),
             pathlib.Path("scripts")]
    files = [p for r in roots for p in ([r] if r.is_file() else r.rglob("*"))
             if p.is_file() and (p.suffix == ".py" or p.parent.name == "scripts")]
    assert len(files) > 100
    writers = [str(p) for p in files
               if "csv.DictWriter(" in p.read_text(errors="replace")]
    assert writers == ["modules/device.py"], writers
    src = open("modules/device.py").read()
    assert src.count("csv.DictWriter(") == 1
    assert 'open_secure(path, "w"' not in src


def test_two_lock_instances_for_one_path_nest_without_blocking(tmp_path):
    """Re-entrancy is per (thread, path): the first version tracked it per
    instance, the inner instance took a second flock, and the process blocked
    on itself. Run in a thread with a bound, so a regression FAILS rather than
    hangs (a hung concurrency test reports nothing)."""
    import threading
    from modules.filestore import PathLock
    path = str(tmp_path / "store.json")
    done = []

    def nest():
        with PathLock(path):
            with PathLock(lambda: path):
                done.append(True)

    t = threading.Thread(target=nest, daemon=True)
    t.start()
    t.join(10)
    assert done == [True], "a nested acquire of one path blocked on itself"
    # Released: another thread can take it now.
    t2 = threading.Thread(target=nest, daemon=True)
    t2.start()
    t2.join(10)
    assert done == [True, True]
