"""The printable admission form — templates, questions, answers and prints
(docs/07 §5, §6).

Four models, all V1, all branch-scoped. The two design decisions worth reading
before changing anything here:

* **`FormTemplate.blocks` is JSON, not a table** (§6.1). Blocks are only ever
  read as a whole document, always in order, never queried individually. The
  price is that the database cannot check their shape, so `blocks.validate_blocks`
  does — **in `save()`**, so a malformed block cannot reach the renderer no
  matter which code path wrote it.
* **`PrintedForm.snapshot` stores the fully resolved form** (§6). A form
  reprinted in three years must show what was signed, not what the record says
  today after a name correction. Same reasoning as storing `Result` rows rather
  than recomputing them.

`save()` doing validation is a deliberate exception to "constraints live in
Meta" (CLAUDE.md §4.2). That rule is about *database* constraints, and Postgres
cannot express "this JSON document has the shape a renderer expects". The choice
is validation in `save()` or a renderer that silently drops a section — and the
silent drop is discovered by the person holding the printed stack.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import BranchScopedModel

from .blocks import validate_blocks


class FormType(models.TextChoices):
    ADMISSION = 'admission', _('Admission form · ভর্তি ফরম')
    UNDERTAKING = 'undertaking', _('Undertaking · অঙ্গিকারনামা')
    ID_CARD = 'id_card', _('ID card · পরিচয়পত্র')
    CERTIFICATE = 'certificate', _('Certificate · সনদ')


class Paper(models.TextChoices):
    A4 = 'A4', 'A4'
    LEGAL = 'Legal', 'Legal'


class QuestionType(models.TextChoices):
    SINGLE_CHOICE = 'single_choice', _('Single choice · একটি বাছাই')
    MULTI_CHOICE = 'multi_choice', _('Multiple choice · একাধিক বাছাই')
    DESCRIPTION = 'description', _('Description · বর্ণনা')
    SHORT_TEXT = 'short_text', _('Short text · সংক্ষিপ্ত উত্তর')
    NUMBER = 'number', _('Number · সংখ্যা')
    DATE = 'date', _('Date · তারিখ')
    YES_NO = 'yes_no', _('Yes / no · হ্যাঁ / না')


class PrintStyle(models.TextChoices):
    INLINE = 'inline', _('Inline · এক লাইনে')
    BLOCK = 'block', _('Block · নিচে লাইনসহ')
    CHECKBOX = 'checkbox', _('Checkbox · ☐ ঘর')


CHOICE_TYPES = {QuestionType.SINGLE_CHOICE, QuestionType.MULTI_CHOICE}

# The closed set of student fields a question may bind to (§5.2). Closed, and
# not "any field name", because `maps_to` writes the field: an open list would
# let a form question overwrite `student_id` or `status` from the data-entry
# screen, which is a much larger hole than the duplication it was added to fix.
MAPPED_FIELDS = {
    'name': _('Name · নাম'),
    'name_bn': _('নাম (বাংলা)'),
    'date_of_birth': _('Date of birth · জন্ম তারিখ'),
    'birth_certificate_no': _('Birth certificate no · জন্ম নিবন্ধন নম্বর'),
    'phone': _('Mobile · মোবাইল'),
    'village': _('Village · গ্রাম/মহল্লা'),
    'post_office': _('Post office · ডাকঘর'),
    'upazila': _('Upazila · উপজেলা'),
    'district': _('District · জেলা'),
    'previous_institution': _('Previous institution · পূর্ববর্তী প্রতিষ্ঠান'),
    'previous_class': _('Previous class · পূর্ববর্তী শ্রেণি'),
    'present_address': _('Present address · বর্তমান ঠিকানা'),
    'permanent_address': _('Permanent address · স্থায়ী ঠিকানা'),
}


class FormTemplate(BranchScopedModel):
    """An ordered list of blocks that renders to one printable document.

    A template rather than a hard-coded page because every madrasah's form
    differs — different pledges, a different Arabic name, a different office
    panel (§2). Hard-coding one institution's form means the next branch needs a
    developer; here an admin edits the pledge list in a textarea and the printed
    form changes, with no deploy.
    """

    name = models.CharField(_('name · নাম'), max_length=100)
    name_bn = models.CharField(_('নাম'), max_length=100, blank=True)
    form_type = models.CharField(
        _('type · ধরন'), max_length=20,
        choices=FormType.choices, default=FormType.ADMISSION,
    )

    blocks = models.JSONField(
        _('blocks · ব্লক'), default=list, blank=True,
        help_text=_('Ordered list of blocks. Validated on save.'),
    )

    paper = models.CharField(
        _('paper · কাগজ'), max_length=10, choices=Paper.choices, default=Paper.A4,
    )
    # CSS margin shorthand, stored as typed. A string rather than four integer
    # columns because it is passed straight to `@page { margin: … }` and a
    # printer's usable area is expressed that way on every page it is set from.
    margins = models.CharField(_('margins · মার্জিন'), max_length=40, default='12mm 14mm')

    is_default = models.BooleanField(_('default · ডিফল্ট'), default=False)
    is_active = models.BooleanField(_('active · সক্রিয়'), default=True)

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('form template · ফরম টেমপ্লেট')
        verbose_name_plural = _('form templates · ফরম টেমপ্লেট')
        ordering = ['branch', 'form_type', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['branch', 'form_type', 'name'],
                name='formtemplate_unique_name_per_type',
            ),
            # At most one default per type per institution. A second default
            # makes "print the admission form" ambiguous, and whichever one the
            # ordering happens to return is the one that gets printed in bulk.
            models.UniqueConstraint(
                fields=['branch', 'form_type'],
                condition=models.Q(is_default=True),
                name='formtemplate_one_default_per_type',
            ),
        ]

    def __str__(self):
        return f'{self.name} ({self.form_type})'

    def save(self, *args, **kwargs):
        # Validated here and not only in the serializer: a management command, a
        # seeding function and the Django admin all write templates, and a
        # renderer that meets a malformed block prints a page with a section
        # silently missing (§6.1).
        validate_blocks(self.blocks or [])
        return super().save(*args, **kwargs)


class Question(BranchScopedModel):
    """The form's variable part — what an institution asks beyond the fixed
    identity fields (§5)."""

    # Null means reusable across every template of this institution, which is
    # the common case: the three standard questions appear on the admission form
    # and again on a transfer form. CASCADE would be wrong for the same reason —
    # deleting a template must not delete a question another one still asks.
    template = models.ForeignKey(
        FormTemplate, verbose_name=_('template · টেমপ্লেট'),
        null=True, blank=True, on_delete=models.SET_NULL, related_name='questions',
    )

    # Groups questions into one `question_set` block. A plain string, not a FK:
    # sections are a printing concern with no identity of their own, and a
    # section table would be three rows an admin has to maintain to add a
    # question.
    section = models.CharField(_('section · অংশ'), max_length=60, default='general')

    text = models.CharField(_('question'), max_length=300)
    text_bn = models.CharField(_('প্রশ্ন'), max_length=300, blank=True)

    type = models.CharField(
        _('type · ধরন'), max_length=20,
        choices=QuestionType.choices, default=QuestionType.SHORT_TEXT,
    )
    options = models.JSONField(
        _('options · বিকল্প'), default=list, blank=True,
        help_text=_('[{value, label, label_bn}] — required for the choice types.'),
    )

    is_required = models.BooleanField(_('required · আবশ্যক'), default=False)
    print_style = models.CharField(
        _('print style · ছাপার ধরন'), max_length=20,
        choices=PrintStyle.choices, default=PrintStyle.INLINE,
    )
    answer_lines = models.PositiveSmallIntegerField(
        _('answer lines · উত্তরের লাইন'), default=1,
    )

    # §5.2 — the anti-duplication rule. A question whose answer is really a
    # student field writes that field and stores NO answer. Without this,
    # "previous institution" ends up in both Student and AdmissionAnswer, they
    # disagree within a month, and no report can be trusted.
    maps_to = models.CharField(
        _('maps to · যে ফিল্ডে যায়'), max_length=40, blank=True,
        help_text=_('A student field this answer writes instead of being stored.'),
    )

    order = models.PositiveIntegerField(_('order · ক্রম'), default=0)
    is_active = models.BooleanField(_('active · সক্রিয়'), default=True)

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('question · প্রশ্ন')
        verbose_name_plural = _('questions · প্রশ্নসমূহ')
        ordering = ['branch', 'section', 'order', 'id']
        indexes = [
            models.Index(fields=['branch', 'section', 'order'],
                         name='question_section_order_idx'),
        ]

    def __str__(self):
        return self.text_bn or self.text

    @property
    def stores_an_answer(self):
        """False for a mapped question. **The rule, in one place.**

        Everything that writes or reads answers goes through this rather than
        re-testing `maps_to`, so "a question either maps to a field or stores an
        answer — never both" cannot be half-implemented in one code path.
        """
        return not self.maps_to

    def save(self, *args, **kwargs):
        from django.core.exceptions import ValidationError

        if self.maps_to and self.maps_to not in MAPPED_FIELDS:
            raise ValidationError(
                f'maps_to={self.maps_to!r} is not a bindable student field · '
                f'এটি শিক্ষার্থীর কোনো ফিল্ড নয়। '
                f'Allowed: {", ".join(sorted(MAPPED_FIELDS))}'
            )
        if self.type in CHOICE_TYPES and not self.options:
            raise ValidationError(
                'A choice question needs options · বাছাইয়ের প্রশ্নে বিকল্প দিতে হবে।'
            )
        return super().save(*args, **kwargs)


class AdmissionAnswer(BranchScopedModel):
    """One applicant's answer to one question.

    Only for questions **without** `maps_to` (§5.2). A mapped question's answer
    lives on the student record and nowhere else.
    """

    # CASCADE from the admission: an answer is part of that application and
    # means nothing without it. The question is PROTECTed instead — deleting a
    # question that has been answered would erase what an applicant wrote, so it
    # is deactivated (`is_active`), not deleted.
    admission = models.ForeignKey(
        'students.Admission', verbose_name=_('admission · ভর্তির আবেদন'),
        on_delete=models.CASCADE, related_name='form_answers',
    )
    question = models.ForeignKey(
        Question, verbose_name=_('question · প্রশ্ন'),
        on_delete=models.PROTECT, related_name='answers',
    )

    # JSON so one column serves every type: `"খারিজি"` for text,
    # `["quran", "hadith"]` for multi-choice, `true` for yes/no. A per-type
    # column set would be six mostly-null columns and a CASE in every read.
    value = models.JSONField(_('answer · উত্তর'), null=True, blank=True)
    answered_at = models.DateTimeField(_('answered at · উত্তরের সময়'), auto_now=True)

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('admission answer · আবেদনের উত্তর')
        verbose_name_plural = _('admission answers · আবেদনের উত্তরসমূহ')
        ordering = ['branch', 'admission', 'question']
        constraints = [
            # One answer per question per application. Two rows would make the
            # printed form and the data-entry screen disagree about what was
            # answered, with no way to tell which is the later one.
            models.UniqueConstraint(
                fields=['admission', 'question'],
                name='admissionanswer_unique_per_question',
            ),
        ]

    def __str__(self):
        return f'{self.admission_id}/{self.question_id}'


class PrintedForm(BranchScopedModel):
    """A form that was actually printed, and exactly what it said (§6)."""

    admission = models.ForeignKey(
        'students.Admission', verbose_name=_('admission · ভর্তির আবেদন'),
        on_delete=models.PROTECT, related_name='printed_forms',
    )
    # PROTECT: the snapshot is what gets reprinted, but the template is the
    # provenance of the document. Deleting it would leave a printed record
    # nobody can say the origin of.
    template = models.ForeignKey(
        FormTemplate, verbose_name=_('template · টেমপ্লেট'),
        on_delete=models.PROTECT, related_name='printed_forms',
    )

    # Its own per-branch gapless sequence, separate from the admission number:
    # the reference form prints both (ফরম নং and ভর্তি নং) because forms are
    # issued before admission numbers exist (§6). Issued through
    # `core.services.next_number` under a row lock — never `max() + 1`, which
    # double-issues the moment two clerks hand out forms in the same second, and
    # an admission season is exactly that situation.
    form_no = models.CharField(_('form no · ফরম নং'), max_length=40)

    # **The important field.** The fully resolved form as it stood at print
    # time — every placeholder value, every answer, and the block list itself.
    # A form reprinted in three years must show what was signed, not what the
    # record says today after a name correction.
    snapshot = models.JSONField(_('snapshot · সংরক্ষিত অনুলিপি'), default=dict)

    printed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_('printed by · মুদ্রণকারী'),
        null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    printed_at = models.DateTimeField(_('printed at · মুদ্রণের সময়'))
    reprint_count = models.PositiveIntegerField(_('reprints · পুনর্মুদ্রণ'), default=0)

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('printed form · মুদ্রিত ফরম')
        verbose_name_plural = _('printed forms · মুদ্রিত ফরম')
        ordering = ['branch', '-printed_at']
        constraints = [
            # The form number is written on a slip an applicant walks away with;
            # two of them held by two people is unrecoverable at the counter.
            models.UniqueConstraint(
                fields=['branch', 'form_no'],
                name='printedform_unique_form_no',
            ),
        ]
        indexes = [
            models.Index(fields=['branch', 'admission'],
                         name='printedform_admission_idx'),
        ]

    def __str__(self):
        return self.form_no
