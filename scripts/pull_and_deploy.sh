#!/usr/bin/env bash
# =============================================================================
# SIES — the routine deploy. This is the one that runs every release.
#
#   sudo -u sies scripts/pull_and_deploy.sh
#   sudo -u sies scripts/pull_and_deploy.sh --no-pull    # deploy what is checked out
#   sudo -u sies scripts/pull_and_deploy.sh --no-backup  # you already have one
#   sudo -u sies scripts/pull_and_deploy.sh --yes        # no confirmation prompt
#
#   git pull -> build -> migrate -> collectstatic -> restart -> health check
#   and, if the health check fails, PUT THE OLD IMAGES BACK.
#
# THE CONTRACT
#   Either the new release is running and answering, or the previous one is.
#   The script never exits leaving the site down and quiet. Every failure path
#   either rolls back or tells you, in the last ten lines of output, exactly
#   what is running and what to do next.
#
# WHAT ROLLBACK CAN AND CANNOT DO
#   It restores IMAGES. It does not restore the DATABASE.
#   Migrations run before anything is swapped, and `migrate` only moves
#   forward — it cannot reverse a migration whose file is not on the branch you
#   have rolled back to. That asymmetry is the whole reason for the rule in
#   DEPLOY.md: never drop a column in the release that stops using it. Obey it
#   and a rollback is only ever code. Break it and rollback restores code that
#   selects a column the table no longer has, and every request 500s with
#   nothing you can redeploy to fix it.
#   A pre-deploy dump is taken at step 4 for the case where that has happened
#   anyway; restoring it is a decision a human makes, with restore_backup.sh.
#
# SAFE TO RE-RUN. A run with no new commits rebuilds and restarts, which is a
# no-op you can use to prove the pipeline still works.
# =============================================================================
set -uo pipefail

DO_PULL=1; DO_BACKUP=1; ASSUME_YES=0
while [ $# -gt 0 ]; do
  case "$1" in
    --no-pull)   DO_PULL=0; shift ;;
    --no-backup) DO_BACKUP=0; shift ;;
    --yes|-y)    ASSUME_YES=1; shift ;;
    -h|--help)   sed -n '2,31p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1  (try --help)" >&2; exit 1 ;;
  esac
done

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

TOTAL=10
START_TIME=$(date +%s)
step() { printf '\n%b[%s/%s]%b %b%s%b\n' "${BOLD}${BLUE}" "$1" "$TOTAL" "$NC" "$BOLD" "$2" "$NC"; }
ok()   { printf '  %b✔%b  %s\n' "$GREEN"  "$NC" "$1"; }
info() { printf '  %b→%b  %s\n' "$CYAN"   "$NC" "$1"; }
warn() { printf '  %b⚠%b  %s\n' "$YELLOW" "$NC" "$1"; }
hr()   { printf '%b%s%b\n' "$BLUE" "$(printf '─%.0s' $(seq 1 70))" "$NC"; }

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname -- "$SCRIPT_DIR")"
SCRIPT_PATH="$SCRIPT_DIR/$(basename -- "${BASH_SOURCE[0]}")"
cd -- "$PROJECT_ROOT" || { echo "cannot enter ${PROJECT_ROOT}" >&2; exit 1; }

COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.production"
BACKEND="sies-backend"
DB_CONTAINER="sies-db"
# Restart order matters: workers and the clock first, the tiers that serve
# browser traffic last, so the shortest possible time is spent with a serving
# container down.
BACKGROUND_SERVICES="sies-celery-worker sies-celery-beat"
SERVING_SERVICES="sies-backend sies-admin"
# Images that a rollback puts back. Anything not listed here is either
# unversioned (postgres, redis, traefik are pinned upstream tags) or not built
# by us.
ROLLBACK_IMAGES="sies-backend sies-admin"

compose() { docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"; }
elapsed() { echo $(( $(date +%s) - START_TIME )); }

# ── Failure handling ─────────────────────────────────────────────────────────
# Everything after the build is guarded. `die` is used before any image has
# changed (nothing to undo); `fail` is used after, and rolls back first.

die() {
  printf '\n  %b✘ ERROR:%b %s\n' "$RED" "$NC" "$1" >&2
  printf '  %bNothing was changed. The running release is untouched.%b\n' "$CYAN" "$NC" >&2
  exit 1
}

ROLLBACK_ARMED=0   # set to 1 once :rollback tags exist and images may have moved

rollback() {
  local reason="$1"
  printf '\n'; hr
  printf '%b  ROLLING BACK%b — %s\n' "${BOLD}${YELLOW}" "$NC" "$reason"
  hr

  if [ "$ROLLBACK_ARMED" = 0 ]; then
    warn "no previous images were tagged — there is nothing to roll back to."
    warn "This is normal on a first deploy. Fix the failure and re-run."
    return 1
  fi

  local img
  for img in $ROLLBACK_IMAGES; do
    if docker image inspect "${img}:rollback" >/dev/null 2>&1; then
      docker tag "${img}:rollback" "${img}:latest"
      info "${img}:latest restored from :rollback"
    else
      warn "${img}:rollback is missing — leaving ${img}:latest as it is"
    fi
  done

  info "recreating containers on the previous images…"
  # shellcheck disable=SC2086  # word splitting of the service list is intended
  if ! compose up -d --no-deps --force-recreate $BACKGROUND_SERVICES $SERVING_SERVICES >/dev/null 2>&1; then
    printf '\n  %b✘ THE ROLLBACK ITSELF FAILED.%b\n' "$RED" "$NC" >&2
    printf '  The site is DOWN. Do this now, by hand:\n' >&2
    printf '    docker compose -f %s --env-file %s up -d\n' "$COMPOSE_FILE" "$ENV_FILE" >&2
    printf '    ./scripts/logs.sh -p %s\n' "$BACKEND" >&2
    return 1
  fi

  if wait_healthy "$BACKEND" 120; then
    printf '\n  %b✔ Rolled back. The PREVIOUS release is serving.%b\n' "$GREEN" "$NC"
    printf '  The database was NOT rolled back — migrations only move forward.\n'
    printf '  If the failure was a schema mismatch, read DEPLOY.md "Database changes".\n'
    return 0
  fi

  printf '\n  %b✘ The previous images are back but the backend is still not answering.%b\n' "$RED" "$NC" >&2
  printf '  This is very unlikely to be the code. Look at the database first:\n' >&2
  printf '    ./scripts/health_check.sh --prod\n' >&2
  printf '    ./scripts/logs.sh -p %s\n' "$BACKEND" >&2
  return 1
}

fail() {
  rollback "$1" || true
  printf '\n  Deploy aborted after %ss.\n' "$(elapsed)" >&2
  exit 1
}

# Waits until a container actually answers. Gives up early if it has exited —
# otherwise a crash-looping image burns the whole timeout in silence.
wait_healthy() {  # container timeout
  local c="$1" max="$2" t0=$SECONDS
  while true; do
    if docker exec "$c" python -c "
import urllib.request as u
u.urlopen(u.Request('http://127.0.0.1:8000/api/health/', headers={'Host':'${DOMAIN}'}), timeout=3)
" >/dev/null 2>&1; then
      printf '\r\033[K'
      return 0
    fi
    if ! docker ps -q -f "name=^${c}$" | grep -q .; then
      printf '\r\033[K'
      warn "${c} exited while starting. Last lines:"
      docker logs "$c" --tail=30 2>&1 | sed 's/^/      /'
      return 1
    fi
    if [ $(( SECONDS - t0 )) -ge "$max" ]; then
      printf '\r\033[K'
      warn "${c} did not answer within ${max}s. Last lines:"
      docker logs "$c" --tail=30 2>&1 | sed 's/^/      /'
      return 1
    fi
    printf '      %s starting… %ss\r' "$c" "$(( SECONDS - t0 ))"
    sleep 2
  done
}

# Traefik will not route to a server until its own health check has passed once
# (3s interval, see the compose labels). A container that answers is therefore
# not yet a container that receives traffic, and the gap between those two facts
# is where a deploy loses requests. This closes it.
wait_in_pool() {  # traefik-service-name timeout
  local svc="$1" max="$2" t0=$SECONDS
  while [ $(( SECONDS - t0 )) -lt "$max" ]; do
    if curl -fsS -m 3 "http://127.0.0.1:8080/api/http/services/${svc}@docker" 2>/dev/null \
         | grep -q '"status":"UP"'; then
      return 0
    fi
    sleep 2
  done
  return 1
}

# ── Banner ───────────────────────────────────────────────────────────────────
hr
printf '%b  SIES — production deploy%b\n' "${BOLD}${GREEN}" "$NC"
printf '  %s   %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$PROJECT_ROOT"
hr

# ── 1. Pre-flight ────────────────────────────────────────────────────────────
step 1 "Pre-flight checks"

command -v docker >/dev/null 2>&1 || die "docker is not installed"
docker compose version >/dev/null 2>&1 || die "the docker compose plugin is missing"
docker info >/dev/null 2>&1 || die "cannot talk to the docker daemon"
[ -f "$COMPOSE_FILE" ] || die "$COMPOSE_FILE not found"
[ -f "$ENV_FILE" ] || die "$ENV_FILE not found"
ok "docker, compose, and the compose/env files are present"

if grep -qE '^[A-Z_]+=.*(CHANGE_ME|REPLACE)' "$ENV_FILE"; then
  die "$ENV_FILE still contains placeholder values"
fi

DOMAIN=$(grep -E '^DOMAIN=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"'"'" )
[ -n "$DOMAIN" ] || die "DOMAIN is not set in $ENV_FILE"
# The health probe carries a real Host header on purpose: ALLOWED_HOSTS is a
# fixed list in production, so a request arriving as `Host: 127.0.0.1` is
# answered with 400 and a perfectly healthy container looks permanently broken.
ok "domain: ${DOMAIN}"

compose config -q || die "compose configuration is invalid"
ok "compose configuration parses"

# A build needs room for a second copy of every image. Running out of disk
# halfway through a build leaves a half-written layer and an unclear error.
DISK_FREE_GB=$(df -BG --output=avail . | tail -1 | tr -dc '0-9')
if [ "${DISK_FREE_GB:-0}" -lt 5 ]; then
  die "only ${DISK_FREE_GB} GB free — a build needs headroom. Try: docker image prune -f"
fi
ok "${DISK_FREE_GB} GB free on this filesystem"

if ! docker ps --format '{{.Names}}' | grep -qx "$DB_CONTAINER"; then
  warn "${DB_CONTAINER} is not running — this looks like a stopped stack, not a release"
  info "if that is deliberate, use scripts/fresh_deploy.sh instead"
fi

# ── 2. Record the state we can return to ─────────────────────────────────────
# Done BEFORE the pull, so the recorded commit is genuinely the one that is
# running, and before the build, so the recorded images are genuinely the ones
# in the containers.
step 2 "Recording the current release"

BEFORE_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)
info "current commit: ${BEFORE_SHA}"

for img in $ROLLBACK_IMAGES; do
  if docker image inspect "${img}:latest" >/dev/null 2>&1; then
    # A tag, not a copy: it costs nothing and pins the image ID so the build
    # below cannot garbage-collect the layers out from under it.
    docker tag "${img}:latest" "${img}:rollback"
    ok "${img}:latest tagged as :rollback"
    ROLLBACK_ARMED=1
  else
    warn "${img}:latest does not exist yet — no rollback target for it"
  fi
done
[ "$ROLLBACK_ARMED" = 1 ] || warn "rollback is NOT available on this run (first deploy?)"

# ── 3. Pull ──────────────────────────────────────────────────────────────────
step 3 "Pulling latest code"
if [ "$DO_PULL" = 0 ]; then
  info "skipped (--no-pull) — deploying whatever is checked out"
else
  if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
    warn "the working tree has local modifications:"
    git status --short | sed 's/^/      /'
    warn "a pull may conflict; commit or stash first if it does"
  fi
  SELF_HASH_BEFORE=$(md5sum "$SCRIPT_PATH" 2>/dev/null | cut -d' ' -f1)

  git pull --ff-only origin main || die "git pull failed (see above)"
  AFTER_SHA=$(git rev-parse --short HEAD)

  if [ "$BEFORE_SHA" = "$AFTER_SHA" ]; then
    info "no new commits (still at ${AFTER_SHA}) — rebuilding and restarting anyway"
  else
    ok "${BEFORE_SHA} → ${AFTER_SHA}"
    git log --oneline "${BEFORE_SHA}..${AFTER_SHA}" | sed 's/^/      /'
  fi

  # bash does not read a script into memory up front. It reads it in blocks,
  # tracking a byte offset — so the pull above can rewrite this file underneath
  # the running shell, and bash then resumes at an offset that is now the middle
  # of a different line. It executes nonsense, halfway through a production
  # deploy. The risk is proportional to how much the script changed, which makes
  # the dangerous case exactly the one where a deploy overhaul lands.
  #
  # So if this file changed, hand over to the new copy. Steps 1–3 are safe to
  # repeat: the second pull finds nothing to do.
  if [ -z "${SIES_DEPLOY_REEXEC:-}" ] && \
     [ "$SELF_HASH_BEFORE" != "$(md5sum "$SCRIPT_PATH" 2>/dev/null | cut -d' ' -f1)" ]; then
    info "the pull updated this deploy script — restarting with the new version"
    export SIES_DEPLOY_REEXEC=1
    exec bash "$SCRIPT_PATH" "$@"
  fi
fi

# ── 4. Pre-deploy backup ─────────────────────────────────────────────────────
# Taken at the single most likely moment to need it: immediately before a
# migration. Custom format (-Fc), because that is what restore_backup.sh reads
# and what pg_restore can restore selectively.
step 4 "Backing up the database before migrating"
if [ "$DO_BACKUP" = 0 ]; then
  warn "skipped (--no-backup) — you are deploying a migration with no safety net"
elif ! docker ps --format '{{.Names}}' | grep -qx "$DB_CONTAINER"; then
  warn "${DB_CONTAINER} is not running — no backup taken"
else
  BACKUP_DIR=$(grep -E '^BACKUP_DIR=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"'"'" )
  BACKUP_DIR="${BACKUP_DIR:-$PROJECT_ROOT/backups}"
  mkdir -p "$BACKUP_DIR"
  chmod 750 "$BACKUP_DIR"
  DB_NAME=$(grep -E '^DB_NAME=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"'"'" )
  DB_USER=$(grep -E '^DB_USER=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"'"'" )
  SERVER_NAME=$(grep -E '^THIS_SERVER_NAME=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"'"'" )
  SERVER_NAME="${SERVER_NAME:-sies}"
  PRE_DUMP="${BACKUP_DIR}/${SERVER_NAME}_predeploy_$(date +%Y%m%d_%H%M%S)_${BEFORE_SHA}.dump"

  info "dumping ${DB_NAME}…"
  if docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" -Fc "$DB_NAME" > "$PRE_DUMP" 2>/dev/null; then
    chmod 600 "$PRE_DUMP"
    ok "$(basename "$PRE_DUMP")  ($(du -h "$PRE_DUMP" | cut -f1))"
    # Scoped to THIS server's pre-deploy dumps. A broader glob would let this
    # machine prune another machine's history off a shared volume.
    ls -t "${BACKUP_DIR}/${SERVER_NAME}_predeploy_"*.dump 2>/dev/null | tail -n +6 | xargs -r rm -f
    ok "older pre-deploy dumps pruned (keeping 5)"
  else
    rm -f "$PRE_DUMP"
    die "pg_dump failed — refusing to migrate without a backup. Use --no-backup to override."
  fi
fi

# ── 5. Build ─────────────────────────────────────────────────────────────────
step 5 "Building images"
info "unchanged layers are cached; a backend-only change takes under a minute"
if ! compose build; then
  # Nothing has been swapped, so there is nothing to roll back — the old images
  # are still tagged :latest and still running. Say so plainly.
  warn "the build failed. The running release is untouched and still serving."
  for img in $ROLLBACK_IMAGES; do docker rmi "${img}:rollback" >/dev/null 2>&1 || true; done
  exit 1
fi
ok "images built"

# From here on, a failure rolls back.

# ── 6. Migrate ───────────────────────────────────────────────────────────────
# On the NEW image, in a one-off container, BEFORE anything is swapped. Two
# reasons: a migration that fails leaves the old containers serving the old
# code against an unchanged database; and the new code never starts against a
# schema it has not got.
step 6 "Applying migrations (new image, before the swap)"
PENDING=$(compose run --rm --no-deps -T "$BACKEND" python manage.py showmigrations --plan 2>/dev/null | grep -c '^\[ \]' || true)
if [ "${PENDING:-0}" -gt 0 ]; then
  info "${PENDING} migration(s) to apply"
  if [ "$ASSUME_YES" = 0 ] && [ -t 0 ]; then
    compose run --rm --no-deps -T "$BACKEND" python manage.py showmigrations --plan 2>/dev/null \
      | grep '^\[ \]' | sed 's/^/      /'
    printf '  Apply these? [y/N] '
    read -r reply
    case "$reply" in [Yy]*) ;; *) die "aborted before migrating" ;; esac
  fi
else
  info "no pending migrations"
fi

if ! compose run --rm --no-deps -T "$BACKEND" python manage.py migrate --noinput; then
  # Deliberately NOT a rollback: nothing has been swapped, the old containers
  # are still serving, and a half-applied migration is a situation a human must
  # look at rather than one a script should paper over.
  printf '\n  %b✘ MIGRATIONS FAILED.%b\n' "$RED" "$NC" >&2
  printf '  Nothing was swapped — the previous release is still serving.\n' >&2
  printf '  The database may be partially migrated. Check before re-running:\n' >&2
  printf '    docker compose -f %s --env-file %s run --rm %s python manage.py showmigrations\n' \
    "$COMPOSE_FILE" "$ENV_FILE" "$BACKEND" >&2
  [ -n "${PRE_DUMP:-}" ] && printf '  Pre-deploy dump: %s\n' "$PRE_DUMP" >&2
  exit 1
fi
ok "migrations applied"

# The second of the two guards from DEPLOY.md. It compares every model's columns
# against information_schema and exits non-zero when the code selects a column
# the database has not got — which is what a rolled-back release looks like from
# the inside. Running it here means a mismatch aborts the deploy with the old
# containers still serving, instead of 500ing after the swap.
# `help <command>` distinguishes "the guard says no" from "the guard does not
# exist yet" — both exit 1 from manage.py, and treating the second as a schema
# mismatch would block every deploy until the command is written.
if compose run --rm --no-deps -T "$BACKEND" python manage.py help check_schema >/dev/null 2>&1; then
  if compose run --rm --no-deps -T "$BACKEND" python manage.py check_schema >/dev/null 2>&1; then
    ok "database schema matches the new code"
  else
    printf '\n  %b✘ SCHEMA MISMATCH — the new code selects columns the database has not got.%b\n' "$RED" "$NC" >&2
    compose run --rm --no-deps -T "$BACKEND" python manage.py check_schema 2>&1 | sed 's/^/      /' >&2
    printf '  Nothing was swapped; the previous release is still serving.\n' >&2
    printf '  See DEPLOY.md "Database changes: never drop a column in the release that stops using it".\n' >&2
    exit 1
  fi
else
  info "check_schema is not available yet (it arrives with the backend) — skipping"
fi

# ── 7. Static files ──────────────────────────────────────────────────────────
step 7 "Collecting static files"
if ! compose run --rm --no-deps -T "$BACKEND" python manage.py collectstatic --noinput >/dev/null; then
  fail "collectstatic failed"
fi
ok "static files collected"

# ── 8. Restart ───────────────────────────────────────────────────────────────
# Background tiers first: nothing is waiting on a Celery worker mid-request, so
# a gap there costs a few seconds of queue latency and nothing else. Then the
# serving tiers, one at a time, each proven healthy before the next is touched.
step 8 "Restarting services"

for svc in $BACKGROUND_SERVICES; do
  info "restarting ${svc}…"
  if ! compose up -d --no-deps --force-recreate "$svc" >/dev/null 2>&1; then
    fail "${svc} failed to start"
  fi
  ok "${svc} restarted"
done

for svc in $SERVING_SERVICES; do
  info "recreating ${svc}…"
  if ! compose up -d --no-deps --force-recreate "$svc" >/dev/null 2>&1; then
    fail "${svc} failed to start"
  fi

  if [ "$svc" = "$BACKEND" ]; then
    if ! wait_healthy "$BACKEND" 180; then
      fail "${BACKEND} never answered /api/health/ on the new image"
    fi
    ok "${BACKEND} is answering"
    # Answering is not the same fact as receiving traffic. Traefik holds a new
    # server out of the pool until its own 3s health check has passed once.
    if wait_in_pool "sies-backend" 60; then
      ok "${BACKEND} is in the Traefik pool"
    else
      warn "${BACKEND} answers but Traefik has not marked it UP after 60s"
      warn "  visitors may be getting 503 — check the dashboard before walking away"
    fi
  else
    # The SPA has no /api/health/; Traefik's own view of it is the honest signal.
    if wait_in_pool "sies-admin" 90; then
      ok "${svc} is in the Traefik pool"
    else
      fail "${svc} never became healthy in Traefik"
    fi
  fi
done

# ── 9. Health check ──────────────────────────────────────────────────────────
# The real one: through Traefik, over TLS, as a browser would — not `docker
# exec` against 127.0.0.1, which proves only that the container is alive.
step 9 "Verifying the deployed release"

PUBLIC_OK=0
for _ in $(seq 1 15); do
  if curl -fsS -m 10 "https://${DOMAIN}/api/health/" >/dev/null 2>&1; then
    PUBLIC_OK=1; break
  fi
  sleep 2
done
if [ "$PUBLIC_OK" = 1 ]; then
  ok "https://${DOMAIN}/api/health/ answers"
else
  fail "the site does not answer over HTTPS after the deploy"
fi

if curl -fsS -m 10 -o /dev/null -w '%{http_code}' "https://${DOMAIN}/myadmin" 2>/dev/null | grep -qE '^(200|30[128])$'; then
  ok "https://${DOMAIN}/myadmin serves the SPA"
else
  warn "/myadmin did not answer as expected — the API is up, the dashboard may not be"
fi

if bash "$SCRIPT_DIR/health_check.sh" --prod --quiet; then
  ok "health_check.sh: all checks passed"
else
  warn "health_check.sh reported a problem — the release is live, read it:"
  bash "$SCRIPT_DIR/health_check.sh" --prod 2>&1 | sed 's/^/      /'
fi

# ── 10. Tidy up ──────────────────────────────────────────────────────────────
# Only now, once the new release is proven. Until this point the :rollback tags
# are the only thing standing between a bad release and a manual rebuild.
step 10 "Tidying up"
for img in $ROLLBACK_IMAGES; do
  docker rmi "${img}:rollback" >/dev/null 2>&1 || true
done
ok "rollback tags released"

# Dangling images only (-f without -a): this never removes an image a stopped
# container still references, so yesterday's release stays available for a
# manual `docker tag`.
PRUNED=$(docker image prune -f 2>/dev/null | tail -1)
info "${PRUNED:-nothing to prune}"

printf '\n'; hr
printf '%b  ✔ Deployed in %ss%b\n' "${BOLD}${GREEN}" "$(elapsed)" "$NC"
printf '    commit   %s\n' "$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
printf '    app      https://%s/myadmin\n' "$DOMAIN"
[ -n "${PRE_DUMP:-}" ] && printf '    backup   %s\n' "$PRE_DUMP"
hr
