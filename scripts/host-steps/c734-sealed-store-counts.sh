#!/usr/bin/env bash
# C734 (docs/OPEN_FINDINGS.md, 2026-10-13): how many sealed values each store holds on the NMAS
# host, now that the one registry (`breakglass.live_ciphertexts`) reads all five kinds: the
# settings, the credential profiles, each network's devices.csv and settings.json, and any
# rotation's parked password. READ-ONLY: it writes nothing, and it prints counts and store
# names, never a value. It also asks whether the key in use opens every one of them
# (`breakglass.check_key_opens`, counts only), the check the break-glass page makes.
#
# Run on the NMAS host, as the operator's own user, with this release deployed:
#     bash <checkout>/scripts/host-steps/c734-sealed-store-counts.sh
# It refuses anywhere else (no flask-app.service, or not its interpreter).
. "$(dirname "$0")/lib.sh"

PY=${NMAS_PY:-/opt/mercury-venv/bin/python}
export PYTHONDONTWRITEBYTECODE=1 CHECKOUT PY

plan "run as the operator's own user, not root" \
     "this is the NMAS host: flask-app.service and its interpreter" \
     "the release reads all five kinds of store" \
     "every store could be read" \
     "the key in use opens every sealed value"

not_root
check "this is the NMAS host: flask-app.service and its interpreter" eq "yes" \
    'systemctl cat flask-app.service >/dev/null 2>&1 && [ -x "$PY" ] && echo yes || echo no'
check "the release reads all five kinds of store" eq "yes" \
    'cd "$CHECKOUT" && "$PY" -c "from modules import breakglass as b; print(\"yes\" if b.JSON_STORE_GLOBS and b.TOKEN_FILE_GLOBS else \"no\")"'

COUNT='
import os, sys
sys.path.insert(0, os.getcwd())
from modules import breakglass as b
from modules.config import DATA_DIR, KEY_FILE
from modules.secrets_store import _PREFIX
found = b.live_ciphertexts(DATA_DIR, _PREFIX)
for name in sorted(k for k in found if k != "_unreadable"):
    print(f"   {len(found[name]):4d}  {name}")
print("   unreadable: " + (", ".join(found.get("_unreadable") or []) or "none"))
if sys.argv[1:] == ["verdict"]:
    with open(KEY_FILE, "rb") as fh:
        check = b.check_key_opens(fh.read().strip(), found)
    print(f"{check[\"verdict\"]} ({check[\"opened\"]} of {check[\"total\"]})")
'
export COUNT
step "count the sealed values in each store (counts and names only)" 'cd "$CHECKOUT" && "$PY" -c "$COUNT"'
check "every store could be read" has "unreadable: none" 'cd "$CHECKOUT" && "$PY" -c "$COUNT"'
check "the key in use opens every sealed value" re "^opens \(" \
    'cd "$CHECKOUT" && "$PY" -c "$COUNT" verdict | tail -1'
summary
