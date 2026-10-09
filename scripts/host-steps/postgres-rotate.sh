#!/usr/bin/env bash
# Phase 4 (board F2, the operator's condition 2026-10-09): change the password of Mercury's
# records-database role ON THE SERVER, the first half of a rotation. The second half is
# Mercury's: Settings › Installation › Records database › Replace…, the same new password, then
# Test. Between the two Mercury holds the old password and cannot reach its records. The
# operator's, on the app host, from the checkout:
#     bash <checkout>/scripts/host-steps/postgres-rotate.sh
#
# The new password is PROMPTED for (input hidden), never printed and never an argument. What
# reaches the server is not the password: a SCRAM-SHA-256 verifier computed here, so the
# password is in neither the server's statement log nor any process's command line. The
# root-only env file's copy (host step 6a's MERCURY_DB_PASSWORD) is replaced too, so the kept
# copy is the current credential.
. "$(dirname "$0")/lib.sh"

DIR=/opt/mercury-postgres
ENV_FILE=$DIR/postgres.env
# The interpreter flask-app runs (section 8.1 of the Phase 4 document): the checks sign in with
# the driver Mercury itself uses.
APP_PY=$(systemctl show -p ExecStart --value flask-app.service | sed -n 's/.*path=\([^ ;]*\).*/\1/p')
export DIR ENV_FILE APP_PY

plan "run as the operator's own user, not root" \
     "docker answers" \
     "mercury-postgres is healthy" \
     "host step 6a's env file is there" \
     "the app's interpreter is read" \
     "the password is letters, digits and . _ ~ - only, 24 characters or more" \
     "the verifier is SCRAM-SHA-256" \
     "the new password signs in as mercury on 127.0.0.1:5433" \
     "a wrong password is refused on 127.0.0.1:5433" \
     "the env file holds the new password"

not_root
check "docker answers" rc0 "" 'docker info >/dev/null'
check "mercury-postgres is healthy" eq "healthy" \
    'docker inspect --format "{{.State.Health.Status}}" mercury-postgres'
check "host step 6a's env file is there" rc0 "" 'sudo test -f "$ENV_FILE"'
check "the app's interpreter is read" re '^/.+python' 'echo "$APP_PY"'

echo "The NEW password for the role mercury. Generate one in another terminal, for example:"
echo "    openssl rand -base64 33 | tr -d '/+='"
read -r -s -p "New password (hidden): " PW; echo
read -r -s -p "The same again: " AGAIN; echo
if [ "$PW" != "$AGAIN" ]; then
    echo "The two entries differ; nothing was changed."
    _stop "the password is letters, digits and . _ ~ - only, 24 characters or more"
fi
unset AGAIN
REDACT=$PW
export PW
check "the password is letters, digits and . _ ~ - only, 24 characters or more" eq "ok" \
    '[[ "$PW" =~ ^[A-Za-z0-9._~-]{24,}$ ]] && echo ok || echo "not ok (length ${#PW})"'

# RFC 7677's verifier, as PostgreSQL stores it: 4096 iterations (its default), a fresh 16-byte
# salt. The password reaches this process on standard input only.
SCRAM='import base64, hashlib, hmac, os, sys
pw = sys.stdin.read().encode()
salt, it = os.urandom(16), 4096
salted = hashlib.pbkdf2_hmac("sha256", pw, salt, it)
client = hmac.new(salted, b"Client Key", "sha256").digest()
b64 = lambda x: base64.b64encode(x).decode()
print("SCRAM-SHA-256$%d:%s$%s:%s" % (it, b64(salt), b64(hashlib.sha256(client).digest()),
                                     b64(hmac.new(salted, b"Server Key", "sha256").digest())))'
VERIFIER=$(printf '%s' "$PW" | python3 -c "$SCRAM")
export VERIFIER
check "the verifier is SCRAM-SHA-256" re '^SCRAM-SHA-256[$]4096:[A-Za-z0-9+/=]+\$[A-Za-z0-9+/=]+:[A-Za-z0-9+/=]+$' \
    'echo "$VERIFIER"'

step "set the role's password on the server (its verifier, on psql's standard input)" \
    'printf "ALTER ROLE mercury PASSWORD '"'"'%s'"'"';\n" "$VERIFIER" \
     | docker exec -i mercury-postgres psql -q -v ON_ERROR_STOP=1 -U postgres -d postgres'
# The superuser's line kept, Mercury's replaced; written whole, root-only, by name.
step "keep the env file's copy current" \
    'kept=$(sudo grep -v "^MERCURY_DB_PASSWORD=" "$ENV_FILE") \
     && printf "%s\nMERCURY_DB_PASSWORD=%s\n" "$kept" "$PW" | sudo install -m 0600 /dev/stdin "$ENV_FILE"'

check "the new password signs in as mercury on 127.0.0.1:5433" eq "mercury" \
    '"$APP_PY" -c "
import os, psycopg
with psycopg.connect(host=\"127.0.0.1\", port=5433, dbname=\"mercury\", user=\"mercury\",
                     password=os.environ[\"PW\"], connect_timeout=10) as c:
    print(c.execute(\"select current_user\").fetchone()[0])"'
check "a wrong password is refused on 127.0.0.1:5433" has "password authentication failed" \
    '"$APP_PY" -c "
import os, psycopg
try:
    psycopg.connect(host=\"127.0.0.1\", port=5433, dbname=\"mercury\", user=\"mercury\",
                    password=\"not-\" + os.environ[\"PW\"], connect_timeout=10).close()
    print(\"signed in with a wrong password\")
except psycopg.OperationalError as exc:
    print(exc)"'
check "the env file holds the new password" rc0 "" \
    'printf "MERCURY_DB_PASSWORD=%s\n" "$PW" | sudo grep -qxF -f - "$ENV_FILE"'
echo "Now the second half, in Mercury: Settings › Installation › Records database › Replace…,"
echo "the same new password, then Test. Until then Mercury holds the old password and cannot"
echo "reach its records."
summary
