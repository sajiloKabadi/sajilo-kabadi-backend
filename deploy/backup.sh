#!/usr/bin/env bash
# Dump the database to /opt/sajilokabadi/backups and keep 14 days.
# Cron (daily 02:30; the server runs on Asia/Kathmandu time):
#   30 2 * * * /opt/sajilokabadi/backup.sh >> /opt/sajilokabadi/backups/backup.log 2>&1
#
# Restore a dump (stops the API while restoring):
#   ./compose.sh stop api
#   ./compose.sh exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' < backups/<file>.dump
#   ./compose.sh start api
set -euo pipefail
cd "$(dirname "$0")"

KEEP_DAYS=14
mkdir -p backups
chmod 700 backups
FILE="backups/sajilokabadi-$(date -u +%Y%m%d-%H%M%S).dump"

# Credentials are read inside the container from its own environment, so
# they never appear on the command line or in this script.
docker exec sajilokabadi-postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' > "$FILE.partial"
mv "$FILE.partial" "$FILE"
chmod 600 "$FILE"

find backups -name 'sajilokabadi-*.dump' -mtime +"$KEEP_DAYS" -delete
echo "$(date -u +%FT%TZ) backup ok: $FILE ($(du -h "$FILE" | cut -f1))"
