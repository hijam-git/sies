# Work Log

Running record of what was built, what was found, and what was decided while
building. Newest phase at the bottom. Findings that change the design are
promoted into `08-decisions.md`; this file is the trail.

**Reference project:** `~/awliaa`
**Design authority:** `05-scope-and-v1.md` (scope) → `08-decisions.md` (overrides)

---

## Status board

| Phase | Contents | State |
|-------|----------|-------|
| 0a | Backend skeleton — `core` app, middleware, base models | ✅ done, 16 tests green |
| 0b | Frontend shell — SPA ported from Awliaa myadmin | 🔄 in progress |
| 0c | Infra — Traefik, env, scripts, prod compose | 🔄 in progress |
| 1 | `accounts` + `branches` — phone auth, roles, ActivityLog, seeding | ⬜ |
| 2 | `academics` + `students` + `staff` + `forms` | ⬜ |
| 3 | `fees` + `finance` | ⬜ |
| 4 | `attendance` | ⬜ |
| 5 | `exams` | ⬜ |
| 6 | Reports + teacher dashboard | ⬜ |
| 7 | Deploy + hardening | ⬜ |

Legend: ⬜ not started · 🔄 in progress · ✅ done · ⚠️ done with a caveat noted

---

## Ground rules being followed

1. **`docs/05` and `docs/08` are the scope.** Nothing marked V2 gets built.
2. **No package added without a reason recorded here.**
3. **Money is `Decimal` everywhere.** No `FloatField`, no float arithmetic.
4. **Business logic in `services.py`, inside `transaction.atomic()`** — never in
   serializers, never in signals (signals fire during fixture loads).
5. **Constraints in `Meta.constraints`**, not in `save()`.
6. **Tests required** for: branch isolation (404 not 403), fee idempotency,
   money arithmetic, phone normalisation, permission fallback, receipt-number
   concurrency, teacher scoping.
7. **Everything runs in Docker Compose.** No host venv, no host `npm install`.
8. **Test the section just built, not the whole app** (`CLAUDE.md` §4a).
   Narrowest test that proves the change, small per-module factories,
   always `--keepdb`. Full suite only at a phase boundary.

---

## Phase 0 — Skeleton

**Goal:** `scripts/dev.sh up` → login screen at `localhost:5000/myadmin`.

### Tasks

- [ ] `backend/` — Dockerfile.dev, requirements.txt, manage.py
- [ ] `backend/app/core/` — settings, celery, urls, wsgi/asgi, exception handler,
      middleware, base models/managers
- [ ] `frontend/admin_dashboard/` — Vite + React 19 + Tailwind shell ported from
      Awliaa, `basename="/myadmin"`
- [ ] `traefik/` — dev static + dynamic config
- [ ] `.env.development.example` + `.env.development`
- [ ] Verify the stack boots and routes

### Findings

**F1 — Awliaa's permission resolution, read in full** (`accounts/permissions.py`
lines 160–340). Porting notes for Phase 1:

- `effective_permissions(user)`: a saved explicit list wins and is
  **intersected with `VALID_PERMISSIONS`** so a stale string from an older
  release silently drops instead of granting something that no longer exists.
  Empty list ⇒ role preset. Port this intersection — the docs described the
  fallback but not the filtering, and the filtering is the safer half.
- Awliaa returns **`set()`** (no permissions at all) when the staff profile is
  missing or inactive, deliberately: falling back to the role preset there
  would leave a dismissed employee with working access, because Django Groups
  outlive the profile. **SIES equivalent: `is_active=False` ⇒ empty set**, never
  the preset.
- `clean_permissions(raw)` validates a submitted list against the catalogue and
  drops anything unknown — so a typo in the API cannot become a permission that
  never matches. Port as-is.
- `POST_IS_AN_UPDATE`: on a **custom `@action`**, POST almost never means
  *create* — it means *update*. Awliaa keeps a second method→action map for
  custom actions, separate from the ViewSet default. Worth porting; it is the
  kind of detail that otherwise lets `fees.create` authorise a `collect` action.
- `OwnerOnlyDelete`: an extra permission class stacked *after* the resource
  check, so an irreversible row removal needs more than a ticked box. SIES
  analogue: destructive deletes on Student/Fee/Payment are principal-only, on
  top of the resource permission.

**F3 — `request.branch` must be lazy, and that has a sharp edge.**
The SPA authenticates with JWT, which DRF resolves *inside the view* — after
every middleware has run. Resolving the branch eagerly in middleware would read
`AnonymousUser` on every API request and scope the whole API to `None`. So
`request.branch` is a `SimpleLazyObject`.

The edge: **`request.branch is None` is always False** — the proxy is not the
thing. `core.middleware.get_branch(request)` unwraps it, `==` and attribute
access work normally. Promoted into `CLAUDE.md` §5 as a warning block because a
raw `is None` check would silently pass for everyone, forever, and nothing would
fail loudly.

**F4 — `manage.py` had to move to `backend/app/`.** `docker-compose.dev.yml`
bind-mounts `./backend/app:/app`, which *replaces* `/app`, so a `manage.py` at
`backend/` is invisible inside the container. `backend/manage.py` is now an
8-line shim that delegates. Compose was already written and is authoritative;
`CLAUDE.md` §2's layout diagram was wrong and has been corrected.

**F5 — `AUTH_USER_MODEL` is conditional, temporarily.** Naming `accounts.User`
before the app exists makes *every* management command fail, including `check`
and `migrate` — Phase 0 would be unrunnable and untestable. Settings uses
`importlib.util.find_spec('accounts')` and flips itself when Phase 1 lands.
**Phase 1 must make this unconditional** — a conditional auth user model is
fine as scaffolding and a liability in production. Added to the Phase 1 tasks.

**F6 — the pg_dump version-skew trap, found in Awliaa.** Awliaa's prod
Dockerfile installs `postgresql-client` **17** against a `postgres:16-alpine`
server. pg_dump 17 writes `SET transaction_timeout = 0` into the dump header,
which PG16 rejects on restore. **Backups keep succeeding**, so it surfaces only
on the day someone needs a restore. SIES uses the same 16-alpine server; pin the
client to 16, and `scripts/restore_backup.sh` should strip that line defensively.
Passed to the infra agent.

**F7 — `perform_create` for a platform admin with no `?branch=`** reached the FK
as the string `'ALL'` and failed as a database type error — a 500 for what is
really a missing parameter. Fixed to raise a DRF `ValidationError`: *"Choose an
institution before creating this. Add ?branch=&lt;id&gt; to the request."*

**F8 — `docs/02` §3.3 pointed cross-branch reads at a `reports/` app** that
`docs/05` §6 says is not created in V1. Corrected: platform-admin report views
live in each module in V1.

**F2 — Divergence from Awliaa, deliberate.** Awliaa stores roles as **Django
Groups**; SIES uses the `Role` model from `docs/03` §1. Reason: the catalogue is
served to the SPA, and a first-class `Role` row with a `permission_matrix` JSON
is directly serialisable, whereas Groups need a parallel lookup table that has to
be kept in step. This also removes Awliaa's `get_staff_role()` string-matching
against a hard-coded `['Manager', 'Staff']` list.
