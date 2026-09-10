"""A small, fast fixture for this module (CLAUDE.md §4a).

One or two institutions, a session, a class and a handful of people — enough to
exercise every path in `students`, small enough to build in milliseconds. No
test in this package loads `seed_demo`.

The enrolment stubs below are the important part. `admit_student()` calls
`academics`' service for the roll and the admission number, and that is exactly
right — but it means a test of *this* module's transaction would otherwise
depend on another module's numbering being correct first. The stubs pin the
boundary through `SIES_ENROLMENT_SERVICE`, the same settings-named-callable
pattern `core.permissions` uses for its resolver (docs/WORKLOG F19).
"""

import itertools
from datetime import date
from types import SimpleNamespace

from accounts.models import User, UserType
from branches.models import Session
from branches.services import create_branch
from students.models import (Admission, AdmissionStatus, Guardian, Student,
                             StudentGuardian)
from students.services import allocate_student_id

# Phones are unique platform-wide, so they come from one counter rather than
# being written out per test — two tests that both wanted 01712345678 would pass
# alone and fail together.
_phone_counter = itertools.count(1)


def next_phone():
    return f'0181{next(_phone_counter):07d}'


def make_branch(code='DHK', name='Dhaka Madrasah', **extra):
    """A seeded institution, created the way production creates one."""
    return create_branch(name=name, name_bn='ঢাকা মাদ্রাসা', code=code, **extra)


def first_stream(branch):
    """The branch's first seeded stream — `hifz` for a madrasah."""
    return branch.stream_set.order_by('order', 'id').first()


def make_session(branch, name='2026'):
    session = Session.objects.create(
        branch=branch, name=name,
        starts_on=date(2026, 1, 1), ends_on=date(2026, 12, 31),
        is_current=True,
    )
    session.streams.set(branch.stream_set.all())
    return session


def make_class(branch, session, name='Class 1', level_order=1):
    """An `academics.AcademicClass`, built from the fields docs/03 §3 requires.

    Imported inside the function: `academics` is built alongside this app, and a
    module-level import would make every test here fail to collect while that
    app is still landing.
    """
    from academics.models import AcademicClass

    return AcademicClass.objects.create(
        branch=branch,
        stream=first_stream(branch),
        session=session,
        name=name,
        year=session.starts_on.year,
        level_order=level_order,
    )


def make_user(branch=None, phone=None, user_type=None, **extra):
    extra.setdefault('name', 'Test User')
    if user_type is None:
        user_type = UserType.PLATFORM_ADMIN if branch is None else UserType.PRINCIPAL
    return User.objects.create_user(
        phone=phone or next_phone(),
        password='correct-horse-9',
        branch=branch,
        user_type=user_type,
        **extra,
    )


def make_student(branch, name='Abdullah', **extra):
    """A student written directly — the paper roll typed in, not an admission."""
    extra.setdefault('stream', first_stream(branch))
    extra.setdefault('admitted_on', date(2026, 1, 5))
    return Student.objects.create(
        branch=branch, student_id=allocate_student_id(), name=name, **extra,
    )


def make_guardian(branch, name='Golam Rasul', phone=None, **extra):
    return Guardian.objects.create(
        branch=branch, name=name, phone=phone or next_phone(), **extra,
    )


def link(student, guardian, is_primary=True):
    return StudentGuardian.objects.create(
        branch=student.branch, student=student, guardian=guardian,
        is_primary=is_primary,
    )


def make_application(branch, session, academic_class, applicant_name='Yusuf',
                     guardian_name='Golam Rasul', guardian_phone=None, **extra):
    """An application with its number allocated the way the service does it."""
    from students.services import allocate_application_no

    return Admission.objects.create(
        branch=branch,
        session=session,
        stream=extra.pop('stream', first_stream(branch)),
        academic_class=academic_class,
        application_no=extra.pop('application_no',
                                 allocate_application_no(branch, session)),
        applicant_name=applicant_name,
        guardian_name=guardian_name,
        guardian_phone=guardian_phone or next_phone(),
        status=extra.pop('status', AdmissionStatus.ACCEPTED),
        **extra,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Enrolment stubs — the `academics` boundary
# ─────────────────────────────────────────────────────────────────────────────

#: Every call the stub received, so a test can assert that re-admission asked
#: for a second enrolment rather than a second student.
enrolment_calls = []


def stub_enrolment(*, student, session, academic_class, enrolled_on=None,
                   section=None, roll=None, branch=None, is_hostel=False,
                   is_transport=False, created_by=None):
    """Stands in for `academics.services.enrol_student`.

    Returns a plain object rather than an Enrolment row: this module's tests are
    about the transaction and the student, and building a real Enrolment would
    drag Section, roll allocation and the admission-number series into a fixture
    that is supposed to stay small.
    """
    enrolment_calls.append({'student': student, 'session': session,
                            'academic_class': academic_class, 'section': section,
                            'roll': roll})
    return SimpleNamespace(
        pk=len(enrolment_calls),
        student=student,
        session=session,
        academic_class=academic_class,
        roll=roll or len(enrolment_calls),
        admission_number=f'ADM-{student.branch.code}-{session.name}-'
                         f'{len(enrolment_calls):05d}',
    )


def failing_enrolment(**kwargs):
    """Fails where the real service would fail — after the Student was written.

    This is the shape of the outage that matters: the person exists, the roll
    allocation blows up, and everything before it has to disappear.
    """
    raise RuntimeError('academics is down')


def reset_enrolment_calls():
    enrolment_calls.clear()
