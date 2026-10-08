"""Mercury's connection to MinIO (Phase 4 step 1; docs/NSOT_PHASE4_MINIO.md, approved by the
operator 2026-10-08): one client, TLS verification as set (C355), and a Test of the four things
every use needs.

The minio SDK is not installed where CI runs (requirements.lock leaves it out until the host
step), so its client is stood in for at the import (`sys.modules["minio"]`), recording how it
was built and what it was asked; Mercury's own code runs for real.
"""

import io
import sys
import types

import pytest

from modules.integrations import s3_archive as S3

VALUES = {"s3_endpoint": "https://192.0.2.5:9000", "s3_bucket": "mercury",
          "s3_prefix": "", "s3_region": "", "s3_verify_tls": True}


class Server:
    """minio's client as a fake server: a bucket, the objects written, and every call made."""

    def __init__(self, exists=True, corrupt=False, fail=""):
        self.exists, self.corrupt, self.fail = exists, corrupt, fail
        self.objects, self.calls, self.built = {}, [], {}

    def __call__(self, host, **kw):
        self.built = dict(kw, host=host)
        return self

    def _maybe_fail(self, name):
        self.calls.append(name)
        if self.fail == name:
            raise OSError(f"S3 error: AccessDenied on {name}")

    def bucket_exists(self, bucket):
        self._maybe_fail("bucket")
        return self.exists

    def put_object(self, bucket, key, data, length, metadata=None):
        self._maybe_fail("put")
        self.objects[key] = data.read()

    def get_object(self, bucket, key):
        self._maybe_fail("get")
        body = self.objects[key] + (b"x" if self.corrupt else b"")
        r = io.BytesIO(body)
        r.release_conn = lambda: None
        return r

    def stat_object(self, bucket, key):
        self._maybe_fail("stat")
        return types.SimpleNamespace(size=len(self.objects[key]))

    def remove_object(self, *a, **k):
        raise AssertionError("Mercury's key cannot delete (M-2): nothing may call remove")


@pytest.fixture
def server(monkeypatch):
    s = Server()
    monkeypatch.setitem(sys.modules, "minio", types.SimpleNamespace(Minio=s))
    monkeypatch.setattr("modules.integrations.base.get_setting",
                        lambda key, default=None: VALUES.get(key, default))
    monkeypatch.setattr("modules.integrations.base.get_secret", lambda key, default="": "k")
    return s


class TestTheOneClient:
    def test_it_is_built_from_the_settings_with_tls_as_set(self, server):
        S3.archive().client()
        assert server.built["host"] == "192.0.2.5:9000" and server.built["secure"] is True
        assert server.built["cert_check"] is True

    def test_verification_off_reaches_the_client(self, server, monkeypatch):
        """C355: the setting changed nothing before; now it is the client's cert_check."""
        monkeypatch.setitem(VALUES, "s3_verify_tls", False)
        S3.archive().client()
        assert server.built["cert_check"] is False

    def test_three_ways_to_have_no_client_are_three_answers(self, server, monkeypatch):
        monkeypatch.setitem(VALUES, "s3_bucket", "")
        with pytest.raises(S3.Unavailable, match="not configured"):
            S3.archive().client()
        monkeypatch.setitem(VALUES, "s3_bucket", "mercury")
        monkeypatch.setitem(sys.modules, "minio", None)
        with pytest.raises(S3.Unavailable, match="minio SDK is not installed"):
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

    @pytest.mark.parametrize("step", ["bucket", "put", "get", "stat"])
    def test_the_first_failing_step_is_named_with_the_servers_answer(self, server, step):
        server.fail = step
        got = S3.archive().test_connection()
        assert got["ok"] is False
        assert got["error"] == f"{step} failed: OSError: S3 error: AccessDenied on {step}"
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

    def test_no_sdk_is_said_not_raised(self, server, monkeypatch):
        monkeypatch.setitem(sys.modules, "minio", None)
        got = S3.archive().test_connection()
        assert got == {"ok": False, "steps": [], "error": (
            "Not usable: the minio SDK is not installed on this host (its host step installs "
            "it: docs/NSOT_PHASE4_MINIO.md section 4)")}


def test_the_answers_past_retention_use_the_one_client(server, monkeypatch):
    from modules.nsot import reads
    monkeypatch.setattr("modules.list_settings.value",
                        lambda list_name, key, default=None: VALUES.get(key, default))
    monkeypatch.setattr("modules.list_settings.secret", lambda list_name, key: "k")
    put, why = reads._s3_put("Lab")
    assert why == "" and put is not None
    put("reads/Lab/run-1.json", b"{}")
    assert server.objects == {"reads/Lab/run-1.json": b"{}"}
    assert server.built["cert_check"] is True
