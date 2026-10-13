#!/usr/bin/env bash
# D16 (the operator's overnight list, 2026-10-13, item 8): Oxidized's containers and store, retired
# after Phase 3 (2026-10-08). Two runs, the operator's (root: the store is uid 30000's, 0600):
#
#   sudo bash <checkout>/scripts/host-steps/d16-oxidized-retire.sh
#       ARCHIVE: copies /opt/oxidized to a private temporary folder, and puts in Mercury's bucket,
#       under archives/oxidized/, one tarball: every text file masked by Mercury's own
#       `redact.redact_text`; Oxidized's `config` files SEALED whole by the application key
#       (`encrypt_value`: they may hold device credentials in fields masking does not know);
#       each git store (`*.git`) as its full history in text (`git log --all -p`), masked,
#       since a repository's compressed objects cannot be masked. `router.db` and every copy of
#       it are NOT archived: they hold device passwords in plaintext, and are shredded. Reads
#       the archive back, compares its sha256, scans the copy again, prints path and checksum.
#
#   sudo bash <checkout>/scripts/host-steps/d16-oxidized-retire.sh --delete <sha256>
#       DELETE: only after finding that archive in the bucket by its checksum: stops nothing
#       (both containers have been exited since Phase 3), removes the two containers, shreds
#       router.db and its copies (`shred -u`), and removes /opt/oxidized.
#
# Names, counts and the checksum are printed, never a value. It refuses off the NMAS host.
. "$(dirname "$0")/lib.sh"

PY=${NMAS_PY:-/opt/mercury-venv/bin/python}
STORE=/opt/oxidized
RUNAS=${SUDO_USER:-}
MODE=archive
WANT=""
if [ "${1:-}" = "--delete" ]; then MODE=delete; WANT="${2:-}"; fi
DIR=$(mktemp -d)
chmod 700 "$DIR"
export PYTHONDONTWRITEBYTECODE=1 CHECKOUT PY STORE MODE WANT DIR RUNAS

plan "run as root through sudo, by the operator's own user" \
     "this is the NMAS host: flask-app.service and its interpreter" \
     "Oxidized's containers are not running" \
     "the archive holds no value Mercury would mask, checked before upload" \
     "the archive is written and read back with the same sha256, the copy scanned again" \
     "the deletion found the archive by its checksum" \
     "nothing of Oxidized is left"

check "run as root through sudo, by the operator's own user" re "^0 [a-z_][a-z0-9_-]*$" \
    'echo "$(id -u) $RUNAS"'
check "this is the NMAS host: flask-app.service and its interpreter" eq "yes" \
    'systemctl cat flask-app.service >/dev/null 2>&1 && [ -x "$PY" ] && echo yes || echo no'
check "Oxidized's containers are not running" eq "0" \
    'docker ps --format "{{.Names}}" | grep -c "^oxidized" || true'

cat > "$DIR/archive.py" <<'PY'
import hashlib
import io
import json
import os
import sys
import tarfile
import time

sys.path.insert(0, os.getcwd())
from modules import redact  # noqa: E402
from modules.integrations.s3_archive import Refused, S3ArchiveIntegration  # noqa: E402
from modules.secrets_store import encrypt_value  # noqa: E402

out, copy, mode, want = os.environ["DIR"], os.path.join(os.environ["DIR"], "store"), \
    os.environ["MODE"], os.environ["WANT"]
s3 = S3ArchiveIntegration()
prefix = s3.key("archives", "oxidized")
if mode == "archive":
    buf, counts = io.BytesIO(), {"masked": 0, "sealed": 0, "shredded, not archived": 0}

    def add(name, data):
        info = tarfile.TarInfo(name)
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))

    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for d, subdirs, files in os.walk(copy):
            if d.endswith(".git") or ".git" + os.sep in d + os.sep:
                continue
            subdirs[:] = [s for s in subdirs if not s.endswith(".git")]
            for f in files:
                path = os.path.join(d, f)
                rel = os.path.relpath(path, copy)
                if f.startswith("router.db") or f.startswith(".router.db"):
                    counts["shredded, not archived"] += 1
                    continue
                text = open(path, encoding="utf-8", errors="replace").read()
                if f.startswith("config"):
                    add(rel + ".sealed", encrypt_value(text).encode())
                    counts["sealed"] += 1
                else:
                    add(rel, redact.redact_text(text).encode())
                    counts["masked"] += 1
        for name in sorted(os.listdir(os.path.join(out, "history"))):
            history = open(os.path.join(out, "history", name), encoding="utf-8",
                           errors="replace").read()
            add(name + ".history.txt", redact.redact_text(history).encode())
            counts["masked"] += 1
    key = f"{prefix}/{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.tar.gz"
    try:
        # Scanned before anything is written: a failing archive never leaves the host (C743).
        r = s3.put_archive(key, buf.getvalue(), metadata={"source": "d16-oxidized-retire"})
    except Refused as exc:
        json.dump({"unmasked": len(exc.members)}, open(os.path.join(out, "result"), "w"))
        print("NOT uploaded: masking would still change", ", ".join(exc.members))
        sys.exit(0)
    json.dump(dict(r, unmasked=0), open(os.path.join(out, "result"), "w"))
    print("archived:", json.dumps(counts))
    print(f"archive: s3://{s3.bucket}/{key}  sha256 {r['sha256']}")
else:
    found = ""
    for page in s3.client().get_paginator("list_objects_v2").paginate(Bucket=s3.bucket,
                                                                       Prefix=prefix):
        for obj in page.get("Contents") or []:
            body = s3.client().get_object(Bucket=s3.bucket, Key=obj["Key"])["Body"].read()
            if hashlib.sha256(body).hexdigest() == want:
                found = obj["Key"]
    json.dump({"found": found}, open(os.path.join(out, "result"), "w"))
    print(f"found: {found or 'nothing with sha256 ' + want}")
PY

if [ "$MODE" = archive ]; then
    step "copy the store to a private folder the operator's user reads" \
        'cp -a "$STORE" "$DIR/store" && mkdir "$DIR/history" && for g in "$DIR"/store/*.git; do git --git-dir="$g" log --all -p > "$DIR/history/$(basename "$g")"; done && chown -R "$RUNAS" "$DIR"'
    step "build the archive (masked, configs sealed, router.db left out), upload, read back" \
        'cd "$CHECKOUT" && sudo -u "$RUNAS" env PYTHONDONTWRITEBYTECODE=1 DIR="$DIR" MODE="$MODE" WANT="" "$PY" "$DIR/archive.py"'
    step "shred the temporary copy" 'find "$DIR/store" -type f -exec shred -u {} + ; find "$DIR/history" -type f -exec shred -u {} + ; rm -rf "$DIR/store" "$DIR/history"'
else
    step "find the archive by its checksum" \
        'cd "$CHECKOUT" && sudo -u "$RUNAS" env PYTHONDONTWRITEBYTECODE=1 DIR="$DIR" MODE="$MODE" WANT="$WANT" "$PY" "$DIR/archive.py"'
fi
check "the archive holds no value Mercury would mask, checked before upload" re "^(0|not asked)$" \
    'if [ "$MODE" = archive ]; then python3 -c "import json; print(json.load(open(\"$DIR/result\"))[\"unmasked\"])"; else echo "not asked"; fi'
check "the archive is written and read back with the same sha256, the copy scanned again" re "^(same|not asked)$" \
    'if [ "$MODE" = archive ]; then python3 -c "import json; r=json.load(open(\"$DIR/result\")); print(\"same\" if r[\"sha256\"]==r[\"read_back\"] and r[\"unmasked_after\"]==0 else \"different\")"; else echo "not asked"; fi'
check "the deletion found the archive by its checksum" re "(archives/oxidized/|^not asked$)" \
    'if [ "$MODE" = delete ]; then python3 -c "import json; print(json.load(open(\"$DIR/result\"))[\"found\"])"; else echo "not asked"; fi'
if [ "$MODE" = delete ]; then
    step "remove the two exited containers" 'docker rm oxidized oxidized-pre-c143'
    step "shred router.db and every copy of it" \
        'find "$STORE" -maxdepth 1 -name "*router.db*" -type f -exec shred -u {} +'
    step "remove the store" 'rm -rf "$STORE"'
fi
check "nothing of Oxidized is left" re "^(gone|not asked)$" \
    'if [ "$MODE" = delete ]; then [ ! -e "$STORE" ] && [ -z "$(docker ps -a --format "{{.Names}}" | grep "^oxidized")" ] && echo gone || echo left; else echo "not asked"; fi'
rm -rf "$DIR"
summary
