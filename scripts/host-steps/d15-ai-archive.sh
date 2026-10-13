#!/usr/bin/env bash
# D15 (the operator's overnight list, 2026-10-13, item 7): archive the AI agent family's data to
# Mercury's MinIO bucket BEFORE the family is removed, and only then, on a second run naming the
# archive's checksum, delete it from the host. The operator's rules for the run:
#   - delete only what is archived to the bucket as a tarball, read back and checksum-verified;
#   - no plaintext credential in the archive: every text file is passed through Mercury's own
#     masking (`redact.redact_text`: by position, and by every value this installation holds),
#     and the AI provider key goes in only SEALED by the application key
#     (`secrets_store.encrypt_value`), never plaintext; the key is never printed.
# The agent cannot run this itself: its hook refuses a read of the stored device configurations
# (`checkpoints/`, `config_cache/`), and the key is a secret value.
#
# Run on the NMAS host, as the operator's own user, with the AI family still deployed:
#     bash <checkout>/scripts/host-steps/d15-ai-archive.sh            # archive, verify, print
#     bash <checkout>/scripts/host-steps/d15-ai-archive.sh --delete <sha256>
# The second form deletes the archived stores (and the key's line in .env) only after reading
# the archive back from the bucket and finding exactly that sha256. It refuses anywhere else.
. "$(dirname "$0")/lib.sh"

PY=${NMAS_PY:-/opt/mercury-venv/bin/python}
export PYTHONDONTWRITEBYTECODE=1 CHECKOUT PY
MODE=archive
WANT=""
if [ "${1:-}" = "--delete" ]; then MODE=delete; WANT="${2:-}"; fi
export MODE WANT
DIR=$(mktemp -d)
export DIR

plan "run as the operator's own user, not root" \
     "this is the NMAS host: flask-app.service and its interpreter" \
     "the bucket answers (Mercury's own Test, read-only)" \
     "the archive holds no value Mercury would mask, checked before upload" \
     "the archive is written and read back with the same sha256, the copy scanned again" \
     "the deletion found the archive by its checksum"

not_root
check "this is the NMAS host: flask-app.service and its interpreter" eq "yes" \
    'systemctl cat flask-app.service >/dev/null 2>&1 && [ -x "$PY" ] && echo yes || echo no'
check "the bucket answers (Mercury's own Test, read-only)" eq "True" \
    'cd "$CHECKOUT" && "$PY" -c "from modules.integrations.s3_archive import S3ArchiveIntegration as S; print(S().test_connection(write=False).get(\"ok\"))"'

cat > "$DIR/archive.py" <<'PY'
"""Build, upload and read back the AI family's archive; or, with --delete, delete what it
holds after finding it by its checksum. Prints names, counts and the checksum, never a value."""
import hashlib
import io
import json
import os
import sys
import tarfile
import time

sys.path.insert(0, os.getcwd())
from modules import redact  # noqa: E402
from modules.config import DATA_DIR  # noqa: E402
from modules.integrations.s3_archive import Refused, S3ArchiveIntegration  # noqa: E402
from modules.secrets_store import encrypt_value  # noqa: E402

STORES = ["chat_histories", "global_kb.json", "checkpoints", "agent_activity.json",
          "ai_debug.log", "provider_config.json", "config_cache", "drift_state.json",
          "trap_analysis_state.json", "ai_usage.json", "ai_usage_log.jsonl"]
ENV = os.path.join(os.getcwd(), ".env")
KEY_NAME = "ANTHROPIC_API_KEY"
s3 = S3ArchiveIntegration()
mode, want, out = os.environ["MODE"], os.environ.get("WANT", ""), os.environ["DIR"]
stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def files(path):
    if os.path.isfile(path):
        return [path]
    return sorted(os.path.join(d, f) for d, _s, fs in os.walk(path) for f in fs)


def key_line():
    if not os.path.exists(ENV):
        return ""
    for line in open(ENV, encoding="utf-8"):
        if line.startswith(KEY_NAME + "="):
            return line.split("=", 1)[1].strip()
    return ""


if mode == "archive":
    buf, counts = io.BytesIO(), {}
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name in STORES:
            for path in files(os.path.join(DATA_DIR, name)):
                raw = open(path, "rb").read()
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    counts[name + " (binary, left out)"] = counts.get(name, 0) + 1
                    continue
                member = os.path.relpath(path, DATA_DIR)
                if name == "provider_config.json":
                    # Provider keys may sit in fields masking does not know: sealed whole.
                    masked, member = encrypt_value(text).encode("utf-8"), member + ".sealed"
                else:
                    masked = redact.redact_text(text).encode("utf-8")
                info = tarfile.TarInfo(member)
                info.size, info.mtime = len(masked), int(os.path.getmtime(path))
                tar.addfile(info, io.BytesIO(masked))
                counts[name] = counts.get(name, 0) + 1
        sealed = encrypt_value(key_line()) if key_line() else ""
        note = json.dumps({"ai_provider_key": sealed, "sealed_by": "the application key "
                           "(secrets_store.encrypt_value); open with Mercury on this host",
                           "stores": counts, "at": stamp}, indent=1).encode("utf-8")
        info = tarfile.TarInfo("ARCHIVE.json")
        info.size = len(note)
        tar.addfile(info, io.BytesIO(note))
    key = s3.key("archives", "ai-family", f"{stamp}.tar.gz")
    try:
        # Scanned before anything is written: a failing archive never leaves the host (C743).
        r = s3.put_archive(key, buf.getvalue(), metadata={"source": "d15-ai-archive"})
    except Refused as exc:
        open(os.path.join(out, "result"), "w").write(json.dumps({"unmasked": len(exc.members)}))
        print("NOT uploaded: masking would still change", ", ".join(exc.members))
        sys.exit(0)
    open(os.path.join(out, "result"), "w").write(json.dumps(dict(r, unmasked=0)))
    print("stores archived:", json.dumps(counts))
    print(f"archive: s3://{s3.bucket}/{key}  sha256 {r['sha256']}  read back {r['read_back']}")
    print("the provider key:", "sealed in ARCHIVE.json" if sealed else "none in .env")
else:
    found = None
    paginator = s3.client().get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=s3.bucket, Prefix=s3.key("archives", "ai-family")):
        for obj in page.get("Contents") or []:
            body = s3.client().get_object(Bucket=s3.bucket, Key=obj["Key"])["Body"].read()
            if hashlib.sha256(body).hexdigest() == want:
                found = obj["Key"]
    open(os.path.join(out, "result"), "w").write(json.dumps({"found": found or ""}))
    if not found:
        print(f"no archive in the bucket has sha256 {want}: nothing deleted")
        sys.exit(1)
    import shutil
    for name in STORES:
        path = os.path.join(DATA_DIR, name)
        if os.path.isdir(path):
            shutil.rmtree(path)
        elif os.path.exists(path):
            os.remove(path)
    if key_line():
        lines = [l for l in open(ENV, encoding="utf-8") if not l.startswith(KEY_NAME + "=")]
        tmp = ENV + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.writelines(lines)
        os.chmod(tmp, 0o600)
        os.replace(tmp, ENV)
    print(f"deleted the archived stores and the key's line; the archive is {found}")
PY

if [ "$MODE" = archive ]; then
    step "build the masked archive, seal the key, upload, read back" \
        'cd "$CHECKOUT" && "$PY" "$DIR/archive.py"'
check "the archive holds no value Mercury would mask, checked before upload" eq "0" \
        'python3 -c "import json; print(json.load(open(\"$DIR/result\"))[\"unmasked\"])"'
check "the archive is written and read back with the same sha256, the copy scanned again" eq "same" \
        'python3 -c "import json; r=json.load(open(\"$DIR/result\")); print(\"same\" if r[\"sha256\"]==r[\"read_back\"] and r[\"unmasked_after\"]==0 else \"different\")"'
check "the deletion found the archive by its checksum" eq "not asked" 'echo "not asked"'
else
check "the archive holds no value Mercury would mask, checked before upload" eq "not asked" 'echo "not asked"'
check "the archive is written and read back with the same sha256, the copy scanned again" eq "not asked" 'echo "not asked"'
    step "find the archive by its checksum, then delete what it holds" \
        'cd "$CHECKOUT" && "$PY" "$DIR/archive.py"'
check "the deletion found the archive by its checksum" re "ai-family/" \
        'python3 -c "import json; print(json.load(open(\"$DIR/result\"))[\"found\"])"'
fi
rm -rf "$DIR"
summary
