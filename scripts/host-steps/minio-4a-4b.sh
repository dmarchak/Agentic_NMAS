#!/usr/bin/env bash
# Phase 4 step 1, host steps 4a and 4b (docs/NSOT_PHASE4_MINIO.md section 4): Mercury's bucket,
# versioned like the others, and the policy its key will hold (deploy/minio/mercury-rw.json:
# list, read, write and multipart on `mercury` only; no delete, M-2). The operator's, on the
# NMAS host, with the mc alias `lab`, after c584-loki-writer.sh:
#     bash <checkout>/scripts/host-steps/minio-4a-4b.sh
. "$(dirname "$0")/lib.sh"

export POLICY="$CHECKOUT/deploy/minio/mercury-rw.json"

plan "run as the operator's own user, not root" \
     "the mc alias lab answers" \
     "C584 is done first: loki-writer no longer holds readwrite" \
     "the checkout holds the policy file" \
     "the bucket exists" \
     "the bucket is versioned" \
     "mercury-rw names the mercury bucket and nothing else" \
     "mercury-rw grants no delete"

not_root
check "the mc alias lab answers" rc0 "" 'mc admin info lab >/dev/null'
check "C584 is done first: loki-writer no longer holds readwrite" lacks "readwrite" \
    'mc admin user info lab loki-writer'
check "the checkout holds the policy file" eq "yes" '[ -s "$POLICY" ] && echo yes'

step "make the bucket" 'mc mb --ignore-existing lab/mercury'
step "version it" 'mc version enable lab/mercury'
step "create (or update) the mercury-rw policy" 'mc admin policy create lab mercury-rw "$POLICY"'

check "the bucket exists" eq "1" "mc ls lab | grep -c ' mercury/\$' || true"
check "the bucket is versioned" has "versioning is enabled" 'mc version info lab/mercury'
check "mercury-rw names the mercury bucket and nothing else" eq "arn:aws:s3:::mercury
arn:aws:s3:::mercury/*" \
    "mc admin policy info lab mercury-rw | grep -o 'arn:aws:s3:::[a-z*/-]*' | sort -u"
check "mercury-rw grants no delete" lacks "Delete" 'mc admin policy info lab mercury-rw'
summary
