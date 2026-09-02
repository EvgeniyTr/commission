#!/usr/bin/env bash
# Restores a pg_dump custom-format backup (created by db_backup.sh) into a
# fresh database on this machine's 'db' container.
#
# Usage:
#   ./scripts/db_restore.sh <dump_file> [db_name]
#
# Refuses to overwrite an existing database - drop it yourself first if you
# really want to replace it:
#   docker compose exec db dropdb -U odoo <db_name>
set -euo pipefail
cd "$(dirname "$0")/.."

DUMP_FILE="${1:?Usage: db_restore.sh <dump_file> [db_name]}"
DB_NAME="${2:-${ODOO_DB:-commission_test}}"

if [ ! -f "$DUMP_FILE" ]; then
    echo "File not found: $DUMP_FILE"
    exit 1
fi

docker compose up -d db
echo "Waiting for postgres..."
until docker compose exec -T db pg_isready -U odoo >/dev/null 2>&1; do sleep 1; done

# -e PGDATABASE=postgres: the 'odoo' role has no same-named database, so
# psql/createdb need an explicit maintenance database to connect to first.
EXISTS=$(docker compose exec -T -e PGDATABASE=postgres db psql -U odoo -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'")
if [ "$EXISTS" = "1" ]; then
    echo "Database '$DB_NAME' already exists - refusing to overwrite it."
    echo "Drop it first if you really want to replace it:"
    echo "  docker compose exec -e PGDATABASE=postgres db dropdb -U odoo $DB_NAME"
    exit 1
fi

echo "Creating database '$DB_NAME'..."
docker compose exec -T -e PGDATABASE=postgres db createdb -U odoo "$DB_NAME"

echo "Restoring '$DUMP_FILE' into '$DB_NAME'..."
docker compose exec -T db pg_restore -U odoo -d "$DB_NAME" --no-owner --no-privileges < "$DUMP_FILE"

echo "Done. Start Odoo against it with:"
echo "  ODOO_DB=$DB_NAME docker compose up -d odoo"
