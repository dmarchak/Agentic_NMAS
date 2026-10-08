#!/usr/bin/env bash
# C584 (docs/OPEN_FINDINGS.md): MinIO's loki-writer user held the built-in readwrite policy,
# every action on every bucket. Measured 2026-10-08: only Loki uses it, only on the loki bucket.
# This gives it a policy on that bucket alone (delete kept: Loki's compactor expires chunks),
# attached BEFORE readwrite is detached so Loki never loses access. Run it before Mercury's
# bucket exists. The operator's, on the NMAS host, with the mc alias `lab`:
#     bash <checkout>/scripts/host-steps/c584-loki-writer.sh
. "$(dirname "$0")/lib.sh"

export POLICY_DIR
POLICY_DIR=$(mktemp -d)
cat > "$POLICY_DIR/loki-only.json" <<'JSON'
{"Version":"2012-10-17","Statement":[
 {"Effect":"Allow","Action":["s3:GetBucketLocation","s3:ListBucket","s3:ListBucketMultipartUploads"],"Resource":["arn:aws:s3:::loki"]},
 {"Effect":"Allow","Action":["s3:GetObject","s3:PutObject","s3:DeleteObject","s3:AbortMultipartUpload","s3:ListMultipartUploadParts"],"Resource":["arn:aws:s3:::loki/*"]}]}
JSON

plan "run as the operator's own user, not root" \
     "the mc alias lab answers" \
     "loki-writer exists" \
     "loki-writer holds loki-only" \
     "loki-writer no longer holds readwrite" \
     "loki-only names the loki bucket and nothing else" \
     "Loki writes as loki-writer in 3 minutes" \
     "no request was refused in those 3 minutes" \
     "Loki logged no access denied"

not_root
check "the mc alias lab answers" rc0 "" 'mc admin info lab >/dev/null'
check "loki-writer exists" has "loki-writer" 'mc admin user list lab'

step "create (or update) the loki-only policy" 'mc admin policy create lab loki-only "$POLICY_DIR/loki-only.json"'
step "attach it to loki-writer" \
    'mc admin user info lab loki-writer | grep -q "loki-only" || mc admin policy attach lab loki-only --user loki-writer'
step "detach readwrite from loki-writer" \
    'mc admin user info lab loki-writer | grep -qw "readwrite" && mc admin policy detach lab readwrite --user loki-writer || true'

check "loki-writer holds loki-only" has "loki-only" 'mc admin user info lab loki-writer'
check "loki-writer no longer holds readwrite" lacks "readwrite" 'mc admin user info lab loki-writer'
check "loki-only names the loki bucket and nothing else" eq "arn:aws:s3:::loki
arn:aws:s3:::loki/*" \
    "mc admin policy info lab loki-only | grep -o 'arn:aws:s3:::[a-z*/-]*' | sort -u"
echo "== watching MinIO for 3 minutes (Loki flushes every few minutes)"
step "trace 3 minutes" 'timeout 180 mc admin trace -v lab > "$POLICY_DIR/trace.txt" 2>&1; true'
check "Loki writes as loki-writer in 3 minutes" ge 1 'grep -c "Credential=loki-writer" "$POLICY_DIR/trace.txt" || true'
check "no request was refused in those 3 minutes" eq "0" \
    'grep -ciE "AccessDenied|403 Forbidden" "$POLICY_DIR/trace.txt" || true'
check "Loki logged no access denied" eq "0" 'docker logs --since 10m loki 2>&1 | grep -ci accessdenied || true'
summary
