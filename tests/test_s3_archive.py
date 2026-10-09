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
