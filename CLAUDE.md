# SIES — Agent Instructions

Instructions for any AI agent (Claude Code or otherwise) building this project.
**Read this file before writing a line of code.**

---

## 0. Read first, in this order

| Doc | Why |
|-----|-----|
| `docs/05-scope-and-v1.md` | **The scope authority.** What is in V1 and what waits. Wins over every other doc. |
| `docs/06-diagrams.md` | The whole system in 15 diagrams. Fastest way to orient. |
| `docs/01-architecture.md` | Services, request path, branch strategy |
| `docs/02-system-design.md` | RBAC, module workflows, API conventions, UI |
| `docs/03-database.md` | Every table, field by field |

**Do not build anything marked V2 in `05` §5.4.** If a task seems to need a V2
table, stop and ask — the answer is usually that V1 does it a simpler way, and
`05` §5.4 says how.

---

## 1. Hard rules — never violate without being told to

| Rule | Detail |
|------|--------|
| **No Next.js** | React 19 + Vite + React Router 7 SPA. No SSR, no Node in production beyond `serve -s dist`. |
| **No Google / OAuth login** | Login is **11-digit phone + password**, JWT. Nothing else. |
| **No DB caching layer** | Do **not** port Awliaa's `core/cache.py` or `storefront_cache.py`. Redis is a Celery broker and nothing more. |
| **No rate limiting** | Do **not** port `core/throttles.py`. No `DEFAULT_THROTTLE_*` in settings. |
| **Celery is required** | Beat + worker. See `docs/01` §4 for the job list. |
| **Traefik is the only exposed port** | Every other container is internal-only. |
| **Money is `Decimal`** | `DecimalField(max_digits=12, decimal_places=2)`. Never `FloatField`, never Python `float`, ever. |
| **Clients never send `branch`** | It is stamped server-side from `request.branch`. A `branch` in a POST body is ignored. |
| **SPA basename is `/myadmin`** | Copied from Awliaa (§3). Traefik routes `/myadmin` → SPA, `/api` → backend. |
| **Dev runs on port 5000** | Traefik's dev entrypoint. `http://localhost:5000/myadmin`. |

---

## 2. Project layout

```
sies/
├── CLAUDE.md                    ← this file
├── README.md
├── docs/                        00–06, the design
├── docker-compose.dev.yml       dev stack, port 5000
├── docker-compose.prod.yml      (phase 7)
├── .env.development(.example)
├── .env.production(.example)
├── traefik/
│   ├── traefik.dev.yml
│   ├── dynamic.dev.yml
│   └── traefik.yml              (prod)
├── scripts/                     §6
├── backend/
│   ├── Dockerfile / Dockerfile.dev
│   ├── manage.py
│   ├── requirements.txt
│   └── app/
│       ├── core/        settings, celery, urls, middleware, exception handlers
│       ├── accounts/    User, Role, permissions, phone auth
│       ├── branches/    Branch (= one institution), Stream, Session
│       ├── academics/   AcademicClass, Section, Subject, Enrolment
│       ├── students/    Student, Guardian, Admission, Document
│       ├── forms/       FormTemplate, Question, AdmissionAnswer, PrintedForm
│       ├── staff/       StaffProfile
│       ├── attendance/  DailyAttendance, ClassAttendance
│       ├── fees/        FeeCategory, Fee, Payment
│       ├── finance/     Income, Expense, categories
│       └── exams/       Exam, ExamSchedule, Mark
└── frontend/
    └── admin_dashboard/         React 19 + Vite + Tailwind (copied from Awliaa)
```

**App dependency direction is one-way** (`docs/06` §2). `core` ← everything;
`accounts`/`branches` ← everything else; `fees` → `finance` and never back;
report code reads from all and is imported by none. A circular import between
apps is a design error, not something to work around.

`notifications/` and `reports/` are **not created in V1**. Report screens live
in each module.

---

## 3. What to copy from Awliaa — `~/awliaa`

The reference project is a working Django + DRF + React SaaS. Copy from it
aggressively; it is why this project can be built fast.

### 3.1 Frontend — copy nearly verbatim

From `~/awliaa/frontend/admin_dashboard/`:

| Copy | Change |
|------|--------|
| `package.json`, `vite.config.ts`, `tsconfig*.json`, `tailwind.config.js`, `postcss.config.js`, `eslint.config.js` | Rename the package; drop `@tiptap/*` unless a rich-text field is needed |
| `Dockerfile`, `Dockerfile.dev`, `serve.json` | Port numbers only |
| `src/App.tsx` | **Keep `<BrowserRouter basename="/myadmin">`.** Replace the route table |
| `src/lib/api.ts` | Keep the `window.ENV.API_URL` runtime-config pattern exactly. Replace the interfaces |
| `src/lib/auth-context.tsx` | Change login from email to **phone** |
| `src/lib/permissions.ts` | Keep the shape; replace the resource list with `docs/02` §2.1 |
| `src/lib/i18n/` | Keep whole — bn/en toggle |
| `src/lib/format.ts`, `timezone.ts`, `apiErrors.ts`, `useTabParam.ts` | Keep whole |
| `src/lib/normalizeBdPhone.ts` + its test | **Keep — this is load-bearing for phone login** |
| `src/lib/printInvoice.ts` | Rename to `printReceipt.ts`, adapt to a fee receipt |
| `src/components/common/*` | Keep `BaseModal`, `FilterBar`, `Pagination`, `SectionCard`, `SortableTh`, `StatCard`, `PeriodFilter`, `ExportCsvButton`, `ImageUploadField`, `ArrayEditor`. Drop the rest |
| `src/pages/DashboardLayout.tsx` | **Keep the whole structure** — grouped sidebar, inline SVG `ICONS` map, `canView()` gating, `NavBadge`, language toggle. Replace nav items with `docs/02` §6 |
| `src/pages/LoginPage.tsx` | Keep layout; phone field instead of email; remove the Google button |
| `src/index.css`, `App.css`, Tailwind theme | Keep — this *is* "the myadmin design" |

**Do not copy:** `SaasAdminPage`, `SubscriptionPage`, `ChoosePlanPage`,
`ProductsPage`, `OrdersPage`, `CourierPage`, `PaymentSettingsPage`,
`WebsitesPage`, `AiWebsiteBuilderPage`, `LivePreviewPage`, `ChatbotPage`,
`BlogPage`, `ReviewsPage`, `MarketingPage`, `PromotionsPage`,
`GoogleCallbackPage`, `subscription-context.tsx`, `planFamilies.ts`,
`signupPlan.ts`, `storeUrl.ts`, `themeShots.ts`, `facebookSdk.ts`,
`components/{catalog,orders,payments,saasadmin,subscription,chatbot,blog,marketing,website,content}/`.

### 3.2 Backend — copy the patterns, not the domain

| Copy | From |
|------|------|
| Celery setup | `backend/app/core/celery.py` — near-verbatim, rename the app to `sies` |
| `CELERY_*` settings, `CELERY_BEAT_SCHEDULE`, `CELERY_TASK_ROUTES`, time limits | `core/settings.py` ~line 969–1060 |
| `SIMPLE_JWT` block, `AUTH_USER_MODEL` pattern | `core/settings.py` ~line 611–626 |
| Exception handler | `core/exception_handlers.py` — one error shape for the whole API |
| **Permission system** | `accounts/permissions.py` — `PERMISSION_CATALOG`, `VALID_PERMISSIONS`, `flatten()`, `ROLE_PERMISSIONS`, the preset-fallback rule. **The single most valuable thing to copy.** Replace the resource list with `docs/02` §2.1 |
| Phone normalisation | `accounts/phone_verification.py` / `identity.py` — the BD phone canonicalisation |
| `Dockerfile`, `Dockerfile.dev`, `requirements.txt` | `backend/` — strip storefront-only packages |
| Test runner + `CELERY_TASK_ALWAYS_EAGER` under test | `core/test_runner.py`, `settings.py:846` |

**Do not copy:** `core/cache.py`, `core/storefront_cache.py`, `core/throttles.py`,
`core/cloudflare*.py`, `core/r2_privacy.py`, `accounts/google_auth_views.py`,
`accounts/oauth_service.py`, and the apps `catalog`, `order`, `payments`,
`subscriptions`, `dokan`, `theme`, `chatbot`, `blog`, `reviews`, `calls`.

### 3.3 Infra — copy and adapt

`~/awliaa/traefik/` (whole dir), `docker-compose.dev.yml` as the template for
ours, `scripts/*.sh` (§6), `DEPLOY.md` and `NEW_SERVER_SETUP.md` as the shape
for ours.

### 3.4 Also worth lifting

- **The "never drop a column in the release that stops using it" rule** and its
  two enforcement guards — `DEPLOY.md` §"Database changes". Adopt it as-is; it
  is what makes rolling deploys safe.
- `scripts/setup_swap.sh` — a small VPS running Postgres + Redis + two Node
  builds will OOM without swap.
- `scripts/auto_backup.sh` + `setup_backup_cron.sh` — this system holds fee
  records; backups are not optional.
- The `.env.*.example` discipline — every real env var documented with a
  comment, committed as `.example`, never the real file.

---

## 4. Django model conventions

*(This section answers "is the structure OK for Django model design?" — yes,
with these conventions applied.)*

### 4.1 Two abstract bases, and every model uses one

```python
# core/models.py
class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name='+')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name='+')
    class Meta:
        abstract = True


class BranchScopedModel(BaseModel):
    branch = models.ForeignKey('branches.Branch', on_delete=models.PROTECT,
                               related_name='%(class)s_set')
    objects = BranchScopedManager()
    class Meta:
        abstract = True
```

**A model is either `BranchScopedModel` or explicitly global.** The global list
is closed: `Branch`, `User`, `Role`. A new model that is neither is a review
failure (`docs/01` §5.3).

### 4.2 Rules

- **`related_name` is always explicit.** Never rely on `foo_set`.
- **`on_delete` is a decision, never a default:**
  - `PROTECT` — anything a financial or academic record points at (Branch,
    Session, FeeCategory, Student from Payment). Deleting it must fail loudly.
  - `CASCADE` — only for rows that are meaningless alone (`StudentGuardian`,
    `ExamSchedule` under `Exam`).
  - `SET_NULL` — audit references (`created_by`, `taken_by`, `collected_by`).
    A deleted user must not delete their attendance records.
- **Choices are `TextChoices` classes**, never bare tuples. They get referenced
  from serializers, tasks and tests.
- **Constraints live in `Meta.constraints`**, not in `save()`. Use
  `UniqueConstraint` and `CheckConstraint` — the database is the last line, and
  application code is not a constraint. The required set is in `docs/03` §13.
- **Indexes are declared**, not hoped for. At minimum the ones in `docs/03`.
- **`Meta.ordering` on every model** — unordered pagination is nondeterministic.
- **Soft delete via `is_active`** on Student, Fee, Payment, Mark, Enrolment.
  Never a hard delete on a record with financial or academic history.
- **Bilingual fields** are `name` + `name_bn`, both on the model.
- **Derived values are properties or computed in a service**, except where
  `docs/03` says to store them (`Fee.payable`, `Fee.paid_amount`,
  `Result.*`) — those are stored deliberately, and the reason is written there.

### 4.3 Where logic lives

```
models.py       fields, constraints, tiny properties. No multi-step logic.
managers.py     queryset scoping and common filters
services.py     multi-step operations in transactions  ← business logic here
serializers.py  validation and shape. No writes beyond the obvious.
views.py        permission class, queryset, call the service. Thin.
tasks.py        Celery entry points. Thin wrappers over services.
signals.py      seeding only (branch → categories). Nothing else.
```

**Anything touching money or spanning two models goes in `services.py`, inside
`transaction.atomic()`.** Concretely: `admit_student()`, `collect_fee()`,
`generate_monthly_fees()`, `save_attendance_register()`, `publish_results()`.
Do not put these in a serializer's `create()`, and never in a signal — a signal
that moves money is a signal that fires twice during a fixture load.

### 4.4 Number sequences

Admission numbers, receipt numbers and voucher numbers are **per branch,
sequential, gapless, and human-quotable**. Generate them inside the transaction
with `SELECT … FOR UPDATE` on a per-branch counter row. **Never `max() + 1`**
— it double-issues under two concurrent counter clerks, which is precisely the
situation it will meet.

---

## 5. API conventions

- `/api/` prefix, versionless, DRF routers + `ModelViewSet`.
- Every branch-scoped viewset inherits `BranchScopedViewSet`, which filters in
  `get_queryset()` and stamps `branch` in `perform_create()`.
- Wrong-branch object returns **404, not 403** — 403 confirms it exists.
- Pagination on every list (page-number, 25 default). `?search=`, `?ordering=`
  and module filters via `django-filter`.
- One error shape for the entire API, from the copied exception handler.
- Self-service under `/api/me/`, filtered to `request.user`. It is a separate
  endpoint family, **not** a weakened staff permission.

---

## 6. Scripts — `scripts/`

Adapted from `~/awliaa/scripts/`. Every one is idempotent and safe to re-run.

| Script | Does |
|--------|------|
| `bootstrap.sh` | **Server onboarding.** Fresh Ubuntu → Docker, compose plugin, ufw (22/80/443 only), fail2ban, swap, timezone Asia/Dhaka, deploy user, directories. Run once per server. |
| `setup_swap.sh` | 2–4 GB swapfile. Called by `bootstrap.sh`; separate because existing servers need it too. |
| `fresh_deploy.sh` | First deploy on a new server: clone, check `.env`, build, migrate, `createsuperuser`, seed, start. |
| `pull_and_deploy.sh` | **The routine deploy.** `git pull` → build changed images → `migrate` → `collectstatic` → rolling restart → health check → **roll back on failure**. This is the one used weekly. |
| `dev.sh` | `up`, `down`, `logs`, `shell`, `dbshell`, `migrate`, `makemigrations`, `test`, `reset` against the dev stack. Saves typing long compose commands. |
| `seed_demo.sh` | One branch, one session, 3 classes, 30 students, 5 teachers, a month of attendance, fees raised and part-collected. **Build this in Phase 1** — every later phase is faster with real-shaped data. |
| `auto_backup.sh` | `pg_dump` + media tarball → timestamped, retention-pruned, off-box copy. |
| `setup_backup_cron.sh` | Installs the nightly cron for the above. |
| `restore_backup.sh` | The other half of a backup. Untested restores are not backups. |
| `health_check.sh` | Hits `/api/health/`, checks Postgres, Redis, worker heartbeat, disk. Exit non-zero for cron/monitoring. |
| `create_branch.sh` | Wraps the management command — creates a branch and its seeded categories. |
| `logs.sh` | Tail any service, or all, with sane defaults. |

Also add these **management commands** (`python manage.py …`):
`seed_categories`, `seed_demo`, `generate_monthly_fees` (manual trigger of the
beat task), `create_admin`, `import_students <csv>`.

`import_students` matters more than it looks — an institution with existing
students on paper or in Excel will otherwise spend days typing. Build it in
Phase 2.

---

## 7. Dev environment

```bash
scripts/dev.sh up
```

| URL | Serves |
|-----|--------|
| `http://localhost:5000/myadmin` | Admin SPA |
| `http://localhost:5000/api/` | DRF, browsable API in dev |
| `http://localhost:5000/admin/` | Django admin |
| `http://localhost:8081` | Traefik dashboard |

**Port 5000 is Traefik's dev entrypoint.** Backend (8000), SPA (3001), Postgres
and Redis are **not published to the host** — same as Awliaa's dev compose.
Reaching a service means going through Traefik, which keeps dev honest about
routing that production also has to do.

Postgres and Redis data live in named volumes; `scripts/dev.sh reset` drops and
re-seeds.

---

## 8. Working rules for the agent

1. **Read `docs/05` before starting any task.** If the task needs a V2 table,
   stop and ask.
2. **One phase at a time**, in the order of `docs/05` §8. Do not start Phase 3
   because Phase 2 is boring.
3. **Migrations:** one per logical change, named meaningfully. Never edit a
   migration that has run anywhere. Never drop a column in the same release that
   stops using it (§3.4).
4. **Tests are required for:** branch isolation (404 not 403), fee idempotency,
   money arithmetic, phone normalisation, permission fallback, and receipt
   number concurrency. Ordinary CRUD gets ordinary tests. See `docs/04` §2.

### 4a. Test the section you just built, not the whole app

**While building, run the narrowest test that proves the thing you just
changed.** A full-suite run after every edit wastes minutes per iteration and
tells you nothing extra, because the other ninety per cent of the suite was
already green when you started.

```bash
scripts/dev.sh test fees.tests.test_collect     # ← the normal case
scripts/dev.sh test fees                        # the module, before moving on
scripts/dev.sh test                             # ONLY at a phase boundary
```

The rules:

- **Per module, keep a small focused fixture** — one branch, one session, one
  class, three students, one teacher. Enough to exercise the module's real
  paths, small enough to build in milliseconds. Put it in
  `<app>/tests/factories.py`, not in a global fixture every app has to load.
- **`seed_demo` is for looking at the app by hand**, not for running tests
  against. Tests build their own data; a shared demo dataset that tests depend
  on becomes a thing nobody dares change.
- **Always `--keepdb`.** Recreating Postgres per run is the single largest cost.
- **`--parallel` only on the full run.** On a single module it costs more in
  worker startup than it saves.
- **Run the full suite at phase boundaries and before reporting a phase done** —
  that is the moment a cross-module regression can actually exist.
- If a narrow test needs the whole app seeded to pass, that is a design smell:
  the module is reaching into things it should not. Fix the coupling rather than
  widening the fixture.

Same principle for manual checks: verify one endpoint with `curl` or one screen
in the browser, not a click-through of the entire dashboard.
5. **Never invent a field.** If `docs/03` does not list it and it is needed, say
   so and update the doc in the same change. The docs and the models must not
   drift.
6. **Do not add a package** without saying why. This project's dependency list
   should stay short enough to read.
7. **Match the surrounding code.** Awliaa's comment style explains *why*, not
   *what* — follow it. A comment restating the line above it is noise.
8. **Bangla and English** on every user-facing string, through `lib/i18n`. Not
   retrofitted later.

### Definition of done for a module

- [ ] Models with `Meta` constraints and indexes from `docs/03`
- [ ] Migration applied cleanly on an empty **and** a seeded database
- [ ] Serializers, `BranchScopedViewSet`, permission class wired
- [ ] Business logic in `services.py`, in a transaction
- [ ] Branch-isolation test passes (404 for another branch's row)
- [ ] Registered in Django admin for debugging
- [ ] Frontend page, sidebar entry, `canView()` gate
- [ ] Both languages present
- [ ] `docs/03` updated if anything changed

---

## 9. Decisions — read `docs/08-decisions.md`

**Both formerly blocking questions are closed. Nothing blocks coding.**

The four decisions that override the earlier docs:

| | Decision |
|---|---|
| **D1** | **A branch is a whole institution** — school, madrasah or college — and SIES is the platform. Nothing may be hard-coded to one institution; `Branch.institution_type` selects what gets seeded. |
| **D2** | **`Category` = the study sector = `Stream`**, one field, a per-branch table (not fixed choices). `StudentCategory` is deleted. |
| **D3** | **Attendance corrections overwrite** the cell. No history in V1. |
| **D4** | **Students may log in optionally** by phone. `/api/me/` is in V1; guardian login stays V2. |

`docs/08` §7 lists the remaining assumptions — correct any that are wrong before
the phase that depends on it.
