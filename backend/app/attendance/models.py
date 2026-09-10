"""Attendance — two tables, exactly as docs/03 §6 separates them.

* **`DailyAttendance`** — one row per *person* per *day*. Students, teachers and
  employees alike; it is what the month register grid (docs/02 §4.4) reads and
  writes.
* **`ClassAttendance`** — one row per *student* per *class period* per day, for
  the institutions that take attendance subject by subject. It is what the
  teacher's today board (docs/08 D7) writes.

Both carry `taken_by`, `taken_at` and `source`, because "who marked my son
absent" is a question that gets asked at a counter and must have an answer.

Nothing in this module has a `save()` override and nothing has a signal
(CLAUDE.md §4.3). Every write goes through `services.py`, inside one
transaction; the constraints below are the database's own last line.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import BranchScopedModel


class PersonType(models.TextChoices):
    """Which of the three person tables a `DailyAttendance` row points at.

    Denormalised alongside the three FKs on purpose. It is not redundant in the
    way it looks: it is what the unique key and the register queries filter on,
    and reading it costs no join — `WHERE person_type='student'` on an index is
    cheaper than three `IS NOT NULL` tests, and the check constraint below keeps
    it honest.
    """

    STUDENT = 'student', _('Student · শিক্ষার্থী')
    TEACHER = 'teacher', _('Teacher · শিক্ষক')
    EMPLOYEE = 'employee', _('Employee · কর্মচারী')


class AttendanceStatus(models.TextChoices):
    PRESENT = 'present', _('Present · উপস্থিত')
    ABSENT = 'absent', _('Absent · অনুপস্থিত')
    LATE = 'late', _('Late · বিলম্বে উপস্থিত')
    LEAVE = 'leave', _('Leave · ছুটি')
    HOLIDAY = 'holiday', _('Holiday · সরকারি ছুটি')
    HALF_DAY = 'half_day', _('Half day · অর্ধদিবস')


class AttendanceSource(models.TextChoices):
    """How the row got here.

    Kept because the answer to a dispute differs by it: a `biometric` row is a
    machine reading and an `import` row came off a spreadsheet somebody typed,
    and neither has a person who can be asked what they saw.
    """

    WEB = 'web', _('Web · ওয়েব')
    MOBILE = 'mobile', _('Mobile · মোবাইল')
    BIOMETRIC = 'biometric', _('Biometric · বায়োমেট্রিক')
    IMPORT = 'import', _('Imported · আমদানি')


class DailyAttendance(BranchScopedModel):
    """One row per person per day (docs/03 §6).

    **Three nullable person FKs and a `person_type`, not a GenericForeignKey.**
    A generic relation cannot be joined efficiently — the month register reads a
    class's whole month in one query and would need a per-row lookup instead —
    and it cannot carry a database-level unique constraint, which is the only
    thing that actually stops two conflicting rows for one day. The cost is one
    `if` in the serializer, and it is paid once. docs/08 D5 raised this from two
    FKs to three when `Teacher` and `Employee` became separate models; that
    changed the constraint, not the design.

    **Corrections OVERWRITE the row in place (docs/08 D3).** A fixed cell updates
    `status`, `taken_by` and `taken_at` on the existing row; `updated_at` records
    when. There is no history table and there are no correction rows.

    The accepted cost, stated plainly: *this table cannot answer "what was this
    cell before it was changed, and who changed it".* The prior value is not
    recoverable from here. That was chosen knowingly in exchange for shipping V1
    sooner — and it is softened, not removed, by docs/08 D8 bringing
    `ActivityLog` into V1, which records the correction with a before and an
    after outside this table.
    """

    date = models.DateField(_('date · তারিখ'), db_index=True)

    person_type = models.CharField(
        _('person type · ব্যক্তির ধরন'),
        max_length=10, choices=PersonType.choices, db_index=True,
    )

    # PROTECT on all three: attendance is an academic record. Deleting a student
    # who has a year of it must fail loudly rather than erase the register the
    # institution certifies from (CLAUDE.md §4.2). Withdrawal is
    # `is_active=False` on the student, not a delete.
    student = models.ForeignKey(
        'students.Student', null=True, blank=True,
        on_delete=models.PROTECT, related_name='daily_attendance',
    )
    teacher = models.ForeignKey(
        'staff.Teacher', null=True, blank=True,
        on_delete=models.PROTECT, related_name='daily_attendance',
    )
    employee = models.ForeignKey(
        'staff.Employee', null=True, blank=True,
        on_delete=models.PROTECT, related_name='daily_attendance',
    )

    # Which class the student was in *that day*. This one field is what keeps a
    # historical register correct: a student promoted in January must still show
    # under Class 5 in last year's December register, and reading the class off
    # their *current* enrolment would silently rewrite every past register the
    # moment somebody changed class. Null for staff, who are enrolled in nothing.
    #
    # SET_NULL rather than PROTECT: an enrolment is closed, never deleted
    # (`academics.services.close_enrolment`), so this only ever fires during a
    # data repair — and losing the class label is better than blocking the
    # repair on a row nobody can otherwise reach.
    enrolment = models.ForeignKey(
        'academics.Enrolment', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='daily_attendance',
    )

    status = models.CharField(
        _('status · অবস্থা'), max_length=10, choices=AttendanceStatus.choices,
    )
    in_time = models.TimeField(_('in time · প্রবেশ'), null=True, blank=True)
    out_time = models.TimeField(_('out time · প্রস্থান'), null=True, blank=True)
    remarks = models.CharField(_('remarks · মন্তব্য'), max_length=200, blank=True)

    # The brief's "who took the attendance". SET_NULL, not CASCADE: a teacher who
    # leaves and whose account is deleted must not take a year of the
    # institution's registers with them (CLAUDE.md §4.2).
    taken_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='daily_attendance_taken',
    )
    # Distinct from `created_at`, and the difference is the point: `created_at`
    # is when the row first appeared, `taken_at` is when the *current* status was
    # set. After a correction the two differ, and `taken_at` is the one a dispute
    # at the counter is actually about.
    taken_at = models.DateTimeField(_('taken at · গ্রহণের সময়'))
    source = models.CharField(
        _('source · উৎস'), max_length=10,
        choices=AttendanceSource.choices, default=AttendanceSource.WEB,
    )

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('daily attendance · দৈনিক হাজিরা')
        verbose_name_plural = _('daily attendance · দৈনিক হাজিরা')
        # Date before id: every read of this table is "a range of days", and the
        # register renders oldest-to-newest left to right.
        ordering = ['branch', 'date', 'person_type', 'id']
        indexes = [
            # The month register's own query — one institution's rows over a date
            # range for one kind of person. Without it this becomes a scan of the
            # largest table in the database, on the screen teachers spend their
            # working day in.
            models.Index(fields=['branch', 'date', 'person_type'],
                         name='dailyatt_branch_date_type'),
            models.Index(fields=['student', 'date'], name='dailyatt_student_date'),
            models.Index(fields=['enrolment', 'date'], name='dailyatt_enrolment_date'),
            models.Index(fields=['teacher', 'date'], name='dailyatt_teacher_date'),
            models.Index(fields=['employee', 'date'], name='dailyatt_employee_date'),
        ]
        constraints = [
            # ── Exactly one person (docs/03 §13, docs/08 D5) ─────────────────
            # `person_type` is folded into each arm, so the discriminator and the
            # FK cannot disagree. A row claiming person_type='student' while
            # pointing at a teacher would be invisible to every register query
            # and impossible to find again afterwards.
            models.CheckConstraint(
                name='dailyatt_exactly_one_person',
                check=(
                    models.Q(person_type=PersonType.STUDENT,
                             student__isnull=False,
                             teacher__isnull=True, employee__isnull=True)
                    | models.Q(person_type=PersonType.TEACHER,
                               teacher__isnull=False,
                               student__isnull=True, employee__isnull=True)
                    | models.Q(person_type=PersonType.EMPLOYEE,
                               employee__isnull=False,
                               student__isnull=True, teacher__isnull=True)
                ),
            ),

            # ── One row per person per day ───────────────────────────────────
            # docs/03 §6 writes this as
            # `unique_together (branch, date, person_type, student, teacher, employee)`.
            # That tuple is declared first, and on its own it is NOT sufficient —
            # worth stating here rather than leaving to be discovered by a
            # duplicated register. Postgres treats NULLs as distinct, so for a
            # student row (teacher and employee both NULL) the tuple never
            # collides and the same student could be marked twice for one day.
            # The three partial constraints below are the ones that actually
            # bite. The full tuple is kept beside them because it is what the doc
            # specifies, and it costs one index.
            models.UniqueConstraint(
                fields=['branch', 'date', 'person_type',
                        'student', 'teacher', 'employee'],
                name='dailyatt_unique_person_day',
            ),
            models.UniqueConstraint(
                fields=['branch', 'date', 'student'],
                condition=models.Q(student__isnull=False),
                name='dailyatt_unique_student_day',
            ),
            models.UniqueConstraint(
                fields=['branch', 'date', 'teacher'],
                condition=models.Q(teacher__isnull=False),
                name='dailyatt_unique_teacher_day',
            ),
            models.UniqueConstraint(
                fields=['branch', 'date', 'employee'],
                condition=models.Q(employee__isnull=False),
                name='dailyatt_unique_employee_day',
            ),
        ]

    def __str__(self):
        return f'{self.person} · {self.date} · {self.status}'

    @property
    def person(self):
        """The one person this row is about — a tiny property, not logic."""
        return self.student or self.teacher or self.employee


class ClassAttendance(BranchScopedModel):
    """One row per student per class period per day (docs/03 §6, docs/08 D7).

    A separate table rather than a nullable `period` column on `DailyAttendance`,
    because the two answer different questions and have different unique keys: a
    student is present *for the day* once, and present *in the third period*
    once. Merging them would make the daily key unenforceable, which is the one
    guarantee that table exists for.

    `period` is a FK to `academics.Period`, not the loose integer the earlier
    draft had — docs/08 D7 changed this when the bell schedule became a table. A
    madrasah shifting its timings in Ramadan then edits eight `Period` rows
    instead of five hundred routine rows, and every attendance row that points at
    a period reads its times from the same place the routine does.

    Corrections overwrite in place, exactly as on `DailyAttendance` (docs/08 D3),
    with the same accepted cost.
    """

    date = models.DateField(_('date · তারিখ'), db_index=True)

    academic_class = models.ForeignKey(
        'academics.AcademicClass', on_delete=models.PROTECT,
        related_name='class_attendance',
    )
    # Nullable: a small class with no sections still takes period attendance.
    section = models.ForeignKey(
        'academics.Section', null=True, blank=True,
        on_delete=models.PROTECT, related_name='class_attendance',
    )
    # Nullable, and deliberately outside the unique key below: the *period* is
    # what identifies the slot, not the subject. A period covered by a
    # substitute teacher taking a different subject is still the same slot, and
    # keying on the subject would let it be marked twice.
    subject = models.ForeignKey(
        'academics.Subject', null=True, blank=True,
        on_delete=models.PROTECT, related_name='class_attendance',
    )
    period = models.ForeignKey(
        'academics.Period', on_delete=models.PROTECT,
        related_name='class_attendance',
    )

    student = models.ForeignKey(
        'students.Student', on_delete=models.PROTECT,
        related_name='class_attendance',
    )
    # Which enrolment this was marked against — the same "keeps the historical
    # register correct" reason as on `DailyAttendance`.
    enrolment = models.ForeignKey(
        'academics.Enrolment', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='class_attendance',
    )

    status = models.CharField(
        _('status · অবস্থা'), max_length=10, choices=AttendanceStatus.choices,
    )
    remarks = models.CharField(_('remarks · মন্তব্য'), max_length=200, blank=True)

    taken_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='class_attendance_taken',
    )
    taken_at = models.DateTimeField(_('taken at · গ্রহণের সময়'))
    source = models.CharField(
        _('source · উৎস'), max_length=10,
        choices=AttendanceSource.choices, default=AttendanceSource.WEB,
    )

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('class attendance · ক্লাস হাজিরা')
        verbose_name_plural = _('class attendance · ক্লাস হাজিরা')
        ordering = ['branch', 'date', 'period', 'academic_class', 'id']
        indexes = [
            models.Index(fields=['branch', 'date', 'academic_class'],
                         name='classatt_branch_date_class'),
            models.Index(fields=['student', 'date'], name='classatt_student_date'),
            models.Index(fields=['period', 'date'], name='classatt_period_date'),
        ]
        constraints = [
            # docs/03 §6's key. As on `DailyAttendance`, the partial constraint
            # beside it is what actually enforces the rule for the NULL case,
            # because `section` is nullable and Postgres treats NULLs as
            # distinct.
            models.UniqueConstraint(
                fields=['branch', 'date', 'academic_class', 'section',
                        'period', 'student'],
                name='classatt_unique_period_student',
            ),
            models.UniqueConstraint(
                fields=['branch', 'date', 'academic_class', 'period', 'student'],
                condition=models.Q(section__isnull=True),
                name='classatt_unique_no_section',
            ),
        ]

    def __str__(self):
        return f'{self.student} · {self.date} · {self.period} · {self.status}'
