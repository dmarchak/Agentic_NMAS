"""S3-compatible archive integration: Mercury's connection to MinIO (Phase 4 step 1,
docs/NSOT_PHASE4_MINIO.md, approved by the operator 2026-10-08).

Targets any S3-compatible endpoint (MinIO, AWS S3, …). ONE client for every use (M-5: the
`s3_*` settings, the installation's value inherited by every network): the golden archive's
post-commit hook, the Show commands answers past retention (`reads.expire`), the Test, and the
installation's own uses to come (the Oxidized bundle, the record dumps). Before this, three
places built a client their own way and none passed `s3_verify_tls` (C355).

Mercury's key can list, read and write its bucket and never delete (M-2): nothing here calls a
delete, and the Test's probe is overwritten in place.

**The library is boto3** (the operator's decision, 2026-10-08): the host runs Ubuntu's system
Python, externally managed, where Ubuntu ships no minio package and `python3-boto3` 1.34.46 is
already installed from apt. Pinned at the host's version through the lock: newer boto3 sends
default checksum headers some MinIO releases reject, and the Test's put and get catch that if
the version moves. An absent library, an unset endpoint and an unreachable server are three
different answers, each named, never a raise into a request.
"""

import logging
import time

from modules.integrations.base import IntegrationClient

log = logging.getLogger(__name__)

#: Where the Test writes its probe, under the network's prefix: overwritten each time, never
#: deleted (Mercury's key cannot delete, M-2).
PROBE = "_probe/mercury-connection-test"
#: The Test's steps, in order, as the manual and the Settings card name them.
TEST_STEPS = ("bucket", "put", "get", "stat")
#: The client library's loggers. At DEBUG botocore logs every request's headers, the
#: `Authorization` header naming the access key among them (C594: CI #537, when the lock first
#: installed boto3), so they are held at WARNING whatever the app's level: Mercury masks a
#: credential on every handler, and a library's debug output is not a place it can.
QUIET_LOGGERS = ("boto3", "botocore", "s3transfer")


class Unavailable(RuntimeError):
    """No client could be built; the message says which of the three reasons."""


class S3ArchiveIntegration(IntegrationClient):
    name = "s3"
    label = "S3 archive"
    url_key = "s3_endpoint"
    secret_keys = ("s3_access_key", "s3_secret_key")
    plain_keys = ("s3_bucket", "s3_region", "s3_prefix", "s3_verify_tls")

    def is_configured(self) -> bool:
        return bool(self.url and self._setting("s3_bucket", ""))

    @property
    def bucket(self) -> str:
        return self._setting("s3_bucket", "") or ""

    def key(self, *parts: str) -> str:
        """An object key under the configured prefix."""
        prefix = (self._setting("s3_prefix", "") or "").strip("/")
        return "/".join(p.strip("/") for p in (prefix, *parts) if p and p.strip("/"))

    def client(self):
        """The one client: endpoint, credentials from the secrets backend, region, and TLS
        verification as set (C355). Raises `Unavailable` naming why none can be built."""
        if not self.is_configured():
            raise Unavailable("not configured: set its endpoint and bucket in Settings "
                              "(Integrations, S3 archive)")
        for name in QUIET_LOGGERS:
            if logging.getLogger(name).getEffectiveLevel() < logging.WARNING:
                logging.getLogger(name).setLevel(logging.WARNING)
        try:
            import boto3
            from botocore.config import Config
        except ImportError:
            raise Unavailable("boto3 is not installed on this host (Ubuntu's python3-boto3: "
                              "docs/NSOT_PHASE4_MINIO.md section 4)") from None
        return boto3.client(
            "s3", endpoint_url=self.url,
            aws_access_key_id=self._secret("s3_access_key"),
            aws_secret_access_key=self._secret("s3_secret_key"),
            region_name=self._setting("s3_region", "") or "us-east-1",
            verify=self.verify_tls,
            # MinIO serves buckets by path, never as a host name.
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}))

    def put(self, key: str, data: bytes, metadata: dict = None, client=None) -> None:
        """Write *data* at *key* (already under the prefix: `key()`). *metadata* names its
        fields without boto3's ``x-amz-meta-`` prefix. Raises on failure."""
        (client or self.client()).put_object(Bucket=self.bucket, Key=key, Body=data,
                                             Metadata=dict(metadata or {}))

    def status(self) -> dict:
        """The status bar's and the integrations reader's answer, every cycle: whether the
        bucket answers, and nothing written. A read writes nothing (CLAUDE.md), and the reader
        runs every minute: the write steps would leave 1,440 versions a day of the probe in a
        versioned bucket. The four-step Test is a person's (`test_connection`)."""
        if not self.is_configured():
            return super().status()
        result = self.test_connection(write=False)
        return {"ok": True, "state": "up" if result.get("ok") else "down", "label": self.label,
                "message": result.get("error") or result.get("message", "Connected")}

    def test_connection(self, write: bool = True) -> dict:
        """The four things every use needs, in order (NSOT_PHASE4_MINIO section 3): the bucket
        answers, a probe is written, read back byte for byte, and its size stated. ``{"ok",
        "steps": [{"name", "ok", "detail"}], "error" | "message"}``; the first step that fails
        is named with what the server answered, and the rest are not tried. With *write*
        false (the reader's, `status`), the bucket step only."""
        try:
            client = self.client()
        except Unavailable as exc:
            return {"ok": False, "error": f"Not usable: {exc}", "steps": []}
        except Exception as exc:                      # noqa: BLE001 (a bad endpoint, said)
            return {"ok": False, "error": f"No client: {type(exc).__name__}: {exc}",
                    "steps": []}
        bucket, key = self.bucket, self.key(PROBE)
        data = f"Mercury's connection test, {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}"\
            .encode("utf-8")
        steps = []

        def step(name, fn, ok_words):
            try:
                ok, detail = fn()
            except Exception as exc:                  # noqa: BLE001 (the server's answer, said)
                ok, detail = False, f"{type(exc).__name__}: {exc}"
            steps.append({"name": name, "ok": ok, "detail": detail if not ok else ok_words})
            return ok

        def _bucket():
            try:
                client.head_bucket(Bucket=bucket)
            except Exception as exc:                  # noqa: BLE001 (a missing bucket, said)
                code = str(((getattr(exc, "response", None) or {}).get("Error") or {})
                           .get("Code", ""))
                if code in ("404", "NoSuchBucket", "NotFound"):
                    return False, f"bucket '{bucket}' does not exist"
                raise
            return True, ""

        def _get():
            body = client.get_object(Bucket=bucket, Key=key)["Body"]
            try:
                got = body.read()
            finally:
                body.close()
            return got == data, (f"read back {len(got)} bytes, not the {len(data)} written"
                                 if got != data else "")

        def _stat():
            size = client.head_object(Bucket=bucket, Key=key)["ContentLength"]
            return size == len(data), f"the probe's size is {size}, not {len(data)}"

        passed = step("bucket", _bucket, f"bucket '{bucket}' answers")
        if passed and not write:
            return {"ok": True, "steps": steps,
                    "message": f"Bucket '{bucket}' answers (the full Test is Settings' Test)"}
        passed = (passed
                  and step("put", lambda: (self.put(key, data, client=client) or True, ""),
                           f"wrote {key}")
                  and step("get", _get, "read it back, byte for byte")
                  and step("stat", _stat, f"{len(data)} bytes, as written"))
        if passed:
            return {"ok": True, "steps": steps,
                    "message": f"Bucket '{bucket}' reachable: wrote, read back and stated {key}"}
        bad = steps[-1]
        return {"ok": False, "steps": steps, "error": f"{bad['name']} failed: {bad['detail']}"}


def archive(list_name: str = "") -> S3ArchiveIntegration:
    """The archive FOR *list_name* (its settings inherit the installation's), or the
    installation's own when none is given."""
    return S3ArchiveIntegration(list_name=list_name)
