#!/usr/bin/env bash
# C665: set `mercury_kind` on NetBox's Device Roles with an ADMIN's token, which this step
# PROMPTS for (hidden), never prints, never stores, never exports, and passes to the tool on
# stdin only (the operator, 2026-10-11: Mercury's own token may not edit roles, and is not
# widened).
#
# The map (`role_kind.ADMIN_MAP`, read by scripts/nmas-netbox-role-kinds-admin): router,
# core-router, edge-router -> router; switch, access-switch -> switch; firewall -> firewall;
# core-switch and distribution-switch -> switch (PROPOSED: Mercury has no l3-switch kind;
# Topology badges a switch L3 when it routes). A role NetBox holds that the map does not list
# is never changed. Shows each role's before, wanted and after: first a plan that writes
# nothing, then, after you type yes, the write and its read-back.
# Run on the NMAS host, as the operator's own user:
#     bash <checkout>/scripts/host-steps/netbox-role-kinds.sh
. "$(dirname "$0")/lib.sh"

PY=${NMAS_PY:-/opt/mercury-venv/bin/python}
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

plan "run as the operator's own user, not root" \
     "a token was given" \
     "the plan reads NetBox's roles" \
     "you typed yes" \
     "every listed role reads back its kind, and no other role moved"

not_root
read -r -s -p "NetBox admin token (hidden, not stored): " TOKEN
echo
REDACT=$TOKEN
check "a token was given" eq "yes" "$([ -n "$TOKEN" ] && echo 'echo yes' || echo 'echo no')"

tool() {   # the token on stdin only, in this shell (never an argument or an exported variable)
    printf '%s' "$TOKEN" | (cd "$CHECKOUT" && "$PY" scripts/nmas-netbox-role-kinds-admin "$@")
}

echo "== PLAN (nothing written)"
tool --plan | tee "$WORK/plan"
check "the plan reads NetBox's roles" has "PLAN ONLY" "cat '$WORK/plan'"

read -r -p "Write these kinds? Type yes to continue: " GO
check "you typed yes" eq "yes" "echo '${GO//\'/}'"

echo "== WRITE, then read back"
tool | tee "$WORK/write"
TOKEN=""
REDACT=""
check "every listed role reads back its kind, and no other role moved" has "RESULT: PASS" \
    "cat '$WORK/write'"
summary
