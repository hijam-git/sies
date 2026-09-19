"""Exam operations that span more than one table (CLAUDE.md §4.3).

Four things live here, and each is a rule the API is not allowed to restate:

* **`save_marks()`** — the entry grid, saved in bulk in one transaction. Same
  shape as the attendance register: the screen sends the whole grid, the service
  upserts it, and sending it twice changes nothing.
* **`assert_can_enter_marks()`** — docs/08 D6's second gate, at *subject*
  granularity. A teacher enters marks for the subjects they hold a
  `SubjectAssignment` for; being class teacher of Class 5 is not a licence to
  enter its mathematics marks.
* **`publish_exam()`** — principal-only, gated on `exams.publish` and never on
  `marks.enter`. Publishing is the moment results become visible; entering marks
  is not.
* **`student_result()` / `tabulation()`** — totals, grades and ranks through
  the বিভাগ's `GradeScale` (`grading.py`) while an exam is open, and read back
  from the `Result` rows `publish_exam()` froze once it is published.

Every arithmetic value here is a `Decimal`. `float` is banned project-wide and
the reason applies with full force to a marksheet: 0.1 + 0.2 is not 0.3 in
binary floating point, and a column that does not add up to its own total is the
one thing a guardian checks by hand.
"""

import json
from decimal import Decimal

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from academics.models import AcademicClass, Enrolment
from academics.services import (teacher_for_user, teacher_scope_applies,
                                teacher_subject_scope)
from accounts.permissions import has_permission
from accounts.services import log_activity
from accounts.models import ActivityAction

from .grading import evaluate, rank_key, scale_for
from .models import Exam, ExamSchedule, ExamStatus, Mark, Result

ZERO = Decimal('0.00')

# ─────────────────────────────────────────────────────────────────────────────
# The second gate — docs/08 D6, at subject granularity
# ─────────────────────────────────────────────────────────────────────────────

def can_enter_marks(user, *, subject, session=None):
    """Whether *user* may enter marks for *subject*.

    Non-teachers — principal, accountant, platform admin, superuser — are not
    narrowed here at all: their gate is the `marks.enter` permission, and D6's
    class/subject scope exists to stop a *teacher* reaching a colleague's
    subject, not to stop the office doing its job.

    A teacher is allowed exactly the subjects they hold an active
    `SubjectAssignment` for. Class responsibility does **not** count: it is what
    lets them see the roster and take daily attendance (D6's action table), and
    reusing it here would mean a class teacher could rewrite every subject's
    marks for their class — including the ones another teacher taught and
    entered.
    """
    branch = getattr(subject, 'branch', None)
    if not teacher_scope_applies(user, branch):
        return True
    teacher = teacher_for_user(user)
    return subject.pk in teacher_subject_scope(teacher, session=session)


def assert_can_enter_marks(user, *, subject, session=None):
    """`can_enter_marks`, as a 403 with a sentence the teacher can act on.

    A refusal here is deliberately **403 and not 404**, which is the opposite of
    the branch rule (CLAUDE.md §5) and for the opposite reason: the subject is
    not hidden from this teacher — it is on the routine they read every morning
    — so pretending it does not exist would only send them to the office to
    report a missing subject. What they need to be told is *whose* it is.
    """
    if not can_enter_marks(user, subject=subject, session=session):
        raise PermissionDenied(
            'You are not assigned to this subject, so you cannot enter its '
            'marks · এই বিষয়ে আপনি নিযুক্ত নন, তাই নম্বর দিতে পারবেন না।'
        )


# ─────────────────────────────────────────────────────────────────────────────
# Marks entry
# ─────────────────────────────────────────────────────────────────────────────

def _as_decimal(value, field):
    if value is None or value == '':
        return None
    try:
        return Decimal(str(value))
    except (ArithmeticError, ValueError):
        raise ValidationError({field: f'{value!r} is not a number · সংখ্যা নয়।'})


@transaction.atomic
def save_marks(*, exam, subject, rows, actor=None, request=None):
    """Upsert the whole marks grid for one paper, in one transaction.

    *rows* is what the entry screen holds — one entry per student:

        [{'enrolment': 12, 'obtained': '78.50', 'practical_obtained': None,
          'is_absent': False}, …]

    Returns `{'created': n, 'updated': n, 'unchanged': n}`.

    **Idempotent by construction.** The grid is keyed on
    `(exam, student, subject)`, which is the table's unique constraint, so
    re-saving an unchanged grid writes nothing and re-saving a corrected one
    overwrites the cell. That matters because a teacher on a phone taps Save
    twice on a slow connection more often than they type a wrong number, and the
    alternative — append rows and let the tabulation sum both — is silent and
    doubles a student's total.

    One transaction for the same reason the attendance register has one: a grid
    half-saved is worse than one not saved, because it looks finished.

    `enrolment` rather than `student` is the caller's key. The enrolment names
    *which class the student sat this in*, and a student who repeated a year has
    two of them; the student id alone cannot say which year's mark this is.
    """
    if exam.status == ExamStatus.PUBLISHED:
        # Editing a published exam changes a result that has already been read
        # out and printed. Unpublishing is a deliberate act with its own audit
        # trail; a marks POST is not it.
        raise ValidationError({
            'exam': 'This exam is published; unpublish it before editing marks · '
                    'ফল প্রকাশিত পরীক্ষার নম্বর সংশোধনের আগে প্রকাশ বাতিল করুন।',
        })

    if subject.branch_id != exam.branch_id:
        raise ValidationError({'subject': 'That subject belongs to another institution.'})

    assert_can_enter_marks(actor, subject=subject, session=exam.session)

    enrolment_ids = [row.get('enrolment') for row in rows]
    enrolments = {
        enrolment.pk: enrolment
        for enrolment in Enrolment.objects.filter(
            pk__in=[e for e in enrolment_ids if e], branch_id=exam.branch_id,
        ).select_related('student')
    }

    existing = {
        mark.student_id: mark
        for mark in Mark.objects.select_for_update().filter(
            exam=exam, subject=subject,
        )
    }

    now = timezone.now()
    created = updated = unchanged = 0
    to_create = []

    for row in rows:
        enrolment = enrolments.get(row.get('enrolment'))
        if enrolment is None:
            raise ValidationError({
                'enrolment': f'No enrolment {row.get("enrolment")!r} in this institution.',
            })

        is_absent = bool(row.get('is_absent'))
        # Absent wins over any number that came with it. The check constraint
        # would refuse the contradictory row anyway; normalising here means the
        # teacher who ticked Absent over a typed 0 gets what they meant rather
        # than a database error they cannot read.
        obtained = None if is_absent else _as_decimal(row.get('obtained'), 'obtained')
        practical = None if is_absent else _as_decimal(
            row.get('practical_obtained'), 'practical_obtained',
        )

        mark = existing.get(enrolment.student_id)
        if mark is None:
            to_create.append(Mark(
                branch_id=exam.branch_id, exam=exam, subject=subject,
                student_id=enrolment.student_id, enrolment=enrolment,
                obtained=obtained, practical_obtained=practical,
                is_absent=is_absent, entered_by=actor, entered_at=now,
                created_by=actor, updated_by=actor,
            ))
            created += 1
            continue

        if (mark.obtained == obtained and mark.practical_obtained == practical
                and mark.is_absent == is_absent and mark.is_active):
            unchanged += 1
            continue

        mark.obtained = obtained
        mark.practical_obtained = practical
        mark.is_absent = is_absent
        mark.enrolment = enrolment
        mark.is_active = True
        mark.entered_by = actor
        mark.entered_at = now
        mark.updated_by = actor
        mark.save(update_fields=[
            'obtained', 'practical_obtained', 'is_absent', 'enrolment',
            'is_active', 'entered_by', 'entered_at', 'updated_by', 'updated_at',
        ])
        updated += 1

    if to_create:
        Mark.objects.bulk_create(to_create)

    result = {'created': created, 'updated': updated, 'unchanged': unchanged}

    log_activity(
        action=ActivityAction.UPDATE, user=actor, request=request,
        branch=exam.branch, obj=exam, model='Mark',
        summary=f'Saved marks for {subject.name} in {exam.name} ({result})',
        summary_bn=f'{exam.name} — {subject.name} বিষয়ের নম্বর সংরক্ষণ',
        after=result, atomic=False,
    )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Publishing — the principal's act, not the teacher's
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def publish_exam(exam, *, actor=None, request=None):
    """Flip an exam to PUBLISHED. **Principal-only.**

    Gated on `exams.publish`, which is a separate checkbox from `marks.enter`
    for a reason the permission catalogue states and this function enforces: a
    teacher enters their own subject's marks, and only a principal decides that
    the whole result is ready to be seen. If publishing rode on `marks.enter`,
    the first teacher to finish their subject would release everybody's result,
    including the papers nobody has marked yet.

    Publishing is also the moment marks become visible to students — see
    `visible_marks_for()`. That is why the check is here in the service and not
    only on the viewset: a management command or a Celery task that published
    without asking would bypass a view-layer check entirely.
    """
    if actor is not None and not has_permission(actor, 'exams', 'publish'):
        raise PermissionDenied(
            'Only a principal may publish results · ফল প্রকাশ কেবল প্রধান শিক্ষক করতে পারেন।'
        )

    if exam.status == ExamStatus.PUBLISHED:
        # Idempotent: a double-click must not move `published_at` and make the
        # marksheet claim it was released later than it was.
        return exam

    exam.status = ExamStatus.PUBLISHED
    exam.published_by = actor
    exam.published_at = timezone.now()
    exam.updated_by = actor
    exam.save(update_fields=['status', 'published_by', 'published_at',
                             'updated_by', 'updated_at'])

    # Frozen here, in the transaction that publishes: the marksheet printed
    # today and the one reprinted in three years must show the same grade even
    # if the institution edits its scale in between (docs/06 #12).
    _store_results(exam, actor=actor)

    log_activity(
        action=ActivityAction.PUBLISH, user=actor, request=request,
        branch=exam.branch, obj=exam, model='Exam',
        summary=f'Published results for {exam.name}',
        summary_bn=f'{exam.name} পরীক্ষার ফল প্রকাশ করা হয়েছে',
        after={'status': exam.status}, atomic=True,
    )
    return exam


def unpublish_exam(exam, *, actor=None, request=None):
    """Take a published result back down. **Principal-only**, like publishing.

    This exists because `save_marks` refuses to touch a published exam and tells
    the caller to unpublish first — and there was nothing to call. One digit
    mistyped at publish time was permanent, which is not a rule anybody chose;
    it was a missing verb.

    The frozen `Result` rows go with it. They are the snapshot of *a* published
    sheet, and keeping them behind an unpublished exam would mean the next
    publish silently compared against a sheet nobody could see. Marks themselves
    are untouched: this reopens the result, it does not erase the exam.

    Idempotent, and logged as the release-level act it is.
    """
    if actor is not None and not has_permission(actor, 'exams', 'publish'):
        raise PermissionDenied(
            'Only a principal may unpublish results · '
            'ফল প্রত্যাহার কেবল প্রধান শিক্ষক করতে পারেন।'
        )

    if exam.status != ExamStatus.PUBLISHED:
        return exam

    exam.status = ExamStatus.MARKS_ENTRY
    exam.published_by = None
    exam.published_at = None
    exam.updated_by = actor
    exam.save(update_fields=['status', 'published_by', 'published_at',
                             'updated_by', 'updated_at'])
    Result.objects.filter(exam=exam).delete()

    log_activity(
        action=ActivityAction.UPDATE, user=actor, request=request,
        branch=exam.branch, obj=exam, model='Exam',
        summary=f'Unpublished results for {exam.name}',
        summary_bn=f'{exam.name} পরীক্ষার ফল প্রত্যাহার করা হয়েছে',
        before={'status': ExamStatus.PUBLISHED},
        after={'status': exam.status}, atomic=True,
    )
    return exam


def marks_are_visible_to(exam, user):
    """Whether *user* may see this exam's marks at all.

    **A student sees nothing until the exam is published** (docs/02 §4.7). Marks
    are entered subject by subject over a fortnight; a student reading them as
    they land sees a half-finished result, compares it with a classmate's, and
    the office spends the week explaining arithmetic that is not finished.

    Staff see marks throughout — entering them is the point.
    """
    if getattr(user, 'user_type', None) in ('student', 'guardian'):
        return exam.status == ExamStatus.PUBLISHED
    return True


def visible_marks_for(queryset, user):
    """Narrow a `Mark` queryset to what *user* is allowed to read.

    Filtering rather than refusing, for the reason `TeacherScopedMixin` gives:
    an invisible row produces a 404 from `get_object()`, and 403 would confirm
    the mark exists — which for an unpublished result is the entire secret.
    """
    if getattr(user, 'user_type', None) not in ('student', 'guardian'):
        return queryset

    queryset = queryset.filter(exam__status=ExamStatus.PUBLISHED)
    student = getattr(user, 'student_profile', None)
    return queryset.filter(student=student) if student is not None else queryset.none()


# ─────────────────────────────────────────────────────────────────────────────
# Reading results — computed, not stored (V1)
# ─────────────────────────────────────────────────────────────────────────────

def _full_marks_map(exam, academic_class=None):
    """`{subject_id: (full, pass)}` for this exam, from the schedule.

    The schedule is authoritative rather than `Subject.full_marks`: a
    half-yearly may be out of 50 where the annual is out of 100, and the totals
    on last year's marksheet must not change when the subject is re-weighted.
    A subject with no schedule row falls back to the subject's own marks, which
    is what a `sabaq` exam nobody timetabled needs.
    """
    schedules = ExamSchedule.objects.filter(exam=exam)
    if academic_class is not None:
        schedules = schedules.filter(academic_class=academic_class)
    return {
        schedule.subject_id: (schedule.full_marks, schedule.pass_marks)
        for schedule in schedules
    }


def _grade_marks(marks, fulls, scale):
    """Grade one student's marks. Returns `(subject_lines, summary)`.

    The schedule's full and pass marks are authoritative; a subject with no
    schedule row falls back to the subject's own (see `_full_marks_map`).
    """
    papers = []
    for mark in marks:
        full, pass_mark = fulls.get(
            mark.subject_id,
            (Decimal(mark.subject.full_marks), Decimal(mark.subject.pass_marks)),
        )
        papers.append({
            'name': mark.subject.name,
            'full': full,
            'pass_mark': pass_mark,
            'obtained': ZERO if mark.is_absent else (mark.total_obtained or ZERO),
            'is_absent': mark.is_absent,
            'is_optional': mark.subject.is_optional,
        })

    graded, summary = evaluate(scale, papers)

    lines = []
    for mark, paper, grade in zip(marks, papers, graded):
        lines.append({
            'subject': mark.subject_id,
            'subject_name': mark.subject.name,
            'subject_name_bn': mark.subject.name_bn,
            'full_marks': paper['full'],
            'pass_marks': paper['pass_mark'],
            'obtained': None if mark.is_absent else mark.obtained,
            'practical_obtained': None if mark.is_absent else mark.practical_obtained,
            'total': paper['obtained'],
            'is_absent': mark.is_absent,
            'is_optional': paper['is_optional'],
            'is_passed': grade['is_passed'],
            'grade': grade['grade'],
            'grade_bn': grade['grade_bn'],
            'point': grade['point'],
        })
    return lines, summary


_SUMMARY_KEYS = ('total_marks', 'obtained_marks', 'percentage', 'gpa', 'grade',
                 'grade_bn', 'is_passed', 'failed_subjects')


def student_result(exam, student):
    """This student's result for this exam.

    Published: the `Result` row frozen at publish, unchanged by any later edit
    to the scale. Open: computed now, through the বিভাগ's scale.

    Absent counts as zero *obtained* but still counts its paper's full marks
    towards the total. Dropping the paper instead would let a student who missed
    their weakest subject come out with a higher percentage than one who sat it.
    """
    if exam.status == ExamStatus.PUBLISHED:
        stored = Result.objects.filter(exam=exam, student=student).order_by('-pk').first()
        if stored is not None:
            return {
                'exam': exam.pk,
                'student': student.pk,
                'student_name': student.name,
                'subjects': stored.subjects,
                **{key: stored.row.get(key) for key in _SUMMARY_KEYS},
                'method': stored.method,
                'scale_name': stored.scale_name,
                'scale_name_bn': stored.scale_name_bn,
                'is_published': True,
            }

    marks = list(
        Mark.objects.filter(exam=exam, student=student, is_active=True)
        .select_related('subject')
    )
    scale = scale_for(exam)
    lines, summary = _grade_marks(marks, _full_marks_map(exam), scale)

    return {
        'exam': exam.pk,
        'student': student.pk,
        'student_name': student.name,
        'subjects': lines,
        **summary,
        'method': scale.method,
        'scale_name': scale.name,
        'scale_name_bn': scale.name_bn,
        'is_published': exam.status == ExamStatus.PUBLISHED,
    }


def _rank(rows, field, method):
    """Write a merit rank into `field` on each passed row, in place.

    GPA then total marks under the board method, total marks under the Qawmi
    one; failures are left unranked. Equal keys share a rank — 1, 2, 2, 4 —
    because breaking a genuine tie arbitrarily is a decision the software does
    not get to make on a teacher's behalf.
    """
    ranked = sorted(
        [row for row in rows if row['is_passed']],
        key=lambda row: rank_key(method, row), reverse=True,
    )
    previous_key = None
    previous_rank = 0
    for index, row in enumerate(ranked, start=1):
        key = rank_key(method, row)
        if key == previous_key:
            row[field] = previous_rank
        else:
            row[field] = index
            previous_rank = index
            previous_key = key


def _compute_rows(exam, academic_class):
    """Every student on this class's sheet, graded and ranked, computed now.

    Returns `(rows, scale, subject_lines_by_enrolment)`. One query for the marks
    and one for the enrolments, then the arithmetic in Python: per-student
    `student_result()` calls would be N+1 queries against a sheet that is
    printed for forty students at once.
    """
    scale = scale_for(exam)
    marks = (
        Mark.objects
        .filter(exam=exam, enrolment__academic_class=academic_class, is_active=True)
        .select_related('subject')
    )
    # Anyone who sat a paper stays on the sheet even once their enrolment is
    # closed. A student who took a transfer certificate before publication had
    # no frozen `Result` row at all, so their marksheet silently fell back to a
    # live recompute against whatever the scale says today — the one property
    # freezing exists to prevent.
    sat = set(marks.values_list('enrolment_id', flat=True))
    enrolments = (
        Enrolment.objects
        .filter(Q(is_active=True) | Q(pk__in=sat),
                branch_id=exam.branch_id, session_id=exam.session_id,
                academic_class=academic_class)
        .select_related('student', 'section')
        .order_by('roll')
    )
    fulls = _full_marks_map(exam, academic_class)

    by_student = {}
    for mark in marks:
        by_student.setdefault(mark.student_id, []).append(mark)

    rows = []
    lines_by_enrolment = {}
    for enrolment in enrolments:
        lines, summary = _grade_marks(by_student.get(enrolment.student_id, []), fulls, scale)
        lines_by_enrolment[enrolment.pk] = lines
        section = enrolment.section

        rows.append({
            'enrolment': enrolment.pk,
            'student': enrolment.student_id,
            'student_name': enrolment.student.name,
            'student_name_bn': enrolment.student.name_bn,
            'student_code': enrolment.student.student_id,
            'section': enrolment.section_id,
            'section_name': section.name if section else '',
            'section_name_bn': section.name_bn if section else '',
            'roll': enrolment.roll,
            'marks': {
                line['subject']: {
                    'obtained': line['obtained'],
                    'practical_obtained': line['practical_obtained'],
                    'total': line['total'],
                    'is_absent': line['is_absent'],
                    'is_passed': line['is_passed'],
                    'grade': line['grade'],
                    'grade_bn': line['grade_bn'],
                    'point': line['point'],
                }
                for line in lines
            },
            **summary,
            'rank_in_class': None,
            'rank_in_section': None,
        })

    _rank(rows, 'rank_in_class', scale.method)

    # The same rule again inside each section. A class split into ক and খ reads
    # its merit list per section as often as for the whole class, and both come
    # from the same marks — so both are on the row, and choosing a section on
    # the screen is a filter rather than a second request.
    by_section = {}
    for row in rows:
        if row['section'] is not None:
            by_section.setdefault(row['section'], []).append(row)
    for section_rows in by_section.values():
        _rank(section_rows, 'rank_in_section', scale.method)

    return rows, scale, lines_by_enrolment


def _sheet(exam, academic_class, rows, method, scale_name, scale_name_bn):
    # Through the same encoder the frozen rows were stored with, so the two
    # paths answer in one shape: subject ids as string keys, money and marks as
    # decimal **strings**. Computed rows used to come back with int keys and
    # Decimals that DRF rendered as floats — the same endpoint with two
    # contracts, and the float half breaking the project's own money rule.
    rows = json.loads(json.dumps(rows, cls=DjangoJSONEncoder))

    sections = {}
    for row in rows:
        if row.get('section') and row['section'] not in sections:
            sections[row['section']] = {
                'id': row['section'],
                'name': row.get('section_name', ''),
                'name_bn': row.get('section_name_bn', ''),
            }
    return {
        'exam': exam.pk,
        'academic_class': academic_class.pk,
        'is_published': exam.status == ExamStatus.PUBLISHED,
        'method': method,
        'scale_name': scale_name,
        'scale_name_bn': scale_name_bn,
        'sections': sorted(sections.values(), key=lambda row: row['name']),
        'rows': rows,
    }


def tabulation(exam, academic_class):
    """The class tabulation sheet: every student, every subject, graded, ranked.

    Published: the rows frozen at publish. Open: computed now.
    """
    if exam.status == ExamStatus.PUBLISHED:
        stored = list(Result.objects.filter(exam=exam, enrolment__academic_class=academic_class))
        if stored:
            rows = sorted(
                (result.row for result in stored),
                key=lambda row: (row.get('roll') is None, row.get('roll') or 0),
            )
            first = stored[0]
            return _sheet(exam, academic_class, rows, first.method,
                          first.scale_name, first.scale_name_bn)

    rows, scale, _lines = _compute_rows(exam, academic_class)
    return _sheet(exam, academic_class, rows, scale.method, scale.name, scale.name_bn)


def _store_results(exam, actor=None):
    """Freeze every class's sheet for this exam into `Result` rows.

    Called by `publish_exam()` inside its transaction. Every enrolled student of
    every class on the exam gets a row — including one who sat nothing, whose
    row says so — so the published sheet is the sheet that was published.
    """
    Result.objects.filter(exam=exam).delete()

    class_ids = set(
        ExamSchedule.objects.filter(exam=exam).values_list('academic_class_id', flat=True)
    )
    class_ids |= set(
        Mark.objects.filter(exam=exam, is_active=True)
        .values_list('enrolment__academic_class_id', flat=True)
    )

    to_create = []
    for academic_class in AcademicClass.objects.filter(pk__in=class_ids):
        rows, scale, lines = _compute_rows(exam, academic_class)
        for row in rows:
            to_create.append(Result(
                branch_id=exam.branch_id, exam=exam,
                student_id=row['student'], enrolment_id=row['enrolment'],
                method=scale.method, scale_name=scale.name, scale_name_bn=scale.name_bn,
                percentage=row['percentage'], gpa=row['gpa'],
                grade=row['grade'], grade_bn=row['grade_bn'], is_passed=row['is_passed'],
                rank_in_class=row['rank_in_class'], rank_in_section=row['rank_in_section'],
                row=row, subjects=lines[row['enrolment']],
                created_by=actor, updated_by=actor,
            ))
    Result.objects.bulk_create(to_create)
    return len(to_create)


def exam_subjects(exam, academic_class):
    """The subjects on this class's paper list, for the entry grid's columns."""
    return list(
        ExamSchedule.objects
        .filter(exam=exam, academic_class=academic_class)
        .select_related('subject')
        .order_by('date', 'start_time')
    )


__all__ = [
    'assert_can_enter_marks', 'can_enter_marks', 'exam_subjects',
    'marks_are_visible_to', 'publish_exam', 'save_marks', 'student_report',
    'student_result', 'tabulation', 'visible_marks_for',
]


def student_report(student, exams):
    """Every exam this student sat, newest first, with their rank in each.

    The screen this feeds is "find a student, see all their results", so it is
    one request rather than one per exam. `exams` is the already-scoped, already
    visibility-filtered list the view decided this caller may see; nothing here
    widens it.

    Rank needs the whole class, so each exam's class sheet is computed once.
    A student sits a handful of exams a year, so that is a handful of sheets,
    not a query per classmate.
    """
    first_mark_per_exam = {}
    marks = (
        Mark.objects
        .filter(student=student, is_active=True, exam__in=exams)
        .select_related('exam', 'exam__session', 'enrolment__academic_class',
                        'enrolment__section')
        .order_by('exam_id', 'id')
    )
    for mark in marks:
        first_mark_per_exam.setdefault(mark.exam_id, mark)

    lines = []
    for mark in sorted(first_mark_per_exam.values(),
                       key=lambda row: row.exam.starts_on, reverse=True):
        exam = mark.exam
        enrolment = mark.enrolment
        sheet = tabulation(exam, enrolment.academic_class)
        mine = next((row for row in sheet['rows'] if row['enrolment'] == enrolment.pk), None)
        section = enrolment.section

        lines.append({
            **student_result(exam, student),
            'exam_name': exam.name,
            'exam_name_bn': exam.name_bn,
            'exam_type': exam.exam_type,
            'status': exam.status,
            'starts_on': exam.starts_on,
            'session': exam.session_id,
            'session_name': exam.session.name,
            'academic_class': enrolment.academic_class_id,
            'class_name': enrolment.academic_class.name,
            'class_name_bn': enrolment.academic_class.name_bn,
            'section': enrolment.section_id,
            'section_name': section.name if section else '',
            'section_name_bn': section.name_bn if section else '',
            'roll': enrolment.roll,
            'rank_in_class': mine['rank_in_class'] if mine else None,
            'rank_in_section': mine['rank_in_section'] if mine else None,
            'class_size': len(sheet['rows']),
        })

    return {
        'student': student.pk,
        'student_code': student.student_id,
        'student_name': student.name,
        'student_name_bn': student.name_bn,
        'exams': lines,
    }
