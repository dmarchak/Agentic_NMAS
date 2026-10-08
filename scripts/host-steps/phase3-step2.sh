#!/usr/bin/env bash
# Phase 3 step 2's host side (docs/NSOT_PHASE3_RETIRE_OXIDIZED.md section 5): remove the
# Oxidized credential helper, its pin and its sudoers entry. The operator's, on the NMAS host:
#     bash <checkout>/scripts/host-steps/phase3-step2.sh
. "$(dirname "$0")/lib.sh"

plan "run as the operator's own user, not root" \
     "the running release treats the helper as retired" \
     "sudoers still parses" \
     "sudo lists no Oxidized helper" \
     "the helper is gone" \
     "its pin is gone" \
     "its sudoers file is gone"

not_root
check "the running release treats the helper as retired" ge 1 \
    "grep -c 'OXIDIZED_RETIRED' '$CHECKOUT/modules/host_steps.py'"

step "remove the sudoers entry" 'sudo rm -f /etc/sudoers.d/nmas-oxidized-cred'
step "remove the helper and its pin" \
    'sudo rm -f /usr/local/sbin/nmas-oxidized-cred /etc/nmas/oxidized-cred.conf'

check "sudoers still parses" rc0 "" 'sudo visudo -c'
check "sudo lists no Oxidized helper" eq "0" 'sudo -n -l | grep -c oxidized-cred || true'
check "the helper is gone" eq "absent" \
    '[ -e /usr/local/sbin/nmas-oxidized-cred ] && echo present || echo absent'
check "its pin is gone" eq "absent" \
    '[ -e /etc/nmas/oxidized-cred.conf ] && echo present || echo absent'
check "its sudoers file is gone" eq "absent" \
    'sudo test -e /etc/sudoers.d/nmas-oxidized-cred && echo present || echo absent'
summary
