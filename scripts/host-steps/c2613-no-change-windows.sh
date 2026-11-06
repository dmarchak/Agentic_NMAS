#!/usr/bin/env bash
# C2613: the installation's no-change window for the hypervisor's nightly backup, set to hold in
# both seasons. The backup runs 02:30 to 03:30 America/Denver (the window every guard states:
# 08:30 to 09:30 UTC under MDT, 09:30 to 10:30 under MST), and `no_change_windows` holds UTC
# only (C2614), so the one UTC value that holds all year is their union, 08:30 to 10:30.
# The value read on 2026-10-25 (C1681) was one window, 08:30 to 09:10, which since 2026-11-01
# has held an hour the backup no longer runs in.
#
# The write goes through `settings_schema.write_settings()`, the one write path
# (scripts/nmas-no-change-windows); the setting has no screen yet (C2611). The tool prints the
# windows before and after, refuses unless the windows set now are exactly OLD (naming both),
# writes nothing when they are already NEW, and reads the new value back.
#
# Run on the NMAS host, as the operator's own user (the app's), from the checkout:
#     bash <checkout>/scripts/host-steps/c2613-no-change-windows.sh <your email>
#     bash <checkout>/scripts/host-steps/c2613-no-change-windows.sh check      # checks only
# Undo: cd <checkout> && /opt/mercury-venv/bin/python scripts/nmas-no-change-windows set \
#     --expect "$NEW" --to "$OLD" --actor <you>     (OLD and NEW as set below)
. "$(dirname "$0")/lib.sh"

ARG=${1:-}
PY=${NMAS_PY:-/opt/mercury-venv/bin/python}
TOOL="cd '$CHECKOUT' && '$PY' scripts/nmas-no-change-windows"
# Each in the tool's own form (`json.dumps(..., sort_keys=True)`), so a plain compare holds.
OLD='[{"end": "09:10", "reason": "the hypervisor'"'"'s nightly backup (measured 2026-10-04 and 05)", "start": "08:30"}]'
NEW='[{"end": "10:30", "reason": "the hypervisor'"'"'s nightly backup, 02:30 to 03:30 America/Denver, both seasons (C2613; UTC only, C2614)", "start": "08:30"}]'
export OLD NEW

plan "run as the operator's own user, not root" \
     "the windows set are 08:30 to 10:30 UTC, exactly"
not_root

if [ "$ARG" != check ]; then
    [ -n "$ARG" ] || { echo "Name who is accountable: bash $0 <your email>"; exit 1; }
    # Prints the windows before and after; exits 1, writing nothing, unless they were OLD.
    step "write the windows through write_settings (refused unless the windows set now are the expected ones)" \
        "$TOOL set --expect \"\$OLD\" --to \"\$NEW\" --actor '$ARG'"
fi
check "the windows set are 08:30 to 10:30 UTC, exactly" eq "$NEW" "$TOOL show"
summary
