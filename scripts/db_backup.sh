#!/usr/bin/env bash
# Dumps the Odoo database (default: commission_test) to a single portable
# file using pg_dump's custom format (compressed, restore-tool-agnostic
# about Postgres minor version / OS / architecture).
#
# Usage:
#   ./scripts/db_backup.sh [db_name] [output_file]
#
# Defaults: db_name=commission_test, output_file=./backup/<db_name>-<date>.dump
set -euo pipefail
cd "$(dirname "$0")/.."

DB_NAME="${1:-${ODOO_DB:-commission_test}}"
OUT_DIR="./backup"
mkdir -p "$OUT_DIR"
OUT_FILE="${2:-$OUT_DIR/${DB_NAME}-$(date +%Y%m%d-%H%M%S).dump}"

echo "Dumping database '$DB_NAME' from the running 'db' container..."
docker compose exec -T db pg_dump -U odoo -Fc "$DB_NAME" > "$OUT_FILE"

echo "Done: $OUT_FILE ($(du -h "$OUT_FILE" | cut -f1))"
echo "Copy this file to the target machine, then run:"
echo "  ./scripts/db_restore.sh \"$(basename "$OUT_FILE")\" [db_name]"
