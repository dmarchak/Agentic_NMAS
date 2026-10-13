#!/usr/bin/env bash
# C749 (the operator, 2026-10-13): MinIO's root user was the factory default `minioadmin`, its
# API (9000) and console (9001) reachable from the lab LAN, and Thanos stored the root key. This
# step, the operator's, on the NMAS host, with the mc alias `lab` (the current root):
#     bash <checkout>/scripts/host-steps/minio-root-rotate.sh
#
#   1. a dated copy of /etc/default/minio and /etc/thanos/objstore.yml (root's, mode 700);
#   2. with the current root: a user `thanos` holding only its bucket (policy thanos-bucket),
#      and a user `mercury-cleanup` holding only s3:DeleteObject and s3:DeleteObjectVersion on
#      Mercury's bucket (policy mercury-cleanup), for future archive cleanups;
#   3. Thanos moved onto `thanos` (objstore.yml's keys), its services restarted, its bucket read;
#   4. the new root user and password in /etc/default/minio, MinIO restarted;
#   5. the proof: the new root answers, the old root is refused, Mercury's own key still answers,
#      Thanos still reads its bucket, the cleanup key deletes a probe of Mercury's and can neither
#      read an object nor delete in Thanos's bucket;
#   6. every mc alias naming this MinIO with the old root user removed (mc kept it in plaintext).
# Any failure after step 3 starts puts both files back from the copy and restarts MinIO and
# Thanos (ON_FAIL).
#
# Every secret is PROMPTED for (input hidden, twice), never printed, never an argument: it reaches
# mc on its standard input or in an environment variable (MC_HOST_<alias>), and the two files
# through a program's standard input. Generate each in another terminal, for example:
#     openssl rand -base64 30 | tr -d '/+='
. "$(dirname "$0")/lib.sh"

PY=${NMAS_PY:-/opt/mercury-venv/bin/python}
# MinIO's address as Mercury's own S3 setting names it (host:port), the one both use.
ENDPOINT=$(cd "$CHECKOUT" && "$PY" -c "from modules.integrations.s3_archive import S3ArchiveIntegration as S; print(S().url.split('://', 1)[-1].rstrip('/'))" 2>/dev/null)
ENVFILE=/etc/default/minio
OBJSTORE=/etc/thanos/objstore.yml
BUCKET=mercury
TBUCKET=thanos
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
COPY=/var/backups/minio/root-rotate-$STAMP
DIR=$(mktemp -d)
chmod 700 "$DIR"
export PYTHONDONTWRITEBYTECODE=1 CHECKOUT PY ENDPOINT ENVFILE OBJSTORE BUCKET TBUCKET COPY DIR
echo "== the dated copy goes to $COPY"

plan "run as the operator's own user, not root" \
     "this is the NMAS host: minio.service, flask-app.service, mc" \
     "the mc alias lab answers as an admin" \
     "the new root user is not the default and the four secrets are well formed and distinct" \
     "the dated copy reads back the same as the originals" \
     "thanos and mercury-cleanup exist, each holding only its policy" \
     "Thanos reads its bucket with its own key" \
     "MinIO answers after its restart" \
     "the new root answers as an admin" \
     "the old root is refused" \
     "Mercury's own key still answers" \
     "Thanos still reads its bucket" \
     "the cleanup key deletes a probe of Mercury's, every version" \
     "the cleanup key can neither read an object nor delete in Thanos's bucket" \
     "no mc alias of this MinIO holds the old root user"

not_root
check "this is the NMAS host: minio.service, flask-app.service, mc" eq "yes" \
    'systemctl cat minio.service >/dev/null 2>&1 && systemctl cat flask-app.service >/dev/null 2>&1 && command -v mc >/dev/null && [ -x "$PY" ] && [ -n "$ENDPOINT" ] && echo yes || echo no'
check "the mc alias lab answers as an admin" rc0 "" 'mc admin info lab >/dev/null'

OLD_USER=$(sudo grep -E '^MINIO_ROOT_USER=' "$ENVFILE" | head -1 | cut -d= -f2- | tr -d '"')
read -r -p "The new root user (not minioadmin; letters, digits, _ and -, 8 or more): " NEW_USER
ask() {   # ask VAR "words": a secret, hidden, twice
    local a b
    read -r -s -p "$2 (hidden): " a; echo
    read -r -s -p "The same again: " b; echo
    if [ "$a" != "$b" ]; then
        echo "The two entries differ; nothing was changed."
        _stop "the new root user is not the default and the four secrets are well formed and distinct"
    fi
    printf -v "$1" '%s' "$a"
}
ask NEW_PW "The new root password"
ask THANOS_PW "The secret for the user thanos"
ask CLEANUP_PW "The secret for the user mercury-cleanup"
REDACT=$NEW_PW
# A check runs in a child shell: it sees only what is exported (C748).
export OLD_USER NEW_USER NEW_PW THANOS_PW CLEANUP_PW
check "the new root user is not the default and the four secrets are well formed and distinct" eq "ok" \
    '[[ "$NEW_USER" =~ ^[A-Za-z0-9_-]{8,}$ ]] && [ "$NEW_USER" != minioadmin ] && [ "$NEW_USER" != "$OLD_USER" ] \
     && for s in "$NEW_PW" "$THANOS_PW" "$CLEANUP_PW"; do [[ "$s" =~ ^[A-Za-z0-9._~-]{20,}$ ]] || exit 0; done \
     && [ "$NEW_PW" != "$THANOS_PW" ] && [ "$NEW_PW" != "$CLEANUP_PW" ] && [ "$THANOS_PW" != "$CLEANUP_PW" ] && echo ok'

step "a fresh dated copy of MinIO's and Thanos's configuration (root's, mode 700)" \
    'sudo install -d -m 700 "$COPY" && sudo cp -a "$ENVFILE" "$OBJSTORE" "$COPY/"'
check "the dated copy reads back the same as the originals" rc0 "" \
    'sudo cmp "$ENVFILE" "$COPY/minio" && sudo cmp "$OBJSTORE" "$COPY/objstore.yml"'

cat > "$DIR/thanos-bucket.json" <<JSON
{"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": ["s3:*"],
 "Resource": ["arn:aws:s3:::$TBUCKET", "arn:aws:s3:::$TBUCKET/*"]}]}
JSON
cat > "$DIR/mercury-cleanup.json" <<JSON
{"Version": "2012-10-17", "Statement": [{"Effect": "Allow",
 "Action": ["s3:DeleteObject", "s3:DeleteObjectVersion"],
 "Resource": ["arn:aws:s3:::$BUCKET/*"]}]}
JSON
# policy_of USER: the policy attached to USER on lab, from mc's JSON field (C752: grepping the
# text for a policy named like its user always matched the user's own name, so mercury-cleanup's
# attach was skipped on the first run). Exported, so a step's command can use it.
policy_of() {
    mc admin user info lab "$1" --json | python3 -c "import sys, json; print(json.load(sys.stdin).get('policyName') or '')"
}
export -f policy_of
step "the two policies" \
    'mc admin policy create lab thanos-bucket "$DIR/thanos-bucket.json" >/dev/null && mc admin policy create lab mercury-cleanup "$DIR/mercury-cleanup.json" >/dev/null'
step "the users thanos and mercury-cleanup (keys on mc's standard input), each its one policy" \
    'printf "%s\n%s\n" thanos "$THANOS_PW" | mc admin user add lab >/dev/null && printf "%s\n%s\n" mercury-cleanup "$CLEANUP_PW" | mc admin user add lab >/dev/null \
     && { [ "$(policy_of thanos)" = thanos-bucket ] || mc admin policy attach lab thanos-bucket --user thanos >/dev/null; } \
     && { [ "$(policy_of mercury-cleanup)" = mercury-cleanup ] || mc admin policy attach lab mercury-cleanup --user mercury-cleanup >/dev/null; }'
check "thanos and mercury-cleanup exist, each holding only its policy" eq "thanos-bucket mercury-cleanup" \
    'echo "$(mc admin user info lab thanos --json | python3 -c "import sys,json; print(json.load(sys.stdin).get(\"policyName\"))") $(mc admin user info lab mercury-cleanup --json | python3 -c "import sys,json; print(json.load(sys.stdin).get(\"policyName\"))")"'

cat > "$DIR/set_keys.py" <<'PY'
"""Rewrite one file's key lines in place, keeping its owner and mode. Standard input: one value
per line, in the order of the keys named. Usage: set_keys.py FILE KEY[=SEP] ...
SEP is ': ' for YAML (access_key: "x") or '=' for an environment file (MINIO_ROOT_USER=x)."""
import os
import re
import sys

path, keys = sys.argv[1], sys.argv[2:]
values = sys.stdin.read().split("\n")
st = os.stat(path)
text = open(path, encoding="utf-8").read()
for key, value in zip(keys, values):
    name, sep = (key.split("=", 1)[0], "=") if key.endswith("=") else (key, ": ")
    pat = re.compile(rf"^(\s*{re.escape(name)}{re.escape(sep.strip()) or '='}\s*).*$", re.M)
    if len(pat.findall(text)) != 1:
        sys.exit(f"{path}: {name} is not set exactly once")
    quoted = f'"{value}"' if sep == ": " else value
    text = pat.sub(lambda m: m.group(1) + quoted, text)
tmp = f"{path}.{os.getpid()}.tmp"
with open(tmp, "w", encoding="utf-8") as fh:
    fh.write(text)
os.chown(tmp, st.st_uid, st.st_gid)
os.chmod(tmp, st.st_mode & 0o7777)
os.replace(tmp, path)
PY

ON_FAIL='sudo install -m "$(sudo stat -c %a "$COPY/minio")" -o root -g root "$COPY/minio" "$ENVFILE"; sudo cp -p "$COPY/objstore.yml" "$OBJSTORE"; sudo systemctl restart minio; sleep 5; sudo systemctl restart thanos-sidecar thanos-store thanos-compact'
ON_FAIL_WHAT="MinIO's and Thanos's files put back from the dated copy, both restarted"
step "Thanos's objstore.yml on the user thanos (the values on standard input)" \
    'printf "%s\n%s" thanos "$THANOS_PW" | sudo python3 "$DIR/set_keys.py" "$OBJSTORE" access_key secret_key'
step "Thanos's three bucket services restarted" \
    'sudo systemctl restart thanos-sidecar thanos-store thanos-compact && sleep 10'
check "Thanos reads its bucket with its own key" rc0 "" \
    'sudo -u prometheus thanos tools bucket ls --objstore.config-file="$OBJSTORE" >/dev/null 2>&1'

step "the new root in MinIO's environment file (the values on standard input)" \
    'printf "%s\n%s" "$NEW_USER" "$NEW_PW" | sudo python3 "$DIR/set_keys.py" "$ENVFILE" MINIO_ROOT_USER= MINIO_ROOT_PASSWORD='
step "MinIO restarted" 'sudo systemctl restart minio'
check "MinIO answers after its restart" rc0 "" \
    'for i in $(seq 1 30); do curl -sf "http://$ENDPOINT/minio/health/live" && exit 0; sleep 1; done; exit 1'

check "the new root answers as an admin" rc0 "" \
    'MC_HOST_newroot=$(printf "%s" "$NEW_PW" | python3 -c "import sys, os, urllib.parse as u; print(\"http://\" + u.quote(os.environ[\"NEW_USER\"], safe=\"\") + \":\" + u.quote(sys.stdin.read(), safe=\"\") + \"@\" + os.environ[\"ENDPOINT\"])") mc admin info newroot >/dev/null'
check "the old root is refused" re "refused" \
    'mc admin info lab >/dev/null 2>&1 && echo "the old root still answers" || echo refused'
check "Mercury's own key still answers" eq "True" \
    'cd "$CHECKOUT" && "$PY" -c "from modules.integrations.s3_archive import S3ArchiveIntegration as S; print(S().test_connection(write=False).get(\"ok\"))"'
check "Thanos still reads its bucket" rc0 "" \
    'sudo -u prometheus thanos tools bucket ls --objstore.config-file="$OBJSTORE" >/dev/null 2>&1'

cat > "$DIR/cleanup_check.py" <<'PY'
"""The cleanup key, proved: a probe written by Mercury's own key under _probe/, deleted (every
version) by the cleanup key; the cleanup key refused a read of it and a delete in Thanos's
bucket. The cleanup secret on standard input. Prints the outcomes, never a key."""
import os
import sys

sys.path.insert(0, os.getcwd())
from modules.integrations.s3_archive import S3ArchiveIntegration  # noqa: E402

secret = sys.stdin.read()
s3 = S3ArchiveIntegration()
own = s3.client()
clean = s3.client(credentials=("mercury-cleanup", secret))
key = s3.key("_probe", "cleanup-key-test")
own.put_object(Bucket=s3.bucket, Key=key, Body=b"probe")


def refused(fn):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        return "AccessDenied" in str(exc) or "Forbidden" in str(exc) or "403" in str(exc)
    return False


read_refused = refused(lambda: clean.get_object(Bucket=s3.bucket, Key=key))
other_refused = refused(lambda: clean.delete_object(Bucket=os.environ["TBUCKET"],
                                                    Key="_probe/never-there"))
vs = own.list_object_versions(Bucket=s3.bucket, Prefix=key)
for v in (vs.get("Versions") or []) + (vs.get("DeleteMarkers") or []):
    if v["Key"] == key:
        clean.delete_object(Bucket=s3.bucket, Key=key, VersionId=v["VersionId"])
left = [v for v in (own.list_object_versions(Bucket=s3.bucket, Prefix=key).get("Versions") or [])
        + (own.list_object_versions(Bucket=s3.bucket, Prefix=key).get("DeleteMarkers") or [])
        if v["Key"] == key]
print(f"deleted every version: {not left}; read refused: {read_refused}; "
      f"delete in {os.environ['TBUCKET']} refused: {other_refused}")
PY
check "the cleanup key deletes a probe of Mercury's, every version" has "deleted every version: True" \
    'cd "$CHECKOUT" && printf "%s" "$CLEANUP_PW" | "$PY" "$DIR/cleanup_check.py"'
check "the cleanup key can neither read an object nor delete in Thanos's bucket" has "read refused: True; delete in thanos refused: True" \
    'cd "$CHECKOUT" && printf "%s" "$CLEANUP_PW" | "$PY" "$DIR/cleanup_check.py"'

ON_FAIL=""
# Only aliases naming THIS MinIO (its endpoint, or loopback on its port): the first run removed
# `dr` too, an alias of the replica, whose own root is also named minioadmin (C752). mine.py
# prints each such alias holding the old root user.
cat > "$DIR/mine.py" <<'PY'
"""The mc aliases that name this MinIO and hold the old root user, one per line."""
import json
import os
import sys
from urllib.parse import urlsplit

host, _, port = os.environ["ENDPOINT"].rpartition(":")
here = {(host, port), ("localhost", port), ("127.0.0.1", port), ("::1", port)}
for d in map(json.loads, filter(str.strip, sys.stdin)):
    u = urlsplit(d.get("URL") or d.get("url") or "")
    if (u.hostname, str(u.port or "")) in here and d.get("accessKey") == os.environ["OLD_USER"]:
        print(d["alias"])
PY
step "remove every mc alias naming this MinIO with the old root user (mc keeps keys in plaintext)" \
    'for a in $(mc alias list --json | python3 "$DIR/mine.py"); do mc alias remove "$a" >/dev/null && echo "removed alias $a"; done; true'
check "no mc alias of this MinIO holds the old root user" eq "0" \
    'mc alias list --json | python3 "$DIR/mine.py" | wc -l'
unset NEW_PW THANOS_PW CLEANUP_PW
rm -rf "$DIR"
echo "== the dated copy: $COPY. Keep the new root password where the break-glass record is kept."
summary
