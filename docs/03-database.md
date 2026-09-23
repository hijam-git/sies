# 03 — Database Design

Every table, field by field. Types are Django field types; `→` is a ForeignKey.
Read `01-architecture.md` and `02-system-design.md` first — this file assumes
the branch-scoping rule and the module behaviour they describe.

> ## Scope: this file describes the FULL design
>
> `05-scope-and-v1.md` is the scope authority and `08-decisions.md` overrides
> both. **V1 is 29 tables** — the list is in `08` §5.
>
> **Deferred to V2:** `BranchAccess` · `Holiday` · `BranchSetting`
> · `Qualification` · `LeaveRequest` · `AttendanceSummary` · `FeeStructure` ·
> `Discount` · `PayrollRun` · `Payslip` · `GradeScale` · `GradeBand` · `Result`
> · everything in §10 (Notifications) and §11 (Reports rollups).
>
> **Deleted entirely:** `StudentCategory` (`08` D2).
> **Added since first draft:** `Stream`, `Period`, `ClassRoutine`, `Employee`,
> `TeacherQualification`, and the four `forms/` tables
> specified in `07-admission-form.md`.
>
> See `05` §5.4 for what V1 does instead of each deferred table.

**Conventions applied to every table below** (not repeated per model):

- `id` BigAutoField.
- `created_at`, `updated_at` — auto timestamps.
- `created_by`, `updated_by` → `User`, nullable, `SET_NULL`.
- `is_active` BooleanField for soft delete on anything with history.
- Money is `DecimalField(max_digits=12, decimal_places=2)` — never float.
- Branch-scoped models inherit `BranchScopedModel` (supplies `branch` +
  the scoped manager). Marked **[BS]** below.
- Bilingual names store `name` (English) and `name_bn`.

---

## 1. Global tables (not branch-scoped)

### `Branch`

The tenant boundary. Everything else hangs off it.

| Field | Type | Notes |
|-------|------|-------|
| `name`, `name_bn`, `name_ar` | Char(150) | Arabic name prints on the letterhead (`07` §1) |
| `institution_type` | Char choices | `madrasah` / `school` / `college` / `combined`. **Selects which streams, classes, labels and form template get seeded** (`08` D1) |
| `code` | Char(10) unique | `DHK`, `CTG` — used in every generated number |
| `established_year` | Int, null | Prints on the letterhead |
| `address`, `address_bn` | Text | |
| `district`, `thana` | Char(80) | |
| `phone`, `alt_phone` | Char(20) | |
| `email` | Email, blank | |
| `logo` | Image, blank | Appears on receipts and marksheets |
| `head` | → `User`, null | Principal |
| ~~`streams`~~ | — | **Removed.** Streams are now the `Stream` table, §2 (`08` D2) |
| `current_session` | → `Session`, null | Default for new records |
| `fine_rule` | JSON | `{per_day, grace_days, max}` — drives the nightly fine job |
| `attendance_window_minutes` | Int, default **120** | How long after a period ends attendance may still be taken (`08` D7). `0` = unlimited |
| `restrict_teachers_to_assigned_classes` | Bool, default **True** | A teacher reaches only the classes they are assigned to (`08` D6). Turn off for a small institution where everyone covers everything |
| `weekly_off_days` | JSON list | `["fri"]`. **V1**, not V2: the month attendance grid (`02` §4.4) shows four or five of them on screen at once, so it cannot wait for the holiday calendar |
| `sms_enabled` | Bool, default True | The institution's own switch. The platform's is the gateway: `SMS_PROVIDER=console` sends nothing |
| `sms_on_admission` | Bool, default **False** | Send when a student is admitted |
| `sms_on_payment` | Bool, default **False** | Send a receipt when a fee payment is taken |
| `sms_sender_id` | Char(20), blank | The name on the guardian's handset, registered with the operator. Per institution, because a madrasah and a college on one gateway account must not appear as each other |
| `default_language` | Char(2) | `bn` / `en` |
| `is_active` | Bool | |

Creating a Branch seeds its streams, fee categories, income categories and
expense categories (§2, §5, §6). This is decision 1 of the "smart" list in
`00-overview.md`.

**Seeded by `branches.services.create_branch()`, not by a signal.** A signal
fires during fixture loads and test setup, which would seed a branch twice and
leave `seed_categories` looking broken. The service is the only supported way to
create an institution.

### `User`

`AUTH_USER_MODEL = 'accounts.User'`, custom manager, **`USERNAME_FIELD = 'phone'`**.

| Field | Type | Notes |
|-------|------|-------|
| `phone` | Char(11) **unique** | Canonical `01XXXXXXXXX`; normalised on save |
| `password` | Char | Django hasher |
| `name`, `name_bn` | Char(120) | One name field, not first/last — Bangladeshi names do not split reliably |
| `email` | Email, blank, **not** unique | Optional; never a login credential |
| `user_type` | Char choices | `platform_admin`, `principal`, `accountant`, `teacher`, `employee`, `student`, `guardian` |
| `branch` | → `Branch`, **null** | NULL ⇒ platform admin, sees all (`01` §5.2) |
| `role` | → `Role`, null | The preset |
| `permissions` | JSON list | `["fees.collect", …]`. **Empty ⇒ use role preset** |
| `photo` | Image, blank | |
| `language` | Char(2) | UI + SMS language |
| `is_active`, `is_staff`, `is_superuser` | Bool | |
| `last_login_ip` | GenericIP, null | |
| `must_change_password` | Bool | True on admin-created accounts |

**Why phone is globally unique, not per branch:** a person is one person. A
teacher moving from Dhaka to Chittagong keeps their login and their history;
duplicating them would fork their attendance and payroll records. Cross-branch
access is `BranchAccess`, below.

### `Role`

| Field | Type | Notes |
|-------|------|-------|
| `name` | Char(50) unique | `Principal`, `Accountant`, `Teacher` … |
| `permission_matrix` | JSON | `{"fees": ["view","collect"], …}` |
| `is_system` | Bool | System presets cannot be deleted |

### `BranchAccess`

Explicit grant for a user who works at more than one branch.

| Field | Type |
|-------|------|
| `user` → `User` | |
| `branch` → `Branch` | |
| `permissions` | JSON list, blank ⇒ inherit the user's own |
| `granted_by` → `User`, `granted_at` | |

`unique_together (user, branch)`.

### `ActivityLog` — **V1** (`08` D8)

Append-only. No update, no delete, ever. Powers the platform admin’s **live
activity feed** (`08` D8), polled on a cursor every 5 seconds.

| Field | Type |
|-------|------|
| `user` → `User`, null | |
| `branch` → `Branch`, null | |
| `action` | Char — `create` / `update` / `delete` / `login` / `publish` / `collect` |
| `model`, `object_id`, `object_label` | Char |
| `before`, `after` | JSON |
| `ip`, `user_agent` | |
| `created_at` | |

Written for: every money row, every mark change, every permission change, every
login. Indexed on `(branch, created_at)` and `(model, object_id)`.

---

## 2. Branches app

### `Stream` **[BS]**

The student's **study sector** — the brief's *Student Type* and *Category*,
which are one field (`08` D2). A table rather than fixed choices, because a
branch is a whole institution and a college's sectors are not a madrasah's
(`08` D1).

| Field | Type | Notes |
|-------|------|-------|
| `branch` | → Branch | |
| `code` | Char(20) | `hifz` · `qaumi` · `general` · `science` · `commerce` · `arts` |
| `name`, `name_bn` | Char(60) | The institution's **own** label — `হাফজ` or `হিফজ`, whichever it uses |
| `order`, `is_active` | | |

`unique_together (branch, code)`. Seeded on branch creation from
`institution_type`:

| `institution_type` | Seeded |
|--------------------|--------|
| `madrasah` | Hifz · Qaumi · General |
| `school` | General |
| `college` | Science · Commerce · Arts |
| `combined` | all six |

Pointed at by `Student`, `AcademicClass`, `Subject`, `Session` and
`GradeScale`. A FK rather than a string gives referential integrity and an
index; a loose string would let a typo silently create a stream nobody can find.

### `Session` **[BS]**

An academic year. Some institutions run the Hijri year for the qaumi stream and
the Gregorian for the general one, so a session belongs to a *stream set*, not
to the whole branch.

| Field | Type | Notes |
|-------|------|-------|
| `branch` | → Branch | |
| `name` | Char(40) | `2026`, `1447 হিজরি` |
| `streams` | M2M → Stream | Which streams this session applies to |
| `starts_on`, `ends_on` | Date | |
| `is_current` | Bool | At most one current per (branch, stream) |

### `Holiday` **[BS]**

| `branch`, `date`, `title`, `applies_to` (students/staff/both) |

Consumed by attendance (no absence SMS on a holiday) and by attendance
percentage calculations (holidays are not absences).

### `BranchSetting` **[BS]**

Key/value JSON for per-branch toggles that do not deserve a column: SMS
templates on/off, attendance cutoff time, receipt footer text, marksheet
signature lines.

---

## 3. Academics app

### `AcademicClass` **[BS]**

The brief's Class model.

| Field | Type | Notes |
|-------|------|-------|
| `branch` | → Branch | |
| `stream` | → Stream | §2 (`08` D2) |
| `name`, `name_bn` | Char(60) | `Class 10`, `Nazera`, `Mizan` |
| `session` | → Session | |
| `year` | Int | Denormalised from session for cheap filtering |
| `level_order` | Int | Sort order; also drives promotion to the next class |
| `capacity` | Int, null | |
| `class_teacher` | → Teacher, null | **The responsible teacher for this class** (`08` D6). Assigned by the admin; also scopes what the teacher may reach |
| `monthly_fee` | Decimal, null | Convenience default; FeeStructure overrides |

`unique_together (branch, session, stream, name)`.

> **Note on the brief's `Name: Class 10 2026`:** the year is *not* baked into the
> name. `name` is `Class 10`; the session/year is a separate field. Baking it in
> makes "show me Class 10 across five years" a string-prefix search, and makes
> promotion logic parse text.

### `Section` **[BS]**

| `branch`, `academic_class` → AcademicClass, `name` (`A`, `Boys`, `Batch-1`), `capacity`, `room`, `in_charge` → Teacher (the section’s responsible teacher, `08` D6) |

### `Subject` **[BS]**

| Field | Notes |
|-------|-------|
| `branch`, `stream` → Stream, `academic_class` → AcademicClass | |
| `name`, `name_bn`, `code` | |
| `full_marks`, `pass_marks` | Int |
| `is_optional` | Bool — excluded from GPA where the grade scale says so |
| `has_practical`, `practical_marks` | |

### `Period` **[BS]**

The institution's bell schedule, defined once (`08` D7).

| Field | Type | Notes |
|-------|------|-------|
| `branch` | → Branch | |
| `stream` | → Stream, null | Null ⇒ all streams. A hifz stream often starts after Fajr while the general stream starts at nine |
| `name`, `name_bn` | Char(30) | `1st Period` · `প্রথম ঘণ্টা` · `Fajr Sabaq` |
| `order` | Int | |
| `start_time`, `end_time` | Time | |
| `is_break` | Bool | Tiffin and prayer breaks occupy a slot but never appear on a teacher's board |

`unique_together (branch, stream, order)`.

**Why a table and not times on each routine row:** an institution changing its
bell schedule for Ramadan edits eight rows, not five hundred.

### `ClassRoutine` **[BS]**

The weekly timetable — what turns "who teaches what" into "at what time"
(`08` D7).

| Field | Type | Notes |
|-------|------|-------|
| `branch`, `session` | → Branch, Session | |
| `academic_class` | → AcademicClass | |
| `section` | → Section, null | |
| `subject` | → Subject | |
| `teacher` | → Teacher | |
| `period` | → Period | |
| `day_of_week` | Int | `0`=Sat … `6`=Fri — the Bangladeshi week |
| `room` | Char, blank | |
| `is_active` | Bool | |

Two unique constraints, and the second is the valuable one:

```
unique_together (branch, session, academic_class, section, day_of_week, period)
unique_together (branch, session, teacher,        day_of_week, period)
```

**A teacher cannot be in two rooms at once.** Timetable clashes are the classic
school-software bug; this makes the database refuse them rather than trusting a
validator someone forgets to call.

Drives the teacher's "today's classes" board, the live attendance window, and
the printed class routine.

### `Enrolment` **[BS]**

**The join that makes the whole model work.** A Student is a person; an
Enrolment is that person in a class, in a section, in a session.

| Field | Type | Notes |
|-------|------|-------|
| `branch`, `student` → Student, `session` → Session | |
| `academic_class` → AcademicClass, `section` → Section, null | |
| `roll` | Int | Per (class, section, session) |
| `admission_number` | Char(30) | `ADM-DHK-2026-00417`, gapless per branch+session |
| `status` | Char | `active` / `promoted` / `passed` / `withdrawn` / `transferred` |
| `enrolled_on`, `left_on` | Date | |
| `is_hostel`, `is_transport` | Bool | Drives which recurring fees apply |

`unique_together (branch, session, academic_class, section, roll)`.

**The brief's "admission history" is simply `student.enrolments.all()`.** No
separate history table, no duplicated data, no drift.

### `SubjectAssignment` **[BS]**

Which teacher teaches which subject to which class/section, per session.

**This table does double duty** (`08` D6): it records the teaching assignment
*and* forms half of the teacher's access scope — a teacher may enter marks only
for the subjects listed here, and take period attendance only for these classes.
The other half is class responsibility (`AcademicClass.class_teacher`,
`Section.in_charge`). Validation rejects a teacher from another branch, or a
class from another session.

| `branch`, `session`, `teacher` → Teacher, `subject` → Subject, `academic_class`, `section` |

---

## 4. Students app

### `Student` **[BS]**

Identity only. Class, session and section live on `Enrolment`.

| Field | Type | Notes |
|-------|------|-------|
| `branch` | → Branch | The branch that owns the record |
| `student_id` | Char(20) unique | `SIES-000123` — permanent, institution-wide |
| `user` | → User, null, OneToOne | Only if the student logs in |
| `stream` | → Stream | **The brief's *Student Type* and *Category* — one field** (`08` D2) |
| `name`, `name_bn` | Char(120) | |
| `photo` | Image | |
| `date_of_birth` | Date | |
| `gender` | Char | |
| `birth_certificate_no`, `nid` | Char, blank | |
| `blood_group` | Char, blank | |
| `religion_notes` | Char, blank | e.g. current Sipara for a hifz student |
| `phone`, `email` | | Optional; the guardian's phone is the one that matters |
| `village`, `post_office`, `upazila`, `district` | Char(80) | **Structured** — the admission form asks for these as four separate boxes (`07` §4), and it makes "students from this upazila" a query, not a text search |
| `present_address`, `permanent_address` | Text | Free text for anything the four fields above do not cover |
| `previous_institution`, `previous_class` | Char, blank | |
| `admitted_on` | Date | First admission |
| `status` | Char | `active` / `passed_out` / `withdrawn` / `transferred` |
| `is_active` | Bool | Soft delete |

### ~~`StudentCategory`~~ — **deleted**

`Category` on the brief's Student model means the study sector, which is
`Stream` (`08` D2). There is no separate orphan/free/waiver dimension. Removed
from V1 and V2 alike.

### `Guardian` **[BS]**

Its own table, not fields on Student, because siblings share a guardian and a
changed phone number must change once.

| Field | Notes |
|-------|-------|
| `branch`, `name`, `name_bn` | |
| `relation` | father / mother / brother / other |
| `phone` | Char(11) — **the SMS destination** |
| `alt_phone`, `nid`, `occupation`, `monthly_income`, `address` | |
| `user` → User, null | Reserved for guardian login (`02` §1) |

### `StudentGuardian` **[BS]**

`student` × `guardian` × `is_primary`. Many-to-many with an attribute, so a
student can have a father and a local guardian and the SMS knows which to use.

### `Admission` (application) **[BS]**

The pre-student record.

| Field | Notes |
|-------|-------|
| `branch`, `session`, `stream`, `academic_class` | Applied for |
| `application_no` | Char, gapless per branch+session |
| `applicant_name`, `dob`, `gender`, `photo`, `guardian_name`, `guardian_phone`, `address` | |
| `previous_institution`, `previous_result` | |
| `status` | `pending` / `interview` / `accepted` / `rejected` / `admitted` / `cancelled` |
| `interview_date`, `interview_score`, `remarks` | |
| `student` → Student, null | Set when the application becomes an admission |
| `processed_by` → User, `processed_at` | |

### `Document` **[BS]**

Certificates, testimonials, birth certificates, transfer certificates.

| `branch`, `owner_type` (student/teacher/employee), `student` → Student null, `teacher` → Teacher null, `employee` → Employee null, `doc_type`, `title`, `file`, `issued_on`, `expires_on`, `uploaded_by` |

Files are served through an authenticated API view, never from a public URL —
these are minors' records (`01` §8).

---

## 5. Staff app — `Teacher` and `Employee`

**Two models, two tables** (`08` D5). A teacher will grow features an employee
never has — evaluation, grading, subject expertise, class load — and those must
not become columns that are null for half the rows.

### `PersonProfile` — abstract, no table

The fields both share, defined once so the two tables cannot drift.
`abstract = True`; it never appears in the database.

| Field | Type | Notes |
|-------|------|-------|
| `branch` | → Branch | From `BranchScopedModel` |
| `user` | → User, OneToOne, null | Login. Null for staff who never sign in |
| `name`, `name_bn` | Char(120) | |
| `photo` | Image, blank | |
| `dob`, `gender`, `nid`, `blood_group` | | |
| `phone`, `alt_phone` | Char(11)/(20) | `phone` matches `user.phone` when a login exists |
| `email` | Email, blank | |
| `village`, `post_office`, `upazila`, `district` | Char(80) | Structured, as on Student |
| `address` | Text, blank | Anything the four above miss |
| `designation` | Char(80) | |
| `joining_date`, `leaving_date` | Date | |
| `employment_status` | Char choices | `active` · `on_leave` · `suspended` · `resigned` · `terminated` · `transferred` |
| `basic_salary`, `allowances`, `deductions` | Decimal(12,2) | |
| `bank_account`, `mobile_banking` | Char, blank | |
| `emergency_contact_name`, `emergency_contact_phone` | | |

### `Teacher` **[BS]**

`PersonProfile` **plus** the brief's teacher fields.

| Field | Type | Notes |
|-------|------|-------|
| *(all of `PersonProfile`)* | | `designation` = মুদাররিস · হাফিজ · Assistant Teacher |
| `teacher_id` | Char(20) unique | **The brief's Teacher ID** — `TCH-DHK-0042`, gapless per branch |
| `streams` | M2M → Stream | Which sectors they teach — hifz, qaumi, general |
| `is_class_teacher` | Bool | Convenience flag; the authoritative link is `AcademicClass.class_teacher` |
| `specialization` | Char, blank | Qur'an, Hadith, Fiqh, Mathematics |
| `max_weekly_periods` | Int, null | Guards against over-assignment |

**The brief's remaining teacher fields are relations, not columns:**

| Brief field | Where it lives |
|-------------|----------------|
| Contact | `phone`, `alt_phone`, `email` |
| Branch | `branch` |
| Joining date | `joining_date` |
| **Qualification** | `TeacherQualification`, below — a teacher has several |
| **Subjects** | `SubjectAssignment` (§3) |
| **Classes** | `SubjectAssignment` + `AcademicClass.class_teacher` + `Section.in_charge` |
| Employment status | `employment_status` |

*Reserved for V2, and the reason this model is separate:* `TeacherEvaluation`,
`TeacherGrade`, lesson records.

### `Employee` **[BS]** — non-teaching staff

| Field | Type | Notes |
|-------|------|-------|
| *(all of `PersonProfile`)* | | `designation` = Accountant · Cook · Guard · Cleaner · Driver |
| `employee_id` | Char(20) unique | `EMP-DHK-0018` |
| `department` | Char(80), blank | Office · Kitchen · Hostel · Security · Transport |
| `duty_shift` | Char, blank | Morning · Evening · Night |

### `TeacherQualification` **[BS]**

`teacher` → Teacher, `degree`, `institution`, `year`, `result`, `certificate`
(file). A teacher has several — a single text field on the profile cannot be
reported on or verified.

*(Employees rarely need this; if one does, it goes in `address`/notes. A second
qualification table for employees is V2 and probably never.)*

### `LeaveRequest` **[BS]** — *V2*

| `branch`, `person_type` (`teacher`/`employee`), `teacher` → Teacher null, `employee` → Employee null, `leave_type`, `from_date`, `to_date`, `days`, `reason`, `status`, `approved_by`, `approved_at` |

Same two-nullable-FK pattern as attendance (§6). Approved leave suppresses
absent-marking.

### 5.1 Who else points at `Teacher`

`AcademicClass.class_teacher` · `Section.in_charge` · `SubjectAssignment.teacher`
· `ExamSchedule.invigilator` — all → `Teacher`, none → `Employee`. That these
are unambiguous is itself an argument for the split.

---

## 6. Attendance app

Two tables, exactly as the brief separates them.

### `DailyAttendance` **[BS]**

One row per person per day.

| Field | Type | Notes |
|-------|------|-------|
| `branch`, `date` | | |
| `person_type` | `student` / `teacher` / `employee` | |
| `student` → Student, null | **Exactly one** of these three is set — DB check constraint (`08` D5) |
| `teacher` → Teacher, null | |
| `employee` → Employee, null | |
| `enrolment` → Enrolment, null | For students: which class they were in that day |
| `status` | `present` / `absent` / `late` / `leave` / `holiday` / `half_day` | |
| `in_time`, `out_time` | Time, null | |
| `remarks` | Char, blank | |
| `taken_by` → User | **The brief's "who took the attendance"** |
| `taken_at` | DateTime | |
| `source` | `web` / `mobile` / `biometric` / `import` | |

**One row per person per day — and `unique_together` alone does NOT deliver it.**

An earlier version of this file specified
`unique_together (branch, date, person_type, student, teacher, employee)`. That
constraint does nothing useful on Postgres: **NULLs compare as distinct**, so two
rows for the same student (both with `teacher` and `employee` NULL) never
collide, and the same person could be marked twice on the same day. The same
trap bit `NumberSequence` (§1) — a nullable column in a unique constraint is
almost never doing what it looks like it is doing.

What actually enforces it is **three partial unique constraints, one per person
type**:

```python
UniqueConstraint(fields=['branch', 'date', 'student'],
                 condition=Q(student__isnull=False), name='dailyatt_unique_student_day')
UniqueConstraint(fields=['branch', 'date', 'teacher'],
                 condition=Q(teacher__isnull=False), name='dailyatt_unique_teacher_day')
UniqueConstraint(fields=['branch', 'date', 'employee'],
                 condition=Q(employee__isnull=False), name='dailyatt_unique_employee_day')
```

`ClassAttendance` has the same problem through its nullable `section`, and takes
the same fix.

> **Why a `person_type` + three nullable FKs instead of Django's generic
> relations:** GenericForeignKey cannot be joined efficiently and cannot carry a
> database-level unique constraint. Three nullable FKs with a check constraint
> keep both, at the cost of one `if` in the serializer. Three, not two, since
> `08` D5 split Teacher from Employee — and `person_type` is folded INTO the
> check constraint so the discriminator can never disagree with the FK that is
> actually set.

> **Corrections overwrite the row** (`08` D3). A fixed cell updates `status`,
> `taken_by` and `taken_at` in place; `updated_at` records when. There is no
> correction history in V1, and the prior value is not recoverable. Chosen
> knowingly, in exchange for shipping sooner.

### `ClassAttendance` **[BS]**

Per class period, for branches that take subject-wise attendance.

| Field | Notes |
|-------|-------|
| `branch`, `date`, `academic_class`, `section`, `subject` → Subject null, `period` → Period |
| `student` → Student, `enrolment` → Enrolment |
| `status`, `remarks` |
| `taken_by` → User, `taken_at`, `source` |

`unique_together (branch, date, academic_class, section, period, student)`.

### `AttendanceSummary` **[BS]** *(rollup)*

Nightly aggregate: `(branch, person, month)` → present / absent / late / leave /
working days / percentage. Written by the 02:00 Celery job so a year's
attendance report is a read of 12 rows, not a scan of 300 × N.

---

## 7. Fees app

### `FeeCategory` **[BS]** — auto-seeded

Created for every branch by the branch-creation signal. The `note` is the
brief's "proper note" and is what the accountant sees in the UI.

| Field | Type |
|-------|------|
| `branch`, `name`, `name_bn`, `code` | |
| `note` | Text — the seeded explanation |
| `recurrence` | `one_time` / `monthly` / `session` / `exam` / `custom` |
| `is_refundable`, `is_mandatory` | Bool |
| `applies_to` | JSON — streams / hostel-only / transport-only |
| `is_system` | Bool — seeded rows cannot be deleted, only deactivated |
| `display_order` | Int |

**Seeded set** (the brief's list, with the notes):

| Code | Name | Recurrence | Note |
|------|------|-----------|------|
| `ADM` | Admission Fee | one_time | Charged once when a student is first admitted. Non-refundable. |
| `SES` | Session Fee | session | Charged once per academic session at enrolment or re-admission. |
| `MON` | Monthly Fee | monthly | The regular tuition fee, raised automatically on the 1st of each month. |
| `EXM` | Examination Fee | exam | Charged per examination; raised when the exam is scheduled. |
| `BOK` | Book Fee | custom | Textbooks and materials issued by the institution. |
| `UNI` | Uniform Fee | custom | Uniform issued or replaced. |
| `TRN` | Transport Fee | monthly | Charged only to students marked as using transport. |
| `HOS` | Hostel Fee | monthly | Charged only to residential students; covers seat and utilities. |
| `FOD` | Food Fee | monthly | Meals for residential students, where billed separately from hostel. |
| `ACT` | Activity Fee | session | Sports, cultural programmes, milad, annual events. |
| `OTH` | Other Fee | custom | Anything not covered above; always give a reason in the remarks. |

### `FeeStructure` **[BS]**

*What a class costs.* Set once per session; the monthly job reads it.

| `branch`, `session`, `academic_class`, `stream`, `category` → FeeCategory, `amount`, `due_day` (day of month), `is_active` |

`unique_together (branch, session, academic_class, category)`.

### `Fee` (invoice) **[BS]**

The brief's fee row, minus the payment fields that moved to `Payment`.

| Field | Type | Notes |
|-------|------|-------|
| `branch`, `student` → Student, `enrolment` → Enrolment | |
| `category` → FeeCategory | |
| `session` → Session, `period` | Char(7) `2026-03` for monthly; blank otherwise |
| `invoice_no` | Char(30) unique per branch |
| `amount` | Decimal — the gross charge |
| `discount` | Decimal — from student category or a manual waiver |
| `fine` | Decimal — accrued nightly while overdue |
| `payable` | Decimal — `amount - discount + fine`, stored, recomputed on change |
| `paid_amount` | Decimal — sum of its payments, maintained on payment save |
| `due_date` | Date |
| `status` | `unpaid` / `partial` / `paid` / `overdue` / `waived` — **derived, never hand-set** |
| `waived_by`, `waive_reason` | |
| `generated_by` | `system` / `manual` |

`unique_together (branch, student, category, period, session)`, **partial on
`is_active`** — this is the constraint that makes the monthly job safe to run
twice (`01` §4). Partial because a cancelled invoice is a soft delete: while it
counted here, a month cancelled by mistake could never be raised again, and
generation skipped that (student, category, period) for good. One *live*
invoice per period per head; the cancelled rows stay as the record of the
cancellation.

Indexes: `(branch, status, due_date)` for the dues report, `(student, session)`
for the student's fee history.

### `Payment` **[BS]**

A receipt. One invoice may have several.

| Field | Type | Notes |
|-------|------|-------|
| `branch`, `fee` → Fee, `student` → Student | |
| `receipt_no` | Char(30) — gapless per branch, quoted out loud |
| `amount` | Decimal |
| `method` | `cash` / `bkash` / `nagad` / `rocket` / `bank` / `cheque` / `card` / `online` |
| `transaction_id` | Char, blank — the brief's field; unique per method when present |
| `paid_at` | DateTime |
| `collected_by` → User | |
| `income` → Income, null | **The auto-posted income row** (`02` §4.6) |
| `note` | |
| `is_reversed`, `reversed_by`, `reverse_reason` | A wrong receipt is reversed, never deleted |

### `Discount` **[BS]**

A standing discount on a student, so it applies to every future invoice without
being re-entered.

| `branch`, `student`, `category` → FeeCategory null (null ⇒ all), `percent` or `amount`, `reason`, `valid_from`, `valid_to`, `approved_by` |

---

## 8. Finance app

### `IncomeCategory` / `ExpenseCategory` **[BS]** — auto-seeded

| `branch`, `name`, `name_bn`, `code`, `note`, `is_system`, `display_order`, `fee_category` → FeeCategory null |

The `fee_category` link is what lets fee collection post to the right income
head automatically.

**Seeded income categories** (the brief's list): Admission Fee, Session Fee,
Monthly Fee, Examination Fee, Book Sale, Donation — plus Hostel, Transport and
Other Income, because the fee categories above generate them and an unmapped
receipt would otherwise land in a null head.

**Seeded expense categories** (the brief's list): Teacher Salary, Electricity,
Internet, Rent, Books, Stationery, Maintenance, Food, Transport, Equipment,
Marketing, Other. Plus Staff Salary (non-teaching), separated from Teacher
Salary so payroll reporting splits the way institutions actually budget.

### `Income` **[BS]** and `Expense` **[BS]**

Same shape, shared abstract base:

| Field | Type | Notes |
|-------|------|-------|
| `branch`, `category` → Income/ExpenseCategory | |
| `voucher_no` | Char(30) — gapless per branch |
| `amount` | Decimal |
| `date` | Date |
| `method` | cash / bkash / nagad / bank / cheque |
| `reference` | Char — transaction id, cheque no |
| `description` | Text |
| `attachment` | File, blank — the bill or slip |
| `session` → Session, null | For session-wise P&L |
| `source` | `manual` / `fee_payment` / `payroll` — non-manual rows are read-only in the UI |
| `payment` → Payment, null | *(Income only)* back-link to the receipt |
| `payslip` → Payslip, null | *(Expense only)* back-link to payroll |
| `recorded_by` → User | |
| `is_approved`, `approved_by` | Optional approval step for expenses over a branch threshold |

Indexes: `(branch, date)`, `(branch, category, date)`.

### `PayrollRun` **[BS]** and `Payslip` **[BS]**

| `PayrollRun`: `branch`, `month`, `status` (draft/approved/paid), `total`, `approved_by` |
| `Payslip`: `run`, `staff`, `basic`, `allowances`, `deductions`, `absent_deduction`, `net`, `paid_at`, `method`, `expense` → Expense null |

Gated on `salary.manage`, separate from `finance` (`02` §2.1).

---

## 9. Exams app

### `Exam` **[BS]**

| `branch`, `session`, `stream`, `name` (`Half-Yearly 2026`), `exam_type` (`monthly`/`half_yearly`/`annual`/`test`/`sabaq`/`board`), `starts_on`, `ends_on`, `status` (`draft`/`scheduled`/`ongoing`/`marks_entry`/`published`), `published_by`, `published_at` |

### `ExamClass` **[BS]**

Which classes sit which exam: `exam` × `academic_class`.

### `ExamSchedule` **[BS]**

| `exam`, `academic_class`, `subject`, `date`, `start_time`, `end_time`, `full_marks`, `pass_marks`, `room`, `invigilator` → Teacher |

### `Mark` **[BS]**

| Field | Notes |
|-------|-------|
| `branch`, `exam`, `student`, `enrolment`, `subject` | |
| `obtained` | Decimal, null when absent |
| `practical_obtained` | Decimal, null |
| `is_absent` | Bool |
| `grade`, `grade_point` | Filled at publish from the grade scale |
| `entered_by` → User, `entered_at` | |

`unique_together (exam, student, subject)`.

### `GradeScale` **[BS]** and `GradeBand` **[BS]**

Per branch **and per stream** (`02` §4.7).

| `GradeScale`: `branch`, `stream`, `name`, `is_default` |
| `GradeBand`: `scale`, `min_percent`, `max_percent`, `grade` (`A+`, `মুমতাজ`), `point`, `is_fail` |

### `Result` **[BS]** *(computed at publish)*

| `branch`, `exam`, `student`, `enrolment`, `total_marks`, `obtained_marks`, `percentage`, `gpa`, `grade`, `rank_in_class`, `rank_in_section`, `is_passed`, `failed_subjects` (JSON), `remarks`, `published_at` |

Stored rather than computed on read: a marksheet printed today and reprinted in
three years must show the same numbers, even if the grade scale has since been
edited.

---

## 10. Notifications app — **the two tables below are V1**

Built for `result_published` and shaped for the rest of the events (`05` §6.2).
`Notice` further down is still V2.

### `NotificationTemplate` **[BS]**

| `branch`, `event` (`fee_due`/`fee_received`/`absent`/`result_published`/`notice`/`admission`), `channel` (`sms`/`email`), `language`, `body`, `is_active` |

Unique on `(branch, event, channel, language)`. A branch that has written none
falls back to the built-in wording, so SMS works the day it is switched on.

### `SmsMessage` (outbox) **[BS]**

| `branch`, `event`, `reference` (`exam:12` — what it is ABOUT), `student` → Student null SET_NULL, `recipient_label`, `to_phone`, `body`, `parts`, `status` (`queued`/`sent`/`failed`/`skipped`), `skip_reason` (`no_phone`/`already_sent`/`sms_off`), `provider`, `provider_code`, `provider_message`, `sent_at`, `attempts` |

Every send is a row with its provider's answer (`02` §4.9), **including the
sends that did not happen** — a student with no guardian number is a `skipped`
row, because that list is the office's work for the afternoon and an absence of
rows is not.

The two automatic events default to **off**: they ride on `admit_student()`
and `collect_fee()` with nobody watching, and a send the office did not ask for
is money leaving without a decision. The result SMS needs no switch — a person
presses it having seen what it will cost.

`reference` is what the message is about, and it decides what "already sent"
means: `exam:12` per student (one result each), `student:88` (one admission
message), `payment:412` — the **payment**, not the invoice, because three
instalments against one invoice are three receipts and three messages.

Unique on `(branch, event, reference, to_phone)` **where status is queued or
sent** — this is what makes "send the results" safe to press twice. Partial,
because a failed send must be retryable and a skipped one must not block the
send that follows the office putting the missing number on file.

`parts` is billing arithmetic, stored at queue time: a Bengali body is Unicode,
so 70 characters is one SMS and 71 is two.

### `Notice` **[BS]**

| `branch`, `title`, `body`, `audience` (JSON: all / class / stream / staff / guardians), `attachment`, `publish_at`, `expires_at`, `is_published`, `sent_sms` |

---

## 11. Reports app — rollup tables — **V2, entire app**

*V1 report screens live in each module and query source rows directly. That is
correct at V1 data volume; these tables are a speed optimisation, and because
they are derived they can be introduced at any time by running the rollup task
over existing history.*

Written nightly, read by the report screens. None of them hold anything that is
not derivable; they exist purely so a year-scale report is a read.

| Table | Grain |
|-------|-------|
| `AttendanceSummary` | branch × person × month (defined in §6) |
| `FeeCollectionSummary` | branch × category × day |
| `DuesSummary` | branch × class × session — outstanding, aged |
| `FinanceSummary` | branch × category × month — income and expense |
| `EnrolmentSummary` | branch × stream × class × session — strength |

Because they are derived, any of them can be dropped and rebuilt from source by
re-running the rollup task. That property is the whole reason they are allowed
to exist alongside the "no caching" rule in `00-overview.md`: a cache you cannot
rebuild is a second source of truth, and a rollup you can rebuild is not.

### `ExportJob`

| `user`, `branch`, `report`, `params` (JSON), `format` (`pdf`/`xlsx`/`csv`), `status`, `file`, `error`, `created_at`, `finished_at` |

Backs the async export flow in `02` §5.

---

## 12. Entity map

V2-only nodes are marked `†`.

```
Branch (= one institution: madrasah / school / college)
   │
   ├─ Stream ──────► pointed at by Student, AcademicClass,
   │                 Subject, Session, GradeScale†
   │
   ├─ Session ─┬─ AcademicClass ─┬─ Section
   │           │                 └─ Subject ─ SubjectAssignment ─ Teacher
   │           └─ FeeStructure†
   │
   ├─ Student ─┬─ Enrolment ──────► AcademicClass, Section, Session
   │           ├─ StudentGuardian ─► Guardian
   │           ├─ Document
   │           ├─ Fee ─┬─ Payment ──────► Income
   │           │       └─ Discount†
   │           ├─ DailyAttendance / ClassAttendance
   │           └─ Mark ──► Exam ──► Result†
   │
   ├─ Admission ─┬─ AdmissionAnswer ──► Question
   │             └─ PrintedForm ──────► FormTemplate
   │
   ├─ Teacher / Employee ─┬─ TeacherQualification
   │                ├─ LeaveRequest†
   │                ├─ DailyAttendance
   │                └─ Payslip† ──► PayrollRun† ──► Expense
   │
   ├─ Income ──► IncomeCategory
   ├─ Expense ─► ExpenseCategory
   ├─ FeeCategory ──► Fee
   ├─ Notice† / Notification† / MessageTemplate†
   └─ rollups†: AttendanceSummary, FeeCollectionSummary, DuesSummary,
                FinanceSummary, EnrolmentSummary

User (global, phone-unique) ─► Branch (nullable = PLATFORM ADMIN)
                            ├─► Role (permission preset)
                            ├─► Student  (optional login, 08 D4)
                            ├─► Teacher / Employee
                            └─► BranchAccess† (multi-institution grant)
ActivityLog (global, append-only) — V1, powers the live feed (08 D8)
```

---

## 13. Constraints worth stating explicitly

| Constraint | Prevents |
|------------|----------|
| `User.phone` unique, 11 digits, normalised | Duplicate humans, login ambiguity |
| `Fee` unique on `(branch, student, category, period, session)` where `is_active` | The monthly job double-charging |
| `DailyAttendance` — THREE partial unique constraints, one per person type | Two conflicting attendance records for one day. `unique_together` over the nullable FKs does NOT do this: Postgres treats NULLs as distinct (§6) |
| `Mark` unique on `(exam, student, subject)` | Two marks for one paper |
| `Enrolment` unique on `(branch, session, class, section, roll)` | Two students on one roll |
| Check: exactly one of `student` / `teacher` / `employee` set on `DailyAttendance` | Orphan or double-owned attendance rows |
| `Payment.amount > 0`; sum of payments ≤ `Fee.payable` | Over-collection, negative receipts |
| Receipt / voucher / admission numbers issued under `SELECT … FOR UPDATE` | Gaps and duplicates under concurrency |
| Soft delete on Student, Fee, Payment, Mark | Destroying an accounting or academic record |
