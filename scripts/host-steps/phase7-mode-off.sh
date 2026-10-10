#!/usr/bin/env bash
# Phase 7 operating mode, OFF: undoes phase7-mode-on.sh (the operator's, 2026-10-09). The
# operator runs it on the LAPTOP, in the same checkout:
#
#   scripts/host-steps/phase7-mode-off.sh
#
# It prints the change and asks before making it: the mode's flag (.claude/phase7-mode) is
# removed FIRST, so a failure after it leaves the mode off, and then CLAUDE.md loses its marked
# "Phase 7 operating mode" section, every other line kept. It says whether CLAUDE.md returns to
# exactly what it was before mode-on (the hash the flag recorded), or differs by edits made
# while the mode was on, which are kept. Then scripts/hooks/claude-no-host-writes refuses
# nmas-deploy on a host again, and a check proves it.
. "$(dirname "$0")/lib.sh"

export MD="$CHECKOUT/CLAUDE.md"
export FLAG="$CHECKOUT/.claude/phase7-mode"
export HOOK="$CHECKOUT/scripts/hooks/claude-no-host-writes"
export BEGIN='<!-- phase7-mode: begin -->'
export END='<!-- phase7-mode: end -->'
export DEPLOY='{"tool_name":"Bash","tool_input":{"command":"scripts/nmas-host nmas -- nmas-deploy --wait"}}'
W=$(mktemp -d)
export W
trap 'rm -rf "$W"' EXIT

plan "run as the operator's own user, not root" \
     "the mode is on: its flag or its section" \
     "the section is whole: as many ends as begins, at most one" \
     "the flag is gone" \
     "CLAUDE.md holds no section" \
     "CLAUDE.md is unchanged outside the section" \
     "the hook refuses nmas-deploy on a host again"

not_root
check "the mode is on: its flag or its section" eq "on" '{ [ -e "$FLAG" ] || grep -qxF "$BEGIN" "$MD"; } && echo on || echo off'
check "the section is whole: as many ends as begins, at most one" eq "whole" 'b=$(grep -cxF "$BEGIN" "$MD"); e=$(grep -cxF "$END" "$MD"); [ "$b" = "$e" ] && [ "$b" -le 1 ] && echo whole || echo "begins $b, ends $e"'

strip_marked "$MD" "$BEGIN" "$END" > "$W/CLAUDE.md"
SHA_KEPT=$(sha256sum < "$W/CLAUDE.md" | cut -d' ' -f1)
export SHA_KEPT
RECORDED=""
if [ -f "$FLAG" ]; then
    RECORDED=$(sed -n 's/^claude_md_sha256_before //p' "$FLAG")
fi

echo
echo "== THE CHANGE (nothing is written until you answer y)"
echo "removes the mode's flag, $FLAG$([ -e "$FLAG" ] || echo ' (already absent)'), and:"
diff -u --label "CLAUDE.md" --label "CLAUDE.md, the mode off" "$MD" "$W/CLAUDE.md"
if [ -z "$RECORDED" ]; then
    echo "No record of CLAUDE.md before mode-on (the flag is absent or holds none)."
elif [ "$RECORDED" = "$SHA_KEPT" ]; then
    echo "CLAUDE.md returns to exactly what it was before mode-on."
else
    echo "CLAUDE.md will differ from what it was before mode-on, outside the section: edits made"
    echo "while the mode was on, which are kept (git diff shows them)."
fi
read -r -p "Apply it? [y/N] " ANSWER
if [ "$ANSWER" != "y" ]; then
    echo "Nothing changed."
    exit 1
fi

step "remove the mode's flag" 'rm -f "$FLAG"'
step "write CLAUDE.md without the section" 'cat "$W/CLAUDE.md" > "$MD"'
check "the flag is gone" eq "gone" '[ -e "$FLAG" ] && echo present || echo gone'
check "CLAUDE.md holds no section" eq 0 'grep -cF "<!-- phase7-mode:" "$MD"'
check "CLAUDE.md is unchanged outside the section" eq "$SHA_KEPT" 'sha256sum < "$MD" | cut -d" " -f1'
check "the hook refuses nmas-deploy on a host again" eq 2 'printf "%s" "$DEPLOY" | env -u NMAS_PHASE7_FLAG python3 "$HOOK" >/dev/null 2>&1; echo $?'
summary
