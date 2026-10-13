#!/usr/bin/env bash
# C729 (docs/OPEN_FINDINGS.md; the operator, 2026-10-13: "I'd rather the backup never holds both
# halves"): the application key moves off the disk the nightly VM image copies, onto a disk of
# its own that the hypervisor leaves out of every image (the disk's backup=0), and data/key.key
# becomes a link to it. The stores stay where they are; an image then holds the sealed values
# and never the key that opens them. Recovery of the key is the break-glass record, so this
# refuses unless an intact export of THIS key exists.
#
# Before: Mercury deployed with the key guard (C729: no key is made for a sealed store, and a
# link to a key that is not there refuses by name), and the disk attached on the hypervisor:
#     qm set <vmid> --scsi1 <storage>:1,backup=0,serial=nmas-key,discard=on,iothread=1,ssd=1
# Run on the NMAS host, with sudo (it formats the new disk, mounts it, and writes /etc/fstab):
#     sudo bash <checkout>/scripts/host-steps/c729-key-disk.sh
# Never prints the key: only its fingerprint (breakglass.key_fingerprint, 16 hex of a sha256).
# Run again it changes nothing it already did, and checks the end state.
. "$(dirname "$0")/lib.sh"

PY=${NMAS_PY:-/opt/mercury-venv/bin/python}
export PYTHONDONTWRITEBYTECODE=1
MOUNT=/var/lib/nmas-key
FP='import sys; sys.path.insert(0, sys.argv[1]); from modules.breakglass import key_fingerprint; print(key_fingerprint(open(sys.argv[2], "rb").read()))'

plan "run as root" \
     "an intact break-glass export holds this key" \
     "exactly one disk carries the serial nmas-key" \
     "the disk is blank or already the key disk" \
     "the key disk is mounted at /var/lib/nmas-key" \
     "the key on the key disk is the key Mercury had" \
     "the key is owner-only on the key disk" \
     "data/key.key is a link to the key disk" \
     "Mercury reads the same key through the link" \
     "no key file is left in the data directory"

check "run as root" eq "0" 'id -u'

# Where the key is (config.KEY_FILE, read as the checkout's owner), and who reads it: the key
# file's own owner, measured, which is the user Mercury runs as.
KEY=$(cd "$CHECKOUT" && sudo -u "$(stat -c %U "$CHECKOUT")" env PYTHONDONTWRITEBYTECODE=1 \
      "$PY" -c 'from modules.config import KEY_FILE; print(KEY_FILE)')
DATA=$(dirname "$KEY")
OWNER=$(stat -L -c %U "$KEY")
GROUP=$(stat -L -c %G "$KEY")
as_owner() { sudo -u "$OWNER" env PYTHONDONTWRITEBYTECODE=1 "$@"; }
export CHECKOUT KEY DATA MOUNT OWNER GROUP PY FP
export -f as_owner
echo "   key read by: $OWNER:$GROUP"

# The fingerprint of the key in use, wherever it is now (the file, or the link's target).
BEFORE=$(as_owner "$PY" -c "$FP" "$CHECKOUT" "$KEY")
export BEFORE
echo "   key in use: fingerprint $BEFORE, at $KEY"

# An export naming this key, and, when it was downloaded, the browser's word that it arrived
# whole (breakglass_intact.jsonl). The newest such export is printed: when, which list.
check "an intact break-glass export holds this key" has "intact export" \
    'as_owner "$PY" -c "
import json, os, sys, time
data, fp = sys.argv[1], sys.argv[2]
def rows(name):
    path = os.path.join(data, name)
    if not os.path.exists(path):
        return []
    return [json.loads(l) for l in open(path, encoding=\"utf-8\") if l.strip()]
intact = {r.get(\"sha256\") for r in rows(\"breakglass_intact.jsonl\") if r.get(\"ok\")}
good = [r for r in rows(\"breakglass_exports.jsonl\") if r.get(\"key_fingerprint\") == fp
        and (r.get(\"via\") != \"browser\" or r.get(\"sha256\") in intact)]
if not good:
    print(\"no export holds key \" + fp + \": make a break-glass export first, and keep it\")
    sys.exit(1)
r = max(good, key=lambda r: r.get(\"at\", 0))
print(\"intact export of \" + r.get(\"list\", \"\") + \" at \" + time.strftime(\"%Y-%m-%d %H:%M UTC\", time.gmtime(r.get(\"at\", 0))))
" "$DATA" "$BEFORE"'

check "exactly one disk carries the serial nmas-key" eq "1" \
    'ls /dev/disk/by-id/ | grep -E "_nmas-key$" | wc -l'
DISK=$(readlink -f "/dev/disk/by-id/$(ls /dev/disk/by-id/ | grep -E '_nmas-key$' | head -1)")
export DISK
echo "   key disk: $DISK"

# Formatted only when it holds no signature at all; an existing ext4 labelled nmas-key is ours.
check "the disk is blank or already the key disk" re "^(blank|ext4 nmas-key)$" \
    'sig=$(blkid -o export "$DISK" 2>/dev/null); if [ -z "$sig" ]; then echo blank; else echo "$(echo "$sig" | sed -n "s/^TYPE=//p") $(echo "$sig" | sed -n "s/^LABEL=//p")"; fi'

if [ -z "$(blkid -o export "$DISK" 2>/dev/null)" ]; then
    step "format the key disk (ext4, label nmas-key)" 'mkfs.ext4 -q -L nmas-key "$DISK"'
fi
UUID=$(blkid -s UUID -o value "$DISK")
export UUID
step "the mount point, owner-only" \
    'install -d -m 700 -o "$OWNER" -g "$GROUP" "$MOUNT"'
# nofail: a key disk that does not attach must not stop the VM booting; Mercury then refuses
# to start, naming the link and its missing target (the key guard), which is the visible state.
step "an /etc/fstab line for the key disk, once" \
    'grep -qE "^UUID=$UUID[[:space:]]" /etc/fstab || printf "UUID=%s %s ext4 defaults,nodev,nosuid,noexec,nofail,x-systemd.device-timeout=10s 0 2\n" "$UUID" "$MOUNT" >> /etc/fstab'
step "mount it" 'systemctl daemon-reload && (findmnt -n "$MOUNT" >/dev/null || mount "$MOUNT")'
step "the mounted root owner-only" 'chown "$OWNER:$GROUP" "$MOUNT" && chmod 700 "$MOUNT"'
check "the key disk is mounted at /var/lib/nmas-key" eq "UUID=$UUID" \
    'echo "UUID=$(findmnt -no UUID "$MOUNT")"'

if [ ! -L "$KEY" ]; then
    step "copy the key to the key disk, owner-only" \
        '[ -e "$MOUNT/key.key" ] && cmp -s "$KEY" "$MOUNT/key.key" || install -m 600 -o "$OWNER" -g "$GROUP" "$KEY" "$MOUNT/key.key"'
fi
check "the key on the key disk is the key Mercury had" eq "$BEFORE" \
    'as_owner "$PY" -c "$FP" "$CHECKOUT" "$MOUNT/key.key"'
check "the key is owner-only on the key disk" eq "600 $OWNER" 'stat -c "%a %U" "$MOUNT/key.key"'

if [ ! -L "$KEY" ]; then
    # From here a failure puts the file back where it was (the copy on the key disk is proven
    # the same key just above).
    ON_FAIL='[ -L "$KEY" ] && cp --remove-destination "$MOUNT/key.key" "$KEY" && chown "$OWNER:$GROUP" "$KEY" && chmod 600 "$KEY" && echo "data/key.key is a file again"'
    ON_FAIL_WHAT="put the key file back in the data directory"
    export ON_FAIL
    step "replace data/key.key by a link to the key disk, in one rename" \
        'ln -s "$MOUNT/key.key" "$DATA/.key.link" && chown -h "$OWNER:$GROUP" "$DATA/.key.link" && mv -T "$DATA/.key.link" "$KEY"'
fi
check "data/key.key is a link to the key disk" eq "$MOUNT/key.key" 'readlink "$KEY"'
check "Mercury reads the same key through the link" eq "$BEFORE" \
    'cd "$CHECKOUT" && as_owner "$PY" -c "from modules.config import read_or_create_fernet_key as k; from modules.breakglass import key_fingerprint as f; print(f(k()))"'
check "no key file is left in the data directory" eq "" \
    'find "$DATA" -maxdepth 1 -name "key.key*" -type f'
# The removed file's blocks are returned to the hypervisor, so the next image holds no copy.
step "trim the root filesystem" 'fstrim -v /'
summary
