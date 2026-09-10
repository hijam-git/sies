"""Classes, sections, subjects, the bell schedule, the timetable and enrolment
(docs/03 §3, docs/08 D6 and D7).

Three things in this file carry more weight than their size suggests:

* **`Enrolment`** is the join that makes the whole model work. A `Student` is a
  person; an enrolment is that person in a class, in a section, in a session. The
  brief's "admission history" is `student.enrolments.all()` — no history table,
  no duplicated data, no drift.
* **`ClassRoutine`** carries two unique constraints, and the second is the
  valuable one: a teacher cannot be in two rooms at once. Timetable clashes are
  the classic school-software bug, and this makes the database refuse them rather
  than trusting a validator someone forgets to call.
* **`SubjectAssignment`** does double duty (D6): it records the teaching
  assignment *and* forms half of a teacher's access scope. See
  `services.teacher_class_scope`.

Models in other apps are referenced by string — `'staff.Teacher'`,
`'students.Student'` — so `makemigrations` can resolve the mutual dependency
between `academics` and `students` itself (docs/WORKLOG F17). Never hand-edit a
migration's dependency list to break that cycle; generate the apps together.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import BranchScopedModel


class DayOfWeek(models.IntegerChoices):
    """The Bangladeshi week: Saturday is day 0 and Friday is the weekend.

    Not Python's `date.weekday()` (Monday=0) and not `isoweekday()`. The routine
    grid is printed and read starting on Saturday, so storing the display order
    means neither the grid nor the "today's classes" board has to rotate the
    week on every render. `services.today_index()` is the one place that
    converts.
    """

    SATURDAY = 0, _('Saturday · শনিবার')
    SUNDAY = 1, _('Sunday · রবিবার')
    MONDAY = 2, _('Monday · সোমবার')
    TUESDAY = 3, _('Tuesday · মঙ্গলবার')
    WEDNESDAY = 4, _('Wednesday · বুধবার')
    THURSDAY = 5, _('Thursday · বৃহস্পতিবার')
    FRIDAY = 6, _('Friday · শুক্রবার')


class EnrolmentStatus(models.TextChoices):
    ACTIVE = 'active', _('Active · অধ্যয়নরত')
    PROMOTED = 'promoted', _('Promoted · উত্তীর্ণ')
    PASSED = 'passed', _('Passed out · সমাপ্ত')
    WITHDRAWN = 'withdrawn', _('Withdrawn · প্রত্যাহার')
    TRANSFERRED = 'transferred', _('Transferred · স্থানান্তরিত')


class AcademicClass(BranchScopedModel):
    """One class, in one stream, in one session.

    The year is deliberately **not** baked into `name` (docs/03 §3). `name` is
    `Class 10`; the session and year are their own fields. Baking it in would
    make "Class 10 across five years" a string-prefix search and make promotion
    logic parse text.
    """

    # PROTECT throughout: a class points at a stream and a session, and both are
    # pointed at in turn by every enrolment, fee and mark under this class.
    # Deleting either must fail loudly rather than silently orphan a year's
    # academic record (CLAUDE.md §4.2).
    stream = models.ForeignKey(
        'branches.Stream',
        verbose_name=_('stream · শাখা'),
        on_delete=models.PROTECT,
        related_name='classes',
    )
    session = models.ForeignKey(
        'branches.Session',
        verbose_name=_('session · শিক্ষাবর্ষ'),
        on_delete=models.PROTECT,
        related_name='classes',
    )

    name = models.CharField(_('name'), max_length=60)
    name_bn = models.CharField(_('নাম'), max_length=60, blank=True)

    # Denormalised from `session.starts_on` so the common filter — "this year's
    # classes" — is an indexed integer comparison instead of a join. Written by
    # `save()` below, never typed by a caller.
    year = models.PositiveIntegerField(_('year · সাল'), db_index=True)

    # Sort order, and also what drives promotion: next year's class is the one
    # with the next `level_order` in the same stream. A name cannot do that job —
    # 'Nazera' does not sort before 'Mizan' alphabetically.
    level_order = models.PositiveIntegerField(_('level · স্তর'), default=0)
    capacity = models.PositiveIntegerField(_('capacity · আসন'), null=True, blank=True)

    # docs/08 D6: the responsible teacher, and half of what that teacher may
    # reach. SET_NULL, not PROTECT — a teacher leaving mid-year must not make the
    # class undeletable or the deletion cascade into a year's enrolments; the
    # class simply has no class teacher until one is named.
    class_teacher = models.ForeignKey(
        'staff.Teacher',
        verbose_name=_('class teacher · শ্রেণি শিক্ষক'),
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='classes_in_charge',
    )

    # A convenience default the fee module reads when no FeeStructure overrides
    # it. Null means "not decided", which is not the same as free.
    monthly_fee = models.DecimalField(
        _('monthly fee · মাসিক বেতন'),
        max_digits=12, decimal_places=2, null=True, blank=True,
    )
    is_active = models.BooleanField(_('active · সক্রিয়'), default=True)

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('class · শ্রেণি')
        verbose_name_plural = _('classes · শ্রেণিসমূহ')
        ordering = ['branch', '-year', 'level_order', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['branch', 'session', 'stream', 'name'],
                name='class_unique_per_session_stream',
            ),
        ]
        indexes = [
            models.Index(fields=['branch', 'session', 'level_order'],
                         name='class_branch_session_idx'),
        ]

    def __str__(self):
        return f'{self.name} · {self.session.name}'

    def save(self, *args, **kwargs):
        # Kept in step with the session on every write rather than only on
        # create: a session whose dates are corrected must not leave last year's
        # classes filed under the wrong year.
        if self.session_id and not self.year:
            self.year = self.session.starts_on.year
        return super().save(*args, **kwargs)


class Section(BranchScopedModel):
    """A division of a class — `A`, `Boys`, `Batch-1`."""

    # CASCADE: a section has no meaning without its class, and deleting a class
    # is already refused by PROTECT the moment it has an enrolment. So this
    # cascade can only ever fire on an empty class.
    academic_class = models.ForeignKey(
        AcademicClass,
        verbose_name=_('class · শ্রেণি'),
        on_delete=models.CASCADE,
        related_name='sections',
    )
    name = models.CharField(_('name · নাম'), max_length=40)
    name_bn = models.CharField(_('নাম'), max_length=40, blank=True)
    capacity = models.PositiveIntegerField(_('capacity · আসন'), null=True, blank=True)
    room = models.CharField(_('room · কক্ষ'), max_length=40, blank=True)

    # docs/08 D6, the section-level half of class responsibility. SET_NULL for
    # the same reason as `AcademicClass.class_teacher`.
    in_charge = models.ForeignKey(
        'staff.Teacher',
        verbose_name=_('in charge · দায়িত্বপ্রাপ্ত শিক্ষক'),
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='sections_in_charge',
    )
    is_active = models.BooleanField(_('active · সক্রিয়'), default=True)

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('section · শাখা')
        verbose_name_plural = _('sections · শাখাসমূহ')
        ordering = ['branch', 'academic_class', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['academic_class', 'name'],
                name='section_unique_per_class',
            ),
        ]

    def __str__(self):
        return f'{self.academic_class.name} — {self.name}'


class Subject(BranchScopedModel):
    """One subject taught to one class."""

    stream = models.ForeignKey(
        'branches.Stream',
        verbose_name=_('stream · শাখা'),
        on_delete=models.PROTECT,
        related_name='subjects',
    )
    # PROTECT, not CASCADE: marks and the routine point at a subject, so removing
    # the class it belongs to must fail rather than take an exam's marks with it.
    academic_class = models.ForeignKey(
        AcademicClass,
        verbose_name=_('class · শ্রেণি'),
        on_delete=models.PROTECT,
        related_name='subjects',
    )

    name = models.CharField(_('name'), max_length=80)
    name_bn = models.CharField(_('নাম'), max_length=80, blank=True)
    code = models.CharField(_('code · কোড'), max_length=20, blank=True)

    full_marks = models.PositiveIntegerField(_('full marks · পূর্ণমান'), default=100)
    pass_marks = models.PositiveIntegerField(_('pass marks · পাস নম্বর'), default=33)
    is_optional = models.BooleanField(_('optional · ঐচ্ছিক'), default=False)
    has_practical = models.BooleanField(_('has practical · ব্যবহারিক আছে'), default=False)
    practical_marks = models.PositiveIntegerField(
        _('practical marks · ব্যবহারিক নম্বর'), default=0,
    )
    is_active = models.BooleanField(_('active · সক্রিয়'), default=True)

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('subject · বিষয়')
        verbose_name_plural = _('subjects · বিষয়সমূহ')
        ordering = ['branch', 'academic_class', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['academic_class', 'name'],
                name='subject_unique_name_per_class',
            ),
            # A pass mark above the full mark makes every student fail, silently,
            # and the report it breaks is printed months later.
            models.CheckConstraint(
                condition=models.Q(pass_marks__lte=models.F('full_marks')),
                name='subject_pass_within_full',
            ),
        ]

    def __str__(self):
        return f'{self.name} · {self.academic_class.name}'


class Period(BranchScopedModel):
    """The institution's bell schedule, defined once (docs/08 D7).

    A table rather than start/end times on every routine row: an institution
    changing its schedule for Ramadan edits eight rows, not five hundred.
    """

    # Null means every stream. A hifz stream often starts after Fajr while the
    # general stream starts at nine, so the schedule is per stream where it needs
    # to be and shared where it does not.
    stream = models.ForeignKey(
        'branches.Stream',
        verbose_name=_('stream · শাখা'),
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name='periods',
    )
    name = models.CharField(_('name'), max_length=30)
    name_bn = models.CharField(_('নাম'), max_length=30, blank=True)
    order = models.PositiveIntegerField(_('order · ক্রম'))
    start_time = models.TimeField(_('starts · শুরু'))
    end_time = models.TimeField(_('ends · শেষ'))

    # Tiffin and prayer occupy a slot in the day but never appear on a teacher's
    # board and never carry attendance.
    is_break = models.BooleanField(_('break · বিরতি'), default=False)
    is_active = models.BooleanField(_('active · সক্রিয়'), default=True)

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('period · ঘণ্টা')
        verbose_name_plural = _('periods · ঘণ্টাসমূহ')
        ordering = ['branch', 'stream', 'order']
        constraints = [
            # Postgres treats NULLs as distinct in a unique index, so a
            # stream-less period would not be constrained by a plain
            # UniqueConstraint on (branch, stream, order). The two constraints
            # cover the two cases: one for a period tied to a stream, one for the
            # institution-wide schedule.
            models.UniqueConstraint(
                fields=['branch', 'stream', 'order'],
                condition=models.Q(stream__isnull=False),
                name='period_unique_order_per_stream',
            ),
            models.UniqueConstraint(
                fields=['branch', 'order'],
                condition=models.Q(stream__isnull=True),
                name='period_unique_order_branch_wide',
            ),
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F('start_time')),
                name='period_ends_after_start',
            ),
        ]

    def __str__(self):
        return f'{self.name} ({self.start_time:%H:%M}–{self.end_time:%H:%M})'


class ClassRoutine(BranchScopedModel):
    """The weekly timetable — what turns "who teaches what" into "at what time"
    (docs/08 D7).

    Drives the teacher's today board, the live attendance window and the printed
    class routine.
    """

    session = models.ForeignKey(
        'branches.Session',
        verbose_name=_('session · শিক্ষাবর্ষ'),
        on_delete=models.PROTECT,
        related_name='routines',
    )
    # CASCADE from the class and the section: a routine row is a cell in that
    # class's timetable and means nothing without it. Everything a routine row
    # points at *sideways* — subject, teacher, period — is PROTECT, because
    # deleting a subject that is still on the timetable is a mistake, not an
    # instruction.
    academic_class = models.ForeignKey(
        AcademicClass,
        verbose_name=_('class · শ্রেণি'),
        on_delete=models.CASCADE,
        related_name='routines',
    )
    section = models.ForeignKey(
        Section,
        verbose_name=_('section · শাখা'),
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='routines',
    )
    subject = models.ForeignKey(
        Subject,
        verbose_name=_('subject · বিষয়'),
        on_delete=models.PROTECT,
        related_name='routines',
    )
    teacher = models.ForeignKey(
        'staff.Teacher',
        verbose_name=_('teacher · শিক্ষক'),
        on_delete=models.PROTECT,
        related_name='routines',
    )
    period = models.ForeignKey(
        Period,
        verbose_name=_('period · ঘণ্টা'),
        on_delete=models.PROTECT,
        related_name='routines',
    )
    day_of_week = models.PositiveSmallIntegerField(
        _('day · দিন'), choices=DayOfWeek.choices,
    )
    room = models.CharField(_('room · কক্ষ'), max_length=40, blank=True)
    is_active = models.BooleanField(_('active · সক্রিয়'), default=True)

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('routine · রুটিন')
        verbose_name_plural = _('routines · রুটিন')
        ordering = ['branch', 'day_of_week', 'period', 'academic_class']
        constraints = [
            # (1) One class is in one place at one time. NULL sections again need
            # the two-constraint treatment: Postgres considers NULLs distinct, so
            # a single constraint would let a class with no sections be
            # double-booked freely.
            models.UniqueConstraint(
                fields=['branch', 'session', 'academic_class', 'section',
                        'day_of_week', 'period'],
                condition=models.Q(section__isnull=False),
                name='routine_unique_slot_per_section',
            ),
            models.UniqueConstraint(
                fields=['branch', 'session', 'academic_class', 'day_of_week', 'period'],
                condition=models.Q(section__isnull=True),
                name='routine_unique_slot_per_class',
            ),
            # (2) **The valuable one.** A teacher cannot be in two rooms at once.
            # Timetable clashes are the classic school-software bug; this makes
            # the database refuse them rather than trusting a validator somebody
            # forgets to call from the bulk-import path.
            models.UniqueConstraint(
                fields=['branch', 'session', 'teacher', 'day_of_week', 'period'],
                name='routine_unique_teacher_slot',
            ),
        ]
        indexes = [
            # The teacher's today board: "my rows, this session, this day".
            models.Index(fields=['branch', 'teacher', 'day_of_week'],
                         name='routine_teacher_day_idx'),
        ]

    def __str__(self):
        return f'{self.get_day_of_week_display()} · {self.period.name} · {self.subject.name}'


class Enrolment(BranchScopedModel):
    """A student in a class, in a section, in a session.

    Soft-deleted only (CLAUDE.md §4.2): an enrolment is what a fee, a mark and a
    day's attendance all hang off, so a hard delete would erase a student's year.
    """

    # PROTECT: deleting a student who has an enrolment must fail. Their record is
    # withdrawn (`status`), never removed — the institution has to be able to
    # answer "was this person ever a student here" years later.
    student = models.ForeignKey(
        'students.Student',
        verbose_name=_('student · শিক্ষার্থী'),
        on_delete=models.PROTECT,
        related_name='enrolments',
    )
    session = models.ForeignKey(
        'branches.Session',
        verbose_name=_('session · শিক্ষাবর্ষ'),
        on_delete=models.PROTECT,
        related_name='enrolments',
    )
    academic_class = models.ForeignKey(
        AcademicClass,
        verbose_name=_('class · শ্রেণি'),
        on_delete=models.PROTECT,
        related_name='enrolments',
    )
    section = models.ForeignKey(
        Section,
        verbose_name=_('section · শাখা'),
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name='enrolments',
    )

    roll = models.PositiveIntegerField(_('roll · রোল'))
    # Issued by `services.next_admission_number()` under a row lock — gapless per
    # branch and session, and quoted out loud at a counter (CLAUDE.md §4.4).
    admission_number = models.CharField(
        _('admission number · ভর্তি নম্বর'), max_length=30,
    )

    status = models.CharField(
        _('status · অবস্থা'), max_length=20,
        choices=EnrolmentStatus.choices, default=EnrolmentStatus.ACTIVE,
    )
    enrolled_on = models.DateField(_('enrolled on · ভর্তির তারিখ'))
    left_on = models.DateField(_('left on · প্রস্থানের তারিখ'), null=True, blank=True)

    # Both drive which recurring fees apply, which is why they live on the
    # enrolment and not on the student: a student may board one year and not the
    # next, and last year's fees must not change when they move out.
    is_hostel = models.BooleanField(_('hostel · আবাসিক'), default=False)
    is_transport = models.BooleanField(_('transport · পরিবহন'), default=False)
    is_active = models.BooleanField(_('active · সক্রিয়'), default=True)

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('enrolment · ভর্তি')
        verbose_name_plural = _('enrolments · ভর্তিসমূহ')
        ordering = ['branch', '-session', 'academic_class', 'section', 'roll']
        constraints = [
            # One roll per class/section/session. Split on section for the NULL
            # reason above — a class with no sections still must not issue roll 7
            # twice.
            models.UniqueConstraint(
                fields=['branch', 'session', 'academic_class', 'section', 'roll'],
                condition=models.Q(section__isnull=False),
                name='enrolment_unique_roll_per_section',
            ),
            models.UniqueConstraint(
                fields=['branch', 'session', 'academic_class', 'roll'],
                condition=models.Q(section__isnull=True),
                name='enrolment_unique_roll_per_class',
            ),
            # The admission number is printed on a slip the guardian keeps; two
            # students holding the same one is unrecoverable at a fee counter.
            models.UniqueConstraint(
                fields=['branch', 'admission_number'],
                name='enrolment_unique_admission_number',
            ),
            # A student enrolled twice in the same session is a data-entry
            # mistake — and it would double every recurring fee they are raised.
            models.UniqueConstraint(
                fields=['branch', 'session', 'student'],
                name='enrolment_one_per_student_per_session',
            ),
        ]
        indexes = [
            models.Index(fields=['branch', 'session', 'status'],
                         name='enrolment_session_status_idx'),
            models.Index(fields=['branch', 'academic_class', 'section'],
                         name='enrolment_class_section_idx'),
        ]

    def __str__(self):
        return f'{self.admission_number} · roll {self.roll}'


class SubjectAssignment(BranchScopedModel):
    """Which teacher teaches which subject to which class/section, per session.

    **This table does double duty** (docs/08 D6): it records the teaching
    assignment *and* forms half of the teacher's access scope — a teacher may
    enter marks only for the subjects listed here, and take period attendance
    only for these classes. The other half is class responsibility
    (`AcademicClass.class_teacher`, `Section.in_charge`).
    """

    session = models.ForeignKey(
        'branches.Session',
        verbose_name=_('session · শিক্ষাবর্ষ'),
        on_delete=models.PROTECT,
        related_name='subject_assignments',
    )
    # PROTECT on the teacher: this row is an access grant, and a delete that
    # silently cascaded would widen or narrow what someone can reach as a side
    # effect of tidying up the staff list.
    teacher = models.ForeignKey(
        'staff.Teacher',
        verbose_name=_('teacher · শিক্ষক'),
        on_delete=models.PROTECT,
        related_name='subject_assignments',
    )
    subject = models.ForeignKey(
        Subject,
        verbose_name=_('subject · বিষয়'),
        on_delete=models.CASCADE,
        related_name='assignments',
    )
    academic_class = models.ForeignKey(
        AcademicClass,
        verbose_name=_('class · শ্রেণি'),
        on_delete=models.CASCADE,
        related_name='subject_assignments',
    )
    section = models.ForeignKey(
        Section,
        verbose_name=_('section · শাখা'),
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='subject_assignments',
    )
    is_active = models.BooleanField(_('active · সক্রিয়'), default=True)

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('subject assignment · বিষয় বণ্টন')
        verbose_name_plural = _('subject assignments · বিষয় বণ্টন')
        ordering = ['branch', '-session', 'academic_class', 'subject']
        constraints = [
            models.UniqueConstraint(
                fields=['branch', 'session', 'teacher', 'subject',
                        'academic_class', 'section'],
                condition=models.Q(section__isnull=False),
                name='assignment_unique_with_section',
            ),
            models.UniqueConstraint(
                fields=['branch', 'session', 'teacher', 'subject', 'academic_class'],
                condition=models.Q(section__isnull=True),
                name='assignment_unique_without_section',
            ),
        ]
        indexes = [
            # The scope query in `services.teacher_class_scope`, which runs on
            # every scoped list request a teacher makes.
            models.Index(fields=['branch', 'session', 'teacher'],
                         name='assignment_teacher_idx'),
        ]

    def __str__(self):
        return f'{self.teacher.name} → {self.subject.name}'
