"""Exams, their schedule and the marks entered against them (docs/03 §9).

**Marks are the record; grades are read through the বিভাগ's scale.** A
`GradeScale` per stream — board GPA or Qawmi grades, with bands the institution
edits — turns marks into grades while an exam is open, and `publish_exam()`
freezes the outcome into one `Result` row per student. A published marksheet
therefore never moves when a scale is edited later. `grading.py` holds the two
methods and their presets.

Marks are `Decimal`, never `float`. A binary float cannot represent 0.1, so a
tabulation sheet built on one disagrees with the sum of its own column, and the
first person to notice is a guardian holding a marksheet.
"""

from decimal import Decimal

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import BranchScopedModel


class ExamType(models.TextChoices):
    MONTHLY = 'monthly', _('Monthly · মাসিক')
    HALF_YEARLY = 'half_yearly', _('Half-yearly · অর্ধবার্ষিক')
    ANNUAL = 'annual', _('Annual · বার্ষিক')
    TEST = 'test', _('Test · টেস্ট')
    # The two madrasah forms (docs/08 D1): `sabaq` is the daily/weekly lesson
    # examination of a qaumi or hifz department, `board` the external বোর্ড
    # পরীক্ষা whose marks arrive from outside and are only recorded here.
    SABAQ = 'sabaq', _('Sabaq · সবক')
    BOARD = 'board', _('Board · বোর্ড পরীক্ষা')


class ExamStatus(models.TextChoices):
    """The lifecycle of docs/06 #12, in order. Only `publish_exam()` reaches
    PUBLISHED, and only a principal may call it."""

    DRAFT = 'draft', _('Draft · খসড়া')
    SCHEDULED = 'scheduled', _('Scheduled · সময়সূচি হয়েছে')
    ONGOING = 'ongoing', _('Ongoing · চলমান')
    MARKS_ENTRY = 'marks_entry', _('Marks entry · নম্বর এন্ট্রি')
    PUBLISHED = 'published', _('Published · ফল প্রকাশিত')


class Exam(BranchScopedModel):
    """One examination event of one stream, in one session."""

    # PROTECT throughout: an exam is pointed at by every mark entered under it,
    # so deleting the session or the stream it belongs to must fail loudly
    # rather than take a year's academic record with it (CLAUDE.md §4.2).
    session = models.ForeignKey(
        'branches.Session', verbose_name=_('session · শিক্ষাবর্ষ'),
        on_delete=models.PROTECT, related_name='exams',
    )
    stream = models.ForeignKey(
        'branches.Stream', verbose_name=_('stream · বিভাগ'),
        on_delete=models.PROTECT, related_name='exams',
    )

    name = models.CharField(_('name'), max_length=100)
    name_bn = models.CharField(_('নাম'), max_length=100, blank=True)
    exam_type = models.CharField(
        _('type · ধরন'), max_length=20,
        choices=ExamType.choices, default=ExamType.MONTHLY,
    )

    starts_on = models.DateField(_('starts on · শুরু'))
    ends_on = models.DateField(_('ends on · শেষ'))

    status = models.CharField(
        _('status · অবস্থা'), max_length=20,
        choices=ExamStatus.choices, default=ExamStatus.DRAFT, db_index=True,
    )

    # SET_NULL, like every audit reference on this project: the principal who
    # published a 2026 result may leave in 2028, and their departure must not
    # erase the fact that the result was published, nor the marks under it.
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_('published by · প্রকাশক'),
        null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    published_at = models.DateTimeField(
        _('published at · প্রকাশের সময়'), null=True, blank=True,
    )

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('exam · পরীক্ষা')
        verbose_name_plural = _('exams · পরীক্ষাসমূহ')
        ordering = ['branch', '-starts_on', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['branch', 'session', 'stream', 'name'],
                name='exam_unique_name_per_session_stream',
            ),
            # An exam that ends before it starts prints a schedule nobody can
            # sit and makes every "exams this month" filter wrong.
            models.CheckConstraint(
                condition=models.Q(ends_on__gte=models.F('starts_on')),
                name='exam_ends_after_start',
            ),
            # Published means published *by someone, at some time*. Half of that
            # pair on its own is a row that cannot answer "who released this
            # result", which is the first question asked when one is disputed.
            models.CheckConstraint(
                condition=(
                    ~models.Q(status=ExamStatus.PUBLISHED)
                    | models.Q(published_at__isnull=False)
                ),
                name='exam_published_has_timestamp',
            ),
        ]
        indexes = [
            models.Index(fields=['branch', 'session', 'status'],
                         name='exam_branch_session_status_idx'),
        ]

    def __str__(self):
        return f'{self.name} · {self.session.name}'

    @property
    def is_published(self):
        return self.status == ExamStatus.PUBLISHED


class ExamClass(BranchScopedModel):
    """Which classes sit this exam.

    A join table rather than a `classes` M2M on `Exam` so it can carry the
    branch column every other row in this project carries, and so a per-class
    detail (a different result-publication date, say) has somewhere to land
    without a migration that rewrites a many-to-many.
    """

    # CASCADE: this row is meaningless without its exam and says nothing on its
    # own — exactly the case CLAUDE.md §4.2 reserves CASCADE for. The marks
    # themselves are PROTECTed, so an exam with marks cannot be deleted anyway.
    exam = models.ForeignKey(
        Exam, verbose_name=_('exam · পরীক্ষা'),
        on_delete=models.CASCADE, related_name='exam_classes',
    )
    academic_class = models.ForeignKey(
        'academics.AcademicClass', verbose_name=_('class · শ্রেণি'),
        on_delete=models.PROTECT, related_name='exam_classes',
    )

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('exam class · পরীক্ষার শ্রেণি')
        verbose_name_plural = _('exam classes · পরীক্ষার শ্রেণিসমূহ')
        ordering = ['branch', 'exam', 'academic_class']
        constraints = [
            models.UniqueConstraint(
                fields=['exam', 'academic_class'],
                name='examclass_unique_per_exam',
            ),
        ]

    def __str__(self):
        return f'{self.exam.name} · {self.academic_class.name}'


class ExamSchedule(BranchScopedModel):
    """One paper: this class sits this subject on this date, in this room."""

    exam = models.ForeignKey(
        Exam, verbose_name=_('exam · পরীক্ষা'),
        on_delete=models.CASCADE, related_name='schedules',
    )
    academic_class = models.ForeignKey(
        'academics.AcademicClass', verbose_name=_('class · শ্রেণি'),
        on_delete=models.PROTECT, related_name='exam_schedules',
    )
    subject = models.ForeignKey(
        'academics.Subject', verbose_name=_('subject · বিষয়'),
        on_delete=models.PROTECT, related_name='exam_schedules',
    )

    date = models.DateField(_('date · তারিখ'))
    start_time = models.TimeField(_('starts · শুরু'))
    end_time = models.TimeField(_('ends · শেষ'))

    # Decimal and not an integer, even though `Subject.full_marks` is an
    # integer: a paper is regularly out of 37.5 in a madrasah where the written
    # and oral parts are split, and rounding it at entry is how a tabulation
    # sheet stops adding up. Copied from the subject when the schedule is
    # created, then editable — a half-yearly may be out of 50 where the annual
    # is out of 100, and last year's schedule must not change when the subject
    # is re-weighted.
    full_marks = models.DecimalField(
        _('full marks · পূর্ণমান'), max_digits=6, decimal_places=2,
    )
    pass_marks = models.DecimalField(
        _('pass marks · পাস নম্বর'), max_digits=6, decimal_places=2,
    )

    room = models.CharField(_('room · কক্ষ'), max_length=40, blank=True)

    # SET_NULL: an invigilator who leaves must not make the schedule
    # undeletable, and must certainly not delete the paper they invigilated.
    invigilator = models.ForeignKey(
        'staff.Teacher', verbose_name=_('invigilator · পরিদর্শক'),
        null=True, blank=True, on_delete=models.SET_NULL,
        related_name='invigilations',
    )

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('exam schedule · পরীক্ষার সময়সূচি')
        verbose_name_plural = _('exam schedules · পরীক্ষার সময়সূচি')
        ordering = ['branch', 'exam', 'date', 'start_time']
        constraints = [
            # One class sits one subject once in one exam. Two rows would print
            # the paper twice on the routine and give marks entry two grids for
            # the same sheet of answers.
            models.UniqueConstraint(
                fields=['exam', 'academic_class', 'subject'],
                name='examschedule_unique_paper',
            ),
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F('start_time')),
                name='examschedule_ends_after_start',
            ),
            # A pass mark above the full mark fails every student silently, and
            # the report it breaks is printed months later.
            models.CheckConstraint(
                condition=models.Q(pass_marks__lte=models.F('full_marks')),
                name='examschedule_pass_within_full',
            ),
        ]
        indexes = [
            models.Index(fields=['branch', 'exam', 'academic_class'],
                         name='examsched_exam_class_idx'),
        ]

    def __str__(self):
        return f'{self.exam.name} · {self.subject.name} · {self.date}'


class Mark(BranchScopedModel):
    """One student's mark in one subject of one exam.

    `enrolment` is stored alongside `student` and is not redundant: the student
    is the person, the enrolment is *which class they were in when they sat
    this*. A student who repeats a year has two enrolments and two sets of
    marks, and only the enrolment can tell them apart (docs/05 §3.2).
    """

    # PROTECT on the exam, deliberately not CASCADE. Marks are academic history
    # — the one record an institution is asked to reproduce years later — so
    # deleting an exam that has marks must fail rather than erase them. An exam
    # with no marks deletes freely, which is the only case a delete is meant for.
    exam = models.ForeignKey(
        Exam, verbose_name=_('exam · পরীক্ষা'),
        on_delete=models.PROTECT, related_name='marks',
    )
    student = models.ForeignKey(
        'students.Student', verbose_name=_('student · শিক্ষার্থী'),
        on_delete=models.PROTECT, related_name='marks',
    )
    enrolment = models.ForeignKey(
        'academics.Enrolment', verbose_name=_('enrolment · ভর্তি'),
        on_delete=models.PROTECT, related_name='marks',
    )
    subject = models.ForeignKey(
        'academics.Subject', verbose_name=_('subject · বিষয়'),
        on_delete=models.PROTECT, related_name='marks',
    )

    # Null, not zero. Zero is a mark a student earned; null is a mark nobody has
    # entered yet, and a tabulation that cannot tell them apart reports an
    # unfinished entry grid as a room full of failures.
    obtained = models.DecimalField(
        _('obtained · প্রাপ্ত নম্বর'), max_digits=6, decimal_places=2,
        null=True, blank=True,
    )
    practical_obtained = models.DecimalField(
        _('practical · ব্যবহারিক'), max_digits=6, decimal_places=2,
        null=True, blank=True,
    )
    is_absent = models.BooleanField(_('absent · অনুপস্থিত'), default=False)

    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_('entered by · এন্ট্রিকারী'),
        null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    entered_at = models.DateTimeField(_('entered at · এন্ট্রির সময়'))

    # Soft delete only (CLAUDE.md §4.2). A mark removed by hand from a published
    # exam changes a result that has already been read out.
    is_active = models.BooleanField(_('active · সক্রিয়'), default=True)

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('mark · নম্বর')
        verbose_name_plural = _('marks · নম্বরসমূহ')
        ordering = ['branch', 'exam', 'student', 'subject']
        constraints = [
            # **The constraint this table exists to carry.** Two marks for one
            # paper is the bug: the entry grid is saved twice, the tabulation
            # sums both rows, and one student's total is silently double. The
            # branch is not in the key — the exam already belongs to exactly one
            # institution, so adding it would only weaken the guarantee.
            models.UniqueConstraint(
                fields=['exam', 'student', 'subject'],
                name='mark_unique_per_paper',
            ),
            # Absent and a number are contradictory claims about the same
            # student, and whichever one a report happens to read is wrong.
            models.CheckConstraint(
                condition=(
                    models.Q(is_absent=False)
                    | (models.Q(obtained__isnull=True)
                       & models.Q(practical_obtained__isnull=True))
                ),
                name='mark_absent_has_no_score',
            ),
            models.CheckConstraint(
                condition=(models.Q(obtained__isnull=True) | models.Q(obtained__gte=0)),
                name='mark_obtained_not_negative',
            ),
            models.CheckConstraint(
                condition=(models.Q(practical_obtained__isnull=True)
                           | models.Q(practical_obtained__gte=0)),
                name='mark_practical_not_negative',
            ),
        ]
        indexes = [
            # The marks-entry grid: one exam, one subject, every student.
            models.Index(fields=['branch', 'exam', 'subject'],
                         name='mark_exam_subject_idx'),
            # The student's own marksheet, and `/api/me/`.
            models.Index(fields=['branch', 'student'], name='mark_student_idx'),
        ]

    def __str__(self):
        score = 'AB' if self.is_absent else (self.obtained if self.obtained is not None else '—')
        return f'{self.student_id}/{self.subject_id}: {score}'

    @property
    def total_obtained(self):
        """Written plus practical, or None when nothing has been entered.

        A property and not a column: it is a sum of two fields on the same row,
        so storing it could only ever disagree with them (CLAUDE.md §4.2).
        """
        if self.is_absent:
            return None
        if self.obtained is None and self.practical_obtained is None:
            return None
        return (self.obtained or 0) + (self.practical_obtained or 0)


class GradingMethod(models.TextChoices):
    """How a scale turns marks into a grade — see `grading.py`."""

    GPA = 'gpa', _('GPA (board) · জিপিএ')
    DIVISION = 'division', _('Qawmi grades · কওমি পদ্ধতি')


class GradeScale(BranchScopedModel):
    """How one বিভাগ grades. One per stream, plus an optional institution default.

    Per stream because the Qawmi stream's marksheet is not the general stream's
    GPA (docs/02 §4.7), and a madrasah runs both side by side.
    """

    # Null is the institution-wide fallback for a stream with no scale of its
    # own. PROTECT: a scale is how every result in its stream was graded.
    stream = models.ForeignKey(
        'branches.Stream', verbose_name=_('stream · বিভাগ'),
        null=True, blank=True, on_delete=models.PROTECT, related_name='grade_scales',
    )
    name = models.CharField(_('name'), max_length=80)
    name_bn = models.CharField(_('নাম'), max_length=80, blank=True)
    method = models.CharField(
        _('method · পদ্ধতি'), max_length=20,
        choices=GradingMethod.choices, default=GradingMethod.GPA,
    )
    # The board rule for an optional (4th) subject: only the points above this
    # are added to the GPA. Ignored under the division method.
    optional_bonus_above = models.DecimalField(
        _('optional subject bonus above · ঐচ্ছিক বিষয়ের বোনাস'),
        max_digits=3, decimal_places=2, default=Decimal('2.00'),
    )
    is_active = models.BooleanField(_('active · সক্রিয়'), default=True)

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('grade scale · গ্রেডিং পদ্ধতি')
        verbose_name_plural = _('grade scales · গ্রেডিং পদ্ধতি')
        ordering = ['branch_id', 'stream_id', 'name']
        constraints = [
            # Two constraints rather than one unique_together: Postgres treats
            # NULLs as distinct, so ('branch', 'stream') alone would allow any
            # number of institution defaults (docs/WORKLOG, the same trap twice).
            models.UniqueConstraint(
                fields=['branch', 'stream'], condition=models.Q(stream__isnull=False),
                name='gradescale_one_per_stream',
            ),
            models.UniqueConstraint(
                fields=['branch'], condition=models.Q(stream__isnull=True),
                name='gradescale_one_default_per_branch',
            ),
            models.CheckConstraint(
                condition=models.Q(optional_bonus_above__gte=0, optional_bonus_above__lte=5),
                name='gradescale_bonus_within_scale',
            ),
        ]

    def __str__(self):
        return self.name


class GradeBand(BranchScopedModel):
    """One grade: from this percentage up, this name and point."""

    # CASCADE: a band means nothing without its scale — exactly the case
    # CLAUDE.md §4.2 reserves CASCADE for. Published results do not point here;
    # they carry the grade they were given.
    scale = models.ForeignKey(
        GradeScale, verbose_name=_('scale · পদ্ধতি'),
        on_delete=models.CASCADE, related_name='bands',
    )
    min_percent = models.DecimalField(_('from % · শুরু %'), max_digits=5, decimal_places=2)
    grade = models.CharField(_('grade · গ্রেড'), max_length=30)
    grade_bn = models.CharField(_('গ্রেড (বাংলা)'), max_length=40, blank=True)
    point = models.DecimalField(_('point · পয়েন্ট'), max_digits=3, decimal_places=2,
                                default=Decimal('0.00'))
    is_fail = models.BooleanField(_('fail · অনুত্তীর্ণ'), default=False)

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('grade band · গ্রেড')
        verbose_name_plural = _('grade bands · গ্রেডসমূহ')
        ordering = ['scale_id', '-min_percent']
        constraints = [
            models.UniqueConstraint(fields=['scale', 'min_percent'],
                                    name='gradeband_unique_floor'),
            models.CheckConstraint(
                condition=models.Q(min_percent__gte=0, min_percent__lte=100),
                name='gradeband_floor_is_a_percentage',
            ),
            models.CheckConstraint(
                condition=models.Q(point__gte=0, point__lte=5),
                name='gradeband_point_within_scale',
            ),
        ]

    def __str__(self):
        return f'{self.grade} ≥ {self.min_percent}%'


class Result(BranchScopedModel):
    """One student's result for one exam, frozen when the exam was published.

    `row` is the tabulation row exactly as it was computed and `subjects` the
    marksheet's subject lines, so a result reprinted in three years is the
    result that was read out — even after the scale is edited (docs/06 #12).
    The scalar columns duplicate what matters for querying and reports.
    """

    exam = models.ForeignKey(Exam, verbose_name=_('exam · পরীক্ষা'),
                             on_delete=models.PROTECT, related_name='results')
    student = models.ForeignKey('students.Student', verbose_name=_('student · শিক্ষার্থী'),
                                on_delete=models.PROTECT, related_name='exam_results')
    enrolment = models.ForeignKey('academics.Enrolment', verbose_name=_('enrolment · ভর্তি'),
                                  on_delete=models.PROTECT, related_name='exam_results')

    method = models.CharField(_('method · পদ্ধতি'), max_length=20, choices=GradingMethod.choices)
    scale_name = models.CharField(_('scale · পদ্ধতি'), max_length=80, blank=True)
    scale_name_bn = models.CharField(_('পদ্ধতি (বাংলা)'), max_length=80, blank=True)

    percentage = models.DecimalField(_('percentage · শতকরা'), max_digits=5, decimal_places=2)
    gpa = models.DecimalField(_('GPA · জিপিএ'), max_digits=3, decimal_places=2,
                              null=True, blank=True)
    grade = models.CharField(_('grade · গ্রেড'), max_length=30)
    grade_bn = models.CharField(_('গ্রেড (বাংলা)'), max_length=40, blank=True)
    is_passed = models.BooleanField(_('passed · উত্তীর্ণ'))
    rank_in_class = models.PositiveIntegerField(_('class rank · শ্রেণিতে মেধাক্রম'),
                                                null=True, blank=True)
    rank_in_section = models.PositiveIntegerField(_('section rank · শাখায় মেধাক্রম'),
                                                  null=True, blank=True)

    row = models.JSONField(_('tabulation row'), encoder=DjangoJSONEncoder)
    subjects = models.JSONField(_('subject lines'), encoder=DjangoJSONEncoder)

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('result · ফলাফল')
        verbose_name_plural = _('results · ফলাফল')
        ordering = ['exam_id', 'enrolment_id']
        constraints = [
            models.UniqueConstraint(fields=['exam', 'enrolment'],
                                    name='result_one_per_exam_enrolment'),
        ]
        indexes = [
            models.Index(fields=['branch', 'student'], name='result_student_idx'),
        ]

    def __str__(self):
        return f'{self.exam_id}/{self.student_id}: {self.grade}'

