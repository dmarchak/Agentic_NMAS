"""S3-compatible archive integration (Phase 0: connection test only).

Targets any S3-compatible endpoint (MinIO, AWS S3, …). The ``minio`` SDK is an
optional dependency and is not in requirements.txt yet — Phase 2 adds it when
the archive is actually written to. Until then an absent SDK reports cleanly
rather than raising.
"""

import logging

from modules.integrations.base import IntegrationClient
from modules.secrets_store import get_secret
from modules.settings_schema import get_setting

log = logging.getLogger(__name__)


class S3ArchiveIntegration(IntegrationClient):
    name = "s3"
    label = "S3 archive"
    url_key = "s3_endpoint"
    secret_keys = ("s3_access_key", "s3_secret_key")
    plain_keys = ("s3_bucket", "s3_region", "s3_prefix", "s3_verify_tls")

    def is_configured(self) -> bool:
        return bool(self.url and get_setting("s3_bucket", ""))

    def test_connection(self) -> dict:
        if not self.is_configured():
            return {"ok": False, "error": "Not configured — set endpoint and bucket in Settings"}
        try:
            from minio import Minio
        except ImportError:
            return {"ok": False,
                    "error": "minio SDK not installed — archive uploads land in Phase 2"}

        endpoint = self.url
        secure = endpoint.startswith("https://")
        host = endpoint.split("://", 1)[-1]
        try:
            client = Minio(
                host,
                access_key=get_secret("s3_access_key"),
                secret_key=get_secret("s3_secret_key"),
                secure=secure,
                region=get_setting("s3_region", "") or None,
            )
            bucket = get_setting("s3_bucket", "")
            if client.bucket_exists(bucket):
                return {"ok": True, "message": f"Bucket '{bucket}' reachable"}
            return {"ok": False, "error": f"Bucket '{bucket}' not found"}
        except Exception as exc:              # noqa: BLE001
            return {"ok": False, "error": str(exc)}
