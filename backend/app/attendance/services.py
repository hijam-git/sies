"""Attendance operations that span more than one table (CLAUDE.md §4.3).

Everything the API does lives here, in a transaction, and the views are thin
wrappers over it. Four things:

* **`is_markable()`** — the one definition of "may this cell be marked at all".
  Future dates, weekly off days and the period attendance window are decided
  here and nowhere else, so the grid, the bulk save and the teacher's board
  cannot disagree about a Friday.
* **`save_register()`** — the batch upsert behind the month grid. One
  transaction, idempotent on the models' own unique keys, `taken_by` stamped
  from the request user per cell.
* **`month_register()`** / **`attendance_summary()`** — the reads. Percentages
  are computed here on every read; the nightly `AttendanceSummary` rollup of
  docs/03 §6 is V2 and this is deliberately the simple version.
* **`teacher_today()`** — the today board of docs/08 D7.

**Server-authoritative, always.** `save_register()` re-decides markability for
every cell it is handed. The client renders off days greyed out, but that is a
convenience for the teacher and not a check: however the client was persuaded to
send a Friday, it lands in `skipped` and never in the database.
"""

import calendar
from datetime import date as date_cls
from datetime import datetime, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from academics.models import Enrolment, EnrolmentStatus, Period
from academics.services import day_index

from .models import (AttendanceSource, AttendanceStatus, ClassAttendance,
                     DailyAttendance, PersonType)

# `Branch.weekly_off_days` stores three-letter lowercase codes (`["fri"]`, its
# default). `DayOfWeek` stores the Bangladeshi week with Saturday at 0, so this
# table is indexed by that and not by Python's Monday-at-0 `weekday()`.
# `academics.services.day_index()` is the one place that converts a date.
WEEKDAY_CODES = ['sat', 'sun', 'mon', 'tue', 'wed', 'thu', 'fri']

# Why a cell could not be marked. Machine-readable codes, because the SPA greys
# a column out on `weekly_off` and shows a toast on `window_closed` — switching
# on a sentence would break the first time somebody improved the wording.
REASON_FUTURE = 'future'
REASON_WEEKLY_OFF = 'weekly_off'
REASON_WINDOW_CLOSED = 'window_closed'
REASON_REGISTER_CLOSED = 'register_closed'
REASON_NOT_ENROLLED = 'not_enrolled'
REASON_OUTSIDE_MONTH = 'outside_month'
REASON_UNKNOWN_STUDENT = 'unknown_student'

# One sentence per code, in both languages (CLAUDE.md §8.9). Kept beside the
# codes rather than in the SPA so that a `skipped` list is readable in a curl
# response and in a log, not only after the front end has rendered it.
REASON_TEXT = {
    REASON_REGISTER_CLOSED: (
        'This day is too old to change. Ask the class teacher or the principal.',
        'এই দিনটি পরিবর্তনের সময় শেষ। শ্রেণি শিক্ষক বা মুহতামিমকে বলুন।',
    ),
    REASON_FUTURE: ('A future date cannot be marked.',
                    'ভবিষ্যতের তারিখে হাজিরা নেওয়া যাবে না।'),
    REASON_WEEKLY_OFF: ('Weekly off day.', 'সাপ্তাহিক ছুটির দিন।'),
    REASON_WINDOW_CLOSED: ('The attendance window for this period has closed.',
                           'এই পিরিয়ডের হাজিরার সময় শেষ হয়েছে।'),
    REASON_NOT_ENROLLED: ('Not enrolled in this class.',
                          'এই শ্রেণিতে ভর্তি নেই।'),
    REASON_OUTSIDE_MONTH: ('Outside the month being saved.',
                           'নির্ধারিত মাসের বাইরের তারিখ।'),
    REASON_UNKNOWN_STUDENT: ('No such student in this institution.',
                             'এই প্রতিষ্ঠানে এমন কোনো শিক্ষার্থী নেই।'),
}


class Markability:
    """The answer `is_markable()` gives, and why.

    A small object rather than a bare bool: every caller needs the reason —
    the grid renders it in the column header, the bulk save copies it into
    `skipped`, the teacher's board turns it into the `!` missed marker — and a
    bool would have each of them re-deriving it and getting a different answer.
    """

    __slots__ = ('ok', 'reason')

    def __init__(self, ok, reason=''):
        self.ok = ok
        self.reason = reason

    def __bool__(self):
        return self.ok

    def as_dict(self):
        english, bangla = REASON_TEXT.get(self.reason, ('', ''))
        return {
            'is_markable': self.ok,
            'reason': self.reason,
            'reason_text': english,
            'reason_text_bn': bangla,
        }


MARKABLE = Markability(True)


# ─────────────────────────────────────────────────────────────────────────────
# The rules — docs/02 §4.4, docs/08 D7
# ─────────────────────────────────────────────────────────────────────────────

def is_markable(branch, on_date, period=None, *, user=None, now=None):
    """May attendance be marked for *on_date* (and *period*) right now?

    The single definition of the rule, in the order the rules actually bite:

    1. **A future date is never markable.** Tomorrow has not happened, and no
       permission makes it have happened. This one has no override.
    2. **A weekly off day is not markable** — `Branch.weekly_off_days`, e.g.
       `["fri"]`. The month grid puts four or five of these on screen at once,
       so the teacher is never asked to mark a Friday and the percentage
       denominator excludes it.
    3. **For period attendance only**, the window of docs/08 D7:
       `Branch.attendance_window_minutes` (default 120, generous on purpose)
       measured from the period's `end_time`. **`0` means unlimited.** Inside the
       window `attendance.take` is enough. Outside it, filling the period in
       afterwards needs `attendance.update` — the class teacher or the
       principal.

    The window is a guard against a period being marked days later from memory,
    not a punishment: connectivity fails and teachers get busy, so the default is
    wide and a principal can always correct.

    *user* is optional so a read can ask the plain question ("is this day off?")
    without an account; with no user, a closed window answers `False`, which is
    the safe direction — a caller that never proved it may override does not get
    the override.
    """
    now = now or timezone.localtime()
    today = now.date()

    if on_date > today:
        return Markability(False, REASON_FUTURE)

    off_days = getattr(branch, 'weekly_off_days', None) or []
    if WEEKDAY_CODES[day_index(on_date)] in {str(d).strip().lower() for d in off_days}:
        return Markability(False, REASON_WEEKLY_OFF)

    if period is None:
        # The DAILY register's own window, in days.
        #
        # An earlier version returned MARKABLE here, reasoning that a window
        # measured in minutes from a period's end time is meaningless for a
        # whole day. That is true, and the conclusion drawn from it was wrong:
        # it left the register with no bound at all, so a teacher could rewrite
        # any past school day in their classes indefinitely. A register that can
        # be edited a month later is not a record of who was there.
        #
        # So the unit changes rather than the rule: days, not minutes.
        back = getattr(branch, 'register_edit_days', 0) or 0
        if back == 0:
            return MARKABLE
        if (today - on_date).days <= back:
            return MARKABLE
        if _may_update(user):
            return MARKABLE
        return Markability(False, REASON_REGISTER_CLOSED)

    window = getattr(branch, 'attendance_window_minutes', 0) or 0
    if window == 0:
        # Unlimited, by the institution's own choice (docs/08 D7).
        return MARKABLE

    closes_at = _aware(datetime.combine(on_date, period.end_time), now) \
        + timedelta(minutes=window)
    if now <= closes_at:
        return MARKABLE

    if _may_update(user):
        return MARKABLE

    return Markability(False, REASON_WINDOW_CLOSED)


def _aware(naive, reference):
    """*naive* in the same timezone as *reference*, when time zones are on."""
    if timezone.is_aware(reference):
        return timezone.make_aware(naive, reference.tzinfo)
    return naive


def _may_update(user):
    """Whether *user* may fill in attendance outside the window.

    `attendance.update` and not `attendance.take`: taking is the live act a
    subject teacher does, correcting afterwards is the class teacher's and the
    principal's (docs/08 D7, and the role presets in accounts/permissions.py).
    """
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True

    from accounts.permissions import has_permission
    return has_permission(user, 'attendance', 'update')


# ─────────────────────────────────────────────────────────────────────────────
# The month register — docs/02 §4.4 and §5.1
# ─────────────────────────────────────────────────────────────────────────────

def parse_month(value):
    """`"2026-03"` → `(2026, 3)`. Raises ValidationError on anything else.

    A ValidationError and not a ValueError: this is reached straight off a query
    string, and DRF turns it into the project's one error shape rather than a
    500 with a traceback (CLAUDE.md §5).
    """
    try:
        year, month = str(value).strip().split('-')
        year, month = int(year), int(month)
        if not 1 <= month <= 12:
            raise ValueError
        date_cls(year, month, 1)
    except (AttributeError, TypeError, ValueError):
        raise ValidationError({
            'month': 'Expected a month as YYYY-MM, for example 2026-03.',
        })
    return year, month


def month_days(year, month):
    last = calendar.monthrange(year, month)[1]
    return [date_cls(year, month, day) for day in range(1, last + 1)]


def register_enrolments(*, branch, academic_class, section=None, session=None):
    """The students whose rows make up this register, in roll order.

    Filtered on `Enrolment` and not on `Student`, because the register is a
    property of the *class*, not of the person: a student who left in March is in
    March's register and out of April's, and that is exactly what
    `is_active` plus `left_on` on the enrolment already record.
    """
    enrolments = (Enrolment.objects
                  .for_branch(branch)
                  .filter(academic_class=academic_class,
                          status=EnrolmentStatus.ACTIVE, is_active=True)
                  .select_related('student')
                  .order_by('roll', 'student__name'))
    if section is not None:
        enrolments = enrolments.filter(section=section)
    if session is not None:
        enrolments = enrolments.filter(session=session)
    return enrolments


def month_register(branch, academic_class, section=None, month=None, *,
                   user=None, now=None):
    """The month grid of docs/02 §4.4, as `{days, students}`.

    Two queries regardless of class size — the enrolments and the month's
    attendance rows — and the cells are assembled in Python. The alternative,
    one query per student or per cell, is 1,800 round trips for a class of sixty.

    Every day carries its own `is_markable` and `reason`, so the grid greys out
    weekends and future dates from the server's answer rather than from a rule
    the front end reimplemented.
    """
    year, month_number = parse_month(month)
    days = month_days(year, month_number)
    now = now or timezone.localtime()

    day_flags = [
        {'date': day.isoformat(), **is_markable(branch, day, user=user, now=now).as_dict()}
        for day in days
    ]

    enrolments = list(register_enrolments(
        branch=branch, academic_class=academic_class, section=section,
    ))

    rows = (DailyAttendance.objects
            .for_branch(branch)
            .filter(person_type=PersonType.STUDENT,
                    student__in=[e.student_id for e in enrolments],
                    date__gte=days[0], date__lte=days[-1])
            .select_related('taken_by'))

    cells_by_student = {}
    for row in rows:
        cells_by_student.setdefault(row.student_id, {})[row.date.isoformat()] = {
            'status': row.status,
            'taken_by': row.taken_by_id,
            'taken_by_name': row.taken_by.name if row.taken_by else '',
            'taken_at': row.taken_at.isoformat() if row.taken_at else None,
            'remarks': row.remarks,
        }

    students = []
    for enrolment in enrolments:
        cells = cells_by_student.get(enrolment.student_id, {})
        students.append({
            # `student` is the primary key the bulk endpoint expects back;
            # `student_id` is the human identifier printed down the left of the
            # grid (`SIES-000123`). Both, because the grid shows one and posts
            # the other, and conflating them is how a save silently targets the
            # wrong row.
            'student': enrolment.student_id,
            'student_code': enrolment.student.student_id,
            'enrolment': enrolment.pk,
            'name': enrolment.student.name,
            'name_bn': enrolment.student.name_bn,
            'roll': enrolment.roll,
            'cells': cells,
            **_totals(cells),
        })

    return {
        'month': f'{year:04d}-{month_number:02d}',
        'class': academic_class.pk,
        'section': section.pk if section is not None else None,
        'days': day_flags,
        'students': students,
    }


def _totals(cells):
    """Present / absent / leave counts and a percentage, computed on read.

    The `AttendanceSummary` rollup of docs/03 §6 is V2. Until it exists this is
    a count over one month of one class, which is a handful of rows already in
    memory — cheap enough that caching it would cost more than it saved.

    `late` counts as present, because it is: the student was there. `half_day`
    counts as half, which is the only reason the numerator is a float. The
    denominator is the days actually **marked**, excluding holidays — so a
    percentage never drops because a month is not finished yet, which is the
    complaint every attendance report gets on the first of the month.
    """
    counts = {status: 0 for status in AttendanceStatus.values}
    for cell in cells.values():
        if cell['status'] in counts:
            counts[cell['status']] += 1

    marked = sum(count for status, count in counts.items()
                 if status != AttendanceStatus.HOLIDAY)
    attended = (counts[AttendanceStatus.PRESENT]
                + counts[AttendanceStatus.LATE]
                + counts[AttendanceStatus.HALF_DAY] * 0.5)

    return {
        'present': counts[AttendanceStatus.PRESENT],
        'absent': counts[AttendanceStatus.ABSENT],
        'late': counts[AttendanceStatus.LATE],
        'leave': counts[AttendanceStatus.LEAVE],
        'half_day': counts[AttendanceStatus.HALF_DAY],
        'holiday': counts[AttendanceStatus.HOLIDAY],
        'marked_days': marked,
        'percent': round(100.0 * attended / marked, 1) if marked else None,
    }


@transaction.atomic
def save_register(*, branch, academic_class, cells, user, section=None,
                  month=None, source=AttendanceSource.WEB, now=None):
    """The batch upsert behind the month grid (docs/02 §5.1, docs/06 #11).

    **One transaction.** A partial save that leaves half a month written is worse
    than a failed one, because nobody can tell which half — so an unexpected
    failure anywhere in the batch rolls the whole thing back, including the cells
    that were already fine. `skipped` is not a failure: a rejected cell is a
    normal, expected answer and the rest of the batch still commits.

    **Idempotent.** Each cell is an upsert on the model's own unique key
    `(branch, date, student)`, so the same payload sent twice writes the same
    rows — which is what makes the grid's debounced auto-save safe to fire
    alongside an explicit Save.

    **Server-authoritative.** Markability is re-decided here for every cell. The
    client's greyed-out columns are a convenience for the teacher, not a check.

    `taken_by` is stamped from *user* **per cell**, never read from the payload:
    the whole point of the column is that it says who actually marked it.

    Returns `{'saved': int, 'skipped': [{student, date, reason, ...}]}`.
    """
    now = now or timezone.localtime()
    bounds = None
    if month is not None:
        year, month_number = parse_month(month)
        days = month_days(year, month_number)
        bounds = (days[0], days[-1])

    # The register's own students, by student id, so an unknown or out-of-class
    # student is rejected rather than written against a class they never
    # attended. This is also where `enrolment` comes from — the field that keeps
    # a historical register correct.
    enrolments = {
        e.student_id: e
        for e in register_enrolments(branch=branch, academic_class=academic_class,
                                     section=section)
    }

    # Markability is decided once per distinct date, not once per cell: sixty
    # students on the same Friday is one question, not sixty.
    markable_cache = {}
    saved = 0
    skipped = []

    for cell in cells:
        on_date = cell['date']
        student_id = cell['student']

        if bounds is not None and not bounds[0] <= on_date <= bounds[1]:
            skipped.append(_skip(student_id, on_date, REASON_OUTSIDE_MONTH))
            continue

        if on_date not in markable_cache:
            markable_cache[on_date] = is_markable(branch, on_date, user=user, now=now)
        verdict = markable_cache[on_date]
        if not verdict.ok:
            skipped.append(_skip(student_id, on_date, verdict.reason))
            continue

        enrolment = enrolments.get(student_id)
        if enrolment is None:
            skipped.append(_skip(student_id, on_date, REASON_NOT_ENROLLED))
            continue

        # `update_or_create` on the unique key IS the upsert (docs/06 #11), and
        # it is the same key the database enforces — so two teachers saving the
        # same cell at once end with one row, and the loser's write is an update
        # rather than an IntegrityError.
        _, created = DailyAttendance.objects.update_or_create(
            branch=branch,
            date=on_date,
            person_type=PersonType.STUDENT,
            student_id=student_id,
            defaults={
                'teacher': None,
                'employee': None,
                'enrolment': enrolment,
                'status': cell['status'],
                'remarks': cell.get('remarks', ''),
                'in_time': cell.get('in_time'),
                'out_time': cell.get('out_time'),
                # Overwritten on every save. This is docs/08 D3 in one line: a
                # correction replaces who took it and when, and the previous
                # values are gone from this table.
                'taken_by': user if getattr(user, 'is_authenticated', False) else None,
                'taken_at': now,
                'source': source,
                'updated_by': user if getattr(user, 'is_authenticated', False) else None,
            },
        )
        if created:
            # `created_by` is not in `defaults`: on an update it would rewrite
            # who first marked the cell, which is a different fact from who last
            # changed it and the only one still recoverable after a correction.
            DailyAttendance.objects.filter(
                branch=branch, date=on_date,
                person_type=PersonType.STUDENT, student_id=student_id,
            ).update(created_by=user if getattr(user, 'is_authenticated', False) else None)
        saved += 1

    return {'saved': saved, 'skipped': skipped}


def _skip(student_id, on_date, reason):
    english, bangla = REASON_TEXT.get(reason, ('', ''))
    return {
        'student': student_id,
        'date': on_date.isoformat(),
        'reason': reason,
        'reason_text': english,
        'reason_text_bn': bangla,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Period attendance — docs/08 D7
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def save_class_attendance(*, branch, academic_class, period, on_date, cells,
                          user, section=None, subject=None,
                          source=AttendanceSource.WEB, now=None):
    """One period's roster, written in one transaction.

    The same three properties as `save_register()` — idempotent, server-
    authoritative, atomic — against `ClassAttendance`'s own unique key
    `(branch, date, academic_class, section, period, student)`. The difference is
    that markability here consults the **window**: a period that ended three
    hours ago is `window_closed` for a subject teacher and open for whoever holds
    `attendance.update`.

    Markability is one question for the whole roster (one date, one period), so
    it is asked once and every cell of a closed period is skipped with the same
    reason — which is what lets the front end show one message rather than
    thirty identical ones.
    """
    now = now or timezone.localtime()
    verdict = is_markable(branch, on_date, period, user=user, now=now)

    enrolments = {
        e.student_id: e
        for e in register_enrolments(branch=branch, academic_class=academic_class,
                                     section=section)
    }

    if not verdict.ok:
        return {
            'saved': 0,
            'skipped': [_skip(cell['student'], on_date, verdict.reason)
                        for cell in cells],
        }

    saved = 0
    skipped = []
    for cell in cells:
        enrolment = enrolments.get(cell['student'])
        if enrolment is None:
            skipped.append(_skip(cell['student'], on_date, REASON_NOT_ENROLLED))
            continue

        ClassAttendance.objects.update_or_create(
            branch=branch,
            date=on_date,
            academic_class=academic_class,
            section=section,
            period=period,
            student_id=cell['student'],
            defaults={
                'subject': subject,
                'enrolment': enrolment,
                'status': cell['status'],
                'remarks': cell.get('remarks', ''),
                'taken_by': user if getattr(user, 'is_authenticated', False) else None,
                'taken_at': now,
                'source': source,
                'updated_by': user if getattr(user, 'is_authenticated', False) else None,
            },
        )
        saved += 1

    return {'saved': saved, 'skipped': skipped}


# ─────────────────────────────────────────────────────────────────────────────
# The teacher's today board — docs/08 D7
# ─────────────────────────────────────────────────────────────────────────────

#: The four states a period card can be in, in the order D7's legend lists them.
STATE_TAKEN = 'taken'
STATE_LIVE = 'live'
STATE_UPCOMING = 'upcoming'
STATE_MISSED = 'missed'


def teacher_today(teacher, on_date=None, *, user=None, now=None):
    """The teacher's board: their periods for *on_date*, in order, with state.

    Each row carries exactly what docs/08 D7 asked for — **name, time, student
    count** — plus the state, which is what makes the board a to-do list rather
    than a decoration.

    The **student count is computed from `Enrolment`, never stored**. A stored
    count is wrong the day after a student is admitted, and it is wrong silently.

    Ordered by `period__order`, which is the bell schedule's own order and not
    the clock: a stream whose first period starts after Fajr still reads
    first-to-last down the card list.

    **Breaks never appear.** A tiffin or prayer slot occupies a period row so the
    timetable lines up, and putting "take attendance for the break" on a
    teacher's to-do list would be nonsense (D7).

    Filtered on `ClassRoutine.teacher` — the periods they actually *teach* — and
    not on the wider class scope of D6, which also includes classes they are
    merely in charge of. A board full of periods somebody else is teaching is not
    a to-do list.
    """
    if teacher is None:
        return []

    from academics.models import ClassRoutine

    on_date = on_date or timezone.localdate()
    now = now or timezone.localtime()
    branch = teacher.branch

    routines = (ClassRoutine.objects
                .for_branch(branch)
                .filter(teacher=teacher,
                        day_of_week=day_index(on_date),
                        is_active=True,
                        period__is_break=False)
                .select_related('academic_class', 'section', 'subject', 'period',
                                'session')
                .order_by('period__order', 'period__start_time', 'id'))

    # One query for every period already taken today, rather than one per row: a
    # teacher with eight periods would otherwise make eight round trips to
    # render a screen that is opened every morning by every teacher at once.
    taken_keys = set(
        ClassAttendance.objects
        .for_branch(branch)
        .filter(date=on_date, taken_by__isnull=False)
        .values_list('academic_class_id', 'section_id', 'period_id')
    )

    board = []
    for routine in routines:
        period = routine.period
        starts = _aware(datetime.combine(on_date, period.start_time), now)
        ends = _aware(datetime.combine(on_date, period.end_time), now)

        key = (routine.academic_class_id, routine.section_id, routine.period_id)
        if key in taken_keys:
            state = STATE_TAKEN
        elif now < starts:
            state = STATE_UPCOMING
        elif now <= ends:
            state = STATE_LIVE
        else:
            state = STATE_MISSED

        verdict = is_markable(branch, on_date, period, user=user, now=now)

        board.append({
            'routine': routine.pk,
            'class': routine.academic_class_id,
            'class_name': routine.academic_class.name,
            'class_name_bn': routine.academic_class.name_bn,
            'section': routine.section_id,
            'section_name': routine.section.name if routine.section else '',
            'subject': routine.subject_id,
            'subject_name': routine.subject.name if routine.subject else '',
            'subject_name_bn': routine.subject.name_bn if routine.subject else '',
            'period': period.pk,
            'period_name': period.name,
            'period_name_bn': period.name_bn,
            'period_order': period.order,
            'start_time': period.start_time.isoformat(timespec='minutes'),
            'end_time': period.end_time.isoformat(timespec='minutes'),
            'room': routine.room,
            'student_count': student_count(
                branch=branch,
                academic_class=routine.academic_class,
                section=routine.section,
                session=routine.session,
            ),
            'state': state,
            # Separate from `state` on purpose: a `missed` period is still
            # markable for a principal, and a `live` one is not markable on a
            # weekly off day. The button is drawn from this, the icon from the
            # state.
            **verdict.as_dict(),
        })

    return board


def student_count(*, branch, academic_class, section=None, session=None):
    """`Enrolment.objects.filter(...).count()` — computed, never stored (D7)."""
    return register_enrolments(
        branch=branch, academic_class=academic_class,
        section=section, session=session,
    ).count()


# ─────────────────────────────────────────────────────────────────────────────
# Reporting
# ─────────────────────────────────────────────────────────────────────────────

def attendance_summary(*, branch, month, person_type=PersonType.STUDENT,
                       academic_class=None, section=None, person_ids=None):
    """Per-person totals and percentages for one month, computed on read.

    The rollup table of docs/03 §6 — a nightly Celery job writing
    `(branch, person, month)` — is **V2**. This is the V1 answer and it is one
    indexed query over one month; the rollup exists for the *year* report, which
    is twelve times this and is not a V1 screen.

    Shape matches the register's per-student totals exactly, so the report screen
    and the grid's right-hand column cannot disagree about what 92% means.
    """
    year, month_number = parse_month(month)
    days = month_days(year, month_number)

    rows = (DailyAttendance.objects
            .for_branch(branch)
            .filter(person_type=person_type,
                    date__gte=days[0], date__lte=days[-1]))

    if academic_class is not None:
        rows = rows.filter(enrolment__academic_class=academic_class)
    if section is not None:
        rows = rows.filter(enrolment__section=section)
    if person_ids is not None:
        rows = rows.filter(**{f'{person_type}_id__in': list(person_ids)})

    person_field = f'{person_type}_id'
    per_person = {}
    for row in rows.only('status', 'date', person_field, 'student_id',
                         'teacher_id', 'employee_id'):
        key = getattr(row, person_field)
        per_person.setdefault(key, {})[row.date.isoformat()] = {'status': row.status}

    return [
        {'person_type': person_type, 'person': key, **_totals(cells)}
        for key, cells in sorted(per_person.items(), key=lambda item: item[0] or 0)
    ]


def period_roster(*, branch, academic_class, period, on_date, section=None,
                  user=None, now=None):
    """One period's roster, defaulted to present (docs/08 D7).

    The read half of the Take-attendance button. Existing rows win over the
    default, so re-opening a period that was already taken shows what was
    recorded rather than resetting thirty students to present — which is how a
    correction screen quietly destroys the data it was opened to fix.
    """
    now = now or timezone.localtime()
    enrolments = list(register_enrolments(
        branch=branch, academic_class=academic_class, section=section,
    ))

    existing = {
        row.student_id: row
        for row in ClassAttendance.objects
        .for_branch(branch)
        .filter(date=on_date, academic_class=academic_class,
                section=section, period=period)
        .select_related('taken_by')
    }

    students = []
    for enrolment in enrolments:
        row = existing.get(enrolment.student_id)
        students.append({
            'student': enrolment.student_id,
            'student_code': enrolment.student.student_id,
            'enrolment': enrolment.pk,
            'name': enrolment.student.name,
            'name_bn': enrolment.student.name_bn,
            'roll': enrolment.roll,
            'status': row.status if row else AttendanceStatus.PRESENT,
            'remarks': row.remarks if row else '',
            'taken_by': row.taken_by_id if row else None,
            'taken_at': row.taken_at.isoformat() if row else None,
            'is_taken': row is not None,
        })

    return {
        'date': on_date.isoformat(),
        'class': academic_class.pk,
        'section': section.pk if section is not None else None,
        'period': period.pk,
        'student_count': len(students),
        'students': students,
        **is_markable(branch, on_date, period, user=user, now=now).as_dict(),
    }


def resolve_period(branch, pk):
    """A `Period` of this institution, or None — 404 is the view's to raise."""
    return Period.objects.for_branch(branch).filter(pk=pk).first()


__all__ = [
    'MARKABLE', 'Markability', 'WEEKDAY_CODES',
    'attendance_summary', 'is_markable', 'month_days', 'month_register',
    'parse_month', 'period_roster', 'register_enrolments', 'resolve_period',
    'save_class_attendance', 'save_register', 'student_count', 'teacher_today',
    'STATE_LIVE', 'STATE_MISSED', 'STATE_TAKEN', 'STATE_UPCOMING',
    'REASON_FUTURE', 'REASON_NOT_ENROLLED', 'REASON_OUTSIDE_MONTH',
    'REASON_UNKNOWN_STUDENT', 'REASON_WEEKLY_OFF', 'REASON_WINDOW_CLOSED',
]
