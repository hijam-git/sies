#!/usr/bin/env bash
# =============================================================================
# SIES — install the nightly backup cron.
#
#   scripts/setup_backup_cron.sh              # 02:30 nightly, plus a weekly verify
#   scripts/setup_backup_cron.sh --at 03:15   # a different hour
#   scripts/setup_backup_cron.sh --remove     # take it out again
#   scripts/setup_backup_cron.sh --show       # what is installed right now
#
# Installs into the CURRENT user's crontab — run it as the deploy user, the same
# one that owns the checkout, or the backup will run as somebody who cannot read
# the docker socket.
#
# Two entries go in:
#   1. auto_backup.sh nightly.
#   2. restore_backup.sh --dry-run weekly. A backup nobody has ever restored is
#      not a backup; this is what turns "the cron says OK" into evidence.
#      See DEPLOY.md, "A backup you have never restored is not a backup".
#
# IDEMPOTENT. Existing SIES entries are replaced, not appended — running this
# five times leaves exactly one schedule, not five backups a night.
# =============================================================================
set -euo pipefail

AT="02:30"; REMOVE=0; SHOW=0
while [ $# -gt 0 ]; do
  case "$1" in
    --at)     AT="$2"; shift 2 ;;
    --remove) REMOVE=1; shift ;;
    --show)   SHOW=1; shift ;;
    -h|--help) sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1  (try --help)" >&2; exit 1 ;;
  esac
done

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
ok()   { printf '  %b✔%b  %s\n' "$GREEN"  "$NC" "$1"; }
info() { printf '  %b→%b  %s\n' "$CYAN"   "$NC" "$1"; }
warn() { printf '  %b⚠%b  %s\n' "$YELLOW" "$NC" "$1"; }
die()  { printf '  %b✘%b  %s\n' "$RED"    "$NC" "$1" >&2; exit 1; }

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname -- "$SCRIPT_DIR")"
BACKUP_SCRIPT="$SCRIPT_DIR/auto_backup.sh"
RESTORE_SCRIPT="$SCRIPT_DIR/restore_backup.sh"
LOG_DIR="$PROJECT_ROOT/logs"
LOG_FILE="$LOG_DIR/backup_cron.log"

# The marker that makes this idempotent. Every line we own carries it, and the
# rebuild below removes exactly those lines and nothing else — so a hand-written
# cron entry sitting next to ours survives.
MARKER="# SIES-BACKUP"

command -v crontab >/dev/null 2>&1 \
  || die "crontab is not installed. Run scripts/bootstrap.sh as root first."

if [ "$SHOW" = 1 ]; then
  crontab -l 2>/dev/null | grep -F "$MARKER" -A0 || echo "  (no SIES cron entries)"
  exit 0
fi

# Read the existing crontab minus our lines. `crontab -l` exits 1 when there is
# no crontab at all, which is not an error here.
CURRENT=$(crontab -l 2>/dev/null | grep -vF "$MARKER" || true)

if [ "$REMOVE" = 1 ]; then
  printf '%s\n' "$CURRENT" | crontab -
  ok "SIES backup cron entries removed"
  warn "nothing is backing this system up now"
  exit 0
fi

[ -f "$BACKUP_SCRIPT" ] || die "$BACKUP_SCRIPT not found"
chmod +x "$BACKUP_SCRIPT" "$RESTORE_SCRIPT" 2>/dev/null || true
mkdir -p "$LOG_DIR"

case "$AT" in
  [0-9][0-9]:[0-9][0-9]) ;;
  *) die "--at wants HH:MM, got '${AT}'" ;;
esac
HOUR=${AT%%:*}; MIN=${AT##*:}
# Strip a leading zero: cron accepts 05 but arithmetic elsewhere does not, and
# "08" is an invalid octal literal in shell, which is a genuinely nasty way for
# this to fail.
HOUR=$((10#$HOUR)); MIN=$((10#$MIN))

# The dry-run verify goes on Sunday, an hour after the nightly dump, so it reads
# a backup that was written a few minutes earlier rather than one from last week.
VERIFY_HOUR=$(( (HOUR + 1) % 24 ))

NEW_LINES=$(cat <<CRON

${MARKER} nightly database + media backup
# Cron has almost no environment: no PATH beyond /usr/bin:/bin, and HOME may not
# be the one the SSH key for the off-box copy lives in. Both are set explicitly
# rather than relied upon.
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
${MIN} ${HOUR} * * * cd ${PROJECT_ROOT} && ${BACKUP_SCRIPT} --quiet >> ${LOG_FILE} 2>&1 ${MARKER}
${MIN} ${VERIFY_HOUR} * * 0 cd ${PROJECT_ROOT} && ${RESTORE_SCRIPT} --dry-run >> ${LOG_FILE} 2>&1 ${MARKER}
CRON
)

printf '%s\n%s\n' "$CURRENT" "$NEW_LINES" | crontab -

ok "cron installed"
info "backup   ${AT} every night"
info "verify   $(printf '%02d:%02d' "$VERIFY_HOUR" "$MIN") every Sunday (restore_backup.sh --dry-run)"
info "log      ${LOG_FILE}"

if systemctl is-active cron >/dev/null 2>&1 || systemctl is-active crond >/dev/null 2>&1; then
  ok "the cron daemon is running"
else
  # An entry in a scheduler that is not running is the exact shape of a silent
  # backup failure: everything looks configured and nothing ever fires.
  warn "the cron daemon is NOT running — these entries will never fire."
  warn "  fix as root:  sudo systemctl enable --now cron"
fi

printf '\n  Prove it works now, rather than finding out in three weeks:\n'
printf '    %s\n' "$BACKUP_SCRIPT"
printf '    %s --dry-run\n' "$RESTORE_SCRIPT"
