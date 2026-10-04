"""The manifest store across processes (CONCURRENCY_AUDIT R6, 2026-10-04).

R6: every manifest writer held a per-process `threading.Lock`; `save()` wrote a shared
`.tmp` inside the repository; `load()` read an unreadable manifest as EMPTY, so the next save
wrote a one-device identity map. Host writers (`nmas-retire`, the dedupe script) ran beside
the app with nothing between them.

Now: the writers hold the repository's own lock (`repo.RepoLock`, cross-process, re-entrant
per thread); a save replaces the file atomically with its temp file BESIDE the repository; a
writer refuses an unreadable manifest (`filestore.StoreUnreadable`), its bytes preserved
beside the repository, never inside it. Driven with real child processes.
"""

import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CHILD = '''
import sys
sys.path.insert(0, {root!r})
from modules.nsot import manifest as M
repo, who, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
for i in range(n):
    M.upsert_device(repo, f"uid:{{who}}-{{i}}", f"{{who}}{{i}}", mgmt_ip="192.0.2.1")
'''


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "lab" / "config_repo"
    (path / ".nsot").mkdir(parents=True)
    return str(path)


def _untracked_inside(repo):
    return sorted(os.path.relpath(os.path.join(d, f), repo)
                  for d, _s, files in os.walk(repo) for f in files
                  if not f == "manifest.json")


class TestAcrossProcesses:
    def test_three_processes_writing_at_once_lose_nothing(self, repo, tmp_path):
        script = tmp_path / "child.py"
        script.write_text(CHILD.format(root=ROOT))
        procs = [subprocess.Popen([sys.executable, str(script), repo, who, "15"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 for who in ("a", "b", "c")]
        for p in procs:
            _out, err = p.communicate(timeout=120)
            assert p.returncode == 0, err.decode()[-600:]
        from modules.nsot import manifest as M
        devices = M.load(repo)["devices"]
        assert len(devices) == 45, sorted(devices)

    def test_the_writer_holds_the_repositorys_lock(self, repo):
        from modules.nsot import manifest as M
        from modules.nsot import repo as R
        assert isinstance(M.lock(repo), R.RepoLock)
        with M.lock(repo):
            assert R.RepoLock(repo).held()
            M.upsert_device(repo, "uid:x", "x")       # re-entrant: no wait on itself


class TestTheFileItself:
    def test_a_save_leaves_nothing_else_inside_the_repository(self, repo):
        from modules.nsot import manifest as M
        M.upsert_device(repo, "uid:x", "x", mgmt_ip="192.0.2.9")
        assert _untracked_inside(repo) == []
        with open(os.path.join(repo, ".nsot", "manifest.json"), encoding="utf-8") as fh:
            assert json.load(fh)["devices"]["uid:x"]["name"] == "x"

    def test_an_unreadable_manifest_refuses_the_write_and_is_kept(self, repo, tmp_path):
        from modules.filestore import StoreUnreadable
        from modules.nsot import manifest as M
        path = os.path.join(repo, ".nsot", "manifest.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write('{"devices": {"uid:a": {"name": "a"}, ')        # torn
        with pytest.raises(StoreUnreadable, match="nothing was written"):
            M.upsert_device(repo, "uid:b", "b")
        with open(path, encoding="utf-8") as fh:
            assert fh.read() == '{"devices": {"uid:a": {"name": "a"}, '
        kept = [f for f in os.listdir(os.path.dirname(repo)) if f.startswith("manifest.json.corrupt-")]
        assert kept and _untracked_inside(repo) == []

    def test_absent_is_empty_not_unreadable(self, repo):
        from modules.nsot import manifest as M
        M.upsert_device(repo, "uid:a", "a")
        assert list(M.load(repo)["devices"]) == ["uid:a"]


class TestTheDedupeScript:
    def test_it_removes_under_the_lock_from_a_fresh_read(self):
        import ast
        src = open(os.path.join(ROOT, "scripts", "nsot_dedupe_manifest.py"), encoding="utf-8").read()
        tree = ast.parse(src)
        withs = [n for n in ast.walk(tree) if isinstance(n, ast.With)
                 and any(ast.unparse(i.context_expr) == "M.lock(repo)" for i in n.items)]
        assert withs, "the apply holds the manifest's lock"
        body = ast.unparse(withs[0])
        assert "M.load_for_write(repo)" in body and "M.save(repo, fresh)" in body
