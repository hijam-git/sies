# Traefik — routing for SIES

Traefik is the **only container that binds a host port** (CLAUDE.md §1). Backend,
SPA, Postgres and Redis publish nothing in either environment; the only way to
reach them is through Traefik on the `sies-network` bridge. That is the security
boundary — and it is also why dev is routed at all: a request in development
travels the same path it will travel in production.

```
                     ┌──────────────────────────────┐
  browser ─────────► │  Traefik                     │
                     │  dev :5000  ·  prod :80/:443 │
                     └───────┬──────────────┬───────┘
                             │              │
        /api /admin /static /media      /myadmin
              priority 100          priority 50 (prod: prefix stripped)
                             │              │
                   ┌─────────▼──────┐  ┌────▼──────────────────┐
                   │ sies-backend   │  │ sies-admin            │
                   │ Django + DRF   │  │ React SPA at /myadmin │
                   └────────────────┘  └───────────────────────┘
```

## The routing model

The priority number is what makes the routers work together: Traefik resolves
an overlap by priority, never by order in the file.

### Production (`docker-compose.prod.yml`)

| Priority | Path | Goes to | Why |
|---:|---|---|---|
| **100** | `/api`, `/admin`, `/static`, `/media` | `sies-backend` | Django owns the API, the Django admin, static files (whitenoise) and uploaded media. |
| **50** | `/myadmin`, prefix **stripped** | `sies-admin` | The built SPA. |
| **1** | `/` exactly | redirect → `/myadmin/` | The bare domain has nothing of its own. |

Anything else is Traefik's plain 404.

**Why the strip.** Vite builds with base `/myadmin/`, so the page requests
`/myadmin/assets/index-<hash>.js` and `/myadmin/config.js`, while `serve` has
`assets/` and `config.js` at the root of `dist/`. Forwarded unchanged, those
requests miss, `serve -s` answers every one of them with `index.html`, and the
browser refuses HTML as a script: a blank dashboard. An earlier version of this
file argued for no strip; it was written against the dev server, where the
problem cannot appear, and it was wrong for the built image. React Router's
`basename="/myadmin"` is unaffected — the browser's URL keeps the prefix; only
the path `serve` sees loses it. The `sies-admin-slash` middleware turns a bare
`/myadmin` into `/myadmin/` first, so the stripped path is never empty.

### Development (`docker-compose.dev.yml`)

The SPA router is a priority-1 catch-all, and nothing is stripped: the Vite
dev server serves under `base` itself. **The backend router must keep the
higher number** in both files — drop `priority=100` and the SPA quietly begins
answering `/api/...` with `index.html`, which surfaces as a JSON parse error in
the dashboard and looks for all the world like a backend bug.

**A new backend path prefix must be added to the priority-100 rule** in both
compose files. Adding a Django URL is not enough.

## Files in this directory

| File | Used by | Notes |
|---|---|---|
| `dynamic/config.yml` | production | Middlewares and TLS options. Watched: edits apply with no restart. |
| `traefik.env.example` | production | Template for `traefik.env`, which is gitignored. |
| `acme.json` | production | Certificates. Lives in the `traefik-acme` named volume, never in the repo. |

### Why there is no `traefik.yml`, `traefik.dev.yml` or `dynamic.dev.yml`

Traefik's three sources of **static** configuration — a config file, `TRAEFIK_*`
environment variables, and CLI flags — are *mutually exclusive*. Traefik takes
one and silently ignores the rest. Both of our compose files configure Traefik
with **CLI flags**, because flags are the only form Compose can interpolate
`${ACME_EMAIL}` and `${DOMAIN}` into; a YAML static file interpolates nothing.

A `traefik.yml` mounted alongside those flags would therefore be read by nobody
while looking authoritative. That is the worst kind of configuration file:
the first time someone edits it to fix an outage, nothing happens, and they
conclude the outage is somewhere else. So it does not exist. The static
configuration lives in `docker-compose.prod.yml` and `docker-compose.dev.yml`,
in full view, next to the labels it interacts with.

CLAUDE.md §2's file listing predates this decision; the routing behaviour it
describes is unchanged.

**Dynamic** configuration has no such exclusivity — the file provider and the
Docker provider coexist — which is why `dynamic/config.yml` is real and mounted.
Dev does not use it: dev has no TLS, no HSTS and nothing worth compressing, and
every dev route is expressible as a Docker label. Hence no `dynamic.dev.yml`.

## Production certificate flow

1. `web` (:80) redirects everything to `websecure` (:443), permanently.
2. `websecure` asks the `letsencrypt` resolver for a certificate.
3. The resolver uses the **HTTP-01 challenge** over the `web` entrypoint. The
   redirect in step 1 does not break this: Traefik answers
   `/.well-known/acme-challenge/` internally, before the redirect applies.
4. The certificate and the ACME account key are written to `${ACME_STORAGE}`
   inside the `traefik-acme` volume.

There is **no DNS-01 challenge and no Cloudflare token**, unlike Awliaa. SIES
serves one institution on one hostname, so it needs no wildcard certificate —
and HTTP-01 needs no third-party API credential that could leak.

**Before the first real issue,** point `ACME_CA_SERVER` at the staging directory
and confirm a certificate is produced. Let's Encrypt allows five duplicate
certificates per domain per week; three failed production attempts against a
misconfigured A record cost you the rest of the week.

## Dashboard

Bound to `127.0.0.1:8080` on the host, so it is unreachable from the internet
even if ufw were misconfigured — which matters, because Docker's published-port
iptables rules are consulted *before* ufw's and a `0.0.0.0` binding would sail
straight past the firewall. Reach it over SSH:

```bash
ssh -L 8080:localhost:8080 deploy@your-server   # then open http://localhost:8080
```

Basic auth (`TRAEFIK_DASHBOARD_AUTH`) is the second lock. In dev the dashboard is
on `http://localhost:8081` with no auth, which is fine: it is bound to your own
machine.

## Operations

```bash
# Is Traefik healthy?
curl -s http://127.0.0.1:8080/ping

# Which routers exist, and at what priority?
curl -s http://127.0.0.1:8080/api/http/routers | python3 -m json.tool

# Which servers are in the backend pool right now?
# (this is exactly what a rolling deploy waits on)
curl -s http://127.0.0.1:8080/api/http/services/sies-backend@docker | python3 -m json.tool

# Certificate inventory
docker compose -f docker-compose.prod.yml --env-file .env.production \
  exec traefik cat /letsencrypt/acme.json | grep -o '"main":"[^"]*"'

# Logs — the access log is JSON on stdout, rotated by Docker's json-file driver
./scripts/logs.sh -p traefik
```

Editing `dynamic/config.yml` needs no restart. Editing the `command:` block in
the compose file does:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d traefik
```

## Troubleshooting

| Symptom | Look at |
|---|---|
| Browser shows `TRAEFIK DEFAULT CERT` | ACME never issued. `docker logs sies-traefik \| grep -i acme`. Usually DNS is not pointing here, or port 80 is blocked upstream. |
| `404 page not found` on `/api/...` | The backend router lost its priority, the container is not on `sies-network`, or `traefik.enable=true` is missing. |
| `502 Bad Gateway` | The backend container is up but not answering yet. `./scripts/health_check.sh`. |
| `503` with a 0 ms upstream time | The pool is empty — every server was removed at once. Zero milliseconds is the signature: a slow backend takes time, an absent one takes none. `pull_and_deploy.sh` exists to prevent exactly this. |
| SPA loads but every API call 404s | You are getting the SPA's `index.html` fallback. Same cause as row 2. |
| Certificate renewal silently stopped | `acme.json` is not persisted, or its mode is not 600. Check the `traefik-acme` volume is still attached. |
