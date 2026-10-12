#!/usr/bin/env bash
# 7.8's host side for the topology service, AFTER the release that removes its renderer
# (deploy/topology/nmas-topology.py): OBSERVE › Topology, over the topology-graph reader,
# replaced it, and nothing in Mercury reads the service any more. The service still runs the
# copy it loaded and its link now points at nothing, so it is stopped and disabled, then its
# unit and link are removed by name. Run on the NMAS host, as the operator's own user:
#     bash <checkout>/scripts/host-steps/topology-service-removal.sh
. "$(dirname "$0")/lib.sh"

UNIT=nmas-topology.service
UNIT_FILE=/etc/systemd/system/nmas-topology.service
LINK=/usr/local/bin/nmas-topology.py
SOURCE="$CHECKOUT/deploy/topology/nmas-topology.py"

plan "run as the operator's own user, not root" \
     "this release no longer carries the renderer" \
     "the service is not running" \
     "the service is not enabled" \
     "the unit file is gone" \
     "the link is gone" \
     "nothing answers on its port"

not_root
check "this release no longer carries the renderer" eq "absent" \
    "[ -e '$SOURCE' ] && echo present || echo absent"

step "stop and disable the service" \
    "if systemctl cat $UNIT >/dev/null 2>&1; then sudo systemctl disable --now $UNIT; fi"
step "remove the unit file and the link by name" \
    "sudo rm -f '$UNIT_FILE' '$LINK' && sudo systemctl daemon-reload"

check "the service is not running" eq "stopped" \
    "systemctl is-active --quiet $UNIT && echo running || echo stopped"
check "the service is not enabled" eq "off" \
    "systemctl is-enabled --quiet $UNIT 2>/dev/null && echo enabled || echo off"
check "the unit file is gone" eq "absent" \
    "[ -e '$UNIT_FILE' ] && echo present || echo absent"
check "the link is gone" eq "absent" \
    "[ -L '$LINK' ] || [ -e '$LINK' ] && echo present || echo absent"
check "nothing answers on its port" eq "000" \
    "curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://127.0.0.1:8088/graph.json || true"
summary
