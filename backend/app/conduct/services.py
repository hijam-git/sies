"""The sheet, and saving it (CLAUDE.md §4.3).

Everything that decides anything is here: which template a class uses, what a
period string means for a given frequency, which students are on the sheet, and
what a save does with the cells it was handed. `views.py` resolves ids and calls
one function.

The shape is `attendance.services` on purpose. It is the same act — a teacher
in front of a class, recording one small thing per student — so it gets the
same properties:

* **one transaction** for the whole grid, because half a class saved is worse
  than none saved and nobody can tell which half;
* **idempotent**, on the sheet's own unique key, so the same payload twice
  writes the same rows and two teachers on two phones produce one sheet;
* **server-authoritative** — a student who is not in this class is skipped with
  a reason, however the client was persuaded to send them.
"""

import logging
from datetime import date as date_cls

from django.db import transaction
from django.utils import timezone

from academics.models import Enrolment

from forms.models import Question, QuestionType

from .models import (ReportAnswer, ReportFrequency, ReportStatus,
                     ReportTemplate, StudentReport)

logger = logging.getLogger(__name__)

REASON_NOT_ENROLLED = 'not_enrolled'
REASON_UNKNOWN_ITEM = 'unknown_item'


# ─────────────────────────────────────────────────────────────────────────────
# Periods
# ─────────────────────────────────────────────────────────────────────────────

def period_for(frequency, on_date=None) -> str:
    """The period string this frequency uses for a date.

    `2026-09-23` daily, `2026-W39` weekly, `2026-09` monthly, `2026-T1` per
    term. One string, because nothing ever needs to ask "which week" without
    first knowing the frequency it belongs to — and four nullable columns would
    be four ways for them to disagree.
    """
    on_date = on_date or timezone.localdate()
    if frequency == ReportFrequency.DAILY:
        return on_date.isoformat()
    if frequency == ReportFrequency.WEEKLY:
        year, week, _day = on_date.isocalendar()
        return f'{year}-W{week:02d}'
    if frequency == ReportFrequency.MONTHLY:
        return f'{on_date.year:04d}-{on_date.month:02d}'
    # Three terms, by the Bangladeshi academic year: Jan–Apr, May–Aug, Sep–Dec.
    term = (on_date.month - 1) // 4 + 1
    return f'{on_date.year:04d}-T{term}'


def parse_period(frequency, raw) -> str:
    """Accept a period as sent, or turn a plain date into one.

    The screen sends `?date=2026-09-23` and lets the server decide what that
    means for a monthly template — the alternative is every caller
    reimplementing `period_for`, and getting the ISO week wrong in January.
    """
    raw = (raw or '').strip()
    if not raw:
        return period_for(frequency)
    try:
        return period_for(frequency, date_cls.fromisoformat(raw))
    except ValueError:
        return raw


# ─────────────────────────────────────────────────────────────────────────────
# Which template
# ─────────────────────────────────────────────────────────────────────────────

def templates_for(branch, academic_class=None):
    """The active templates this class is observed with, most specific first.

    A template for THIS class beats one for its বিভাগ, which beats one for the
    whole institution. The order is what lets the screen open on the right one
    without asking (CLAUDE.md §7b).
    """
    templates = (ReportTemplate.objects
                 .for_branch(branch)
                 .filter(is_active=True)
                 .select_related('stream', 'academic_class'))
    if academic_class is None:
        return list(templates)

    fitting = [t for t in templates if t.applies_to(academic_class)]
    fitting.sort(key=lambda t: (0 if t.academic_class_id else 1 if t.stream_id else 2,
                                t.name))
    return fitting


def template_questions(template):
    """The sheet's questions, in the order they are asked.

    **Explicitly chosen questions win; otherwise the whole section.** The same
    shape as every default on the SPA (§7b) — an explicit choice beats the
    obvious one — and it is what lets two templates drawing on one bank ask
    different lists. A daily sheet of three questions and a monthly review of
    twelve can share নামাজ without a second copy of it drifting out of step.

    `forms.Question` is the bank and Settings → Questions is its editor: there
    is no second place to write a question, and none of this code knows what
    any of them say.
    """
    chosen = list(
        Question.objects
        .filter(report_links__template=template, is_active=True)
        .order_by('report_links__order', 'report_links__id')
    )
    if chosen:
        return chosen

    return list(
        Question.objects
        .for_branch(template.branch)
        .filter(section=template.section, is_active=True)
        .order_by('order', 'id')
    )


def set_template_questions(template, question_ids):
    """Replace what a template asks, in the order given. Returns the count.

    A replace rather than add/remove calls: the setup screen holds the whole
    list, and two half-applied requests are how an ordering ends up with two
    questions claiming position three.

    A question from another institution is dropped rather than refused — the
    branch-scoped queryset simply never returns it, which is the same 404-shaped
    answer the rest of the API gives (CLAUDE.md §5).
    """
    from .models import ReportTemplateQuestion

    with transaction.atomic():
        allowed = {
            question.pk: question
            for question in Question.objects.for_branch(template.branch)
            .filter(pk__in=list(question_ids or []))
        }
        ReportTemplateQuestion.objects.filter(template=template).delete()
        ReportTemplateQuestion.objects.bulk_create([
            ReportTemplateQuestion(branch=template.branch, template=template,
                                   question=allowed[pk], order=(index + 1) * 10)
            for index, pk in enumerate(question_ids or [])
            if pk in allowed
        ])
    return ReportTemplateQuestion.objects.filter(template=template).count()


def responsible_teachers(template, academic_class, section=None):
    """Who is responsible for this sheet — and it is a list, not one person.

    A whole-class assignment covers every শাখা, so a section's sheet may have
    both its own teacher and the class's. Responsibility here directs and
    chases; it does not fence anybody out (see `ReportAssignment`).
    """
    from django.db.models import Q

    from .models import ReportAssignment

    query = Q(section__isnull=True)
    if section is not None:
        query |= Q(section=section)

    return list(
        ReportAssignment.objects
        .filter(query, template=template, academic_class=academic_class)
        .select_related('teacher', 'section')
    )


def assignments_for(teacher, *, branch=None):
    """Every sheet this teacher is responsible for — their own to-do list."""
    from .models import ReportAssignment

    rows = (ReportAssignment.objects
            .filter(teacher=teacher)
            .select_related('template', 'academic_class', 'section'))
    if branch is not None:
        rows = rows.filter(branch=branch)
    return list(rows)


def sheet_enrolments(branch, academic_class, section=None):
    """The students on the sheet, in roll order — the register's own rule."""
    enrolments = (Enrolment.objects
                  .for_branch(branch)
                  .filter(academic_class=academic_class, is_active=True)
                  .select_related('student', 'section'))
    if section is not None:
        enrolments = enrolments.filter(section=section)
    return list(enrolments.order_by('roll', 'id'))


# ─────────────────────────────────────────────────────────────────────────────
# Reading the sheet
# ─────────────────────────────────────────────────────────────────────────────

def sheet(template, *, academic_class, section=None, period=None, on_date=None):
    """Everything the grid draws: the items, the students, and what is filled.

    One query for the reports and one for the answers, then the assembly in
    Python — a query per student is forty round trips for a screen a teacher
    opens every morning.
    """
    branch = template.branch
    period = period or period_for(template.frequency, on_date)
    items = template_questions(template)
    enrolments = sheet_enrolments(branch, academic_class, section)

    reports = {
        report.enrolment_id: report
        for report in StudentReport.objects
        .filter(branch=branch, template=template, period=period,
                enrolment__in=[e.pk for e in enrolments])
        .select_related('filled_by')
    }
    answers = {}
    for answer in ReportAnswer.objects.filter(report__in=list(reports.values())):
        answers.setdefault(answer.report_id, {})[answer.item_id] = answer.value

    students = []
    for enrolment in enrolments:
        report = reports.get(enrolment.pk)
        students.append({
            'enrolment': enrolment.pk,
            'student': enrolment.student_id,
            'name': enrolment.student.name,
            'name_bn': enrolment.student.name_bn,
            'roll': enrolment.roll,
            'section': enrolment.section_id,
            'filled': report is not None,
            'filled_by': report.filled_by_id if report else None,
            'filled_by_name': (report.filled_by.name
                               if report and report.filled_by else ''),
            'remarks': report.remarks if report else '',
            'answers': {str(item_id): value
                        for item_id, value in answers.get(report.pk, {}).items()}
            if report else {},
        })

    return {
        'template': template.pk,
        'template_name': template.name_bn or template.name,
        'frequency': template.frequency,
        'period': period,
        'academic_class': academic_class.pk,
        # TWO different sections, and they were both called `section` — a
        # duplicate key, so Python kept the last one and the class-section id
        # the caller asked for was silently dropped from every response.
        'section': getattr(section, 'pk', None),      # the CLASS section, echoed back
        'question_section': template.section,          # the question-bank slice
        # Who is meant to fill this, so the screen can say so — and so a sheet
        # nobody filled has a name against it rather than an accusation at the
        # whole staff room.
        'responsible': [
            {'teacher': row.teacher_id,
             'name': row.teacher.name_bn or row.teacher.name,
             'section': row.section_id}
            for row in responsible_teachers(template, academic_class, section)
        ],
        'items': [
            {
                'id': item.pk, 'text': item.text, 'text_bn': item.text_bn,
                'type': item.type, 'options': item.options,
                'is_required': item.is_required, 'order': item.order,
            }
            for item in items
        ],
        'students': students,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Saving it
# ─────────────────────────────────────────────────────────────────────────────

def _options(question):
    """A question's choices as plain strings, whichever shape they are stored in.

    `forms.Question.options` accepts `["ভালো", …]` and
    `[{"value": …, "label": …}]`; the sheet stores the value.
    """
    values = []
    for option in (question.options or []):
        if isinstance(option, dict):
            value = option.get('value', option.get('label'))
        else:
            value = option
        if value is not None and str(value).strip():
            values.append(str(value).strip())
    return values


def clean_value(item, value):
    """The answer, as its question says it should be. Never raises.

    A refusal here would fail a whole class's save over one stray cell, so a
    value that cannot be read becomes None — an unanswered question, which is
    a state the sheet already has and the teacher can see.
    """
    if value is None or value == '':
        return None
    if item.type == QuestionType.YES_NO:
        return bool(value)
    if item.type == QuestionType.SINGLE_CHOICE:
        allowed = _options(item)
        return str(value) if str(value) in allowed else None
    if item.type == QuestionType.MULTI_CHOICE:
        allowed = set(_options(item))
        chosen = value if isinstance(value, (list, tuple)) else [value]
        return [str(v) for v in chosen if str(v) in allowed] or None
    if item.type == QuestionType.NUMBER:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    # DATE, SHORT_TEXT, DESCRIPTION — text, bounded so one paste cannot become
    # the whole row.
    return str(value)[:200]


@transaction.atomic
def save_sheet(*, template, academic_class, rows, section=None, period=None,
               on_date=None, teacher=None, actor=None):
    """Write the grid. One transaction, idempotent, server-authoritative.

    `rows` is `[{'enrolment': 12, 'answers': {'<item id>': value}, 'remarks': ''}]`.

    Returns `{'saved': n, 'skipped': [...]}`. A student who is not in this class
    is skipped with a reason rather than written: the register decides who is on
    the sheet, not the payload.
    """
    branch = template.branch
    period = period or period_for(template.frequency, on_date)
    now = timezone.now()

    allowed = {e.pk: e for e in sheet_enrolments(branch, academic_class, section)}
    items = {question.pk: question for question in template_questions(template)}

    saved, skipped = 0, []
    for row in rows:
        enrolment = allowed.get(row.get('enrolment'))
        if enrolment is None:
            skipped.append({'enrolment': row.get('enrolment'),
                            'reason': REASON_NOT_ENROLLED})
            continue

        report, _created = StudentReport.objects.update_or_create(
            branch=branch, template=template, enrolment=enrolment, period=period,
            defaults={
                'student_id': enrolment.student_id,
                'status': ReportStatus.SUBMITTED,
                'remarks': (row.get('remarks') or '')[:200],
                # Overwritten on every save: a correction replaces who filled it
                # and when, which is docs/08 D3's rule for the register applied
                # to the same kind of record.
                'filled_by': teacher,
                'filled_at': now,
                'updated_by': actor,
            },
        )

        for raw_item, value in (row.get('answers') or {}).items():
            try:
                item = items[int(raw_item)]
            except (KeyError, TypeError, ValueError):
                skipped.append({'enrolment': enrolment.pk, 'item': raw_item,
                                'reason': REASON_UNKNOWN_ITEM})
                continue
            ReportAnswer.objects.update_or_create(
                branch=branch, report=report, item=item,
                defaults={'value': clean_value(item, value), 'updated_by': actor},
            )
        saved += 1

    logger.info('Conduct sheet saved: template=%s period=%s saved=%d skipped=%d',
                template.pk, period, saved, len(skipped))
    return {'saved': saved, 'skipped': skipped, 'period': period}


def student_history(student, *, template=None, limit=30):
    """One student's sheets, newest first — what a guardian is shown."""
    reports = (StudentReport.objects
               .filter(student=student)
               .select_related('template', 'filled_by')
               .prefetch_related('answers__item')
               .order_by('-period'))
    if template is not None:
        reports = reports.filter(template=template)

    return [
        {
            'period': report.period,
            'template': report.template_id,
            'template_name': report.template.name_bn or report.template.name,
            'filled_by_name': report.filled_by.name if report.filled_by else '',
            'remarks': report.remarks,
            'answers': [
                {'item': answer.item_id,
                 'text': answer.item.text_bn or answer.item.text,
                 'type': answer.item.type,
                 'value': answer.value}
                for answer in report.answers.all()
            ],
        }
        for report in reports[:limit]
    ]
