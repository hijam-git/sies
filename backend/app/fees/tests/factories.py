"""A small, fast fixture for fees and finance (CLAUDE.md §4a).

One institution, one session, one class, three students — enough to exercise
every path money takes through this module, small enough to build in
milliseconds. No `seed_demo`: a shared demo dataset that tests depend on becomes
a thing nobody dares change.

`make_branch()` goes through `branches.services.create_branch()` rather than
`Branch.objects.create()`, so every fixture gets the real seeded fee, income and
expense categories. That is deliberate — the seeding is half of what these tests
are checking, and a fixture that hand-built three categories would prove the
tests' own fixture correct rather than the system.
"""

import itertools
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model

from accounts.permissions import VALID_PERMISSIONS
from branches.models import InstitutionType, Session
from branches.services import create_branch

_phone_counter = itertools.count(1)


def next_phone():
    """Phones are unique platform-wide, so they come from one counter.

    Two tests that both wrote 01712345678 would pass alone and fail together.
    """
    return f'0182{next(_phone_counter):07d}'


def make_branch(code='DHK', name='Dhaka Madrasah', **extra):
    """A seeded institution, created the way production creates one."""
    return create_branch(
        name=name, name_bn='ঢাকা মাদ্রাসা', code=code,
        institution_type=extra.pop('institution_type', InstitutionType.MADRASAH),
        **extra,
    )


def first_stream(branch):
    return branch.stream_set.order_by('order', 'id').first()


def make_session(branch, name='2026', is_current=True, year=None):
    """Dates derived from the name, because `academics` numbers admissions by
    `session.starts_on.year` — two sessions sharing a start year would collide
    on `ADM-DHK-<year>-00001`."""
    year = year or (int(name) if name.isdigit() else 2026)
    session = Session.objects.create(
        branch=branch, name=name,
        starts_on=date(year, 1, 1), ends_on=date(year, 12, 31),
        is_current=is_current,
    )
    session.streams.set(branch.stream_set.all())
    return session


def make_user(branch, phone=None, user_type='principal', **extra):
    """An account holding every permission, unless a test says otherwise.

    Full permissions by default so that a refusal proves the *branch scope*
    refused it, and not that the account happened to lack `fees.view`.
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


def make_class(branch, session, name='Class 5', monthly_fee='500.00', **extra):
    from academics.models import AcademicClass

    return AcademicClass.objects.create(
        branch=branch,
        stream=extra.pop('stream', first_stream(branch)),
        session=session,
        name=name,
        year=session.starts_on.year,
        monthly_fee=Decimal(monthly_fee),
        **extra,
    )


def make_student(branch, name='Abdullah', **extra):
    """Explicitly atomic, because `TransactionTestCase` runs in autocommit.

    `allocate_student_id()` takes a row lock and Django refuses
    `select_for_update` outside a transaction. Under `TestCase` the wrapping
    transaction hides that; the concurrency tests have no such wrapper, and a
    fixture that only worked under one of the two would be a trap.
    """
    from django.db import transaction

    from students.models import Student
    from students.services import allocate_student_id

    extra.setdefault('stream', first_stream(branch))
    extra.setdefault('admitted_on', date(2026, 1, 5))
    with transaction.atomic():
        return Student.objects.create(
            branch=branch, student_id=allocate_student_id(), name=name, **extra,
        )


def make_enrolment(branch, session, academic_class, student=None,
                   is_hostel=False, is_transport=False):
    """Through `academics.services`, which owns the roll and admission number."""
    from academics.services import enrol_student

    student = student or make_student(branch)
    return enrol_student(
        branch=branch, student=student, session=session,
        academic_class=academic_class, enrolled_on=date(2026, 1, 5),
        is_hostel=is_hostel, is_transport=is_transport,
    )


def category(branch, code):
    """A seeded fee category by code — 'MON', 'ADM', 'HOS', 'TRN'."""
    from fees.models import FeeCategory

    return FeeCategory.objects.get(branch=branch, code=code)


def make_fee(branch, session, student=None, code='MON', amount='500.00',
             period='2026-03', due_date=None, discount='0.00',
             enrolment=None, actor=None):
    """One invoice, raised through the service so numbering is real."""
    from fees.services import raise_fee

    fee, _created = raise_fee(
        branch=branch,
        student=student or (enrolment.student if enrolment else make_student(branch)),
        enrolment=enrolment,
        category=category(branch, code),
        session=session,
        amount=Decimal(amount),
        discount=Decimal(discount),
        period=period,
        due_date=due_date or date(2026, 3, 10),
        actor=actor,
    )
    return fee


class FeeFixture:
    """The setUp most tests in this package want, in one place.

    A mixin rather than a base TestCase so `TransactionTestCase` (the
    concurrency test) can use exactly the same fixture without inheriting
    `TestCase`'s wrapping transaction — which would deadlock threads against
    each other rather than testing them.
    """

    def build_fixture(self):
        self.branch = make_branch()
        self.session = make_session(self.branch)
        self.academic_class = make_class(self.branch, self.session)
        self.user = make_user(self.branch)
        self.enrolment = make_enrolment(self.branch, self.session,
                                        self.academic_class)
        self.student = self.enrolment.student
