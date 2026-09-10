# SIES backend — production image.
#
# Same /app == backend/app layout as Dockerfile.dev, so a path that works in
# development works here. Nothing is bind-mounted in production; the code in
# the image is the code that runs.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# postgresql-client is here for pg_dump, which scripts/auto_backup.sh runs from
# this container. Debian trixie ships client 17 while the server is
# postgres:16-alpine — pg_dump 17 writes `SET transaction_timeout = 0` into the
# dump header and Postgres 16 rejects it, so such a dump does NOT restore with a
# plain `psql` pipe. awliaa hit exactly this and it stayed invisible until a
# restore was needed, because the backups kept succeeding.
# scripts/restore_backup.sh must strip that line. Remove this comment only when
# the two versions are made to match.
#
# netcat-openbsd: the entrypoint waits for Postgres with it.
# gettext: compilemessages runs at build time, below.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        postgresql-client \
        netcat-openbsd \
        gettext \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY app/ /app/

RUN mkdir -p /app/staticfiles /app/media

# collectstatic needs settings to import, which needs a key. This one lives for
# the length of the RUN and never lands in the image's environment.
RUN DJANGO_SECRET_KEY=build-time-only-not-a-runtime-key DEBUG=0 ALLOWED_HOSTS=localhost \
        python manage.py collectstatic --noinput

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000

CMD ["/usr/local/bin/docker-entrypoint.sh"]
