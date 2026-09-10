"""Form operations that span more than one table (CLAUDE.md §4.3).

Three of them, and each carries a rule from docs/07 that nothing else may
restate:

* **`save_answers()`** — §5.2. A question either maps to a student field or
  stores an answer, **never both**. Without that rule "previous institution"
  ends up in `Student` *and* in `AdmissionAnswer`, the two disagree within a
  month, and no report built on either can be trusted.
* **`print_form()`** — §6. Issues the form number under a row lock and stores
  the fully resolved `snapshot`, so a reprint in three years shows what was
  signed rather than what the record says today.
* **`seed_form_templates()`** lives in `seeding.py` next door, for the same
  reason branch seeding does: it is data, and it is called from
  `branches.services.create_branch()`, never from a signal.
"""

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from accounts.models import ActivityAction
from accounts.services import log_activity
from core.services import format_number, next_number

from .models import AdmissionAnswer, FormTemplate, PrintedForm, Question
from .placeholders import build_context
from .renderer import question_payload, render_document, render_form

#: The counter kind for form numbers. A string literal rather than a
#: `NumberSequence.Kind` member because adding one is a migration on `core`,
#: which this app may not write. `core.NumberSequence.Kind` should gain
#: `FORM = 'form'` when core is next touched — the column is a plain CharField
#: and its choices are not enforced by the database, so the counter is correct
#: either way; what is missing is the label in the admin.
FORM_NUMBER_KIND = 'form'
FORM_NUMBER_PREFIX = 'FRM'


def allocate_form_no(branch):
    """`FRM-DHK-00041` — gapless, per branch, for the life of the institution.

    Its own sequence, separate from the admission number, because the reference
    form prints both: forms are handed out *before* an admission number exists
    (§6). Reserved through `core.services.next_number`, which takes the row lock
    — never `max() + 1`, which double-issues the moment two clerks hand out
    forms in the same second, and admission season is exactly that situation.

    Must be called inside the caller's transaction, and `print_form()` is.
    """
    _number, padded = next_number(branch=branch, kind=FORM_NUMBER_KIND, width=5)
    return format_number(prefix=FORM_NUMBER_PREFIX, branch=branch, number_padded=padded)


def default_template(branch, form_type='admission'):
    """The institution's default template of this type, or its first active one."""
    templates = FormTemplate.objects.filter(
        branch=branch, form_type=form_type, is_active=True,
    )
    return templates.filter(is_default=True).first() or templates.first()


def form_questions(branch, template=None):
    """The questions this template prints.

    A question with `template=None` is reusable across every template of the
    institution (the common case — the three standard questions appear on the
    admission form and again on a transfer form), so both are returned.
    """
    questions = Question.objects.filter(branch=branch, is_active=True)
    if template is not None:
        questions = questions.filter(template__in=[None, template.pk])
    else:
        questions = questions.filter(template__isnull=True)
    return list(questions.order_by('section', 'order', 'id'))


def answer_map(admission):
    """`{'<question id>': value}` — only questions that store an answer.

    Keyed by string because it goes into `snapshot`, and JSON has no integer
    keys; a dict that changed shape on the way to storage would make the reprint
    path differ from the print path.
    """
    return {
        str(answer.question_id): answer.value
        for answer in AdmissionAnswer.objects.filter(admission=admission)
    }


# ─────────────────────────────────────────────────────────────────────────────
# Answers — §5.2
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def save_answers(*, admission, answers, actor=None, request=None):
    """Save one applicant's answers. Returns `{'stored': n, 'mapped': n}`.

    *answers* is `{question_id: value}`.

    **A mapped question writes the student field and stores no answer.** The
    field is written on the `Student` when the application has been admitted and
    on the `Admission` otherwise — which is not a compromise but the same rule
    applied twice: the answer belongs on whichever row is the record of that
    person right now, and before admission the application *is* the record
    (docs/02 §4.1 — most applications never become a Student).

    Any stray `AdmissionAnswer` for a question that has since gained a `maps_to`
    is deleted here. That is the migration path for changing a question's
    binding, and doing it silently at write time is correct: leaving the row
    behind would recreate exactly the duplication §5.2 exists to prevent.
    """
    questions = {
        question.pk: question
        for question in Question.objects.filter(
            branch_id=admission.branch_id, pk__in=list(answers),
        )
    }

    unknown = set(answers) - set(questions)
    if unknown:
        raise ValidationError({
            'answers': f'No question {sorted(unknown)} in this institution · '
                       f'এই প্রতিষ্ঠানে এমন প্রশ্ন নেই।',
        })

    student = admission.student
    target = student or admission
    stored = mapped = 0
    changed_fields = []

    for question_id, value in answers.items():
        question = questions[question_id]

        if question.stores_an_answer:
            AdmissionAnswer.objects.update_or_create(
                admission=admission, question=question,
                defaults={'branch_id': admission.branch_id, 'value': value,
                          'updated_by': actor},
            )
            stored += 1
            continue

        # A mapped question. The field, and nothing else.
        AdmissionAnswer.objects.filter(admission=admission, question=question).delete()
        if hasattr(target, question.maps_to):
            setattr(target, question.maps_to, _field_value(value))
            changed_fields.append(question.maps_to)
            mapped += 1

    if changed_fields:
        target.updated_by = actor
        target.save(update_fields=[*set(changed_fields), 'updated_by', 'updated_at'])

    result = {'stored': stored, 'mapped': mapped}
    log_activity(
        action=ActivityAction.UPDATE, user=actor, request=request,
        branch=admission.branch, obj=admission, model='AdmissionAnswer',
        summary=f'Saved admission form answers ({result})',
        summary_bn='ভর্তি ফরমের উত্তর সংরক্ষণ করা হয়েছে',
        after=result, atomic=False,
    )
    return result


def _field_value(value):
    """A JSON answer as something a Char/Date/Bool field will take."""
    if value is None:
        return ''
    if isinstance(value, bool):
        return value
    if isinstance(value, list):
        return ', '.join(str(item) for item in value)
    return value


# ─────────────────────────────────────────────────────────────────────────────
# Printing — §6, §7
# ─────────────────────────────────────────────────────────────────────────────

def build_snapshot(*, admission, template, printed_form=None, mode='filled'):
    """Everything `render_document()` needs, as plain JSON.

    The snapshot is the argument list, not a rendered string. Storing the HTML
    would freeze this release's CSS into a row and make a 2029 reprint look like
    2026's stylesheet bug; storing the arguments keeps the *content* fixed —
    which is what was signed — while the presentation stays current.
    """
    questions = form_questions(admission.branch, template)
    context = ({} if mode == 'blank'
               else build_context(branch=admission.branch, admission=admission,
                                  printed_form=printed_form))
    return {
        'blocks': template.blocks or [],
        'context': context,
        'questions': [question_payload(question) for question in questions],
        'answers': {} if mode == 'blank' else answer_map(admission),
        'paper': template.paper,
        'margins': template.margins,
        'title': template.name_bn or template.name,
    }


@transaction.atomic
def print_form(*, admission, template=None, mode='filled', actor=None, request=None):
    """Render an admission form and, in filled mode, record that it was printed.

    Returns `(html, printed_form)`; `printed_form` is None for a blank.

    **Blank mode records nothing and issues no form number**, and that is the
    right asymmetry. A blank is one sheet off a stack of two hundred printed
    before anybody applied; its ফরম নং is written on by hand at the counter, and
    burning a gapless sequence number per sheet of paper would make the numbered
    series meaningless as a record of applications received.
    """
    template = template or default_template(admission.branch)
    if template is None:
        raise ValidationError({
            'template': 'This institution has no admission form template · '
                        'এই প্রতিষ্ঠানের কোনো ভর্তি ফরম টেমপ্লেট নেই।',
        })
    if template.branch_id != admission.branch_id:
        raise ValidationError({'template': 'That template belongs to another institution.'})

    if mode == 'blank':
        snapshot = build_snapshot(admission=admission, template=template, mode='blank')
        return render_document(**snapshot), None

    now = timezone.now()
    printed = PrintedForm(
        branch_id=admission.branch_id, admission=admission, template=template,
        # Reserved inside this transaction, so the number and the row it belongs
        # to succeed or fail together — a reserved number whose row was never
        # written is precisely the gap the sequence must not have.
        form_no=allocate_form_no(admission.branch),
        printed_by=actor, printed_at=now, created_by=actor, updated_by=actor,
    )
    printed.snapshot = build_snapshot(
        admission=admission, template=template, printed_form=printed, mode='filled',
    )
    printed.save()

    log_activity(
        action=ActivityAction.CREATE, user=actor, request=request,
        branch=admission.branch, obj=printed, model='PrintedForm',
        summary=f'Printed admission form {printed.form_no}',
        summary_bn=f'ভর্তি ফরম {printed.form_no} মুদ্রণ করা হয়েছে',
        after={'form_no': printed.form_no}, atomic=False,
    )
    return render_document(**printed.snapshot), printed


@transaction.atomic
def reprint(printed_form, *, actor=None, request=None):
    """Re-render a printed form **from its snapshot**.

    Not from the record. A student whose name was corrected last year still has
    a signed form on file with the old spelling, and the reprint has to match
    the paper in the file — otherwise the reprint is a different document
    wearing the same form number.
    """
    printed_form.reprint_count += 1
    printed_form.updated_by = actor
    printed_form.save(update_fields=['reprint_count', 'updated_by', 'updated_at'])

    log_activity(
        action=ActivityAction.UPDATE, user=actor, request=request, branch=printed_form.branch, obj=printed_form,
        model='PrintedForm',
        summary=f'Reprinted form {printed_form.form_no} '
                f'(#{printed_form.reprint_count})',
        summary_bn=f'ফরম {printed_form.form_no} পুনর্মুদ্রণ',
        atomic=False,
    )
    return render_document(**printed_form.snapshot)


def preview_template(template, *, mode='blank'):
    """Render a template with no admission behind it — the editor's preview."""
    return render_form(
        template=template,
        questions=form_questions(template.branch, template),
        mode=mode,
    )
