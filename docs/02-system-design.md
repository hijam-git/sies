# 02 — System Design

*How the system behaves.* Architecture is in `01`; the tables are in `03`.
This file is the bridge: roles, branch scoping, each module's workflow, the API
conventions, and the admin UI.

---

## 1. Actors

Remember that **a branch is a whole institution** (`08` D1), so "all branches"
below means *across every institution on the platform*.

| Actor | Logs in? | Scope | Cares about |
|-------|----------|-------|-------------|
| **Platform Admin** | yes | all institutions | Onboarding institutions, cross-institution reports, role presets |
| **Platform Accountant** | yes | all institutions | Consolidated income/expense across institutions |
| **Principal / Institution Admin** | yes | one institution | Everything in their institution |
| **Accountant** | yes | one institution | Fees, income, expenses, salary, receipts |
| **Teacher** | yes | one institution | Their classes: attendance, marks, students |
| **Employee (non-teaching)** | yes | one institution | Their own attendance, assigned duties |
| **Student** | **optional** | one institution | Own profile, fees, attendance, results |
| **Guardian** | no in V1 | their children | Fee dues, attendance, results — read by staff for them |

All logins are **11-digit phone + password**. One phone, one account.

**Students may log in if they want to** (`08` D4) — `Student.user` is nullable
and "enable login" is an action on the record, not a requirement of admission.
Most young students will never have one. `/api/me/` is therefore **in V1**.

**Guardian login stays V2.** Guardians are contact records in V1; the `Guardian`
table already carries a nullable `user`, so it can be switched on later without
a migration.

---

## 2. RBAC — roles are presets, permissions are the truth

Ported almost verbatim from `awliaa/backend/app/accounts/permissions.py`, which
is the strongest idea in the reference project and worth restating:

> A **role** ticks a set of boxes. The **boxes** are what gets enforced.

Fixed roles cannot express "runs admissions but must never see the accounts",
and every institution eventually needs exactly that. So:

- `Role` is a named preset: a `{resource: [actions]}` matrix.
- `User.permissions` is a flat list of `"resource.action"` strings.
- **Empty list ⇒ fall back to the role's preset.** Accounts created before an
  admin ever customised anything keep working. (Awliaa's rule; keep it.)
- The catalogue is served to the dashboard at `GET /api/accounts/permission-catalog/`,
  so the checkbox screen is generated from the backend and cannot drift from
  what the backend enforces. One source of truth, not two copies.

### 2.1 The permission catalogue

| Resource | Actions | Covers |
|----------|---------|--------|
| `dashboard` | view | The overview page and its numbers |
| `branches` | view, create, update | Institution list and settings (platform admin) |
| `academics` | view, create, update, delete | Classes, sections, subjects, sessions, streams, **routine** |
| `students` | view, create, update, delete | Student records and profiles |
| `admissions` | view, create, update | Applications, admission, enrolment |
| `teachers` | view, create, update, delete | Teacher profiles and assignments |
| `employees` | view, create, update, delete | Non-teaching staff |
| `attendance` | view, take, update | Taking and correcting attendance |
| `fees` | view, create, update, collect, waive | Invoices, collection, discounts |
| `finance` | view, create, update | Income, expenses, ledger |
| `salary` | view, manage | Payroll — separate from `finance` on purpose |
| `exams` | view, create, update, publish | Exams, schedules, marks, results |
| `marks` | view, enter, update | Entering marks — a teacher gets this without `exams.create`. `view` exists so `canView()` needs no special case |
| `reports` | view, export | Reports and their exports |
| `notices` | view, create, delete | Notice board. (Bulk SMS is V2 — `08` §7) |
| `documents` | view, upload, delete | Certificates, testimonials, student files |
| `settings` | view, update | Institution settings, fee categories, form templates |
| `users` | view, create, update | Accounts, roles, permission assignment |
| `activity` | view | The live activity feed and history (`08` D8) |

Two separations are deliberate and carry the same reasoning as Awliaa's
`purchasing` split:

- **`salary` is not `finance`.** Letting an accountant post the electricity bill
  is a much smaller decision than letting them see what every teacher earns.
- **`marks.enter` is not `exams.publish`.** A teacher enters their subject's
  marks; only the principal publishes a result, and publishing is the moment
  results become visible to students and the rank is computed.

### 2.2 Default presets

Nine presets, covering both teaching and non-teaching staff. A preset is a
starting point, never a cage — see §2.3.

| Preset | Gets |
|--------|------|
| **Platform Admin** | Everything, across every institution: `branches.*`, `users.*`, `activity.view` |
| **Principal** | Everything in their institution except `branches.create` and `activity.view` |
| **Accountant** | `dashboard.view` · `fees.*` · `finance.*` · `reports.view/export` · `students.view` · `academics.view` |
| **Admission Officer** | `dashboard.view` · `admissions.*` · `students.view/create/update` · `fees.view/create` · `documents.upload` |
| **Teacher** | `dashboard.view` · `academics.view` · `attendance.view/take` · `marks.view/enter/update` · `students.view` · `exams.view` |
| **Class Teacher** | Teacher, plus `attendance.update` · `documents.view` |
| **Hostel Warden** | `dashboard.view` · `students.view` · `attendance.view/take` |
| **Office Assistant** | `dashboard.view` · `students.view` · `documents.view/upload` · `notices.view` |
| **General Employee** | `dashboard.view` only, plus their own self-service pages |
| Student | Self-service only (§2.5) — not a preset, a different surface |

Non-teaching staff differ from each other more than teachers do: a hostel
warden takes attendance, a librarian does not, a cook needs nothing but their
own payslip. One thin `General Employee` preset plus per-person ticks covers all
of them without inventing a role per job title.

### 2.3 Any permission can be granted per person

**The superuser — or a principal within their institution — may tick or untick
any individual permission on any individual teacher or employee.** This is the
whole point of the preset model, and it is how the system handles the cases a
fixed role list never can:

- A teacher who also collects fees at the counter → tick `fees.collect`. No new
  role, no second account.
- A senior teacher who may enter marks but must not publish results → they have
  `marks.enter` and simply never get `exams.publish`.
- An accountant who must not see payroll → `finance.*` without `salary.view`.
- An office assistant trusted with admissions during the season → tick
  `admissions.create`, untick it in March.

**How it resolves** (`06` #6):

```
user.permissions is empty  →  use the role preset      ← the normal case
user.permissions is set    →  use exactly that list    ← the customised case
```

The preset is **not merged** with the custom list. Once an admin customises a
person, that list is the whole truth for them — otherwise unticking a box the
preset grants would silently do nothing, which is the most dangerous kind of
permission bug. The UI makes this explicit: opening the permission screen for a
user shows the preset's boxes pre-ticked, and saving converts them into that
user's own list.

Changing a role preset afterwards therefore moves everyone still on the preset
and leaves customised people alone — which is what an admin expects.

Every permission change is written to the activity log with before and after
(`03` §1, **V1** per `08` D8), because "who gave the office assistant access to the accounts"
must have an answer.

### 2.4 Teacher assignment is a second gate

A permission says *what verb*; an **assignment** says *which classes* (`08` D6).
Both must pass for a teacher:

```
attendance.take          ← permission: may they take attendance at all?
class is one of theirs   ← assignment: for THIS class?
```

Without the second gate, `attendance.take` marks every class in the institution
and `marks.enter` covers subjects they do not teach.

A teacher's scope is the union of the classes they are **in charge of**
(`AcademicClass.class_teacher`, `Section.in_charge`) and the classes where they
hold a **`SubjectAssignment`**, for the current session. Out-of-scope classes
never appear in their class picker, so the limit reads as a shorter list rather
than a refusal.

Principals, accountants and the platform admin are not scoped this way — they
see the whole institution. `Branch.restrict_teachers_to_assigned_classes`
(default **on**) lets a small institution where everyone covers everything turn
it off.

Assignments are made by the admin on **Staff → Assignments**: pick a session,
set each class's class teacher and each subject's teacher.

### 2.5 Self-service is not a permission

A student reading their own result is not `exams.view`; it is a different
endpoint family (`/api/me/…`) whose queryset is filtered to
`request.user`'s own records and which grants nothing else. Modelling
self-service as a weak version of a staff permission is how systems end up
letting a student list the whole class by changing an id in the URL.

---

## 3. Branch scoping

Restating `01` §5 in operational terms.

1. `BranchScopeMiddleware` resolves `request.branch` after authentication:
   - `user.branch` is set → that branch, and `?branch=` is **ignored** (not an
     error — ignored, so a copied platform-admin URL degrades safely).
   - `user.branch` is `NULL` (the platform admin) → `?branch=<id>` if given, else the
     special value `ALL`.
2. Every branch-scoped viewset inherits `BranchScopedViewSet`, whose
   `get_queryset()` applies the filter and whose `perform_create()` stamps
   `branch` from `request.branch` — **the client never supplies `branch` on
   write.** A branch id in a POST body is ignored, so it cannot be used to
   write into a branch the user cannot see.
3. Cross-branch reads happen only through explicitly-named platform-admin report
   views (in each module in V1 — there is no `reports/` app until V2), gated on
   `reports.view` **and** `user.branch is NULL`.
4. A `MultiBranch` grant (`BranchAccess`) widens step 1's result to a set.

Tests assert the negative case per module: *a branch-A user requesting a
branch-B object receives 404, not 403* — 403 confirms the object exists.

---

## 4. Modules

### 4.1 Admissions

```
Application → Screening/Interview → Offer → Admission → Enrolment → Student active
```

- An **Application** is captured with the applicant's details, chosen stream
  (a `Stream` row), class and session. It exists before any Student row.
- Admission converts an accepted application into a **Student** + **Enrolment**,
  allocates the admission number and roll, and raises the **Admission Fee** and
  **Session Fee** invoices in the same transaction. One click, three
  consequences, all or nothing.
- Re-admission into the next session creates a **new Enrolment**, never a new
  Student. This is why enrolment is its own table (`03` §Academics): a student's
  identity is stable, their class/section/session is not, and the admission
  history the brief asks for *is* the list of their enrolments.

### 4.2 Student management

Everything the brief lists hangs off the student record: photo, category,
branch, session, class, section, guardian, contacts. The *histories* —
admission, fee, payment, examination, documents — are not fields; they are
queries over the rows those modules already own. Storing a "fee history" on the
student would be a second copy that drifts from the fee table.

Student ID vs admission number, since the brief lists both:
- **Student ID** — permanent, institution-wide, never reused: `SIES-000123`.
- **Admission number** — per branch, per session, human-quoted:
  `ADM-DHK-2026-00417`. Changes on re-admission; the Student ID does not.

### 4.3 Teacher & employee

Two models, `Teacher` and `Employee` (`08` D5), sharing an abstract base rather
than two near-identical tables, because attendance, salary, leave and documents
are identical for both and duplicating them doubles every future change. The
teaching-only parts (subjects, class assignments) live in their own tables and
are simply absent for non-teaching staff.

### 4.4 Attendance

Two kinds, exactly as the brief separates them:

- **Daily attendance** — one row per person per day. Applies to students,
  teachers and employees alike (the person is a `User` reference plus their
  role), records status, time in/out, and **who took it**.
- **Class attendance** — one row per student per class-period per day, for
  institutions that take attendance subject-by-subject. Also records the class,
  the period, and the taker.

Both carry `taken_by`, `taken_at`, and a `source` (web / mobile / biometric /
imported), because "who marked my son absent" is a question that gets asked and
must have an answer. Corrections are a new row plus an audit entry, never an
in-place edit that erases what was originally recorded.

Absence triggers an async SMS to the guardian on the branch's rule (e.g. after
09:30, once per day, not on holidays). *(SMS is V2 — see `05` §5.4.)*

#### The attendance screen is a monthly register grid

**Students down the side, days across the top.** The teacher opens one class and
section for one month and marks cell by cell.

```
Class 10 · Section A · March 2026            [◀ Feb]  [March 2026]  [Apr ▶]
┌──────────┬─────────────────┬───┬───┬───┬───┬───┬───┬── … ──┬───┬──────┐
│ Student  │ Name            │ 1 │ 2 │ 3 │ 4 │ 5 │ 6 │       │31 │  %   │
├──────────┼─────────────────┼───┼───┼───┼───┼───┼───┼── … ──┼───┼──────┤
│ SIES-…01 │ Abdullah Rahman │ P │ P │ A │ P │ L │ ▒ │       │   │ 92%  │
│ SIES-…02 │ Bilal Hossain   │ P │ A │ A │ P │ P │ ▒ │       │   │ 78%  │
│ SIES-…03 │ Umar Faruk      │ P │ P │ P │ P │ P │ ▒ │       │   │ 100% │
├──────────┼─────────────────┼───┼───┼───┼───┼───┼───┼── … ──┼───┼──────┤
│          │ Present         │ 3 │ 2 │ 1 │ 3 │ 2 │ ▒ │       │   │      │
└──────────┴─────────────────┴───┴───┴───┴───┴───┴───┴── … ──┴───┴──────┘
   ▒ = weekly off / holiday, not markable      P present · A absent · L leave
```

This is the screen teachers spend their time in, so it is designed around the
hand, not the mouse:

- **Keyboard first.** Arrow keys move between cells; `P` / `A` / `L` / `H` set a
  status and advance; `Enter` drops to the next student, same day. A teacher
  marking sixty students should never touch the mouse.
- **Column and row bulk actions.** "Mark whole day present" on a date header,
  then correct the three who are absent — which is how attendance actually goes.
  Same for a row, for a student who was away all week.
- **Batch save, not per-cell save.** Sixty students × thirty days is 1,800 cells;
  one request per cell is 1,800 requests. The grid tracks dirty cells and posts
  them together (§5.1 below), on an explicit Save and on a debounce.
- **Future dates are locked.** Tomorrow cannot be marked.
- **Weekly off days and holidays are rendered as non-markable columns**, so the
  teacher is not asked to mark a Friday and the percentage denominator excludes
  it. Holidays are V2; the weekly off day is a V1 field on `Branch`
  (`weekly_off_days`, e.g. `["fri"]`) precisely because a month grid puts four
  or five of them on screen immediately.
- **Live totals.** Per-day present count along the bottom, per-student
  percentage down the right, both recalculated client-side as cells change.
- **Every cell records its own `taken_by` and `taken_at`.** The grid is a view
  over `DailyAttendance` rows; the model does not change to support it.

The same grid serves **staff attendance** — teachers and employees down the side
instead of students — since `DailyAttendance` already holds both.

The single-day roster view is kept as a secondary tab for the branch that
prefers marking today only, but the month grid is the default.

### 4.5 Fees

The brief's fee row, elaborated into the two tables it actually needs:

- **FeeStructure** — *what a class costs*: category × class × session × amount.
  Set once per session by the accountant. This is why the monthly job knows the
  amount without anyone typing it.
- **Fee (invoice)** — *what one student owes*: branch, student, category,
  amount, due date, status, discount, fine, paid amount.
- **Payment** — *a receipt*: amount, method, transaction id, date, collected_by.
  Separate from the invoice because part payments are normal and one invoice can
  have several receipts. Collapsing them into one row (as the brief's field list
  suggests) makes the second instalment impossible to record.

Status is **derived**, never hand-set: `unpaid → partial → paid`, plus
`overdue` (due date passed and balance > 0) and `waived`. A field a human can
set to "paid" without money arriving is an invitation.

Fee categories seed themselves on branch creation (`03` §Fees), covering the
brief's list: Admission, Session, Monthly, Examination, Book, Uniform,
Transport, Hostel, Activity, plus custom.

### 4.6 Finance

Income and Expense are structurally the same shape — branch, category, amount,
date, method, reference, voucher number, recorded_by, attachment — so they share
a base and differ only in direction and default categories (the brief's two
lists, seeded per branch).

**Fee collection posts income automatically.** A `Payment` row writes the
matching `Income` row in the same transaction, tagged with the payment's id.
Nobody re-enters it, and the two cannot disagree. Manual income entry stays
available for donations and other non-fee receipts.

Salary is an expense with its own module (payroll run → per-staff payslip →
expense rows), gated on `salary.manage`.

### 4.7 Examinations

```
Exam (session, class, type) → ExamSchedule (subject, date, full/pass marks)
   → Mark (student × subject: obtained, absent flag, entered_by)
   → publish → Result (total, average, GPA, grade, rank, pass/fail)
```

Marks are entered per subject by the teacher (`marks.enter`). Publishing is a
separate, principal-only action that runs the whole-class computation as a
Celery task and only then makes results visible. Grade scales are per branch and
per stream — the Qaumi stream's grading is not the general stream's GPA, and
hard-coding one of them is a rewrite later.

### 4.8 Reports

Every report is (a) branch-scoped or platform-wide, (b) period-filtered, and
(c) exportable to PDF/Excel via an async job. The set:

| Family | Reports |
|--------|---------|
| Students | Strength by class/stream/branch, admission trend, withdrawals |
| Attendance | Daily register, monthly percentage, defaulters, staff attendance |
| Fees | Collection by day/month/category, outstanding dues, defaulter list, receipt reprint |
| Finance | Income/expense statement, category breakdown, branch P&L, group consolidated |
| Exams | Marksheet, tabulation sheet, merit list, subject analysis, progress card |
| Staff | Payroll register, leave summary |

Platform admin gets a **branch comparison** view — collection %, attendance %,
strength, expense per student — which is the reason the branch model exists.

### 4.9 Notifications

One outbox table and one adapter interface, with SMS as the first (and, for
Bangladesh, primary) channel. Templates are per branch, per language, per event
(fee due, fee received, absent, result published, notice). Every send is logged
with its provider response, because "we sent it" needs evidence when a guardian
says otherwise.

---

## 5. API conventions

- Base path `/api/`, versionless. DRF `ModelViewSet` + routers, as in Awliaa.
- **Consistent envelope on non-list responses:** `{ success, data, message }`;
  errors go through one `EXCEPTION_HANDLER` (Awliaa's
  `core/exception_handlers.py`) so the SPA has exactly one error shape to render.
- **Pagination** on every list, page-number style, default 25.
- **Filtering** with `django-filter`; every list supports `?search=`,
  `?ordering=`, and its module's natural filters (`?class=`, `?session=`,
  `?status=`, `?from=&to=`).
- **Writes never accept `branch`.** It is stamped server-side (§3).
- **Exports return a job**, not a file: `POST /api/reports/<name>/export/` →
  `{ job_id }`, then `GET /api/jobs/<id>/` → status → download URL.
  *(V2 — V1 downloads CSV synchronously.)*
- **Self-service** lives under `/api/me/` and is filtered to the caller.

### 5.1 The attendance register endpoints

The month grid needs two endpoints that are not plain CRUD, because 1,800 cells
cannot be 1,800 requests:

```
GET  /api/attendance/register/?class=<id>&section=<id>&month=2026-03
  → { days: [ {date, is_markable, reason} … ],      # off days flagged here
      students: [ {student_id, name, roll,
                   cells: { "2026-03-01": {status, taken_by, taken_at}, … },
                   present, absent, leave, percent } ] }

POST /api/attendance/register/bulk/
  { class, section, month,
    cells: [ {student, date, status}, … ] }         # dirty cells only
  → { saved, skipped: [ {student, date, reason} ] }
```

Three properties the bulk endpoint must have:

1. **Idempotent** — it upserts on `(branch, date, person, student)`, which is
   already the table's unique key (`03` §6). Saving twice writes the same rows.
2. **Server-authoritative on what is markable** — a future date or an off day is
   rejected and reported in `skipped`, never silently written, however the client
   was persuaded to send it.
3. **One transaction** — a partial save that leaves half a month written is worse
   than a failed one, because nobody can tell which half.

`taken_by` is stamped from `request.user` per cell, not sent by the client.

Endpoint families: `auth`, `accounts`, `branches`, `academics`, `students`,
`admissions`, `staff`, `attendance`, `fees`, `finance`, `exams`, `reports`,
`notifications`, `me`, `jobs`.

---

## 6. Admin UI

Copied from `awliaa/frontend/admin_dashboard` — React 19, Vite 7, React Router 7,
Tailwind 3, TypeScript. Same structure, same conventions, different pages.

**Carried over unchanged:** `lib/api.ts` (runtime `window.ENV.API_URL`),
`lib/auth-context.tsx`, `lib/permissions.ts`, `lib/format.ts`, `lib/timezone.ts`,
`lib/i18n/` (bn/en toggle), `lib/useTabParam.ts`, `lib/printInvoice.ts` (becomes
`printReceipt`), and `components/common/*`: `BaseModal`, `FilterBar`,
`Pagination`, `SectionCard`, `SortableTh`, `StatCard`, `PeriodFilter`,
`ExportCsvButton`, `ImageUploadField`, `ArrayEditor`.

**`DashboardLayout.tsx`** is reused as-is in structure: grouped collapsible
sidebar, inline SVG icon map, `canView(resource)` gating every nav item, waiting-
work badges (here: unpaid-fee count, pending admissions, unmarked attendance),
language toggle, branch switcher for the platform admin.

### Navigation

```
Overview
Academics ─ Classes · Sections · Subjects · Sessions · **Routine**
Students  ─ All students · Admissions · Enrolment · Documents
Staff     ─ Teachers · Employees · **Assignments**
Attendance─ **Month register** · Class attendance · Daily register · Reports
Fees      ─ Fee structure · Invoices · Collect fee · Dues · Discounts
Accounts  ─ Income · Expenses · Salary · Ledger
Exams     ─ Exams · Schedule · Marks entry · Results · Marksheets
Reports   ─ (the families in §4.8)
Notices   ─ Notice board          (SMS is V2)
Settings  ─ Institution · Fee categories · Form templates
Users     ─ Accounts · Roles & permissions · **Live activity**
Branches  ─ (super admin only)
```

Every entry is hidden unless `canView(resource)` passes — the same gate Awliaa's
layout already applies.

### Screens that carry the weight

- **Collect fee** — search student by name/phone/admission no → outstanding
  invoices → part or full payment → receipt printed. This screen is used more
  than any other and is designed first.
- **Attendance register** — the month grid of §4.4: students down, thirty days
  across, keyboard-driven, batch-saved. Along with Collect fee, this is where
  the institution's daily hours are actually spent.
- **Marks entry** — one class × one subject as a keyboard-navigable grid, saving
  per row, resumable. Deliberately the same interaction model as the attendance
  register, so a teacher learns one grid and knows both.

Each is a page under `src/pages/`, with its module components under
`src/components/<module>/`, matching Awliaa's layout exactly.
