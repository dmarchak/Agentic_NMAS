#!/usr/bin/env bash
# C663 step 2's host side, BEFORE the release that empties `netbox_excluded_vrfs`'s default
# (docs/END_OF_SESSION.md). Until that release the default named one emulator's management
# VRF; a host that relied on the default would, after it, model that VRF's addresses on the
# next NetBox import. So the value in force now is RATIFIED: written to the settings file as
# it is, through Mercury's own write path (`settings_schema.ratify`, never a change), so the
# new default moves nothing here. Run on the NMAS host, as the operator's own user:
#     bash <checkout>/scripts/host-steps/c663-step2-pin-vrfs.sh
. "$(dirname "$0")/lib.sh"

PY=${NMAS_PY:-/opt/mercury-venv/bin/python}
KEY=netbox_excluded_vrfs
ACTOR="${ACTOR:-$(id -un) (host shell, C663 step 2)}"
read_origin="cd '$CHECKOUT' && '$PY' -c 'from modules.settings_schema import origin_of; print(origin_of(\"$KEY\"))'"

plan "run as the operator's own user, not root" \
     "the setting is declared in the running checkout" \
     "the setting's value comes from the settings file" \
     "it holds at least one VRF"

not_root
check "the setting is declared in the running checkout" ge 1 \
    "grep -c '\"$KEY\"' '$CHECKOUT/modules/settings_schema.py'"

step "ratify the value in force (written as it is, with who)" \
    "cd '$CHECKOUT' && '$PY' -c 'import sys; from modules.settings_schema import ratify; r = ratify(\"$KEY\", actor=sys.argv[1]); print({k: r.get(k) for k in (\"ok\", \"error\", \"already\", \"key\", \"origin\")}); sys.exit(0 if r.get(\"ok\") else 1)' '$ACTOR'"

check "the setting's value comes from the settings file" eq "file" "$read_origin"
check "it holds at least one VRF" ge 1 \
    "cd '$CHECKOUT' && '$PY' -c 'from modules.settings_schema import get_setting; v = get_setting(\"$KEY\"); print(len(v if isinstance(v, list) else str(v).replace(\",\", \" \").split()))'"
summary
