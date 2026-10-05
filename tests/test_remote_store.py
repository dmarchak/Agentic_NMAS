"""The publication record and its pushes across processes (CONCURRENCY_AUDIT R18; 2026-10-04).

R18:
- Each commit starts its own hook thread, and `record_push` and its siblings were unlocked
  read-modify-writes of `remote.json` through one shared `.tmp`. A failure recording
  `pending_tags` and a success popping them at once lost a tag the C223 rule says is kept.
- An unreadable `remote.json` read as "no remote", so the push hook answered "no remote
  configured, nothing pushed" with ok: publication stopped behind a success message.
- Two pushes of HEAD could arrive out of order and be recorded as a divergence.
- The S3 hook uploaded the WORKING file under the hook's sha.

Now:
- Every writer of `remote.json` reads it for writing and replaces it whole, under one lock
  across processes (`update_remote`). An unreadable file refuses, kept, never read as empty.
- The push hook says the file is unreadable.
- One publisher per repository at a time pushes the HEAD it reads under that lock.
- The S3 hook uploads the blob at the hook's sha.

Driven with real child processes, real repositories and a bare remote.
"""

import json
import os
import subprocess
import sys

import pytest

from modules.nsot import remote as R

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIST = "Lab"


def _git(repo, *args):
    out = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                         env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@l",
                                  GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@l"))
    assert out.returncode == 0, f"git {args}: {out.stderr}"
    return out.stdout.strip()


@pytest.fixture
def store(tmp_path, monkeypatch):
    """This list's data folder, with a remote recorded."""
    folder = tmp_path / "lab"
    folder.mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(folder))
    path = folder / "remote.json"
    path.write_text(json.dumps({"owner": "o", "repo": "r", "branch": "main",
                                "auto_push": True}), encoding="utf-8")
    return path


RECORDER = '''
import json, sys
sys.path.insert(0, {root!r})
import modules.config as config
config.get_list_data_dir = lambda name: {folder!r}
from modules.nsot import remote as R
who = sys.argv[1]
for i in range(40):
    if who == "held":
        R.record_push_held("Lab", reason="held", tags=[f"held/{{i}}"])
    else:
        R.record_push_failure("Lab", actor="t", reason="down", tags=[f"failed/{{i}}"])
'''


class TestTheRecordAcrossProcesses:
    def test_two_processes_recording_at_once_lose_no_pending_tag(self, store):
        procs = [subprocess.Popen([sys.executable, "-c",
                                   RECORDER.format(root=ROOT, folder=str(store.parent)), who],
                                  stderr=subprocess.PIPE, text=True)
                 for who in ("held", "failed")]
        for p in procs:
            _o, err = p.communicate(timeout=120)
            assert p.returncode == 0, err[-500:]
        pending = set(json.loads(store.read_text(encoding="utf-8"))["pending_tags"])
        want = {f"held/{i}" for i in range(40)} | {f"failed/{i}" for i in range(40)}
        assert want <= pending, f"lost {len(want - pending)} pending tag(s)"

    def test_an_unreadable_record_refuses_every_writer_and_is_kept(self, store):
        store.write_text("{not json", encoding="utf-8")
        for out in (R.record_push("Lab", actor="t", commit="a" * 40),
                    R.record_push_failure("Lab", actor="t", reason="x"),
                    R.record_push_held("Lab", reason="x"),
                    R.enable_auto_push("Lab", actor="t")):
            assert out["ok"] is False and "could not be read" in out["error"], out
        assert store.read_text(encoding="utf-8") == "{not json"
        assert any(n.startswith("remote.json.corrupt") for n in os.listdir(store.parent))

    def test_the_push_hook_says_unreadable_never_no_remote(self, store):
        from modules.nsot import archive

        store.write_text("{not json", encoding="utf-8")
        out = archive.push_hook({"list_name": LIST, "repo": str(store.parent)})
        assert out["ok"] is False
        assert "remote.json could not be read" in out["error"]
        assert "no remote configured" not in out["error"]

    def test_absent_is_still_no_remote(self, store):
        from modules.nsot import archive

        store.unlink()
        out = archive.push_hook({"list_name": LIST, "repo": str(store.parent)})
        assert out["ok"] is True and "no remote configured" in out["message"]


HOLDER = '''
import sys, time
sys.path.insert(0, {root!r})
from modules.nsot import remote as R
with R.publish_lock(sys.argv[1]):
    print("held", flush=True)
    time.sleep(2)
'''


@pytest.fixture
def world(tmp_path, monkeypatch, store):
    """A repository with two commits; a bare remote holding the first."""
    local = str(tmp_path / "config_repo")
    os.makedirs(local)
    _git(local, "init", "-q", "-b", "main")
    for text in ("hostname s1\n", "hostname s1\n!\n"):
        with open(os.path.join(local, "golden.cfg"), "w", encoding="utf-8") as fh:
            fh.write(text)
        _git(local, "add", "-A")
        _git(local, "commit", "-q", "-m", "a commit")
    bare = str(tmp_path / "remote.git")
    subprocess.run(["git", "init", "-q", "-b", "main", "--bare", bare], check=True)
    _git(local, "push", "-q", bare, "HEAD~1:refs/heads/main")
    monkeypatch.setattr(R, "remote_url", lambda config: bare)
    monkeypatch.setattr(R, "auto_push_decision", lambda name, repo: {"push": True,
                                                                     "reason": "ok"})
    return {"local": local, "bare": bare}


class TestOnePublisherPushesWhatItReads:
    def test_a_hook_for_an_older_commit_pushes_head_and_records_no_divergence(self, world,
                                                                             store):
        from modules.nsot import archive

        older = _git(world["local"], "rev-parse", "HEAD~1")
        out = archive.push_hook({"list_name": LIST, "repo": world["local"], "sha": older})
        assert out["ok"] is True, out
        head = _git(world["local"], "rev-parse", "HEAD")
        assert _git(world["bare"], "rev-parse", "main") == head
        record = json.loads(store.read_text(encoding="utf-8"))
        assert record["last_push"]["commit"] == head and "last_push_failure" not in record

    def test_a_push_waits_while_another_process_publishes(self, world):
        """Another process holds this repository's publish lock for 2 s; the hook pushes only
        after it lets go, so two publishers never push at once."""
        import time

        from modules.nsot import archive

        holder = subprocess.Popen([sys.executable, "-c", HOLDER.format(root=ROOT),
                                   world["local"]], stdout=subprocess.PIPE, text=True)
        assert holder.stdout.readline().strip() == "held"
        started = time.time()
        out = archive.push_hook({"list_name": LIST, "repo": world["local"]})
        waited = time.time() - started
        holder.communicate(timeout=30)
        assert out["ok"] is True, out
        assert waited >= 1.5, f"the hook pushed after {waited:.2f} s, while the lock was held"

    def test_the_publish_lock_is_beside_the_repository_never_inside(self, world):
        lock = R.publish_lock(world["local"])
        assert os.path.dirname(lock.path()) == os.path.dirname(world["local"])


class _Minio:
    """The two calls the hook makes on minio's client, recording what was uploaded."""
    uploads: dict = {}

    def __init__(self, *_a, **_k):
        pass

    def put_object(self, bucket, key, data, length, metadata=None):
        _Minio.uploads[key] = (data.read(), length, dict(metadata or {}))


class TestTheArchiveUploadsWhatWasCommitted:
    def test_the_blob_at_the_hooks_sha_is_uploaded_not_the_working_file(self, tmp_path,
                                                                         monkeypatch):
        import types

        from modules.nsot import archive

        repo = str(tmp_path / "config_repo")
        os.makedirs(os.path.join(repo, "golden"))
        _git(repo, "init", "-q", "-b", "main")
        golden = os.path.join(repo, "golden", "s1.cfg")
        with open(golden, "w", encoding="utf-8") as fh:
            fh.write("hostname s1\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "s1's golden")
        sha = _git(repo, "rev-parse", "HEAD")
        with open(golden, "w", encoding="utf-8") as fh:     # a later save, not yet committed
            fh.write("hostname s1\ninterface Loopback9\n")

        class _S3:
            url = "http://192.0.2.5:9000"

            def __init__(self, list_name=""):
                assert list_name == "Default", "the archive is the commit's own network's"

            def is_configured(self):
                return True

        _Minio.uploads = {}
        monkeypatch.setitem(sys.modules, "minio", types.SimpleNamespace(Minio=_Minio))
        monkeypatch.setattr("modules.integrations.s3_archive.S3ArchiveIntegration", _S3)
        monkeypatch.setattr("modules.secrets_store.get_secret", lambda key: "x")
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda key, default=None: {"s3_bucket": "b"}.get(key, default))
        out = archive.s3_archive_hook({"repo": repo, "sha": sha, "devices": ["s1"],
                                       "tags": [], "source": "t", "actor": "t",
                                       "list_name": "Default"})
        assert out["ok"] is True, out
        (key, (data, length, meta)), = _Minio.uploads.items()
        assert data == b"hostname s1\n" and length == len(data)
        assert meta["x-amz-meta-commit"] == sha and key.endswith(f"{sha[:12]}.cfg")
