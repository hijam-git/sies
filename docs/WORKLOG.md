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
| 0b | Frontend shell — SPA ported from Awliaa myadmin | ⚠️ done — responsive verified by CSS audit, not rendered (F16) |
| 0c | Infra — Traefik, env, scripts, prod compose | ✅ done |
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

- [x] `backend/` — Dockerfile.dev, requirements.txt, manage.py
- [x] `backend/app/core/` — settings, celery, urls, wsgi/asgi, exception handler,
      middleware, base models/managers
- [x] `frontend/admin_dashboard/` — Vite + React 19 + Tailwind shell ported from
      Awliaa, `basename="/myadmin"`
- [x] `traefik/` — dynamic config (no static file; CLI flags, see F10)
- [x] `.env.development.example` + `.env.development`
- [x] Verified WITHOUT Docker: `manage.py check` clean, 16/16 core tests pass,
      `tsc -b` + eslint + `vite build` + 7/7 vitest clean.
- [ ] ⚠️ **Not verified: the Docker stack itself.** No Docker in this build
      environment — `scripts/dev.sh up` has never been executed. First run on a
      machine with Docker may surface compose/Dockerfile issues.

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

**F9 — the repo-root `.dockerignore` was inert.** Build contexts are
`./backend` and `./frontend/admin_dashboard`, so Docker never reads a root-level
one. Without a per-context file, `docker build ./backend` copies a local venv,
every `__pycache__` and any stray `.env` into the image — a fatter image and
secrets baked into a layer that survives deleting the file. Created
`backend/.dockerignore` and `frontend/admin_dashboard/.dockerignore`, each
saying in its header why it, and not the root file, is the one that applies.

**F10 — no `traefik.yml`, deliberately.** Traefik's static-config sources (CLI
flags, `traefik.yml`, env vars) are mutually exclusive. Both compose files
configure it with **CLI flags** — the only form Compose interpolates
`${ACME_EMAIL}` into — so a mounted `traefik.yml` would be silently ignored
while looking authoritative, which is worse than absent. `CLAUDE.md` §2's layout
listed those files; corrected to match reality, and `traefik/README.md` explains
the choice.

**F11 — backup retention is asymmetric, and correctly so.** With **no** remote
configured, old backups are still pruned: a full disk takes Postgres down, which
is worse than a gap in backup history. With a remote **configured but failing**,
nothing is pruned — those local copies are all that exist. Getting this the
obvious way round (always prune) means a week of silent copy failures ends with
the old backups gone and nothing anywhere saying so.

**F12 — three gaps in the permission catalogue, found by building the UI
against it.** All three are now fixed in `docs/02` §2.1, and Phase 1's backend
catalogue must match:

- **No resource covered Academics at all.** Classes, sections, subjects,
  sessions, streams and the routine had nothing to gate on, and were being
  mapped onto `settings` by inference. Added `academics` (view/create/update/
  delete), and added `academics.view` to the Teacher and Accountant presets.
- **`marks` had no `view` action**, so a literal `canView('marks')` would have
  hidden Marks entry from the only role that uses it. Added `marks.view` rather
  than special-casing the resource in `canView()` — a fallback that says "any
  action counts as view" is the kind of rule that later hides a real bug.
- **`settings` and `academics` overlapped** ("sessions, fee structures").
  Redescribed so each resource owns one thing.

**F13 — the nav in `docs/02` §6 listed Notices → SMS, which `docs/08` §7 puts in
V2.** The scope authority wins; the row is omitted rather than shipped as a
placeholder that never fills in. Both docs now agree.

**F14 — `overflow-x: clip`, not `hidden`, on `html, body`.** `hidden` creates a
scroll container, which silently breaks `position: sticky` on descendants —
and the attendance register's frozen first column (`CLAUDE.md` §7a) depends on
exactly that. Worth knowing before the register is built, because the symptom
would appear months later and look unrelated.

**F15 — the API error-code vocabulary is a contract, and nothing defined it.**
The SPA's `apiErrors.ts` maps codes to Bangla/English messages, so Phase 1's
exception handler must emit exactly these or the UI falls back to a generic
message: `invalid_phone` · `invalid_credentials` · `account_inactive` ·
`permission_denied` · `not_found` · `out_of_scope` · `fee_already_paid` ·
`attendance_window_closed` · `results_published` · `duplicate` ·
`protected_reference`. **Phase 1 task: make the backend emit these**, and treat
the list as shared — adding a code means adding its two translations.

**F16 — responsiveness is verified by CSS audit, not by rendering.** No browser
is available in this environment, so the four widths (360/390/768/1280) were
checked by confirming the emitted classes exist in the build, not by looking at
a page. **A rendered pass on a real device toolbar is still owed** before the UI
is called finished. Recorded rather than glossed over.

### Carried into Phase 1 as tasks

- **Make `AUTH_USER_MODEL` unconditional** once `accounts` exists (F5).
- **Write the management commands the deploy scripts already call:**
  `create_admin`, `seed_categories`, `seed_demo`, and `check_schema`.
  `pull_and_deploy.sh` detects their absence and skips — so until `check_schema`
  and `test_migration_safety.py` exist, **the two-release column rule is
  advisory only** and the rollback has no schema guard behind it.
- **Rollback restores images, never the database.** That is by design, but it
  means the column rule is the only thing standing between a rollback and a
  broken schema. Treat the guard as load-bearing, not as a nicety.

**F2 — Divergence from Awliaa, deliberate.** Awliaa stores roles as **Django
Groups**; SIES uses the `Role` model from `docs/03` §1. Reason: the catalogue is
served to the SPA, and a first-class `Role` row with a `permission_matrix` JSON
is directly serialisable, whereas Groups need a parallel lookup table that has to
be kept in step. This also removes Awliaa's `get_staff_role()` string-matching
against a hard-coded `['Manager', 'Staff']` list.
