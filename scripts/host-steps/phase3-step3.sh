#!/usr/bin/env bash
# Phase 3 step 3 (docs/NSOT_PHASE3_RETIRE_OXIDIZED.md section 5): call the lab's startup sync by
# its new name. Measured 2026-10-08: ~/bin/clab-sync changes to ~/lab-configs and runs
# ./oxidized-to-config.sh, a link into the checkout that already resolves to
# clab-startup-sync.sh; so this changes the name it is called by, not what runs. Lab tooling,
# removed once run. The operator's, on the NMAS host:
#     bash <checkout>/scripts/host-steps/phase3-step3.sh
. "$(dirname "$0")/lib.sh"

export WRAPPER="$HOME/bin/clab-sync" LABDIR="$HOME/lab-configs"
export TARGET="$CHECKOUT/scripts/clab-startup-sync.sh"
export BACKUP="$HOME/bin/clab-sync.before-phase3"
OLD='./oxidized-to-config.sh --yes'
NEW='./clab-startup-sync.sh --yes'

plan "run as the operator's own user, not root" \
     "the checkout holds the renamed sync script" \
     "the wrapper ends with the old name or already the new" \
     "the wrapper's last line is the new name" \
     "only the last line changed" \
     "the new name links to the checkout's script" \
     "the sync ran and succeeded" \
     "it built from an earned baseline and validated every file" \
     "it refused nothing"

not_root
check "the checkout holds the renamed sync script" eq "yes" '[ -x "$TARGET" ] && echo yes'
check "the wrapper ends with the old name or already the new" re "^(\\./oxidized-to-config\\.sh|\\./clab-startup-sync\\.sh) --yes\$" \
    'tail -n 1 "$WRAPPER"'
echo "== the wrapper NOW:"
cat "$WRAPPER"

step "keep a copy of the wrapper as it was" '[ -e "$BACKUP" ] || cp -p "$WRAPPER" "$BACKUP"'
step "link the new name beside the old one" 'ln -sfn "$TARGET" "$LABDIR/clab-startup-sync.sh"'
step "call the new name" "sed -i 's#^\\./oxidized-to-config\\.sh --yes\$#./clab-startup-sync.sh --yes#' \"\$WRAPPER\""
echo "== the wrapper AFTER:"
cat "$WRAPPER"

check "the wrapper's last line is the new name" eq "$NEW" 'tail -n 1 "$WRAPPER"'
check "only the last line changed" eq "2" \
    'diff "$BACKUP" "$WRAPPER" | grep -c "^[<>]" || true'
check "the new name links to the checkout's script" eq "$(readlink -f "$TARGET")" \
    'readlink -f "$LABDIR/clab-startup-sync.sh"'

export STARTED
STARTED=$(date +%s)
step "run the sync once" 'sudo systemctl start clab-sync.service'
# A oneshot unit returns when the run ends; otherwise wait for it. Bounded at 10 minutes: the
# run's length was not measured, so the bound is generous and says so when it fires.
step "wait for the run to end" \
    'for i in $(seq 1 120); do s=$(systemctl show clab-sync.service -p ActiveState --value); [ "$s" = active ] || [ "$s" = activating ] || exit 0; sleep 5; done; echo "still running after 10 minutes"; exit 1'
check "the sync ran and succeeded" eq "success 0" \
    'echo "$(systemctl show clab-sync.service -p Result --value) $(systemctl show clab-sync.service -p ExecMainStatus --value)"'
check "it built from an earned baseline and validated every file" has "All files converted and validated." \
    'journalctl -u clab-sync.service --since "@$STARTED" --no-pager'
check "it refused nothing" lacks "REFUSED" \
    'journalctl -u clab-sync.service --since "@$STARTED" --no-pager | grep -E "REFUSED|PROBLEMS" || true'
echo "   ~/lab-configs/oxidized-to-config.sh stays one release (the repository keeps the old name until then)."
summary
