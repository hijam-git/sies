"""The four endpoints, and the two gates every one of them applies.

    can this user take attendance?   → permission:  attendance.take
    for THIS class?                  → assignment:  is it one of theirs? (D6)

Both refusals are **404, not 403** (CLAUDE.md §5). A 403 confirms the class
exists, which is exactly what a probe is looking for — so a wrong-branch class
and an unassigned class must be indistinguishable in the response.

`ROOT_URLCONF` is overridden to this package's own map, because `core/urls.py`
includes the attendance routes in the phase that wires the app in.
"""

from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import UserType
from attendance.models import AttendanceStatus, DailyAttendance

from .factories import (make_branch, make_class, make_section, make_session,
                        make_students, make_subject, make_teacher, make_user)

URLS = 'attendance.tests.urls'


def markable_day(branch):
    """Today, or the most recent day that is not the branch's weekly off day."""
    day = timezone.localdate()
    while day.strftime('%a').lower() in branch.weekly_off_days:
        day -= timedelta(days=1)
    return day


@override_settings(ROOT_URLCONF=URLS)
class RegisterEndpointTests(TestCase):

    def setUp(self):
        self.branch = make_branch()
        self.session = make_session(self.branch)
        self.klass = make_class(self.branch, self.session)
        self.section = make_section(self.klass)
        self.enrolments = make_students(
            self.branch, self.session, self.klass, self.section, count=3,
        )
        self.user = make_user(self.branch)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

        self.day = markable_day(self.branch)
        self.month = f'{self.day.year:04d}-{self.day.month:02d}'

    def test_get_returns_days_and_students(self):
        response = self.client.get('/api/attendance/register/', {
            'class': self.klass.pk, 'section': self.section.pk,
            'month': self.month,
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['students']), 3)
        self.assertIn('is_markable', response.data['days'][0])
        self.assertIn('cells', response.data['students'][0])

    def test_a_missing_month_is_a_400_not_a_500(self):
        response = self.client.get('/api/attendance/register/',
                                   {'class': self.klass.pk})
        self.assertEqual(response.status_code, 400)

    def test_bulk_saves_and_is_idempotent_over_http(self):
        payload = {
            'class': self.klass.pk, 'section': self.section.pk,
            'month': self.month,
            'cells': [{'student': e.student_id, 'date': self.day.isoformat(),
                       'status': AttendanceStatus.PRESENT}
                      for e in self.enrolments],
        }

        first = self.client.post('/api/attendance/register/bulk/', payload,
                                 format='json')
        second = self.client.post('/api/attendance/register/bulk/', payload,
                                  format='json')

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data['saved'], 3)
        self.assertEqual(second.data['saved'], 3)
        self.assertEqual(DailyAttendance.objects.count(), 3)

    def test_bulk_rejects_a_future_date_into_skipped(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        response = self.client.post('/api/attendance/register/bulk/', {
            'class': self.klass.pk, 'month': f'{tomorrow.year:04d}-{tomorrow.month:02d}',
            'cells': [{'student': self.enrolments[0].student_id,
                       'date': tomorrow.isoformat(),
                       'status': AttendanceStatus.PRESENT}],
        }, format='json')

        self.assertEqual(response.data['saved'], 0)
        self.assertEqual(response.data['skipped'][0]['reason'], 'future')
        self.assertFalse(DailyAttendance.objects.exists())

    def test_a_client_supplied_branch_is_ignored(self):
        """CLAUDE.md §1 — `branch` in a POST body does nothing."""
        other = make_branch(code='CTG', name='Chittagong Madrasah')
        self.client.post('/api/attendance/register/bulk/', {
            'class': self.klass.pk, 'branch': other.pk, 'month': self.month,
            'cells': [{'student': self.enrolments[0].student_id,
                       'date': self.day.isoformat(),
                       'status': AttendanceStatus.PRESENT}],
        }, format='json')

        self.assertEqual(DailyAttendance.objects.get().branch_id, self.branch.pk)

    def test_taking_attendance_needs_the_take_permission(self):
        weak = make_user(self.branch, permissions=['attendance.view'])
        self.client.force_authenticate(weak)

        response = self.client.post('/api/attendance/register/bulk/', {
            'class': self.klass.pk, 'month': self.month, 'cells': [],
        }, format='json')

        self.assertEqual(response.status_code, 403)


@override_settings(ROOT_URLCONF=URLS)
class BranchIsolationTests(TestCase):
    """Another institution's class is **404, not 403** (CLAUDE.md §5)."""

    def setUp(self):
        self.dhaka = make_branch(code='DHK')
        self.chittagong = make_branch(code='CTG', name='Chittagong Madrasah')

        self.their_session = make_session(self.chittagong)
        self.their_class = make_class(self.chittagong, self.their_session)
        make_students(self.chittagong, self.their_session, self.their_class, count=2)

        self.user = make_user(self.dhaka)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

        self.day = markable_day(self.dhaka)
        self.month = f'{self.day.year:04d}-{self.day.month:02d}'

    def test_reading_another_branchs_register_is_404(self):
        response = self.client.get('/api/attendance/register/', {
            'class': self.their_class.pk, 'month': self.month,
        })
        self.assertEqual(response.status_code, 404)

    def test_writing_into_another_branch_is_404_and_writes_nothing(self):
        response = self.client.post('/api/attendance/register/bulk/', {
            'class': self.their_class.pk, 'month': self.month,
            'cells': [{'student': 1, 'date': self.day.isoformat(),
                       'status': AttendanceStatus.PRESENT}],
        }, format='json')

        self.assertEqual(response.status_code, 404)
        self.assertFalse(DailyAttendance.objects.exists())


@override_settings(ROOT_URLCONF=URLS)
class TeacherScopeTests(TestCase):
    """docs/08 D6 — a permission answers *what verb*, an assignment *which class*.

    Without the second gate, `attendance.take` lets a teacher mark every class in
    the institution.
    """

    def setUp(self):
        self.branch = make_branch()
        self.session = make_session(self.branch)

        self.mine = make_class(self.branch, self.session, name='Class 5')
        self.not_mine = make_class(self.branch, self.session, name='Class 7',
                                   level_order=7)
        make_students(self.branch, self.session, self.mine, count=2)
        make_students(self.branch, self.session, self.not_mine, count=2)

        self.account = make_user(self.branch, user_type=UserType.TEACHER)
        self.teacher = make_teacher(self.branch, user=self.account)
        # Class teacher of one class only — the "class responsibility" half of
        # the D6 scope.
        self.mine.class_teacher = self.teacher
        self.mine.save(update_fields=['class_teacher'])

        self.client = APIClient()
        self.client.force_authenticate(self.account)

        self.day = markable_day(self.branch)
        self.month = f'{self.day.year:04d}-{self.day.month:02d}'

    def bulk(self, academic_class):
        return self.client.post('/api/attendance/register/bulk/', {
            'class': academic_class.pk, 'month': self.month, 'cells': [],
        }, format='json')

    def test_a_teacher_may_mark_their_own_class(self):
        self.assertEqual(self.bulk(self.mine).status_code, 200)

    def test_a_teacher_cannot_mark_a_class_they_are_not_assigned_to(self):
        self.assertEqual(self.bulk(self.not_mine).status_code, 404)

    def test_the_same_refusal_on_read(self):
        response = self.client.get('/api/attendance/register/', {
            'class': self.not_mine.pk, 'month': self.month,
        })
        self.assertEqual(response.status_code, 404)

    def test_a_subject_assignment_also_grants_the_class(self):
        """The second half of the D6 union — a subject teacher reaches the class
        they teach in, without being its class teacher."""
        from academics.models import SubjectAssignment

        subject = make_subject(self.not_mine, name='Arabic')
        SubjectAssignment.objects.create(
            branch=self.branch, session=self.session, teacher=self.teacher,
            subject=subject, academic_class=self.not_mine,
        )
        self.assertEqual(self.bulk(self.not_mine).status_code, 200)

    def test_the_institution_can_turn_the_restriction_off(self):
        """`Branch.restrict_teachers_to_assigned_classes` — a small madrasah where
        three teachers cover everything (docs/08 D6)."""
        self.branch.restrict_teachers_to_assigned_classes = False
        self.branch.save(update_fields=['restrict_teachers_to_assigned_classes'])

        self.assertEqual(self.bulk(self.not_mine).status_code, 200)

    def test_a_principal_is_never_scoped(self):
        principal = make_user(self.branch, user_type=UserType.PRINCIPAL)
        self.client.force_authenticate(principal)

        self.assertEqual(self.bulk(self.not_mine).status_code, 200)
