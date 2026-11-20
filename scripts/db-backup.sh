#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

backup_dir="${1:-$repo_root/backups}"
mkdir -p "$backup_dir"
chmod 700 "$backup_dir"
umask 077

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
archive="$backup_dir/clipforge-$timestamp-$$-$RANDOM.dump"
temporary="$archive.tmp"
trap 'python3 -c '\''import pathlib, sys; pathlib.Path(sys.argv[1]).unlink(missing_ok=True)'\'' "$temporary"' EXIT

docker compose exec -T postgres sh -ec \
  'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --format=custom --no-owner --no-acl' \
  > "$temporary"

test -s "$temporary"
docker compose exec -T postgres pg_restore --list < "$temporary" >/dev/null
mv "$temporary" "$archive"
trap - EXIT
printf 'Backup created: %s\n' "$archive"
