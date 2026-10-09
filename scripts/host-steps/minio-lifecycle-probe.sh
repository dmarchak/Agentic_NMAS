#!/usr/bin/env bash
# MinIO lifecycle for the Test's probe (docs/NSOT_PHASE4_MINIO.md, M-2): Mercury's key cannot
# delete and the bucket is versioned, so every Settings Test leaves another version of
# _probe/mercury-connection-test. This rule expires those noncurrent versions after a day;
# the current probe stays (one object). MinIO's lifecycle does the expiry, never Mercury.
# The operator's, on the NMAS host, with the mc alias `lab`, after minio-4a-4b.sh:
#     bash <checkout>/scripts/host-steps/minio-lifecycle-probe.sh
. "$(dirname "$0")/lib.sh"

plan "run as the operator's own user, not root" \
     "the mc alias lab answers" \
     "the bucket mercury exists and is versioned" \
     "a rule names the _probe/ prefix" \
     "it expires noncurrent versions after 1 day" \
     "it expires no current object" \
     "it is the only rule on _probe/"

not_root
check "the mc alias lab answers" rc0 "" 'mc admin info lab >/dev/null'
check "the bucket mercury exists and is versioned" has "versioning is enabled" \
    'mc version info lab/mercury'

step "add the rule (once: an existing _probe/ rule is left as it is)" \
    'mc ilm rule ls lab/mercury --json 2>/dev/null | tr -d " \n" | grep -q "\"Prefix\":\"_probe/\"" || mc ilm rule add --prefix "_probe/" --noncurrent-expire-days 1 lab/mercury'
echo "== the bucket's rules now:"
mc ilm rule ls lab/mercury 2>&1

check "a rule names the _probe/ prefix" has '"Prefix":"_probe/"' 'mc ilm rule ls lab/mercury --json | tr -d " \n"'
check "it expires noncurrent versions after 1 day" has '"NoncurrentDays":1' \
    'mc ilm rule ls lab/mercury --json | tr -d " \n"'
check "it expires no current object" lacks '"Expiration":{"Days"' 'mc ilm rule ls lab/mercury --json | tr -d " \n"'
check "it is the only rule on _probe/" eq "1" \
    'mc ilm rule ls lab/mercury --json | tr -d " \n" | grep -o "\"Prefix\":\"_probe/\"" | wc -l'
summary
