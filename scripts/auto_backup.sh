#!/usr/bin/env bash
# =============================================================================
# SIES — nightly backup: database + media, with retention and an off-box copy
# to rsync, to Cloudflare R2, or to both.
#
#   scripts/auto_backup.sh
#   scripts/auto_backup.sh --no-media     # database only (faster, incomplete)
#   scripts/auto_backup.sh --quiet        # only speak on failure (for cron)
#
# Installed by scripts/setup_backup_cron.sh. Restored by scripts/restore_backup.sh.
#
# WHY BOTH HALVES
#   A pg_dump alone is NOT a backup of this system. Student photos, guardian
#   documents and generated receipts live on the `media` volume, not in the
#   database, and a restore without them leaves every student record pointing at
#   a file that is not there.
#
# THIS SCRIPT FAILS LOUDLY.
#   Every step is checked, a non-zero exit is a real failure, and a run that
#   could not copy anything off this machine says so as an ERROR rather than
#   letting an unread success line imply the data is safe. A backup system that
#   fails quietly is worse than none: it removes the worry without removing the
#   risk.
#
# SAFE TO RE-RUN, and safe to run while the stack is live: pg_dump takes a
# consistent snapshot inside one transaction and blocks nothing.
# =============================================================================
set -euo pipefail

DO_MEDIA=1; QUIET=0
while [ $# -gt 0 ]; do
  case "$1" in
    --no-media) DO_MEDIA=0; shift ;;
    --quiet|-q) QUIET=1; shift ;;
    -h|--help)  sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1  (try --help)" >&2; exit 1 ;;
  esac
done

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname -- "$SCRIPT_DIR")"
cd -- "$PROJECT_ROOT" || { echo "cannot enter ${PROJECT_ROOT}" >&2; exit 1; }

ENV_FILE="${ENV_FILE:-$PROJECT_ROOT/.env.production}"
DB_CONTAINER="${DB_CONTAINER:-sies-db}"
BACKEND_CONTAINER="${BACKEND_CONTAINER:-sies-backend}"

# Read a variable out of the env file without sourcing it — sourcing would
# execute whatever is in there, and would also clobber this script's own
# variables with values that happen to share a name.
# A key that is ABSENT must yield an empty string, not kill the script.
#
# `grep` returns 1 when it matches nothing, `pipefail` promotes that to the
# pipeline's status, and `set -e` then exits — in auto_backup.sh that happened
# BEFORE the logging trap was installed, so a single missing optional variable
# produced a backup run that did nothing, wrote no log, and said nothing. A
# backup script that silently declines to run is worse than no backup script,
# because the cron entry still looks healthy.
#
# `|| true` is the whole fix: a missing key is a normal state, not an error.
envget() {
  grep -E "^$1=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"'"'" || true
}

[ -f "$ENV_FILE" ] || { echo "ERROR: $ENV_FILE not found" >&2; exit 1; }

DB_NAME=$(envget DB_NAME);   DB_NAME="${DB_NAME:-sies}"
DB_USER=$(envget DB_USER);   DB_USER="${DB_USER:-sies}"
BACKUP_DIR=$(envget BACKUP_DIR); BACKUP_DIR="${BACKUP_DIR:-$PROJECT_ROOT/backups}"
KEEP_DAILY=$(envget BACKUP_KEEP_DAILY);   KEEP_DAILY="${KEEP_DAILY:-14}"
KEEP_WEEKLY=$(envget BACKUP_KEEP_WEEKLY); KEEP_WEEKLY="${KEEP_WEEKLY:-8}"
REMOTE=$(envget BACKUP_REMOTE)
REMOTE_KEY=$(envget BACKUP_REMOTE_SSH_KEY)
# Cloudflare R2, the other off-box target. Either one counts as offsite;
# having both is better than choosing, because they fail differently — a
# dead SSH key and a rotated API token are not the same outage.
R2_BACKUP_BUCKET=$(envget R2_BACKUP_BUCKET)
SERVER_NAME=$(envget THIS_SERVER_NAME); SERVER_NAME="${SERVER_NAME:-sies}"

LOG_DIR="$PROJECT_ROOT/logs"
LOG_FILE="$LOG_DIR/backup.log"
STAMP=$(date +%Y%m%d_%H%M%S)
# ISO week number. One dump per week is promoted to the weekly set, which is
# what makes "restore to a month ago" possible without keeping 30 daily copies
# of the media volume.
ISOWEEK=$(date +%G-W%V)

mkdir -p "$BACKUP_DIR/daily" "$BACKUP_DIR/weekly" "$LOG_DIR"
# 0750 throughout: these files are the entire student and fee database in
# readable form. Anyone who can read this directory can read every record.
chmod 750 "$BACKUP_DIR" "$BACKUP_DIR/daily" "$BACKUP_DIR/weekly"

log() {
  local level="$1"; shift
  printf '[%s] [%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$level" "$*" >> "$LOG_FILE"
  if [ "$level" = ERROR ]; then
    printf '[ERROR] %s\n' "$*" >&2
  elif [ "$QUIET" = 0 ]; then
    printf '[%s] %s\n' "$level" "$*"
  fi
}

# Anything that exits non-zero from here lands in the log with its exit code,
# so a cron failure is explicable from the log alone rather than from an email
# nobody has configured.
trap 'rc=$?; [ $rc -ne 0 ] && log ERROR "=== backup run ended UNSUCCESSFULLY (exit $rc) ==="; exit $rc' EXIT

log INFO "=== backup started (${SERVER_NAME}) ==="

docker ps --format '{{.Names}}' | grep -qx "$DB_CONTAINER" \
  || { log ERROR "container ${DB_CONTAINER} is not running — nothing to back up"; exit 1; }

# Refuse to start a backup that cannot finish. A dump that runs out of disk
# leaves a truncated file that looks like a backup and restores as garbage.
FREE_MB=$(df -BM --output=avail "$BACKUP_DIR" | tail -1 | tr -dc '0-9')
if [ "${FREE_MB:-0}" -lt 1024 ]; then
  log ERROR "only ${FREE_MB} MB free in ${BACKUP_DIR} — refusing to write a truncated dump"
  exit 1
fi

# ── pg_dump / server version skew ────────────────────────────────────────────
# This check exists because the failure it catches is invisible until the worst
# possible day.
#
# pg_dump 17 writes `SET transaction_timeout = 0;` into the dump header. A
# PostgreSQL 16 server REJECTS that statement on restore. So a stack whose
# client is 17 and whose server is 16 produces backups that succeed every single
# night, log nothing, and cannot be restored — and you find out on the day you
# need one. (Awliaa's production image shipped exactly that combination:
# postgresql-client 17 against postgres:16-alpine.)
#
# We dump by exec-ing into the database container, so the client is the server's
# own and the majors match by construction. This verifies that rather than
# assuming it, because the day someone "simplifies" this to run pg_dump from the
# backend container or the host is the day the trap is re-armed.
#
# If you ever DO need a client outside the container, install postgresql-client
# pinned to the SERVER major (16), never the distro default.
CLIENT_MAJOR=$(docker exec "$DB_CONTAINER" pg_dump --version 2>/dev/null \
  | grep -oE '[0-9]+' | head -1)
SERVER_MAJOR=$(docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc 'SHOW server_version;' 2>/dev/null \
  | grep -oE '[0-9]+' | head -1)
if [ -z "$CLIENT_MAJOR" ] || [ -z "$SERVER_MAJOR" ]; then
  log ERROR "could not determine pg_dump/server versions — refusing to write an unverifiable dump"
  exit 1
fi
if [ "$CLIENT_MAJOR" != "$SERVER_MAJOR" ]; then
  log ERROR "pg_dump is ${CLIENT_MAJOR}, the server is ${SERVER_MAJOR}."
  log ERROR "  A newer client writes statements an older server refuses on restore"
  log ERROR "  (pg_dump 17 emits 'SET transaction_timeout = 0;', which PG16 rejects)."
  log ERROR "  The dump would appear to succeed and would NOT restore. Aborting."
  log ERROR "  Fix: dump with the server's own client, or pin postgresql-client to ${SERVER_MAJOR}."
  exit 1
fi
log INFO "pg_dump ${CLIENT_MAJOR} against server ${SERVER_MAJOR} — versions match"

# ── Database ─────────────────────────────────────────────────────────────────
# -Fc (custom format) rather than plain SQL: it is compressed already, and
# pg_restore can read it selectively — one table, or schema without data —
# which is exactly what you want at 2 a.m. when only one table is wrong.
DUMP="$BACKUP_DIR/daily/${SERVER_NAME}_db_${STAMP}.dump"
log INFO "dumping ${DB_NAME}…"
if ! docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" -Fc --no-owner "$DB_NAME" > "$DUMP"; then
  rm -f "$DUMP"
  log ERROR "pg_dump failed — no database backup was taken"
  exit 1
fi
chmod 600 "$DUMP"

# A pg_dump that fails partway can still exit 0 if the failure was on the write
# side. Reading the archive's table of contents proves the file is a complete,
# parseable archive — the cheapest real verification available.
#
# The archive is copied INTO the container and read from a real path. It cannot
# be piped: a custom-format archive is read by seeking to its table of contents,
# and `pg_restore --list /dev/stdin` therefore fails on every dump, however
# healthy. That turned this check into one that condemned good backups — the
# script renamed each one .corrupt and exited 1, so the nightly job looked
# broken while the dumps beside it were perfectly restorable.
VERIFY_PATH="/tmp/$(basename "$DUMP")"
if ! docker cp "$DUMP" "$DB_CONTAINER:$VERIFY_PATH" >/dev/null 2>&1; then
  log ERROR "could not copy the dump into ${DB_CONTAINER} to verify it"
  mv "$DUMP" "${DUMP}.unverified"
  exit 1
fi
if ! docker exec "$DB_CONTAINER" pg_restore --list "$VERIFY_PATH" >/dev/null 2>&1; then
  docker exec "$DB_CONTAINER" rm -f "$VERIFY_PATH" >/dev/null 2>&1 || true
  log ERROR "the dump is not a readable pg_restore archive — treating it as failed"
  mv "$DUMP" "${DUMP}.corrupt"
  exit 1
fi
docker exec "$DB_CONTAINER" rm -f "$VERIFY_PATH" >/dev/null 2>&1 || true
log INFO "database: $(basename "$DUMP") ($(du -h "$DUMP" | cut -f1)), archive verified"

# ── Media ────────────────────────────────────────────────────────────────────
MEDIA_TAR=""
if [ "$DO_MEDIA" = 0 ]; then
  log INFO "media skipped (--no-media) — this backup is NOT complete on its own"
elif ! docker ps --format '{{.Names}}' | grep -qx "$BACKEND_CONTAINER"; then
  log ERROR "container ${BACKEND_CONTAINER} is not running — media NOT backed up"
  log ERROR "  the database dump alone leaves every photo and document behind"
else
  MEDIA_TAR="$BACKUP_DIR/daily/${SERVER_NAME}_media_${STAMP}.tar.gz"
  log INFO "archiving media…"
  # Streamed out of the container, so it works whether media is a named volume,
  # a bind mount, or something else later. -C /app so paths in the archive are
  # relative and a restore cannot escape its target directory.
  if ! docker exec "$BACKEND_CONTAINER" tar -czf - -C /app media > "$MEDIA_TAR" 2>/dev/null; then
    rm -f "$MEDIA_TAR"
    log ERROR "media archive failed"
    exit 1
  fi
  chmod 600 "$MEDIA_TAR"
  if ! tar -tzf "$MEDIA_TAR" >/dev/null 2>&1; then
    log ERROR "the media archive does not read back — treating it as failed"
    mv "$MEDIA_TAR" "${MEDIA_TAR}.corrupt"
    exit 1
  fi
  log INFO "media: $(basename "$MEDIA_TAR") ($(du -h "$MEDIA_TAR" | cut -f1)), archive verified"
fi

# ── Weekly promotion ─────────────────────────────────────────────────────────
# Copy, not move: today's dump stays in the daily set as well. A hard link would
# be smaller, but the two sets are pruned independently and a link means pruning
# one does not actually free anything — which is confusing precisely when the
# disk is filling.
if ! ls "$BACKUP_DIR/weekly/${SERVER_NAME}_db_${ISOWEEK}"* >/dev/null 2>&1; then
  cp -p "$DUMP" "$BACKUP_DIR/weekly/${SERVER_NAME}_db_${ISOWEEK}_${STAMP}.dump"
  [ -n "$MEDIA_TAR" ] && cp -p "$MEDIA_TAR" "$BACKUP_DIR/weekly/${SERVER_NAME}_media_${ISOWEEK}_${STAMP}.tar.gz"
  log INFO "promoted this run to the weekly set (${ISOWEEK})"
fi

# ── Off-box copy ─────────────────────────────────────────────────────────────
# A backup on the same disk as the database survives a bad migration but not a
# dead server, and the dead server is the case backups exist for.
OFFSITE=FAILED

# ── Cloudflare R2 ────────────────────────────────────────────────────────────
# Runs inside the backend container, which already holds the R2 credentials it
# uses for uploads — nothing extra to configure per host or per cron user, which
# is the way an off-box copy usually dies (see the rsync note below about HOME).
#
# The dump lives on the host, so it is copied in rather than mounted: a mount
# would put the whole backup directory inside a running application container
# for the sake of one file a night.
if [ -n "$R2_BACKUP_BUCKET" ]; then
  log INFO "copying to R2 bucket ${R2_BACKUP_BUCKET}…"
  R2_OK=1
  for f in "$DUMP" ${MEDIA_TAR:+"$MEDIA_TAR"}; do
    if docker cp "$f" "${BACKEND_CONTAINER}:/tmp/$(basename "$f")" 2>>"$LOG_FILE" \
       && docker exec "$BACKEND_CONTAINER" python manage.py backup_to_r2 \
            --file "/tmp/$(basename "$f")" >>"$LOG_FILE" 2>&1; then
      :
    else
      R2_OK=0
      log ERROR "R2 upload FAILED for $(basename "$f") — see $LOG_FILE"
    fi
    # Never leave a database dump inside the application container.
    docker exec "$BACKEND_CONTAINER" rm -f "/tmp/$(basename "$f")" 2>/dev/null || true
  done
  if [ "$R2_OK" = 1 ]; then
    OFFSITE=ok
    log INFO "R2 copy complete"
  fi
fi

if [ -z "$REMOTE" ]; then
  if [ "$OFFSITE" != ok ]; then
    # Deliberately an ERROR, not an info line. Local-only is a real gap, and the
    # nightly cron mail is the only place anyone will ever see it said.
    log ERROR "no off-box copy — tonight's backup exists only on this machine"
    log ERROR "  set BACKUP_REMOTE (rsync) or R2_BACKUP_BUCKET (Cloudflare R2) in .env.production."
  fi
else
  RSYNC_SSH="ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new"
  # cron's HOME is not the HOME the key was configured in, which is the single
  # most common way an off-box copy fails silently. Name the key explicitly.
  [ -n "$REMOTE_KEY" ] && RSYNC_SSH="$RSYNC_SSH -i $REMOTE_KEY"
  log INFO "copying to ${REMOTE}…"
  if rsync -a --partial --timeout=300 -e "$RSYNC_SSH" \
        "$DUMP" ${MEDIA_TAR:+"$MEDIA_TAR"} "$REMOTE/" 2>>"$LOG_FILE"; then
    OFFSITE=ok
    log INFO "off-box copy complete"
  else
    log ERROR "off-box copy FAILED — tonight's backup exists only on this machine"
    log ERROR "  the local copy is fine; see the rsync error above in $LOG_FILE"
  fi
fi

# ── Retention ────────────────────────────────────────────────────────────────
# Runs LAST, and only prunes by age when the off-box copy worked.
#
# The other order deletes dumps that never left this machine, and logs it as
# routine housekeeping — a week of failed copies ends with the old backups
# quietly gone and no line anywhere saying so.
prune() {  # dir pattern keep
  local dir="$1" pattern="$2" keep="$3" f n=0
  # -printf/sort by mtime rather than by filename: a clock change or a manual
  # copy would otherwise reorder them and prune the wrong end.
  while IFS= read -r f; do
    rm -f "$f"; n=$((n+1))
    log INFO "pruned $(basename "$f")"
  done < <(find "$dir" -maxdepth 1 -name "$pattern" -type f -printf '%T@ %p\n' \
             | sort -rn | tail -n +$((keep + 1)) | cut -d' ' -f2-)
  return 0
}

if [ "$OFFSITE" = ok ] || [ -z "$REMOTE" ]; then
  # With no remote configured at all, pruning still has to happen or the disk
  # fills — and a full disk takes Postgres down with it, which is worse than a
  # gap in backup history. With a remote configured that FAILED, we keep
  # everything: the local copies are all that exist.
  prune "$BACKUP_DIR/daily"  "${SERVER_NAME}_db_*.dump"       "$KEEP_DAILY"
  prune "$BACKUP_DIR/daily"  "${SERVER_NAME}_media_*.tar.gz"  "$KEEP_DAILY"
  prune "$BACKUP_DIR/weekly" "${SERVER_NAME}_db_*.dump"       "$KEEP_WEEKLY"
  prune "$BACKUP_DIR/weekly" "${SERVER_NAME}_media_*.tar.gz"  "$KEEP_WEEKLY"
else
  log INFO "keeping ALL local backups — the off-box copy failed, so these are the only copies"
fi

COUNT=$(find "$BACKUP_DIR" -name '*.dump' -o -name '*.tar.gz' | wc -l)
log INFO "${COUNT} file(s), $(du -sh "$BACKUP_DIR" | cut -f1) in ${BACKUP_DIR}"

if [ "$OFFSITE" = ok ]; then
  log INFO "=== backup complete — local copy taken, off-box copy sent ==="
  exit 0
fi

# Said as a failure, because it is one: a dump that exists only on the machine
# it came from does not survive that machine. Non-zero so cron notices.
log ERROR "=== backup taken LOCALLY ONLY — no off-box copy exists ==="
exit 1
