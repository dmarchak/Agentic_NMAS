#!/usr/bin/env bash
# C789 (docs/OPEN_FINDINGS.md): the one trap that socket-activated snmptrapd (2026-10-09 17:41:18
# UTC, the service's own start) was logged with its sender `<UNKNOWN>`, so it got no `device`
# label; every trap since, with snmptrapd already running, named its device (the operator's port
# flap, 2026-10-15: both traps device="s1"). n=1 each way. snmptrapd.service is `static` and
# started only by snmptrapd.socket, so after every boot the FIRST trap is the activating one.
#
# This makes multi-user.target want snmptrapd.service (`systemctl add-wants`: a symlink in
# /etc/systemd/system/multi-user.target.wants/, nothing else), so at boot snmptrapd starts and
# takes its sockets from snmptrapd.socket before any trap arrives. Nothing restarts now; the
# running snmptrapd and its socket are left as they are. The proof is the next boot's first
# trap naming its device (C789 stays UNKNOWN until then). Undo, by hand:
#     sudo rm /etc/systemd/system/multi-user.target.wants/snmptrapd.service && sudo systemctl daemon-reload
#
# The operator's, on the NMAS host, as their own user (sudo asked once):
#     bash <checkout>/scripts/host-steps/c789-snmptrapd-at-boot.sh
. "$(dirname "$0")/lib.sh"

export LINK=/etc/systemd/system/multi-user.target.wants/snmptrapd.service
ON_FAIL_WHAT="the wants link removed again"
ON_FAIL="sudo rm -f '$LINK' && sudo systemctl daemon-reload && echo 'the link is gone'"

plan "run as the operator's own user, not root" \
     "snmptrapd.socket is enabled and snmptrapd.service is started by it" \
     "nothing yet starts snmptrapd.service at boot" \
     "multi-user.target wants snmptrapd.service" \
     "snmptrapd and its socket still run, not restarted"

not_root
check "snmptrapd.socket is enabled and snmptrapd.service is started by it" eq "enabled snmptrapd.socket" \
    'echo "$(systemctl is-enabled snmptrapd.socket) $(systemctl show snmptrapd.service -p TriggeredBy --value)"'
check "nothing yet starts snmptrapd.service at boot" eq "absent" \
    '[ -e "$LINK" ] && echo present || echo absent'
export SINCE
SINCE=$(systemctl show snmptrapd.service -p ActiveEnterTimestamp --value)
step "multi-user.target wants snmptrapd.service" \
    'sudo systemctl add-wants multi-user.target snmptrapd.service'
check "multi-user.target wants snmptrapd.service" eq "snmptrapd.service" \
    'systemctl show multi-user.target -p Wants --value | tr " " "\n" | grep -x snmptrapd.service'
ON_FAIL=""
check "snmptrapd and its socket still run, not restarted" eq "active active same" \
    'echo "$(systemctl is-active snmptrapd.service) $(systemctl is-active snmptrapd.socket) $([ "$(systemctl show snmptrapd.service -p ActiveEnterTimestamp --value)" = "$SINCE" ] && echo same || echo restarted)"'
summary
