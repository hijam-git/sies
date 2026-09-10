#!/usr/bin/env bash
# =============================================================================
# SIES — tail the logs, without typing the long compose invocation.
#
#   scripts/logs.sh                      dev, everything, follow
#   scripts/logs.sh sies-backend         dev, one service
#   scripts/logs.sh -p                   production, everything
#   scripts/logs.sh -p sies-backend      production, one service
#   scripts/logs.sh -p be                the same — see the aliases below
#   scripts/logs.sh -n 500 -p be         last 500 lines
#   scripts/logs.sh --no-follow -p be    print and exit (for piping to grep)
#   scripts/logs.sh -p --errors          only lines that look like problems
#
# Aliases, because nobody wants to type sies-celery-worker at 2 a.m.:
#   be/backend · fe/admin/spa · db · redis · worker/celery · beat · traefik/proxy
#
# Read-only. Nothing here changes anything.
# =============================================================================
set -euo pipefail

PROD=0; FOLLOW=1; TAIL=200; ERRORS=0; SERVICE=""

while [ $# -gt 0 ]; do
  case "$1" in
    -p|--prod)     PROD=1; shift ;;
    -d|--dev)      PROD=0; shift ;;
    -n|--tail)     TAIL="$2"; shift 2 ;;
    --no-follow)   FOLLOW=0; shift ;;
    --errors)      ERRORS=1; shift ;;
    -h|--help)     sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*)            echo "Unknown option: $1  (try --help)" >&2; exit 1 ;;
    *)             SERVICE="$1"; shift ;;
  esac
done

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname -- "$SCRIPT_DIR")"
cd -- "$PROJECT_ROOT" || { echo "cannot enter ${PROJECT_ROOT}" >&2; exit 1; }

if [ "$PROD" = 1 ]; then
  COMPOSE_FILE="docker-compose.prod.yml"; ENV_FILE=".env.production"
else
  COMPOSE_FILE="docker-compose.dev.yml";  ENV_FILE=".env.development"
fi
[ -f "$ENV_FILE" ] || { echo "$ENV_FILE not found — wrong environment? (-p for production)" >&2; exit 1; }

# Compose service names, which are the same in both files; only the container
# names differ. Resolving to the SERVICE name means one alias table works for
# dev and prod alike.
case "$SERVICE" in
  be|backend|api|django)   SERVICE="sies-backend" ;;
  fe|admin|spa|frontend)   SERVICE="sies-admin" ;;
  db|postgres|pg)          SERVICE="sies-db" ;;
  redis|cache)             SERVICE="sies-redis" ;;
  worker|celery)           SERVICE="sies-celery-worker" ;;
  beat|clock|cron)         SERVICE="sies-celery-beat" ;;
  proxy|traefik)           SERVICE="traefik" ;;
  "")                      ;;
  *)                       ;;   # anything else is passed through as-is
esac

ARGS=(logs "--tail=$TAIL")
# --errors implies a finite read: you cannot grep a stream that never ends and
# still get output when you expect it.
[ "$FOLLOW" = 1 ] && [ "$ERRORS" = 0 ] && ARGS+=(-f)
[ -n "$SERVICE" ] && ARGS+=("$SERVICE")

if [ "$ERRORS" = 1 ]; then
  # Deliberately broad. It is better to show three harmless lines than to filter
  # out the one that explains the outage — so this matches how problems are
  # spelled across Python tracebacks, gunicorn, Postgres and Traefik's JSON log.
  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "${ARGS[@]}" 2>&1 \
    | grep -iE 'error|exception|traceback|critical|fatal|failed|panic|"status":5[0-9][0-9]| 5[0-9][0-9] ' \
    || echo "(nothing matching in the last ${TAIL} lines — good)"
  exit 0
fi

exec docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "${ARGS[@]}"
