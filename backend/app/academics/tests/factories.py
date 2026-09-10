"""A small, fast fixture for this module (CLAUDE.md §4a).

One or two institutions, a session, a class with two sections, a subject, a
period and a teacher. Enough to exercise the routine constraints and the teacher
scope; small enough to build in milliseconds. No `seed_demo`.

Nothing here builds a `Student`: the `students` app is written in parallel, and a
fixture that needed it would make this module's tests unrunnable until it lands.
Enrolment numbering is therefore tested at `services.next_admission_number()`,
where the guarantee actually is.
"""

from datetime import date, time

from django.contrib.auth import get_user_model

from accounts.permissions import VALID_PERMISSIONS
from branches.models import InstitutionType, Session
from branches.services import create_branch
from staff.services import create_teacher

from academics.models import (AcademicClass, ClassRoutine, Period, Section,
                              Subject, SubjectAssignment)


def make_branch(code='DHK', name='Dhaka Madrasah', **extra):
    return create_branch(
        name=name, name_bn='ঢাকা মাদ্রাসা', code=code,
        institution_type=extra.pop('institution_type', InstitutionType.MADRASAH),
        **extra,
    )


def make_session(branch, name='2026', starts_on=None, ends_on=None):
    session = Session.objects.create(
        branch=branch, name=name,
        starts_on=starts_on or date(2026, 1, 1),
        ends_on=ends_on or date(2026, 12, 31),
    )
    session.streams.set(branch.stream_set.all())
    return session


def make_user(branch, phone='01711000001', user_type='principal', **extra):
    """An account holding every permission in the catalogue, unless told otherwise.

    Full permissions by default so that a refusal in these tests proves the
    *branch* or the *scope* refused it, and not that the account happened to lack
    `academics.view`. A test about permissions passes its own list.
    """
    User = get_user_model()
    return User.objects.create_user(
        phone=phone, password='pass-phrase-1234',
        name=extra.pop('name', f'User {phone}'),
        branch=branch, user_type=user_type,
        permissions=extra.pop('permissions', sorted(VALID_PERMISSIONS)),
        **extra,
    )


def make_teacher(branch, name='Abdul Karim', user=None):
    return create_teacher(branch=branch, name=name, user=user)


def make_class(branch, session, name='Class 5', stream=None, **extra):
    return AcademicClass.objects.create(
        branch=branch, session=session,
        stream=stream or branch.stream_set.first(),
        name=name, **extra,
    )


def make_section(academic_class, name='A', **extra):
    return Section.objects.create(
        branch=academic_class.branch, academic_class=academic_class,
        name=name, **extra,
    )


def make_subject(academic_class, name='Arabic', **extra):
    return Subject.objects.create(
        branch=academic_class.branch,
        stream=academic_class.stream,
        academic_class=academic_class,
        name=name, **extra,
    )


def make_period(branch, order=1, stream=None, **extra):
    return Period.objects.create(
        branch=branch, stream=stream, order=order,
        name=extra.pop('name', f'Period {order}'),
        start_time=extra.pop('start_time', time(9 + order, 0)),
        end_time=extra.pop('end_time', time(9 + order, 45)),
        **extra,
    )


def make_routine(*, session, academic_class, subject, teacher, period,
                 section=None, day_of_week=0, **extra):
    return ClassRoutine.objects.create(
        branch=academic_class.branch, session=session,
        academic_class=academic_class, section=section, subject=subject,
        teacher=teacher, period=period, day_of_week=day_of_week, **extra,
    )


def make_assignment(*, session, teacher, subject, academic_class, section=None):
    return SubjectAssignment.objects.create(
        branch=academic_class.branch, session=session, teacher=teacher,
        subject=subject, academic_class=academic_class, section=section,
    )
