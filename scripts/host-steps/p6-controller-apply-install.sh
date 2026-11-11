#!/usr/bin/env bash
# P6 (the SDN platform design revision 6, section 10 H, change C and C2; section 16b, S3 step 1):
# install the controller's apply script, move the controller's unit to User=ryu when it is not
# there already, and only then hand /opt/ryu-apps to the deploy account. ORDER MATTERS (C2):
# while Ryu runs as root, a folder of code it executes that `mercury` can write would make
# `mercury` root-equivalent at the next restart, so the folder changes owner only after the
# checks read User=ryu, active, every switch back, and the script refusing with no request.
#
# IT TAKES THE CONTROLLER AS IT IS (C2985, C2986): one argument, the unit's name; no file is
# edited by hand before or after it.
# - The unit's own command line is read by the apply script's own functions (`unit_read`): its
#   ryu-manager, where Ryu's REST answers on this host (the unit's --wsapi-host and
#   --wsapi-port, loopback only when it names none), and every app it loads. Apps the unit
#   loads from /opt/ryu-apps or anywhere else are KEPT: Mercury's deploys carry them in the
#   drop-in, each drawn in the plan as "kept: ..., not managed by Mercury", until an app of
#   the same name is deployed through Mercury. REST's bind is carried as the unit has it.
# - How many switches must come back is the number Ryu lists before anything changes.
# - Nothing is changed before every check above the first step passes, and each check that
#   fails says what it wanted and what it got.
# - It is idempotent: the script is installed again from the release; the sudoers line is
#   installed only when its file is absent (a file holding anything else is refused, never
#   written over); a mercury.conf that is already there (a deploy's, or an earlier run's) is
#   left as it is; and the unit is restarted ONLY when it does not run as User=ryu yet.
#
# Needs first: the `mercury` and `ryu` accounts (the deploy account's login is the operator's
# to create: its key or password is a secret). And, ONLY when the unit does not run as
# User=ryu yet (the script says which before it changes anything, and stops for the window
# when one is needed), the restart's window, declared before this runs (no screen declares one
# for a host step yet, C1361: scripts/nmas-planned-restart on Mercury's own host).
#
# Run ON THE CONTROLLER HOST, as the operator's own user (each step uses sudo), from a copy of
# the release holding scripts/host-steps/ and deploy/controller/:
#     bash <release>/scripts/host-steps/p6-controller-apply-install.sh <ryu unit>
# <ryu unit> is the systemd unit Ryu runs as (NetBox's config context key openflow.unit, e.g.
# ryu-manager.service); add `restart` after it once the window is declared, when the script
# says the unit must restart.
# Undo (the folder untouched): sudo rm /etc/systemd/system/<ryu unit>.d/mercury.conf
#     && sudo systemctl daemon-reload && sudo systemctl restart <ryu unit>
. "$(dirname "$0")/lib.sh"

UNIT=${1:-}
MAY_RESTART=${2:-}
RELEASE=$CHECKOUT
SCRIPT_SRC=$RELEASE/deploy/controller/mercury-ryu-apply
DROPIN_SRC=$RELEASE/deploy/controller/mercury.conf
INSTALLED=/usr/local/sbin/mercury-ryu-apply
DROPIN_DIR=/etc/systemd/system/$UNIT.d
SUDOERS_FILE=/etc/sudoers.d/mercury-ryu-apply
SUDOERS_LINE='mercury ALL=(root) NOPASSWD: /usr/local/sbin/mercury-ryu-apply ""'
# The bounds, each 2.5 x a measured time (the controller's reboot test of 2026-11-11): Ryu
# answered within 30 s of its process starting, so 75 s; every switch and link was back 21 s
# after Ryu answered, so 55 s (52.5 s taken up to a whole 5 s read). Each is counted on this
# host's uptime clock (/proc/uptime), which does not step when NTP corrects the wall clock
# after a boot (C2982, C2983), from the moment this script acts or sees the answer.
RYU_BOUND_S=75
BACK_BOUND_S=55
BOUND_WHY="2.5 x the 30 s and the 21 s measured at the controller's reboot test of 2026-11-11, on this host's uptime clock"
export UNIT SCRIPT_SRC INSTALLED DROPIN_DIR SUDOERS_FILE SUDOERS_LINE RYU_BOUND_S BACK_BOUND_S BOUND_WHY

if ! [[ "$UNIT" =~ ^[A-Za-z0-9][A-Za-z0-9_.@-]{0,63}\.service$ ]] \
        || ! [[ "$MAY_RESTART" =~ ^(restart)?$ ]]; then
    echo "Usage: bash $0 <ryu unit>.service [restart]"
    exit 1
fi

# The unit's own command line, read by the apply script's own functions (one home: what the
# install accepts is what a deploy carries). -B: no bytecode is written beside the release.
unit_read() {
    python3 -B -c 'import importlib.machinery as m, importlib.util as u, sys
l = m.SourceFileLoader("mercury_ryu_apply", sys.argv[1])
a = u.module_from_spec(u.spec_from_loader(l.name, l))
l.exec_module(a)
sys.exit(a.unit_read(sys.argv[2:]))' "$SCRIPT_SRC" "$1"
}
# How many switches Ryu lists, read where its REST is bound (-g: an IPv6 address is bracketed).
switch_count() {
    local body
    body=$(curl -g -s --max-time 4 "$REST/stats/switches") \
        || { echo "no answer from $REST/stats/switches (curl exit $?)"; return 1; }
    printf '%s' "$body" | python3 -c 'import json, sys
try:
    print(len(json.load(sys.stdin)))
except ValueError:
    print("the answer from Ryu is not a JSON list")
    sys.exit(1)'
}
uptime_s() { cut -d. -f1 /proc/uptime; }
# wait_for <what> <bound seconds> <switches wanted, or - for any answer>: a read every 5 s,
# counted on the uptime clock; a firing bound names what was read, how often, and the bound.
wait_for() {
    local what=$1 bound=$2 want=$3 start reads=0 got="" wanted="any answer"
    [ "$want" = - ] || wanted="$want switches"
    start=$(uptime_s)
    while :; do
        reads=$((reads + 1))
        if got=$(switch_count 2>&1) && [[ "$got" =~ ^[0-9]+$ ]] \
                && { [ "$want" = - ] || [ "$got" -ge "$want" ]; }; then
            echo "waited for $what: $(( $(uptime_s) - start )) s and $reads reads, $got switches"
            return 0
        fi
        if [ $(( $(uptime_s) - start )) -ge "$bound" ]; then
            echo "waited for $what: the bound of $bound s fired ($BOUND_WHY) after $reads reads of $REST/stats/switches; it wanted $wanted and the last read gave: $got"
            return 1
        fi
        sleep 5
    done
}
export -f unit_read switch_count uptime_s wait_for

plan "run as the operator's own user, not root" \
     "the release holds the script and the first drop-in" \
     "the accounts mercury and ryu exist" \
     "the sudoers file is absent or exactly the one line, and visudo -c parses every file" \
     "the unit's own command line can be carried whole" \
     "the ryu account can read every app the unit loads" \
     "Ryu lists its switches where its REST is bound, before anything changes" \
     "the unit runs as User=ryu already, or this run may restart it" \
     "the installed script is root-owned 0755 and is the release's, rendered" \
     "the sudoers line is the one line, and visudo -c parses every file" \
     "the unit runs as User=ryu and is active" \
     "Ryu answers within its start bound" \
     "every switch it listed before is back within the bound" \
     "with no request, the script refuses by name (no request)" \
     "/opt/ryu-apps and its .apply folder are owned by mercury mercury" \
     "mercury cannot write the drop-in folder or /usr/local/sbin"
not_root

# --- Every check before the first change -----------------------------------------------------
check "the release holds the script and the first drop-in" rc0 "" \
    "[ -f '$SCRIPT_SRC' ] && [ -f '$DROPIN_SRC' ] && grep -qx 'User=ryu' '$DROPIN_SRC'"
check "the accounts mercury and ryu exist" eq "" \
    'for a in mercury ryu; do id -u "$a" >/dev/null 2>&1 || echo "no account $a on this host"; done'
check "the sudoers file is absent or exactly the one line, and visudo -c parses every file" eq "ok" \
    'sudo visudo -c >/dev/null 2>&1 || { echo "visudo -c refuses the sudoers files as they are"; exit 0; }; if sudo test -e "$SUDOERS_FILE"; then [ "$(sudo cat "$SUDOERS_FILE" | grep -v "^#" | grep -v "^$")" = "$SUDOERS_LINE" ] && echo ok || echo "$SUDOERS_FILE holds something other than the one line: $SUDOERS_LINE"; else echo ok; fi'
check "the unit's own command line can be carried whole" rc0 "" \
    'unit_read "$UNIT"'
READ=$(unit_read "$UNIT")
MANAGER=$(printf '%s\n' "$READ" | sed -n 's/^manager=//p')
REST=$(printf '%s\n' "$READ" | sed -n 's/^rest=//p')
KEPT_APPS=$(printf '%s\n' "$READ" | sed -n 's/^app=//p' | tr '\n' ' ')
export MANAGER REST KEPT_APPS
echo "      $UNIT runs $MANAGER; Ryu's REST is read at $REST"
echo "      carried by every deploy: $(printf '%s\n' "$READ" | sed -n 's/^kept=//p')"
check "the ryu account can read every app the unit loads" eq "" \
    'for f in $KEPT_APPS; do sudo -u ryu test -r "$f" || echo "$f ($(stat -c "%U:%G %a" "$f" 2>&1)) cannot be read by ryu"; done'
check "Ryu lists its switches where its REST is bound, before anything changes" re '^[0-9]+$' \
    'switch_count'
SWITCHES=$(switch_count)
USER_NOW=$(systemctl show -p User "$UNIT" | sed -n 's/^User=//p')
export SWITCHES USER_NOW MAY_RESTART
echo "      Ryu lists $SWITCHES switches now; $UNIT runs as User=${USER_NOW:-(empty, root)}"
check "the unit runs as User=ryu already, or this run may restart it" eq "ok" \
    'if [ "$USER_NOW" = ryu ] || [ "$MAY_RESTART" = restart ]; then echo ok; else echo "the unit runs as User=${USER_NOW:-(empty, root)}, not ryu, so this install must restart it and every switch drops: declare the planned-restart window first (scripts/nmas-planned-restart on the host Mercury runs on), then run this again with restart after the unit name. Nothing was changed"; fi'

# --- The changes -----------------------------------------------------------------------------
# Rendered into a fresh folder, then installed by name (never a glob).
WORK=$(mktemp -d)
export WORK
step "render the script for this host (its unit and its ryu-manager), into $WORK" \
    'sed -e "s|^RYU_UNIT = \"@RYU_UNIT@\"$|RYU_UNIT = \"$UNIT\"|" -e "s|^RYU_MANAGER = \"@RYU_MANAGER@\"$|RYU_MANAGER = \"$MANAGER\"|" '"'$SCRIPT_SRC'"' > "$WORK/mercury-ryu-apply" && ! grep -q "@RYU_" "$WORK/mercury-ryu-apply"'
step "install the script root-owned, 0755" \
    'sudo install -o root -g root -m 0755 "$WORK/mercury-ryu-apply" "$INSTALLED"'
check "the installed script is root-owned 0755 and is the release's, rendered" rc0 "" \
    '[ "$(stat -c "%U:%G %a" "$INSTALLED")" = "root:root 755" ] && sudo cmp -s "$WORK/mercury-ryu-apply" "$INSTALLED"'
if sudo test -e "$SUDOERS_FILE"; then
    echo "== KEPT: $SUDOERS_FILE is there already and is the one line"
else
    step "render the sudoers line into $WORK and check it parses" \
        'printf "%s\n" "$SUDOERS_LINE" > "$WORK/mercury-ryu-apply.sudoers" && sudo visudo -cf "$WORK/mercury-ryu-apply.sudoers" >/dev/null'
    step "install the sudoers line root-owned, 0440" \
        'sudo install -o root -g root -m 0440 "$WORK/mercury-ryu-apply.sudoers" "$SUDOERS_FILE"'
fi
check "the sudoers line is the one line, and visudo -c parses every file" rc0 "" \
    'sudo visudo -c >/dev/null && [ "$(sudo cat "$SUDOERS_FILE" | grep -v "^#" | grep -v "^$")" = "$SUDOERS_LINE" ]'

if [ -e "$DROPIN_DIR/mercury.conf" ]; then
    echo "== KEPT: $DROPIN_DIR/mercury.conf is there already (a deploy's, or an earlier run's): left as it is"
else
    ON_FAIL_WHAT="put the unit back as it was (the folder untouched)"
    ON_FAIL="sudo rm -f '$DROPIN_DIR/mercury.conf' && sudo systemctl daemon-reload"
    if [ "$USER_NOW" != ryu ]; then
        ON_FAIL="$ON_FAIL && sudo systemctl restart '$UNIT'"
    fi
    step "install the first drop-in (User=ryu only)" \
        "sudo install -d -o root -g root -m 0755 '$DROPIN_DIR' && sudo install -o root -g root -m 0644 '$DROPIN_SRC' '$DROPIN_DIR/mercury.conf'"
    step "reload systemd" \
        'sudo systemctl daemon-reload'
fi
if [ "$USER_NOW" = ryu ]; then
    echo "== NO RESTART: $UNIT runs as User=ryu already, so the first drop-in changes nothing it runs"
else
    step "restart the unit, so it runs as ryu" \
        'sudo systemctl restart "$UNIT"; sleep 5'
fi
check "the unit runs as User=ryu and is active" eq "$(printf 'User=ryu\nActiveState=active')" \
    'systemctl show -p User -p ActiveState "$UNIT" | sort -r'
check "Ryu answers within its start bound" rc0 "" \
    'wait_for "Ryu to answer" "$RYU_BOUND_S" -'
check "every switch it listed before is back within the bound" rc0 "" \
    'wait_for "every switch to be back" "$BACK_BOUND_S" "$SWITCHES"'
check "with no request, the script refuses by name (no request)" has "no request" \
    'sudo -u mercury sudo -n "$INSTALLED"; true'
ON_FAIL=""

# Only now, with User=ryu read back: the folder changes owner (C2). What the unit loads from it
# today stays where it is, root-owned; the folder itself is the deploy account's from here.
step "hand /opt/ryu-apps and its .apply folder to the deploy account" \
    'sudo install -d -o mercury -g mercury -m 0755 /opt/ryu-apps && sudo install -d -o mercury -g mercury -m 0700 /opt/ryu-apps/.apply'
check "/opt/ryu-apps and its .apply folder are owned by mercury mercury" eq "mercury:mercury 755 mercury:mercury 700" \
    'echo $(stat -c "%U:%G %a" /opt/ryu-apps /opt/ryu-apps/.apply)'
check "mercury cannot write the drop-in folder or /usr/local/sbin" eq "no no" \
    'echo $(sudo -u mercury test -w "$DROPIN_DIR" && echo yes || echo no) $(sudo -u mercury test -w /usr/local/sbin && echo yes || echo no)'
rm -r "$WORK"
summary
