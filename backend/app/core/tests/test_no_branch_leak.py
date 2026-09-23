"""Nothing of one institution reaches another. Proved by asking, not by reading.

`test_scoping_contract` reads the SQL each endpoint builds. This one builds a
second institution full of real rows — students, guardians, invoices, receipts,
marks, attendance, SMS — signs in as the FIRST institution's principal, and
walks **every routed endpoint**:

* every list must come back without a single one of the other institution's
  rows; and
* every detail of one of their rows must be **404 — never 403**, because 403
  confirms the row exists, which is what a probe is looking for (CLAUDE.md §5).
  A POST-only action is POSTed to rather than GETed, because a 405 to a GET
  proves nothing about `collect`, `publish` or `send-results-sms` — and those
  are the ones where a leak would cost money or release somebody's results.

The sweep is generated from the URL resolver, so an endpoint added next month
is covered the day it is routed rather than the day somebody remembers to write
a test for it. That is the whole point: this is the test that catches the
screen nobody thought to check.
"""

import re
from datetime import date, time
from decimal import Decimal

from django.test import TestCase
from django.urls import get_resolver
from rest_framework.test import APIClient

from accounts.permissions import VALID_PERMISSIONS

PK = re.compile(r'\(\?P<pk>[^)]+\)')
#: The router's own patterns arrive as regexes — `api/^fees/(?P<pk>[^/.]+)/$`
#: — and the format suffix routes (`fees\.(?P<format>…)`) are the same endpoint
#: twice. This turns one into a URL, or into None when it is not worth calling.
SUFFIX = re.compile(r'\\?\.\(\?P<format>[^)]+\)/\?')


def to_url(route, pk=None):
    if SUFFIX.search(route):
        return None                      # the .json twin of a route already swept
    url = route.replace('^', '').replace('$', '')
    if '(?P<pk>' in url:
        if pk is None:
            return None
        url = PK.sub(str(pk), url)
    elif '(?P<' in url or '<' in url:
        return None                      # takes some other id this sweep cannot invent
    return '/' + url


def routes():
    """`(name, cls, url_pattern)` for everything mounted under /api/."""
    def walk(patterns, prefix=''):
        for pattern in patterns:
            if hasattr(pattern, 'url_patterns'):
                yield from walk(pattern.url_patterns, prefix + str(pattern.pattern))
            else:
                yield prefix + str(pattern.pattern), pattern.callback

    for route, callback in walk(get_resolver().url_patterns):
        cls = getattr(callback, 'cls', None) or getattr(callback, 'view_class', None)
        if cls is not None and route.startswith('api/'):
            yield route, cls


def build_institution(code, phone_seed):
    """A whole institution with a row in every table a screen can reach."""
    from academics.models import Subject
    from academics.services import enrol_student
    from attendance.models import AttendanceStatus, DailyAttendance, PersonType
    from branches.models import Session
    from branches.services import create_branch
    from django.utils import timezone
    from exams.models import Exam, ExamSchedule, ExamType
    from exams.services import publish_exam, save_marks
    from fees.models import FeeCategory
    from fees.services import collect_fee, raise_fee
    from notifications.models import NotificationEvent, SmsMessage
    from staff.services import create_teacher
    from students.models import Guardian, Student, StudentGuardian
    from students.services import allocate_student_id

    branch = create_branch(name=f'{code} Institution', name_bn=f'{code} প্রতিষ্ঠান',
                           code=code)
    session = Session.objects.create(branch=branch, name='2026',
                                     starts_on=date(2026, 1, 1),
                                     ends_on=date(2026, 12, 31), is_current=True)
    session.streams.set(branch.stream_set.all())
    stream = branch.stream_set.first()

    from academics.models import AcademicClass, Section
    academic_class = AcademicClass.objects.create(
        branch=branch, session=session, stream=stream, name='Class 5',
        year=2026, monthly_fee=Decimal('500.00'),
    )
    Section.objects.create(branch=branch, academic_class=academic_class, name='A')
    subject = Subject.objects.create(branch=branch, stream=stream,
                                     academic_class=academic_class, name='Arabic')

    teacher = create_teacher(branch=branch, name=f'{code} Teacher')

    student = Student.objects.create(branch=branch, stream=stream,
                                     student_id=allocate_student_id(),
                                     name=f'{code} Student',
                                     admitted_on=date(2026, 1, 5))
    guardian = Guardian.objects.create(branch=branch, name=f'{code} Father',
                                       phone=f'0171{phone_seed}0001', relation='father')
    StudentGuardian.objects.create(branch=branch, student=student,
                                   guardian=guardian, is_primary=True)
    enrolment = enrol_student(branch=branch, student=student, session=session,
                              academic_class=academic_class,
                              enrolled_on=date(2026, 1, 5))

    fee, _ = raise_fee(branch=branch, student=student,
                       category=FeeCategory.objects.get(branch=branch, code='MON'),
                       session=session, amount=Decimal('500.00'), period='2026-03',
                       enrolment=enrolment, due_date=date(2026, 3, 10))
    collect_fee(fee=fee, amount=Decimal('100.00'))

    exam = Exam.objects.create(branch=branch, session=session, stream=stream,
                               name=f'{code} Half-Yearly', exam_type=ExamType.HALF_YEARLY,
                               starts_on=date(2026, 6, 1), ends_on=date(2026, 6, 10))
    ExamSchedule.objects.create(branch=branch, exam=exam, academic_class=academic_class,
                                subject=subject, date=date(2026, 6, 2),
                                start_time=time(9, 0), end_time=time(12, 0),
                                full_marks=Decimal('100.00'), pass_marks=Decimal('33.00'))
    save_marks(exam=exam, subject=subject,
               rows=[{'enrolment': enrolment.pk, 'obtained': '80'}])
    publish_exam(exam)

    DailyAttendance.objects.create(branch=branch, person_type=PersonType.STUDENT,
                                   student=student, enrolment=enrolment,
                                   date=date(2026, 3, 3), status=AttendanceStatus.PRESENT,
                                   taken_at=timezone.now())
    SmsMessage.objects.create(branch=branch, event=NotificationEvent.RESULT_PUBLISHED,
                              to_phone=f'0171{phone_seed}0001', body='theirs',
                              status='sent')
    return {'branch': branch, 'session': session, 'class': academic_class,
            'student': student, 'teacher': teacher, 'exam': exam, 'fee': fee}


class NothingLeaksTests(TestCase):
    """One institution's principal, let loose on another institution's ids."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model

        cls.mine = build_institution('AAA', '99')
        cls.theirs = build_institution('BBB', '98')

        User = get_user_model()
        cls.principal = User.objects.create_user(
            phone='01799000011', password='pass-phrase-1234', name='A Principal',
            branch=cls.mine['branch'], user_type='principal',
            # Every permission there is, so a refusal below proves the BRANCH
            # refused it and not that the account lacked a checkbox.
            permissions=sorted(VALID_PERMISSIONS),
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.principal)

    def their_rows(self, model):
        if not any(f.name == 'branch' for f in model._meta.fields):
            return set()
        return set(model.objects.filter(branch=self.theirs['branch'])
                   .values_list('pk', flat=True))

    def test_no_list_returns_another_institutions_rows(self):
        checked, leaks = 0, []
        for route, cls in routes():
            url = to_url(route)
            if url is None:
                continue
            model = getattr(getattr(cls, 'queryset', None), 'model', None)
            if model is None:
                continue
            theirs = self.their_rows(model)
            if not theirs:
                continue

            response = self.client.get(url)
            if response.status_code != 200:
                continue
            body = response.data
            rows = body.get('results', body) if isinstance(body, dict) else body
            if not isinstance(rows, list):
                continue

            checked += 1
            seen = {row.get('id') for row in rows if isinstance(row, dict)}
            if seen & theirs:
                leaks.append(f'{cls.__name__} ({url}) returned {seen & theirs}')

        self.assertEqual(leaks, [], 'Another institution’s rows came back: '
                                    + '; '.join(leaks))
        # The sweep has to have swept something.
        self.assertGreaterEqual(checked, 15, f'only {checked} list endpoints covered')

    def test_every_detail_of_their_row_is_404_never_403(self):
        checked, wrong = 0, []
        for route, cls in routes():
            if '?P<pk>' not in route:
                continue
            model = getattr(getattr(cls, 'queryset', None), 'model', None)
            if model is None:
                continue
            theirs = sorted(self.their_rows(model))
            if not theirs:
                continue

            url = to_url(route, pk=theirs[0])
            if url is None:
                continue

            response = self.client.get(url)
            if response.status_code == 405:
                # A POST-only action — `collect`, `publish`, `send-results-sms`.
                # A 405 to a GET proves nothing about them, and they are the
                # endpoints where a leak would actually cost something: money
                # taken against another institution's invoice, results released
                # on their exam. So they are asked the way they are meant to be.
                response = self.client.post(url, {}, format='json')

            checked += 1
            if response.status_code != 404:
                wrong.append(f'{cls.__name__} {url} → {response.status_code}')

        self.assertEqual(wrong, [],
                         'A wrong-branch row must answer 404, never 403 or 200: '
                         + '; '.join(wrong))
        self.assertGreaterEqual(checked, 15, f'only {checked} detail endpoints covered')
