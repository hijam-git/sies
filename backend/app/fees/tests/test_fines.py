"""Late fines — nightly, capped, and they stop when the invoice is paid.

`Branch.fine_rule` is `{per_day, grace_days, max}` and every one of the three is
a rule a guardian will eventually be told about at a counter. Each has a test
here, plus the property that makes the job safe to run twice: the fine is
recomputed from the day count, never incremented.
"""

from datetime import date
from decimal import Decimal

from django.test import TestCase

from fees.models import FeeStatus
from fees.services import accrue_fines, collect_fee, fine_for

from .factories import FeeFixture, make_fee


class FineRuleTests(FeeFixture, TestCase):
    def setUp(self):
        self.build_fixture()
        self.branch.fine_rule = {'per_day': 10, 'grace_days': 3, 'max': 100}
        self.branch.save(update_fields=['fine_rule'])
        # Due on the 10th, so every date below reads as "n days after the 10th".
        self.fee = make_fee(self.branch, self.session, student=self.student,
                            amount='500.00', due_date=date(2026, 3, 10))

    def test_no_fine_inside_the_grace_period(self):
        accrue_fines(self.branch, on_date=date(2026, 3, 13))
        self.fee.refresh_from_db()

        self.assertEqual(self.fee.fine, Decimal('0.00'))
        self.assertEqual(self.fee.payable, Decimal('500.00'))

    def test_the_fine_accrues_per_day_after_the_grace_period(self):
        accrue_fines(self.branch, on_date=date(2026, 3, 18))
        self.fee.refresh_from_db()

        # 18th − 10th = 8 days, minus 3 grace = 5 chargeable days × ৳10.
        self.assertEqual(self.fee.fine, Decimal('50.00'))
        self.assertEqual(self.fee.payable, Decimal('550.00'))
        self.assertEqual(self.fee.status, FeeStatus.OVERDUE)

    def test_the_fine_is_capped(self):
        """An invoice forgotten for a year must not owe more fine than fee."""
        accrue_fines(self.branch, on_date=date(2027, 3, 18))
        self.fee.refresh_from_db()

        self.assertEqual(self.fee.fine, Decimal('100.00'))
        self.assertEqual(self.fee.payable, Decimal('600.00'))

    def test_running_twice_on_the_same_night_changes_nothing(self):
        """Recomputed from the day count, never `F('fine') + x`."""
        accrue_fines(self.branch, on_date=date(2026, 3, 18))
        accrue_fines(self.branch, on_date=date(2026, 3, 18))
        self.fee.refresh_from_db()

        self.assertEqual(self.fee.fine, Decimal('50.00'))

    def test_it_stops_when_the_invoice_is_paid(self):
        accrue_fines(self.branch, on_date=date(2026, 3, 18))
        self.fee.refresh_from_db()

        collect_fee(fee=self.fee, amount=self.fee.balance, collected_by=self.user)
        self.fee.refresh_from_db()
        self.assertEqual(self.fee.status, FeeStatus.PAID)

        accrue_fines(self.branch, on_date=date(2026, 4, 30))
        self.fee.refresh_from_db()
        self.assertEqual(self.fee.fine, Decimal('50.00'))
        self.assertEqual(self.fee.status, FeeStatus.PAID)

    def test_a_partly_paid_invoice_keeps_accruing(self):
        collect_fee(fee=self.fee, amount=Decimal('100.00'), collected_by=self.user)

        accrue_fines(self.branch, on_date=date(2026, 3, 18))
        self.fee.refresh_from_db()
        self.assertEqual(self.fee.fine, Decimal('50.00'))
        self.assertEqual(self.fee.payable, Decimal('550.00'))
        self.assertEqual(self.fee.status, FeeStatus.OVERDUE)

    def test_a_waived_invoice_never_accrues(self):
        from fees.services import waive_fee

        waive_fee(self.fee, reason='Orphan', actor=self.user)
        accrue_fines(self.branch, on_date=date(2026, 4, 30))
        self.fee.refresh_from_db()

        self.assertEqual(self.fee.fine, Decimal('0.00'))
        self.assertEqual(self.fee.status, FeeStatus.WAIVED)

    def test_a_branch_with_no_policy_accrues_nothing(self):
        """`default_fine_rule()` is per_day 0 — the job reads it and moves on."""
        self.branch.fine_rule = {'per_day': 0, 'grace_days': 0, 'max': 0}
        self.branch.save(update_fields=['fine_rule'])

        accrue_fines(self.branch, on_date=date(2026, 4, 30))
        self.fee.refresh_from_db()
        self.assertEqual(self.fee.fine, Decimal('0.00'))

    def test_mark_overdue_covers_the_branch_that_does_not_fine(self):
        """Otherwise its dues screen would show nothing as late."""
        from fees.services import mark_overdue

        self.branch.fine_rule = {'per_day': 0, 'grace_days': 0, 'max': 0}
        self.branch.save(update_fields=['fine_rule'])

        mark_overdue(self.branch, on_date=date(2026, 4, 30))
        self.fee.refresh_from_db()
        self.assertEqual(self.fee.status, FeeStatus.OVERDUE)

    def test_fine_for_reads_json_numbers_as_decimals(self):
        """The rule comes out of a JSON column, so it may hold floats."""
        fine = fine_for(rule={'per_day': 10.5, 'max': 0}, days_late=2)

        self.assertIsInstance(fine, Decimal)
        self.assertEqual(fine, Decimal('21.00'))

    def test_an_uncapped_rule_keeps_accruing(self):
        self.branch.fine_rule = {'per_day': 5, 'grace_days': 0, 'max': 0}
        self.branch.save(update_fields=['fine_rule'])

        accrue_fines(self.branch, on_date=date(2026, 5, 10))
        self.fee.refresh_from_db()
        # 61 days from 10 March to 10 May.
        self.assertEqual(self.fee.fine, Decimal('305.00'))
