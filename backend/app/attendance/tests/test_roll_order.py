"""Every attendance roster is read in class-roll order.

The month grid, the single-day phone list and the period roster are all called
out down the register by roll, so a list in name or admission order makes the
teacher hunt for every student. The rolls here are deliberately out of step
with both the names and the order the students were created in.
"""

from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from academics.services import change_roll
from attendance.services import month_register, period_roster

from .factories import (enrol, make_branch, make_class, make_period,
                        make_section, make_session, make_student, make_user)


def markable_day(branch):
    day = timezone.localdate()
    while day.strftime('%a').lower() in branch.weekly_off_days:
        day -= timedelta(days=1)
    return day


class RosterOrderTests(TestCase):

    def setUp(self):
        self.branch = make_branch()
        self.session = make_session(self.branch)
        self.user = make_user(self.branch)
        self.klass = make_class(self.branch, self.session)
        # Created Abdullah, Bilal, Umar → rolls 1, 2, 3. Then renumbered so
        # roll order is Umar, Abdullah, Bilal: matches neither names nor ids.
        self.abdullah, self.bilal, self.umar = [
            enrol(make_student(self.branch, name=name),
                  session=self.session, academic_class=self.klass)
            for name in ('Abdullah', 'Bilal', 'Umar')
        ]
        change_roll(self.umar, roll=1, swap=True)    # Umar 1, Abdullah 3
        change_roll(self.abdullah, roll=2, swap=True)  # Abdullah 2, Bilal 3
        self.day = markable_day(self.branch)
        self.month = f'{self.day.year:04d}-{self.day.month:02d}'

    def names(self, rows):
        return [row['name'] for row in rows]

    def test_month_register_is_in_roll_order(self):
        register = month_register(self.branch, self.klass, None, self.month,
                                  user=self.user)
        self.assertEqual(self.names(register['students']), ['Umar', 'Abdullah', 'Bilal'])
        self.assertEqual([s['roll'] for s in register['students']], [1, 2, 3])

    def test_period_roster_is_in_roll_order(self):
        period = make_period(self.branch)
        roster = period_roster(branch=self.branch, academic_class=self.klass,
                               period=period, on_date=self.day, user=self.user)
        self.assertEqual(self.names(roster['students']), ['Umar', 'Abdullah', 'Bilal'])

    def test_rows_carry_both_the_roll_and_the_student_id(self):
        register = month_register(self.branch, self.klass, None, self.month,
                                  user=self.user)
        first = register['students'][0]
        self.assertEqual(first['roll'], 1)
        self.assertEqual(first['student_code'], self.umar.student.student_id)

    def test_whole_class_view_groups_by_section_then_roll(self):
        """Rolls restart per section, so A-1, B-1, A-2 would be nonsense."""
        klass = make_class(self.branch, self.session, name='Class 6', level_order=6)
        section_b = make_section(klass, name='B')
        section_a = make_section(klass, name='A')
        b1 = enrol(make_student(self.branch, 'B one'), session=self.session,
                   academic_class=klass, section=section_b)
        a1 = enrol(make_student(self.branch, 'A one'), session=self.session,
                   academic_class=klass, section=section_a)
        b2 = enrol(make_student(self.branch, 'B two'), session=self.session,
                   academic_class=klass, section=section_b)
        a2 = enrol(make_student(self.branch, 'A two'), session=self.session,
                   academic_class=klass, section=section_a)

        register = month_register(self.branch, klass, None, self.month, user=self.user)

        self.assertEqual(
            [(s['section_name'], s['roll']) for s in register['students']],
            [('A', 1), ('A', 2), ('B', 1), ('B', 2)],
        )
        self.assertEqual([s['enrolment'] for s in register['students']],
                         [a1.pk, a2.pk, b1.pk, b2.pk])


@override_settings(ROOT_URLCONF='attendance.tests.urls')
class RosterOrderEndpointTests(TestCase):
    """The same order through `ClassAttendanceView`, the period roster API."""

    def setUp(self):
        self.branch = make_branch()
        self.session = make_session(self.branch)
        self.klass = make_class(self.branch, self.session)
        self.first, self.second = [
            enrol(make_student(self.branch, name=name),
                  session=self.session, academic_class=self.klass)
            for name in ('Zayd', 'Ali')
        ]
        change_roll(self.first, roll=2, swap=True)  # Ali 1, Zayd 2
        self.period = make_period(self.branch)
        self.client = APIClient()
        self.client.force_authenticate(make_user(self.branch))

    def test_class_roster_endpoint_orders_by_roll(self):
        response = self.client.get('/api/attendance/class/', {
            'class': self.klass.pk, 'period': self.period.pk,
            'date': markable_day(self.branch).isoformat(),
        })
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([s['name'] for s in response.data['students']], ['Ali', 'Zayd'])
        self.assertEqual([s['roll'] for s in response.data['students']], [1, 2])
