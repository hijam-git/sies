#!/bin/sh
# Production start: wait for the database, migrate, then serve.
#
# Migrations run here rather than in a separate one-shot container because this
# is a single-VPS deployment with one backend replica — there is no second
# instance to race with. If the stack ever runs more than one, this moves into
# its own deploy step and this script drops to just gunicorn.
set -e

if [ -n "$DB_HOST" ]; then
    echo "Waiting for Postgres at $DB_HOST:${DB_PORT:-5432} ..."
    while ! nc -z "$DB_HOST" "${DB_PORT:-5432}"; do
        sleep 0.2
    done
    echo "Postgres is up."
fi

echo "Applying migrations ..."
python manage.py migrate --noinput

# gthread rather than sync workers: report and export endpoints are I/O-bound
# waits on Postgres, and a sync worker blocked on one serves nothing else.
# max-requests recycles a worker periodically so a slow leak cannot grow without
# bound on a small VPS.
exec gunicorn core.wsgi:application \
    --bind 0.0.0.0:8000 \
    --worker-class gthread \
    --workers "${GUNICORN_WORKERS:-3}" \
    --threads "${GUNICORN_THREADS:-4}" \
    --timeout "${GUNICORN_TIMEOUT:-120}" \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --access-logfile - \
    --error-logfile -
