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

# netcat-openbsd: the entrypoint waits for Postgres with it. That is all.
#
# No gettext: there are no .po files — the bilingual strings live in the SPA's
# lib/i18n and in `name`/`name_bn` columns, not in Django's catalogue.
# No compiler, no libpq, no postgresql-client. Every requirement ships a wheel
# (psycopg[binary] carries its own libpq), and every pg_dump in scripts/ runs
# inside the sies-db container — which is also what keeps the dump's client
# version equal to the server's. A client 17 here against server 16 writes
# `SET transaction_timeout` into the dump, and that dump does not restore.
RUN apt-get update && apt-get install -y --no-install-recommends \
        netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# The app runs unprivileged. uid 1000 so a file it writes into a volume has the
# same owner as the deploy user on a stock Ubuntu host.
RUN groupadd --gid 1000 app && useradd --uid 1000 --gid app --no-create-home app

COPY app/ /app/

# Created here, owned by app, BEFORE a volume is mounted over them: Docker seeds
# an empty named volume from the image directory, ownership included, so the
# media, static and beat volumes come up writable by the app user.
RUN mkdir -p /app/staticfiles /app/media /beat

# collectstatic needs settings to import, which needs a key. This one lives for
# the length of the RUN and never lands in the image's environment.
RUN DJANGO_SECRET_KEY=build-time-only-not-a-runtime-key DEBUG=0 ALLOWED_HOSTS=localhost \
        python manage.py collectstatic --noinput \
    && chown -R app:app /app/staticfiles /app/media /beat

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

USER app

EXPOSE 8000

CMD ["/usr/local/bin/docker-entrypoint.sh"]
