#!/usr/bin/env bash
# C3078 (the operator's approval and conditions, 2026-11-11): install the collector's close
# helper on Mercury's host: the root-owned script, its root-owned configuration and its one
# sudoers line. The helper closes ONE established telemetry session the collector still holds
# after its device gave it up, and only a session from a peer its configuration lists to the
# one listener its configuration names (deploy/collector/mercury-collector-close: its header
# is the whole of what it does and refuses).
#
# - Every check runs before the first change, and each that fails says what it wanted and what
#   it got: the release holds the helper; `ss` is root's and names -K; the kernel can destroy a
#   socket (where its config can be read; said when it cannot); the service user exists; the
#   collector listens on the listener, on an IPv4 socket; the configuration renders by the
#   helper's own rules (each peer an IPv4 address, at least one); what is already there is as
#   this step leaves it; the sudoers file is absent or exactly the one line, and `visudo -c`
#   parses every file.
# - Then it installs the helper (root:root 0755) from the release, renders the configuration
#   into a fresh folder and installs it by name (root:root 0644), makes the outcome's folder
#   (root's) and the request's (the service user's, 0700), and installs the sudoers line
#   (0440) when its file is absent, after `visudo -cf` has parsed the rendered file.
# - Then it proves the copy where it landed: two DRY RUNS as the service user, through sudo's
#   one line: a peer of the list (the helper answers no_match or would_close) and an address
#   that is not in it (the helper refuses it), each outcome printed. A dry run closes nothing.
# - It restarts nothing and closes nothing. Run again it installs the same three files: that
#   is how the peer list is regenerated after a device's telemetry is added or re-addressed.
#
# Run ON MERCURY'S HOST, as the operator's own user (each step uses sudo), from the release:
#     scripts/nmas-collector-peers <listener address>:<port> > <peers file>     (as Mercury's user)
#     bash <release>/scripts/host-steps/c3078-collector-close-install.sh \
#         <service user> <listener address>:<port> <peers file>
# <service user> is the account Mercury runs as; <listener address>:<port> the address and
# port the collector listens on, as the devices' receivers name it; <peers file> one IPv4
# address a line, what scripts/nmas-collector-peers printed.
# Undo: sudo rm /usr/local/sbin/mercury-collector-close /etc/mercury/collector-close.conf
#     /etc/sudoers.d/mercury-collector-close
. "$(dirname "$0")/lib.sh"

SERVICE_USER=${1:-}
LISTENER=${2:-}
PEERS_FILE=${3:-}
RELEASE=$CHECKOUT
HELPER_SRC=$RELEASE/deploy/collector/mercury-collector-close
INSTALLED=/usr/local/sbin/mercury-collector-close
CONF_DIR=/etc/mercury
CONF=$CONF_DIR/collector-close.conf
STATE_DIR=/var/lib/mercury-collector-close
REQUEST_DIR=$STATE_DIR/request
REQUEST=$REQUEST_DIR/request.json
SUDOERS_FILE=/etc/sudoers.d/mercury-collector-close
SUDOERS_LINE="$SERVICE_USER ALL=(root) NOPASSWD: /usr/local/sbin/mercury-collector-close \"\""
PYTHON=/usr/bin/python3

if ! [[ "$SERVICE_USER" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]] || [ "$SERVICE_USER" = root ] \
        || [ -z "$LISTENER" ] || [ -z "$PEERS_FILE" ] || [ $# -ne 3 ]; then
    echo "Usage: bash $0 <service user> <listener address>:<port> <peers file>"
    exit 1
fi
L_ADDR=${LISTENER%:*}
L_PORT=${LISTENER##*:}
# `ss` by its real path, found here and written into the configuration: the helper runs that
# file and never looks one up.
SS=$(readlink -f "$(command -v ss 2>/dev/null)" 2>/dev/null)
KCONF=/boot/config-$(uname -r)
export SERVICE_USER LISTENER PEERS_FILE HELPER_SRC INSTALLED CONF_DIR CONF STATE_DIR \
    REQUEST_DIR REQUEST SUDOERS_FILE SUDOERS_LINE PYTHON L_ADDR L_PORT SS KCONF

# The configuration's text, by the helper's own functions loaded from the release (one home:
# what the install writes is what the helper accepts). -I: nothing of the caller's environment
# or folder is imported; -B: no bytecode is written beside the release.
render_conf() {
    "$PYTHON" -I -B -c 'import importlib.machinery as m, importlib.util as u, sys
l = m.SourceFileLoader("mercury_collector_close", sys.argv[1])
a = u.module_from_spec(u.spec_from_loader(l.name, l))
l.exec_module(a)
sys.exit(a.render(sys.argv[2:]))' "$HELPER_SRC" "$SERVICE_USER" "$LISTENER" "$SS" < "$PEERS_FILE"
}
# What is already there and is not as this step leaves it, one line each; nothing when all is.
state_problems() {
    local p
    for p in "$CONF_DIR" "$STATE_DIR"; do
        if [ -e "$p" ] || [ -L "$p" ]; then
            [ "$(stat -c "%F %U:%G %a" "$p")" = "directory root:root 755" ] \
                || echo "$p is $(stat -c "%F %U:%G %a" "$p"), not a directory root:root 755"
        fi
    done
    if [ -e "$REQUEST_DIR" ] || [ -L "$REQUEST_DIR" ]; then
        [ "$(stat -c "%F %U %a" "$REQUEST_DIR")" = "directory $SERVICE_USER 700" ] \
            || echo "$REQUEST_DIR is $(stat -c "%F %U %a" "$REQUEST_DIR"), not a directory of $SERVICE_USER's, mode 700"
    fi
    if [ -e "$CONF" ] || [ -L "$CONF" ]; then
        [ "$(stat -c "%F %U:%G %a" "$CONF")" = "regular file root:root 644" ] \
            || echo "$CONF is $(stat -c "%F %U:%G %a" "$CONF"), not a regular file root:root 644"
    fi
    sudo -u "$SERVICE_USER" test -w /usr/local/sbin \
        && echo "/usr/local/sbin ($(stat -c "%U:%G %a" /usr/local/sbin)) is writable by $SERVICE_USER"
    true
}
# Each path among the arguments the service user can write; nothing when it can write none.
writable_by_service_user() {
    local p
    for p in "$@"; do
        sudo -u "$SERVICE_USER" test -w "$p" && echo "$p"
    done
    true
}
# dry_run <id> <peer> <port>: one dry-run request written as the service user, then the helper
# run as Mercury runs it (sudo's one line, no argument); the helper's outcome is its one
# printed line. A dry run closes nothing.
dry_run() {
    sudo -u "$SERVICE_USER" sh -c 'umask 077 && printf "%s\n" "$1" > "$2.new" && mv "$2.new" "$2"' \
        sh "{\"id\": \"$1\", \"peer\": \"$2\", \"port\": \"$3\", \"dry_run\": true}" "$REQUEST" \
        || { echo "the request could not be written as $SERVICE_USER"; return 1; }
    sudo -u "$SERVICE_USER" sudo -n "$INSTALLED"
    true
}
export -f render_conf state_problems writable_by_service_user dry_run

plan "run as the operator's own user, not root" \
     "the release holds the helper, and it parses under $PYTHON (3.8 or later)" \
     "ss is a program of root's that no one else can write, and names -K" \
     "the kernel can destroy a socket (CONFIG_INET_DIAG_DESTROY=y)" \
     "the service user exists" \
     "the collector listens on the listener, on an IPv4 socket" \
     "the configuration renders by the helper's own rules" \
     "what is already there is as this step leaves it" \
     "the sudoers file is absent or exactly the one line, and visudo -c parses every file" \
     "the installed helper is root:root 755 and is the release's" \
     "the installed configuration is root:root 644 and is the one rendered" \
     "the outcome's folder is root's and the request's is the service user's" \
     "the sudoers line is the one line, and visudo -c parses every file" \
     "the service user can write none of what was installed" \
     "a dry run for a peer of the list is answered no_match or would_close" \
     "a dry run for an address not in the list is refused (refused_peer)"
not_root

# --- Every check before the first change -----------------------------------------------------
check "the release holds the helper, and it parses under $PYTHON (3.8 or later)" rc0 "" \
    '[ -f "$HELPER_SRC" ] && "$PYTHON" -I -B -c "import sys; sys.version_info >= (3, 8) or sys.exit(\"Python \" + sys.version.split()[0] + \" is older than 3.8\"); compile(open(sys.argv[1]).read(), sys.argv[1], \"exec\")" "$HELPER_SRC"'
check "ss is a program of root's that no one else can write, and names -K" eq "ok" \
    'if [ -z "$SS" ]; then echo "no ss on this host (iproute2)"; elif [ "$(stat -c "%F %U" "$SS")" != "regular file root" ] || [ -n "$(find "$SS" -maxdepth 0 -perm /022)" ]; then echo "$SS is $(stat -c "%F %U:%G %a" "$SS"), not a regular file of root that no one else can write"; elif ! "$SS" -h 2>&1 | grep -q -- "-K, --kill"; then echo "$SS -h names no -K, --kill: this ss cannot close a socket"; else echo ok; fi'
if [ -r "$KCONF" ]; then
    check "the kernel can destroy a socket (CONFIG_INET_DIAG_DESTROY=y)" eq "CONFIG_INET_DIAG_DESTROY=y" \
        'grep -E "^(# )?CONFIG_INET_DIAG_DESTROY[= ]" "$KCONF" || echo "$KCONF does not name CONFIG_INET_DIAG_DESTROY"'
elif [ -r /proc/config.gz ]; then
    check "the kernel can destroy a socket (CONFIG_INET_DIAG_DESTROY=y)" eq "CONFIG_INET_DIAG_DESTROY=y" \
        'zcat /proc/config.gz | grep -E "^(# )?CONFIG_INET_DIAG_DESTROY[= ]" || echo "/proc/config.gz does not name CONFIG_INET_DIAG_DESTROY"'
else
    not_asked "the kernel can destroy a socket (CONFIG_INET_DIAG_DESTROY=y)" \
        "neither $KCONF nor /proc/config.gz can be read, so it could not be checked: a kernel without it answers the first real close with not_gone"
fi
check "the service user exists" eq "" \
    'id -u "$SERVICE_USER" >/dev/null 2>&1 || echo "no account $SERVICE_USER on this host"'
SERVICE_GROUP=$(id -gn "$SERVICE_USER")
export SERVICE_GROUP
check "the collector listens on the listener, on an IPv4 socket" eq "ok" \
    'n=$("$SS" -H -4 -l -t -n sport = ":$L_PORT" | awk -v a="$L_ADDR:$L_PORT" -v w="0.0.0.0:$L_PORT" "\$4 == a || \$4 == w { n++ } END { print n + 0 }"); if [ "$n" -ge 1 ]; then echo ok; else echo "ss lists no IPv4 socket listening at $LISTENER or at 0.0.0.0:$L_PORT: the helper closes sessions of an IPv4 listening socket in this host'"'"'s own network namespace; a collector listening on [::]:$L_PORT, or inside a container, is not served yet"; fi'
check "the configuration renders by the helper's own rules" rc0 "" \
    '[ -r "$PEERS_FILE" ] || { echo "the peers file $PEERS_FILE cannot be read"; exit 1; }; render_conf >/dev/null'
check "what is already there is as this step leaves it" eq "" \
    'state_problems'
check "the sudoers file is absent or exactly the one line, and visudo -c parses every file" eq "ok" \
    'sudo visudo -c >/dev/null 2>&1 || { echo "visudo -c refuses the sudoers files as they are"; exit 0; }; if sudo test -e "$SUDOERS_FILE"; then [ "$(sudo cat "$SUDOERS_FILE" | grep -v "^#" | grep -v "^$")" = "$SUDOERS_LINE" ] && echo ok || echo "$SUDOERS_FILE holds something other than the one line: $SUDOERS_LINE"; else echo ok; fi'

# --- The changes -----------------------------------------------------------------------------
# Rendered into a fresh folder, then installed by name (never a glob).
WORK=$(mktemp -d)
export WORK
step "render the configuration for this host into $WORK" \
    'render_conf > "$WORK/collector-close.conf"'
step "install the helper root-owned, 0755" \
    'sudo install -o root -g root -m 0755 "$HELPER_SRC" "$INSTALLED"'
check "the installed helper is root:root 755 and is the release's" rc0 "" \
    '[ "$(stat -c "%F %U:%G %a" "$INSTALLED")" = "regular file root:root 755" ] && sudo cmp -s "$HELPER_SRC" "$INSTALLED"'
step "install the configuration root-owned, 0644, in a folder of root's" \
    'sudo install -d -o root -g root -m 0755 "$CONF_DIR" && sudo install -o root -g root -m 0644 "$WORK/collector-close.conf" "$CONF"'
check "the installed configuration is root:root 644 and is the one rendered" rc0 "" \
    '[ "$(stat -c "%F %U:%G %a" "$CONF")" = "regular file root:root 644" ] && [ "$(stat -c "%F %U:%G %a" "$CONF_DIR")" = "directory root:root 755" ] && sudo cmp -s "$WORK/collector-close.conf" "$CONF"'
step "make the outcome's folder (root's) and the request's (the service user's, 0700)" \
    'sudo install -d -o root -g root -m 0755 "$STATE_DIR" && sudo install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0700 "$REQUEST_DIR"'
check "the outcome's folder is root's and the request's is the service user's" eq "directory root:root 755 directory $SERVICE_USER:$SERVICE_GROUP 700" \
    'echo $(stat -c "%F %U:%G %a" "$STATE_DIR" "$REQUEST_DIR")'
if sudo test -e "$SUDOERS_FILE"; then
    echo "== KEPT: $SUDOERS_FILE is there already and is the one line"
else
    step "render the sudoers line into $WORK and check it parses" \
        'printf "%s\n" "$SUDOERS_LINE" > "$WORK/mercury-collector-close.sudoers" && sudo visudo -cf "$WORK/mercury-collector-close.sudoers" >/dev/null'
    step "install the sudoers line root-owned, 0440" \
        'sudo install -o root -g root -m 0440 "$WORK/mercury-collector-close.sudoers" "$SUDOERS_FILE"'
fi
check "the sudoers line is the one line, and visudo -c parses every file" rc0 "" \
    'sudo visudo -c >/dev/null && [ "$(sudo cat "$SUDOERS_FILE" | grep -v "^#" | grep -v "^$")" = "$SUDOERS_LINE" ] && [ "$(sudo stat -c "%U:%G %a" "$SUDOERS_FILE")" = "root:root 440" ]'
check "the service user can write none of what was installed" eq "" \
    'writable_by_service_user "$INSTALLED" "$CONF" "$CONF_DIR" "$STATE_DIR" "$SUDOERS_FILE" /usr/local/sbin'

# --- The copy, proved where it landed: two dry runs, which close nothing ----------------------
IN_LIST=$(head -n 1 "$PEERS_FILE")
NOT_LISTED=""
for candidate in 192.0.2.1 198.51.100.1 203.0.113.1; do
    if ! grep -qxF "$candidate" "$PEERS_FILE"; then
        NOT_LISTED=$candidate
        break
    fi
done
export IN_LIST NOT_LISTED
FIRST=$(dry_run install-step-listed "$IN_LIST" 1)
echo "      a dry run for $IN_LIST port 1: $FIRST"
export FIRST
check "a dry run for a peer of the list is answered no_match or would_close" re '"code": "(no_match|would_close)"' \
    'printf "%s" "$FIRST"'
SECOND=$([ -z "$NOT_LISTED" ] || dry_run install-step-not-listed "$NOT_LISTED" 1)
echo "      a dry run for $NOT_LISTED port 1: $SECOND"
export SECOND
check "a dry run for an address not in the list is refused (refused_peer)" has '"code": "refused_peer"' \
    '[ -n "$NOT_LISTED" ] || { echo "192.0.2.1, 198.51.100.1 and 203.0.113.1 are all in the peers file, so no address outside it was tried"; exit 0; }; printf "%s" "$SECOND"'
rm -r "$WORK"
echo "== INSTALLED: $INSTALLED, $CONF ($(wc -l < "$PEERS_FILE") peers, listener $LISTENER) and $SUDOERS_FILE. Nothing was restarted and nothing was closed."
echo "== TRY IT (as $SERVICE_USER, closes nothing): scripts/nmas-collector-close-dry-run $IN_LIST 1"
echo "== UNDO: sudo rm $INSTALLED $CONF $SUDOERS_FILE"
summary
