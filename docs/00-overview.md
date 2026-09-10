# SIES — Smart Islamic Education System

**Status:** Design document. No code has been written yet.
**Reference implementation:** `~/awliaa` (Django 5 + DRF backend, React 19 + Vite
admin dashboard, Celery, Redis, Traefik). SIES borrows its architecture, its
admin UI, and its role/permission system, and drops what it does not need.

---

## 1. What this system is

A management platform for Islamic educational institutions. One deployment
serves many **branches** — and **a branch is a complete institution**: a
madrasah, a school, or a college (`08` D1). Each runs its own students,
teachers, admissions, attendance, fees, accounts, examinations and reports; the
**platform admin** sees across all of them.

### The three streams

A **stream** is the student's study sector — what the brief calls both *Student
Type* and *Category*, which are one thing (`08` D2). These three are canonical
and are what a madrasah is seeded with:

| Stream    | Meaning |
|-----------|---------|
| `hifz`    | Qur'an memorisation (written "Hafj" in the brief) |
| `qaumi`   | Qaumi madrasah curriculum (Ibtidaiyyah → Dawra) |
| `general` | National curriculum (Class 1–10, SSC etc.) |

They are **rows in a per-branch `Stream` table**, not a fixed enum in code. Two
reasons, and neither changes the three above:

1. **Each institution types its own Bangla label.** One writes "হিফজ", another
   "হাফজ". The `code` stays `hifz`; only `name_bn` differs. This is what retires
   the earlier "Hafj = Hifz?" question — nobody has to be told they spell it
   wrong.
2. **A branch may be a school or a college** (`08` D1), whose sectors are not a
   madrasah's. Those institutions get their own rows rather than being forced
   into these three.

Seeded on branch creation from `institution_type`:

| `institution_type` | Seeded streams |
|--------------------|----------------|
| `madrasah` | **Hifz · Qaumi · General** — the three above |
| `school` | General |
| `college` | Science · Commerce · Arts |
| `combined` | all six |

## 2. What "smart" means here (scope guard)

"Smart" in this system means **the software does the recurring clerical work by
itself**, not that it contains AI. Concretely, and this is the whole list:

1. **Fee categories seed themselves.** Creating a branch creates its eleven fee
   categories with sensible notes and recurrence rules. Nobody types them.
2. **Monthly fees generate themselves.** A Celery beat job raises the month's
   invoices for every active enrolment on the 1st, priced by the student's
   class and any standing discount.
3. **Fines accrue themselves.** Overdue invoices pick up the branch's fine rule
   nightly, capped, and stop when paid.
4. **Fees post to accounts by themselves.** A recorded payment writes the
   matching Income row. There is no second data entry, and the two can never
   disagree.
5. **Reminders send themselves.** SMS to the guardian before a due date, after
   it, and on absence — on the branch's own schedule, in the branch's language.
6. **Reports are pre-aggregated.** Nightly rollups so a year-long report is a
   read, not a scan.

Everything else is ordinary CRUD, done carefully.

## 3. Non-goals (explicitly excluded by the brief)

- **No Next.js.** The frontend is React + Vite + React Router, SPA only, exactly
  like `awliaa/frontend/admin_dashboard`.
- **No Google / OAuth login.** Login is **11-digit phone number + password**.
- **No database query caching layer.** Redis exists for Celery broker/result and
  for session-ish short-lived keys (OTP, rate-free idempotency), not as a
  read-through cache in front of Postgres.
- **No API rate-limit system.** `awliaa`'s `core/throttles.py` is not ported.
- **No storefront, no e-commerce, no subscriptions/billing.** SIES is one
  institution's internal system, not a SaaS with paying tenants. The tenant
  boundary is the *branch*, and branches are created by the platform admin, not
  self-signup.

## 4. Document map

Read in order — architecture, then system, then database.

| File | Contents |
|------|----------|
| `00-overview.md` | This file — scope, streams, non-goals |
| `01-architecture.md` | Services, request path, Traefik, Celery, multi-branch strategy, deployment |
| `02-system-design.md` | Actors, RBAC, branch scoping, module workflows, API conventions, admin UI |
| `03-database.md` | Every table, field by field, with the reasoning and constraints |
| `04-roadmap.md` | Testing, risks, full-design build order *(phases superseded by `05` §8)* |
| **`05-scope-and-v1.md`** | **The scope authority** — what the software is, the V1 cut line, what is deferred and why |
| `06-diagrams.md` | The whole system in 15 diagrams — landscape, yearly loop, ERD, every key flow |

> **If you read one file, read `05`.** `01`–`03` describe the full design; `05`
> says which parts of it are being built first, and is the tie-breaker wherever
> the documents disagree.

## 5. What was taken from Awliaa, and what was left

**Taken:**

- Project shape: `backend/app/<domain-app>/` + `frontend/admin_dashboard/`,
  `docker-compose.{dev,prod}.yml`, `traefik/`.
- `AUTH_USER_MODEL = accounts.User` with a custom manager; JWT via SimpleJWT.
- The **granular permission model** from `accounts/permissions.py`: roles are
  *presets* that tick boxes; the boxes are what is enforced. This is the single
  best idea in the reference project and is ported almost verbatim.
- The admin dashboard shell: `DashboardLayout.tsx` sidebar with grouped nav +
  inline SVG icon set + waiting-work badges, `lib/api.ts` runtime `window.ENV`
  API URL, `lib/auth-context.tsx`, `lib/permissions.ts`, `lib/i18n` (bn/en
  toggle), and `components/common/*` (`BaseModal`, `FilterBar`, `Pagination`,
  `SectionCard`, `SortableTh`, `StatCard`, `PeriodFilter`, `ExportCsvButton`,
  `ImageUploadField`).
- Celery layout: `core/celery.py`, `CELERY_*` settings, `CELERY_BEAT_SCHEDULE`,
  task routing, per-task time limits.
- Traefik as the single entrypoint with automatic TLS.

**Left behind:** dokan/storefront, catalog, order, payments gateways,
subscriptions, chatbot, blog, reviews, marketing campaigns, Google OAuth,
throttles, the read-through cache layer, R2/CDN image hosting (SIES stores
student photos and documents on local/volume media behind the API — see
`02-data-model.md` §Documents).
