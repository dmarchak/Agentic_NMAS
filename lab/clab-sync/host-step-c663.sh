#!/usr/bin/env bash
# C663 step 1's host step, on the NMAS host, from the updated checkout, right after the deploy
# that moves the lab's startup sync into lab/clab-sync/ (LAB TOOLING, not the product).
#
#   bash lab/clab-sync/host-step-c663.sh
#
# 1. The lab's own map, data/lab_targets/Default.tsv (gitignored, owner-only), written from
#    what the app serves now at /clab/sync_targets (the route stays until C663 step 2 removes
#    it), so the sync reads exactly the rows it read before.
# 2. The sync's symlink in ~/lab-configs repointed from scripts/ to lab/clab-sync/.
# 3. Two links that now point at nothing removed (the old name's link, the old helper's).
# 4. The path unit re-rendered and installed: it watches baseline-earned AND golden-committed.
# Each step is checked; the first failure stops it, naming what it compared.
set -euo pipefail

CHECKOUT="$(cd "$(dirname "$(readlink -f "$0")")/../.." && pwd)"
LIST=Default
MAP="$CHECKOUT/data/lab_targets/$LIST.tsv"

echo "== 1. the lab's map from the app's /clab/sync_targets"
mkdir -p "$CHECKOUT/data/lab_targets"
tmp="$(mktemp "$CHECKOUT/data/lab_targets/.$LIST.XXXXXX")"
curl -sf "http://127.0.0.1:5000/clab/sync_targets?list=$LIST" -o "$tmp"
rows="$(grep -cv '^#' "$tmp" || true)"
[ "$rows" -ge 1 ] || { echo "REFUSED - the app served $rows device rows, expected at least 1"; rm -f "$tmp"; exit 2; }
chmod 600 "$tmp" && mv "$tmp" "$MAP"
echo "   $MAP: $rows device row(s)"

echo "== 2. the sync's link repointed to lab/clab-sync/"
ln -sfn "$CHECKOUT/lab/clab-sync/clab-startup-sync.sh" "$HOME/lab-configs/clab-startup-sync.sh"
target="$(readlink -f "$HOME/lab-configs/clab-startup-sync.sh")"
[ "$target" = "$CHECKOUT/lab/clab-sync/clab-startup-sync.sh" ] || { echo "REFUSED - the link resolves to $target"; exit 2; }
echo "   ~/lab-configs/clab-startup-sync.sh -> $target"

echo "== 3. links to removed files"
for l in "$HOME/lab-configs/oxidized-to-config.sh" "$HOME/bin/nmas-clab-targets"; do
  if [ -L "$l" ] && [ ! -e "$l" ]; then rm -f "$l"; echo "   removed $l (pointed at nothing)"; fi
done

echo "== 4. the path unit, watching both events"
d="$(mktemp -d)"
"$CHECKOUT/scripts/nmas-render-units" --out "$d" "$CHECKOUT/lab/clab-sync/clab-sync.path"
sudo install -o root -g root -m 0644 "$d/clab-sync.path" /etc/systemd/system/clab-sync.path
sudo systemctl daemon-reload
sudo systemctl restart clab-sync.path
watched="$(systemctl show clab-sync.path -p Paths --value)"
echo "   watching: $watched"
case "$watched" in *golden-committed/$LIST*) ;; *) echo "REFUSED - the unit does not watch golden-committed/$LIST"; exit 2 ;; esac
systemctl is-active clab-sync.path

echo "== 5. the helper reads the map"
"$CHECKOUT/lab/clab-sync/clab-targets" --list "$LIST" | wc -l
echo "done"
