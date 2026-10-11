#!/usr/bin/env bash
# C663 step 3b's host side, AFTER the release that renames the topology renderer: it carried
# the lab's name (rcn-topology) and is now nmas-topology. The unit is rendered from the one
# installed (its user, restart policy and ordering kept), into a fresh folder, and installed
# by name; the old unit and link are removed once the new service runs. Run on the NMAS host,
# as the operator's own user:
#     bash <checkout>/scripts/host-steps/c663-step3b-topology.sh
. "$(dirname "$0")/lib.sh"

OLD_UNIT=/etc/systemd/system/rcn-topology.service
NEW_UNIT=/etc/systemd/system/nmas-topology.service
OLD_LINK=/usr/local/bin/rcn-topology.py
NEW_LINK=/usr/local/bin/nmas-topology.py
SOURCE="$CHECKOUT/deploy/topology/nmas-topology.py"
WORK=$(mktemp -d)

plan "run as the operator's own user, not root" \
     "this release's renderer is in the checkout" \
     "the new unit runs the new link" \
     "the new link is the checkout's renderer" \
     "nmas-topology.service is active" \
     "it answers on its port" \
     "the old unit is gone" \
     "the old link is gone"

not_root
check "this release's renderer is in the checkout" eq "present" \
    "[ -f '$SOURCE' ] && echo present || echo absent"

step "render the new unit from the installed one, into $WORK" \
    "sed -e 's#^ExecStart=.*#ExecStart=/usr/bin/python3 $NEW_LINK#' \
         -e 's#^Description=.*#Description=Mercury LLDP topology renderer#' \
         '$OLD_UNIT' > '$WORK/nmas-topology.service' && cat '$WORK/nmas-topology.service'"
step "install the new unit and link by name" \
    "sudo install -m 0644 '$WORK/nmas-topology.service' '$NEW_UNIT' \
     && sudo ln -sfn '$SOURCE' '$NEW_LINK'"
step "stop the old service and start the new one" \
    "sudo systemctl disable --now rcn-topology.service && sudo systemctl daemon-reload \
     && sudo systemctl enable --now nmas-topology.service"
step "remove the old unit and link" \
    "sudo rm -f '$OLD_UNIT' '$OLD_LINK' && sudo systemctl daemon-reload"

check "the new unit runs the new link" has "$NEW_LINK" \
    "systemctl cat nmas-topology.service | grep '^ExecStart='"
check "the new link is the checkout's renderer" eq "$(readlink -f "$SOURCE")" \
    "readlink -f '$NEW_LINK'"
check "nmas-topology.service is active" eq "active" "systemctl is-active nmas-topology.service"
check "it answers on its port" eq "200" \
    "sleep 3; curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8088/graph.json"
check "the old unit is gone" eq "absent" "[ -e '$OLD_UNIT' ] && echo present || echo absent"
check "the old link is gone" eq "absent" "[ -e '$OLD_LINK' ] && echo present || echo absent"
summary
