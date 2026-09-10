"""The bulk register save — its three required properties (docs/02 §5.1).

    1. idempotent          — the same payload twice writes the same rows
    2. server-authoritative — a future date or an off day is REJECTED into
                              `skipped`, never silently written
    3. one transaction     — a partial save cannot leave half a month written

Dates here are computed from *today* rather than written as literals. A test
pinned to `2026-03-15` starts failing the day that becomes a future date, and a
suite that breaks with the calendar gets its assertion deleted rather than its
cause fixed.
"""

from datetime import timedelta

from django.db import DataError
from django.test import TestCase
from django.utils import timezone

from attendance.models import AttendanceStatus, DailyAttendance, PersonType
from attendance.services import (REASON_FUTURE, REASON_NOT_ENROLLED,
                                 REASON_OUTSIDE_MONTH, REASON_WEEKLY_OFF,
                                 month_register, save_register)

from .factories import (make_branch, make_class, make_section, make_session,
                        make_student, make_students, make_user)


def month_of(day):
    return f'{day.year:04d}-{day.month:02d}'


class RegisterSaveTests(TestCase):

    def setUp(self):
        self.branch = make_branch()
        self.session = make_session(self.branch)
        self.user = make_user(self.branch)
        self.klass = make_class(self.branch, self.session)
        self.section = make_section(self.klass)
        self.enrolments = make_students(
            self.branch, self.session, self.klass, self.section, count=3,
        )
        self.today = timezone.localdate()

        # A markable weekday inside this month: today, unless today is the
        # branch's weekly off day, in which case yesterday.
        self.day = self.today
        while self.day.strftime('%a').lower() in self.branch.weekly_off_days:
            self.day -= timedelta(days=1)

    def cells(self, status=AttendanceStatus.PRESENT, day=None):
        return [{'student': e.student_id, 'date': day or self.day, 'status': status}
                for e in self.enrolments]

    def save(self, cells, **kwargs):
        kwargs.setdefault('month', month_of(self.day))
        return save_register(
            branch=self.branch, academic_class=self.klass, section=self.section,
            cells=cells, user=self.user, **kwargs,
        )

    # ── idempotency ──────────────────────────────────────────────────────────

    def test_the_same_payload_twice_writes_the_same_rows(self):
        """The grid auto-saves on a debounce *and* on an explicit Save, so the
        same cells arrive twice as a matter of course."""
        first = self.save(self.cells())
        rows_after_first = set(DailyAttendance.objects.values_list('id', flat=True))

        second = self.save(self.cells())

        self.assertEqual(first['saved'], 3)
        self.assertEqual(second['saved'], 3)
        self.assertEqual(DailyAttendance.objects.count(), 3)
        self.assertEqual(
            set(DailyAttendance.objects.values_list('id', flat=True)),
            rows_after_first,
        )

    def test_a_correction_overwrites_the_cell_in_place(self):
        """docs/08 D3, and the reason there is no history table."""
        self.save(self.cells(AttendanceStatus.PRESENT))
        self.save(self.cells(AttendanceStatus.ABSENT))

        self.assertEqual(DailyAttendance.objects.count(), 3)
        self.assertEqual(
            set(DailyAttendance.objects.values_list('status', flat=True)),
            {AttendanceStatus.ABSENT},
        )

    def test_taken_by_is_stamped_per_cell_from_the_request_user(self):
        """Never from the client — the column exists to answer "who marked my son
        absent" and a client-supplied value answers nothing."""
        self.save(self.cells())
        self.assertEqual(
            set(DailyAttendance.objects.values_list('taken_by', flat=True)),
            {self.user.pk},
        )

    def test_the_enrolment_of_the_day_is_recorded(self):
        """What keeps a historical register correct after a promotion."""
        self.save(self.cells())
        for enrolment in self.enrolments:
            row = DailyAttendance.objects.get(student=enrolment.student)
            self.assertEqual(row.enrolment_id, enrolment.pk)
            self.assertEqual(row.person_type, PersonType.STUDENT)

    # ── server-authoritative ─────────────────────────────────────────────────

    def test_a_future_date_is_skipped_and_never_written(self):
        tomorrow = self.today + timedelta(days=1)
        result = self.save(
            [{'student': self.enrolments[0].student_id, 'date': tomorrow,
              'status': AttendanceStatus.PRESENT}],
            month=month_of(tomorrow),
        )

        self.assertEqual(result['saved'], 0)
        self.assertEqual([s['reason'] for s in result['skipped']], [REASON_FUTURE])
        self.assertFalse(DailyAttendance.objects.exists())

    def test_a_weekly_off_day_is_skipped_and_never_written(self):
        """`Branch.weekly_off_days` defaults to `["fri"]`, and the month grid puts
        four or five of them on screen at once."""
        friday = self.today
        while friday.strftime('%a').lower() != 'fri':
            friday -= timedelta(days=1)

        result = self.save(
            [{'student': self.enrolments[0].student_id, 'date': friday,
              'status': AttendanceStatus.PRESENT}],
            month=month_of(friday),
        )

        self.assertEqual(result['saved'], 0)
        self.assertEqual([s['reason'] for s in result['skipped']],
                         [REASON_WEEKLY_OFF])
        self.assertFalse(DailyAttendance.objects.exists())

    def test_the_good_cells_of_a_mixed_batch_still_commit(self):
        """A rejected cell is a normal answer, not a failure of the batch."""
        tomorrow = self.today + timedelta(days=1)
        result = self.save(self.cells() + [
            {'student': self.enrolments[0].student_id, 'date': tomorrow,
             'status': AttendanceStatus.PRESENT},
        ])

        self.assertEqual(result['saved'], 3)
        self.assertEqual(len(result['skipped']), 1)
        self.assertEqual(DailyAttendance.objects.count(), 3)

    def test_a_student_from_another_class_is_skipped(self):
        outsider = make_student(self.branch, name='Not Enrolled Here')
        result = self.save([{'student': outsider.pk, 'date': self.day,
                             'status': AttendanceStatus.PRESENT}])

        self.assertEqual(result['saved'], 0)
        self.assertEqual([s['reason'] for s in result['skipped']],
                         [REASON_NOT_ENROLLED])
        self.assertFalse(DailyAttendance.objects.exists())

    def test_a_cell_outside_the_month_being_saved_is_skipped(self):
        """The grid had one month open; a cell from another one is a client bug or
        a probe, and either way it does not belong in this save."""
        last_month = self.day.replace(day=1) - timedelta(days=1)
        result = self.save([{'student': self.enrolments[0].student_id,
                             'date': last_month,
                             'status': AttendanceStatus.PRESENT}])

        self.assertEqual([s['reason'] for s in result['skipped']],
                         [REASON_OUTSIDE_MONTH])
        self.assertFalse(DailyAttendance.objects.exists())

    # ── one transaction ──────────────────────────────────────────────────────

    def test_a_partial_failure_rolls_the_whole_batch_back(self):
        """A partial save that leaves half a month written is worse than a failed
        one, because nobody can tell which half (docs/02 §5.1).

        The failure is forced at the database rather than mocked: a status longer
        than the column is exactly the shape of bug this protects against — the
        first cells are already written when the last one is rejected.
        """
        good = self.cells()
        poisoned = good + [{'student': self.enrolments[0].student_id,
                            'date': self.day,
                            'status': 'a-status-far-too-long-for-the-column'}]

        with self.assertRaises(DataError):
            self.save(poisoned)

        self.assertFalse(DailyAttendance.objects.exists())


class MonthRegisterReadTests(TestCase):
    """The GET half — the grid's own shape (docs/02 §4.4)."""

    def setUp(self):
        self.branch = make_branch()
        self.session = make_session(self.branch)
        self.user = make_user(self.branch)
        self.klass = make_class(self.branch, self.session)
        self.enrolments = make_students(
            self.branch, self.session, self.klass, count=2,
        )
        self.today = timezone.localdate()
        self.day = self.today
        while self.day.strftime('%a').lower() in self.branch.weekly_off_days:
            self.day -= timedelta(days=1)
        self.month = month_of(self.day)

    def test_every_day_of_the_month_is_returned_with_its_own_flag(self):
        register = month_register(self.branch, self.klass, None, self.month,
                                  user=self.user)
        first = register['days'][0]['date']

        self.assertEqual(first, f'{self.month}-01')
        self.assertTrue(all('is_markable' in day for day in register['days']))
        self.assertTrue(any(day['reason'] == 'weekly_off'
                            for day in register['days']))

    def test_students_come_back_in_roll_order_with_cells_and_totals(self):
        save_register(
            branch=self.branch, academic_class=self.klass, month=self.month,
            user=self.user,
            cells=[{'student': self.enrolments[0].student_id, 'date': self.day,
                    'status': AttendanceStatus.PRESENT},
                   {'student': self.enrolments[1].student_id, 'date': self.day,
                    'status': AttendanceStatus.ABSENT}],
        )

        register = month_register(self.branch, self.klass, None, self.month,
                                  user=self.user)
        rolls = [row['roll'] for row in register['students']]

        self.assertEqual(rolls, sorted(rolls))
        self.assertEqual(register['students'][0]['present'], 1)
        self.assertEqual(register['students'][0]['percent'], 100.0)
        self.assertEqual(register['students'][1]['absent'], 1)
        self.assertEqual(register['students'][1]['percent'], 0.0)
        self.assertEqual(
            register['students'][0]['cells'][self.day.isoformat()]['status'],
            AttendanceStatus.PRESENT,
        )
