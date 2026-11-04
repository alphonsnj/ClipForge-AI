#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || ! -f "$1" ]]; then
  echo "Usage: $0 /path/to/clipforge-backup.dump" >&2
  exit 2
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
archive="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
restore_db="clipforge_restore_check_$$"
restore_created=0

drop_restore_db() {
  [[ "$restore_created" == 1 ]] || return 0
  docker compose exec -T postgres sh -ec \
    'PGPASSWORD="$POSTGRES_PASSWORD" dropdb --if-exists --username "$POSTGRES_USER" "$1"' \
    sh "$restore_db" >/dev/null
}
trap drop_restore_db EXIT INT TERM

docker compose exec -T postgres pg_restore --list < "$archive" >/dev/null
docker compose exec -T postgres sh -ec \
  'PGPASSWORD="$POSTGRES_PASSWORD" createdb --username "$POSTGRES_USER" "$1"' \
  sh "$restore_db"
restore_created=1
docker compose exec -T postgres sh -ec \
  'pg_restore --username "$POSTGRES_USER" --exit-on-error --no-owner --no-acl --dbname "$1"' \
  sh "$restore_db" < "$archive"

echo "Restored database migration revision:"
docker compose exec -T postgres sh -ec \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql --no-psqlrc --tuples-only --no-align --username "$POSTGRES_USER" --dbname "$1" --command "SELECT version_num FROM alembic_version"' \
  sh "$restore_db"
echo "Restore check passed; removing disposable database $restore_db."
