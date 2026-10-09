#!/usr/bin/env bash
# Phase 4, host step 6a (docs/NSOT_PHASE4_RECORDS_POSTGRES.md section 6): Mercury's records
# database in its own container on 127.0.0.1:5433 (P4-1, PG-1), and the PostgreSQL driver for
# the app's interpreter as the host's apt package (python3-psycopg, as boto3 was). The
# operator's, on the NMAS host, from the checkout:
#     bash <checkout>/scripts/host-steps/postgres-6a.sh
#
# Mercury's database password is PROMPTED for (input hidden), never printed and never an
# argument; keep it for Settings, where the records database's settings ask for it. The
# superuser's password is generated here into the root-only env file and never shown. Safe to
# run again: an env file already there is kept (the passwords only take effect on an empty
# volume), and the checks prove the password you enter is Mercury's.
. "$(dirname "$0")/lib.sh"

DIR=/opt/mercury-postgres
COMPOSE=$DIR/docker-compose.yml
PSYCOPG=3.1.17-2

plan "run as the operator's own user, not root" \
     "docker answers" \
     "NetBox's database container is running" \
     "the password is letters, digits and . _ ~ - only, 24 characters or more" \
     "mercury-postgres is healthy" \
     "its server is PostgreSQL 18" \
     "the role mercury owns the database mercury" \
     "mercury is not a superuser" \
     "5433 is published on 127.0.0.1 only" \
     "NetBox's database container was not restarted" \
     "installing python3-psycopg changes no other installed package" \
     "the app's interpreter imports psycopg $PSYCOPG" \
     "psycopg signs in as mercury on 127.0.0.1:5433 with your password" \
     "a wrong password is refused on 127.0.0.1:5433"

not_root
check "docker answers" rc0 "" 'docker info >/dev/null'
check "NetBox's database container is running" eq "running" \
    'docker inspect --format "{{.State.Status}}" netbox-docker-postgres-1'
NETBOX_STARTED=$(docker inspect --format '{{.State.StartedAt}}' netbox-docker-postgres-1)

echo "Mercury's database password. Generate one in another terminal, for example:"
echo "    openssl rand -base64 33 | tr -d '/+='"
read -r -s -p "Password for the role mercury (hidden): " PW; echo
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

# Rendered into a fresh folder, then installed by name.
export CHECKOUT DIR COMPOSE
step "install the compose file and the init script, by name" \
    'd=$(mktemp -d) && cp "$CHECKOUT/deploy/postgres/docker-compose.yml" "$d/" \
     && cp "$CHECKOUT/deploy/postgres/initdb/10-mercury.sh" "$d/" \
     && sudo install -d -m 0750 "$DIR" "$DIR/initdb" \
     && sudo install -m 0640 "$d/docker-compose.yml" "$COMPOSE" \
     && sudo install -m 0644 "$d/10-mercury.sh" "$DIR/initdb/10-mercury.sh"'

if sudo test -f "$DIR/postgres.env"; then
    echo "== the env file exists already: kept (its passwords took effect when the volume was"
    echo "   first made); the checks below prove the password you entered is Mercury's."
else
    echo "== STEP: write the root-only env file (the superuser's password generated, never shown)"
    if ! printf 'POSTGRES_PASSWORD=%s\nMERCURY_DB_PASSWORD=%s\n' "$(openssl rand -hex 24)" "$PW" \
            | sudo install -m 0600 /dev/stdin "$DIR/postgres.env"; then
        echo "STEP FAILED: write the env file"
        _stop "mercury-postgres is healthy"
    fi
fi

step "start mercury-postgres" 'sudo docker compose -f "$COMPOSE" up -d'
# Not measured: a first start initialises an empty cluster; the health check's own budget is
# 6 tries 10 s apart, so this waits up to 90 s and says how long it took.
echo "== waiting for the health check (up to 90 s)"
for i in $(seq 1 45); do
    state=$(docker inspect --format '{{.State.Health.Status}}' mercury-postgres 2>/dev/null)
    [ "$state" = healthy ] && { echo "   healthy after about $((i * 2)) s"; break; }
    sleep 2
done
check "mercury-postgres is healthy" eq "healthy" \
    'docker inspect --format "{{.State.Health.Status}}" mercury-postgres'
check "its server is PostgreSQL 18" re '^18\.' \
    'docker exec mercury-postgres psql -U postgres -tAc "show server_version"'
check "the role mercury owns the database mercury" eq "mercury" \
    'docker exec mercury-postgres psql -U postgres -tAc "select pg_get_userbyid(datdba) from pg_database where datname = '"'mercury'"'"'
check "mercury is not a superuser" eq "f" \
    'docker exec mercury-postgres psql -U postgres -tAc "select rolsuper from pg_roles where rolname = '"'mercury'"'"'
check "5433 is published on 127.0.0.1 only" eq "127.0.0.1:5433" \
    'ss -ltnH "sport = :5433" | tr -s " " | cut -d " " -f 4 | sort -u | paste -sd " "'
export NETBOX_STARTED
check "NetBox's database container was not restarted" eq "$NETBOX_STARTED" \
    'docker inspect --format "{{.State.StartedAt}}" netbox-docker-postgres-1'

check "installing python3-psycopg changes no other installed package" eq "0 upgraded 0 removed" \
    'apt-get -s install "python3-psycopg='"$PSYCOPG"'" | sed -nE "s/^([0-9]+) upgraded, [0-9]+ newly installed, ([0-9]+) to remove.*/\1 upgraded \2 removed/p"'
step "install python3-psycopg $PSYCOPG" 'sudo apt-get install -y "python3-psycopg='"$PSYCOPG"'"'
check "the app's interpreter imports psycopg $PSYCOPG" eq "${PSYCOPG%-*}" \
    '/usr/bin/python3 -c "import psycopg; print(psycopg.__version__)"'
check "psycopg signs in as mercury on 127.0.0.1:5433 with your password" eq "mercury" \
    '/usr/bin/python3 -c "
import os, psycopg
with psycopg.connect(host=\"127.0.0.1\", port=5433, dbname=\"mercury\", user=\"mercury\",
                     password=os.environ[\"PW\"], connect_timeout=10) as c:
    print(c.execute(\"select current_user\").fetchone()[0])"'
# The image trusts connections from inside the container; through the published port it asks
# for the password (scram-sha-256), measured on a throwaway copy of this image 2026-10-09.
check "a wrong password is refused on 127.0.0.1:5433" has "password authentication failed" \
    '/usr/bin/python3 -c "
import os, psycopg
try:
    psycopg.connect(host=\"127.0.0.1\", port=5433, dbname=\"mercury\", user=\"mercury\",
                    password=\"not-\" + os.environ[\"PW\"], connect_timeout=10).close()
    print(\"signed in with a wrong password\")
except psycopg.OperationalError as exc:
    print(exc)"'
unset PW
echo "Next: the lock is regenerated from this host (read-only), and the records database's"
echo "settings arrive with the receipts store; enter Mercury's password there."
summary
