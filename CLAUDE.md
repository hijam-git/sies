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
| **100% mobile responsive** | Every screen, no exceptions. See §7a — this is a hard requirement, not a polish pass. |

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
│   ├── dynamic/config.yml       middlewares (headers, retry, cache)
│   ├── traefik.env.example
│   └── README.md                routing model + why there is no traefik.yml
├── scripts/                     §6
├── backend/
│   ├── Dockerfile / Dockerfile.dev
│   ├── manage.py                shim → app/manage.py
│   ├── requirements.txt
│   └── app/                     ← bind-mounted to /app; the REAL manage.py lives here
│       ├── core/        settings, celery, urls, middleware, exception handlers
│       ├── accounts/    User, Role, ActivityLog, permissions, phone auth
│       ├── branches/    Branch (= one institution), Stream, Session
│       ├── academics/   AcademicClass, Section, Subject, Enrolment, Period, ClassRoutine
│       ├── students/    Student, Guardian, Admission, Document
│       ├── forms/       FormTemplate, Question, AdmissionAnswer, PrintedForm
│       ├── staff/       Teacher, Employee, TeacherQualification
│       ├── attendance/  DailyAttendance, ClassAttendance
│       ├── fees/        FeeCategory, Fee, Payment
│       ├── finance/     Income, Expense, categories
│       ├── exams/       Exam, ExamSchedule, Mark
│       ├── notifications/ NotificationTemplate, SmsMessage, gateways
│       │                  (result, admission and fee-received SMS)
│       └── conduct/     ReportTemplate, StudentReport, ReportAnswer —
│                        the নামাজ/আদব register. Its questions are
│                        `forms.Question`; there is no second bank
└── frontend/
    └── admin_dashboard/         React 19 + Vite + Tailwind (copied from Awliaa)
```

**App dependency direction is one-way** (`docs/06` §2). `core` ← everything;
`accounts`/`branches` ← everything else; `fees` → `finance` and never back;
report code reads from all and is imported by none. A circular import between
apps is a design error, not something to work around.

`reports/` is **not created in V1**. Report screens live
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
signals.py      Avoid. Nothing in V1 uses one — see below.
```

**Anything touching money or spanning two models goes in `services.py`, inside
`transaction.atomic()`.** Concretely: `admit_student()`, `collect_fee()`,
`generate_monthly_fees()`, `save_attendance_register()`, `publish_results()`.
Do not put these in a serializer's `create()`, and never in a signal — a signal
that moves money is a signal that fires twice during a fixture load.

**No signals in V1, including for seeding.** An earlier draft of this file said
seeding was the one legitimate use; that was wrong, and for its own stated
reason. `post_save` on `Branch` fires during fixture loads and test setup, so a
branch gets seeded twice and `seed_categories` then looks broken. Branch seeding
lives in `branches.services.create_branch()`, which is the only supported way to
create an institution. If you think you need a signal, you need a service.

### 4.4 Number sequences

Admission numbers, receipt numbers and voucher numbers are **per branch,
sequential, gapless, and human-quotable**. Generate them inside the transaction
with `SELECT … FOR UPDATE` on a per-branch counter row. **Never `max() + 1`**
— it double-issues under two concurrent counter clerks, which is precisely the
situation it will meet.

---

## 5. API conventions

> ### ⚠️ `request.branch` is lazy — use `get_branch(request)` for identity checks
>
> `BranchScopeMiddleware` attaches `request.branch` as a **`SimpleLazyObject`**,
> and it has to: the SPA authenticates with JWT, DRF resolves that *inside the
> view* — after every middleware has run — so resolving eagerly would read
> `AnonymousUser` on every API request and scope the entire API to `None`.
>
> The consequence you must remember:
>
> ```python
> request.branch is None            # ← ALWAYS False. The proxy is not the thing.
> get_branch(request) is None       # ← correct
>
> request.branch == ALL_BRANCHES    # ← fine, == unwraps
> branch.name                       # ← fine, attribute access unwraps
> ```
>
> `from core.middleware import get_branch, is_all_branches, ALL_BRANCHES`.
> `BranchScopedViewSet` already goes through `get_branch()`, so inheriting it
> means you never touch this. Write a raw `is None` check against
> `request.branch` and it silently passes, every time, for everyone.

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

## 7a. Mobile responsiveness — a hard requirement

**Every screen must work on a 360px-wide phone.** Not "degrade acceptably" —
*work*. This is not a polish pass at the end; a screen that is not responsive is
not finished.

The reason is concrete: **a teacher takes attendance on their phone.** They are
standing in front of a class, not sitting at a desk. The teacher's dashboard,
the class roster and the attendance screens are phone-first by nature, and an
accountant checking a student's dues at the counter is often on a phone too.

### Breakpoints

Tailwind defaults, mobile-first. Write the phone layout, then widen:

```
base   → 360–639px   phone
sm     → 640px       large phone / small tablet
md     → 768px       tablet
lg     → 1024px      laptop — the sidebar appears here
xl     → 1280px      desktop
```

Never write a `lg:`-first layout and patch the phone case afterwards; it always
leaves something broken.

### The rules

1. **The body never scrolls horizontally.** Any wide thing — a table, a grid, a
   code block, a diagram — scrolls inside its own `overflow-x-auto` container.
2. **Sidebar becomes a drawer** below `lg`. Hamburger in the header, slide-over
   panel, backdrop, closes on route change and on Escape. This is Awliaa's
   pattern; keep it.
3. **Tables become cards** below `md`, unless they are genuinely grid-shaped
   (§ below). A five-column table squeezed onto a phone is unreadable; the same
   row as a stacked card with labels is fine. Build one `<ResponsiveTable>` in
   `components/common/` and use it everywhere rather than solving this per page.
4. **Compact controls, still tappable.** The owner asked for small, modern
   buttons across the whole panel (2026-09-10), replacing the earlier 44px
   rule. Buttons are **36px on a phone, 32px from `sm`**, 13px text — take them
   from `components/common/styles.ts` (`btnPrimary`, `btnSecondary`,
   `btnDanger`, `btnRowAction`) or the `.tap` class, never a hand-written
   `min-h-[44px]`. Nothing interactive goes below 28px, and the attendance
   cells keep their own larger size: a teacher marks forty of them standing up.
5. **Forms are single-column on phone.** Two-column field grids collapse; no
   side-by-side inputs below `sm`.
6. **Modals are full-screen sheets on phone**, centred dialogs from `md` up.
   `BaseModal` handles this once, for everyone.
7. **No fixed pixel widths** on layout containers. No `min-width` that exceeds
   360px. Use `max-w-*`, flex and grid.
8. **Font size ≥ 16px on inputs** — anything smaller makes iOS Safari zoom on
   focus, which throws the layout.
9. **Bottom-safe padding** so a fixed action bar clears the phone's home
   indicator.

### The three hard screens, and how each solves it

These are grid-shaped and cannot become cards. Each needs a real answer, not a
scrollbar and a shrug.

**Attendance month register** (`docs/02` §4.4) — 31 columns of cells.
- **Freeze the first column** (student ID + name) with `position: sticky; left: 0`
  and let the day columns scroll horizontally.
- Below `md`, **default to a single-day view** — a vertical list of students for
  one date, with prev/next day arrows — and offer the full month grid behind a
  "grid view" toggle for anyone who wants to pinch and scroll. The single-day
  list is what a teacher actually wants on a phone anyway.
- Keep the day-header bulk action ("mark whole day present") reachable in both.

**Marks entry** — one class × one subject.
- Sticky student column, one input per row. This one is naturally narrow, so a
  vertical list works on phone with no separate mode.
- Numeric keypad: `inputMode="numeric"`.

**Teacher's today board** (`08` D7) — already a vertical list of period cards.
Phone-first by construction; just make sure the **Take attendance** button is
full-width and thumb-reachable on small screens.

### Printable forms are the one exception

`docs/07`'s admission form is fixed A4 by design — that is the point of it. On a
phone it renders inside a horizontally scrollable, pinch-zoomable preview
container, with a full-width **Print** button. The *page* stays A4; the *preview*
is responsive.

### 7b. Do not ask for something the system already knows

**Every picker on a screen is a decision the user has to make before they can
start.** Most of them have an obvious right answer, and defaulting to it removes
the decision entirely. This is what "simple and easy" actually means here — not
fewer features, fewer questions.

The rule, in order of preference:

1. **Default to what is true right now.** The current session, the current
   month, today, the period happening at this moment, the exam currently in
   marks entry. Never "the first row the API returned" — an alphabetical
   accident is not an answer.
2. **Default to the user's own scope.** A teacher's own class before any other
   class; their own subject before any other subject. They are almost always
   there about their own work.
3. **If there is exactly one option, do not render a picker at all.** Show what
   was chosen as plain text. A dropdown with one entry is a control that cannot
   do anything.
4. **Hide the pickers once a default has been applied**, behind a small
   "change" or "another …" control. The exceptions are real — covering a
   colleague, correcting last week — but they are exceptions, and they should
   not cost the common case four decisions.
5. **A date range defaults to this month**, not to empty. An empty range means
   "everything", which is never what someone opening a ledger wants to see
   first.

Worked example — `ClassAttendanceTab`: it asked for class, section, period and
subject before showing anything. It now opens on the live period from the
teacher's own day board with every picker hidden, and *another class* reveals
them. Four decisions became zero for the case that happens all day.

**Derive the default; do not write it into state with an effect.** An effect
costs a second render and then fights the user — once they choose for
themselves their choice has to win, and the flag guarding that becomes a state
machine nobody asked for. Let an explicit choice simply take precedence:

```ts
const classId = explicitChoice || theObviousDefault || firstAsLastResort;
```

### Verifying

Check at **360px** (small Android), **390px** (iPhone), **768px** (tablet) and
**1280px**. A screen is not done until all four are correct. Test with the
browser devtools device toolbar; do not assume Tailwind classes did the job.

---

## 8. Working rules for the agent

1. **Read `docs/05` before starting any task.** If the task needs a V2 table,
   stop and ask.
2. **One phase at a time**, in the order of `docs/05` §8. Do not start Phase 3
   because Phase 2 is boring.
2a. **A phase is not done until its SCREENS work.** Backend + migrations +
   tests is half a phase. If a platform admin cannot do the thing by clicking
   in `/myadmin`, the feature does not exist as far as the institution using it
   is concerned. Every phase ships: models → API → **screens** → seed data that
   demonstrates it. A nav entry still pointing at `PhasePlaceholder` when its
   backend is live is a bug, not a pending task.
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
5. **Commit when a section is done.** Not per file, not once per phase — one
   commit per coherent, working unit of work. See §8a.
6. **Never invent a field.** If `docs/03` does not list it and it is needed, say
   so and update the doc in the same change. The docs and the models must not
   drift.
7. **Do not add a package** without saying why. This project's dependency list
   should stay short enough to read.
8. **Match the surrounding code.** Awliaa's comment style explains *why*, not
   *what* — follow it. A comment restating the line above it is noise.
9. **Bangla and English** on every user-facing string, through `lib/i18n`. Not
   retrofitted later.

### 8a. Committing

**One commit per coherent, working section.** Not per file — that buries the
change in noise. Not once per phase — that produces a commit nobody can review
or revert.

A section is committable when it **works and its narrow tests pass** (§4a). For
example, within Phase 1: the `User` model + phone auth is one commit; the
permission catalogue + `Role` is another; branch seeding is a third.

```
git add <the files for this section>      # explicit paths, never -A blindly
scripts/dev.sh test <that module>          # must be green BEFORE committing
git commit
```

**Message format** — subject in the imperative under ~65 characters, blank line,
then a body explaining *why* this shape and anything a reviewer would otherwise
have to reconstruct. Match the style of the existing commits.

```
Add User model with phone-number authentication

USERNAME_FIELD is phone, normalised to canonical 01XXXXXXXXX on save,
so +880/880/dashed forms all resolve to one account. Phone is globally
unique rather than per-branch: a teacher moving institution keeps their
login and their history.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
```

Every commit message ends with that `Co-Authored-By` line.

**Never commit:** `.env.development`, `.env.production`, any real secret, any
`__pycache__`, `node_modules`, `dist`, `media/`, or a migration that has not been
run. Check `git status` before staging; do not `git add -A` while another agent
may be mid-write.

**Do not commit a broken section** to "save progress". A commit is a claim that
this state works.

### Definition of done for a module

- [ ] Models with `Meta` constraints and indexes from `docs/03`
- [ ] Migration applied cleanly on an empty **and** a seeded database
- [ ] Serializers, `BranchScopedViewSet`, permission class wired
- [ ] Business logic in `services.py`, in a transaction
- [ ] Branch-isolation test passes (404 for another branch's row)
- [ ] Registered in Django admin for debugging
- [ ] Frontend page, sidebar entry, `canView()` gate
- [ ] Both languages present (bn + en)
- [ ] **Responsive at 360px, 390px, 768px, 1280px** (§7a)
- [ ] Committed, with its narrow tests green (§8a)
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
