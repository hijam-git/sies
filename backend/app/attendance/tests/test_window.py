"""The attendance window — docs/08 D7.

    inside the window   → `attendance.take` is enough
    outside it          → refused, unless the caller holds `attendance.update`
    window = 0          → unlimited

`now` is injected into every call rather than mocked. The rule is a comparison
between two moments, so a test that could not name both moments would be testing
the clock.
"""

from datetime import date, datetime, timedelta

from django.test import TestCase
from django.utils import timezone

from attendance.services import REASON_WINDOW_CLOSED, is_markable

from .factories import make_branch, make_period, make_user


def at(when):
    """A localtime-aware datetime, the way `timezone.localtime()` produces one."""
    return timezone.make_aware(when, timezone.get_current_timezone())


class AttendanceWindowTests(TestCase):

    def setUp(self):
        self.branch = make_branch()
        # 2 March 2026 is a Monday — not the branch's weekly off day, so the
        # window is the only rule that can refuse anything below.
        self.day = date(2026, 3, 2)
        # order=1 → 09:00–09:45 (see `make_period`).
        self.period = make_period(self.branch, order=1)

        self.taker = make_user(
            self.branch, permissions=['attendance.view', 'attendance.take'],
        )
        self.corrector = make_user(
            self.branch,
            permissions=['attendance.view', 'attendance.take', 'attendance.update'],
        )

    def test_inside_the_window_take_is_enough(self):
        """Default 120 minutes from 09:45, so 10:30 is comfortably inside."""
        verdict = is_markable(self.branch, self.day, self.period,
                              user=self.taker, now=at(datetime(2026, 3, 2, 10, 30)))
        self.assertTrue(verdict.ok)

    def test_during_the_period_itself_is_inside(self):
        verdict = is_markable(self.branch, self.day, self.period,
                              user=self.taker, now=at(datetime(2026, 3, 2, 9, 20)))
        self.assertTrue(verdict.ok)

    def test_outside_the_window_take_is_refused(self):
        """The button is gone and the period shows `!` missed (docs/08 D7)."""
        verdict = is_markable(self.branch, self.day, self.period,
                              user=self.taker, now=at(datetime(2026, 3, 2, 14, 0)))
        self.assertFalse(verdict.ok)
        self.assertEqual(verdict.reason, REASON_WINDOW_CLOSED)

    def test_outside_the_window_update_still_gets_through(self):
        """The class teacher and the principal fill it in afterwards."""
        verdict = is_markable(self.branch, self.day, self.period,
                              user=self.corrector,
                              now=at(datetime(2026, 3, 2, 14, 0)))
        self.assertTrue(verdict.ok)

    def test_a_strict_institution_can_narrow_it(self):
        """15 minutes — the institution that wants it strict sets it to 15."""
        self.branch.attendance_window_minutes = 15
        self.branch.save(update_fields=['attendance_window_minutes'])

        self.assertTrue(is_markable(self.branch, self.day, self.period,
                                    user=self.taker,
                                    now=at(datetime(2026, 3, 2, 9, 55))).ok)
        self.assertFalse(is_markable(self.branch, self.day, self.period,
                                     user=self.taker,
                                     now=at(datetime(2026, 3, 2, 10, 5))).ok)

    def test_zero_means_unlimited(self):
        """One that wants it off sets it to 0 (docs/08 D7)."""
        self.branch.attendance_window_minutes = 0
        self.branch.save(update_fields=['attendance_window_minutes'])

        verdict = is_markable(self.branch, self.day, self.period,
                              user=self.taker,
                              now=at(datetime(2026, 3, 5, 23, 30)))
        self.assertTrue(verdict.ok)

    def test_the_window_never_unlocks_a_future_date(self):
        """Rule 1 has no override. Tomorrow has not happened, and `0` for
        unlimited must not be read as "unlimited in both directions"."""
        self.branch.attendance_window_minutes = 0
        self.branch.save(update_fields=['attendance_window_minutes'])
        now = timezone.localtime()

        verdict = is_markable(self.branch, now.date() + timedelta(days=1),
                              self.period, user=self.corrector, now=now)
        self.assertFalse(verdict.ok)

    def test_day_attendance_has_no_window(self):
        """The window is measured from a period's end time; a whole day has none,
        so the month register is not locked at some arbitrary hour."""
        verdict = is_markable(self.branch, self.day, None, user=self.taker,
                              now=at(datetime(2026, 3, 2, 23, 59)))
        self.assertTrue(verdict.ok)
