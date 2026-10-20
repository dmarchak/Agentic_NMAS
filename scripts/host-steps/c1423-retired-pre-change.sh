#!/usr/bin/env bash
# C1423's one-off (the operator, 2026-10-20), for ONE retired device at a time: the deploy
# pipeline keeps the last pre-change running config of each device it deploys to, owner-only,
# in the network's data folder (`_record_pre_change` in modules/pipeline.py; it holds the
# device's credentials), and Retire does not remove it, so a retired device's last running
# config outlives it. This step removes that one file, and only when:
#   1. the device is retired (the network's repository holds its retire commit) and is not in
#      the network's inventory now (a new device of that name has not been onboarded);
#   2. the file is a regular file (no link), owned by the owner of the network's inventory,
#      mode 0600, written before the retire commit, its first line the pipeline's header naming
#      the device. Its contents are never printed: the header is compared, not shown.
# Nothing else in the folder moves. Not tracked in any git repository (the data folder is
# ignored); the nightly VM backups keep their copies, which are the operator's. The real fix
# (C1423): Retire removes it in its commit step.
# Run on the NMAS host, as the operator's own user (sudo asked for the reads and the removal):
#     bash <checkout>/scripts/host-steps/c1423-retired-pre-change.sh <device> [network]
. "$(dirname "$0")/lib.sh"

DEV=${1:-}
NET=${2:-Default}
if ! [[ "$DEV" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]]; then
    echo "REFUSED: name the retired device: bash $0 <device> [network] (got '${DEV}')"
    exit 2
fi
PY=${NMAS_PY:-/opt/mercury-venv/bin/python}
WORK=$(mktemp -d)
echo "== the device: $DEV, in the network: $NET"

plan "run as the operator's own user, not root" \
     "the network's data folder and inventory are found" \
     "the device has a retire commit in the network's repository" \
     "the device is not in the network's inventory now" \
     "the file is a regular file, not a link" \
     "the file is owned by the inventory's owner, mode 600" \
     "the file was written before the retire commit" \
     "the file's first line is the pipeline's header naming the device" \
     "the file is gone" \
     "nothing else in the folder moved"

not_root
step "the network's folder, the device's file name, its retire time and whether it is listed now" \
    "cd '$CHECKOUT' && '$PY' -c '
import datetime, os, sys
from modules.config import list_data_path
from modules.device import load_saved_devices
from modules.goldens import _safe_device_name
from modules.nsot import retire
dev, net = sys.argv[1], sys.argv[2]
d = list_data_path(net)
inv = os.path.join(d, \"devices.csv\")
rec = retire.retired_record(os.path.join(d, \"config_repo\"), dev) if os.path.isdir(d) else None
listed = [x.get(\"hostname\") for x in load_saved_devices(inv)] if os.path.isfile(inv) else []
at = int(datetime.datetime.fromisoformat(rec[\"at\"]).timestamp()) if rec else \"\"
print(d, _safe_device_name(dev), at, \"listed\" if dev in listed else \"unlisted\", sep=\"\\n\")
' '$DEV' '$NET' > '$WORK/facts' && cat '$WORK/facts'"
DIR=$(sed -n 1p "$WORK/facts")
SAFE=$(sed -n 2p "$WORK/facts")
RETIRED_AT=$(sed -n 3p "$WORK/facts")
FILE="$DIR/pre_change/$SAFE.cfg"
echo "== the file: $FILE"

check "the network's data folder and inventory are found" eq "found" \
    "sudo test -d '$DIR' && sudo test -f '$DIR/devices.csv' && echo found || echo 'not found'"
check "the device has a retire commit in the network's repository" re '^[0-9]+$' \
    "echo '${RETIRED_AT:-no retire commit}'"
check "the device is not in the network's inventory now" eq "unlisted" "sed -n 4p '$WORK/facts'"
check "the file is a regular file, not a link" eq "regular" \
    "sudo test -L '$FILE' && echo link || { sudo test -f '$FILE' && echo regular || echo absent; }"
check "the file is owned by the inventory's owner, mode 600" eq "ok" \
    "[ \"\$(sudo stat -c '%u %a' '$FILE')\" = \"\$(sudo stat -c '%u' '$DIR/devices.csv') 600\" ] && echo ok || echo \"owner and mode: \$(sudo stat -c '%U %a' '$FILE'), inventory owner: \$(sudo stat -c '%U' '$DIR/devices.csv')\""
check "the file was written before the retire commit" eq "before" \
    "[ \"\$(sudo stat -c '%Y' '$FILE')\" -le '$RETIRED_AT' ] && echo before || echo \"after (written \$(sudo stat -c '%y' '$FILE'))\""
check "the file's first line is the pipeline's header naming the device" eq "matches" \
    "sudo head -n 1 '$FILE' | grep -qF -- '! Pre-change snapshot — $DEV (' && echo matches || echo 'does not match (not shown)'"

step "every other file in the folder, recorded before" \
    "sudo find '$DIR/pre_change' -mindepth 1 ! -path '$FILE' -printf '%P %s %T@\n' | sort > '$WORK/others.before' && wc -l < '$WORK/others.before'"
step "remove the file (by name)" "sudo rm -- '$FILE'"
check "the file is gone" eq "absent" "sudo test -e '$FILE' && echo present || echo absent"
check "nothing else in the folder moved" eq "" \
    "sudo find '$DIR/pre_change' -mindepth 1 -printf '%P %s %T@\n' | sort | diff '$WORK/others.before' -"
summary
