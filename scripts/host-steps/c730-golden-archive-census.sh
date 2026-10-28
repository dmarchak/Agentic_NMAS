#!/usr/bin/env bash
# C730 (the operator's decision D6, 2026-10-15): the golden archive in Mercury's bucket held each
# device's SNMP communities and type-9 hashes verbatim. From the release carrying C730, every
# golden is written masked, at `goldens/<network>/<device>/<stamp>.masked.cfg`, its metadata
# naming the masking. What was written before stays in the bucket, every version of it: deleting
# or keeping it is the operator's (Mercury's key cannot delete, M-2).
#
# This step MEASURES, read-only, with Mercury's own key (list and read; it writes nothing and
# deletes nothing): every version under goldens/, each read and asked whether Mercury's masking
# (`redact_text`, the installation's values) would still change it. It prints counts and object
# folders, never a value. What masking does not know (a shape `redact._POSITIONAL` does not
# name) is not counted: an object holding only those reads as masked here. It counts the installation's archive (Default's
# endpoint, bucket and prefix); a network that set its own bucket or prefix is not counted
# (none had, read 2026-10-09: docs/NSOT_PHASE4_MINIO.md section 3).
#
# Run on the NMAS host, as the operator's own user, after the C730 release is deployed:
#     bash <checkout>/scripts/host-steps/c730-golden-archive-census.sh
. "$(dirname "$0")/lib.sh"

PY=${NMAS_PY:-/opt/mercury-venv/bin/python}
DIR=$(mktemp -d)
chmod 700 "$DIR"
export PYTHONDONTWRITEBYTECODE=1 CHECKOUT PY DIR

plan "run as the operator's own user, not root" \
     "this is the NMAS host: flask-app.service and its interpreter" \
     "the release carrying C730 is the checkout's: the archive has its census" \
     "every version under goldens/ was read" \
     "no object written masked holds a value masking would change" \
     "the unmasked objects are counted"

not_root
check "this is the NMAS host: flask-app.service and its interpreter" eq "yes" \
    'systemctl cat flask-app.service >/dev/null 2>&1 && [ -x "$PY" ] && echo yes || echo no'
check "the release carrying C730 is the checkout's: the archive has its census" eq "yes" \
    'cd "$CHECKOUT" && "$PY" -c "from modules.integrations.s3_archive import S3ArchiveIntegration as S; print(\"yes\" if hasattr(S, \"golden_census\") else \"no\")"'

cat > "$DIR/census.py" <<'PY'
"""Every version under goldens/, counted (C730). Prints counts and folders, never a value."""
import json
import os
import sys

sys.path.insert(0, os.getcwd())
from modules.integrations.s3_archive import S3ArchiveIntegration  # noqa: E402

s3 = S3ArchiveIntegration()
if not s3.is_configured():
    print("the S3 archive is not configured: nothing to count")
    sys.exit(1)
got = s3.golden_census()
unmasked = sum(got["unmasked"].values())
print(f"bucket {s3.bucket}, under {s3.key('goldens')}/: {got['versions']} version(s) of "
      f"{got['current']} object(s); {got['marked']} version(s) written masked "
      f"(*.masked.cfg), {got['versions'] - got['marked']} written before C730")
print(f"versions holding a value Mercury would mask: {unmasked}, in "
      f"{len(got['unmasked'])} device folder(s)")
for folder, n in sorted(got["unmasked"].items()):
    print(f"  {folder}/: {n}")
for name, why in (("marked_unmasked", "written masked, yet masking would change it"),
                  ("not_text", "not UTF-8 text, so not shown masked"),
                  ("unreadable", "not read with Mercury's key")):
    print(f"{why}: {len(got[name])}")
    for key in got[name]:
        print(f"  {key}")
json.dump(dict(got, unmasked_total=unmasked), open(os.path.join(os.environ["DIR"], "result"),
                                                    "w"))
PY

step "count every version under goldens/, read-only" 'cd "$CHECKOUT" && "$PY" "$DIR/census.py"'
check "every version under goldens/ was read" eq "0" \
    'python3 -c "import json; r=json.load(open(\"$DIR/result\")); print(len(r[\"unreadable\"]) + len(r[\"not_text\"]))"'
check "no object written masked holds a value masking would change" eq "0" \
    'python3 -c "import json; print(len(json.load(open(\"$DIR/result\"))[\"marked_unmasked\"]))"'
check "the unmasked objects are counted" re "^[0-9]+$" \
    'python3 -c "import json; print(json.load(open(\"$DIR/result\"))[\"unmasked_total\"])"'
rm -rf "$DIR"
summary
