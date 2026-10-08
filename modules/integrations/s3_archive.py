"""S3-compatible archive integration: Mercury's connection to MinIO (Phase 4 step 1,
docs/NSOT_PHASE4_MINIO.md, approved by the operator 2026-10-08).

Targets any S3-compatible endpoint (MinIO, AWS S3, …). ONE client for every use (M-5: the
`s3_*` settings, the installation's value inherited by every network): the golden archive's
post-commit hook, the Show commands answers past retention (`reads.expire`), the Test, and the
installation's own uses to come (the Oxidized bundle, the record dumps). Before this, three
places built a client their own way and none passed `s3_verify_tls` (C355).

Mercury's key can list, read and write its bucket and never delete (M-2): nothing here calls a
delete, and the Test's probe is overwritten in place. The ``minio`` SDK is optional (absent from
requirements.lock until the host step installs it); an absent SDK, an unset endpoint and an
unreachable server are three different answers, each named, never a raise into a request.
"""

import io
import logging
import time

from modules.integrations.base import IntegrationClient

log = logging.getLogger(__name__)

#: Where the Test writes its probe, under the network's prefix: overwritten each time, never
#: deleted (Mercury's key cannot delete, M-2).
PROBE = "_probe/mercury-connection-test"
#: The Test's steps, in order, as the manual and the Settings card name them.
TEST_STEPS = ("bucket", "put", "get", "stat")


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
        try:
            from minio import Minio
        except ImportError:
            raise Unavailable("the minio SDK is not installed on this host (its host step "
                              "installs it: docs/NSOT_PHASE4_MINIO.md section 4)") from None
        endpoint = self.url
        return Minio(endpoint.split("://", 1)[-1],
                     access_key=self._secret("s3_access_key"),
                     secret_key=self._secret("s3_secret_key"),
                     secure=endpoint.startswith("https://"),
                     region=self._setting("s3_region", "") or None,
                     cert_check=self.verify_tls)

    def put(self, key: str, data: bytes, metadata: dict = None, client=None) -> None:
        """Write *data* at *key* (already under the prefix: `key()`). Raises on failure."""
        (client or self.client()).put_object(self.bucket, key, io.BytesIO(data), len(data),
                                             metadata=metadata or None)

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

        def _get():
            r = client.get_object(bucket, key)
            try:
                got = r.read()
            finally:
                r.close()
                r.release_conn()
            return got == data, (f"read back {len(got)} bytes, not the {len(data)} written"
                                 if got != data else "")

        def _stat():
            st = client.stat_object(bucket, key)
            return st.size == len(data), f"the probe's size is {st.size}, not {len(data)}"

        passed = step("bucket", lambda: (bool(client.bucket_exists(bucket)),
                                        f"bucket '{bucket}' does not exist"),
                      f"bucket '{bucket}' answers")
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
