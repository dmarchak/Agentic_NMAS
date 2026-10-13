#!/usr/bin/env bash
# C743 (2026-10-13): delete the two archive objects the first D15 and Oxidized runs left in
# Mercury's bucket, and every version of them, then show they are gone. The operator's
# instruction: "Write a host step that deletes both objects (and every version of them, if the
# bucket versions objects) and confirms they're gone. Don't keep them."
#
# Measured before this was written (read-only, Mercury's own key, counts only): neither object
# holds a value Mercury would mask. Each failed its check because masking was not idempotent:
# a second pass turned an already masked `secret 9 <redacted:x>` into two placeholders, and an
# `snmp-server host` line's `version` keyword into one (1 member in each archive). Fixed in the
# same commit. They are deleted all the same, as asked: the fixed runs write new archives.
#
# Mercury's own key cannot delete (M-2). The step PROMPTS for a MinIO key that can (input
# hidden, never an argument, never printed or stored); it is handed to Python in the
# environment of the one command that uses it. Each object is deleted only if its sha256 begins
# with the prefix the operator was given for it.
#
# Run on the NMAS host, as the operator's own user:
#     bash <checkout>/scripts/host-steps/c743-delete-archive-objects.sh
. "$(dirname "$0")/lib.sh"

PY=${NMAS_PY:-/opt/mercury-venv/bin/python}
# key=the sha256 prefix it must carry (the two first runs' printed checksums).
OBJECTS="archives/ai-family/20261013T161055Z.tar.gz=8b47fbf1 archives/oxidized/20261013T161059Z.tar.gz=99444884"
DIR=$(mktemp -d)
chmod 700 "$DIR"
export PYTHONDONTWRITEBYTECODE=1 CHECKOUT PY OBJECTS DIR

plan "run as the operator's own user, not root" \
     "this is the NMAS host: flask-app.service and its interpreter" \
     "a key was typed" \
     "each object is the one named, by its checksum's prefix" \
     "every version and delete marker of both objects is deleted" \
     "neither object is in the bucket, in any version"

not_root
check "this is the NMAS host: flask-app.service and its interpreter" eq "yes" \
    'systemctl cat flask-app.service >/dev/null 2>&1 && [ -x "$PY" ] && echo yes || echo no'

echo "A MinIO key that may delete in Mercury's bucket (the root user, or a key with"
echo "s3:DeleteObject and s3:DeleteObjectVersion on it). Mercury's own key cannot."
read -r -p "Access key: " ACCESS
read -r -s -p "Secret key (hidden): " SECRET; echo
REDACT=$SECRET
check "a key was typed" eq "yes" '[ -n "$ACCESS" ] && [ -n "$SECRET" ] && echo yes || echo no'

cat > "$DIR/delete.py" <<'PY'
"""Delete every version of each named object, after checking its checksum's prefix; then
list again. Prints keys, version counts and the checks' words, never the key typed."""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.getcwd())
from modules.integrations.s3_archive import S3ArchiveIntegration  # noqa: E402

phase, out = sys.argv[1], os.environ["DIR"]
objects = dict(o.split("=", 1) for o in os.environ["OBJECTS"].split())
s3 = S3ArchiveIntegration()
c = s3.client(credentials=(os.environ.pop("MINIO_ACCESS"), os.environ.pop("MINIO_SECRET")))
try:
    print("bucket versioning:", c.get_bucket_versioning(Bucket=s3.bucket).get("Status")
          or "never enabled")
except Exception as exc:  # noqa: BLE001
    print("bucket versioning: unreadable with this key:", type(exc).__name__)


def versions(key):
    """``[(version_id, is_marker)]`` of exactly *key*, every page."""
    got = []
    for page in c.get_paginator("list_object_versions").paginate(Bucket=s3.bucket, Prefix=key):
        got += [(v["VersionId"], False) for v in page.get("Versions") or [] if v["Key"] == key]
        got += [(m["VersionId"], True) for m in page.get("DeleteMarkers") or []
                if m["Key"] == key]
    return got


result = {}
for key, prefix in objects.items():
    vs = versions(key)
    if phase == "identify":
        shas = []
        for vid, marker in vs:
            if not marker:
                body = c.get_object(Bucket=s3.bucket, Key=key, VersionId=vid)["Body"].read()
                shas.append(hashlib.sha256(body).hexdigest())
        ok = bool(shas) and all(s.startswith(prefix) for s in shas)
        print(f"{key}: {len(shas)} version(s), {len(vs) - len(shas)} delete marker(s); "
              f"sha256 {', '.join(s[:16] + '…' for s in shas) or 'none'}; "
              f"{'matches' if ok else 'DOES NOT match'} {prefix}…")
        result[key] = ok
    elif phase == "delete":
        for vid, _marker in vs:
            c.delete_object(Bucket=s3.bucket, Key=key, VersionId=vid)
        print(f"{key}: deleted {len(vs)} version(s) and marker(s)")
        result[key] = len(vs)
    else:
        left = versions(key)
        print(f"{key}: {len(left)} version(s) or marker(s) left")
        result[key] = len(left)
json.dump(result, open(os.path.join(out, phase), "w"))
PY

RUN='cd "$CHECKOUT" && MINIO_ACCESS="$ACCESS" MINIO_SECRET="$SECRET" "$PY" "$DIR/delete.py"'
export ACCESS SECRET RUN
step "list both objects' versions and read each one's checksum" "$RUN identify"
check "each object is the one named, by its checksum's prefix" eq "True" \
    'python3 -c "import json; print(all(json.load(open(\"$DIR/identify\")).values()))"'
step "delete every version and delete marker of both" "$RUN delete"
check "every version and delete marker of both objects is deleted" eq "True" \
    'python3 -c "import json; print(all(n > 0 for n in json.load(open(\"$DIR/delete\")).values()))"'
step "list both objects again" "$RUN gone"
check "neither object is in the bucket, in any version" eq "0" \
    'python3 -c "import json; print(sum(json.load(open(\"$DIR/gone\")).values()))"'
unset ACCESS SECRET
rm -rf "$DIR"
summary
