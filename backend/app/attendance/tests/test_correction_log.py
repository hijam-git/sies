"""A correction has to be recoverable from the activity log (D3 + D8).

D3 says an attendance correction **overwrites** the cell and keeps no history in
the attendance table. It says that *because* D8 puts the change in `ActivityLog`
with a before and an after — and the log was being written with an `after`
alone, so a cell changed from Absent to Present left no record anywhere of what
it had been. The two decisions only work as a pair.
"""

from datetime import date

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import ActivityLog
from attendance.models import AttendanceStatus

from .factories import (make_branch, make_class, make_session, make_students,
                        make_user)


@override_settings(ROOT_URLCONF='attendance.tests.urls')
class CorrectionLogTests(TestCase):
    def setUp(self):
        self.branch = make_branch()
        self.session = make_session(self.branch)
        self.academic_class = make_class(self.branch, self.session)
        self.enrolments = make_students(self.branch, self.session,
                                        self.academic_class, count=2)
        self.user = make_user(self.branch)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.day = date(2026, 3, 3)

    def save(self, status):
        return self.client.post(
            '/api/attendance/register/bulk/',
            {
                'class': self.academic_class.pk,
                'month': '2026-03',
                'cells': [{'student': self.enrolments[0].student_id,
                           'date': self.day.isoformat(), 'status': status}],
            },
            format='json',
        )

    def test_a_corrected_cell_records_what_it_was(self):
        self.assertEqual(self.save(AttendanceStatus.ABSENT).status_code, 200)
        self.assertEqual(self.save(AttendanceStatus.PRESENT).status_code, 200)

        log = ActivityLog.objects.filter(model='DailyAttendance').order_by('-id').first()
        changed = (log.before or {}).get('changed') or []

        self.assertEqual(len(changed), 1)
        self.assertEqual(changed[0]['from'], AttendanceStatus.ABSENT)
        self.assertEqual(changed[0]['to'], AttendanceStatus.PRESENT)
        self.assertEqual(changed[0]['student'], self.enrolments[0].student_id)

    def test_a_first_marking_changes_nothing_and_says_so(self):
        """Not every save is a correction — a cell that had no value is new."""
        self.assertEqual(self.save(AttendanceStatus.PRESENT).status_code, 200)

        log = ActivityLog.objects.filter(model='DailyAttendance').order_by('-id').first()
        self.assertEqual((log.before or {}).get('changed'), [])

    def test_re_saving_the_same_status_is_not_a_correction(self):
        self.save(AttendanceStatus.PRESENT)
        self.save(AttendanceStatus.PRESENT)

        log = ActivityLog.objects.filter(model='DailyAttendance').order_by('-id').first()
        self.assertEqual((log.before or {}).get('changed'), [])
