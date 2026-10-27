#!/usr/bin/env bash
# C1917: NetBox (Docker-published on 0.0.0.0:8000 and [::]:8000, which bypass ufw's rules for
# IPv4) admits only the operator's laptop from the network (the operator, 2026-10-27, after
# C1916's Loki change). IPv4 is filtered in DOCKER-USER, the chain Docker leaves to the host,
# matching the connection's original destination port (8000) so NetBox's own containers, which
# talk to it on 8080 inside their network, are untouched; the host itself reaches NetBox by its
# own address (Mercury's netbox_url), which never passes FORWARD, so the rule cannot cut it off.
# IPv6 reaches NetBox through docker-proxy, a host process, so ufw's INPUT governs it: denied.
# The rules live in a marked block of /etc/ufw/after.rules (a copy kept beside it first), so a
# reboot or `ufw reload` keeps them.
# Run on the NMAS host, as the operator's own user (sudo is asked for ufw and iptables):
#     bash <checkout>/scripts/host-steps/c1917-netbox-docker-user.sh <laptop IPv4>   # apply, check
#     bash <checkout>/scripts/host-steps/c1917-netbox-docker-user.sh check <laptop IPv4>
#     bash <checkout>/scripts/host-steps/c1917-netbox-docker-user.sh rollback
# After apply: from the laptop NetBox answers; from any other LAN address it times out.
. "$(dirname "$0")/lib.sh"

MODE=apply
case ${1:-} in check|rollback) MODE=$1; shift ;; esac
LAPTOP=${1:-}
RULES=/etc/ufw/after.rules
BEGIN="# BEGIN C1917: NetBox from the operator's laptop only"
END="# END C1917"
export RULES BEGIN END LAPTOP

plan "run as the operator's own user, not root" \
     "the laptop's address is one IPv4 address" \
     "after.rules holds the C1917 block once" \
     "DOCKER-USER admits the laptop to 8000 before it drops the rest" \
     "ufw denies 8000/tcp over IPv6" \
     "NetBox still answers on the host's own address"
not_root

if [ "$MODE" = rollback ]; then
    step "remove the C1917 block from after.rules (a copy kept as after.rules.before-c1917-rollback)" \
        'sudo cp -p "$RULES" "$RULES.before-c1917-rollback" && strip_marked "$RULES" "$BEGIN" "$END" | sudo tee "$RULES.new" >/dev/null && sudo mv "$RULES.new" "$RULES"'
    step "drop the IPv6 deny and reload ufw" 'sudo ufw --force delete deny proto tcp from any to any port 8000 >/dev/null 2>&1; sudo ufw reload'
    step "flush DOCKER-USER back to Docker's own (RETURN)" 'sudo iptables -F DOCKER-USER && sudo iptables -A DOCKER-USER -j RETURN'
    not_asked "the laptop's address is one IPv4 address" "rollback needs no address"
    not_asked "after.rules holds the C1917 block once" "rollback removes it"
    not_asked "DOCKER-USER admits the laptop to 8000 before it drops the rest" "rollback removes it"
    not_asked "ufw denies 8000/tcp over IPv6" "rollback removes it"
    check "NetBox still answers on the host's own address" re '^(200|302)$' \
        'curl -s -o /dev/null -w "%{http_code}" -m 5 http://$(hostname -I | cut -d" " -f1):8000/login/'
    summary
    exit 0
fi

check "the laptop's address is one IPv4 address" re '^([0-9]{1,3}\.){3}[0-9]{1,3}$' 'printf "%s" "$LAPTOP"'
if [ "$MODE" = apply ]; then
    step "keep a copy of after.rules" 'sudo cp -p "$RULES" "$RULES.before-c1917"'
    ON_FAIL='sudo cp -p "$RULES.before-c1917" "$RULES" && sudo ufw reload'
    ON_FAIL_WHAT="put after.rules back and reload ufw"
    step "append the C1917 block to after.rules (unless it is there)" \
        'sudo grep -qxF "$BEGIN" "$RULES" || printf "\n%s\n*filter\n:DOCKER-USER - [0:0]\n-A DOCKER-USER -p tcp -m conntrack --ctorigdstport 8000 --ctdir ORIGINAL -s %s -j RETURN\n-A DOCKER-USER -p tcp -m conntrack --ctorigdstport 8000 --ctdir ORIGINAL -j DROP\n-A DOCKER-USER -j RETURN\nCOMMIT\n%s\n" "$BEGIN" "$LAPTOP" "$END" | sudo tee -a "$RULES" >/dev/null'
    step "deny 8000/tcp over IPv6 (docker-proxy listens on [::]:8000) and reload ufw" \
        'sudo ufw deny proto tcp from any to any port 8000 comment "C1917: NetBox from the laptop only" >/dev/null && sudo ufw reload'
fi
check "after.rules holds the C1917 block once" eq "1" 'sudo grep -cxF "$BEGIN" "$RULES"'
check "DOCKER-USER admits the laptop to 8000 before it drops the rest" re "-s ${LAPTOP//./\\.}/32 [^|]*--ctorigdstport 8000 [^|]*-j RETURN \| [^|]*--ctorigdstport 8000 [^|]*-j DROP" \
    'sudo iptables -S DOCKER-USER | grep -- "-A DOCKER-USER" | tr "\n" "|" | sed "s/|/ | /g"'
check "ufw denies 8000/tcp over IPv6" has "8000/tcp (v6)" 'sudo ufw status | grep "8000/tcp (v6)" | grep DENY'
check "NetBox still answers on the host's own address" re '^(200|302)$' \
    'curl -s -o /dev/null -w "%{http_code}" -m 5 http://$(hostname -I | cut -d" " -f1):8000/login/'
summary
