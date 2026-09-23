# SIES — Deployment

How this system is run: locally, on a new server, and every week after that.

---

## Architecture

```
                            Internet
                               │
                        ┌──────▼───────┐
                        │   Traefik    │   80 → 443, Let's Encrypt
                        │  THE ONLY    │   the only published port
                        │ EXPOSED PORT │
                        └───┬──────┬───┘
              priority 100  │      │  priority 50, prefix stripped
        /api /admin /static /media │  /myadmin   (and / → /myadmin/)
                            │      │
                  ┌─────────▼──┐ ┌─▼──────────────────┐
                  │sies-backend│ │ sies-admin         │
                  │Django+DRF  │ │ React SPA /myadmin │
                  │ gunicorn   │ │ serve -s dist      │
                  └──┬──────┬──┘ └────────────────────┘
                     │      │
          ┌──────────▼─┐ ┌──▼────────┐
          │ sies-db    │ │sies-redis │
          │ Postgres 16│ │broker only│
          └──────▲─────┘ └─────▲─────┘
                 │             │
      ┌──────────┴─────────────┴───────────┐
      │ sies-celery-worker  │ sies-celery-beat │
      │ fees, reports, PDFs │ the clock         │
      └─────────────────────┴───────────────────┘
```

Seven containers. That is the whole production footprint.

| Environment | URL | Compose file | Env file |
|---|---|---|---|
| **dev** | `http://localhost:5000/myadmin` | `docker-compose.dev.yml` | `.env.development` |
| **prod** | `https://<DOMAIN>/myadmin` | `docker-compose.prod.yml` | `.env.production` |

Both environments run their own Traefik. There is no shared proxy and no
staging tier in V1 — one institution, one server.

---

## Quick start

### Development

```bash
scripts/dev.sh up
```

That is the whole thing. It copies `.env.development.example` into place if the
env file is missing, builds, starts, and waits for `/api/health/`.

| URL | Serves |
|---|---|
| `http://localhost:5000/myadmin` | Admin SPA |
| `http://localhost:5000/api/` | DRF, browsable in dev |
| `http://localhost:5000/admin/` | Django admin |
| `http://localhost:8081` | Traefik dashboard |

Backend (8000), SPA (5173), Postgres and Redis publish nothing. Reaching them
means going through Traefik — which keeps dev honest about the routing that
production also has to do.

```bash
scripts/dev.sh logs sies-backend    scripts/dev.sh migrate
scripts/dev.sh shell                scripts/dev.sh test
scripts/dev.sh reset                # DESTROYS the dev database, then re-seeds
```

### Production, on a server that is already set up

```bash
sudo -u sies /opt/sies/scripts/pull_and_deploy.sh
```

---

## First-time server setup

### 1. Bootstrap the box

Copy one file to a bare Ubuntu server and run it:

```bash
scp scripts/bootstrap.sh root@<server-ip>:/root/
ssh root@<server-ip> 'bash /root/bootstrap.sh --audit'   # see what it would do
ssh root@<server-ip> 'bash /root/bootstrap.sh'           # do it
```

It installs Docker and the compose plugin, sets the timezone to Asia/Dhaka,
enables ufw with 22/80/443 and nothing else, installs fail2ban and
unattended-upgrades, creates the swapfile, creates the `sies` deploy user, and
clones the repository as that user.

For a private repo over SSH it generates a deploy key, prints it, and exits 2
asking you to paste it into GitHub → Settings → Deploy keys (read-only). Run it
again afterwards.

### 2. Fill in the secrets

```bash
sudo -u sies cp /opt/sies/.env.production.example /opt/sies/.env.production
sudo -u sies nano /opt/sies/.env.production
sudo chmod 600 /opt/sies/.env.production
```

Every variable is documented in the file. The ones that must change:

| Variable | How |
|---|---|
| `DOMAIN` | your hostname; its A record must already point at this server |
| `DJANGO_SECRET_KEY` | `python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'` |
| `DB_PASSWORD` | `openssl rand -base64 32` |
| `ACME_EMAIL` | a mailbox somebody reads |
| `TRAEFIK_DASHBOARD_AUTH` | `htpasswd -nbB admin 'pw' \| sed -e 's/\$/\$\$/g'` |
| `BACKUP_REMOTE` | an off-box rsync destination — see the backups section |

`fresh_deploy.sh` refuses to run while any `CHANGE_ME` remains, so a half-filled
file fails before the build rather than during it.

Do the same for `traefik/traefik.env` (copy from `traefik.env.example`) if you
want to be able to start Traefik on its own during a certificate problem.

### 3. First deploy

```bash
sudo -u sies /opt/sies/scripts/fresh_deploy.sh
```

Builds, starts Postgres and Redis, migrates, collects static files, starts
everything, prompts for the first superuser (phone + password — there is no
email field), seeds default categories, and health-checks.

### 4. Backups — the same day, not later

```bash
sudo -u sies /opt/sies/scripts/setup_backup_cron.sh
sudo -u sies /opt/sies/scripts/auto_backup.sh          # prove it works now
sudo -u sies /opt/sies/scripts/restore_backup.sh --dry-run
```

---

## The routine deploy

```bash
sudo -u sies /opt/sies/scripts/pull_and_deploy.sh
```

| Step | | What happens if it fails |
|---:|---|---|
| 1 | pre-flight: env, compose config, disk | aborts, nothing touched |
| 2 | tag current images as `:rollback` | warns; rollback unavailable this run |
| 3 | `git pull` (re-execs itself if the pull changed this script) | aborts |
| 4 | pre-deploy `pg_dump -Fc` | aborts — no migration without a backup |
| 5 | build images | aborts, old images still running |
| 6 | **migrate on the new image, before any swap** | aborts, old release still serving |
| 6b | `manage.py check_schema` — **not built yet; the script skips it** | — |
| 7 | collectstatic | **rolls back** |
| 8 | restart: workers → backend → SPA, each proven healthy | **rolls back** |
| 9 | verify over HTTPS as a browser sees it | **rolls back** |
| 10 | drop the `:rollback` tags, prune dangling images | — |

**The contract: either the new release is running and answering, or the previous
one is.** The script never exits leaving the site down and quiet.

**What rollback restores: images. Not the database.** Migrations run before
anything is swapped, and `migrate` only moves forward — it cannot reverse a
migration whose file is not on the branch you rolled back to. That asymmetry is
the entire reason for the rule below.

Restarting a serving container is a short interruption, not a zero-downtime
swap: SIES runs one container per tier, so there is no second one to carry
traffic. The `retry@file` middleware absorbs the connection failures that occur
in the second or two while a container is being recreated — it only retries when
no response byte was received, so it cannot double-submit a fee payment.

---

## Database changes: never drop a column in the release that stops using it

A migration in the reference project dropped a column in the same release that
stopped reading it. That release deployed, then the code was rolled back.

**A rollback returns code. It cannot return a column.**

The live code went on selecting a column the table no longer had, and every
read answered 500 — and redeploying could not repair it, because `migrate` only
moves forward and cannot reverse a migration whose file is not on the branch
being deployed. The fix had to ship as a new forward migration.

So drops happen in two releases, never one:

| | |
|---|---|
| **Release 1** | Stop reading the field. Ship it. Let it settle. |
| **Release 2** | Drop the column. |

Between the two, the database has a column nothing reads — which is harmless,
and is the entire point. Now a rollback of either release is only ever code.

The same rule protects the restart in step 8 for a second reason: for a few
seconds the old and new containers can overlap on one database, and a column
dropped in that window breaks whichever one is still serving.

The rule applies to `RemoveField`, `DeleteModel`, `RenameField` and
`RenameModel` alike. A rename is a drop and an add wearing one name.

### The two guards that enforce it

> **Neither guard exists in SIES yet.** Both are described here as awliaa
> runs them and as they are meant to be built; until they are, the rule is
> enforced by review alone. `pull_and_deploy.sh` looks for `check_schema` and
> skips step 6b when it is missing.

**`core/tests/test_migration_safety.py`** — fails the test suite when a new
migration contains `RemoveField`, `DeleteModel`, `RenameField` or `RenameModel`.
When release 1 has genuinely already shipped, acknowledge it in the migration
file itself:

```python
# SAFE-DESTRUCTIVE: `is_active` stopped being read in the release of
# 2026-09-04; this drops the column one release later.
```

The test also holds a **baseline** of the files that already contained a drop
when the guard was written. That list may only ever shrink — a new destructive
migration gets the marker comment, where a reviewer will read it, not a new
baseline entry.

**`manage.py check_schema`** — compares every model's columns against
`information_schema` and exits 1 if the code selects a column the database has
not got. `scripts/pull_and_deploy.sh` runs it as step 6b, straight after
`migrate` and before any container is restarted, so a mismatch aborts the deploy
with the old containers still serving. Extra columns the code no longer uses are
reported but never fail — that is the normal, correct state between the two
halves of a drop.

Run it by hand any time:

```bash
docker exec sies-backend python manage.py check_schema
```

---

## A backup you have never restored is not a backup

`scripts/auto_backup.sh` writes a `pg_dump -Fc` archive **and** a tarball of the
media volume. Both are needed: student photos, guardian documents and generated
receipts live on the volume, not in the database, so a database-only restore
leaves every student record pointing at a file that is not there.

The reason to actually *test* restores, rather than trusting a green cron log:

> The reference project's production image installed `postgresql-client` **17**
> while running a **`postgres:16`** server. pg_dump 17 writes
> `SET transaction_timeout = 0;` into the dump header, and PostgreSQL 16 rejects
> that statement on restore. **The backups kept succeeding.** Nothing failed,
> nothing warned. It would have surfaced on the day someone needed a restore —
> the worst possible day to discover the backups do not restore.

Three defences, all already in place:

1. **`auto_backup.sh` refuses to write a dump when the client and server majors
   differ.** It reads `pg_dump --version` and `SHOW server_version` and aborts
   loudly rather than producing a file that looks fine and is not.
2. **We dump with the server's own client**, by exec-ing into the database
   container. If you ever install `postgresql-client` on the host or in the
   backend image, **pin it to 16** to match `postgres:16-alpine`. An unpinned
   client tracks the distro and re-arms this trap on some future `apt upgrade`.
3. **`restore_backup.sh` strips `SET transaction_timeout = 0;`** from plain-SQL
   dumps on the way in. That `sed` looks like cruft; it is the difference
   between a restore and an outage. Custom-format dumps (what we write) do not
   need it — `pg_restore` regenerates statements for the target server, which is
   one of the reasons the format was chosen.

### The schedule

`setup_backup_cron.sh` installs two entries, not one:

```
02:30 nightly    auto_backup.sh --quiet
03:30 Sundays    restore_backup.sh --dry-run
```

The Sunday entry reads the newest archive with `pg_restore --list`, checks the
media tarball alongside it, and changes nothing. It is what turns "the cron says
OK" into evidence. `health_check.sh` fails when the newest backup is more than
48 hours old.

### Restoring for real

```bash
scripts/restore_backup.sh --list
scripts/restore_backup.sh --dry-run --file backups/daily/sies_db_20260910_023000.dump
scripts/restore_backup.sh --file backups/daily/sies_db_20260910_023000.dump \
  --confirm RESTORE-SIES-PRODUCTION
```

A real restore drops and recreates the database. It requires the exact
confirmation token — which cannot be produced by an up-arrow — and it dumps the
current database to `backups/pre_restore_*.dump` before touching anything.

### Off-box

`BACKUP_REMOTE` in `.env.production` is an rsync destination. **Set it.** A
backup on the same disk as the database survives a bad migration but not a dead
server, and the dead server is the case backups exist for. With it unset,
`auto_backup.sh` exits non-zero every night and says so in the cron mail — that
noise is deliberate.

---

## Traefik

Full detail in `traefik/README.md`. The short version:

| Priority | Path | Goes to |
|---:|---|---|
| 100 | `/api`, `/admin`, `/static`, `/media` | `sies-backend` |
| 50 | `/myadmin`, **prefix stripped** | `sies-admin` |
| 1 | `/` exactly | redirect to `/myadmin/` |

Anything else is Traefik's own 404.

**The strip is load-bearing.** Vite builds with base `/myadmin/`, so the page
asks for `/myadmin/assets/index-<hash>.js`, but `serve` has `assets/` at the
root of `dist/`. Unstripped, the request misses, `serve -s` answers with
`index.html`, and the browser refuses HTML as a script — a blank dashboard with
a MIME-type error in the console. Development never shows it, because Vite's
dev server understands `base` itself.

`/static` is served by whitenoise inside gunicorn. `/media` is presigned R2
links when R2 is configured; without R2, Django serves the media volume itself
(`core/media.py`) — except `documents/`, which only ever leaves through the
authenticated download.

**Adding a backend path prefix means editing the priority-100 rule.** A new
Django URL alone is not enough.

```bash
# dashboard, from your laptop
ssh -L 8080:localhost:8080 sies@server     # then http://localhost:8080

# is it healthy?
curl -s http://127.0.0.1:8080/ping

# certificates
docker exec sies-traefik cat /letsencrypt/acme.json | grep -o '"main":"[^"]*"'

# apply a change to the command: block (dynamic/config.yml needs no restart)
docker compose -f docker-compose.prod.yml --env-file .env.production up -d traefik
```

Before the first real certificate, set `ACME_CA_SERVER` to Let's Encrypt's
staging directory and confirm issuance works. Five duplicate certificates per
domain per week is the limit, and three failed attempts against a misconfigured
A record costs you the rest of the week.

---

## Common operations

```bash
# logs — aliases: be fe db redis worker beat traefik
scripts/logs.sh -p be
scripts/logs.sh -p --errors -n 500
scripts/logs.sh be                       # dev

# health, exits non-zero for cron/monitoring
scripts/health_check.sh --prod

# a management command
docker exec -it sies-backend python manage.py <command>

# a shell in the database
docker exec -it sies-db psql -U sies -d sies

# restart one service
docker compose -f docker-compose.prod.yml --env-file .env.production restart sies-backend

# what is running, and what image is it
docker compose -f docker-compose.prod.yml --env-file .env.production ps
```

### Roll back by hand

`pull_and_deploy.sh` rolls back automatically, but if you need to go back a
release after the fact:

```bash
docker images sies-backend                       # find the previous image ID
docker tag <image-id> sies-backend:latest
docker compose -f docker-compose.prod.yml --env-file .env.production \
  up -d --force-recreate sies-backend
```

Then read the migration rule above, because that is the half this does not
undo.

---

## Troubleshooting

| Symptom | Look at |
|---|---|
| `TRAEFIK DEFAULT CERT` in the browser | ACME never issued. `docker logs sies-traefik \| grep -i acme`. DNS or port 80. |
| `404` on `/api/...` | The backend router lost its priority, or the container is not on `sies-network`. |
| `502 Bad Gateway` | The backend is up but not answering. `scripts/health_check.sh --prod`. |
| `503` with a 0 ms upstream | The routing pool is empty. Zero milliseconds is the signature — a slow backend takes time, an absent one takes none. |
| `400 Bad Request` on everything | `ALLOWED_HOSTS` does not contain `DOMAIN`. |
| Blank dashboard, MIME-type error in the console | `/myadmin` is reaching `serve` unstripped — the `sies-admin-strip` middleware is missing from the router. |
| `config.js` 404 / `window.ENV` undefined | A `command:` on `sies-admin` replaced the entrypoint that writes it. |
| Django admin has no CSS | `collectstatic` did not run into the `static` volume, or whitenoise is missing from `MIDDLEWARE`. |
| Photos and logos 404 | No R2 and the `media` volume is not mounted on `sies-backend`, or R2 is set with a wrong key — check `docker logs sies-backend`. |
| Login succeeds then immediately logs out | The site is being reached over plain HTTP: secure cookies are on whenever `DEBUG=0`. |
| Nothing in the background runs | Beat and the worker are on different `CELERY_BROKER_URL` databases. Neither logs an error. |
| Fees generated twice | Two beat containers. Exactly one may exist. |
| `FATAL: sorry, too many clients` | `GUNICORN_WORKERS` × `DB_CONN_MAX_AGE` against Postgres' 100-connection limit. |
| Random 502s under load | The OOM killer. Check `free -h` and that swap is on (`scripts/setup_swap.sh`). |
| A shell script fails with `bad interpreter` | CRLF line endings. `.gitattributes` forces LF; check the file was not written by a Windows editor that ignored it. |
