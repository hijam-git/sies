"""Period attendance — `POST /api/attendance/class/` (docs/08 D7).

The other half of the teacher's board: the **Take attendance** button opens one
period's roster and one submit writes `ClassAttendance` rows. Same three
properties as the register — idempotent, server-authoritative, one transaction —
with the window added, because this is the path the window exists for.
"""

from datetime import date, datetime

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import UserType
from attendance.models import AttendanceStatus, ClassAttendance
from attendance.services import period_roster, save_class_attendance

from .factories import (make_branch, make_class, make_period, make_section,
                        make_session, make_students, make_subject, make_user)

MONDAY = date(2026, 3, 2)


def at(when):
    return timezone.make_aware(when, timezone.get_current_timezone())


class ClassAttendanceServiceTests(TestCase):

    def setUp(self):
        self.branch = make_branch()
        self.session = make_session(self.branch)
        self.user = make_user(self.branch)
        self.klass = make_class(self.branch, self.session)
        self.section = make_section(self.klass)
        self.subject = make_subject(self.klass)
        self.period = make_period(self.branch, order=1)  # 09:00–09:45
        self.enrolments = make_students(
            self.branch, self.session, self.klass, self.section, count=3,
        )

    def save(self, status=AttendanceStatus.PRESENT, user=None, when=None):
        return save_class_attendance(
            branch=self.branch, academic_class=self.klass, section=self.section,
            subject=self.subject, period=self.period, on_date=MONDAY,
            cells=[{'student': e.student_id, 'status': status}
                   for e in self.enrolments],
            user=user or self.user,
            now=at(when or datetime(2026, 3, 2, 9, 30)),
        )

    def test_the_roster_defaults_to_present(self):
        roster = period_roster(
            branch=self.branch, academic_class=self.klass, section=self.section,
            period=self.period, on_date=MONDAY, user=self.user,
            now=at(datetime(2026, 3, 2, 9, 30)),
        )
        self.assertEqual(roster['student_count'], 3)
        self.assertTrue(all(row['status'] == AttendanceStatus.PRESENT
                            for row in roster['students']))
        self.assertFalse(any(row['is_taken'] for row in roster['students']))

    def test_a_taken_period_reopens_with_what_was_recorded(self):
        """Re-opening must not reset thirty students to present — that is how a
        correction screen destroys the data it was opened to fix."""
        self.save(AttendanceStatus.ABSENT)

        roster = period_roster(
            branch=self.branch, academic_class=self.klass, section=self.section,
            period=self.period, on_date=MONDAY, user=self.user,
            now=at(datetime(2026, 3, 2, 9, 30)),
        )
        self.assertTrue(all(row['status'] == AttendanceStatus.ABSENT
                            for row in roster['students']))
        self.assertTrue(all(row['is_taken'] for row in roster['students']))

    def test_saving_twice_writes_the_same_rows(self):
        self.save()
        rows = set(ClassAttendance.objects.values_list('id', flat=True))
        self.save(AttendanceStatus.LATE)

        self.assertEqual(ClassAttendance.objects.count(), 3)
        self.assertEqual(set(ClassAttendance.objects.values_list('id', flat=True)),
                         rows)

    def test_a_closed_window_skips_the_whole_roster(self):
        """One question for one period, so the front end shows one message and
        not thirty identical ones."""
        taker = make_user(self.branch, user_type=UserType.TEACHER,
                          permissions=['attendance.view', 'attendance.take'])
        result = self.save(user=taker, when=datetime(2026, 3, 2, 14, 0))

        self.assertEqual(result['saved'], 0)
        self.assertEqual(len(result['skipped']), 3)
        self.assertEqual(result['skipped'][0]['reason'], 'window_closed')
        self.assertFalse(ClassAttendance.objects.exists())

    def test_a_corrector_gets_through_the_closed_window(self):
        result = self.save(when=datetime(2026, 3, 2, 14, 0))
        self.assertEqual(result['saved'], 3)

    def test_the_same_period_in_two_sections_is_two_sets_of_rows(self):
        """A period is a slot in the day, not a room: two sections can be marked
        for the same period without colliding on the unique key."""
        other = make_section(self.klass, name='B')
        theirs = make_students(self.branch, self.session, self.klass, other,
                               count=2)
        self.save()

        save_class_attendance(
            branch=self.branch, academic_class=self.klass, section=other,
            subject=self.subject, period=self.period, on_date=MONDAY,
            cells=[{'student': e.student_id, 'status': AttendanceStatus.PRESENT}
                   for e in theirs],
            user=self.user, now=at(datetime(2026, 3, 2, 9, 30)),
        )

        self.assertEqual(
            ClassAttendance.objects.filter(section=self.section).count(), 3)
        self.assertEqual(ClassAttendance.objects.filter(section=other).count(), 2)


@override_settings(ROOT_URLCONF='attendance.tests.urls')
class ClassAttendanceEndpointTests(TestCase):

    def setUp(self):
        self.branch = make_branch()
        # Unlimited window, so this test asserts the endpoint and not the clock.
        self.branch.attendance_window_minutes = 0
        self.branch.save(update_fields=['attendance_window_minutes'])

        self.session = make_session(self.branch)
        self.user = make_user(self.branch)
        self.klass = make_class(self.branch, self.session)
        self.subject = make_subject(self.klass)
        self.period = make_period(self.branch, order=1)
        self.enrolments = make_students(
            self.branch, self.session, self.klass, count=2,
        )

        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def payload(self, status=AttendanceStatus.PRESENT):
        return {
            'class': self.klass.pk, 'period': self.period.pk,
            'subject': self.subject.pk, 'date': MONDAY.isoformat(),
            'cells': [{'student': e.student_id, 'date': MONDAY.isoformat(),
                       'status': status}
                      for e in self.enrolments],
        }

    def test_post_writes_the_roster(self):
        response = self.client.post('/api/attendance/class/', self.payload(),
                                    format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['saved'], 2)
        self.assertEqual(ClassAttendance.objects.count(), 2)

    def test_a_period_from_another_institution_is_404(self):
        other = make_branch(code='CTG', name='Chittagong Madrasah')
        their_period = make_period(other, order=1)

        body = {**self.payload(), 'period': their_period.pk}
        response = self.client.post('/api/attendance/class/', body, format='json')

        self.assertEqual(response.status_code, 404)
        self.assertFalse(ClassAttendance.objects.exists())

    def test_reading_the_roster_needs_only_view(self):
        reader = make_user(self.branch, permissions=['attendance.view'])
        self.client.force_authenticate(reader)

        response = self.client.get('/api/attendance/class/', {
            'class': self.klass.pk, 'period': self.period.pk,
            'date': MONDAY.isoformat(),
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['student_count'], 2)

    def test_writing_needs_take(self):
        reader = make_user(self.branch, permissions=['attendance.view'])
        self.client.force_authenticate(reader)

        response = self.client.post('/api/attendance/class/', self.payload(),
                                    format='json')
        self.assertEqual(response.status_code, 403)
