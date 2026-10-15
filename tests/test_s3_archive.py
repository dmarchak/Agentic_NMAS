"""Mercury's connection to MinIO (Phase 4 step 1; docs/NSOT_PHASE4_MINIO.md, approved by the
operator 2026-10-08): one client, TLS verification as set (C355), and a Test of the four things
every use needs. The client is boto3 (the operator's decision, 2026-10-08: the host's apt
package, 1.34.46, pinned through the lock).

boto3 is not installed where CI runs until the lock is regenerated on the host, so it is stood
in for at its import (`sys.modules["boto3"]`, `["botocore.config"]`), recording how the client
was built and what it was asked, with boto3's own call shapes (keyword arguments, `Body`,
`ContentLength`, a missing bucket as a 404 error); Mercury's own code runs for real.
"""

import io
import sys
import types

import pytest

from modules.integrations import s3_archive as S3

VALUES = {"s3_endpoint": "https://192.0.2.5:9000", "s3_bucket": "mercury",
          "s3_prefix": "", "s3_region": "", "s3_verify_tls": True}


class ClientError(Exception):
    """botocore's ClientError, as far as Mercury reads it: a `response` with an error code."""

    def __init__(self, code, op):
        super().__init__(f"An error occurred ({code}) when calling the {op} operation")
        self.response = {"Error": {"Code": code}}


class Server:
    """boto3's S3 client as a fake server: a bucket, the objects written, every call made."""

    def __init__(self, exists=True, corrupt=False, fail=""):
        self.exists, self.corrupt, self.fail = exists, corrupt, fail
        self.objects, self.calls, self.built, self.metadata = {}, [], {}, {}

    def client(self, service, **kw):
        self.built = dict(kw, service=service)
        return self

    def _maybe_fail(self, name, op):
        self.calls.append(name)
        if self.fail == name:
            raise ClientError("AccessDenied", op)

    def head_bucket(self, Bucket):
        self._maybe_fail("bucket", "HeadBucket")
        if not self.exists:
            raise ClientError("404", "HeadBucket")

    def put_object(self, Bucket, Key, Body, Metadata=None):
        self._maybe_fail("put", "PutObject")
        self.objects[Key] = bytes(Body)
        self.metadata[Key] = dict(Metadata or {})

    def get_object(self, Bucket, Key):
        self._maybe_fail("get", "GetObject")
        return {"Body": io.BytesIO(self.objects[Key] + (b"x" if self.corrupt else b""))}

    def head_object(self, Bucket, Key):
        self._maybe_fail("stat", "HeadObject")
        return {"ContentLength": len(self.objects[Key])}

    def delete_object(self, *a, **k):
        raise AssertionError("Mercury's key cannot delete (M-2): nothing may call a delete")

    delete_objects = delete_object


def _install(monkeypatch, server):
    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=server.client))
    monkeypatch.setitem(sys.modules, "botocore", types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, "botocore.config",
                        types.SimpleNamespace(Config=lambda **kw: dict(kw)))


@pytest.fixture
def server(monkeypatch):
    s = Server()
    _install(monkeypatch, s)
    monkeypatch.setattr("modules.integrations.base.get_setting",
                        lambda key, default=None: VALUES.get(key, default))
    monkeypatch.setattr("modules.integrations.base.get_secret", lambda key, default="": "k")
    return s


class TestTheOneClient:
    def test_it_is_built_from_the_settings_with_tls_as_set(self, server):
        S3.archive().client()
        b = server.built
        assert b["service"] == "s3" and b["endpoint_url"] == "https://192.0.2.5:9000"
        assert b["verify"] is True and b["region_name"] == "us-east-1"
        assert b["config"] == {"signature_version": "s3v4", "s3": {"addressing_style": "path"}}

    def test_verification_off_reaches_the_client(self, server, monkeypatch):
        """C355: the setting changed nothing before; now it is the client's `verify`."""
        monkeypatch.setitem(VALUES, "s3_verify_tls", False)
        S3.archive().client()
        assert server.built["verify"] is False

    def test_three_ways_to_have_no_client_are_three_answers(self, server, monkeypatch):
        monkeypatch.setitem(VALUES, "s3_bucket", "")
        with pytest.raises(S3.Unavailable, match="not configured"):
            S3.archive().client()
        monkeypatch.setitem(VALUES, "s3_bucket", "mercury")
        monkeypatch.setitem(sys.modules, "boto3", None)
        with pytest.raises(S3.Unavailable, match="boto3 is not installed"):
            S3.archive().client()

    def test_keys_sit_under_the_prefix(self, server, monkeypatch):
        monkeypatch.setitem(VALUES, "s3_prefix", "/lab/")
        assert S3.archive().key("goldens", "default", "r1", "x.cfg") == \
            "lab/goldens/default/r1/x.cfg"


class TestTheTest:
    def test_four_steps_pass_and_the_probe_is_overwritten_never_deleted(self, server):
        got = S3.archive().test_connection()
        assert got["ok"] is True, got
        assert [s["name"] for s in got["steps"]] == list(S3.TEST_STEPS)
        assert server.calls == ["bucket", "put", "get", "stat"]
        assert list(server.objects) == [S3.PROBE]
        assert "wrote, read back and stated" in got["message"]

    @pytest.mark.parametrize("step,op", [("bucket", "HeadBucket"), ("put", "PutObject"),
                                         ("get", "GetObject"), ("stat", "HeadObject")])
    def test_the_first_failing_step_is_named_with_the_servers_answer(self, server, step, op):
        server.fail = step
        got = S3.archive().test_connection()
        assert got["ok"] is False
        assert got["error"] == (f"{step} failed: ClientError: An error occurred (AccessDenied) "
                                f"when calling the {op} operation")
        assert [s["name"] for s in got["steps"]][-1] == step, "the rest are not tried"

    def test_a_missing_bucket_and_a_changed_probe_are_failures(self, server):
        server.exists = False
        assert S3.archive().test_connection()["error"] == \
            "bucket failed: bucket 'mercury' does not exist"
        server.exists, server.corrupt = True, True
        got = S3.archive().test_connection()
        assert got["error"].startswith("get failed: read back ")

    def test_the_readers_status_writes_nothing(self, server):
        """The integrations reader asks `status()` every minute: a read writes nothing, so it
        asks only whether the bucket answers."""
        st = S3.archive().status()
        assert st["state"] == "up" and server.calls == ["bucket"] and server.objects == {}
        server.exists = False
        assert S3.archive().status()["state"] == "down"

    def test_no_client_library_is_said_not_raised(self, server, monkeypatch):
        monkeypatch.setitem(sys.modules, "boto3", None)
        got = S3.archive().test_connection()
        assert got == {"ok": False, "steps": [], "error": (
            "Not usable: boto3 is not installed on this host (Ubuntu's python3-boto3: "
            "docs/NSOT_PHASE4_MINIO.md section 4)")}


def test_the_answers_past_retention_use_the_one_client(server, monkeypatch):
    from modules.nsot import reads
    monkeypatch.setattr("modules.list_settings.value",
                        lambda list_name, key, default=None: VALUES.get(key, default))
    monkeypatch.setattr("modules.list_settings.secret", lambda list_name, key: "k")
    put, why = reads._s3_put("Lab")
    assert why == "" and put is not None
    put("reads/Lab/run-1.json", b"{}")
    assert server.objects == {"reads/Lab/run-1.json": b"{}"}
    assert server.built["verify"] is True


def _tarball(members: dict) -> bytes:
    import tarfile
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class TestAnArchiveLeavesTheHostOnlyMasked:
    """C743 (2026-10-13): the archive steps scanned the copy AFTER it was uploaded, so a failing
    archive was already in the bucket; and the scan read every typed secret line already masked
    as a value. Now the one path scans first and refuses by member name."""

    MASKED = {"log.txt": b"username admin secret 9 <redacted:user_password>\n"
                         b"snmp-server host 192.0.2.1 version 2c <redacted:snmp_community>\n",
              "store.json.sealed": b"gAAAAABexampletoken=="}

    def test_a_masked_archive_is_written_read_back_and_scanned_again(self, server):
        body = _tarball(self.MASKED)
        r = S3.S3ArchiveIntegration().put_archive("archives/x/1.tar.gz", body,
                                                  metadata={"source": "test"})
        assert server.objects["archives/x/1.tar.gz"] == body
        assert r["sha256"] == r["read_back"] and r["unmasked_after"] == 0
        assert server.metadata["archives/x/1.tar.gz"] == {"source": "test",
                                                          "sha256": r["sha256"]}

    def test_a_value_masking_would_change_is_refused_before_any_write(self, server):
        body = _tarball(dict(self.MASKED, **{"notes.txt": b"enable secret 5 $1$ab$cdefgh\n"}))
        with pytest.raises(S3.Refused) as got:
            S3.S3ArchiveIntegration().put_archive("archives/x/2.tar.gz", body)
        assert got.value.members == ["notes.txt"]
        assert "$1$ab$cdefgh" not in str(got.value)
        assert server.objects == {} and "put" not in server.calls

    def test_a_member_that_is_not_text_is_refused(self, server):
        body = _tarball(dict(self.MASKED, **{"blob.bin": b"\xff\xfe\x00"}))
        with pytest.raises(S3.Refused) as got:
            S3.S3ArchiveIntegration().put_archive("archives/x/3.tar.gz", body)
        assert got.value.members == ["blob.bin"]


# --- C730: a golden leaves the host masked ----------------------------------------------------

#: The values planted in a golden: two communities (a `community` line and a trap host's), a
#: type-9 hash on `enable secret` and on a user, and a value the installation holds (the value
#: rule), on a line no position names.
COMMUNITY_RO = "PlantedRo7"
COMMUNITY_TRAP = "PlantedTrap8"
TYPE9 = "$9$nhEmQVczB7dqsO$X.HsgL6x1il0RxkOSSvyQYwucySCt7qFm4v7pqCxkKM"
USER9 = "$9$5k9uTmZgpUIg2E$Pl4nTedUserHashAAAAAAAAAAAAAAAAAAAAAAAAAAA"
HELD = "HeldSecretValue42"
PLANTED_GOLDEN = (
    "hostname r1\n"
    f"enable secret 9 {TYPE9}\n"
    f"username admin privilege 15 secret 9 {USER9}\n"
    "interface GigabitEthernet1\n"
    f" description uplink {HELD}\n"
    f"snmp-server community {COMMUNITY_RO} RO\n"
    f"snmp-server host 192.0.2.9 version 2c {COMMUNITY_TRAP}\n"
    "end\n")
#: C745's shapes, which masking does not know: an OSPF MD5 key, a BGP neighbour's password and
#: an SNMPv3 user's keys. NOT masked in the archive, as on every other outbound path.
C745_VALUES = ("OspfPlantedKey1", "BgpPlantedPw2", "V3AuthPlanted3", "V3PrivPlanted4")
C745_GOLDEN = (
    "interface GigabitEthernet2\n"
    f" ip ospf message-digest-key 1 md5 {C745_VALUES[0]}\n"
    "router bgp 65001\n"
    f" neighbor 192.0.2.7 password {C745_VALUES[1]}\n"
    f"snmp-server user mon grp v3 auth sha {C745_VALUES[2]} priv aes 128 {C745_VALUES[3]}\n")


def _git(repo, *args):
    import os
    import subprocess
    out = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                         env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@l",
                                  GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@l"))
    assert out.returncode == 0, f"git {args}: {out.stderr}"
    return out.stdout.strip()


@pytest.fixture
def hook(server, monkeypatch, tmp_path):
    """The real post-commit hook over a real repository, the S3 client stood in: commit
    ``{device: golden text}`` and run the hook on that commit; ``(result, server)``."""
    import os

    from modules.nsot import archive

    monkeypatch.setattr("modules.list_settings.value",
                        lambda list_name, key, default=None: VALUES.get(key, default))
    monkeypatch.setattr("modules.list_settings.secret", lambda list_name, key: "k")
    monkeypatch.setattr("modules.redact.known_secret_values",
                        lambda: {HELD: "snmp_community_ro"})
    repo = str(tmp_path / "config_repo")
    os.makedirs(os.path.join(repo, "golden"))
    _git(repo, "init", "-q", "-b", "main")

    def run(goldens: dict):
        for device, text in goldens.items():
            with open(os.path.join(repo, "golden", f"{device}.cfg"), "wb") as fh:
                fh.write(text if isinstance(text, bytes) else text.encode("utf-8"))
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "goldens")
        sha = _git(repo, "rev-parse", "HEAD")
        return archive.s3_archive_hook({"repo": repo, "sha": sha, "devices": list(goldens),
                                        "tags": ["baseline/20261015T120000Z"], "source": "t",
                                        "actor": "t", "list_name": "Lab"}), server
    return run


class TestAGoldenLeavesTheHostMasked:
    """C730 (the operator's decision D6, 2026-10-15): the archive held each golden's
    communities and type-9 hashes verbatim. Every golden now reaches the bucket masked by
    `redact_text`, its key and metadata naming the masking."""

    def test_a_planted_community_and_type9_hash_reach_the_archive_masked(self, hook):
        got, srv = hook({"r1": PLANTED_GOLDEN})
        assert got == {"ok": True, "message": "archived 1 config(s), masked"}, got
        (key, body), = srv.objects.items()
        assert key == "goldens/lab/r1/20261015T120000Z.masked.cfg"
        text = body.decode("utf-8")
        for value in (COMMUNITY_RO, COMMUNITY_TRAP, TYPE9, USER9, HELD):
            assert value not in text, f"{value[:6]}… reached the archive"
        assert "enable secret 9 <redacted:enable_secret>\n" in text
        assert "username admin privilege 15 secret 9 <redacted:user_password>\n" in text
        assert "snmp-server community <redacted:snmp_community> RO\n" in text
        assert "snmp-server host 192.0.2.9 version 2c <redacted:snmp_community>\n" in text
        assert " description uplink <redacted:snmp_community_ro>\n" in text, "the value rule"
        assert text.startswith("hostname r1\n") and text.endswith("end\n"), "the rest kept"
        assert srv.metadata[key].get("masking") == "redact_text", srv.metadata[key]
        assert srv.metadata[key]["commit"], "the commit still named"

    def test_what_the_archive_holds_masking_would_not_change(self, hook):
        """The check a reader (the census) makes is the writer's own: masked again, unchanged."""
        from modules import redact
        _got, srv = hook({"r1": PLANTED_GOLDEN})
        (body,) = srv.objects.values()
        text = body.decode("utf-8")
        assert redact.redact_text(text) == text

    def test_a_golden_masking_cannot_finish_is_not_written(self, hook, monkeypatch):
        """A masking that a second pass still changes (C743's defect) is refused by device, and
        nothing of that golden is written; the others are."""
        from modules import redact
        real = redact.redact_text
        monkeypatch.setattr("modules.redact.redact_text",
                            lambda text, values=None: real(text, values) + "#")
        got, srv = hook({"r1": PLANTED_GOLDEN})
        assert got["ok"] is False
        assert got["error"] == ("r1: masking it a second time still changed it, so the first "
                                "pass is not shown complete (C743)")
        assert srv.objects == {}

    def test_a_golden_that_is_not_text_is_not_written(self, hook):
        got, srv = hook({"r1": PLANTED_GOLDEN, "r2": b"hostname r2\n\xff\xfe\n"})
        assert got == {"ok": False, "error": "r2: not UTF-8 text (byte 12), so it cannot be "
                                             "shown masked"}
        assert list(srv.objects) == ["goldens/lab/r1/20261015T120000Z.masked.cfg"]

    def test_known_gap_c745_shapes_masking_does_not_know_reach_the_archive_unmasked(self, hook):
        """KNOWN GAP, C745 (open): masking does not know an OSPF MD5 key, a BGP neighbour's
        password or an SNMPv3 user's keys, so the archive holds them as every other outbound
        path does. Measured: none appears in the fleet's captured fixtures. When C745 adds a
        shape to `redact._POSITIONAL`, this test fails for it: move that value to the test
        above."""
        _got, srv = hook({"r1": C745_GOLDEN})
        (body,) = srv.objects.values()
        text = body.decode("utf-8")
        assert [v for v in C745_VALUES if v in text] == list(C745_VALUES), \
            "a C745 shape is masked now: move it to the masked test and close that part of C745"


class TestOneWritePath:
    """An unmasked golden write is impossible by construction: `put` refuses a key under
    goldens/, `put_golden` has no unmasked form, and `_put_object`, the one call that writes,
    is called only by those two."""

    @pytest.mark.parametrize("prefix,key", [
        ("", "goldens/lab/r1/x.cfg"), ("", "/goldens/lab/r1/x.cfg"), ("", "goldens"),
        ("lab", "lab/goldens/default/s1/abc.cfg"), ("lab", "goldens/default/s1/abc.cfg")])
    def test_put_refuses_a_key_under_goldens(self, server, monkeypatch, prefix, key):
        monkeypatch.setitem(VALUES, "s3_prefix", prefix)
        with pytest.raises(ValueError, match="where a golden is written only masked"):
            S3.archive().put(key, PLANTED_GOLDEN.encode("utf-8"))
        assert server.objects == {} and "put" not in server.calls

    def test_put_still_writes_elsewhere(self, server):
        S3.archive().put("reads/Lab/run-1.json", b"{}")
        S3.archive().put("goldensmith/x", b"x")
        assert set(server.objects) == {"reads/Lab/run-1.json", "goldensmith/x"}

    def test_put_golden_masks_and_names_its_masking_whatever_metadata_it_is_given(self, server,
                                                                                   monkeypatch):
        monkeypatch.setattr("modules.redact.known_secret_values", lambda: {})
        key = S3.archive().put_golden("lab", "r1", "s", PLANTED_GOLDEN.encode("utf-8"),
                                      metadata={"masking": "none"})
        assert key == "goldens/lab/r1/s.masked.cfg"
        assert COMMUNITY_RO.encode() not in server.objects[key]
        assert server.metadata[key] == {"masking": "redact_text"}

    @staticmethod
    def _writers(files) -> dict:
        """``{"<file>:<function>": [what it calls]}`` for every call of `put_object` or
        `_put_object` in *files*, by parsing (never a substring of prose)."""
        import ast
        import os

        from tests.source_index import ROOT, tree
        out = {}
        for path in files:
            for fn in ast.walk(tree(path)):
                if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for n in ast.walk(fn):
                    if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                            and n.func.attr in ("put_object", "_put_object")):
                        name = f"{os.path.relpath(path, ROOT)}:{fn.name}"
                        out.setdefault(name, []).append(n.func.attr)
        return out

    def test_the_one_call_that_writes_is_reached_only_through_put_and_put_golden(self):
        from tests.source_index import tracked
        files = tracked("app.py", "modules", "routes", "scripts", "lab", suffix=".py")
        assert len(files) >= 200, f"the population shrank: {len(files)}"
        assert self._writers(files) == {
            "modules/integrations/s3_archive.py:_put_object": ["put_object"],
            "modules/integrations/s3_archive.py:put": ["_put_object"],
            "modules/integrations/s3_archive.py:put_golden": ["_put_object"],
        }

    def test_the_scan_finds_a_planted_second_writer(self, tmp_path):
        planted = tmp_path / "hook.py"
        planted.write_text("def upload(c, key, data):\n"
                           "    c.put_object(Bucket='b', Key=key, Body=data)\n", encoding="utf-8")
        assert list(self._writers([str(planted)]).values()) == [["put_object"]]

    def test_no_host_step_writes_around_the_one_path(self):
        """The host steps' own Python (in their heredocs, which no parse reaches) writes through
        the integration (`put_archive`, which reaches `put`); the one direct `put_object` is
        minio-root-rotate.sh's probe of a new key, at a `_probe/` key."""
        import os
        import re

        from tests.source_index import tracked
        steps = tracked("scripts/host-steps", suffix=".sh")
        assert len(steps) >= 30, len(steps)
        direct = {os.path.basename(p): re.findall(r"\.put_object\(", open(p, encoding="utf-8")
                                                  .read()) for p in steps}
        assert {k: len(v) for k, v in direct.items() if v} == {"minio-root-rotate.sh": 1}


class Census:
    """A versioned bucket as boto3's client sees it: ``{key: [(version_id, body, latest)]}``;
    a version whose body is None is refused (a key without the version-read right)."""

    def __init__(self, objects):
        self.objects, self.reads = objects, []

    def get_paginator(self, name):
        assert name == "list_object_versions"
        srv = self

        class _P:
            def paginate(self, Bucket, Prefix):
                yield {"Versions": [{"Key": k, "VersionId": vid, "IsLatest": latest}
                                    for k, vs in srv.objects.items() if k.startswith(Prefix)
                                    for vid, _b, latest in vs]}
        return _P()

    def get_object(self, Bucket, Key, VersionId=None):
        self.reads.append((Key, VersionId))
        for vid, body, latest in self.objects[Key]:
            if (VersionId is None and latest) or vid == VersionId:
                if body is None:
                    raise ClientError("AccessDenied", "GetObject")
                return {"Body": io.BytesIO(body)}
        raise AssertionError((Key, VersionId))


class TestTheCensus:
    """The operator's measurement (`c730-golden-archive-census.sh`): read-only, counts and
    keys, never a value."""

    def test_it_counts_each_kind_and_names_no_value(self, server, monkeypatch):
        monkeypatch.setattr("modules.redact.known_secret_values", lambda: {})
        masked = S3.masked_golden(PLANTED_GOLDEN.encode("utf-8"))
        bucket = Census({
            "goldens/lab/r1/aaa.cfg": [("v2", PLANTED_GOLDEN.encode(), True),
                                       ("v1", PLANTED_GOLDEN.encode(), False)],
            "goldens/lab/r2/bbb.cfg": [("v1", b"hostname r2\n", True)],
            "goldens/lab/r1/ccc.masked.cfg": [("v1", masked, True)],
            "goldens/lab/r3/ddd.masked.cfg": [("v1", PLANTED_GOLDEN.encode(), True)],
            "goldens/lab/r4/eee.cfg": [("v1", b"\xff\xfe", True), ("v0", None, False)],
            "reads/Lab/run.json": [("v1", PLANTED_GOLDEN.encode(), True)],
        })
        got = S3.archive().golden_census(client=bucket)
        assert got == {"versions": 7, "current": 5, "marked": 2,
                       "unmasked": {"goldens/lab/r1": 2},
                       "marked_unmasked": ["goldens/lab/r3/ddd.masked.cfg"],
                       "not_text": ["goldens/lab/r4/eee.cfg"],
                       "unreadable": ["goldens/lab/r4/eee.cfg (ClientError)"]}
        assert ("goldens/lab/r1/aaa.cfg", None) in bucket.reads, "the latest read as the object"
        assert ("goldens/lab/r1/aaa.cfg", "v1") in bucket.reads, "an older one by its version"
        assert not any(k.startswith("reads/") for k, _v in bucket.reads), "goldens/ only"
        assert COMMUNITY_RO not in repr(got) and TYPE9 not in repr(got)
