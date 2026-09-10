"""The teacher's today board — docs/08 D7.

    ✓ taken   ● live now   ○ upcoming   ! missed

The board is the teacher's home screen, so the three things it has to get right
are the ones asserted here: the **order** (the bell schedule's, not the clock's),
the **student count** (computed from `Enrolment`, never stored), and the
**state** of each period.

`now` is injected, because every state but `taken` is a comparison against it.
"""

from datetime import date, datetime, time

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import UserType
from attendance.models import AttendanceStatus, ClassAttendance
from attendance.services import (STATE_LIVE, STATE_MISSED, STATE_TAKEN,
                                 STATE_UPCOMING, teacher_today)

from .factories import (make_branch, make_class, make_period, make_routine,
                        make_section, make_session, make_students,
                        make_subject, make_teacher, make_user)

# 2 March 2026 is a Monday. `academics.DayOfWeek` numbers the Bangladeshi week
# from Saturday, so Monday is 2 — the value the routine rows below carry.
MONDAY = date(2026, 3, 2)
MONDAY_INDEX = 2


def at(when):
    return timezone.make_aware(when, timezone.get_current_timezone())


class TeacherTodayTests(TestCase):

    def setUp(self):
        self.branch = make_branch()
        self.session = make_session(self.branch)
        self.account = make_user(self.branch, user_type=UserType.TEACHER)
        self.teacher = make_teacher(self.branch, user=self.account)

        self.klass = make_class(self.branch, self.session)
        self.section = make_section(self.klass)
        self.subject = make_subject(self.klass, name='Qur’an')
        self.enrolments = make_students(
            self.branch, self.session, self.klass, self.section, count=3,
        )

        # 09:00, 10:00, 11:00, 12:00 — one 45-minute period each.
        self.periods = [make_period(self.branch, order=n) for n in range(1, 5)]
        # A break occupies a slot so the timetable lines up, and must never
        # appear on the board (docs/08 D7).
        self.break_period = make_period(
            self.branch, order=5, is_break=True,
            start=time(13, 0), end=time(13, 30), name='Tiffin',
        )

        for period in [*self.periods, self.break_period]:
            make_routine(session=self.session, academic_class=self.klass,
                         section=self.section, subject=self.subject,
                         teacher=self.teacher, period=period,
                         day_of_week=MONDAY_INDEX)

        # The second period was taken. Every other state is decided by the clock.
        ClassAttendance.objects.create(
            branch=self.branch, date=MONDAY, academic_class=self.klass,
            section=self.section, subject=self.subject, period=self.periods[1],
            student=self.enrolments[0].student, enrolment=self.enrolments[0],
            status=AttendanceStatus.PRESENT,
            taken_by=self.account, taken_at=timezone.now(),
        )

    def board(self, when=datetime(2026, 3, 2, 11, 20)):
        return teacher_today(self.teacher, MONDAY, user=self.account,
                             now=at(when))

    def test_periods_come_back_in_bell_schedule_order(self):
        self.assertEqual([row['period_order'] for row in self.board()],
                         [1, 2, 3, 4])

    def test_a_break_never_appears(self):
        self.assertNotIn(self.break_period.pk,
                         [row['period'] for row in self.board()])

    def test_the_student_count_is_computed_from_enrolment(self):
        self.assertEqual([row['student_count'] for row in self.board()],
                         [3, 3, 3, 3])

    def test_a_new_admission_changes_the_count_immediately(self):
        """Computed, never stored — a stored count is wrong the day after an
        admission, and it is wrong silently."""
        make_students(self.branch, self.session, self.klass, self.section, count=1)
        self.assertEqual(self.board()[0]['student_count'], 4)

    def test_the_four_states(self):
        """At 11:20: the 09:00 period was never taken, the 10:00 one was, the
        11:00 one is running, and the 12:00 one has not started."""
        self.assertEqual([row['state'] for row in self.board()],
                         [STATE_MISSED, STATE_TAKEN, STATE_LIVE, STATE_UPCOMING])

    def test_everything_is_upcoming_before_the_day_starts(self):
        states = [row['state'] for row in self.board(datetime(2026, 3, 2, 7, 0))]
        # The taken period stays taken: it is a fact about the data, not about
        # the clock, and it wins over every time comparison.
        self.assertEqual(states, [STATE_UPCOMING, STATE_TAKEN,
                                  STATE_UPCOMING, STATE_UPCOMING])

    def test_a_missed_period_is_still_markable_for_a_corrector(self):
        """`state` and `is_markable` are separate on purpose: the icon comes from
        one and the button from the other (docs/08 D7)."""
        board = self.board()
        missed = board[0]
        self.assertEqual(missed['state'], STATE_MISSED)
        # The default 120-minute window closed at 11:45 for the 09:00 period…
        self.assertTrue(missed['is_markable'])  # …but this account holds update.

        taker = make_user(self.branch, user_type=UserType.TEACHER,
                          permissions=['attendance.view', 'attendance.take'])
        for_taker = teacher_today(self.teacher, MONDAY, user=taker,
                                  now=at(datetime(2026, 3, 2, 14, 0)))
        self.assertFalse(for_taker[0]['is_markable'])
        self.assertEqual(for_taker[0]['reason'], 'window_closed')

    def test_another_teachers_periods_are_not_on_this_board(self):
        """Filtered to the periods they actually teach — a board full of somebody
        else's classes is not a to-do list."""
        other = make_teacher(self.branch, name='Rafiq Ahmed')
        self.assertEqual(teacher_today(other, MONDAY, user=self.account,
                                       now=at(datetime(2026, 3, 2, 11, 20))), [])

    def test_a_different_weekday_has_a_different_board(self):
        tuesday = date(2026, 3, 3)
        self.assertEqual(teacher_today(self.teacher, tuesday, user=self.account,
                                       now=at(datetime(2026, 3, 3, 11, 20))), [])


@override_settings(ROOT_URLCONF='attendance.tests.urls')
class MyDayEndpointTests(TestCase):
    """`GET /api/attendance/my-day/?date=` — the board over HTTP."""

    def setUp(self):
        self.branch = make_branch()
        self.session = make_session(self.branch)
        self.account = make_user(self.branch, user_type=UserType.TEACHER)
        self.teacher = make_teacher(self.branch, user=self.account)

        self.klass = make_class(self.branch, self.session)
        self.subject = make_subject(self.klass)
        make_students(self.branch, self.session, self.klass, count=2)
        self.period = make_period(self.branch, order=1)
        make_routine(session=self.session, academic_class=self.klass,
                     subject=self.subject, teacher=self.teacher,
                     period=self.period, day_of_week=MONDAY_INDEX)

        self.client = APIClient()
        self.client.force_authenticate(self.account)

    def test_the_board_is_returned_for_the_requested_date(self):
        response = self.client.get('/api/attendance/my-day/',
                                   {'date': MONDAY.isoformat()})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['date'], MONDAY.isoformat())
        self.assertEqual(len(response.data['periods']), 1)
        self.assertEqual(response.data['periods'][0]['student_count'], 2)

    def test_an_account_with_no_teacher_profile_gets_an_empty_board(self):
        """A principal opening the teacher dashboard should see "nothing
        scheduled for you", not a 403."""
        principal = make_user(self.branch, user_type=UserType.PRINCIPAL)
        self.client.force_authenticate(principal)

        response = self.client.get('/api/attendance/my-day/',
                                   {'date': MONDAY.isoformat()})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['periods'], [])
