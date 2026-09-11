"""A small, fast fixture for the exams module (CLAUDE.md §4a).

One institution, one session, one class, two subjects, two students and a
teacher — enough to exercise the unique constraint, the subject scope and the
publish gate, small enough to build in milliseconds. A second institution is
built only by the branch-isolation test, which is the one thing that needs it.

Nothing here calls `seed_demo`: a shared demo dataset that tests depend on
becomes a thing nobody dares change.
"""

from datetime import date, time
from decimal import Decimal

from django.contrib.auth import get_user_model

from academics.models import AcademicClass, Enrolment, Subject, SubjectAssignment
from branches.models import InstitutionType, Session
from branches.services import create_branch
from staff.services import create_teacher
from students.models import Student
from students.services import allocate_student_id

from exams.models import Exam, ExamSchedule, ExamType


def make_branch(code='DHK', name='Dhaka Madrasah', **extra):
    return create_branch(
        name=name, name_bn='ঢাকা মাদ্রাসা', code=code,
        institution_type=extra.pop('institution_type', InstitutionType.MADRASAH),
        **extra,
    )


def make_session(branch, name='2026'):
    session = Session.objects.create(
        branch=branch, name=name,
        starts_on=date(2026, 1, 1), ends_on=date(2026, 12, 31),
    )
    session.streams.set(branch.stream_set.all())
    return session


def make_user(branch, phone='01711000001', user_type='principal', permissions=None,
              **extra):
    """An account holding every permission unless a test names its own.

    Full permissions by default so a refusal proves the *scope* refused it and
    not that the account happened to lack `marks.enter`.
    """
    from accounts.permissions import VALID_PERMISSIONS

    User = get_user_model()
    return User.objects.create_user(
        phone=phone, password='pass-phrase-1234',
        name=extra.pop('name', f'User {phone}'),
        branch=branch, user_type=user_type,
        permissions=sorted(VALID_PERMISSIONS) if permissions is None else permissions,
        **extra,
    )


def make_teacher(branch, name='Abdul Karim', user=None):
    return create_teacher(branch=branch, name=name, user=user)


def make_class(branch, session, name='Class 5', **extra):
    return AcademicClass.objects.create(
        branch=branch, session=session, stream=branch.stream_set.first(),
        name=name, **extra,
    )


def make_subject(academic_class, name='Arabic', **extra):
    return Subject.objects.create(
        branch=academic_class.branch, stream=academic_class.stream,
        academic_class=academic_class, name=name, **extra,
    )


def make_student(branch, name='Rahim Uddin', **extra):
    # `student_id` comes from the platform-wide counter, not from a literal: it
    # is globally unique, so two fixtures inventing 'S-1' would collide the
    # moment a test builds a second institution.
    return Student.objects.create(
        branch=branch, stream=branch.stream_set.first(), name=name,
        student_id=allocate_student_id(), **extra,
    )


def make_enrolment(*, student, session, academic_class, roll=1, **extra):
    return Enrolment.objects.create(
        branch=academic_class.branch, student=student, session=session,
        academic_class=academic_class, roll=roll,
        admission_number=extra.pop('admission_number', f'ADM-{roll:04d}'),
        enrolled_on=extra.pop('enrolled_on', date(2026, 1, 5)),
        **extra,
    )


def make_assignment(*, session, teacher, subject, academic_class):
    return SubjectAssignment.objects.create(
        branch=academic_class.branch, session=session, teacher=teacher,
        subject=subject, academic_class=academic_class,
    )


def make_exam(branch, session, name='Half-Yearly 2026', **extra):
    return Exam.objects.create(
        branch=branch, session=session,
        stream=extra.pop('stream', None) or branch.stream_set.first(),
        name=name, exam_type=extra.pop('exam_type', ExamType.HALF_YEARLY),
        starts_on=extra.pop('starts_on', date(2026, 6, 1)),
        ends_on=extra.pop('ends_on', date(2026, 6, 10)),
        **extra,
    )


def make_schedule(*, exam, academic_class, subject, full_marks='100.00',
                  pass_marks='33.00', **extra):
    return ExamSchedule.objects.create(
        branch=exam.branch, exam=exam, academic_class=academic_class,
        subject=subject,
        date=extra.pop('date', date(2026, 6, 2)),
        start_time=extra.pop('start_time', time(9, 0)),
        end_time=extra.pop('end_time', time(12, 0)),
        full_marks=Decimal(full_marks), pass_marks=Decimal(pass_marks),
        **extra,
    )


def small_world(code='DHK', phone='01711000001'):
    """The whole fixture in one call, as a dict of what a test needs."""
    branch = make_branch(code=code, name=f'{code} Madrasah')
    session = make_session(branch)
    academic_class = make_class(branch, session)
    arabic = make_subject(academic_class, name='Arabic')
    fiqh = make_subject(academic_class, name='Fiqh')

    students = [make_student(branch, name=f'Student {n}') for n in (1, 2)]
    enrolments = [
        make_enrolment(student=student, session=session,
                       academic_class=academic_class, roll=index,
                       admission_number=f'{code}-{index:04d}')
        for index, student in enumerate(students, start=1)
    ]

    # The general stream, so the fixture grades by board GPA — the method most
    # assertions here are written in. The Qawmi method has its own tests.
    exam = make_exam(branch, session, stream=branch.stream_set.get(code='general'))
    make_schedule(exam=exam, academic_class=academic_class, subject=arabic)
    make_schedule(exam=exam, academic_class=academic_class, subject=fiqh,
                  date=date(2026, 6, 3))

    return {
        'branch': branch, 'session': session, 'class': academic_class,
        'arabic': arabic, 'fiqh': fiqh, 'students': students,
        'enrolments': enrolments, 'exam': exam,
        'principal': make_user(branch, phone=phone, user_type='principal'),
    }
