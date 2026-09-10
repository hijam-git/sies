"""A small, fast fixture for the forms module (CLAUDE.md §4a).

One institution with its seeded admission template, one applicant, and the
helpers to give that applicant a Student record when a test needs one. No
`seed_demo`.
"""

from datetime import date

from django.contrib.auth import get_user_model

from academics.models import AcademicClass
from branches.models import InstitutionType, Session
from branches.services import create_branch
from students.models import Admission, Student
from students.services import allocate_student_id

from forms.models import FormTemplate, Question
from forms.seeding import seed_form_templates


def make_branch(code='DHK', name='Dhaka Madrasah', **extra):
    branch = create_branch(
        name=name, name_bn='ঢাকা মাদ্রাসা', code=code,
        name_ar='مركز التعليم الاسلامي',
        established_year=1985,
        address_bn='দাশেরবাড়ি, ঢাকা',
        institution_type=extra.pop('institution_type', InstitutionType.MADRASAH),
        **extra,
    )
    # Called explicitly, exactly as `branches.services.create_branch()` will
    # call it once the one-line hook lands there (see `forms/seeding.py`).
    seed_form_templates(branch)
    return branch


def make_session(branch, name='2026'):
    session = Session.objects.create(
        branch=branch, name=name,
        starts_on=date(2026, 1, 1), ends_on=date(2026, 12, 31),
    )
    session.streams.set(branch.stream_set.all())
    return session


def make_user(branch, phone='01711000001', user_type='principal', permissions=None,
              **extra):
    from accounts.permissions import VALID_PERMISSIONS

    User = get_user_model()
    return User.objects.create_user(
        phone=phone, password='pass-phrase-1234',
        name=extra.pop('name', f'User {phone}'),
        branch=branch, user_type=user_type,
        permissions=sorted(VALID_PERMISSIONS) if permissions is None else permissions,
        **extra,
    )


def make_class(branch, session, name='Class 5'):
    return AcademicClass.objects.create(
        branch=branch, session=session, stream=branch.stream_set.first(),
        name=name, name_bn='পঞ্চম শ্রেণি',
    )


def make_student(branch, name='Rahim Uddin', **extra):
    return Student.objects.create(
        branch=branch, stream=branch.stream_set.first(), name=name,
        name_bn=extra.pop('name_bn', 'রহিম উদ্দিন'),
        student_id=allocate_student_id(), **extra,
    )


def make_admission(branch, session, academic_class, **extra):
    return Admission.objects.create(
        branch=branch, session=session, stream=branch.stream_set.first(),
        academic_class=academic_class,
        application_no=extra.pop('application_no', 'APP-0001'),
        applicant_name=extra.pop('applicant_name', 'Rahim Uddin'),
        applicant_name_bn=extra.pop('applicant_name_bn', 'রহিম উদ্দিন'),
        guardian_name=extra.pop('guardian_name', 'আব্দুল করিম'),
        guardian_phone=extra.pop('guardian_phone', '01712345678'),
        village=extra.pop('village', 'দাশেরবাড়ি'),
        **extra,
    )


def admission_template(branch):
    return FormTemplate.objects.get(branch=branch, form_type='admission')


def make_question(branch, **extra):
    return Question.objects.create(
        branch=branch,
        section=extra.pop('section', 'admission'),
        text=extra.pop('text', 'Any medical condition?'),
        text_bn=extra.pop('text_bn', 'কোনো শারীরিক সমস্যা আছে কি'),
        type=extra.pop('type', 'short_text'),
        **extra,
    )


def small_world(code='DHK', phone='01711000001'):
    branch = make_branch(code=code, name=f'{code} Madrasah')
    session = make_session(branch)
    academic_class = make_class(branch, session)
    admission = make_admission(branch, session, academic_class,
                               application_no=f'APP-{code}-0001')
    return {
        'branch': branch, 'session': session, 'class': academic_class,
        'admission': admission,
        'template': admission_template(branch),
        'user': make_user(branch, phone=phone),
    }
