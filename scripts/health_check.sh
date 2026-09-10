#!/usr/bin/env bash
# =============================================================================
# SIES — is the system actually working?
#
#   scripts/health_check.sh            # dev stack  (docker-compose.dev.yml)
#   scripts/health_check.sh --prod     # production stack
#   scripts/health_check.sh --prod -q  # exit code only, for cron/monitoring
#
# Checks, in order of how badly each one hurts:
#   1. containers are running
#   2. the API answers /api/health/
#   3. Postgres accepts a query
#   4. Redis answers PING
#   5. a Celery worker answers a ping over the broker
#   6. celery-beat's schedule file is being updated
#   7. disk free
#   8. the newest backup is recent enough  (prod only)
#   9. TLS certificate expiry               (prod only)
#
# EXITS NON-ZERO ON ANY FAILURE, so it can be a cron job or a monitoring probe:
#   */10 * * * * /opt/sies/scripts/health_check.sh --prod -q || echo "SIES unhealthy"
#
# Warnings do NOT fail the run. Only things that mean the system is not doing
# its job do — otherwise the alert gets muted, and then the real one is muted too.
#
# Read-only. Safe to run as often as you like.
# =============================================================================
set -uo pipefail

PROD=0; QUIET=0
while [ $# -gt 0 ]; do
  case "$1" in
    --prod|-p)  PROD=1; shift ;;
    --quiet|-q) QUIET=1; shift ;;
    -h|--help)  sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1  (try --help)" >&2; exit 1 ;;
  esac
done

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
FAILURES=0; WARNINGS=0

say()  { [ "$QUIET" = 1 ] || printf '%s\n' "$1"; }
ok()   { [ "$QUIET" = 1 ] || printf '  %b✔%b  %s\n' "$GREEN"  "$NC" "$1"; }
info() { [ "$QUIET" = 1 ] || printf '  %b→%b  %s\n' "$CYAN"   "$NC" "$1"; }
warn() { WARNINGS=$((WARNINGS+1)); [ "$QUIET" = 1 ] || printf '  %b⚠%b  %s\n' "$YELLOW" "$NC" "$1"; }
bad()  { FAILURES=$((FAILURES+1)); printf '  %b✘%b  %s\n' "$RED" "$NC" "$1" >&2; }

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname -- "$SCRIPT_DIR")"
cd -- "$PROJECT_ROOT" || { echo "cannot enter ${PROJECT_ROOT}" >&2; exit 1; }

if [ "$PROD" = 1 ]; then
  COMPOSE_FILE="docker-compose.prod.yml"; ENV_FILE=".env.production"
  BACKEND="sies-backend"; DB="sies-db"; REDIS="sies-redis"
  WORKER="sies-celery-worker"; BEAT="sies-celery-beat"; ADMIN="sies-admin"; PROXY="sies-traefik"
else
  COMPOSE_FILE="docker-compose.dev.yml"; ENV_FILE=".env.development"
  BACKEND="sies-backend-dev"; DB="sies-db-dev"; REDIS="sies-redis-dev"
  WORKER="sies-celery-worker-dev"; BEAT="sies-celery-beat-dev"; ADMIN="sies-admin-dev"; PROXY="sies-traefik-dev"
fi

envget() { grep -E "^$1=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"'"'" ; }
DOMAIN=$(envget DOMAIN); DOMAIN="${DOMAIN:-localhost}"
DB_NAME=$(envget DB_NAME); DB_NAME="${DB_NAME:-sies}"
DB_USER=$(envget DB_USER); DB_USER="${DB_USER:-sies}"

say ""
say "$(printf '%bSIES health%b  %s  (%s)' "$BOLD" "$NC" "$(date '+%Y-%m-%d %H:%M:%S')" "$([ "$PROD" = 1 ] && echo production || echo development)")"
say ""

# ── 1. Containers ────────────────────────────────────────────────────────────
running() { docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$1"; }

for c in "$PROXY" "$DB" "$REDIS" "$BACKEND" "$WORKER" "$BEAT" "$ADMIN"; do
  if running "$c"; then
    # A container can be `Up` and simultaneously `unhealthy`; the restart policy
    # then keeps it running while it fails every request. Report the health
    # state, not just the fact that it exists.
    STATE=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}running{{end}}' "$c" 2>/dev/null)
    case "$STATE" in
      healthy|running) ok "$c ($STATE)" ;;
      starting)        warn "$c is still starting" ;;
      *)               bad  "$c is $STATE" ;;
    esac
  else
    bad "$c is NOT running"
  fi
done

# ── 2. API ───────────────────────────────────────────────────────────────────
# Through the container, with the real Host header: ALLOWED_HOSTS is strict in
# production and a probe sent as `Host: 127.0.0.1` gets a 400 from a perfectly
# healthy application.
if running "$BACKEND"; then
  if docker exec "$BACKEND" python -c "
import urllib.request as u
r = u.urlopen(u.Request('http://127.0.0.1:8000/api/health/', headers={'Host':'${DOMAIN}'}), timeout=5)
raise SystemExit(0 if r.status == 200 else 1)
" >/dev/null 2>&1; then
    ok "/api/health/ answers 200"
  else
    bad "/api/health/ did not answer 200 — the API is down"
  fi
fi

# From outside, as a browser sees it. This is a different fact from the one
# above: it also proves Traefik is routing and TLS is working.
if [ "$PROD" = 1 ]; then
  if curl -fsS -m 10 "https://${DOMAIN}/api/health/" >/dev/null 2>&1; then
    ok "https://${DOMAIN}/api/health/ answers from outside"
  else
    bad "the site does not answer over HTTPS — visitors cannot reach it"
  fi
fi

# ── 3. Postgres ──────────────────────────────────────────────────────────────
# A real query, not pg_isready. pg_isready says the process is listening;
# SELECT 1 says the database is actually usable, which is a different thing when
# the disk is full or the cluster is in recovery.
if running "$DB"; then
  if docker exec "$DB" psql -U "$DB_USER" -d "$DB_NAME" -tAc 'SELECT 1;' >/dev/null 2>&1; then
    CONNS=$(docker exec "$DB" psql -U "$DB_USER" -d "$DB_NAME" -tAc \
      'SELECT count(*) FROM pg_stat_activity;' 2>/dev/null || echo '?')
    MAXCONN=$(docker exec "$DB" psql -U "$DB_USER" -d "$DB_NAME" -tAc 'SHOW max_connections;' 2>/dev/null || echo '?')
    ok "Postgres answers queries (${CONNS}/${MAXCONN} connections)"
    if [ "$CONNS" != '?' ] && [ "$MAXCONN" != '?' ] && [ "$CONNS" -gt $((MAXCONN * 80 / 100)) ]; then
      warn "connection pool is over 80% — lower DB_CONN_MAX_AGE or GUNICORN_WORKERS"
    fi
  else
    bad "Postgres is running but will not answer SELECT 1"
  fi
fi

# ── 4. Redis ─────────────────────────────────────────────────────────────────
if running "$REDIS"; then
  if docker exec "$REDIS" redis-cli ping 2>/dev/null | grep -q PONG; then
    QUEUED=$(docker exec "$REDIS" redis-cli -n 2 llen celery 2>/dev/null || echo 0)
    ok "Redis answers PING (${QUEUED} task(s) queued)"
    # A queue that is long is not itself a failure — a bulk fee run is supposed
    # to make one. A queue that is long AND not draining is, but that needs two
    # samples, which is monitoring's job rather than this script's.
    [ "${QUEUED:-0}" -gt 500 ] && warn "${QUEUED} queued tasks — is the worker keeping up?"
  else
    bad "Redis did not answer PING — no background work can run"
  fi
fi

# ── 5. Celery worker ─────────────────────────────────────────────────────────
# A worker that has lost its broker keeps running and looks perfectly fine in
# `docker ps`. Only a ping across the broker proves it is still consuming.
if running "$WORKER"; then
  if docker exec "$WORKER" celery -A core inspect ping -t 10 2>/dev/null | grep -q pong; then
    ok "Celery worker answers a broker ping"
  else
    bad "the Celery worker does not answer — fees, reports and reminders are not running"
  fi
fi

# ── 6. Celery beat ───────────────────────────────────────────────────────────
# Beat has no port and no inspect interface. Its schedule file's mtime is the
# only external evidence that the clock is still ticking; a wedged beat stops
# touching it while the container stays up.
if running "$BEAT"; then
  SCHED=$(docker exec "$BEAT" sh -c 'ls /beat/celerybeat-schedule* /tmp/celerybeat-schedule* 2>/dev/null | head -1' 2>/dev/null)
  if [ -n "$SCHED" ]; then
    if docker exec "$BEAT" sh -c "find '$SCHED' -mmin -60 | grep -q ." 2>/dev/null; then
      ok "celery-beat's schedule was written within the hour"
    else
      warn "celery-beat has not written its schedule in over an hour — it may be wedged"
    fi
  else
    warn "celery-beat has no schedule file yet (normal for the first few minutes)"
  fi
fi

# ── 7. Disk ──────────────────────────────────────────────────────────────────
# A full disk stops Postgres mid-write, and that is the failure with the longest
# recovery time on this box. Warn early, fail before it is too late to fix
# calmly.
DISK_PCT=$(df --output=pcent . | tail -1 | tr -dc '0-9')
DISK_FREE=$(df -h --output=avail . | tail -1 | tr -d ' ')
if [ "${DISK_PCT:-0}" -ge 95 ]; then
  bad "disk ${DISK_PCT}% full (${DISK_FREE} free) — Postgres will stop writing"
elif [ "${DISK_PCT:-0}" -ge 85 ]; then
  warn "disk ${DISK_PCT}% full (${DISK_FREE} free) — prune images or old backups"
else
  ok "disk ${DISK_PCT}% used, ${DISK_FREE} free"
fi

MEM_FREE=$(free -m | awk '/^Mem:/{print $7}')
[ "${MEM_FREE:-9999}" -lt 200 ] && warn "only ${MEM_FREE} MB available memory — check swap is on"

# ── 8. Backups ───────────────────────────────────────────────────────────────
if [ "$PROD" = 1 ]; then
  BACKUP_DIR=$(envget BACKUP_DIR); BACKUP_DIR="${BACKUP_DIR:-$PROJECT_ROOT/backups}"
  NEWEST=$(find "$BACKUP_DIR" -name '*_db_*.dump' -type f -printf '%T@ %p\n' 2>/dev/null \
             | sort -rn | head -1 | cut -d' ' -f2-)
  if [ -z "$NEWEST" ]; then
    bad "no database backup exists. Run scripts/setup_backup_cron.sh today."
  else
    AGE_H=$(( ( $(date +%s) - $(stat -c %Y "$NEWEST") ) / 3600 ))
    if [ "$AGE_H" -gt 48 ]; then
      # Two days is past "the cron slipped" and into "the cron is broken".
      bad "the newest backup is ${AGE_H}h old — the nightly job is not running"
    elif [ "$AGE_H" -gt 26 ]; then
      warn "the newest backup is ${AGE_H}h old — last night's run may have failed"
    else
      ok "newest backup is ${AGE_H}h old ($(basename "$NEWEST"))"
    fi
  fi
fi

# ── 9. TLS ───────────────────────────────────────────────────────────────────
# Renewal is automatic, so this is not about remembering to renew — it is about
# noticing that automatic renewal has quietly stopped working, which shows up
# only as a shrinking number.
if [ "$PROD" = 1 ] && command -v openssl >/dev/null 2>&1; then
  EXP=$(echo | openssl s_client -servername "$DOMAIN" -connect "${DOMAIN}:443" 2>/dev/null \
        | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)
  if [ -n "$EXP" ]; then
    DAYS=$(( ( $(date -d "$EXP" +%s) - $(date +%s) ) / 86400 ))
    if   [ "$DAYS" -lt 7 ];  then bad  "the TLS certificate expires in ${DAYS} days — renewal has failed"
    elif [ "$DAYS" -lt 21 ]; then warn "the TLS certificate expires in ${DAYS} days (renewal is due at 30)"
    else                          ok   "TLS certificate valid for ${DAYS} more days"
    fi
  else
    warn "could not read the TLS certificate for ${DOMAIN}"
  fi
fi

# ── Result ───────────────────────────────────────────────────────────────────
say ""
if [ "$FAILURES" -gt 0 ]; then
  printf '  %b%s failure(s), %s warning(s)%b\n\n' "$RED" "$FAILURES" "$WARNINGS" "$NC" >&2
  exit 1
fi
say "$(printf '  %bAll checks passed%b  (%s warning(s))\n' "$GREEN" "$NC" "$WARNINGS")"
exit 0
