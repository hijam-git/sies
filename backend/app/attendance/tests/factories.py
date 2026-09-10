"""A small, fast fixture for this module (CLAUDE.md §4a).

One institution, one session, one class with a section, three students, one
teacher, two periods and a routine row. Enough to exercise every path attendance
has — the register, the window, the scope, the board — and small enough to build
in milliseconds. Nothing here loads `seed_demo`.

Unlike `academics.tests.factories` this one *does* build students, because it has
to: a register with no students tests nothing. It goes through the real
`enrol_student()` service so the rolls and admission numbers come out the way
production makes them, and so a change to that service surfaces here rather than
in a seeded database three phases later.
"""

import itertools
from datetime import date, time

from academics.models import ClassRoutine, Period
from academics.services import enrol_student
from accounts.models import UserType
from accounts.permissions import VALID_PERMISSIONS
from branches.models import Branch, InstitutionType, Session
from branches.seeding import seed_streams
from django.contrib.auth import get_user_model
from staff.services import create_teacher
from students.models import Student
from students.services import allocate_student_id

# Phones are unique platform-wide, so they come from one counter rather than
# being written out per test — two tests that both wanted 01712345678 would pass
# alone and fail together.
_phones = itertools.count(1)


def next_phone():
    return f'0191{next(_phones):07d}'


def make_branch(code='DHK', name='Dhaka Madrasah', **extra):
    """An institution with its streams — the only seeded rows attendance uses.

    Deliberately **not** `branches.services.create_branch()`, and the reason is
    the one CLAUDE.md §4a gives: `create_branch()` also seeds fee, income and
    expense heads, so a fixture built on it would make every test in this module
    depend on the `fees` app being finished and installed. Attendance touches no
    fee category, and a module whose tests cannot run until another phase lands
    is the coupling that section tells us to fix rather than to widen the fixture
    around.

    `seed_streams()` is called explicitly because a `Stream` is genuinely
    required — `AcademicClass.stream` is not nullable — and it is the same
    function `create_branch()` calls, so the rows are the production ones.
    """
    branch = Branch.objects.create(
        name=name, name_bn='ঢাকা মাদ্রাসা', code=code,
        institution_type=extra.pop('institution_type', InstitutionType.MADRASAH),
        **extra,
    )
    seed_streams(branch)
    return branch


def first_stream(branch):
    return branch.stream_set.order_by('order', 'id').first()


def make_session(branch, name='2026'):
    session = Session.objects.create(
        branch=branch, name=name,
        starts_on=date(2026, 1, 1), ends_on=date(2026, 12, 31),
        is_current=True,
    )
    session.streams.set(branch.stream_set.all())
    return session


def make_user(branch, phone=None, user_type=UserType.PRINCIPAL, **extra):
    """An account holding every permission in the catalogue, unless told otherwise.

    Full permissions by default so that a refusal in these tests proves the
    *branch*, the *scope* or the *window* refused it, and not that the account
    happened to lack `attendance.take`. A test about permissions passes its own
    list.
    """
    User = get_user_model()
    return User.objects.create_user(
        phone=phone or next_phone(),
        password='correct-horse-9',
        name=extra.pop('name', 'Test User'),
        branch=branch,
        user_type=user_type,
        permissions=extra.pop('permissions', sorted(VALID_PERMISSIONS)),
        **extra,
    )


def make_teacher(branch, name='Abdul Karim', user=None):
    return create_teacher(branch=branch, name=name, user=user)


def make_class(branch, session, name='Class 5', level_order=5, **extra):
    from academics.models import AcademicClass

    return AcademicClass.objects.create(
        branch=branch, session=session, stream=first_stream(branch),
        name=name, year=session.starts_on.year, level_order=level_order,
        **extra,
    )


def make_section(academic_class, name='A', **extra):
    from academics.models import Section

    return Section.objects.create(
        branch=academic_class.branch, academic_class=academic_class,
        name=name, **extra,
    )


def make_subject(academic_class, name='Arabic', **extra):
    from academics.models import Subject

    return Subject.objects.create(
        branch=academic_class.branch, stream=academic_class.stream,
        academic_class=academic_class, name=name, **extra,
    )


def make_student(branch, name='Abdullah', **extra):
    extra.setdefault('stream', first_stream(branch))
    extra.setdefault('admitted_on', date(2026, 1, 5))
    return Student.objects.create(
        branch=branch, student_id=allocate_student_id(), name=name, **extra,
    )


def enrol(student, *, session, academic_class, section=None, roll=None):
    return enrol_student(
        branch=student.branch, student=student, session=session,
        academic_class=academic_class, section=section, roll=roll,
        enrolled_on=date(2026, 1, 5),
    )


def make_students(branch, session, academic_class, section=None, count=3):
    """*count* students, enrolled, in roll order. Returns the enrolments."""
    names = ['Abdullah Rahman', 'Bilal Hossain', 'Umar Faruk',
             'Yusuf Ali', 'Zayd Khan']
    return [
        enrol(make_student(branch, name=names[i % len(names)]),
              session=session, academic_class=academic_class, section=section)
        for i in range(count)
    ]


def make_period(branch, order=1, stream=None, start=None, end=None, **extra):
    return Period.objects.create(
        branch=branch, stream=stream, order=order,
        name=extra.pop('name', f'{order} Period'),
        start_time=start or time(8 + order, 0),
        end_time=end or time(8 + order, 45),
        **extra,
    )


def make_routine(*, session, academic_class, subject, teacher, period,
                 section=None, day_of_week=0, **extra):
    return ClassRoutine.objects.create(
        branch=academic_class.branch, session=session,
        academic_class=academic_class, section=section, subject=subject,
        teacher=teacher, period=period, day_of_week=day_of_week, **extra,
    )
