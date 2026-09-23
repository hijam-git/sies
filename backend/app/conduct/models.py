"""The observation register — নামাজ, কুরআন, আদব (docs/02 §4.10).

What this is, and what it is not: exam marks say what a student **knows**, and
this says what they **do**. A madrasah's day turns on নামাজে উপস্থিতি, তিলাওয়াত
and আদব long before it turns on a half-yearly paper, and none of that fits a
`Mark` — there is no full-marks, no pass mark, and no exam it belongs to.

Four tables, and the shape is deliberately the one this project already has for
attendance, because it is the same act: a teacher, standing in front of a class,
recording one small thing about each student.

    forms.Question   the question bank — ALREADY BUILT, with its own editor
    ReportTemplate   which section of it to ask, how often, and of whom
    StudentReport    one student's sheet for one period
      └─ ReportAnswer one question's answer on it

**There is no second question model.** `forms.Question` already holds text in
both languages, a type (yes/no, single choice, number, short text…), options,
ordering and an active flag — and Settings → Questions is already a screen for
writing them, with drag-ordering. A report template names a **section** of that
bank; the questions in it are the sheet, in their own order. An institution
adds নামাজ by adding a question, exactly as it adds one to the admission form.

**The template is the customisation.** Narrowed to a বিভাগ or a class where
that matters — a হিফজ template must not appear on a general class's screen —
and nothing in the code knows what নামাজ is.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import BranchScopedModel


class ReportFrequency(models.TextChoices):
    """How often a sheet is filled — and therefore what `StudentReport.period`
    holds: a date, an ISO week, a month, or a term."""

    DAILY = 'daily', _('Daily · প্রতিদিন')
    WEEKLY = 'weekly', _('Weekly · সাপ্তাহিক')
    MONTHLY = 'monthly', _('Monthly · মাসিক')
    TERM = 'term', _('Per term · সাময়িক')


class ReportStatus(models.TextChoices):
    DRAFT = 'draft', _('Draft · খসড়া')
    SUBMITTED = 'submitted', _('Submitted · জমা')


class ReportTemplate(BranchScopedModel):
    """What this institution observes, how often, and for whom."""

    name = models.CharField(_('name · নাম'), max_length=80)
    name_bn = models.CharField(_('নাম'), max_length=80, blank=True)
    frequency = models.CharField(_('frequency · কত ঘনঘন'), max_length=10,
                                 choices=ReportFrequency.choices,
                                 default=ReportFrequency.DAILY)

    #: NULL means every বিভাগ / every class. The narrowing exists because a
    #: হিফজ template on a general class's screen is four questions a teacher
    #: has to skip every single day.
    stream = models.ForeignKey(
        'branches.Stream', verbose_name=_('বিভাগ · stream'),
        null=True, blank=True, on_delete=models.PROTECT, related_name='report_templates',
    )
    academic_class = models.ForeignKey(
        'academics.AcademicClass', verbose_name=_('class · শ্রেণি'),
        null=True, blank=True, on_delete=models.PROTECT, related_name='report_templates',
    )

    #: Which section of the question bank this sheet asks. `forms.Question`
    #: groups by section already — the admission form's `question_set` blocks
    #: use the same field — so a section is how an institution says "these
    #: questions are the daily আমল sheet" without a second bank to maintain.
    section = models.CharField(_('question section · প্রশ্নের অংশ'), max_length=60,
                               default='conduct')

    is_active = models.BooleanField(_('active · সক্রিয়'), default=True)

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('report template · রিপোর্টের নমুনা')
        verbose_name_plural = _('report templates · রিপোর্টের নমুনা')
        ordering = ['branch', 'name']
        constraints = [
            models.UniqueConstraint(fields=['branch', 'name'],
                                    name='reporttemplate_unique_name_per_branch'),
        ]

    def __str__(self):
        return self.name_bn or self.name

    def applies_to(self, academic_class) -> bool:
        """Whether this template is the one for that class."""
        if self.academic_class_id and self.academic_class_id != academic_class.pk:
            return False
        if self.stream_id and self.stream_id != academic_class.stream_id:
            return False
        return True


class ReportTemplateQuestion(BranchScopedModel):
    """Which questions THIS template asks, and in what order.

    The section alone could not answer "some reports have fewer questions, some
    more": a question belongs to exactly one section, so two templates drawing
    from `conduct` asked the identical list and the only way to differ was to
    duplicate নামাজ into a second section — two rows that then drift apart.

    So the section is the **default** and this is the **override**, which is the
    same shape as every picker on the SPA (§7b: an explicit choice beats the
    obvious default). A template with no rows here asks its whole section, which
    is what makes the quick path quick; a template with rows asks exactly those,
    in this order, and two templates may share a question without copying it.
    """

    template = models.ForeignKey(
        ReportTemplate, verbose_name=_('template · নমুনা'),
        on_delete=models.CASCADE, related_name='question_links',
    )
    question = models.ForeignKey(
        'forms.Question', verbose_name=_('question · প্রশ্ন'),
        # PROTECT, not CASCADE: dropping a question that a template asks should
        # fail loudly rather than quietly shorten somebody's sheet. Deactivating
        # it takes it off tomorrow's sheet and leaves the filled ones alone.
        on_delete=models.PROTECT, related_name='report_links',
    )
    order = models.PositiveSmallIntegerField(_('order · ক্রম'), default=0)

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('template question · নমুনার প্রশ্ন')
        verbose_name_plural = _('template questions · নমুনার প্রশ্ন')
        ordering = ['template', 'order', 'id']
        constraints = [
            models.UniqueConstraint(fields=['template', 'question'],
                                    name='templatequestion_once_per_template'),
        ]

    def __str__(self):
        return f'{self.template_id} · {self.question_id}'


class ReportAssignment(BranchScopedModel):
    """Who is responsible for filling one template for one class.

    **Responsibility, not exclusivity.** It decides what a teacher's screen
    opens on and who appears on the list of sheets nobody has filled; it does
    NOT stop a colleague covering for them. Locking the sheet to one person
    would mean a report simply does not get filled on the day they are ill,
    which is the opposite of what an institution wants from it — and
    `StudentReport.filled_by` already records who actually did it.

    The same rule `SubjectAssignment` follows for the routine (docs/08 D6):
    an assignment grants and directs, it does not fence off.
    """

    template = models.ForeignKey(
        ReportTemplate, verbose_name=_('template · নমুনা'),
        on_delete=models.CASCADE, related_name='assignments',
    )
    academic_class = models.ForeignKey(
        'academics.AcademicClass', verbose_name=_('class · শ্রেণি'),
        on_delete=models.PROTECT, related_name='conduct_assignments',
    )
    #: NULL means the whole class rather than one শাখা.
    section = models.ForeignKey(
        'academics.Section', verbose_name=_('section · শাখা'),
        null=True, blank=True, on_delete=models.PROTECT,
        related_name='conduct_assignments',
    )
    teacher = models.ForeignKey(
        'staff.Teacher', verbose_name=_('teacher · শিক্ষক'),
        on_delete=models.PROTECT, related_name='conduct_assignments',
    )

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('report assignment · রিপোর্টের দায়িত্ব')
        verbose_name_plural = _('report assignments · রিপোর্টের দায়িত্ব')
        ordering = ['template', 'academic_class', 'section', 'teacher']
        constraints = [
            # Two constraints and not one, because Postgres treats NULLs as
            # distinct: without the second, "the whole class" could be assigned
            # to the same teacher twice and both rows would be legal.
            models.UniqueConstraint(
                fields=['template', 'academic_class', 'section', 'teacher'],
                condition=models.Q(section__isnull=False),
                name='reportassignment_once_per_section',
            ),
            models.UniqueConstraint(
                fields=['template', 'academic_class', 'teacher'],
                condition=models.Q(section__isnull=True),
                name='reportassignment_once_per_class',
            ),
        ]

    def __str__(self):
        return f'{self.template_id} · {self.academic_class_id} → {self.teacher_id}'


class StudentReport(BranchScopedModel):
    """One student's sheet for one period."""

    template = models.ForeignKey(
        ReportTemplate, verbose_name=_('template · নমুনা'),
        on_delete=models.PROTECT, related_name='reports',
    )
    #: The enrolment, not the student: a report belongs to a class and a
    #: session, and a student who repeats a year has two of both. This is the
    #: same reason the attendance register and the marks grid are keyed on it.
    enrolment = models.ForeignKey(
        'academics.Enrolment', verbose_name=_('enrolment · ভর্তি'),
        on_delete=models.PROTECT, related_name='conduct_reports',
    )
    student = models.ForeignKey(
        'students.Student', verbose_name=_('student · শিক্ষার্থী'),
        on_delete=models.PROTECT, related_name='conduct_reports',
    )

    #: What the period IS depends on the template's frequency: `2026-09-23`
    #: daily, `2026-W39` weekly, `2026-09` monthly, `2026-T1` per term. One
    #: string rather than four nullable columns, because nothing ever needs to
    #: ask "which week" without first knowing the frequency it belongs to.
    period = models.CharField(_('period · সময়'), max_length=12)

    status = models.CharField(_('status · অবস্থা'), max_length=10,
                              choices=ReportStatus.choices, default=ReportStatus.SUBMITTED)
    remarks = models.CharField(_('remarks · মন্তব্য'), max_length=200, blank=True)

    #: Who filled it in. SET_NULL for the usual audit reason (CLAUDE.md §4.2):
    #: a teacher who leaves must not take a term of observations with them.
    filled_by = models.ForeignKey(
        'staff.Teacher', verbose_name=_('filled by · যিনি দিয়েছেন'),
        null=True, blank=True, on_delete=models.SET_NULL, related_name='conduct_reports',
    )
    filled_at = models.DateTimeField(_('filled at · সময়'), null=True, blank=True)

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('student report · শিক্ষার্থীর রিপোর্ট')
        verbose_name_plural = _('student reports · শিক্ষার্থীর রিপোর্ট')
        ordering = ['-period', 'enrolment_id']
        constraints = [
            # One sheet per student per period per template. This is what makes
            # saving the grid safe to repeat — the same idempotency the monthly
            # fee job rests on, for the same reason: two teachers with the same
            # class open on two phones must not produce two sheets.
            models.UniqueConstraint(
                fields=['branch', 'template', 'enrolment', 'period'],
                name='studentreport_one_per_period',
            ),
        ]
        indexes = [
            models.Index(fields=['branch', 'template', 'period'],
                         name='studentreport_sheet_idx'),
            models.Index(fields=['student', '-period'], name='studentreport_history_idx'),
        ]

    def __str__(self):
        return f'{self.student_id} · {self.period}'


class ReportAnswer(BranchScopedModel):
    """One item's answer on one sheet."""

    report = models.ForeignKey(
        StudentReport, verbose_name=_('report · রিপোর্ট'),
        on_delete=models.CASCADE, related_name='answers',
    )
    #: The question from the bank (`forms.Question`). PROTECT: an answer is a
    #: record of what was asked, and deleting the question would leave a value
    #: nobody can read. Deactivate it instead — `is_active` takes it off
    #: tomorrow's sheet and leaves every sheet already filled intact.
    item = models.ForeignKey(
        'forms.Question', verbose_name=_('question · প্রশ্ন'),
        on_delete=models.PROTECT, related_name='conduct_answers',
    )

    #: The answer, in whatever shape its item takes: `true`, `"good"`, `12`,
    #: `"আজ দেরিতে এসেছে"`. JSON rather than five nullable columns — the item
    #: says what the value means, and a column per type is four NULLs on every
    #: row plus a rule nothing enforces about which one is filled.
    value = models.JSONField(_('answer · উত্তর'), null=True, blank=True)

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('report answer · উত্তর')
        verbose_name_plural = _('report answers · উত্তর')
        ordering = ['report', 'item__order', 'item_id']
        constraints = [
            models.UniqueConstraint(fields=['report', 'item'],
                                    name='reportanswer_one_per_item'),
        ]

    def __str__(self):
        return f'{self.item_id}={self.value!r}'
