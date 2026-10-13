#!/usr/bin/env bash
# D16 (the operator's overnight list, 2026-10-13, item 8): archive a removed family's data to
# Mercury's MinIO bucket, and only then, on a second run naming the archive's checksum, delete
# it. The rules: delete only what is archived as a tarball, read back and checksum-verified; no
# plaintext credential in an archive (every text file passed through Mercury's own masking,
# `redact.redact_text`, and the read-back copy scanned again: the check wants nothing it would
# change). Names and counts are printed, never a value.
#
# Run on the NMAS host, as the operator's own user, from the checkout:
#     bash scripts/host-steps/d16-archive.sh <family> <path under the data directory>...
#     bash scripts/host-steps/d16-archive.sh <family> --delete <sha256> <path>...
# It refuses anywhere else, and refuses a path outside the data directory.
. "$(dirname "$0")/lib.sh"

PY=${NMAS_PY:-/opt/mercury-venv/bin/python}
export PYTHONDONTWRITEBYTECODE=1 CHECKOUT PY
FAMILY="${1:-}"
shift || true
MODE=archive
WANT=""
if [ "${1:-}" = "--delete" ]; then MODE=delete; WANT="${2:-}"; shift 2 || true; fi
PATHS="$*"
DIR=$(mktemp -d)
export FAMILY MODE WANT PATHS DIR

plan "run as the operator's own user, not root" \
     "this is the NMAS host: flask-app.service and its interpreter" \
     "a family and at least one path are named" \
     "the archive holds no value Mercury would mask, checked before upload" \
     "the archive is written and read back with the same sha256, the copy scanned again" \
     "the deletion found the archive by its checksum"

not_root
check "this is the NMAS host: flask-app.service and its interpreter" eq "yes" \
    'systemctl cat flask-app.service >/dev/null 2>&1 && [ -x "$PY" ] && echo yes || echo no'
check "a family and at least one path are named" re "^[a-z0-9-]+ .+" 'echo "$FAMILY $PATHS"'

cat > "$DIR/archive.py" <<'PY'
import hashlib
import io
import json
import os
import shutil
import sys
import tarfile
import time

sys.path.insert(0, os.getcwd())
from modules import redact  # noqa: E402
from modules.config import DATA_DIR  # noqa: E402
from modules.integrations.s3_archive import Refused, S3ArchiveIntegration  # noqa: E402

family, mode, want, out = (os.environ[k] for k in ("FAMILY", "MODE", "WANT", "DIR"))
names = os.environ["PATHS"].split()
root = os.path.realpath(DATA_DIR)
paths = [os.path.realpath(os.path.join(DATA_DIR, n)) for n in names]
if any(not p.startswith(root + os.sep) for p in paths):
    print("a path is outside the data directory: refused")
    sys.exit(1)
s3 = S3ArchiveIntegration()
prefix = s3.key("archives", family)


def files(path):
    if os.path.isfile(path):
        return [path]
    return sorted(os.path.join(d, f) for d, _s, fs in os.walk(path) for f in fs)


if mode == "archive":
    buf, counts, skipped = io.BytesIO(), {}, 0
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path in paths:
            for f in files(path):
                try:
                    text = open(f, encoding="utf-8").read()
                except UnicodeDecodeError:
                    skipped += 1
                    continue
                data = redact.redact_text(text).encode("utf-8")
                info = tarfile.TarInfo(os.path.relpath(f, root))
                info.size, info.mtime = len(data), int(os.path.getmtime(f))
                tar.addfile(info, io.BytesIO(data))
                counts[os.path.relpath(path, root)] = counts.get(os.path.relpath(path, root),
                                                                 0) + 1
    if skipped:
        print(f"{skipped} binary file(s) cannot be masked: refused, nothing written")
        sys.exit(1)
    key = f"{prefix}/{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.tar.gz"
    try:
        # Scanned before anything is written: a failing archive never leaves the host (C743).
        r = s3.put_archive(key, buf.getvalue(), metadata={"source": "d16-archive"})
    except Refused as exc:
        json.dump({"unmasked": len(exc.members)}, open(os.path.join(out, "result"), "w"))
        print("NOT uploaded: masking would still change", ", ".join(exc.members))
        sys.exit(0)
    json.dump(dict(r, unmasked=0), open(os.path.join(out, "result"), "w"))
    print("archived:", json.dumps(counts))
    print(f"archive: s3://{s3.bucket}/{key}  sha256 {r['sha256']}")
else:
    found = None
    for page in s3.client().get_paginator("list_objects_v2").paginate(Bucket=s3.bucket,
                                                                       Prefix=prefix):
        for obj in page.get("Contents") or []:
            body = s3.client().get_object(Bucket=s3.bucket, Key=obj["Key"])["Body"].read()
            if hashlib.sha256(body).hexdigest() == want:
                found = obj["Key"]
    json.dump({"found": found or ""}, open(os.path.join(out, "result"), "w"))
    if not found:
        print(f"no archive under {prefix} has sha256 {want}: nothing deleted")
        sys.exit(1)
    for path in paths:
        if os.path.isdir(path):
            shutil.rmtree(path)
        elif os.path.exists(path):
            os.remove(path)
    print(f"deleted {len(paths)} path(s); the archive is s3://{s3.bucket}/{found}")
PY

if [ "$MODE" = archive ]; then
    step "build the masked archive, upload, read back" 'cd "$CHECKOUT" && "$PY" "$DIR/archive.py"'
else
    step "find the archive by its checksum, then delete what it holds" \
        'cd "$CHECKOUT" && "$PY" "$DIR/archive.py"'
fi
# Each check is asked only in its own mode; the other mode's are NOT ASKED, never PASS (C757).
if [ "$MODE" = archive ]; then
    check "the archive holds no value Mercury would mask, checked before upload" eq "0" \
        'python3 -c "import json; print(json.load(open(\"$DIR/result\"))[\"unmasked\"])"'
    check "the archive is written and read back with the same sha256, the copy scanned again" eq "same" \
        'python3 -c "import json; r=json.load(open(\"$DIR/result\")); print(\"same\" if r[\"sha256\"]==r[\"read_back\"] and r[\"unmasked_after\"]==0 else \"different\")"'
    not_asked "the deletion found the archive by its checksum" "the --delete run's"
else
    not_asked "the archive holds no value Mercury would mask, checked before upload" "the archive run's"
    not_asked "the archive is written and read back with the same sha256, the copy scanned again" "the archive run's"
    check "the deletion found the archive by its checksum" re "archives/" \
        'python3 -c "import json; print(json.load(open(\"$DIR/result\"))[\"found\"])"'
fi
rm -rf "$DIR"
summary
