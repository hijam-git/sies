"""A month register shows one class's cells, and only that class's.

The register selected its rows by **student** over a date range. One enrolment
per student per session is a constraint, so the case this misses is the session
boundary: a session ends mid-January, the student moves up to Class 6 in the new
one, and Class 6's January register showed the first fortnight's cells — marked
in Class 5, under a different enrolment — as its own, counted in its
percentages. `attendance_summary()` filtered on the enrolment all along, so the
grid and the summary disagreed for exactly the students a year boundary touches.
"""

from datetime import date

from django.test import TestCase
from django.utils import timezone

from attendance.models import AttendanceStatus, DailyAttendance, PersonType
from attendance.services import month_register

from .factories import (enrol, make_branch, make_class, make_session,
                        make_student, make_user)


class RegisterBelongsToOneClassTests(TestCase):
    def setUp(self):
        self.branch = make_branch()
        # The old session runs to mid-January, which is the case this is
        # about: both enrolments are live inside the same month.
        self.last_year = make_session(self.branch, name='2025')
        self.last_year.starts_on = date(2025, 1, 1)
        self.last_year.ends_on = date(2026, 1, 15)
        self.last_year.is_current = False
        self.last_year.save()
        self.this_year = make_session(self.branch, name='2026')
        self.five = make_class(self.branch, self.last_year, name='Class 5')
        self.six = make_class(self.branch, self.this_year, name='Class 6', level_order=6)
        self.user = make_user(self.branch)

        self.student = make_student(self.branch, name='Moved Up In January')
        self.old = enrol(self.student, session=self.last_year,
                         academic_class=self.five, roll=1)
        self.old.left_on = date(2026, 1, 15)
        self.old.is_active = False
        self.old.save(update_fields=['left_on', 'is_active'])
        self.new = enrol(self.student, session=self.this_year,
                         academic_class=self.six, roll=1)

        DailyAttendance.objects.create(
            branch=self.branch, person_type=PersonType.STUDENT,
            student=self.student, enrolment=self.old, date=date(2026, 1, 6),
            status=AttendanceStatus.ABSENT, taken_at=timezone.now(),
        )
        DailyAttendance.objects.create(
            branch=self.branch, person_type=PersonType.STUDENT,
            student=self.student, enrolment=self.new, date=date(2026, 1, 20),
            status=AttendanceStatus.PRESENT, taken_at=timezone.now(),
        )

    def cells(self, academic_class):
        register = month_register(self.branch, academic_class, month='2026-01',
                                  user=self.user)
        rows = [row for row in register['students'] if row['student'] == self.student.pk]
        return rows[0]['cells'] if rows else {}

    def test_the_new_class_does_not_show_the_old_classes_cells(self):
        cells = self.cells(self.six)

        self.assertIn('2026-01-20', cells)
        self.assertNotIn('2026-01-06', cells)

    def test_a_cell_with_no_enrolment_still_belongs_to_the_student(self):
        """`enrolment` is SET_NULL and arrived after the first rows existed, so
        a cell carrying none is claimed by the student — the old behaviour,
        kept for exactly those rows."""
        DailyAttendance.objects.create(
            branch=self.branch, person_type=PersonType.STUDENT,
            student=self.student, enrolment=None, date=date(2026, 1, 27),
            status=AttendanceStatus.LATE, taken_at=timezone.now(),
        )

        self.assertIn('2026-01-27', self.cells(self.six))
