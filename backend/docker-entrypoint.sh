#!/bin/sh
# Production start: wait for the database, then serve.
#
# No `migrate` here. Migrations belong to the deploy scripts, which take a
# pg_dump first and run them once, before any container is swapped
# (scripts/pull_and_deploy.sh step 6, scripts/fresh_deploy.sh step 4). A
# migrate on every start would also run on a rollback, and on the restart
# Docker does after a crash — neither of which is the moment to change a schema.
set -e

if [ -n "$DB_HOST" ]; then
    echo "Waiting for Postgres at $DB_HOST:${DB_PORT:-5432} ..."
    while ! nc -z "$DB_HOST" "${DB_PORT:-5432}"; do
        sleep 0.2
    done
    echo "Postgres is up."
fi

# gthread rather than sync workers: report and export endpoints are I/O-bound
# waits on Postgres, and a sync worker blocked on one serves nothing else.
# max-requests recycles a worker periodically so a slow leak cannot grow without
# bound on a small VPS. Access log to stdout, where the json-file driver rotates
# it — without it a 502 has no request line to match against Traefik's log.
exec gunicorn core.wsgi:application \
    --bind 0.0.0.0:8000 \
    --worker-class gthread \
    --workers "${GUNICORN_WORKERS:-3}" \
    --threads "${GUNICORN_THREADS:-4}" \
    --timeout "${GUNICORN_TIMEOUT:-120}" \
    --graceful-timeout 30 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --access-logfile - \
    --error-logfile -
