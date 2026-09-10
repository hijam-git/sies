# 08 — Decisions

Answers given by the owner, and what each one changes. **This file is
authoritative over `00`–`07` wherever they disagree**, alongside
`05-scope-and-v1.md` for scope.

Recorded 2026-09-10.

---

## D1 · A Branch is a whole institution. This is a platform.

> *"A branch means a School / madrasah / college / a full platform."*

The earlier docs assumed one institution with several campuses. That was wrong.
**Each branch is a complete, independent educational institution** — a school, a
madrasah, or a college — and SIES is the platform they all run on.

### What this changes

| Was | Now |
|-----|-----|
| "Head office" = the institution's own central office | **Platform admin** = the operator of SIES; sees across institutions |
| Streams fixed to `hifz` / `qaumi` / `general` | **Streams are per-institution and open-ended** — a college has Science / Commerce / Arts, not Hifz. See D2 |
| Seed Dasherbari's real classes and fees | **Seed nothing institution-specific.** Defaults are generic and every one is editable |
| One admission form template | **A default template per institution type** — madrasah, school, college — each editable |
| Class names could be a fixed list | Free text per institution. `Nazera` and `Class 6` and `Honours 1st Year` all live in the same column |

### What does *not* change

The architecture was already right for this, which is the useful part: one
database with a `branch_id` column, a base queryset that scopes every viewset,
per-branch number sequences, per-branch seeded categories. Those decisions
(`01` §5) hold exactly as written. Only the *meaning* of the word "branch"
widens.

### Consequences to carry through

1. **`Branch` gains `institution_type`** — `madrasah` / `school` / `college` /
   `combined`. It selects which defaults get seeded and which labels the UI
   shows (মুহতামিম vs Principal, জামাত vs Class).
2. **Onboarding a new institution is a first-class flow**, not a one-off admin
   task: create branch → pick type → seeded categories, streams, classes and
   form template → create its first admin user. One screen, one transaction.
3. **Nothing may be hard-coded to a madrasah.** Every Bangla/Arabic label, every
   pledge line, every fee category name is data, not code.
4. **The term "branch" stays** in code and URLs, because it is the owner's word
   and renaming it later is churn. `docs/00` §1 is updated to define it as
   *"an institution on the platform"*.
5. **Cross-institution reporting is the platform admin's view**, and it must be
   explicitly permission-gated — the operator can see it; no institution's own
   principal ever can. `01` §5.2 already says this; it matters more now, because
   the institutions are unrelated organisations rather than sibling campuses.

> **Question this raises, not blocking:** are these institutions unrelated
> customers (true multi-tenant SaaS — needing per-institution billing,
> self-signup, data-export-on-leave), or a group of institutions under one
> owner? Assumed **one owner, many institutions** for now. If they are paying
> customers, subscriptions come back into scope and Awliaa has that code.

---

## D2 · `Category` means the study sector — it is the stream

> *"Means Hafj / Quami / General, the student's study sector."*

The original brief listed **Student Type (Hafj, Quami, General)** and
**Category** as two fields. They are one field. There is no orphan/free/waiver
dimension in V1.

### What this changes

- **`StudentCategory` is deleted** from the design. It does not exist in V1 or
  V2. The automatic-discount-by-category idea goes with it.
- `Student.stream` and `Student.category` collapse into **one field**.
- **Combined with D1, it cannot be a fixed enum of three.** A college's sectors
  are Science / Commerce / Arts; a school's may be nothing at all. So:

### `Stream` becomes a per-branch lookup table

```
Stream  [branch-scoped]
  branch      → Branch
  code        Char(20)    hifz · qaumi · general · science · commerce …
  name        Char(60)    "Hifz"
  name_bn     Char(60)    "হিফজ"  ← the branch's own label, e.g. "হাফজ"
  order       Int
  is_active   Bool
  unique_together (branch, code)
```

Seeded on branch creation from `institution_type`:

| Institution type | Seeded streams |
|------------------|----------------|
| `madrasah` | Hifz · Qaumi · General |
| `school` | General |
| `college` | Science · Commerce · Arts |
| `combined` | Hifz · Qaumi · General · Science · Commerce · Arts |

`Student.stream`, `AcademicClass.stream`, `Session.streams`, `Subject.stream`
and `GradeScale.stream` all become **FKs to `Stream`** instead of char choices.

**Why a table and not a JSON list on Branch:** these are pointed at by five
other models and filtered on constantly. A FK gives referential integrity and an
index; a JSON list gives neither, and a typo'd stream string would silently
create a sixth stream nobody can find.

This also retires the "Hafj = Hifz?" question from `05` §7 — the branch types its
own label into `name_bn` and gets whatever spelling it uses.

### D2a · The three canonical streams are confirmed

> *Owner, on the original stream table: "is okay."*

The three streams and their meanings are correct and stand as the canonical set
a **madrasah** is seeded with (`00` §1):

| Stream | Meaning |
|--------|---------|
| `hifz` | Qur'an memorisation (written "Hafj" in the brief) |
| `qaumi` | Qaumi madrasah curriculum (Ibtidaiyyah → Dawra) |
| `general` | National curriculum (Class 1–10, SSC etc.) |

**This does not conflict with the `Stream` table.** The table exists so each
institution can type its own Bangla label for these three, and so a school or
college (D1) can have sectors that are not these. For every madrasah on the
platform, the seeded streams are exactly the three above.

---

## D3 · Attendance corrections overwrite the cell

> *Chosen: overwrite.*

`DailyAttendance` and `ClassAttendance` are updated in place. `status`,
`taken_by` and `taken_at` are overwritten; `updated_at` records when. No history
table, no correction rows.

**Accepted consequence, stated plainly:** the system cannot answer *"what was
this cell before it was changed, and who changed it"*. If that is ever needed,
it needs the activity log — which **D8 has since brought into V1**, so a
correction is in fact recorded there with before and after. See D8.
That is the price of V1 shipping sooner, and it was chosen knowingly.

The bulk register endpoint (`02` §5.1) therefore upserts, which it already did.
Nothing else changes.

**Closes** `05` §7.2.

---

## D4 · Students may log in, optionally, with their phone

> *"Student can login with his phone number if wants."*

- `Student.user` is a **nullable OneToOne** to `User`, exactly as designed. Most
  young students will not have one.
- Creating the login is an action on the student record ("enable login"), not a
  requirement of admission. A student with no phone is admitted normally.
- **`/api/me/` is in V1**, not deferred. A logged-in student sees their own
  profile, fee dues and payment history, attendance summary, and published
  results.

**The rule from `02` §2.5 stands and matters more now:** self-service is *not* a
weak staff permission. `/api/me/` filters to `request.user`'s own records and
grants nothing else. A student must never be able to reach another student's row
by changing an id — which is exactly what modelling this as `students.view`
would allow.

Guardian login remains V2 (`05` §5.4). Guardians are contact records in V1.

---

## D5 · Teacher and Employee are separate models

> *"Make Teacher different, teacher may have grading system etc. later, and I
> provided teacher fields."*

The earlier design merged both into one `StaffProfile` with an
`employment_type` flag. **Overruled.** `Teacher` and `Employee` are two models,
two tables.

The reason given is the right one: a teacher is going to grow features an
employee never has — evaluation and grading of teachers, subject expertise,
class load, lesson records. Keeping them in one table means every one of those
becomes a column that is null for half the rows, and the "which type is this"
check spreads through the codebase until nobody can add a teacher feature
safely.

### Shared fields live in an abstract base, not a shared table

Both models carry the same twenty-odd identity, contact, salary and employment
fields. Those are defined **once**, in an abstract Django model, so the two
tables cannot drift:

```python
class PersonProfile(BranchScopedModel):      # abstract = True
    user, name, name_bn, photo, dob, gender, nid, blood_group,
    phone, alt_phone, email, village, post_office, upazila, district,
    designation, joining_date, leaving_date, employment_status,
    basic_salary, allowances, deductions, bank_account, mobile_banking,
    emergency_contact_name, emergency_contact_phone
    class Meta: abstract = True

class Teacher(PersonProfile):   teacher_id,  streams(M2M), …
class Employee(PersonProfile):  employee_id, department, duty_shift, …
```

Abstract inheritance, **not** multi-table inheritance: each gets a clean,
independent table with no implicit join, and the field definitions stay in one
place. Adding a shared field is one edit and two migrations.

### What this costs, and how it is paid

Three models now reference "a person", where two did before:

- **`DailyAttendance`** takes `person_type` (`student` / `teacher` /
  `employee`) plus **three** nullable FKs, with a check constraint that exactly
  one is set. It already used this pattern for two; extending to three changes
  the constraint, not the design.
- **`Payslip`** (V2) points at teacher **or** employee, same pattern.
- **A person who moves from teaching to non-teaching** needs a new `Employee`
  row; their `Teacher` row is closed with `leaving_date` and
  `employment_status='transferred'`. Their attendance and payroll history stays
  attached to whichever row it was recorded against, which is honest — it did
  happen under that role.

That last point is the accepted cost of this decision, stated plainly. It is
rare, and the alternative cost — teacher features polluting a shared table — is
paid every week instead of once a year.

### Both stay in the `staff/` app

Two models, one Django app. They share serializer helpers, the salary service
and the staff-attendance views; splitting the app would duplicate those without
buying anything. The **UI** shows Staff → Teachers and Staff → Employees as
separate screens, as the brief lists them.

### Reserved for later, per the reason given

`TeacherEvaluation` and `TeacherGrade` are **V2**, not designed here — but the
separate `Teacher` table is what makes them cheap to add. Noted so the intent is
not lost.

Full field lists are in `03-database.md` §5.

---

## D6 · Admin assigns teachers to classes — and the assignment is an access scope

> *"Admin can assign teacher to class, which class he is responsible."*

Two different assignments exist, and they are not the same thing:

| Assignment | Meaning | Where |
|------------|---------|-------|
| **Class responsibility** | This teacher is *in charge of* this class — the class teacher / শ্রেণি শিক্ষক | `AcademicClass.class_teacher` → Teacher, and `Section.in_charge` → Teacher |
| **Subject teaching** | This teacher teaches *this subject* to this class/section | `SubjectAssignment` (§3) |

Both are **per session**, because `AcademicClass` is itself per session. A
teacher who is class teacher of Class 5 in 2026 and Class 6 in 2027 has two
rows, and the 2026 record stays correct forever. No history table is needed —
this falls out of the existing design.

### The part that matters: assignment limits what a teacher can reach

A permission answers *what verb*. An assignment answers **which classes**. Both
gates apply:

```
can this teacher take attendance?   → permission:  attendance.take
for THIS class?                     → assignment:  is it one of theirs?
```

Without the second gate, giving a teacher `attendance.take` lets them mark
**every class in the institution**, and `marks.enter` lets them enter marks for
subjects they do not teach. That is not a theoretical risk; it is the normal
consequence of role-only access control in a school system.

**A teacher's class scope** is the union of:

1. classes and sections where they are `class_teacher` / `in_charge`, and
2. classes where they hold a `SubjectAssignment`,

for the **current session**. Concretely:

| Action | Allowed for |
|--------|-------------|
| Daily attendance | Classes they are in charge of |
| Class (period) attendance | Classes where they teach that subject |
| Marks entry | Only the subjects they are assigned |
| Student list | Students enrolled in their scoped classes |
| Everything else | As their permissions allow |

Principals, accountants and the platform admin are **not** scoped this way —
they see the whole institution. The scope applies to the `teacher` user type.

### One switch, because small institutions differ

`Branch.restrict_teachers_to_assigned_classes` — **default `true`**. A small
madrasah where three teachers cover everything can turn it off and let any
teacher mark any class. Making this a setting rather than a hard rule means the
strict default protects the institutions that need it without obstructing the
ones that do not.

### Consequences

- `TeacherScopedMixin` sits alongside `BranchScopedViewSet` on the attendance,
  marks and student viewsets. Same 404-not-403 rule.
- **Out-of-scope classes do not appear** in the class picker on the attendance
  and marks screens — the teacher sees only their own, so the restriction reads
  as a shorter list rather than an error.
- The dashboard shows a teacher **their** classes: today's attendance not yet
  taken, marks not yet entered.
- New UI: **Staff → Assignments** — pick a session, then set each class's class
  teacher and each subject's teacher. One screen, and it is what makes the
  scoping above meaningful.
- A `SubjectAssignment` referencing a teacher from another branch, or a class
  from another session, is rejected at validation.

### What this does *not* add

No new tables. `AcademicClass.class_teacher`, `Section.in_charge` and
`SubjectAssignment` already existed; D6 defines what they *mean* for access and
adds the assignment screen. A single FK per class assumes **one** responsible
teacher — if an institution needs a co-class-teacher, that becomes a
`ClassTeacher` table in V2.

---

## D7 · The teacher's panel is a live "today's classes" board

> *"The class he is assigned will show in his admin panel with class info (name,
> time, student count). After class starts he can click to enter and start
> attendance during the class duration."*

This is the teacher's home screen, and it exposes a real gap: **the design had
no timetable.** `SubjectAssignment` (D6) records *who teaches what to which
class*; it does not record *when*. "Time" and "during the class duration" both
require a routine.

### Two new tables

**`Period`** — the institution's bell schedule, defined once.

```
Period  [branch-scoped]
  branch      → Branch
  stream      → Stream, null      null = applies to all streams
  name        Char(30)            "1st Period", "প্রথম ঘণ্টা", "Fajr Sabaq"
  order       Int
  start_time  Time
  end_time    Time
  is_break    Bool                tiffin / prayer breaks occupy a slot
  unique_together (branch, stream, order)
```

A table rather than times on each routine row: a madrasah changing its bell
schedule in Ramadan edits **eight rows, not five hundred**. `stream` is nullable
because a hifz stream often starts after Fajr while the general stream starts at
nine.

**`ClassRoutine`** — the weekly timetable.

```
ClassRoutine  [branch-scoped]
  branch, session   → Branch, Session
  academic_class    → AcademicClass
  section           → Section, null
  subject           → Subject
  teacher           → Teacher
  period            → Period
  day_of_week       Int      0=Sat … 6=Fri (BD week)
  room              Char, blank
  is_active         Bool

  unique_together (branch, session, academic_class, section, day_of_week, period)
  unique_together (branch, session, teacher, day_of_week, period)
```

**The second constraint is the valuable one:** a teacher cannot be in two rooms
at once. Timetable clashes are the classic school-software bug, and this makes
the database refuse them rather than leaving it to a validator someone forgets
to call.

### The teacher's dashboard

```
আজকের ক্লাস · Saturday, 12 September                     3 of 5 taken

┌────────────────────────────────────────────────────────────────┐
│ ✓ 1st Period  08:00–08:45   Class 5 · A   Qur'an       32 students │
│ ✓ 2nd Period  08:45–09:30   Class 6 · B   Hadith       28 students │
│ ● 3rd Period  09:30–10:15   Class 5 · A   Fiqh         32 students │
│                                          [ Take attendance → ]    │
│ ○ 5th Period  11:00–11:45   Class 7      Arabic        25 students │
│ ○ 7th Period  13:00–13:45   Class 6 · B  Tafsir        28 students │
└────────────────────────────────────────────────────────────────┘
   ✓ taken   ● live now   ○ upcoming   ! missed
```

Each row carries exactly what was asked for — **name, time, student count** —
plus the state, which is what makes the board useful rather than decorative.
Student count is `Enrolment.objects.filter(...).count()`, computed, never stored.

The **Take attendance** button is live only on the current period. Clicking it
opens the roster for that one class, defaulted to present, and one submit writes
`ClassAttendance` rows.

### The attendance window

Attendance for a period may be taken from `start_time` until `end_time` plus a
grace, set by `Branch.attendance_window_minutes` (**default 120** — generous on
purpose).

- **Inside the window** — the teacher takes it, needing only `attendance.take`.
- **Outside it** — the button is gone. The period shows `!` missed, and it takes
  `attendance.update` (class teacher, principal) to fill in afterwards.

The window is a guard against a period being marked days later from memory, not
a punishment. Connectivity fails and teachers get busy, so the default is wide
and a principal can always correct. An institution that wants it strict sets it
to 15; one that wants it off sets it to 0 for unlimited.

### How this fits the two attendance paths

Both already existed; the routine just gives the second one its trigger.

| Path | Who | Writes | Entry point |
|------|-----|--------|-------------|
| **Month register grid** (`02` §4.4) | Class teacher | `DailyAttendance` | Attendance → Register |
| **Live period attendance** | Subject teacher | `ClassAttendance` | This dashboard |

An institution that takes attendance once a day uses the grid and ignores the
board; one that takes it per period uses the board. Both are supported without
either being bolted onto the other.

### Consequences

- **V1 grows to 28 tables** — `Period` and `ClassRoutine`. (D8 then adds
  `ActivityLog`, making it 29 — see '08' §5 for the final list.)
- New screen **Academics → Routine**: a weekly grid per class, with clash
  detection surfaced as you edit rather than on save.
- The teacher's dashboard replaces the generic overview for the `teacher` user
  type. A teacher opening the system sees their day, not a chart.
- `ClassAttendance.period` becomes a **FK to `Period`** instead of a loose
  integer.
- Phase 4 (attendance) gains the routine; **`Period` and `ClassRoutine` are
  built in Phase 2** with the rest of academics, because the dashboard and the
  timetable screen both depend on them.
- A period with `is_break=True` never appears on the teacher's board.

---

## D8 · The platform admin sees all activity, live

> *"And main admin (super admin) can see realtime all activity in admin panel."*

**`AuditLog` moves from V2 into V1**, renamed **`ActivityLog`** because it is now
a feature people look at, not just a forensic record. It is the data behind the
live feed.

### What counts as activity

**State changes and logins. Never reads.** A feed carrying every page view is
noise nobody watches, and it would be the largest table in the database within a
month.

| Logged | Examples |
|--------|----------|
| Money | Fee collected · fee waived · income · expense · receipt reversed |
| People | Student admitted · student withdrawn · teacher added · employee added |
| Academic | Attendance taken · marks entered · **results published** |
| Access | Login · failed login · permission changed · role changed · user created |
| Setup | Branch created · session opened · fee category edited |

### The table

```
ActivityLog   [global, append-only — no update, no delete, ever]
  user           → User, null          who
  branch         → Branch, null        where (null = platform-level)
  action         Char   create · update · delete · login · login_failed
                        · collect · waive · publish · take_attendance
  model          Char   "Payment"
  object_id      Char
  object_label   Char   "Receipt RCP-DHK-2026-00412"
  summary        Char   "Collected ৳1,200 from Abdullah Rahman (Class 5)"
  summary_bn     Char
  before, after  JSON   only for update
  ip, user_agent Char
  created_at     DateTime  db_index
```

`summary` is written at log time, not rendered later, so the feed is one query
with no joins and stays readable even after the underlying row changes.

**Indexes:** `(created_at DESC)` · `(branch, created_at DESC)` ·
`(user, created_at DESC)` · `(model, object_id)`.

**Retention:** a nightly Celery task prunes rows older than
`Branch.activity_retention_days` (default **180**). This table grows faster than
any other and is the one most likely to become a problem if left alone.

### "Realtime" means polling, and that is the right answer

The live feed is a **cursor poll every 5 seconds**, not WebSockets:

```
GET /api/activity/?since=<last_id>&branch=&user=&action=
  → { items: [...], last_id: 88214 }
```

Why not Django Channels and WebSockets:

- It would add an ASGI server, a channel layer and a second deployment shape,
  for an audience of a handful of platform admins watching a feed.
- A 5-second delay is invisible to a human reading a list of events. This is a
  monitoring board, not a chat application or a trading screen.
- **Awliaa already proves the pattern** — its `useBadgeCounts` polls on an
  interval and refreshes on tab focus, for exactly this class of "what is
  waiting" display.

The endpoint is cursor-based rather than time-based so nothing is missed or
duplicated across polls. The UI pauses polling when the tab is hidden, and shows
"paused — N new" rather than silently reordering the list under someone's cursor.

**When to revisit:** if a future feature needs true push — a live chat, or a
second person's edit appearing mid-form — that is the moment to add Channels,
and this feed rides along on it. Not before.

### It is branch-scoped like everything else

New permission **`activity.view`**.

| Who | Sees |
|-----|------|
| Platform admin | Every institution — the feed asked for here |
| Principal (if granted) | Their own institution only |
| Everyone else | Nothing |

The same `BranchScopedViewSet` rule applies, so a principal cannot read another
institution's feed by removing a filter.

### The screen

**Live Activity**, platform-admin nav:

```
সরাসরি কার্যক্রম · Live Activity          ● live      [ Pause ]

  14:32:07  Dasherbari    Accountant Karim   Collected ৳1,200 · Abdullah Rahman
  14:31:55  Dasherbari    Teacher Yusuf      Attendance taken · Class 5 A · 32
  14:31:12  Sirajganj     Principal Habib    Published results · Half-Yearly
  14:30:48  Dasherbari    Admin              Permission changed · Yusuf +fees.collect
  14:29:33  Sirajganj     Teacher Nasir      Login
```

Filters: institution · person · action type · date range. Money rows are tinted,
failed logins and permission changes flagged — those are what an owner actually
watches for. A compact five-row version sits on the platform-admin dashboard.

### Where the logging happens

In **`services.py`**, at the same place the transaction commits — not in Django
signals. A signal fires during fixture loads and test setup and would fill the
feed with events nobody performed. Ordinary CRUD is covered by a mixin on
`BranchScopedViewSet`; money and academic operations log explicitly with a
written summary.

**Logging never breaks the operation it records.** The write is inside the
transaction for money (so a rolled-back payment logs nothing), and failures
elsewhere are swallowed with an error-log line. A broken feed must not stop a
teacher taking attendance.

### A welcome side effect — this softens D3

D3 accepted that attendance corrections overwrite with no history. With
`ActivityLog` in V1, a correction is now **logged** with `before` and `after`.
The register still shows only the current value, but *"who changed my son's
attendance, and from what"* has an answer after all — one of the few times extra
scope pays back an accepted compromise.

### Consequences

- **V1 grows to 29 tables.** `ActivityLog` moves out of the V2 list.
- `Branch` gains `activity_retention_days` (default 180).
- Built in **Phase 1** with `accounts`, because every later phase must log into
  it as it is written. Retrofitting logging across nine apps afterwards is how
  half the events end up missing.

---

## 5. Net effect on the V1 table list

`05` §6 listed 19; `07` added 4 for the printable form; D2 adds `Stream` and
removes `StudentCategory`.

**V1 is now 29 tables** (D5 split StaffProfile into Teacher + Employee and added TeacherQualification):

| App | Tables |
|-----|--------|
| `accounts` | User · Role · **ActivityLog** |
| `branches` | Branch · Session · **Stream** |
| `academics` | AcademicClass · Section · Subject · Enrolment · **Period · ClassRoutine** |
| `students` | Student · Guardian · StudentGuardian · Admission · Document |
| `staff` | **Teacher · Employee · TeacherQualification** |
| `attendance` | DailyAttendance · ClassAttendance |
| `fees` | FeeCategory · Fee · Payment |
| `finance` | IncomeCategory · ExpenseCategory · Income · Expense |
| `exams` | Exam · ExamSchedule · Mark |
| `forms` | FormTemplate · Question · AdmissionAnswer · PrintedForm |

*(33 rows counting joins and lookups; 29 are the ones anyone thinks of as a
model.)* **`StudentCategory` is removed.**

---

## 6. Both blocking questions are now closed

`05` §7 listed two. D2 closes the first, D3 closes the second. **Nothing blocks
the start of coding.**

---

## 7. Remaining assumptions — say if any is wrong

None of these blocks a start; each is recorded so it can be corrected cheaply.

| # | Assumption |
|---|------------|
| 1 | Bangla is the default UI language; English is the toggle |
| 2 | The institutions belong to one owner, not paying customers (D1's open question) |
| 3 | Fee amounts are set per institution, per class, per session |
| 4 | Hostel, food and transport are fee categories driven by flags on `Enrolment`, not modules |
| 5 | One VPS, one domain, Traefik TLS, Postgres in a container |
| 6 | An institution's classes are entered by its own admin, not seeded from a national list |
| 7 | SMS is V2; V1 shows dues and absences on screen only |

---

## 8. Docs that need patching to match

| Doc | Patch |
|-----|-------|
| `00` §1 | Define "branch" as *an institution on the platform*; streams are per-branch, not a fixed three |
| `01` §5, §6 | "Head office" → "platform admin"; add `branches.Stream`; `forms/` app |
| `02` §1 | Actor table: platform admin vs institution principal |
| `03` §1 | `Branch` gains `institution_type`, `name_ar`, `established_year`; **delete `StudentCategory`**; add `Stream`; `Student.category` → FK `Stream`; split address into village/post_office/upazila/district (`07` §4) |
| `03` §6 | Note the overwrite decision (D3) |
| `05` §6, §7 | Table list → 24; both open questions closed |
| `07` | Default form template is seeded **per `institution_type`** |
| `CLAUDE.md` §9 | Replace the open questions with a pointer to this file |
