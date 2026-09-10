# 01 — Architecture

Read this before the system design (`02`) and the database design (`03`).
This file answers: *what runs, where, and how a request travels.*

---

## 1. The shape, in one picture

```
                            ┌─────────────────────────────┐
   browser ── HTTPS ──────► │  Traefik  (:80 / :443)      │
   (admin, teacher,         │  TLS via Let's Encrypt      │
    student, guardian)      │  the ONLY exposed container │
                            └───────┬─────────────┬───────┘
                                    │             │
                    Host: sies.­…  /api/*         everything else
                                    │             │
                            ┌───────▼──────┐  ┌───▼──────────────────┐
                            │  backend     │  │  admin_dashboard     │
                            │  Django+DRF  │  │  React SPA (static)  │
                            │  gunicorn    │  │  `serve -s dist`     │
                            └──┬────┬───┬──┘  └──────────────────────┘
                               │    │   │
              ┌────────────────┘    │   └──────────────┐
              │                     │                  │
       ┌──────▼──────┐      ┌───────▼──────┐    ┌──────▼───────┐
       │ PostgreSQL  │      │    Redis     │    │  media vol   │
       │ (the truth) │      │ broker+result│    │ photos, docs │
       └──────▲──────┘      └───────▲──────┘    └──────▲───────┘
              │                     │                  │
       ┌──────┴─────────────────────┴──────────────────┴───────┐
       │  celery-worker        │  celery-beat                   │
       │  fee generation,      │  the clock: monthly fees,      │
       │  SMS, reports, PDFs   │  fines, reminders, rollups     │
       └───────────────────────┴────────────────────────────────┘
```

Seven containers. That is the entire production footprint:
`traefik`, `backend`, `admin_dashboard`, `postgres`, `redis`,
`celery-worker`, `celery-beat`.

---

## 2. Why these pieces and not others

**Traefik, not nginx.** Carried over from Awliaa (`awliaa/traefik/`). It reads
routing from container labels, so adding a service is a label, not an nginx
config edit and reload. It gets and renews TLS certificates itself. Only
Traefik binds a host port; everything else talks on the internal Docker
network and is unreachable from outside. That is the security boundary.

**Django + DRF, no Next.js.** The brief is explicit. The API is the only
backend; the SPA is static files. There is no server-side rendering, no BFF,
no Node process in production beyond the tiny static file server. This is a
staff-facing internal tool behind a login — SEO and first-paint SSR buy
nothing here, and dropping Next removes a whole runtime from the deployment.

**PostgreSQL.** Financial rows and academic records need real transactions,
real foreign keys and real decimal arithmetic. `DecimalField` on money,
never float. Fee payment + income posting happen inside one
`transaction.atomic()` block or neither happens.

**Redis, as broker only.** Per the brief there is **no database caching layer**.
Awliaa's `core/cache.py` and `storefront_cache.py` are not ported. Redis holds
the Celery queue, Celery results, and short-lived operational keys (an OTP, an
idempotency key on a payment POST). If a Redis flush would lose data that
matters, it is in the wrong store.

**Celery, required.** The brief asks for it, and §4 below is why it earns its
place: this system's defining feature is work that happens without anyone
clicking.

**No rate limiting.** Awliaa's `core/throttles.py` is deliberately not ported.
This is an internal system on a known user population.

---

## 3. The request path

### 3.1 Authentication

Login is **11-digit phone number + password**. No email login, no Google, no
magic link.

```
POST /api/auth/login/   { phone: "01712345678", password: "…" }
   → { access, refresh, user: { id, phone, name, user_type, branch,
                                 permissions: [...] } }
```

- **JWT** via `djangorestframework-simplejwt`, exactly as Awliaa configures it
  (`SIMPLE_JWT` in settings). Short-lived access token, rotating refresh.
- The phone is **normalised before it is stored or compared** — Awliaa already
  has this logic (`lib/normalizeBdPhone`), and it is ported. `+8801712345678`,
  `8801712345678`, `01712345678` and `01712-345678` are one person. Stored
  canonical form: 11 digits beginning `01`.
- Phone is **globally unique**, not unique-per-branch. A person is one person;
  a teacher who moves branch keeps their login. Cross-branch access is a
  separate mechanism (§5.2), not a duplicate account.
- The login response carries the user's **resolved permission list**, so the
  SPA can hide what the user cannot do without a second round trip. The list is
  advisory for the UI and authoritative only on the server.

### 3.2 Every subsequent request

```
Authorization: Bearer <access>
        │
        ▼
  JWT auth ──► request.user
        │
        ▼
  BranchScopeMiddleware ──► request.branch
        │      (from user.branch, or ?branch= for the platform admin)
        ▼
  DRF permission class ──► "fees.create" in user's effective permissions?
        │
        ▼
  ViewSet.get_queryset() ──► .filter(branch=request.branch)
        │
        ▼
  response
```

Four gates, and the order matters. Authentication says *who*, branch scoping
says *which branch's data exists at all for this request*, the permission class
says *what verb*, and the queryset filter is the belt-and-braces that makes a
forgotten permission check a 404 rather than a leak.

Detail of the scoping rules is in `02-system-design.md` §Branch scoping; the
permission catalogue is in `02` §RBAC.

---

## 4. Background work — what Celery actually does

| Job | Trigger | Why it cannot be request-time |
|-----|---------|-------------------------------|
| Generate monthly fee invoices | Beat, 1st of month 00:15 | Thousands of rows across all branches; nobody should have to click "raise this month's fees" |
| Apply overdue fines | Beat, nightly 01:00 | Depends on the passage of time, not on a user action |
| Fee due / overdue SMS to guardian | Beat, daily 09:00 | Outbound I/O to an SMS gateway; must not block or fail a page |
| Absence SMS to guardian | On attendance submit (async) | The teacher's "save" must return instantly |
| Nightly report rollups | Beat, 02:00 | Pre-aggregate so year-scale reports are a read |
| Result processing & rank calculation | On "publish results" | Whole-class computation; long, and must be resumable |
| PDF/Excel generation (marksheets, certificates, ledgers, ID cards) | On demand, async | Seconds to minutes; returns a job id, then a download |
| Bulk SMS / notices | On demand, async | Fan-out over many recipients |
| Database backup | Beat, daily | Housekeeping |

Beat schedule lives in `CELERY_BEAT_SCHEDULE` (same pattern as
`awliaa/backend/app/core/settings.py:1054`). Two queues — `default` and `slow`
(exports, bulk SMS) — so one long export cannot starve fee generation.
`CELERY_TASK_TIME_LIMIT` / `SOFT_TIME_LIMIT` are set as in Awliaa.

**Every scheduled money task is idempotent.** Fee generation is keyed on
`(student, category, period)` with a unique constraint, so running it twice
produces one invoice, not two. This is non-negotiable: a beat job that
double-charges a guardian is worse than one that never runs.

---

## 5. Multi-branch: the central architectural decision

### 5.1 One database, branch column — not schema-per-branch

Every business row carries `branch_id`. Rejected alternatives, and why:

- *Separate database per branch* — makes the platform-admin consolidated report
  (the whole point of a branch model) a cross-database join, and multiplies
  migrations by the branch count.
- *Postgres schema per branch* — same reporting problem, plus connection
  routing complexity, for a system whose branch count is in the tens.

A branch column, enforced by a base queryset that every viewset inherits, is
simple enough to audit by reading one file.

### 5.2 Who sees across branches

| Scope | `user.branch` | Sees |
|-------|---------------|------|
| Platform admin (super admin, group accountant) | `NULL` | All branches; may filter with `?branch=<id>` |
| Branch user (principal, teacher, accountant, student) | set | Exactly that branch |
| Multi-branch user (a teacher at two branches) | primary set | Their branch **plus** any in `BranchAccess` |

`BranchAccess` is an explicit grant table rather than a many-to-many on User,
because a grant needs its own attributes — who granted it, when, and with what
permission subset at that branch.

### 5.3 The rule that keeps it honest

**A model is either branch-scoped or global, and it says so in its base class.**
`BranchScopedModel` supplies the FK and the manager. Global models are a short,
closed list: `Branch`, `User`, `Role` presets, and the enum/lookup tables. A new
model that is neither is a review failure. Reports that span branches go through
one explicitly-named path (`HeadOfficeReportView`) that is permission-gated, not
through a viewset that quietly forgot its filter.

---

## 6. Backend application layout

Mirrors `awliaa/backend/app/` — one Django app per domain, `core` for the
project itself. The apps SIES needs are far fewer than Awliaa's fourteen:

```
backend/app/
├── core/          settings, celery, urls, middleware, exception handlers
├── accounts/      User, phone auth, roles, permissions, BranchAccess
├── branches/      Branch (= one institution), Stream, Session, calendar
├── academics/     Class, Section, Subject, Enrolment
├── students/      Student profile, guardian, admission, documents
├── forms/         FormTemplate, Question, AdmissionAnswer, PrintedForm
├── staff/         Teacher & employee profiles, qualifications, assignments
├── attendance/    Daily attendance, class attendance, leave
├── fees/          FeeCategory, FeeStructure, Fee invoice, Payment, Discount
├── finance/       Income, Expense, categories, ledger, salary
├── exams/         Exam, ExamSchedule, Mark, Grade scale, Result
├── reports/       Rollup tables, report builders, exports
└── notifications/ SMS/email adapters, templates, notice board, outbox
```

Thirteen apps, and the dependency direction is one-way: `core` ← everything;
`accounts`/`branches` ← everything else; `fees` → `finance` (a payment posts an
income) but never the reverse. `forms` depends on `branches` + `students` and is
imported by none. `reports` reads from all and is read by none. Cycles are what
turn a Django project into a single ball of mud, so this ordering is a rule, not
an observation.

*In V1, `notifications/` and `reports/` are not created at all (`05` §6) —
eleven apps.*

---

## 7. Environments and deployment

Three compose files, as in Awliaa: `docker-compose.dev.yml`,
`.staging.yml`, `.prod.yml`, driven by `.env.<env>` with a committed
`.example` alongside each.

- **dev** — Django `runserver` with autoreload, Vite dev server with HMR,
  Postgres and Redis in containers, Traefik on `*.localhost`, `DEBUG=1`,
  `CELERY_TASK_ALWAYS_EAGER=1` for tests (Awliaa's pattern, settings:846).
- **staging** — production images, separate database, real Celery, SMS gateway
  in sandbox mode so no message reaches a real guardian.
- **prod** — gunicorn behind Traefik, static SPA served by `serve -s dist`,
  daily `pg_dump` to off-box storage, Sentry-style error reporting.

**Runtime configuration of the SPA.** The dashboard reads its API URL from
`window.ENV.API_URL`, injected by the container's entrypoint at startup — the
exact trick from `awliaa/frontend/admin_dashboard/src/lib/api.ts`. It means one
built image promotes from staging to production unchanged, which is the only
way "we tested it in staging" is a true statement.

---

## 8. What is deliberately absent

| Absent | Because |
|--------|---------|
| Next.js / SSR | Brief; internal tool behind a login |
| Google & social login | Brief; phone + password only |
| DB read cache | Brief; correctness of money beats microseconds |
| API rate limiting | Brief; known internal user population |
| Storefront, catalog, orders, subscriptions, chatbot, blog, reviews, marketing | Awliaa is a SaaS e-commerce platform; SIES is one institution's internal system |
| CDN / R2 media | Student photos and documents are private records, served through the API behind auth, not from a public bucket |

---

## 9. Cross-cutting decisions

- **Money is `Decimal(12,2)`.** Never float, anywhere, including in serializers
  and report aggregations.
- **Time is Asia/Dhaka.** `TIME_ZONE='Asia/Dhaka'`, `USE_TZ=True`; stored UTC,
  rendered Dhaka. `CELERY_TIMEZONE` matches, or the "1st of the month" job
  fires on the wrong day for six hours a year.
- **Soft delete on records with history** (students, fees, payments, marks).
  A withdrawn student's fee history must survive the withdrawal; a hard delete
  of a paid invoice destroys an accounting record.
- **Append-only activity log** (`08` D8) on money, marks, attendance and permission changes: who, what,
  before, after, when, from which IP. Adapted from `accounts/activity.py`.
- **Bilingual from day one.** Bangla and English, via the `lib/i18n` toggle
  already in the Awliaa dashboard. Student and class names store both forms;
  SMS templates exist per language and pick by the guardian's preference.
- **Numbers people quote out loud are human-readable.** Admission number, roll,
  receipt number and voucher number are per-branch, per-session, sequential and
  gapless (`ADM-DHK-2026-00417`), generated under a row lock — not UUIDs, and
  not `max()+1` in Python, which double-issues under concurrency.
