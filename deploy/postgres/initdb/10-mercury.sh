#!/bin/sh
# Mercury's own role and database in its records container (Phase 4, P4-1). The image's
# entrypoint runs this ONCE, on an empty volume, as the superuser; never again. The role owns
# its database and is not a superuser: dumps and the restore test run as the superuser, inside
# the container. The password arrives in the environment (the root-only env file) and reaches
# psql as a variable on its standard input, never on a command line.
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
     --set=pw="$MERCURY_DB_PASSWORD" <<'SQL'
CREATE ROLE mercury LOGIN PASSWORD :'pw';
CREATE DATABASE mercury OWNER mercury;
REVOKE ALL ON DATABASE mercury FROM PUBLIC;
SQL
