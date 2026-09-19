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
| 0b | Frontend shell — SPA ported from Awliaa myadmin | ✅ done — responsiveness now verified by rendering, 48/48 (F16 closed) |
| 0c | Infra — Traefik, env, scripts, prod compose | ✅ done |
| 1 | `accounts` + `branches` | ✅ backend + screens |
| 2 | `academics` + `students` + `staff` | ✅ backend · screens 🔄 · `forms` 🔄 |
| 3 | `fees` + `finance` | 🔄 |
| 4 | `attendance` | 🔄 |
| 5 | `exams` | 🔄 |
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

---

## Phase 1 — accounts + branches

**Done.** 130 tests green. `manage.py check` clean, `makemigrations --check`
reports no drift, and an end-to-end smoke run creates an institution, logs in
through the `+880` phone form, and reads every Phase 1 endpoint.

### Findings

**F17 — circular migration dependency, and the way out.**
`accounts.User.branch → branches.Branch`, while `branches.Branch.head →
AUTH_USER_MODEL` **and** every `BranchScopedModel` carries `created_by` →
AUTH_USER_MODEL. So each app's initial migration genuinely needs the other.

Removing one FK by hand does not work — the model `Meta.indexes`,
`Meta.constraints` and the `ModelAdmin` all reference it, so `check` fails
before `makemigrations` runs.

**The fix: generate both apps in ONE `makemigrations accounts branches` run.**
Django detects the cycle itself and splits it — `accounts/0001` (no branch FK),
`branches/0001`, then `accounts/0002` adding the FKs back. Generating them one
app at a time produces an unresolvable graph.

**This will recur in Phase 2** (`students` ↔ `academics` through `Enrolment`) —
generate mutually-dependent apps together, and never hand-edit a dependency list
to break a cycle.

**F18 — an error-code contract breach, caught by building both halves.**
`core/exception_handlers.py` emitted `CODE_PROTECTED = 'protected'`, but the
SPA's `apiErrors.ts` (and F15) require **`protected_reference`**. Every `PROTECT`
breach reaching the boundary as an `IntegrityError` would have shown the user a
generic fallback instead of "this is still referenced by…". One-word fix, but it
only surfaced because the vocabulary was written down as a contract first.

**F19 — `core` cannot import `accounts`, so the permission resolver is named in
settings.** `SIES_PERMISSION_RESOLVER = 'accounts.permissions.permission_resolver'`,
imported lazily. Without it `core.permissions.HasPermission` — which *other* apps
use — silently falls back to core's default resolver, which knows neither the
inactive-user rule nor the stale-string filter (F1). It would not error; it would
just quietly apply weaker rules.

**F20 — `fresh_deploy.sh` called `createsuperuser`, which is the wrong command
here.** Django's own command knows nothing about `user_type` or `branch`, so the
first account would be a superuser with no platform-admin identity — passing
every permission check via the `is_superuser` shortcut while reading as the wrong
kind of user everywhere else. Switched to `create_admin`, which sets
`user_type=platform_admin` and `branch=NULL` and is idempotent. Also added
`seed_roles` **before** `seed_categories`: an account whose Role row does not
exist falls back to an empty permission set, so it logs in and sees nothing —
which reads as a broken deploy rather than a missing seed.

**F21 — `docs/02` §2.2 said "Nine presets" and listed nine, but §1 listed
Platform Accountant as an actor with no preset at all.** Now ten, with
Platform Accountant defined as cross-institution but money-only.

**F22 — verification is on SQLite, via a scratchpad settings shim.**
`core/settings.py` is Postgres-only by design and there is no Postgres in this
build environment. Model logic, permissions, services, serialisers, views and
branch scoping are genuinely exercised. **Not exercised:** `CheckConstraint` SQL
(including `user_platform_admin_has_no_branch`), the named `Meta.indexes`,
`SELECT … FOR UPDATE`, and column-length truncation. Those stay unverified until
the stack runs on Postgres.

### Verified in the smoke run

| Check | Result |
|---|---|
| `create_branch()` seeds streams | `hifz` · `qaumi` · `general` for a madrasah |
| Seeding is idempotent | second run creates 0 |
| Platform admin has `branch=None` | yes |
| Login with `+8801711111111` | 200 — normalisation works end to end |
| Permissions returned to the SPA | 57 entries |
| Permission catalogue | 19 resources in doc order, 10 presets |
| Wrong password | 401, code `invalid_credentials` (F15 contract) |
| `login` + `login_failed` logged | 2 rows in ActivityLog |

---

---

## Phase 2 — academics · students · staff · forms

### Findings

**F23 — two counter models arrived at once, and only one may ship.**
Parallel agents each invented a sequence table: `staff.NumberSequence`,
branch-scoped `(branch, kind, scope)`, and `students.NumberSequence`, global with
`next_value(scope)`.

**Keep `staff.NumberSequence`.** It sits lower in the dependency chain
(`staff ← academics ← students`), and it is branch-scoped, which is the
requirement — receipt, admission and voucher numbers are *per institution*
(`CLAUDE.md` §4.4). A global counter would make two institutions share one
sequence, so Dhaka issuing receipt 412 would push Chittagong to 413 and neither
institution's books would run 1..n. `students` is rewritten onto it.

**F24 — `NumberSequence` is a real table that `docs/03` never listed.**
`CLAUDE.md` §4.4 requires per-branch gapless numbers issued under
`SELECT … FOR UPDATE`, which needs a counter row to lock — but no table for it
appears in the database design. Added to `docs/03` §5. **V1 is 30 tables.**

**F25 — `admission_number` is per *enrolment*, not per person, and that is
correct.** `docs/03` §3 says gapless per branch+session, so `promote_enrolment()`
issues a **new** number each session rather than carrying the old one forward.
The permanent per-person identifier is `Student.student_id` (`SIES-000123`),
which never changes and is never reused. This is the D-level distinction from
`docs/02` §4.2 working as designed: identity is stable, enrolment is not.

**F26 — migration order for Phase 2.** `academics ↔ students` are mutually
dependent through `Enrolment.student`, exactly as F17 predicted. Generate
`staff academics students` in **one** `makemigrations` run, and put them in
`_SIES_APPS` in dependency order: `staff` → `academics` → `students`.
`settings.py` still lists `staff` as Phase 3; that is wrong and must move.

**F27 — `unique_together` over nullable FKs enforces nothing. Twice now.**
`docs/03` §6 specified
`unique_together (branch, date, person_type, student, teacher, employee)` for
"one attendance row per person per day". On Postgres **NULLs compare as
distinct**, so two rows for the same student — both with `teacher` and
`employee` NULL — never collide, and a student could be marked twice on the same
day with nothing to stop it.

The real enforcement is **three partial unique constraints**, one per person
type, each with `condition=Q(<fk>__isnull=False)`. `ClassAttendance` has the same
hole through its nullable `section`, and takes the same fix.

**This is the second time the same trap has appeared** — `NumberSequence`
(F23/F24) needed exactly this treatment for its nullable `branch`. Treat any
unique constraint containing a nullable column as wrong until proven otherwise;
it almost never does what it looks like it does.

The agent also folded `person_type` INTO the check constraint, so the
discriminator can never disagree with the FK that is actually set. That is
better than what the docs asked for.

**F28 — two docs contradicted D3 and D5 and have been corrected.**
`docs/02` §4.4 still read *"corrections are a new row plus an audit entry, never
an in-place edit"* — the exact opposite of D3. `docs/03` §6 still described "two
nullable FKs" after D5 made it three. Both fixed, and §4.4 now says where the
history actually lives: not in the attendance table, but in the `ActivityLog`
entry, which carries before and after (D8).

**F30 — `NumberSequence.Kind` was missing three kinds.** `form`, `receipt` and
`voucher` counters are all needed and none were declared. Choices are not
DB-enforced, so the counters worked with literal strings — only the admin label
was missing — but a closed enum that quietly does not close is worse than no
enum. All three added.

**F31 — `Mark.grade` / `grade_point` are columns nothing can write.**
`docs/03` §9 lists them as "filled at publish from the grade scale", but
`GradeScale` is V2 (`05` §5.4). Omitted from the model; V1 computes grades on
read, and `publish_exam`'s docstring names the exact slot where the stored
`Result` lands when the grade scale arrives.

**F32 — `branch.head_title` is a placeholder with no column, and stays that
way.** `docs/07` §4 lists it, and the honest implementation derives it from
`institution_type` — মুহতামিম for a madrasah, প্রধান শিক্ষক for a school, অধ্যক্ষ
for a college — rather than adding a field an admin would have to fill in
correctly for the letterhead to read right.

**F33 — blank forms issue no number.** A madrasah prints a stack of blank
admission forms at admission season. Allocating a gapless `form_no` for each
would burn the series on paper that may never be filled in, so blank mode writes
no `PrintedForm` and takes no number. Only a filled form is a record.

**F29 — `branches.seeding` breaks `create_branch()` while `fees` is uninstalled.**
The plug-in point imports `fees.models` inside the function, so `manage.py check`
stays clean and the failure only appears at call time —
`RuntimeError: Model class fees.models.FeeCategory doesn't declare an explicit
app_label`. A phased build will hit this every time an app is written before it
is wired, so seeding must **skip a stage whose app is not installed and log
that it did**, rather than raising. Fixed at integration.

---

### Carried into Phase 1 as tasks *(from Phase 0 — now done)*

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

---

## Handover pass — closing what was owed

**F34 — a placeholder outlived the feature it stood in for.** Settings kept a
`PhasePlaceholder` on "Fee categories" from when fees were unbuilt, and the
sidebar listed it as a sub-item. Fee heads have had a real screen since Phase 3,
at Fees → Fee setup, beside the invoices they price. So the tab and its nav
entry are removed rather than pointed at the same editor: two doors to one
screen is one door too many, and `CLAUDE.md` §2a calls a live-backend
placeholder a bug, not a pending task. A bookmark carrying the old
`?tab=fee-categories` falls back to the first tab — `useTabParam` already does
that for an unknown value — rather than rendering an empty panel; checked in a
browser, not assumed.

**F35 — `FeeSetupTab`'s own docstring had gone stale in the same way.** It still
said `default_amount` was missing from `FeeCategorySerializer` and that the
amount was therefore read-only. The field was added to the serializer when that
finding was fixed; the screen had already adapted on its own, because
`amountServed` reads the field's presence off the payload rather than off a
version flag. Only the prose was wrong, which is the kind of comment that sends
the next reader looking for a bug that is not there.

**F36 — a head priced on Fee setup raised no invoice.** The screen serves and
edits `FeeCategory.default_amount`, and nothing read it: `monthly_amount()`
priced a general head from `AcademicClass.monthly_fee` and returned None for a
hostel- or transport-only head unless the caller passed a figure, while
`raise_admission_fees()` returned early whenever `amounts` was empty. So an
accountant could type ৳300 against Transport Fee, watch it save, and the monthly
job would still count it unpriced — silently, because from the job's side
nothing was wrong. Both now fall back to the head's own price, in a stated
order: the run's own figure, then the class tuition (general heads only,
because it *is* the tuition), then `default_amount`. Priced nowhere still
raises nothing — a ৳0 invoice prints and looks paid, which is the failure this
rule exists to avoid. Nine tests in `fees/tests/test_pricing.py` pin the order,
including the stand-in enrolment `admit_student()`'s own tests rely on.

**Both items owed in `ACCEPTANCE.md` §5 are now done by running them.**
Responsiveness is verified by rendering twelve screens at four widths — 48/48
clean — which closes F16. A backup was restored: `pg_dump -Fc` of the live dev
database into a scratch database, every table compared (students 144, invoices
227, payments 57, marks 96, all equal) and the money still balancing in the copy
(receipts ৳85,500 = posted income ৳85,500). Server and client are both
PostgreSQL 16.11, so F6's version-skew trap is not present here.
