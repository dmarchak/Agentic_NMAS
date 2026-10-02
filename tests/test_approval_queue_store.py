"""The approval queue's store holds across processes and never erases a decision
(CONCURRENCY_AUDIT R4, 2026-10-02).

Re-measured before the fix: `_save_queue` truncated in place with no lock, `_load_queue` read
an unreadable file as an empty queue, `get_pending()` and `get_all()` SAVED on every call
(the main page polls them from every tab every 30 s), and `resolve()` saved the list it read
before its execution again afterwards, over whatever the drift run had added meanwhile.

- two PROCESSES adding items at once lose none;
- a read writes nothing, an expired item included;
- an unreadable queue refuses every write (the file kept, a `.corrupt-` copy beside it) and
  is its own answer to a read: 503 with the reason, never an empty list;
- an item added while an approval executes is kept;
- two approvers at once: the second is told it is decided;
- a save replaces the file (a new inode), never a truncate in place.
"""

import json
import os
import subprocess
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CHILD = '''
import sys
sys.path.insert(0, {root!r})
from modules import approval_queue as Q
path, tag, net, n = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
Q._queue_path = lambda *a: path
for i in range(n):
    Q.add_approval("update_golden_config", f"{{tag}} {{i}}", f"{{net}}.{{i}}",
                   device_hostname=f"{{tag}}{{i}}")
'''


@pytest.fixture
def queue(tmp_path, monkeypatch):
    from modules import approval_queue as Q
    path = str(tmp_path / "approval_queue.json")
    monkeypatch.setattr(Q, "_queue_path", lambda *a: path)
    monkeypatch.setattr("modules.inventory.is_stale", lambda ip, ln="": False)
    return Q, path


def _add(Q, host="r1"):
    return Q.add_approval("update_golden_config", f"drift on {host}",
                          f"192.0.2.{int(host[1:]) if host[1:].isdigit() else 1}",
                          device_hostname=host)


class TestTwoProcesses:
    def test_two_processes_adding_at_once_lose_nothing(self, queue, tmp_path):
        Q, path = queue
        script = tmp_path / "child.py"
        script.write_text(CHILD.format(root=ROOT))
        # Distinct addresses: the queue keeps one pending item per device and kind.
        procs = [subprocess.Popen([sys.executable, str(script), path, tag, net, "40"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 for tag, net in (("a", "192.0.2"), ("b", "198.51.100"))]
        for p in procs:
            out, err = p.communicate(timeout=120)
            assert p.returncode == 0, err.decode()[-2000:]
        hosts = sorted(e["device_hostname"] for e in json.load(open(path)))
        assert hosts == sorted([f"a{i}" for i in range(40)] + [f"b{i}" for i in range(40)])


class TestReadsWriteNothing:
    def test_a_read_leaves_the_file_as_it_was_an_expired_item_included(self, queue):
        Q, path = queue
        _add(Q)
        entries = json.load(open(path))
        entries[0]["created_ts"] = time.time() - (Q.EXPIRY_HOURS + 1) * 3600
        open(path, "w").write(json.dumps(entries))
        before = (open(path, "rb").read(), os.stat(path).st_ino)
        assert Q.get_pending() == []
        assert Q.get_all()[0]["status"] == "expired", "expiry still applies, in memory"
        assert (open(path, "rb").read(), os.stat(path).st_ino) == before


class TestAnUnreadableQueue:
    def test_writes_refuse_and_the_file_is_kept(self, queue):
        from modules.filestore import StoreUnreadable
        Q, path = queue
        open(path, "w").write('[{"id": "x", "status": "pend')
        before = open(path, "rb").read()
        with pytest.raises(StoreUnreadable):
            _add(Q)
        got = Q.resolve("x", "approve", actor="a@example.com")
        assert got["ok"] is False and got["unreadable"] and "could not be read" in got["error"]
        assert Q.mark_done("x", actor="a")["unreadable"] is True
        assert Q.withdraw("x", "a reason given", "test")["unreadable"] is True
        assert open(path, "rb").read() == before
        assert [f for f in os.listdir(os.path.dirname(path)) if ".corrupt-" in f]

    def test_a_read_says_so_never_an_empty_queue(self, queue):
        from modules.filestore import StoreUnreadable
        Q, path = queue
        open(path, "w").write("{torn")
        with pytest.raises(StoreUnreadable):
            Q.get_pending()
        from app import app
        r = app.test_client().get("/ai/approvals")
        assert r.status_code == 503 and "could not be read" in r.get_json()["error"]
        a = app.test_client().post("/ai/approvals/x/approve")
        assert a.status_code == 503
        d = app.test_client().get("/drift/status").get_json()
        assert d["pending_approvals"] is None and "could not be read" \
            in d["pending_approvals_error"]


class TestResolve:
    def test_an_item_added_while_it_executes_is_kept(self, queue, monkeypatch):
        Q, path = queue
        first = _add(Q, "r1")

        def execute_while_the_drift_run_adds(entry, actor=""):
            _add(Q, "r9")                      # the drift run, meanwhile
            return {"error": "the device did not answer"}

        monkeypatch.setattr(Q, "_execute", execute_while_the_drift_run_adds)
        got = Q.resolve(first, "approve", actor="a@example.com")
        assert got["ok"]
        by_host = {e["device_hostname"]: e for e in json.load(open(path))}
        assert set(by_host) == {"r1", "r9"}, "the item added meanwhile was overwritten"
        assert by_host["r1"]["status"] == "pending"
        assert by_host["r1"]["context"] == "Last attempt failed: the device did not answer"

    def test_the_second_approver_is_told_it_is_decided(self, queue, monkeypatch):
        Q, _path = queue
        eid = _add(Q)
        monkeypatch.setattr(Q, "_execute", lambda entry, actor="": {"ok": True})
        assert Q.resolve(eid, "approve", actor="a@example.com")["ok"]
        second = Q.resolve(eid, "reject", actor="b@example.com")
        assert second == {"ok": False, "error": "Approval is already approved"}


class TestTheWrite:
    def test_a_save_replaces_the_file(self, queue):
        Q, path = queue
        _add(Q, "r1")
        inode = os.stat(path).st_ino
        _add(Q, "r2")
        assert os.stat(path).st_ino != inode, "truncated in place, not replaced"
