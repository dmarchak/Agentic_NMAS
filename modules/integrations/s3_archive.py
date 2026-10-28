"""S3-compatible archive integration: Mercury's connection to MinIO (Phase 4 step 1,
docs/NSOT_PHASE4_MINIO.md, approved by the operator 2026-10-08).

Targets any S3-compatible endpoint (MinIO, AWS S3, …). ONE client for every use (M-5: the
`s3_*` settings, the installation's value inherited by every network): the golden archive's
post-commit hook, the Show commands answers past retention (`reads.expire`), the Test, and the
installation's own uses to come (the Oxidized bundle, the record dumps). Before this, three
places built a client their own way and none passed `s3_verify_tls` (C355).

Mercury's key can list, read and write its bucket and never delete (M-2): nothing here calls a
delete, and the Test's probe is overwritten in place.

Nothing leaves the host unmasked (C730, C743): a golden only through `put_golden`, which masks
it and names the masking on the object; a removed family's archive only through `put_archive`,
which refuses one masking would still change. `put` refuses a key under ``goldens/``.

**The library is boto3** (the operator's decision, 2026-10-08): the host runs Ubuntu's system
Python, externally managed, where Ubuntu ships no minio package and `python3-boto3` 1.34.46 is
already installed from apt. Pinned at the host's version through the lock: newer boto3 sends
default checksum headers some MinIO releases reject, and the Test's put and get catch that if
the version moves. An absent library, an unset endpoint and an unreachable server are three
different answers, each named, never a raise into a request.
"""

import hashlib
import io
import logging
import tarfile
import time

from modules import redact
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


#: Where each golden's archive copy is written, under the prefix:
#: ``goldens/<network>/<device>/<stamp>.masked.cfg`` (NSOT_PHASE4_MINIO, M-1).
GOLDENS = "goldens"
#: C730 (the operator's decision D6, 2026-10-15): a golden leaves the host MASKED, as on every
#: outbound path. The repository keeps it verbatim (masking is outbound: docs/SECRETS.md); the
#: archive held each device's communities and type-9 hashes verbatim until then. The marker is
#: in the key, so a listing tells a masked copy from one written before (`<stamp>.cfg`), and in
#: the object's metadata (`masking`), so a read of one object does too.
GOLDEN_SUFFIX = ".masked.cfg"
GOLDEN_MASKING = "redact_text"


class Unavailable(RuntimeError):
    """No client could be built; the message says which of the three reasons."""


class Unmaskable(RuntimeError):
    """A golden was not archived: it could not be shown masked (the message says why, never a
    value)."""


def masked_golden(data: bytes, values: dict = None) -> bytes:
    """*data*, a golden's committed bytes, masked by the masking every outbound path uses
    (`redact.redact_text`: by position, and by every value this installation holds, resolved
    once). Raises `Unmaskable` for bytes that are not UTF-8 text (they cannot be shown masked)
    and for a result a second pass would still change: masking twice changes nothing (C743), so
    a change says the first pass is not complete. What masking does not know is not masked
    (a shape `redact._POSITIONAL` does not name): the archive is as masked as every other
    outbound path, no more."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Unmaskable(f"not UTF-8 text (byte {exc.start}), so it cannot be shown "
                         "masked") from None
    values = redact.known_secret_values() if values is None else values
    masked = redact.redact_text(text, values)
    if redact.redact_text(masked, values) != masked:
        raise Unmaskable("masking it a second time still changed it, so the first pass is "
                         "not shown complete (C743)")
    return masked.encode("utf-8")


class Refused(RuntimeError):
    """An archive was not written: *members* name what Mercury's masking would still change
    (names only, never a value)."""

    def __init__(self, members: list):
        self.members = list(members)
        super().__init__(f"{len(self.members)} member(s) hold a value Mercury would mask: "
                         + ", ".join(self.members))


def unmasked_members(body: bytes) -> list:
    """The members of the gzip tarball *body* that Mercury's masking would still change, by
    name, every member read (a sealed one is a token masking leaves alone). A member that is
    not UTF-8 text is named too: it cannot be shown to be masked. Sound only because masking
    twice changes nothing (C743): before that, every typed secret line already masked read as
    a value."""
    out = []
    with tarfile.open(fileobj=io.BytesIO(body), mode="r:gz") as tar:
        for m in tar.getmembers():
            if not m.isfile():
                continue
            try:
                text = tar.extractfile(m).read().decode("utf-8")
            except UnicodeDecodeError:
                out.append(m.name)
                continue
            if redact.redact_text(text) != text:
                out.append(m.name)
    return out


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

    def client(self, credentials: tuple = None):
        """The one client: endpoint, credentials from the secrets backend, region, and TLS
        verification as set (C355). Raises `Unavailable` naming why none can be built.
        *credentials* ``(access_key, secret_key)``: another key on the same endpoint, typed by
        the operator for what Mercury's own key may not do (a host step's delete, C743); never
        stored, and Mercury's code never passes it."""
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
            aws_access_key_id=credentials[0] if credentials else self._secret("s3_access_key"),
            aws_secret_access_key=(credentials[1] if credentials
                                   else self._secret("s3_secret_key")),
            region_name=self._setting("s3_region", "") or "us-east-1",
            verify=self.verify_tls,
            # MinIO serves buckets by path, never as a host name.
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}))

    def _put_object(self, key: str, data: bytes, metadata: dict, client=None) -> None:
        """The one call that writes an object; `put` and `put_golden` are its only callers
        (C730, tests/test_s3_archive.py)."""
        (client or self.client()).put_object(Bucket=self.bucket, Key=key, Body=data,
                                             Metadata=dict(metadata or {}))

    def put(self, key: str, data: bytes, metadata: dict = None, client=None) -> None:
        """Write *data* at *key* (already under the prefix: `key()`). *metadata* names its
        fields without boto3's ``x-amz-meta-`` prefix. Raises on failure. A key under
        ``goldens/`` is refused: a golden is written only masked, by `put_golden` (C730)."""
        bare = key.lstrip("/")
        # Under the prefix, or at the bucket's root whatever the prefix (a key built without it).
        for root in (self.key(GOLDENS), GOLDENS):
            if bare == root or bare.startswith(root + "/"):
                raise ValueError(f"refused: the key {key} is under {root}/, where a golden is "
                                 "written only masked, by put_golden (C730)")
        self._put_object(key, data, metadata, client)

    def put_golden(self, network: str, device: str, stamp: str, data: bytes,
                   metadata: dict = None, client=None) -> str:
        """Write a golden's committed bytes *data*, MASKED (`masked_golden`), at
        ``goldens/<network>/<device>/<stamp>.masked.cfg`` under the prefix, its metadata naming
        the masking (``masking: redact_text``); the key written. The one path a golden reaches
        the bucket by: there is no unmasked form of this call (C730). Raises `Unmaskable`
        before anything is written, or the server's error."""
        body = masked_golden(data)
        key = self.key(GOLDENS, network, device, f"{stamp}{GOLDEN_SUFFIX}")
        self._put_object(key, body, {**(metadata or {}), "masking": GOLDEN_MASKING}, client)
        return key

    def golden_census(self, client=None) -> dict:
        """Read-only: every version of every object under ``goldens/``, each read and asked
        whether Mercury's masking would still change it (C730's measurement, the operator's
        host step `c730-golden-archive-census.sh`). Counts and keys, never a value:
        ``{"versions", "current", "marked", "unmasked": {"<device folder>": n},
        "marked_unmasked": [key], "not_text": [key], "unreadable": [key (why)]}``. The latest
        version is read as the object (GetObject); an older one by its version id, which a key
        without that right is refused, and each refusal is named, never counted as masked."""
        c = client or self.client()
        root = self.key(GOLDENS) + "/"
        values = redact.known_secret_values()
        out = {"versions": 0, "current": 0, "marked": 0, "unmasked": {},
               "marked_unmasked": [], "not_text": [], "unreadable": []}
        for page in c.get_paginator("list_object_versions").paginate(Bucket=self.bucket,
                                                                     Prefix=root):
            for v in page.get("Versions") or []:
                key, latest = v["Key"], bool(v.get("IsLatest"))
                out["versions"] += 1
                out["current"] += latest
                marked = key.endswith(GOLDEN_SUFFIX)
                out["marked"] += marked
                try:
                    kw = {} if latest else {"VersionId": v.get("VersionId")}
                    body = c.get_object(Bucket=self.bucket, Key=key, **kw)["Body"].read()
                except Exception as exc:              # noqa: BLE001 (named, never masked)
                    out["unreadable"].append(f"{key} ({type(exc).__name__})")
                    continue
                try:
                    text = body.decode("utf-8")
                except UnicodeDecodeError:
                    out["not_text"].append(key)
                    continue
                if redact.redact_text(text, values) == text:
                    continue
                if marked:
                    out["marked_unmasked"].append(key)
                else:
                    folder = key.rsplit("/", 1)[0]
                    out["unmasked"][folder] = out["unmasked"].get(folder, 0) + 1
        return out

    def put_archive(self, key: str, body: bytes, metadata: dict = None) -> dict:
        """Write the masked tarball *body* at *key*, the one path a removed family's archive
        leaves the host by (C743): it is scanned BEFORE anything is written, and `Refused`
        names the members masking would still change, so a failing archive never reaches the
        bucket; then written, read back, and the copy read back scanned again.
        ``{"key", "sha256", "read_back", "unmasked_after"}``: the two checksums and the count
        of members of the copy that masking would change."""
        flagged = unmasked_members(body)
        if flagged:
            raise Refused(flagged)
        digest = hashlib.sha256(body).hexdigest()
        client = self.client()
        self.put(key, body, metadata={**(metadata or {}), "sha256": digest}, client=client)
        back = client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        return {"key": key, "sha256": digest, "read_back": hashlib.sha256(back).hexdigest(),
                "unmasked_after": len(unmasked_members(back))}

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
