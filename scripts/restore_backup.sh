#!/usr/bin/env bash
# =============================================================================
# SIES — restore a backup. The other half of auto_backup.sh.
#
#   scripts/restore_backup.sh --dry-run                    # newest backup, verify only
#   scripts/restore_backup.sh --dry-run --file <dump>      # a specific one
#   scripts/restore_backup.sh --list                       # what is available
#   scripts/restore_backup.sh --file <dump> --confirm RESTORE-SIES-PRODUCTION
#
# AN UNTESTED RESTORE IS NOT A BACKUP.
#   --dry-run reads the archive, lists what it contains, checks the media
#   tarball alongside it, and changes NOTHING. Run it on a schedule. It is the
#   only thing that tells you the nightly job is producing files that actually
#   restore — see DEPLOY.md, "A backup you have never restored is not a backup".
#
# A REAL RESTORE IS DESTRUCTIVE.
#   It drops and recreates the database. Every fee, payment and mark entered
#   since the dump was taken is gone, permanently, with no undo. That is why it
#   needs --confirm with the exact token above: a token cannot be produced by
#   an accidental up-arrow, and it cannot be produced by a script that meant to
#   pass --dry-run.
#
# ORDER OF OPERATIONS for a real restore:
#   1. stop the application containers (so nothing writes mid-restore)
#   2. dump the CURRENT database first — you may want it back
#   3. drop, recreate, pg_restore
#   4. restore media if a matching tarball is present
#   5. migrate (the dump may predate a migration), then start everything
# =============================================================================
set -euo pipefail

DRY_RUN=0; LIST=0; FILE=""; CONFIRM=""; DO_MEDIA=1
CONFIRM_TOKEN="RESTORE-SIES-PRODUCTION"

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)  DRY_RUN=1; shift ;;
    --list)     LIST=1; shift ;;
    --file)     FILE="$2"; shift 2 ;;
    --confirm)  CONFIRM="$2"; shift 2 ;;
    --no-media) DO_MEDIA=0; shift ;;
    -h|--help)  sed -n '2,29p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1  (try --help)" >&2; exit 1 ;;
  esac
done

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
ok()   { printf '  %b✔%b  %s\n' "$GREEN"  "$NC" "$1"; }
info() { printf '  %b→%b  %s\n' "$CYAN"   "$NC" "$1"; }
warn() { printf '  %b⚠%b  %s\n' "$YELLOW" "$NC" "$1"; }
die()  { printf '\n  %b✘ ERROR:%b %s\n' "$RED" "$NC" "$1" >&2; exit 1; }

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname -- "$SCRIPT_DIR")"
cd -- "$PROJECT_ROOT" || die "cannot enter ${PROJECT_ROOT}"

COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE="${ENV_FILE:-$PROJECT_ROOT/.env.production}"
DB_CONTAINER="${DB_CONTAINER:-sies-db}"
BACKEND_CONTAINER="${BACKEND_CONTAINER:-sies-backend}"
compose() { docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"; }

envget() { grep -E "^$1=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"'"'" ; }
[ -f "$ENV_FILE" ] || die "$ENV_FILE not found"

DB_NAME=$(envget DB_NAME); DB_NAME="${DB_NAME:-sies}"
DB_USER=$(envget DB_USER); DB_USER="${DB_USER:-sies}"
BACKUP_DIR=$(envget BACKUP_DIR); BACKUP_DIR="${BACKUP_DIR:-$PROJECT_ROOT/backups}"

# ── --list ───────────────────────────────────────────────────────────────────
if [ "$LIST" = 1 ]; then
  printf '%bAvailable backups in %s%b\n\n' "$BOLD" "$BACKUP_DIR" "$NC"
  find "$BACKUP_DIR" -name '*.dump' -type f -printf '%T@ %TY-%Tm-%Td %TH:%TM  %10s  %p\n' \
    | sort -rn | cut -d' ' -f2- | sed 's/^/  /'
  exit 0
fi

# ── Pick a file ──────────────────────────────────────────────────────────────
if [ -z "$FILE" ]; then
  FILE=$(find "$BACKUP_DIR" -name '*_db_*.dump' -type f -printf '%T@ %p\n' \
           | sort -rn | head -1 | cut -d' ' -f2-)
  [ -n "$FILE" ] || die "no backups found under ${BACKUP_DIR} (try --list)"
  info "newest backup selected automatically"
fi
[ -f "$FILE" ] || die "no such file: ${FILE}"

printf '%bBackup:%b %s  (%s, %s)\n' "$BOLD" "$NC" "$FILE" \
  "$(du -h "$FILE" | cut -f1)" "$(date -r "$FILE" '+%Y-%m-%d %H:%M')"

# The media tarball that belongs to this dump, matched on the timestamp in the
# filename. A database restored without its media leaves every student record
# pointing at a photo that is not there.
MEDIA_FILE=""
if [ "$DO_MEDIA" = 1 ]; then
  CANDIDATE="${FILE//_db_/_media_}"
  CANDIDATE="${CANDIDATE%.dump}.tar.gz"
  if [ -f "$CANDIDATE" ]; then
    MEDIA_FILE="$CANDIDATE"
    printf '%bMedia: %b %s  (%s)\n' "$BOLD" "$NC" "$MEDIA_FILE" "$(du -h "$MEDIA_FILE" | cut -f1)"
  else
    warn "no matching media archive for this dump — media will NOT be restored"
  fi
fi

docker ps --format '{{.Names}}' | grep -qx "$DB_CONTAINER" \
  || die "${DB_CONTAINER} is not running; start it first: docker compose -f ${COMPOSE_FILE} --env-file ${ENV_FILE} up -d ${DB_CONTAINER}"

# ── Verify the archive ───────────────────────────────────────────────────────
# pg_restore --list parses the whole archive header and table of contents. A
# truncated or corrupted dump fails here, which is the entire point of the
# dry run.
printf '\n%bVerifying the archive…%b\n' "$BOLD" "$NC"
if ! docker exec -i "$DB_CONTAINER" pg_restore --list /dev/stdin < "$FILE" > /tmp/sies_restore_toc.$$ 2>/dev/null; then
  rm -f "/tmp/sies_restore_toc.$$"
  die "this file is NOT a readable pg_restore archive. It will not restore. Take a fresh backup and investigate."
fi
TABLES=$(grep -c 'TABLE DATA' "/tmp/sies_restore_toc.$$" || true)
ok "archive is readable — ${TABLES} table(s) with data"
info "largest entries:"
grep 'TABLE DATA' "/tmp/sies_restore_toc.$$" | awk '{print $NF}' | head -10 | sed 's/^/        /'
rm -f "/tmp/sies_restore_toc.$$"

if [ -n "$MEDIA_FILE" ]; then
  tar -tzf "$MEDIA_FILE" >/dev/null 2>&1 \
    && ok "media archive is readable ($(tar -tzf "$MEDIA_FILE" | wc -l) entries)" \
    || die "the media archive does not read back — it is corrupt"
fi

# Version skew, from the other direction. A dump taken by a NEWER pg_dump than
# this server can contain statements this server rejects — pg_dump 17 emits
# `SET transaction_timeout = 0;`, which PostgreSQL 16 refuses. The dump is
# written happily and fails only here, on the day it is needed.
#
# For a CUSTOM-FORMAT dump (what auto_backup.sh writes, -Fc) pg_restore
# regenerates the statements for the target server, so the problem does not
# arise — that is one of the reasons the format was chosen.
#
# For a PLAIN-SQL dump, restored below with psql, there is no such translation,
# so the offending line is stripped on the way in. DO NOT DELETE THAT sed: it
# looks like cruft and it is the difference between a restore and an outage.
ARCHIVE_VER=$(docker exec -i "$DB_CONTAINER" pg_restore --list /dev/stdin < "$FILE" 2>/dev/null \
  | grep -oE 'Dumped by pg_dump version: [0-9]+' | grep -oE '[0-9]+$' | head -1 || true)
SERVER_MAJOR=$(docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d postgres -tAc 'SHOW server_version;' 2>/dev/null \
  | grep -oE '[0-9]+' | head -1)
if [ -n "$ARCHIVE_VER" ] && [ -n "$SERVER_MAJOR" ] && [ "$ARCHIVE_VER" -gt "$SERVER_MAJOR" ]; then
  warn "this dump was written by pg_dump ${ARCHIVE_VER} but the server is ${SERVER_MAJOR}."
  warn "  pg_restore will translate most of it, but a restore across a major"
  warn "  version boundary is not guaranteed. Restore onto a ${ARCHIVE_VER} server if you can."
fi

if [ "$DRY_RUN" = 1 ]; then
  printf '\n  %b✔ DRY RUN — the backup verifies. Nothing was changed.%b\n' "$GREEN" "$NC"
  printf '  To restore it for real:\n'
  printf '    %s --file %s --confirm %s\n' "$0" "$FILE" "$CONFIRM_TOKEN"
  exit 0
fi

# ── The point of no return ───────────────────────────────────────────────────
if [ "$CONFIRM" != "$CONFIRM_TOKEN" ]; then
  printf '\n'
  printf '  %bThis will DROP the %s database and replace it with the backup above.%b\n' "$RED" "$DB_NAME" "$NC"
  printf '  Everything entered since %s is lost permanently.\n' "$(date -r "$FILE" '+%Y-%m-%d %H:%M')"
  printf '\n  Re-run with:  --confirm %s\n' "$CONFIRM_TOKEN"
  exit 1
fi

printf '\n%b── RESTORING ─────────────────────────────────────────%b\n' "$BOLD" "$NC"

# 1. Stop everything that writes. Postgres stays up — it is what we restore
#    into. Leaving the workers running would have Celery writing rows into a
#    database that is being dropped underneath it.
info "stopping application containers…"
compose stop sies-backend sies-celery-worker sies-celery-beat sies-admin >/dev/null 2>&1 || true
ok "application stopped (Postgres still running)"

# 2. Dump what is there NOW. The most common regret in a restore is discovering
#    that the current data was not as worthless as it looked five minutes ago.
SAFETY="${BACKUP_DIR}/pre_restore_$(date +%Y%m%d_%H%M%S).dump"
info "dumping the CURRENT database to ${SAFETY} first…"
if docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" -Fc --no-owner "$DB_NAME" > "$SAFETY" 2>/dev/null; then
  chmod 600 "$SAFETY"
  ok "current state saved ($(du -h "$SAFETY" | cut -f1))"
else
  rm -f "$SAFETY"
  warn "could not dump the current database (does it exist?) — continuing"
fi

# 3. Drop and recreate. --clean --if-exists on pg_restore leaves orphaned
#    objects behind when the dump does not know about them; a fresh database is
#    the only way to be certain the result matches the backup exactly.
info "recreating the database…"
# Terminate other sessions first, or DROP DATABASE fails with "is being
# accessed by other users" — Django's persistent connections outlive the
# container stop by up to DB_CONN_MAX_AGE.
docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d postgres -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${DB_NAME}' AND pid <> pg_backend_pid();" >/dev/null
docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d postgres -c "DROP DATABASE IF EXISTS \"${DB_NAME}\";" >/dev/null
docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d postgres -c "CREATE DATABASE \"${DB_NAME}\" OWNER \"${DB_USER}\";" >/dev/null
ok "empty database created"

info "restoring…"
case "$FILE" in
  *.sql|*.sql.gz)
    # Plain SQL. See the version-skew note above: the sed strips
    # `SET transaction_timeout = 0;`, which pg_dump 17 emits and PostgreSQL 16
    # rejects. Without it the restore dies on line 12 of a 400 MB file.
    # DO NOT REMOVE — it is load-bearing, not cruft.
    if [ "${FILE##*.}" = gz ]; then CAT=zcat; else CAT=cat; fi
    if ! $CAT "$FILE" | sed '/^SET transaction_timeout = 0;$/d' \
         | docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 >/dev/null; then
      die "restore FAILED. The database is now EMPTY. Your previous data is in ${SAFETY}"
    fi
    ;;
  *)
    # Custom format. pg_restore regenerates statements for this server, so no
    # stripping is needed or possible.
    # --no-owner --no-privileges: the dump's role names need not exist here,
    # and on a rebuilt server they often do not.
    if ! docker exec -i "$DB_CONTAINER" pg_restore -U "$DB_USER" -d "$DB_NAME" \
           --no-owner --no-privileges --exit-on-error /dev/stdin < "$FILE"; then
      die "restore FAILED. The database is now EMPTY. Your previous data is in ${SAFETY}"
    fi
    ;;
esac
ok "database restored"

# 4. Media. Restored into a running backend container because that is what has
#    the volume mounted. --strip-components is deliberately absent: the archive
#    contains `media/...` and is unpacked at /app, which puts it back exactly
#    where it came from.
if [ -n "$MEDIA_FILE" ]; then
  info "restoring media…"
  compose up -d --no-deps "$BACKEND_CONTAINER" >/dev/null
  sleep 5
  if docker exec -i "$BACKEND_CONTAINER" tar -xzf - -C /app < "$MEDIA_FILE"; then
    ok "media restored"
  else
    warn "media restore failed — the database is restored, files are not"
  fi
fi

# 5. The dump may predate a migration that the deployed code needs. Running it
#    now means the stack comes up against a schema its code understands.
info "applying migrations…"
compose up -d >/dev/null
sleep 10
if compose exec -T "$BACKEND_CONTAINER" python manage.py migrate --noinput; then
  ok "migrations applied"
else
  warn "migrate failed — the data is restored but the schema may lag the code"
fi

printf '\n  %b✔ Restore complete.%b\n' "$GREEN" "$NC"
printf '    restored from  %s\n' "$FILE"
printf '    previous state %s   (delete it once you are satisfied)\n' "${SAFETY:-none}"
printf '\n  Verify before telling anyone it is done:\n'
printf '    ./scripts/health_check.sh --prod\n'
printf '    check the most recent fee payment in the dashboard against what you expect\n'
