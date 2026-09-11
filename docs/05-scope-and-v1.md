# 05 — Scope Analysis & the V1 Cut Line

*This document is the scope authority.* Where it disagrees with `01`–`04`, this
one wins. `03-database.md` marks every table V1 or V2 against the cut line
defined here.

Written after a scope review in which the owner's position was: **the feature
set in the original brief is enough to start; improvements come later.** That
position is correct, and this document makes it enforceable rather than a
sentiment — by drawing an explicit line and, more importantly, by naming the
few things that genuinely cannot be deferred without cost.

---

## 1. What this software is, underneath the module names

SIES is **three ledgers sharing one set of people, partitioned by branch.**

| Ledger | The question it answers | Rows |
|--------|-------------------------|------|
| **People** | Who belongs here, and in what capacity | Students, teachers, employees |
| **Time** | Was this person here today | Attendance |
| **Money** | Who owes what; what came in; what went out | Fees, payments, income, expenses |

**Examinations** is a fourth record type layered on People — performance.
**Reports** is not a module at all; it is a read across the other four. That is
why reports are built last and why they require no new concepts to exist. A
report that needs a new table is a sign that something upstream was not recorded
properly.

**Branch** matters in exactly three places, and nowhere else:

1. It partitions every query.
2. It owns its own number sequences — each branch counts its own receipts,
   vouchers and admission numbers.
3. It is the axis the platform admin consolidates along.

Every other part of the system is branch-agnostic. This is worth stating because
it bounds how much of the codebase has to think about branches at all: the base
queryset, the number generator, and the platform-admin report views. Nothing else.

---

## 2. The loop the software exists to run

```
Session opens
  → classes defined → fee amounts set
    → admissions → enrolment
      → DAILY:    attendance · fee collection at the counter
      → MONTHLY:  fees generate · salary paid
      → PERIODIC: exams · marks · results
    → session closes → promotion
  → next session's enrolment
```

Every screen in the system sits on top of that loop. It is also the test for
whether a proposed feature belongs in V1: **if the yearly loop completes without
it, it is V2.** That single question resolves most scope arguments without
further discussion.

---

## 3. The three genuinely hard parts

Everything else in this system is careful CRUD. These three are not, and they
are where design attention and test effort belong.

### 3.1 Money correctness

The fee lifecycle — invoice → discount → fine → part payments → income posting —
is the only place where a defect costs real money and real trust with a guardian.
Every other kind of mistake is recoverable by re-entering data. A wrong fee is
recoverable only by an apology.

### 3.2 Time-varying identity

**This is the failure that quietly ruins school systems.** A student is not a
fixed object:

- Their class changes every year.
- Their roll changes.
- Their fee changes.
- Their section changes.
- Their guardian's phone changes.

And attendance recorded in 2024 must still show which class they were in *in
2024* — not which class they are in when the report is run. Systems that store
`class` directly on the student produce historical reports that are silently
wrong two years in, and by then the correct answer is no longer recoverable from
the data.

This is the entire justification for the `Enrolment` table, and it is the one
structural decision that cannot be deferred (§5.3).

### 3.3 Concurrency at the counter

Three accountants collecting fees on the 5th of the month. Receipt numbers must
not duplicate and must not gap; the same invoice must not be paid twice. This is
why numbers are issued under a row lock and never by `max() + 1`, and why the
payment endpoint is idempotent.

---

## 4. Where the brief and this design differ, and why

The original brief is the source of the feature set. This design changed three
of its models. Each change exists to prevent a specific, concrete failure — not
for tidiness.

| Brief said | Design says | The failure prevented |
|------------|-------------|------------------------|
| Student holds class, session, admission history, fee history, exam results | `Enrolment` table; histories are queries | Historical reports become permanently wrong (§3.2). Retrofitting means unpicking every past record. |
| `Fee` holds `payment_method`, `transaction_id`, `payment_date`, `paid_amount` | `Fee` (invoice) and `Payment` (receipt) are separate | A guardian paying ৳2,000 now and ৳3,000 next week is **unrecordable**. Part payment is normal, not an edge case. |
| Student login implied by "student can login by phone" | `Student.user` is nullable | A seven-year-old hifz student has no phone. If the Student record *is* the login, a child cannot be admitted without inventing a phone number. |
| `Class.name = "Class 10 2026"`, plus a separate `year` field | `name = "Class 10"`, year on the session | The brief itself carries both, which is the redundancy showing. Baking the year into the name makes "Class 10 across five years" a string search and makes promotion logic parse text. |

### 4.1 A point where the brief confirms the design

The brief's default **income** categories are *Admission Fee, Session Fee,
Monthly Fee, Examination Fee, Book Sale, Donation*. Four of those map one-to-one
onto its **fee** categories.

That is not a coincidence to be tidied away — it is the brief already intending
that **fee collection becomes income**. Doing it by hand means entering every
collection twice, into two lists that will disagree before the first month is
out. The automatic posting of a `Payment` to an `Income` row (`02` §4.6) is
therefore an implementation of the brief, not an addition to it.

---

## 5. The audit: what is whose

### 5.1 Group A — the brief, as given

Branch · User (phone login, branch FK) · Fee · FeeCategory (11 auto-seeded with
notes) · Student · Teacher profile · Daily Attendance · Class Attendance ·
Class (stream/name/year) · Income + default categories · Expense + default
categories · Awliaa admin UI · Awliaa role system · Celery · Traefik · DRF +
React · no Next.js · no Google login · no DB cache · no rate limiting.

### 5.2 Group B — forced by the brief, not optional additions

These are not extra scope. The listed features cannot exist without them:

| Table | Required by |
|-------|-------------|
| `Subject` | "Examinations" — marks are per subject |
| `Mark` | "Examinations" — an exam with no marks table is a calendar |
| `Section` | The brief lists "Section/batch" on Student |
| `Session` | The brief lists it on Student, and "Session Fee" as a category |
| `Guardian` | The brief lists "Guardian" and "Contact information" on Student |

`Guardian` is its own table rather than fields on Student because siblings share
a guardian, and a changed phone number must change in one place. Starting with
guardian columns on Student and splitting later is a migration with duplicate
reconciliation in it — cheap now, tedious later, for a table with six columns.

### 5.3 Group C — structural corrections held firm

The three model changes in §4. Of these, **`Enrolment` and the `Fee`/`Payment`
split are the only two things in this entire document that are expensive to add
later.** Everything else in the design can be bolted on to a running system with
an additive migration. These two cannot: by the time they are needed, there is
history to unpick.

If only two decisions survive this review, they should be these two.

### 5.4 Group D — deferred to V2

Introduced by this design, not by the brief. **Every one is purely additive** —
adding it later means new tables and new code, with no migration of existing
data and no rework of what V1 wrote:

| Deferred | V1 does instead |
|----------|-----------------|
| Notifications / SMS outbox / templates | Nothing. Fee dues and absences are read on screen |
| Payroll (`PayrollRun`, `Payslip`) | Salary is an ordinary `Expense` row under "Teacher Salary" |
| ~~`AuditLog`~~ | **Promoted into V1 as `ActivityLog`** (`08` D8) — it is the data behind the platform admin's live feed |
| Rollup tables (`AttendanceSummary` etc.) | Reports query source rows directly — correct at V1 data volume, just slower |
| `ExportJob` / async exports | Synchronous CSV download, which is fine at this scale |
| Guardian login | Guardians are contact records; staff read the data for them |
| `BranchAccess` (multi-branch users) | A user belongs to one branch, or to the platform admin |
| `LeaveRequest` | Attendance status `leave`, marked by hand |
| `Holiday` calendar | Attendance simply is not taken |
| `FeeStructure` | `AcademicClass.monthly_fee`, as the brief implies |
| ~~`GradeScale` / `GradeBand` / `Result`~~ | **Moved into V1 on 2026-09-11** at the owner's request: an editable scale per বিভাগ (board GPA or Qawmi grades) under Settings → Grading, and results frozen at publish. See `exams/grading.py`. |
| `Discount` (standing) | Per-invoice `discount` amount, entered when raised |
| ~~`StudentCategory`~~ | **Deleted, not deferred** — `Category` is the stream (`08` D2) |
| `Qualification` table | Text field on the staff profile |
| `BranchSetting` | Columns on `Branch` |

---

## 6. The V1 cut line

**Twenty-nine tables. They run the entire yearly loop of §2, end to end.**

| App | V1 tables |
|-----|-----------|
| `accounts` | `User`, `Role`, `ActivityLog` |
| `branches` | `Branch`, `Session`, **`Stream`** |
| `academics` | `AcademicClass`, `Section`, `Subject`, `Enrolment`, `Period`, `ClassRoutine` |
| `students` | `Student`, `Guardian`, `StudentGuardian`, `Admission`, `Document` |
| `staff` | `Teacher`, `Employee`, `TeacherQualification` |
| `attendance` | `DailyAttendance`, `ClassAttendance` |
| `fees` | `FeeCategory`, `Fee`, `Payment` |
| `finance` | `IncomeCategory`, `ExpenseCategory`, `Income`, `Expense` |
| `exams` | `Exam`, `ExamSchedule`, `Mark` |
| **`forms`** | **`FormTemplate`, `Question`, `AdmissionAnswer`, `PrintedForm`** |

*(Grown from the original nineteen: `Stream` arrived with `08` D2, the four
`forms` tables with `07-admission-form.md`, and `StudentCategory` was deleted.
Against the forty in `03-database.md`.)*

Apps `notifications` and `reports` do not exist as Django apps in V1. Report
*screens* do — they live in each module and read that module's own tables.

### 6.1 What V1 can do on day one

- Platform admin creates a branch; its fee, income and expense categories seed
  themselves.
- Sessions and classes are set up; each class carries its monthly fee.
- A student is admitted: application → student → enrolment → admission number →
  admission and session fee invoices raised, in one transaction.
- Teachers and employees are on the system with phone logins and role presets.
- Attendance is taken daily and per class, recording who took it.
- Monthly fees generate themselves on the 1st; overdue fines accrue nightly.
- An accountant collects a fee at the counter, part or full, prints a receipt —
  and the income row posts itself.
- Income and expenses are recorded against seeded categories.
- Exams are scheduled, marks entered per subject, marksheets printed.
- Every screen is branch-scoped; the platform admin sees across branches.

That is the brief, delivered.

### 6.2 What V1 cannot do

No SMS to guardians. No payslips. No guardian login. No audit trail beyond
`created_by`. No async exports. No standing discounts. These are the price of
shipping, they are all in group D, and none of them cost anything to add later.

---

## 7. Open questions — **all closed**

Both questions this section once listed have been answered. See
`08-decisions.md`:

| Was | Answer |
|-----|--------|
| What does `Category` mean on Student? | It **is** the study sector — the stream. One field, now a per-branch `Stream` table. `StudentCategory` deleted. (`08` D2) |
| Attendance corrections — overwrite or keep history? | **Overwrite.** No history in V1. (`08` D3) |

Two further decisions arrived with them and change more than these did:

| | |
|---|---|
| **`08` D1** | **A branch is a whole institution** — school, madrasah or college — and SIES is the platform they run on. Nothing may be hard-coded to one institution. |
| **`08` D4** | **Students may log in optionally** by phone; `/api/me/` is therefore V1, not V2. |

**Nothing blocks coding.** Remaining non-blocking assumptions are listed in
`08` §7.

---

## 8. Revised build order

Replaces the phases in `04-roadmap.md`, which were written against the full
design. Same sequence, shorter.

| Phase | Contents | Done when |
|-------|----------|-----------|
| **0** | Repo, Docker, Traefik, Django `core`, SPA shell from Awliaa | A super admin logs in by phone and sees an empty dashboard |
| **1** | `accounts` + `branches` — User, phone auth, `Role`, permission catalogue, Branch with category seeding, Session | A branch is created and opens with its categories in place |
| **2** | `academics` + `students` + `staff` | A student is admitted end to end and appears on a class roster |
| **3** | `fees` + `finance` — **the reason the system exists** | Fees raise themselves overnight; a counter collection posts its own income |
| **4** | `attendance` | Daily and class attendance, with the register |
| **5** | `exams` | Marks entry grid and printed marksheets |
| **6** | Report screens per module, branch comparison for the platform admin | The brief is delivered |

Phase 3 is the one that matters. It is also the one with the real tests: run
monthly generation twice and assert one invoice; part-pay an invoice and assert
the income total; issue receipts concurrently and assert no duplicate number.

---

## 9. The rule that keeps V1 being V1

Anything not in §6 is V2 until the yearly loop in §2 is running in production
with real students, real fees and real money. The question for any proposed
addition before then is the one from §2:

> **Does the yearly loop complete without it?**

If yes, it waits.
