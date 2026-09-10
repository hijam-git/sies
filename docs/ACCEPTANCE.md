# Acceptance — what "all phases finished and tested" means

The gate this project has to pass before it is handed over. Nothing here is
optional, and nothing counts as done because an agent reported it done — every
line is checked by running it.

**Status:** in progress. Ticks are only added after the check has actually run.

---

## 1. Every phase ships four things, not one

A phase is complete when **all four** exist. Backend-with-placeholder-UI is half
a phase reported as a whole one, which already happened once (`CLAUDE.md` §2a).

| | Models + migrations | API | **Screens** | Seed data proving it |
|---|---|---|---|---|
| 1 · accounts + branches | ✅ | ✅ | ✅ | ✅ |
| 2 · academics + students + staff | ✅ | ✅ | ✅ | ✅ |
| 2 · forms (printable admission form) | ✅ | ✅ | ✅ | ✅ |
| 3 · fees + finance | ✅ | ✅ | ✅ | ✅ |
| 4 · attendance | ✅ | ✅ | ✅ | ✅ |
| 5 · exams | ✅ | ✅ | ✅ | ✅ |
| 6 · reports + teacher dashboard | ✅ | ✅ | ✅ | ✅ |
| 7 · deploy + hardening | — | — | — | — |

---

## 2. The tests that are the point

Ordinary CRUD gets ordinary tests. **These are the ones that justify the
project's design, and each must exist and pass:**

- [x] **Fee idempotency** — `generate_monthly_fees` twice ⇒ ONE invoice per
      (student, category, period). The constraint that makes a retried beat job
      safe.
- [x] **Receipt-number concurrency** — several threads collecting at once get
      distinct consecutive numbers. No gaps, no duplicates.
- [x] **Income auto-posting is atomic** — a collection writes exactly one Income
      row; a rolled-back collection writes **neither**.
- [x] **Money arithmetic** — part payments, `payable = amount − discount + fine`,
      over-collection refused, every status transition in `docs/06` #8.
- [x] **Fines** — accrue while overdue, respect grace, respect the cap, stop on
      payment.
- [x] **Attendance is idempotent and server-authoritative** — same batch twice ⇒
      same rows; a future date or off day is rejected into `skipped`, never
      written, however the client was persuaded to send it.
- [x] **Attendance window** — inside it `attendance.take` suffices; outside it
      needs `attendance.update`.
- [x] **Teacher scoping (D6)** — a teacher cannot mark attendance for, or enter
      marks in, a class or subject they are not assigned.
- [x] **Timetable double-booking** — the database refuses a teacher in two rooms
      at once.
- [x] **Marks** — one mark per (exam, student, subject); invisible before
      publish; publish is principal-only.
- [x] **Branch isolation, every module** — a branch-A user gets **404, not 403**,
      for a branch-B row, on read *and* write. 403 confirms the row exists.
- [x] **Phone normalisation** — all four input forms resolve to one account.
- [x] **Permission fallback** — empty list ⇒ preset; explicit list wins and is
      never merged; inactive user ⇒ no permissions; a stale permission string is
      dropped.
- [x] **`/api/me/` isolation** — a student cannot reach another student's record
      by changing an id.
- [x] **Printed form** — `blank` renders rules where `filled` renders values;
      `PrintedForm.snapshot` still shows the OLD values after the student record
      changes; an unknown placeholder is rejected when the template is saved.
- [x] **`admit_student` atomicity** — forced failure partway writes nothing.

---

## 3. Whole-system checks

- [x] `manage.py check` clean
- [x] `makemigrations --check --dry-run` reports **no drift**
- [x] Migrations apply to an **empty** database AND to the existing seeded one
- [x] **Full backend suite green, in Docker, on Postgres**
- [x] `tsc -b` · `eslint .` · `vite build` · `vitest` all clean
- [x] No `FloatField` anywhere; money is `Decimal` end to end
- [x] No signals (`CLAUDE.md` §4.3)
- [x] Every V1 nav entry reaches a real screen — no `PhasePlaceholder` left on a
      feature whose backend is live
- [x] Celery beat schedule populated and the worker consumes both queues

---

## 4. The demo the owner actually opens

One seeded institution that exercises the whole yearly loop, so the system can
be judged by using it rather than by reading a report:

- [x] A madrasah with its three streams and a current session
- [x] Classes across all three streams, with sections and subjects
- [x] A bell schedule and a weekly routine with no clashes
- [x] Teachers **assigned** to classes and subjects — so scoping is visible
- [x] Employees
- [x] Students enrolled with rolls, guardians, and structured addresses
- [x] A month of attendance already marked
- [x] Fees generated, some collected, some overdue with fines — and the income
      ledger agreeing with the receipts **without anyone having typed it twice**
- [x] An exam with marks entered
- [x] **Logins handed over: a platform admin, a principal, a teacher, a student**

---

## 5. Stated honestly, not quietly

Two things are still owed and will be reported as owed rather than glossed:

- [ ] **Responsiveness verified by rendering**, at 360 / 390 / 768 / 1280 — not
      by auditing the emitted CSS, which is all that has happened so far (F16).
- [ ] **A restore actually performed** from `auto_backup.sh` output. A backup
      never restored is not a backup (F6).
