#!/usr/bin/env bash
# SIES — development helper.
#
#   scripts/dev.sh up        start everything    → http://localhost:5000/myadmin
#   scripts/dev.sh down      stop
#   scripts/dev.sh logs [s]  tail all, or one service
#   scripts/dev.sh shell     Django shell_plus
#   scripts/dev.sh bash      a shell in the backend container
#   scripts/dev.sh dbshell   psql
#   scripts/dev.sh mm [app]  makemigrations
#   scripts/dev.sh migrate   migrate
#   scripts/dev.sh test [label] run tests — narrow label while building,
#                            bare = full suite (phase boundaries only)
#   scripts/dev.sh seed      seed demo data
#   scripts/dev.sh admin     create a superuser
#   scripts/dev.sh reset     DESTROY volumes and rebuild from scratch
#   scripts/dev.sh ps        status
#
# Everything here is idempotent except `reset`, which says so.

set -euo pipefail

cd "$(dirname "$0")/.."

COMPOSE="docker compose -f docker-compose.dev.yml"
BE="sies-backend"
URL="http://localhost:5000/myadmin"

# A missing env file is the most common first-run failure; fix it silently.
if [[ ! -f .env.development ]]; then
  if [[ -f .env.development.example ]]; then
    echo "→ .env.development missing; copying from .example"
    cp .env.development.example .env.development
  else
    echo "✗ .env.development and its .example are both missing." >&2
    exit 1
  fi
fi

cmd="${1:-up}"; shift || true

case "$cmd" in
  up)
    $COMPOSE up -d --build
    echo "→ waiting for the backend…"
    for _ in $(seq 1 40); do
      if curl -fsS "http://localhost:5000/api/health/" >/dev/null 2>&1; then
        echo "✓ up"
        echo "    app       $URL"
        echo "    api       http://localhost:5000/api/"
        echo "    django    http://localhost:5000/admin/"
        echo "    traefik   http://localhost:8081"
        exit 0
      fi
      sleep 2
    done
    echo "! backend did not answer /api/health/ in 80s — check: scripts/dev.sh logs $BE" >&2
    ;;

  down)     $COMPOSE down ;;
  ps)       $COMPOSE ps ;;
  logs)     $COMPOSE logs -f --tail=100 "${1:-}" ;;
  bash)     $COMPOSE exec $BE bash ;;
  shell)    $COMPOSE exec $BE python manage.py shell ;;
  dbshell)  $COMPOSE exec $BE python manage.py dbshell ;;
  migrate)  $COMPOSE exec $BE python manage.py migrate ;;
  mm)       $COMPOSE exec $BE python manage.py makemigrations "${1:-}" ;;
  admin)    $COMPOSE exec $BE python manage.py create_admin ;;
  seed)     $COMPOSE exec $BE python manage.py seed_demo ;;

  test)
    # CELERY_TASK_ALWAYS_EAGER is set in settings under test (awliaa's pattern),
    # so scheduled work runs inline and is assertable.
    #
    # --keepdb always: recreating Postgres per run is the largest single cost.
    # --parallel ONLY on a full run — on one module the worker startup costs
    # more than the parallelism saves. See CLAUDE.md §4a.
    label="${1:-}"
    if [[ -n "$label" ]]; then
      echo "→ testing $label"
      $COMPOSE exec $BE python manage.py test "$label" --keepdb "${@:2}"
    else
      echo "→ full suite (do this at phase boundaries, not every edit)"
      $COMPOSE exec $BE python manage.py test --keepdb --parallel
    fi
    ;;

  reset)
    read -rp "This DESTROYS the dev database and media. Type 'yes': " ok
    [[ "$ok" == "yes" ]] || { echo "aborted"; exit 1; }
    $COMPOSE down -v
    $COMPOSE up -d --build
    sleep 8
    $COMPOSE exec $BE python manage.py migrate
    $COMPOSE exec $BE python manage.py seed_demo
    echo "✓ reset — $URL"
    ;;

  *)
    sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
    ;;
esac
