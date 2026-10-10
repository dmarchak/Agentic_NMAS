#!/usr/bin/env bash
# Phase 7 operating mode, ON (the operator's decision, 2026-10-09). The operator runs it on the
# LAPTOP, in the checkout the agent works in (its hooks are there), never on a host:
#
#   scripts/host-steps/phase7-mode-on.sh
#
# It prints the change and asks before making it:
#   - CLAUDE.md gains the marked section "Phase 7 operating mode (in force)" before "## Project";
#   - the mode's flag, .claude/phase7-mode (gitignored, owner-only), is written. While it
#     exists, scripts/hooks/claude-no-host-writes lets nmas-deploy on a host through (a git write
#     in a host's checkout stays refused); claude-no-claude-md-edits refuses the agent's tools
#     on the flag and on running this script.
# The flag records CLAUDE.md's hash from before, so phase7-mode-off.sh can say whether CLAUDE.md
# returns to exactly that. A failure after the answer puts CLAUDE.md back and removes the flag.
# Nothing else is touched. phase7-mode-off.sh ends the mode.
. "$(dirname "$0")/lib.sh"

export MD="$CHECKOUT/CLAUDE.md"
export FLAG="$CHECKOUT/.claude/phase7-mode"
export HOOK="$CHECKOUT/scripts/hooks/claude-no-host-writes"
export BEGIN='<!-- phase7-mode: begin -->'
export END='<!-- phase7-mode: end -->'
export DEPLOY='{"tool_name":"Bash","tool_input":{"command":"scripts/nmas-host nmas -- nmas-deploy --wait"}}'
export PULL='{"tool_name":"Bash","tool_input":{"command":"scripts/nmas-host nmas -- git pull"}}'
W=$(mktemp -d)
export W
trap 'rm -rf "$W"' EXIT

plan "run as the operator's own user, not root" \
     "the hook in this checkout reads the mode's flag" \
     "the mode is off" \
     "CLAUDE.md has one Project heading to insert before" \
     "the flag is ignored by git" \
     "CLAUDE.md holds the section once" \
     "CLAUDE.md is unchanged outside the section" \
     "the flag is a regular file, owner-only" \
     "the hook lets nmas-deploy on a host through" \
     "the hook still refuses a git pull on a host"

not_root
check "the hook in this checkout reads the mode's flag" rc0 '' 'grep -q "def phase7_mode" "$HOOK"'
check "the mode is off" eq "off" '{ [ -e "$FLAG" ] || grep -qxF "$BEGIN" "$MD"; } && echo on || echo off'
check "CLAUDE.md has one Project heading to insert before" eq 1 'grep -cx "## Project" "$MD"'
check "the flag is ignored by git" eq "ignored" 'git -C "$CHECKOUT" check-ignore -q .claude/phase7-mode && echo ignored || echo "not ignored"'

cat > "$W/section.md" <<'SECTION'
<!-- phase7-mode: begin -->
## Phase 7 operating mode (in force)

**The operator's decision, 2026-10-09, for the rest of Phase 7** (the lab's Proxmox snapshots
and backups taken). Where a rule below makes something the operator's, this section governs. It
ends when the operator runs `scripts/host-steps/phase7-mode-off.sh`.

- **The agent runs deploys** (`nmas-deploy --wait`, CI green), host steps and host commands,
  sudo included, on the NMAS host and the lab host. A git write in a host's checkout stays
  refused (`scripts/hooks/claude-no-host-writes`, which reads the mode's flag). Proxmox stays
  read-only.
- **The agent runs device operations and walks through Mercury** (deploys, saves, restarts,
  redeploys), keeping the standing facts: nothing staged on s3, nothing in 08:30 to 09:10 UTC,
  a planned-restart window declared before a restart.
- **Boards the agent draws count as signed off by the operator, and the agent takes its
  recommended option on a decision;** each is one line in `docs/STANDING_APPROVAL_LOG.md`.
- Every commit still goes through the gate and is pushed, with CI green before the next.
- **Still the operator's; the agent stops and asks:** (1) any secret value: the operator types
  secrets, and the agent never prints, stores or reads one; (2) anything outside the lab:
  Cloudflare, DNS, GitHub visibility, anything public; (3) a new third-party package licence;
  (4) deleting or rotating backups or snapshots.
- Status to resume from, and anything waiting on the operator: `docs/END_OF_SESSION.md`.
<!-- phase7-mode: end -->
SECTION
awk -v sect="$W/section.md" '
    $0 == "## Project" { while ((getline line < sect) > 0) print line; print "" }
    { print }' "$MD" > "$W/CLAUDE.md"
cp "$MD" "$W/before.md"
SHA_BEFORE=$(sha256sum < "$MD" | cut -d' ' -f1)
export SHA_BEFORE

echo
echo "== THE CHANGE (nothing is written until you answer y)"
diff -u --label "CLAUDE.md" --label "CLAUDE.md, the mode on" "$MD" "$W/CLAUDE.md"
echo
echo "and writes the mode's flag, $FLAG (owner-only, gitignored), which"
echo "scripts/hooks/claude-no-host-writes reads."
read -r -p "Apply it? [y/N] " ANSWER
if [ "$ANSWER" != "y" ]; then
    echo "Nothing changed."
    exit 1
fi

ON_FAIL='cat "$W/before.md" > "$MD"; rm -f "$FLAG"; echo "CLAUDE.md put back, the flag removed"'
ON_FAIL_WHAT="put CLAUDE.md back and remove the flag"
step "write CLAUDE.md with the section" 'cat "$W/CLAUDE.md" > "$MD"'
step "write the mode's flag" 'umask 077 && printf "on %s\nclaude_md_sha256_before %s\n" "$(date -u +%FT%TZ)" "$SHA_BEFORE" > "$FLAG"'
check "CLAUDE.md holds the section once" eq 1 'grep -cxF "$BEGIN" "$MD"'
check "CLAUDE.md is unchanged outside the section" eq "$SHA_BEFORE" 'strip_marked "$MD" "$BEGIN" "$END" | sha256sum | cut -d" " -f1'
check "the flag is a regular file, owner-only" eq "regular file 600" 'stat -c "%F %a" "$FLAG"'
check "the hook lets nmas-deploy on a host through" eq 0 'printf "%s" "$DEPLOY" | env -u NMAS_PHASE7_FLAG python3 "$HOOK" >/dev/null 2>&1; echo $?'
check "the hook still refuses a git pull on a host" eq 2 'printf "%s" "$PULL" | env -u NMAS_PHASE7_FLAG python3 "$HOOK" >/dev/null 2>&1; echo $?'
summary
