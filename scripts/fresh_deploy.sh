#!/usr/bin/env bash
# =============================================================================
# SIES — FIRST deploy on a prepared server. Run this once, after bootstrap.sh.
#
#   sudo -u sies scripts/fresh_deploy.sh
#   sudo -u sies scripts/fresh_deploy.sh --no-seed        # no demo data
#   sudo -u sies scripts/fresh_deploy.sh --no-superuser   # create it later
#
# Order, and why:
#   1. verify .env.production is real, not a filled-out-by-nobody copy
#   2. build the images
#   3. start Postgres and Redis, wait for them to be genuinely ready
#   4. migrate  — on an empty database this creates the schema
#   5. collectstatic
#   6. start the application containers
#   7. create the first superuser (interactive; skipped when not on a terminal)
#   8. seed the branch's default categories
#   9. health check
#
# Every deploy AFTER this one is scripts/pull_and_deploy.sh, which is a
# different job with different failure modes — provisioning happens once and
# releasing happens weekly, and the two should never break for the same reason.
#
# SAFE TO RE-RUN. It never drops anything. A second run finds the database
# already migrated, the superuser already present, and says so. The only step
# that asks a question is the superuser, and it asks before it acts.
# =============================================================================
set -euo pipefail

SEED=1
SUPERUSER=1
while [ $# -gt 0 ]; do
  case "$1" in
    --no-seed)      SEED=0; shift ;;
    --no-superuser) SUPERUSER=0; shift ;;
    -h|--help)      sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1  (try --help)" >&2; exit 1 ;;
  esac
done

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

TOTAL=9
step() { printf '\n%b[%s/%s]%b %b%s%b\n' "${BOLD}${BLUE}" "$1" "$TOTAL" "$NC" "$BOLD" "$2" "$NC"; }
ok()   { printf '  %b✔%b  %s\n' "$GREEN"  "$NC" "$1"; }
info() { printf '  %b→%b  %s\n' "$CYAN"   "$NC" "$1"; }
warn() { printf '  %b⚠%b  %s\n' "$YELLOW" "$NC" "$1"; }
die()  { printf '\n  %b✘ ERROR:%b %s\n' "$RED" "$NC" "$1" >&2; exit 1; }

# cd with error handling: a failed cd followed by a docker compose call would
# run against whatever directory the caller happened to be in.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname -- "$SCRIPT_DIR")"
cd -- "$PROJECT_ROOT" || die "cannot enter ${PROJECT_ROOT}"

COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.production"
BACKEND="sies-backend"
compose() { docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"; }

printf '%b  SIES — first deploy%b   %s\n' "${BOLD}${GREEN}" "$NC" "$(date '+%Y-%m-%d %H:%M:%S')"
printf '  %s\n' "$PROJECT_ROOT"

# ── 1. Pre-flight ────────────────────────────────────────────────────────────
step 1 "Pre-flight checks"

command -v docker >/dev/null 2>&1 || die "docker is not installed. Run scripts/bootstrap.sh first."
docker compose version >/dev/null 2>&1 || die "the docker compose plugin is missing."
docker info >/dev/null 2>&1 || die "cannot talk to the docker daemon. Is this user in the docker group? (log out and back in after bootstrap.sh)"
ok "docker and compose available"

[ -f "$COMPOSE_FILE" ] || die "$COMPOSE_FILE not found"
[ -f "$ENV_FILE" ] || die "$ENV_FILE not found. Copy .env.production.example and fill it in."
ok "$COMPOSE_FILE and $ENV_FILE present"

# A world-readable .env.production is the database password and the session
# signing key, readable by every account on the box.
PERM=$(stat -c '%a' "$ENV_FILE")
if [ "$PERM" != "600" ]; then
  warn "$ENV_FILE is mode ${PERM}; tightening to 600"
  chmod 600 "$ENV_FILE"
fi

# The check that matters. A copied-but-unedited env file starts the stack
# perfectly and hands the world a known secret key, so this fails hard rather
# than warning.
PLACEHOLDERS=$(grep -nE '^[A-Z_]+=.*(CHANGE_ME|REPLACE|your-|example\.com)' "$ENV_FILE" || true)
if [ -n "$PLACEHOLDERS" ]; then
  printf '\n'
  printf '%s\n' "$PLACEHOLDERS" | sed 's/^/      /'
  die "the lines above are still placeholders. Fill them in before deploying."
fi
ok "no placeholder values left in $ENV_FILE"

# Anything the compose file needs that the env file does not define would fail
# later, mid-build, with a message about an unset variable and no context.
for v in DOMAIN DJANGO_SECRET_KEY DB_NAME DB_USER DB_PASSWORD ACME_EMAIL TRAEFIK_DASHBOARD_AUTH; do
  grep -qE "^${v}=.+" "$ENV_FILE" || die "${v} is missing or empty in ${ENV_FILE}"
done
ok "required variables present"

# `config` parses the compose file with the env file applied, so a typo in
# either is caught here rather than after a ten-minute build.
compose config -q || die "compose configuration is invalid (see above)"
ok "compose configuration parses"

DOMAIN=$(grep -E '^DOMAIN=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"'"'" )
info "domain: ${DOMAIN}"

# DNS must already point here or Let's Encrypt's HTTP-01 challenge fails, and
# three failures against production burn the weekly quota for this hostname.
if command -v getent >/dev/null 2>&1; then
  RESOLVED=$(getent hosts "$DOMAIN" 2>/dev/null | awk '{print $1}' | head -1 || true)
  PUBIP=$(curl -fsS -m 10 https://api.ipify.org 2>/dev/null || true)
  if [ -n "$RESOLVED" ] && [ -n "$PUBIP" ] && [ "$RESOLVED" = "$PUBIP" ]; then
    ok "DNS: ${DOMAIN} -> ${RESOLVED} (this server)"
  elif [ -z "$RESOLVED" ]; then
    warn "${DOMAIN} does not resolve — TLS issuance will fail until it does"
  else
    warn "${DOMAIN} resolves to ${RESOLVED}, this server is ${PUBIP:-unknown}"
    warn "  if that is a proxy, fine; if not, TLS issuance will fail"
  fi
fi

# ── 2. Build ─────────────────────────────────────────────────────────────────
step 2 "Building images"
info "first build pulls base images and compiles the SPA — several minutes"
compose build
ok "images built"

# ── 3. Data services ─────────────────────────────────────────────────────────
step 3 "Starting Postgres and Redis"
compose up -d sies-db sies-redis

info "waiting for Postgres to accept connections…"
for _ in $(seq 1 60); do
  if compose exec -T sies-db pg_isready -q 2>/dev/null; then
    ok "Postgres ready"
    break
  fi
  sleep 2
done
compose exec -T sies-db pg_isready -q 2>/dev/null \
  || die "Postgres did not become ready. Check: ./scripts/logs.sh -p sies-db"

compose exec -T sies-redis redis-cli ping >/dev/null 2>&1 \
  && ok "Redis ready" \
  || die "Redis did not answer PING"

# ── 4. Migrate ───────────────────────────────────────────────────────────────
# `run --rm` starts a one-off container from the built image rather than using
# a running one — on a first deploy there is no running backend yet, and doing
# it this way makes step 4 identical to the pre-swap migration in
# pull_and_deploy.sh.
step 4 "Applying migrations"
compose run --rm --no-deps -T "$BACKEND" python manage.py migrate --noinput \
  || die "migrations failed — nothing has been started, fix and re-run"
ok "database schema is current"

# ── 5. Static files ──────────────────────────────────────────────────────────
step 5 "Collecting static files"
compose run --rm --no-deps -T "$BACKEND" python manage.py collectstatic --noinput >/dev/null \
  || die "collectstatic failed"
ok "static files collected (the Django admin loads its CSS from here)"

# ── 6. Start everything ──────────────────────────────────────────────────────
step 6 "Starting the stack"
compose up -d
ok "all containers started"

info "waiting for the backend to answer /api/health/…"
HEALTHY=0
for _ in $(seq 1 60); do
  if docker exec "$BACKEND" python -c "
import urllib.request as u
u.urlopen(u.Request('http://127.0.0.1:8000/api/health/', headers={'Host':'${DOMAIN}'}), timeout=3)
" >/dev/null 2>&1; then
    HEALTHY=1; break
  fi
  sleep 2
done
[ "$HEALTHY" = 1 ] || {
  docker logs "$BACKEND" --tail=40 2>&1 | sed 's/^/      /'
  die "the backend never answered. Logs above."
}
ok "backend healthy"

# ── 7. Superuser ─────────────────────────────────────────────────────────────
# createsuperuser needs a TTY to prompt. Under cron, CI, or `| tee`, there is no
# terminal — so this detects that and skips with instructions rather than
# hanging forever on a prompt nobody can see.
step 7 "First superuser"
if [ "$SUPERUSER" = 0 ]; then
  info "skipped (--no-superuser)"
elif compose exec -T "$BACKEND" python -c "
import django; django.setup()
from django.contrib.auth import get_user_model
raise SystemExit(0 if get_user_model().objects.filter(is_superuser=True).exists() else 1)
" >/dev/null 2>&1; then
  ok "a superuser already exists — skipping"
elif [ -t 0 ] && [ -t 1 ]; then
  info "login is 11-digit phone + password (CLAUDE.md §1) — there is no email field"
  docker exec -it "$BACKEND" python manage.py createsuperuser \
    || warn "superuser not created; do it later with the command below"
else
  warn "no terminal attached — cannot prompt for a password."
  info "create it when you are at a terminal:"
  info "  docker exec -it ${BACKEND} python manage.py createsuperuser"
fi

# ── 8. Seed ──────────────────────────────────────────────────────────────────
# seed_categories is idempotent by design (signals.py seeds a branch's default
# fee and finance categories). Running it twice is a no-op, which is why it is
# safe to leave in a script people re-run.
step 8 "Seeding default categories"
if [ "$SEED" = 0 ]; then
  info "skipped (--no-seed)"
elif compose exec -T "$BACKEND" python manage.py seed_categories 2>/dev/null; then
  ok "default categories seeded"
else
  warn "seed_categories is not available yet (it arrives in Phase 1) — skipping"
fi

# ── 9. Health ────────────────────────────────────────────────────────────────
step 9 "Health check"
if bash "$SCRIPT_DIR/health_check.sh" --prod; then
  ok "all checks passed"
else
  warn "health_check.sh reported a problem — the stack is up, read its output above"
fi

printf '\n%b────────────────────────────────────────────────────%b\n' "$BOLD" "$NC"
printf '  %b✔ SIES is deployed.%b\n\n' "$GREEN" "$NC"
printf '    app        https://%s/myadmin\n' "$DOMAIN"
printf '    api        https://%s/api/\n' "$DOMAIN"
printf '    django     https://%s/admin/\n' "$DOMAIN"
printf '    traefik    ssh -L 8080:localhost:8080 <you>@<server>  then http://localhost:8080\n'
printf '\n  Next:\n'
printf '    1. %bscripts/setup_backup_cron.sh%b   — nightly backups. Do this today.\n' "$BOLD" "$NC"
printf '    2. take one backup and RESTORE it into a scratch database, once,\n'
printf '       so the restore path is known to work before it is needed.\n'
printf '    3. every later release: %bscripts/pull_and_deploy.sh%b\n' "$BOLD" "$NC"
