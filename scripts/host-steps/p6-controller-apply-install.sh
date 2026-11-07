#!/usr/bin/env bash
# P6 (the SDN platform design revision 6, section 10 H, change C and C2; section 16b, S3 step 1):
# install the controller's apply script, move the controller's unit to User=ryu, and only then
# hand /opt/ryu-apps to the deploy account. ORDER MATTERS (C2): while Ryu runs as root, a folder
# of code it executes that `mercury` can write would make `mercury` root-equivalent at the next
# restart, so the folder changes owner only after the checks read User=ryu, active, every
# switch back, and the script refusing with no request.
#
# Needs first (S1, 16b step 5): the `mercury` and `ryu` accounts and the one sudoers line,
#     mercury ALL=(root) NOPASSWD: /usr/local/sbin/mercury-ryu-apply ""
# in /etc/sudoers.d/mercury-ryu-apply. And, on the NMAS host BEFORE this runs, the restart's
# window: nmas-planned-restart <network> <controller> --minutes 20 --why "S3: Ryu to User=ryu" \
#     --by <operator>
#
# Run ON THE CONTROLLER HOST, as the operator's own user (each step uses sudo), from a copy of
# the release holding scripts/host-steps/ and deploy/controller/:
#     bash <release>/scripts/host-steps/p6-controller-apply-install.sh <ryu unit> <ryu-manager> <switches>
# <ryu unit> is the unit S1 wrote down (e.g. ryu-manager.service), <ryu-manager> the absolute path
# its ExecStart runs, <switches> how many datapaths connect (five in lab9).
# Undo (step 1 only, the folder untouched): sudo rm /etc/systemd/system/<ryu unit>.d/mercury.conf
#     && sudo systemctl daemon-reload && sudo systemctl restart <ryu unit>
. "$(dirname "$0")/lib.sh"

UNIT=${1:-}
MANAGER=${2:-}
SWITCHES=${3:-}
RELEASE=$CHECKOUT
SCRIPT_SRC=$RELEASE/deploy/controller/mercury-ryu-apply
DROPIN_SRC=$RELEASE/deploy/controller/mercury.conf
INSTALLED=/usr/local/sbin/mercury-ryu-apply
DROPIN_DIR=/etc/systemd/system/$UNIT.d
SUDOERS_LINE='mercury ALL=(root) NOPASSWD: /usr/local/sbin/mercury-ryu-apply ""'
# The reconnect bound: 2.5 x the slowest switch's reconnect. A PLACEHOLDER until S1's reboot
# test measures it (modules/apps/post_check.RECONNECT: the operator's 90 s figure, unmeasured).
BOUND_S=225
export UNIT MANAGER SWITCHES INSTALLED DROPIN_DIR SUDOERS_LINE BOUND_S

if ! [[ "$UNIT" =~ ^[A-Za-z0-9][A-Za-z0-9_.@-]{0,63}\.service$ ]] \
        || ! [[ "$MANAGER" =~ ^/[A-Za-z0-9_./-]+$ ]] || ! [[ "$SWITCHES" =~ ^[0-9]+$ ]]; then
    echo "Usage: bash $0 <ryu unit>.service <absolute ryu-manager path> <number of switches>"
    exit 1
fi

plan "run as the operator's own user, not root" \
     "the release holds the script and the first drop-in" \
     "the sudoers line is the one line, and visudo -c parses every file" \
     "the unit's ExecStart runs the named ryu-manager, with no path under /opt/ryu-apps or /home" \
     "the installed script is root-owned 0755 and is the release's, rendered" \
     "the unit runs as User=ryu and is active" \
     "Ryu lists every switch within the bound" \
     "with no request, the script refuses by name (no request)" \
     "/opt/ryu-apps and its .apply folder are owned by mercury mercury" \
     "mercury cannot write the drop-in folder or /usr/local/sbin"
not_root

check "the release holds the script and the first drop-in" rc0 "" \
    "[ -f '$SCRIPT_SRC' ] && [ -f '$DROPIN_SRC' ] && grep -qx 'User=ryu' '$DROPIN_SRC'"
check "the sudoers line is the one line, and visudo -c parses every file" rc0 "" \
    'sudo visudo -c >/dev/null && [ "$(sudo cat /etc/sudoers.d/mercury-ryu-apply | grep -v "^#" | grep -v "^$")" = "$SUDOERS_LINE" ]'
check "the unit's ExecStart runs the named ryu-manager, with no path under /opt/ryu-apps or /home" rc0 "" \
    'got=$(systemctl show -p ExecStart "$UNIT"); printf "%s" "$got" | grep -qF "path=$MANAGER ;" && ! printf "%s" "$got" | grep -qE "/opt/ryu-apps|/home"'

# Rendered into a fresh folder, then installed by name (never a glob).
WORK=$(mktemp -d)
export WORK
step "render the script for this host (its unit and its ryu-manager), into $WORK" \
    'sed -e "s|^RYU_UNIT = \"@RYU_UNIT@\"$|RYU_UNIT = \"$UNIT\"|" -e "s|^RYU_MANAGER = \"@RYU_MANAGER@\"$|RYU_MANAGER = \"$MANAGER\"|" '"'$SCRIPT_SRC'"' > "$WORK/mercury-ryu-apply" && ! grep -q "@RYU_" "$WORK/mercury-ryu-apply"'
step "install the script root-owned, 0755" \
    'sudo install -o root -g root -m 0755 "$WORK/mercury-ryu-apply" "$INSTALLED"'
check "the installed script is root-owned 0755 and is the release's, rendered" rc0 "" \
    '[ "$(stat -c "%U:%G %a" "$INSTALLED")" = "root:root 755" ] && sudo cmp -s "$WORK/mercury-ryu-apply" "$INSTALLED"'

ON_FAIL_WHAT="put the unit back as it was (the folder untouched)"
ON_FAIL="sudo rm -f '$DROPIN_DIR/mercury.conf' && sudo systemctl daemon-reload && sudo systemctl restart '$UNIT'"
step "install the first drop-in (User=ryu only)" \
    "sudo install -d -o root -g root -m 0755 '$DROPIN_DIR' && sudo install -o root -g root -m 0644 '$DROPIN_SRC' '$DROPIN_DIR/mercury.conf'"
step "reload systemd and restart the unit" \
    'sudo systemctl daemon-reload && sudo systemctl restart "$UNIT"'
check "the unit runs as User=ryu and is active" eq "$(printf 'User=ryu\nActiveState=active')" \
    'sleep 5; systemctl show -p User -p ActiveState "$UNIT" | sort -r'
check "Ryu lists every switch within the bound" rc0 "" \
    'for i in $(seq 1 $((BOUND_S / 5))); do n=$(curl -s --max-time 4 http://127.0.0.1:8080/stats/switches | python3 -c "import json,sys; print(len(json.load(sys.stdin)))" 2>/dev/null); [ "${n:-0}" -ge "$SWITCHES" ] && exit 0; sleep 5; done; echo "only ${n:-0} of $SWITCHES after $BOUND_S s (a placeholder bound, S1 unmeasured)"; exit 1'
check "with no request, the script refuses by name (no request)" has "no request" \
    'sudo -u mercury sudo -n "$INSTALLED"; true'
ON_FAIL=""

# Only now, with User=ryu read back: the folder changes owner (C2).
step "hand /opt/ryu-apps and its .apply folder to the deploy account" \
    'sudo install -d -o mercury -g mercury -m 0755 /opt/ryu-apps && sudo install -d -o mercury -g mercury -m 0700 /opt/ryu-apps/.apply'
check "/opt/ryu-apps and its .apply folder are owned by mercury mercury" eq "mercury:mercury 755 mercury:mercury 700" \
    'echo $(stat -c "%U:%G %a" /opt/ryu-apps /opt/ryu-apps/.apply)'
check "mercury cannot write the drop-in folder or /usr/local/sbin" eq "no no" \
    'echo $(sudo -u mercury test -w "$DROPIN_DIR" && echo yes || echo no) $(sudo -u mercury test -w /usr/local/sbin && echo yes || echo no)'
rm -r "$WORK"
summary
