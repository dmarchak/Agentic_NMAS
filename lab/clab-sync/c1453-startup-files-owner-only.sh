#!/usr/bin/env bash
# C1453's one-off (LAB TOOLING; the lab host, after the one-file redeploy's B step): the lab's
# startup files hold every device's accounts and SNMP communities, and until the sync made them
# owner-only from creation (clab-startup-sync.sh, `umask 077`) they and their timestamped
# backups were written 0664 (read 2026-10-20). This step, for one lab folder:
#   1. makes every `configs/*.cfg` 0600, and every `configs.bak-*` backup 0700 with its files
#      0600 (go-rwx);
#   2. ignores the backups in the lab's repository (`/configs.bak-*/`, `/backup-*/` in
#      .gitignore), so `git status` stops listing them; .gitignore is then the operator's to
#      commit;
#   3. deletes NOTHING: removing a backup is the operator's.
# Run on the lab host as the lab's own user (never root):
#     bash c1453-startup-files-owner-only.sh [lab folder, default ~/labs/lab]
set -uo pipefail

LAB=${1:-$HOME/labs/lab}
fail=0
pass() { echo "PASS  $*"; }
bad() { echo "FAIL  $*"; fail=1; }

[ "$(id -u)" -ne 0 ] || { echo "REFUSED: run as the lab's own user, not root"; exit 2; }
[ -d "$LAB/configs" ] || { echo "REFUSED: $LAB has no configs/ folder"; exit 2; }
git -C "$LAB" rev-parse --git-dir >/dev/null 2>&1 \
    || { echo "REFUSED: $LAB is not a git repository"; exit 2; }
shopt -s nullglob
cfgs=("$LAB"/configs/*.cfg)
baks=("$LAB"/configs.bak-*)
[ "${#cfgs[@]}" -gt 0 ] || { echo "REFUSED: $LAB/configs holds no .cfg file"; exit 2; }

open_files() {   # files or folders under the given paths readable or writable by group or other
    find "$@" \( -perm -g=r -o -perm -o=r -o -perm -g=w -o -perm -o=w \) -print 2>/dev/null
}
echo "== $LAB: ${#cfgs[@]} startup file(s), ${#baks[@]} backup folder(s)"
echo "   before: $(open_files "${cfgs[@]}" "${baks[@]}" | wc -l) path(s) open to group or other"

chmod 600 -- "${cfgs[@]}"
[ "${#baks[@]}" -eq 0 ] || chmod -R go-rwx -- "${baks[@]}"

left=$(open_files "${cfgs[@]}" "${baks[@]}" | wc -l)
[ "$left" -eq 0 ] && pass "every startup file is 0600 and every backup is owner-only" \
    || bad "$left path(s) still open to group or other"
for f in "${cfgs[@]}"; do
    [ "$(stat -c %a "$f")" = 600 ] || bad "$(basename "$f") is $(stat -c %a "$f"), not 600"
done

touch "$LAB/.gitignore"
for pat in '/configs.bak-*/' '/backup-*/'; do
    grep -qxF -- "$pat" "$LAB/.gitignore" || printf '%s\n' "$pat" >> "$LAB/.gitignore"
done
grep -qxF '/configs.bak-*/' "$LAB/.gitignore" && grep -qxF '/backup-*/' "$LAB/.gitignore" \
    && pass ".gitignore ignores the backups (/configs.bak-*/, /backup-*/)" \
    || bad ".gitignore does not hold both patterns"
untracked=$(git -C "$LAB" status --porcelain --untracked-files=normal \
    | grep -cE '^\?\? (configs\.bak-|backup-)' || true)
[ "$untracked" -eq 0 ] && pass "git status lists no backup folder" \
    || bad "git status still lists $untracked backup folder(s)"

echo "== nothing was deleted; commit .gitignore in $LAB (the operator's)"
[ "$fail" -eq 0 ] && { echo "== RESULT: PASS"; exit 0; } || { echo "== RESULT: FAIL"; exit 1; }
