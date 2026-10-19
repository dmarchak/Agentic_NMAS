#!/usr/bin/env bash
# C1346: the firewall admits TFTP (udp/69, the ZTP responder) from each relayed ZTP subnet
# Mercury holds. ufw admits udp/69 from the management subnet only (docs/DEPLOY_LINUX.md, the
# responder's section), so a device behind a relay asks and is never answered. Idempotent: a
# rule ufw already has is skipped, and a run with every subnet admitted changes nothing.
#   1. the relayed ZTP subnets, from Mercury's IPv4 subnet file (scripts/nmas-ztp-firewall);
#   2. the responder's interface, from its installed socket unit (BindToDevice=);
#   3. one `ufw allow in on <interface> proto udp from <prefix> to any port 69` each;
#   4. `ufw status` read back: every prefix admitted on that interface;
#   5. what ufw admits recorded beside the ZTP fragment, for job health's `ztp-firewall` row (this
#      host's app cannot read ufw; the record names when the step read it).
# Run on the NMAS host, as the operator's own user (sudo is asked for ufw):
#     bash <checkout>/scripts/host-steps/c1346-ztp-relayed-firewall.sh
. "$(dirname "$0")/lib.sh"

PY=${NMAS_PY:-/opt/mercury-venv/bin/python}
TOOL="cd '$CHECKOUT' && '$PY' scripts/nmas-ztp-firewall"
WORK=$(mktemp -d)

plan "run as the operator's own user, not root" \
     "the responder's socket names its interface" \
     "Mercury's subnet file names the relayed ZTP subnets" \
     "ufw is active" \
     "udp/69 is admitted from every relayed ZTP subnet on the responder's interface" \
     "the record of what ufw admits reads back and admits every relayed ZTP subnet"

not_root
check "the responder's socket names its interface" re '^[A-Za-z0-9._@-]+$' "$TOOL interface"
IFACE=$(bash -o pipefail -c "$TOOL interface")
check "Mercury's subnet file names the relayed ZTP subnets" rc0 0 \
    "$TOOL prefixes > '$WORK/prefixes' && echo \"\$(wc -l < '$WORK/prefixes') subnet(s)\" && cat '$WORK/prefixes'"
check "ufw is active" has "Status: active" "sudo ufw status"
step "admit udp/69 from each relayed ZTP subnet on $IFACE (ufw skips a rule it has)" \
    "while read -r p; do [[ \"\$p\" =~ ^[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+/[0-9]+\$ ]] || { echo \"not a prefix: \$p\"; exit 1; }; \
       sudo ufw allow in on '$IFACE' proto udp from \"\$p\" to any port 69 comment 'NMAS ZTP responder, relayed subnet (C1346)' || exit 1; \
     done < '$WORK/prefixes'"
check "udp/69 is admitted from every relayed ZTP subnet on the responder's interface" rc0 0 \
    "sudo ufw status | ( $TOOL check )"
step "record what ufw admits, for job health" "sudo ufw status | ( $TOOL record )"
check "the record of what ufw admits reads back and admits every relayed ZTP subnet" rc0 0 \
    "$TOOL verify"
summary
