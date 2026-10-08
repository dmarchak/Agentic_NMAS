#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# clab-startup-sync.sh (until 2026-10-08 oxidized-to-config.sh, which stays a
# link to this file for one release, so a host still calling the old name keeps
# working until it is repointed: Phase 3, docs/NSOT_PHASE3_RETIRE_OXIDIZED.md)
#
# Turns each device's newest EARNED baseline (credentials from its current
# golden), as committed in the network's repository, into replayable
# containerlab startup-configs. Oxidized is not read (Phase 3, the operator's
# decision, 2026-10-08): GitHub owns configurations.
#
#   RUN ON THE NMAS VM:
#     ./clab-startup-sync.sh
#
#   It converts, shows the full diff against what is currently on the clab
#   VM, and asks before copying anything. Nothing is written to the clab VM
#   without an explicit yes.
#
#   Options:
#     ./clab-startup-sync.sh --no-deploy    convert and diff only
#     ./clab-startup-sync.sh --yes          skip the prompt (for cron)
#     CLAB=user@host ./clab-startup-sync.sh
#     NMAS_URL=http://<nmas-host>:5000 ./clab-startup-sync.sh
#
# WHEN IT RUNS (C553): a baseline earned starts it at once. The app writes
#   data/events/baseline-earned/<network> on every commit that earns a baseline
#   (a generic event, naming no lab tool); the host's clab-sync.path unit
#   watches the lab's network's file and starts clab-sync.service. The 30-minute
#   timer stays as the fallback.
#
#   With neither set, both come from data/lab_hosts.json beside the NMAS
#   checkout, through nmas-host (the repository is public, so the hosts'
#   addresses are not in this file); a missing file REFUSES, exit 2.
#
# WHERE THE DEVICE LIST COMES FROM
#   The NMAS, once, via nmas-clab-targets. It used to be SIX places encoding
#   the same population: three loops over "r1 r2 r3 r4 r5 s1 s2 s3 s4", the
#   implicit cp glob, the ROUTERS string, and the NODE array. All were
#   current when they were written. r6 was in none of them.
#
#   If the NMAS cannot be asked, this STOPS. It does not fall back to a
#   default directory: a guess about where a config boots from writes one
#   device's credentials into another lab.
#
# EVERY ssh USES -n WHEN IT IS NOT FED BY A PIPE
#   ssh reads its stdin to EOF and forwards it to the remote command. Inside
#   a `while read` loop stdin IS the loop's input, so on 2026-09-24 the first
#   ssh in the copy body swallowed the rest of the destinations list: the
#   loop ran ONCE, nine of ten files were copied, and the script printed
#   "Startup-configs updated." and exited 0. In the full-diff loop the same
#   ssh ate the terminal that `less` needed, so a diff that was asked for
#   never appeared.
#
#   Every command return code was 0. There was nothing for error handling to
#   catch, which is why the verification below counts and re-reads rather
#   than trusting them.
#
# THE REVIEW IS NOT OPT-IN, AND HAS NO MOVING PARTS
#   The full diff used to be behind "Show the full diff? [y/N]" - one
#   keystroke from being skipped, before a script that overwrites boot
#   configuration. It is now shown first and the only question is whether to
#   proceed.
#
#   It is also written straight to stdout. This one section failed four
#   times for four different causes - the opt-in default, ssh consuming the
#   tty that less needed, and finally less itself swallowing the output on
#   this machine with PAGER and LESS both unset. None of the four was the
#   logic: the loop, the diff and the comparison were right every time, and
#   only the display was lost. A review step with dependencies is a review
#   step that will eventually not happen.
#
# WHY A SANITISER IS STILL NEEDED
#   A golden is a captured running config, so it carries what a running
#   config carries: the device's certificate chains, vrnetlab's management
#   VRF and interface, licensing state. Replay that as a startup-config and
#   vrnetlab will fight its own bootstrap.
#
#   It also has a blind spot that is easy to miss: a running-config records
#   "shutdown" on a down interface but records NOTHING on an up one. Harvest
#   a working device and every interface comes back administratively down on
#   the next deploy. This cost a full rebuild on 2026-08-30 - all SVIs and
#   every routed port on r1-r4 came up shut, so only s3 was reachable.
#   The sanitiser therefore re-injects "no shutdown" into any interface block
#   that carries an address and does not explicitly say shutdown.
#
# WHAT THE SANITISER REMOVES, AND WHY (the rules in sanitise() below)
#   "! comment" lines      provenance (a store's header), never configuration
#   banner blocks          vrnetlab types the file into the console and waits
#                          for a prompt; the ^C delimiter breaks that match
#                          and HANGS the boot
#   crypto pki trustpoint, the device's own self-signed certificate: the
#   certificate chain      device makes a new one at boot (C302), and a
#                          certificate body cannot be typed back in
#   crypto key lines       keys are not configuration
#   vrf definition         vrnetlab's management plumbing, which its own
#     clab-mgmt, Gi1       bootstrap sets; two copies fight
#     (routers), ip/ipv6
#     route vrf clab-mgmt
#   call-home,             Cisco's call-home, which reaches out to Cisco (D4)
#     service call-home
#   version, boot markers, image and hardware state the device reports, not
#   license, platform,     configuration it takes from a file
#     diagnostic bootup,
#     memory free low-watermark, Building/Current configuration
#   ip ssh maxstartups,    no reason was recorded when these rules were
#     ip tftp source-interface,  written (ip domain name example.com is
#     ip domain name example.com  vrnetlab's default); kept as found
#   end, blank lines       structure; one `end` is appended
#   And it ADDS: `no shutdown` (above); on switches `no logging console`
#   (where the config lacks it; no reason was recorded) and the SSH host
#   key's generation, which no config holds.
#
# WHAT NO CONFIG SOURCE RESTORES (a redeploy makes these anew, whatever the
# file holds)
#   RSA host keys          SSH's key is generated at boot, so its fingerprint
#                          changes: a client that pinned it refuses
#   certificate keys       the self-signed certificate and its key (RESTCONF's)
#                          are new, by design (C302)
#   SNMPv3 users           their localized keys never appear in a running
#                          config (this fleet uses v2c; a v3 user is lost)
#
# THE SOURCE IS THE NEWEST EARNED BASELINE (plan item 4, the operator's
# decision, 2026-10-01)
#   Oxidized polled, so building from its copy made a change somebody made on
#   a device at 2am and never approved what that device booted, and one such
#   change held every device's file back (C306, C309). Each file is built by
#   scripts/nmas-startup-source from the list's newest baseline that EARNED
#   its tag (every device at its committed intent, not withdrawn), with every
#   credential family (accounts, enable, SNMP communities) taken from the
#   device's CURRENT golden, so a rotation since the baseline is never undone
#   by a redeploy. A device the baseline does not hold is NOT BUILT, named,
#   and every other device is still written; the run then exits 3 so job
#   health sees it.
#
#   Whether a device still runs what its file boots is the app's to say, from
#   its own record (the drift check, and the lab startup row's
#   `since_baseline`): Oxidized's copy, the cross-check this job printed until
#   Phase 3, is not read.
#
#   The file is configuration only: the baseline is named in the lab
#   commit's message (C313), and a file whose configuration did not move is
#   neither copied nor committed.
#
# ALWAYS review 'git diff configs/' before redeploying.
# ---------------------------------------------------------------------------
set -uo pipefail

OUT="${OUT:-configs}"
# Whether CLAB was set in the environment, checked BEFORE the default is
# applied: the map carries a host too, and an explicit CLAB= must still win.
CLAB_FROM_ENV="${CLAB+yes}"
CLAB="${CLAB:-}"
STAGE="${STAGE:-/tmp/clab-startup-staged}"
NMAS_URL="${NMAS_URL:-}"
# THE NETWORK THIS LAB BOOTS, NAMED, NEVER THE INSTALLATION'S ACTIVE LIST (C482).
#
# Measured 2026-10-05: with a second network made active on today's page, both helpers
# below asked for the ACTIVE list (`throwaway`), so the map held its one device and the
# source refused ("throwaway has no earned baseline"), and every run failed from 18:24
# UTC for every network: Default's lab files were not synced for 2.5 hours. The sync
# serves the network whose devices this lab's topology boots; a network with its own
# topology is outside it, and another lab's network runs its own sync with its own
# CLAB_LIST.
CLAB_LIST="${CLAB_LIST:-Default}"
# HELPERS ARE RESOLVED BESIDE THIS SCRIPT, NEVER THROUGH PATH.
#
# Measured 2026-09-25: `~/bin/nmas-clab-targets` was on the operator's
# interactive PATH and not on systemd's, so clab-sync.service failed every
# 30 minutes for ~36 hours (72 runs, 2026-09-24 08:40 onwards) with
# "command not found" -> "REFUSED - the NMAS could not be asked". The
# refusal was correct and went into a journal nobody read, and r6's startup
# config fell a day behind its branch-site config.
#
# This script lives in the NMAS repository (scripts/) and is deployed as a
# SYMLINK, so its real path is the checkout and the helpers are its
# siblings. One copy: the deployed file had also diverged from the repo's.
SELF="$(readlink -f "${BASH_SOURCE[0]}")"
HERE="$(dirname "$SELF")"
TARGETS="${TARGETS:-$HERE/nmas-clab-targets}"
SOURCE="${SOURCE:-$HERE/nmas-startup-source}"
# The committer's identity, on EVERY commit this job makes (see the commit
# step): used by the reconcile below as well as the per-lab commit.
GIT_ID=(-c user.name=clab-sync -c user.email=clab-sync@nmas.invalid)
# ONE sync at a time (CONCURRENCY_AUDIT R40): two persists, or a persist and this script's
# timer, ran two fleet-wide syncs into the same staging folder and committed to the lab
# repositories at once. Beside the staging folder; opened read-only, so whichever user made
# it, the other can still lock it. A second run waits up to ten minutes, then refuses.
# Descriptor 8: a wrapper that runs this script may hold its own lock on 9.
SYNC_LOCK="$STAGE.lock"
[ -e "$SYNC_LOCK" ] || : > "$SYNC_LOCK" 2>/dev/null
exec 8<"$SYNC_LOCK" || { echo "REFUSED - cannot open the sync lock $SYNC_LOCK"; exit 2; }
if ! flock -w 600 8; then
  echo "REFUSED - another clab startup sync held $SYNC_LOCK for ten minutes"
  exit 75
fi
for helper in "$TARGETS" "$SOURCE" "$HERE/nmas-host"; do
  if [ ! -x "$helper" ]; then
    echo "REFUSED - helper not found or not executable: $helper"
    echo "  (resolved beside this script, $SELF -- not through PATH, which"
    echo "  differs between a login shell and systemd)"
    exit 2
  fi
done
# THE HOSTS ARE NOT IN THIS FILE (the operator, 2026-09-29: the repository
# is public). An unset NMAS_URL or CLAB is read from data/lab_hosts.json
# through nmas-host, beside this script, and a file that is missing or
# unreadable REFUSES naming it: a guessed address is how a config lands on
# the wrong machine. Not in a command substitution, so `exit` leaves the job.
lab_value() {  # $1 host, $2 field, $3 the variable it stands in for -> LAB_VALUE
  local out
  if ! out="$("$HERE/nmas-host" "$1" --field "$2" 2>&1)"; then
    echo "REFUSED - $3 is not set, and the lab hosts file could not be read:"
    echo "  $out"
    echo "  The hosts' addresses are kept out of the public repository, in"
    echo "  data/lab_hosts.json beside the NMAS checkout. Create it, or set $3=."
    exit 2
  fi
  LAB_VALUE="$out"
}
if [ -z "$NMAS_URL" ]; then
  lab_value nmas lan NMAS_URL
  NMAS_URL="http://$LAB_VALUE:5000"
fi

# Each device's source, built from the newest earned baseline (plan item 4).
SRCDIR="$(mktemp -d)"
# What each lab holds NOW, read once per device, compared here (C313).
CUR="$(mktemp -d)"
# The app re-reads what this job writes as soon as it ends, success or not
# (the operator, 2026-10-01: the lab-startup reader read two minutes before a
# sync and its rows stood for ten). Its unit lives outside the repository, so
# the job tells the app itself; the timer's own result is unaffected.
finished() {
  rm -rf "$CUR" "$SRCDIR"
  NMAS_URL="$NMAS_URL" "$HERE/nmas-job-finished" clab-sync \
    || echo "(the app could not be told this sync finished; its readers catch up on their own schedule)"
}
trap finished EXIT

DEPLOY=ask
for a in "$@"; do
  case "$a" in
    --no-deploy) DEPLOY=no  ;;
    --yes|-y)    DEPLOY=yes ;;
    # COMPUTED FROM AN ANCHOR. It was `sed -n '2,73p'` and drifted three
    # times, each time silently truncating the only documentation this
    # script has. The anchor is the first line of code.
    --help|-h)   head -n "$(( $(grep -n '^set -uo pipefail' "$0" | head -1 | cut -d: -f1) - 1 ))" "$0" | tail -n +2; exit 0 ;;
    *) echo "unknown option: $a"; exit 1 ;;
  esac
done

# ---------------------------------------------------------------------------
# The map, fetched ONCE. Replaces NODE, ROUTERS and all four device loops.
# One ask is one consistent snapshot; a per-device ask is N chances to become
# unreachable mid-run, and a partial map is worse than none.
# ---------------------------------------------------------------------------
# Every associative array is ASSIGNED empty, never only declared: under
# `set -u` bash calls a declared-but-empty one unbound, so `${#X[@]}` on it
# aborts the command (2026-10-02: the nothing-to-copy exit crashed on
# NOT_BUILT, the run carried on past it and exited 1 on its best outcome).
declare -A CFGDIR=() PLATFORM=() LAB=()
DEVICES=()

map="$("$TARGETS" --url "$NMAS_URL" --list "$CLAB_LIST")" || {
  echo "REFUSED - the NMAS could not be asked where configs belong."
  echo "Not falling back to a default directory: a guess about where a"
  echo "config boots from writes one device's credentials into another lab."
  exit 2
}

# Columns are appended by the NMAS and never reordered: a sixth (Oxidized's
# node name, served by an NMAS before Phase 3) is read into `_rest` and not
# used.
while IFS=$'\t' read -r n cfgdir lab clabhost platform _rest; do
  [ -n "${n:-}" ] || continue
  case "$n" in '#'*) continue ;; esac
  # A row the NMAS could not complete is a device nobody should write.
  if [ -z "${cfgdir:-}" ] || [ -z "${platform:-}" ]; then
    echo "REFUSED $n: incomplete map row"
    echo "   configs_dir='${cfgdir:-}' platform='${platform:-}'"
    exit 2
  fi
  DEVICES+=("$n")
  CFGDIR[$n]="$cfgdir"
  PLATFORM[$n]="$platform"
  LAB[$n]="$lab"
  [ -z "$CLAB_FROM_ENV" ] && [ -n "${clabhost:-}" ] && CLAB="$clabhost"
done <<<"$map"
# Only when neither the environment nor the map named the lab host.
if [ -z "$CLAB" ]; then
  lab_value clab user CLAB; clab_user="$LAB_VALUE"
  lab_value clab lan CLAB; CLAB="$clab_user@$LAB_VALUE"
fi

[ ${#DEVICES[@]} -gt 0 ] || { echo "REFUSED - the map is empty. That is a fact about the answer, not about the fleet."; exit 2; }

echo "Map: ${#DEVICES[@]} device(s) of $CLAB_LIST from $NMAS_URL"

# The config DIALECT decides the sanitising rules, not the hostname. The
# default branch REFUSES: picking a kind for a platform nobody described is
# what ROUTERS did, and it picks wrong for exactly the devices nobody
# thought about.
kind_for() {
  case "$1" in
    cisco_iosxe) echo router ;;
    cisco_ios)   echo switch ;;
    *) return 1 ;;
  esac
}

mkdir -p "$OUT"

sanitise() {   # sanitise router|switch
awk -v kind="$1" '
  # ---- flush a pending "no shutdown" ---------------------------------------
  # Must be the FIRST rule. Any non-indented line ends the current interface
  # block, and several rules below use next, so the flush has to happen
  # before any of them can swallow the line. In particular a crypto pki
  # block immediately after an interface would otherwise lose the injection.
  # NOTE: no apostrophes anywhere in this awk program - it is inside a
  # single-quoted shell string and one quote truncates the whole thing.
  !/^[ \t]/ && inif { if (hadaddr && !hadshut) { print " no shutdown"; b=0 } inif=0 }

  # ---- a metadata header, and every "! comment" line ----------------------
  /^![ \t]/ { next }

  # ---- IOSv banner blocks: banner exec ^C ... ^C
  # Multi-line, and the ^C is a literal control character. vrnetlab pushes
  # config line by line and waits for a prompt, so a banner block breaks the
  # expect matching and HANGS THE BOOT. Drop them.
  /^banner [a-z-]+ / { ban=1; next }
  ban { if ($0 ~ /\003|\^C/) ban=0; next }

  # ---- multi-line blocks dropped whole ------------------------------------
  /^crypto pki (trustpoint|certificate chain)/ { blk=1 }
  /^vrf definition clab-mgmt$/                 { blk=1 }
  /^interface GigabitEthernet1$/ && kind=="router" { blk=1 }
  /^call-home$/ { ch=1; next }
  ch && /^!$/      { ch=0; next }
  ch && !/^[ \t]/ { ch=0 }
  ch               { next }
  blk && /^!$/ { blk=0; next }
  blk          { next }

  # ---- interface blocks ----------------------------------------------------
  # A running-config shows "shutdown" but never "no shutdown", so an
  # interface that was up loses that fact when harvested. Re-inject it for
  # any block that carries an address and was not explicitly shut.
  # Addressless blocks (switchports) are left alone - they default to up.
  /^interface / { inif=1; hadshut=0; hadaddr=0; b=0; print; next }
  inif && /^[ \t]/ {
      if ($0 ~ /^[ \t]+(ip|ipv6) address/) hadaddr=1
      if ($0 ~ /^[ \t]+shutdown[ \t]*$/)   hadshut=1
      b=0; print; next
  }

  # ---- single lines --------------------------------------------------------
  /^Building configuration/      { next }
  /^Current configuration/       { next }
  /^version /                    { next }
  /^boot-(start|end)-marker$/    { next }
  /^license /                    { next }
  /^diagnostic bootup/           { next }
  /^memory free low-watermark/   { next }
  /^platform /                   { next }
  /^service call-home/           { next }
  /^ip ssh maxstartups/          { next }
  /^ip tftp source-interface/    { next }
  /^ip route vrf clab-mgmt/      { next }
  /^ipv6 route vrf clab-mgmt/    { next }
  /^crypto key/                  { next }
  /^ip domain name example.com$/ { next }
  /^end$/                        { next }
  /^[ \t]*$/                     { next }

  # ---- collapse runs of bare bangs -----------------------------------------
  /^!$/ { if (b) next; b=1; print; next }
        { b=0; print }

  # ---- file ended mid-interface --------------------------------------------
  END { if (inif && hadaddr && !hadshut) print " no shutdown" }
'
}

# Every distinct destination in the map, once.
# >>> render_device
# One renderer, used for this run's output and by the app's lab startup row
# (lab_startup.py runs these functions through bash, the same rules).
#
# THE FILE IS CONFIGURATION ONLY (the operator, 2026-10-01, C313). It began
# with `! <h> - from Oxidized HEAD <sha>`, so every Oxidized commit (any
# device's poll) changed every file by that one line, the sync reported all
# of them CHANGED and committed all of them, and a real change was one line
# in nine identical diffs. The provenance is kept in the lab commit's message
# ("startup from <baseline> ...: r1 r3"), and a commit carries only the files
# whose configuration changed.
render_device() {   # render_device <name> <router|switch> <raw>
  local n="$1" kind="$2" raw="$3"
  # only add the header line if the harvested config does not already have it
  if [ "$kind" = switch ] && ! grep -q '^no logging console$' <<<"$raw"; then
    printf 'no logging console\n!\n'
  fi
  sanitise "$kind" <<<"$raw"
  # the RSA key is not in running-config; re-issue so SSH works on a fresh boot
  if [ "$kind" = switch ]; then
    printf '!\nip domain-name rcn.lab\ncrypto key generate rsa modulus 2048\nip ssh version 2\n'
  fi
  printf '!\nend\n'
}
# <<< render_device

# >>> config_body
# A file's CONFIGURATION: the text less the provenance header a file written
# before C313 still carries (its first three lines, `!`, the header, `!`).
# A file written since has none and passes through unchanged, so an old file
# whose configuration is current compares equal and is left alone; its old
# header goes when its configuration next changes.
config_body() {   # config_body <name>, the file on stdin
  awk -v h="! $1 - from Oxidized " '
    NR <= 3 { held[NR] = $0
              if (NR == 3 && index(held[2], h) != 1) { print held[1]; print held[2]; print held[3] }
              next }
    { print }
    END { if (NR < 3) for (i = 1; i <= NR; i++) print held[i] }'
}
# <<< config_body

destinations() {
  local n
  for n in "${DEVICES[@]}"; do echo "${CFGDIR[$n]}"; done | sort -u
}

# >>> build
# THE SOURCE IS THE NEWEST EARNED BASELINE (plan item 4, the operator's
# decision, 2026-10-01), every credential from the device's CURRENT golden
# (C309). A device the baseline does not hold is NOT BUILT, named with its
# reason, and every other device is still written (C309: one device used to
# hold every file back).
if ! "$SOURCE" --out "$SRCDIR" --list "$CLAB_LIST"; then
  echo "REFUSED - no startup source could be built (the reason is above): nothing"
  echo "is written. The files are built only from an earned baseline, so a"
  echo "redeploy cannot boot a change nobody approved."
  exit 2
fi
BASE_TAG=""; BASE_COMMIT=""
IFS=$'\t' read -r _ BASE_TAG BASE_COMMIT < <(grep '^# baseline' "$SRCDIR/sources.tsv")
if [ -z "$BASE_TAG" ]; then
  echo "REFUSED - the startup source named no baseline ($SRCDIR/sources.tsv has no"
  echo "'# baseline' line): nothing is written, since what the files would be built"
  echo "from is unknown."
  exit 2
fi
declare -A SOURCE_STATE=() SOURCE_WHY=() NOT_BUILT=()
while IFS=$'\t' read -r h st why; do
  case "$h" in ''|'#'*) continue ;; esac
  SOURCE_STATE[$h]="$st"; SOURCE_WHY[$h]="$why"
done < "$SRCDIR/sources.tsv"
echo "Building from $BASE_TAG (${BASE_COMMIT:0:10}); credentials from each device's current"
echo "golden"
echo
fail=0

for n in "${DEVICES[@]}"; do
  if ! kind="$(kind_for "${PLATFORM[$n]}")"; then
    printf '%-4s REFUSED - no sanitising rules for platform %s\n' "$n" "${PLATFORM[$n]}"
    fail=1; continue
  fi
  printf '%-4s ' "$n"

  if [ "${SOURCE_STATE[$n]:-}" != ok ]; then
    NOT_BUILT[$n]="${SOURCE_WHY[$n]:-the startup source names no such device}"
    echo "NOT BUILT - ${NOT_BUILT[$n]}"
    rm -f "$OUT/${n}.cfg"
    continue
  fi
  raw="$(cat "$SRCDIR/${n}.cfg")"
  if ! grep -q '^hostname' <<<"$raw"; then
    echo "SKIPPED - the baseline's golden for $n holds no hostname"
    fail=1; continue
  fi
  render_device "$n" "$kind" "$raw" > "$OUT/${n}.cfg"

  lines=$(wc -l < "$OUT/${n}.cfg")
  ends=$(grep -c '^end$'  "$OUT/${n}.cfg")
  mg=$(grep -c '^interface GigabitEthernet1$' "$OUT/${n}.cfg")
  cert=$(grep -cE '^ +[0-9A-F]{8} ' "$OUT/${n}.cfg")
  ban=$(grep -c '^banner ' "$OUT/${n}.cfg")

  # addressed interfaces that would come up administratively down
  ifdown=$(awk '
    !/^[ \t]/ && v { if (a && !s) c++; v=0 }
    /^interface / { v=1; a=0; s=0; next }
    v && /^[ \t]/ {
        if ($0 ~ /^[ \t]+(ip|ipv6) address/) a=1
        if ($0 ~ /^[ \t]+no shutdown[ \t]*$/) s=1
    }
    END { if (v && a && !s) c++; print c+0 }' "$OUT/${n}.cfg")

  # sanity: a real config has exactly one hostname. An empty file has none,
  # and the old validation could not tell the difference.
  hn=$(grep -c '^hostname ' "$OUT/${n}.cfg")

  # truncation guard: every interface/router block the baseline holds must survive
  # sanitising (routers legitimately lose GigabitEthernet1, the mgmt port).
  raw_if=$(grep -c '^interface ' <<<"$raw")
  [ "$kind" = router ] && grep -q '^interface GigabitEthernet1$' <<<"$raw" && raw_if=$((raw_if-1))
  out_if=$(grep -c '^interface ' "$OUT/${n}.cfg")
  raw_rt=$(grep -c '^router ' <<<"$raw")
  out_rt=$(grep -c '^router ' "$OUT/${n}.cfg")

  printf '%4s lines  end=%s  up-ifs-ok' "$lines" "$ends"
  [ "$ends" -ne 1 ]                        && { printf '  <-- BAD end count'; fail=1; }
  [ "$hn"   -ne 1 ]                        && { printf '  <-- hostname count %s' "$hn"; fail=1; }
  [ "$out_if" -ne "$raw_if" ] && { printf '  <-- interfaces %s of %s (TRUNCATED?)' "$out_if" "$raw_if"; fail=1; }
  [ "$out_rt" -ne "$raw_rt" ] && { printf '  <-- router blocks %s of %s (TRUNCATED?)' "$out_rt" "$raw_rt"; fail=1; }
  [ "$kind" = router ] && [ "$mg" -ne 0 ]  && { printf '  <-- mgmt leaked';   fail=1; }
  [ "$cert" -ne 0 ]                        && { printf '  <-- cert leaked';   fail=1; }
  [ "$ban"  -ne 0 ]                        && { printf '  <-- banner leaked (will hang boot)'; fail=1; }
  [ "$ifdown" -ne 0 ]                      && { printf '  <-- %s addressed interface(s) missing no shutdown' "$ifdown"; fail=1; }
  echo
done

echo
if [ $fail -ne 0 ]; then
  echo "PROBLEMS ABOVE - nothing will be copied. Fix these first."
  exit 1
fi
echo "All files converted and validated."
# The devices not built leave the run here, each already named.
built=()
for n in "${DEVICES[@]}"; do [ -n "${NOT_BUILT[$n]:-}" ] || built+=("$n"); done
NOT_BUILT_LIST="$(IFS=,; echo "${!NOT_BUILT[*]}")"
DEVICES=("${built[@]}")
# <<< build

# ---------------------------------------------------------------------------
# Account for every mapped device BEFORE anything is copied. A device the
# sanitiser produced nothing for is NAMED rather than silently skipped - that
# was r6's state for two days and nothing reported it.
#
# A mapped device with no file blocks. A file nobody mapped does not: that is
# worth knowing and is not a reason to stop a sync.
# ---------------------------------------------------------------------------
echo
if ! "$TARGETS" --url "$NMAS_URL" --list "$CLAB_LIST" --reconcile "$OUT" --not-built "$NOT_BUILT_LIST"; then
  echo
  echo "PROBLEMS ABOVE - nothing will be copied."
  exit 1
fi

# What each device runs NOW against what its file boots is the app's to say,
# from its own record (the drift check; the lab startup row's since_baseline).
# This job printed Oxidized's copy against the file until Phase 3 (2026-10-08).

[ "$DEPLOY" = no ] && { echo "--no-deploy set, stopping here."; exit 0; }

# ---------------------------------------------------------------------------
# Diff against what is currently on the clab VM
# ---------------------------------------------------------------------------
echo
echo "=========================================================="
echo " Comparing against ${CLAB}, per lab"
destinations | sed 's/^/   /'
echo "=========================================================="

if ! ssh -n -o ConnectTimeout=10 -o BatchMode=yes "$CLAB" true 2>/dev/null; then
  echo
  echo "Cannot reach $CLAB without a password."
  echo "Set up a key so this can run unattended:"
  echo "    ssh-keygen -t ed25519 -N ''"
  echo "    ssh-copy-id $CLAB"
  echo
  echo "Converted files are in ./$OUT - copy them by hand if you prefer."
  exit 1
fi

ssh -n "$CLAB" "rm -rf $STAGE && mkdir -p $STAGE" || exit 1
rsync -a "$OUT"/ "${CLAB}:${STAGE}/" || exit 1

# >>> reconcile
# EVERY MANAGED FILE, EVERY RUN -- before the early exit and before any copy.
#
# C15, measured 2026-09-25: the 20:17 run wrote labs/r6/configs/r6.cfg and
# its commit failed; the 20:30 run found nothing to copy and exited 0 at
# "Nothing to do" BEFORE the commit step. The write was stranded: staged,
# unversioned, invisible to every later run -- and the run reported success.
#
# A dirty tracked (or untracked) file is committed only when it is PROVABLY
# this job's own output: its configuration identical to what this run built
# from the newest earned baseline. The sanitiser is deterministic, so a match
# is reproducible, not a judgement. Anything else is REFUSED for that device:
# neither committed (which would record a hand edit as a harvest) nor
# overwritten (which would destroy it), named, and the run exits 3 -- a
# refusal that exited 0 would reproduce the defect.
#
# Until Phase 3 (2026-10-08) a file that was not this run's output was also
# tried against the device's last 20 versions in Oxidized. Oxidized is not
# read now, so a write stranded by an EARLIER baseline's run, found only after
# a newer baseline was earned, is refused and named rather than guessed at:
# commit or discard it by hand. A stranded write is found by the next run,
# which a baseline now starts at once (C553), so a newer baseline in between
# is rare.
declare -A REFUSED_DIRTY=()
reconcile() {
  local n dest rel st out body
  for n in "${DEVICES[@]}"; do
    dest="${CFGDIR[$n]}/${n}.cfg"
    rel="$(basename "${CFGDIR[$n]}")/${n}.cfg"
    st="$(ssh -n "$CLAB" "cd \$(dirname '${CFGDIR[$n]}') 2>/dev/null && git rev-parse --git-dir >/dev/null 2>&1 && git status --porcelain -- '$rel'" 2>/dev/null)"
    [ -n "$st" ] || continue
    body="$(ssh -n "$CLAB" "cat '$dest'" 2>/dev/null | config_body "$n")"
    if [ -n "${BASE_TAG:-}" ] && [ -s "$OUT/${n}.cfg" ] \
         && [ "$body" = "$(cat "$OUT/${n}.cfg")" ]; then
      if out="$(ssh -n "$CLAB" "cd \$(dirname '${CFGDIR[$n]}') && git add -- '$rel' && git ${GIT_ID[*]} commit -q -m 'startup from $BASE_TAG (recorded late: an earlier run wrote it and its commit failed): $n' -- '$rel'" 2>&1)"; then
        printf '  %-4s RECORDED LATE - its uncommitted file was this job'"'"'s own output for %s\n' "$n" "$BASE_TAG"
      else
        REFUSED_DIRTY[$n]="its own uncommitted output could not be committed - git said: ${out%%$'\n'*}"
      fi
    else
      REFUSED_DIRTY[$n]="uncommitted changes this run did not produce (they differ from what $BASE_TAG builds for $n)"
    fi
  done
}
# <<< reconcile

reconcile
if [ ${#REFUSED_DIRTY[@]} -gt 0 ]; then
  echo
  echo "REFUSED - left exactly as found, neither committed nor overwritten:"
  for n in "${!REFUSED_DIRTY[@]}"; do
    printf '  %-4s %s\n       %s\n' "$n" "${CFGDIR[$n]}/${n}.cfg" "${REFUSED_DIRTY[$n]}"
  done
  echo "  Commit or discard each by hand. This job will not guess which you meant."
  keep=()
  for n in "${DEVICES[@]}"; do [ -n "${REFUSED_DIRTY[$n]:-}" ] || keep+=("$n"); done
  DEVICES=("${keep[@]}")
fi

# >>> compare
# CONFIGURATION AGAINST CONFIGURATION (C313). Each lab's current file is read
# once and its configuration (config_body) compared with this run's: a file
# whose configuration did not move is unchanged, whatever run or baseline it
# was written from, and is neither copied nor committed. Only COPY is.
changed=0
newfiles=0
COPY=()
echo
for n in "${DEVICES[@]}"; do
  ssh -n "$CLAB" "if [ -e '${CFGDIR[$n]}/${n}.cfg' ]; then cat '${CFGDIR[$n]}/${n}.cfg'; else exit 4; fi" \
    > "$CUR/${n}.file" 2>/dev/null
  rc=$?
  if [ "$rc" -eq 4 ]; then
    printf '  %-4s %-16s NEW - no current file on the clab VM\n' "$n" "${LAB[$n]}"
    newfiles=$((newfiles+1)); COPY+=("$n")
    continue
  elif [ "$rc" -ne 0 ]; then
    echo
    echo "REFUSED - ${CFGDIR[$n]}/${n}.cfg could not be read on $CLAB (exit $rc): what it"
    echo "holds is unknown, so nothing is compared or copied. Staged files left at ${CLAB}:${STAGE}."
    exit 1
  fi
  config_body "$n" < "$CUR/${n}.file" > "$CUR/${n}.cfg"
  d="$(diff -u "$CUR/${n}.cfg" "$OUT/${n}.cfg")"
  if [ -z "$d" ]; then
    printf '  %-4s %-16s unchanged\n' "$n" "${LAB[$n]}"
  else
    add=$(grep -c '^+[^+]' <<<"$d")
    del=$(grep -c '^-[^-]' <<<"$d")
    printf '  %-4s %-16s CHANGED  +%s / -%s lines\n' "$n" "${LAB[$n]}" "$add" "$del"
    changed=$((changed+1)); COPY+=("$n")
  fi
done
# <<< compare

if [ $((changed + newfiles)) -eq 0 ]; then
  echo
  # Says what was checked, never "updated for 0 of 0" (the operator).
  labs_here=$(destinations | wc -l)
  case "$labs_here" in
    1) echo "The lab already holds $BASE_TAG; nothing to update." ;;
    2) echo "Both labs already hold $BASE_TAG; nothing to update." ;;
    *) echo "All $labs_here labs already hold $BASE_TAG; nothing to update." ;;
  esac
  [ ${#NOT_BUILT[@]} -eq 0 ] || echo "(${#NOT_BUILT[@]} device(s) NOT BUILT, named above.)"
  ssh -n "$CLAB" "rm -rf $STAGE"
  # The exit that stranded r6 (C15) said "Nothing to do" and returned 0. A
  # refusal above is something to do, and job health must see it.
  [ ${#REFUSED_DIRTY[@]} -eq 0 ] || exit 3
  [ ${#NOT_BUILT[@]} -eq 0 ] || exit 3
  exit 0
fi

# From here on the run works on the files that MOVE (C313): an unchanged file
# is not backed up, copied, read back or committed, and a lab with none of
# them is not touched at all.
DEVICES=("${COPY[@]}")

# ---------------------------------------------------------------------------
# The full diff, SHOWN rather than offered, then one question
#
# It used to be "Show the full diff? [y/N]" - opt-in, defaulting to No, one
# keystroke from being skipped before a script that overwrites boot
# configuration. A diff that must be asked for is a diff nobody reads at 2am.
# The only decision left is whether to proceed.
# ---------------------------------------------------------------------------
if [ "$DEPLOY" = ask ]; then
  # STDOUT, NO PAGER. Measured 2026-09-24: with PAGER and LESS both unset
  # and /usr/bin/less present, `less -R` swallowed this output on the NMAS
  # while `PAGER=cat` showed it correctly. The same block, the same data,
  # the same comparison - only the display was lost.
  #
  # Not chased further, because the finding is not which less flag did it:
  # the only review step before an irreversible write depended on an
  # external program behaving, and on this machine it did not. The
  # terminal's scrollback is already a pager and it cannot be misconfigured
  # into showing nothing.
  for n in "${DEVICES[@]}"; do
    cur="$CUR/${n}.cfg"; [ -e "$cur" ] || cur=/dev/null
    out="$(diff -u "$cur" "$OUT/${n}.cfg" || true)"
    [ -n "$out" ] && { echo; echo "########## $n  (${LAB[$n]}) ##########"; echo "$out"; }
  done

  echo
  echo "This will overwrite these files on $CLAB:"
  for n in "${DEVICES[@]}"; do echo "    ${CFGDIR[$n]}/${n}.cfg"; done
  echo "A timestamped backup is taken first, and these are startup-configs -"
  echo "they only take effect on the next 'containerlab deploy --cleanup'."
  echo
  read -r -p "Copy the new configs over? [y/N] " ans
  if [[ ! "$ans" =~ ^[Yy] ]]; then
    echo "Left alone. Staged copy is at ${CLAB}:${STAGE}"
    exit 0
  fi
fi

# ---------------------------------------------------------------------------
# Back up, copy, verify, commit - PER LAB
#
# One transfer per DESTINATION, not per device: the unit of work is a lab,
# which is the unit --stray and the lab map already use.
#
# --files-from rather than a staging directory per lab: ./configs holds
# exactly one <hostname>.cfg per device and nothing else, so selecting a
# subset needs no second copy of it.
#
# EVERY ssh HERE USES -n. Without it the first one consumes the destinations
# list this loop is reading from, and the loop runs once.
# ---------------------------------------------------------------------------
ts=$(date +%Y%m%d-%H%M%S)
tried_dests=0
total_dests=$(destinations | wc -l)
# Each lab ends in exactly one of these. A lab is copied only after its own
# backup SUCCEEDED (C106 (2)): the backup was `cp -r ... 2>/dev/null; rsync`,
# and the `;` let a failed backup go on to overwrite the configs it existed
# to protect. And a failed step is named for the step: a skipped lab used to
# reach the count check as "the loop ran fewer times", and the read-back as
# "the copy reported success", both false.
COPIED_DIRS=()
FAILED_DIRS=()

# WHETHER EACH LAB CAN COMMIT, asked BEFORE anything is copied (C106 (2), the
# operator: "ask whether it will work before doing the irreversible part").
# The commit's preconditions were found after the overwrite: a lab whose
# repository could not take a commit had its startup configs replaced and
# then reported "COMMIT FAILED", configs changed and history not. A lab with
# no repository is copied as before and reported NOT VERSIONED below: that
# state is declared and named every run.
declare -A CANNOT_COMMIT=()
while read -r dir; do
  [ -n "$dir" ] || continue
  pre="$(ssh -n "$CLAB" "cd \$(dirname '$dir') 2>/dev/null || { echo ok; exit 0; }; \
    git rev-parse --git-dir >/dev/null 2>&1 || { echo ok; exit 0; }; \
    gd=\$(git rev-parse --absolute-git-dir); \
    [ -w \"\$gd\" ] || { echo \"its git directory \$gd is not writable\"; exit 0; }; \
    [ -e \"\$gd/index.lock\" ] && { echo \"\$gd/index.lock exists (another git process, or one that died)\"; exit 0; }; \
    echo ok" 2>&1)"
  [ "$pre" = "ok" ] || CANNOT_COMMIT["$dir"]="${pre:-the check could not run}"
done < <(destinations)

while read -r dir; do
  [ -n "$dir" ] || continue
  tried_dests=$((tried_dests+1))
  if [ -n "${CANNOT_COMMIT[$dir]:-}" ]; then
    FAILED_DIRS+=("$dir: CANNOT COMMIT (${CANNOT_COMMIT[$dir]}); NOTHING was copied, its configs are untouched")
    continue
  fi
  list=""
  for n in "${DEVICES[@]}"; do
    [ "${CFGDIR[$n]}" = "$dir" ] && list="${list}${n}.cfg"$'\n'
  done
  count=$(printf '%s' "$list" | grep -c . || true)

  # FED BY A PIPE, so this one must NOT take -n: its stdin is the file list,
  # not the loop's input, and -n would send the remote `cat` nothing.
  if ! printf '%s' "$list" | ssh "$CLAB" "cat > '$STAGE/.files'"; then
    FAILED_DIRS+=("$dir: the file list could not be staged; NOTHING was copied, its configs are untouched")
    continue
  fi
  if ! err="$(ssh -n "$CLAB" "cp -r '$dir' '${dir}.bak-${ts}'" 2>&1)"; then
    FAILED_DIRS+=("$dir: BACKUP FAILED (${err%%$'\n'*}); NOTHING was copied, its configs are untouched")
    continue
  fi
  if ssh -n "$CLAB" "rsync -a --files-from='$STAGE/.files' '$STAGE/' '$dir/'"; then
    echo "Copied $count file(s) to $dir   (backup ${dir}.bak-${ts})"
    COPIED_DIRS+=("$dir")
  else
    FAILED_DIRS+=("$dir: COPY FAILED after its backup ${dir}.bak-${ts} was taken; its configs may be PARTLY overwritten (restore from that backup)")
  fi
done < <(destinations)

# ---------------------------------------------------------------------------
# COUNT, then READ BACK. Both before STAGE is removed.
#
# The count catches a loop that ran fewer times than there are destinations -
# the 2026-09-24 failure, where every command returned 0 and there was
# nothing for error handling to catch. It counts ATTEMPTS: a lab that was
# tried and failed is named below, not blamed on the loop.
#
# The read-back is the one that matters: it asks the clab VM what is actually
# in each destination rather than trusting what the transport reported. Same
# rule as "a failed push reports what LANDED, not what was pushed", and as
# verify_startup_carries_current() reading the file rather than the report.
# It reads the labs that were COPIED; a lab that failed was never written.
# ---------------------------------------------------------------------------
if [ "$tried_dests" -ne "$total_dests" ]; then
  echo
  echo "REFUSED - tried $tried_dests of $total_dests destination(s)."
  echo "The loop ran fewer times than there are destinations. Staged files"
  echo "left at ${CLAB}:${STAGE} - do not re-run until this is understood."
  exit 1
fi

verify=""
verified=0
for n in "${DEVICES[@]}"; do
  for d in "${COPIED_DIRS[@]}"; do
    if [ "${CFGDIR[$n]}" = "$d" ]; then
      verify="${verify}cmp -s '$STAGE/${n}.cfg' '${CFGDIR[$n]}/${n}.cfg' || echo '${n} ${CFGDIR[$n]}'"$'\n'
      verified=$((verified+1))
    fi
  done
done
mismatched=""
[ -n "$verify" ] && mismatched="$(ssh -n "$CLAB" "$verify")"

if [ -n "$mismatched" ]; then
  echo
  echo "REFUSED - these devices are NOT what was staged:"
  printf '%s\n' "$mismatched" | sed 's/^/    /'
  echo
  echo "The copy reported success for their lab and the files do not match."
  echo "Staged files left at ${CLAB}:${STAGE}."
  exit 1
fi

[ "$verified" -gt 0 ] && echo "Verified: all $verified file(s) in the ${#COPIED_DIRS[@]} copied lab(s) match the staged copy."

# The staged files are kept while any lab failed: they are what a re-run or a
# hand copy of the failed lab would use.
[ ${#FAILED_DIRS[@]} -eq 0 ] && ssh -n "$CLAB" "rm -rf $STAGE"

# THREE OUTCOMES, NOT ONE SENTENCE.
#
# `|| echo "Not a git repo, or nothing to commit"` named two causes and
# distinguished neither, so it printed the same line since August while
# meaning only one of them. Measured 2026-09-24: labs/lab IS a repo with
# configs/ tracked and byte-identical to HEAD - a correct no-op - while
# labs/r6 is not a repo at all. Two genuinely different states, one
# sentence. Same shape as the census exiting 1 for both "the teardown left
# objects behind" and "there was no baseline".
#
#   committed    - history gained something
#   unchanged    - the system working; the content really did not move
#   NOT VERSIONED - a gap in coverage, and the only one that needs action
# THE `git add` BELOW IS SCOPED TO THE CONFIGS DIRECTORY ON PURPOSE.
# `git add -A "$(basename "$dir")"` stages only that path. A bare
# `git add -A` here would sweep containerlab's runtime state from the lab
# directory -- `clab-<lab>/.state.clab.yaml` and `clab-<lab>/.tls/ca/ca.key`,
# a PRIVATE KEY.
#
# Measured 2026-09-24: this script's own add was already scoped and was
# fine. The bare `git add -A` was in the setup recipe the script PRINTED for
# an unversioned destination, and it put that key in a commit. The defect
# was in the advice, not in the action -- which is why the recipe below now
# writes a .gitignore and names the paths it stages.
# IDENTITY RIDES ON EVERY COMMIT (-c), and is never assumed from the repo.
#
# Measured 2026-09-25: labs/r6 IS a repo (d3f8486 "initial: configs only")
# with configs/r6.cfg staged, and the commit failed because the repo has no
# user.email -- its first commit passed -c inline and never persisted it. That
# failure was reported as "NOT VERSIONED" with the `git init` recipe: a
# commit that wanted an identity, announced as an absent repository, with a
# remedy that would be wrong to follow.
#
# The committer is this job, so the identity is a property of the job and
# travels with it: setting it at init covers only repos this script created,
# and relying on the repo's config fails on exactly the repos somebody set
# up by hand. `.invalid` (RFC 2606) because it names a service, not a mailbox.
unversioned=()
failed=()
while read -r dir; do
  [ -n "$dir" ] || continue
  # ONLY THIS JOB'S FILES, by path. `git add -A configs` would sweep a
  # refused hand edit sitting in the same directory into a harvest commit,
  # and `git commit` with no pathspec would commit anything else staged.
  files=""; names=""
  for n in "${DEVICES[@]}"; do
    [ "${CFGDIR[$n]}" = "$dir" ] && { files="$files '$(basename "$dir")/${n}.cfg'"; names="$names $n"; }
  done
  [ -n "$files" ] || continue
  outcome="$(ssh -n "$CLAB" "cd \$(dirname '$dir') 2>/dev/null || { echo nodir; exit 0; }; \
    git rev-parse --git-dir >/dev/null 2>&1 || { echo norepo; exit 0; }; \
    err=\$(git add --$files 2>&1) || { printf 'addfailed %s\n' \"\$(printf '%s' \"\$err\" | head -1)\"; exit 0; }; \
    git diff --cached --quiet --$files && { echo unchanged; exit 0; }; \
    err=\$(git ${GIT_ID[*]} commit -q -m 'startup from $BASE_TAG ($ts):$names' --$files 2>&1) \
      && echo committed \
      || printf 'commitfailed %s\n' \"\$(printf '%s' \"\$err\" | head -1)\"")"
  kind="${outcome%% *}"
  reason="${outcome#"$kind"}"; reason="${reason# }"
  case "$kind" in
    committed)    echo "  $dir: committed" ;;
    unchanged)    echo "  $dir: unchanged - nothing to commit (the content did not move)" ;;
    norepo)       echo "  $dir: NOT VERSIONED - the parent directory is not a git repo"
                  unversioned+=("$dir") ;;
    nodir)        echo "  $dir: NOT VERSIONED - parent directory does not exist"
                  unversioned+=("$dir") ;;
    addfailed)    echo "  $dir: ADD FAILED in an existing repository - git said: ${reason:-no reason given}"
                  failed+=("$dir") ;;
    commitfailed) echo "  $dir: COMMIT FAILED in an existing repository - git said: ${reason:-no reason given}"
                  failed+=("$dir") ;;
    *)            echo "  $dir: UNKNOWN OUTCOME ($outcome) - treat as not committed"
                  failed+=("$dir") ;;
  esac
# Only the labs COPIED: a lab whose backup or copy failed was never written
# by this run, so there is nothing of it to commit (C106 (2)).
done < <(printf '%s\n' "${COPIED_DIRS[@]}")

# A failure in an EXISTING repository is not "not versioned": the repository
# is there and the fix is git's own message, not `git init`. Reported apart,
# and it makes the run exit non-zero so the job's failure is visible.
if [ ${#failed[@]} -gt 0 ]; then
  echo
  echo "${#failed[@]} destination(s) did NOT COMMIT, in repositories that exist:"
  printf '    %s\n' "${failed[@]}"
  echo "  The startup configs were written; their history did not move. Fix"
  echo "  the cause git named above -- do NOT run the git init recipe."
fi

if [ ${#unversioned[@]} -gt 0 ]; then
  echo
  echo "${#unversioned[@]} destination(s) are NOT VERSIONED:"
  printf '    %s\n' "${unversioned[@]}"
  echo "  Their startup configs are the only copy of what those devices boot"
  echo "  with. The backup directories beside them are what accumulates when"
  echo "  a versioned store is not receiving anything -- labs/lab has 29"
  echo "  going back to August."
  echo
  echo "  The recipe below adds ONLY the configs directory and writes a"
  echo "  .gitignore first. Do not use a bare 'git add -A' here: a lab"
  echo "  directory also holds containerlab's runtime state, including"
  echo "  clab-<lab>/.tls/ca/ca.key -- a PRIVATE KEY. An unscoped add on"
  echo "  2026-09-24 committed exactly that."
  for d in "${unversioned[@]}"; do
    parent="$(dirname "$d")"
    leaf="$(basename "$d")"
    echo
    echo "    ssh $CLAB \"cd '$parent' && git init -q && \\"
    echo "      printf '%s\\n' 'clab-*/' '*.bak-*/' > .gitignore && \\"
    echo "      git add .gitignore '$leaf' && \\"
    echo "      git commit -q -m 'initial: $leaf only'\""
  done
fi

echo
# THE STATE FIRST (C106): a run that updated some labs and not others says
# so before anything that reads as success.
if [ ${#FAILED_DIRS[@]} -gt 0 ]; then
  echo "NOT ALL LABS UPDATED: ${#COPIED_DIRS[@]} of $total_dests updated. Staged files left at ${CLAB}:${STAGE}."
  printf '    %s\n' "${FAILED_DIRS[@]}"
fi
echo "Startup-configs updated for ${#COPIED_DIRS[@]} of $total_dests lab(s). They take effect on the next destroy/deploy of"
echo "each affected lab."
# Exit 3 when a destination did not commit, so a timer running this reports
# the failure rather than succeeding around it.
[ ${#FAILED_DIRS[@]} -eq 0 ] || exit 3
[ ${#failed[@]} -eq 0 ] || exit 3
[ ${#REFUSED_DIRTY[@]} -eq 0 ] || exit 3
[ ${#NOT_BUILT[@]} -eq 0 ] || exit 3
