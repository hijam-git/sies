# 04 — Build Order & Open Questions

> **Partly superseded.** The phases in §1 were written against the full design.
> `05-scope-and-v1.md` §8 replaces them with the shorter V1 sequence, and `05`
> §7 replaces the open questions in §3 with the two that actually block a start.
> **§2 (testing) and §4 (risks) below still stand in full** — they are about how
> to build, not what.

---

## 1. What to build, in order

The ordering rule: **nothing is built before the thing it depends on, and each
phase ends with something a real user can use.**

### Phase 0 — Skeleton (foundation)

- Repo layout, `docker-compose.dev.yml`, Traefik on `*.localhost`.
- Django project + `core` (settings, celery, urls, exception handler,
  `BranchScopeMiddleware`), Postgres, Redis.
- Vite React SPA scaffolded from `awliaa/frontend/admin_dashboard`, with
  `lib/api.ts`, `lib/auth-context.tsx`, `lib/i18n`, `components/common/*` and
  `DashboardLayout` ported and stripped of Awliaa's pages.
- **Done when:** a super admin can log in with a phone number and see an empty
  dashboard shell.

### Phase 1 — Identity & branches

`accounts` + `branches`. User, phone login, Role, permission catalogue endpoint,
`BranchAccess`, `ActivityLog`, Branch CRUD with the category-seeding signal,
Session, Holiday.

**Done when:** the platform admin can create a branch, and that branch opens with its
fee, income and expense categories already in place.

### Phase 2 — Academic spine

`academics` + `students` + `staff`. Classes, sections, subjects, enrolment,
student records, guardians, admissions, staff profiles.

**Done when:** a student can be admitted end to end and appears on a class roster.

### Phase 3 — The money (the reason the system exists)

`fees` + `finance`. Fee structure, invoices, the **Collect fee** screen and
receipt, discounts, income/expense, the auto-posting of payments to income.
Celery: monthly generation, nightly fines.

**Done when:** a month's fees raise themselves overnight, an accountant collects
one at the counter, and the income statement already shows it.

### Phase 4 — Attendance

Daily and class attendance, the take-attendance screen, leave, absence SMS,
the nightly summary rollup.

### Phase 5 — Examinations

Exams, schedules, marks entry grid, grade scales per stream, publish + rank
computation, marksheets and tabulation sheets.

### Phase 6 — Reports & notifications

The report families in `02` §4.8, async PDF/Excel export, notice board, bulk
SMS, templates, cross-institution branch comparison.

### Phase 7 — Hardening

Backups, staging→prod promotion, audit-log review screen, permission-matrix
review, load check on the collect-fee and marks-entry paths.

---

## 2. Testing the parts that can hurt someone

Ordinary CRUD gets ordinary tests. These get deliberate ones:

- **Branch isolation** — per module, assert a branch-A user gets **404** (not
  403) for a branch-B object, on read *and* write.
- **Idempotency** — run monthly fee generation twice; assert one invoice.
- **Money arithmetic** — part payments, discount + fine interaction, over-payment
  rejection, receipt reversal.
- **Phone normalisation** — all four input forms resolve to one account.
- **Permission fallback** — a user with an empty `permissions` list behaves
  exactly as their role preset says.
- **Rank computation** — ties, absentees, optional subjects, failed subjects.

`CELERY_TASK_ALWAYS_EAGER=1` under test, as Awliaa does.

---

## 3. Open questions — need your answer before Phase 1

| # | Question | Default if you don't answer |
|---|----------|------------------------------|
| 1 | Is **"Hafj" = Hifz**? | Yes. Code `hifz`, label configurable per branch |
| 2 | Do **guardians get their own login**? | No for Phase 1 — SMS only. Model supports it later |
| 3 | Do **students get a login**? | Yes, optional per student (`Student.user` nullable) |
| 4 | Which **SMS gateway**? | Adapter interface with one Bangladeshi provider; swappable |
| 5 | Do the qaumi and general streams share a **session/year**, or run separate calendars? | Separate — `Session.streams` supports both |
| 6 | Should **fee amounts** come from the class (`FeeStructure`) or be per student? | Class, with per-student `Discount` on top |
| 7 | **Fine rule** — flat per day, percentage, capped? | Per-branch JSON `{per_day, grace_days, max}` |
| 8 | Is there an **expense approval** step, and above what amount? | Optional per-branch threshold, off by default |
| 9 | Does the institution need **hostel and transport as modules**, or only as fee heads? | Fee heads only, for now — flags on `Enrolment` |
| 10 | **Mobile app** for teachers taking attendance? | Not in scope; the SPA is responsive |

Question 2 is the one that changes the most work, because a guardian login means
a second self-service surface and a second permission story.

---

## 4. Risks

| Risk | Mitigation |
|------|------------|
| A beat job double-charges guardians | Unique constraint on the invoice grain; idempotency test in CI (§2) |
| Branch data leaks across branches | Scoping in the base viewset *and* the queryset; 404-not-403 tests per module |
| Receipt numbers duplicate at a busy counter | Row-locked sequence, never `max()+1` |
| The permission catalogue in the SPA drifts from the backend | The SPA fetches it; there is no second copy |
| SMS costs run away on a bulk send | Outbox rows carry cost; per-branch monthly cap with a warning before send |
| Scope creep back toward Awliaa's SaaS features | `00-overview.md` §3 is the list of things this system is not |
