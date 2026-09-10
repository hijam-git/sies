"""A wrong receipt is reversed, never deleted (docs/01 §9, docs/06 #8).

The reversal has to move three things together: the receipt, the invoice's
balance and status, and the income row it posted. If any one of them is left
behind, the institution's books say something different from its fee ledger and
nobody can tell which is right.
"""

from decimal import Decimal

from django.test import TestCase

from accounts.services import CodedError
from finance.models import Income
from fees.models import FeeStatus, Payment
from fees.services import collect_fee, reverse_payment

from .factories import FeeFixture, make_fee


class ReversalTests(FeeFixture, TestCase):
    def setUp(self):
        self.build_fixture()
        self.fee = make_fee(self.branch, self.session, student=self.student,
                            amount='500.00')
        self.payment = collect_fee(fee=self.fee, amount=Decimal('500.00'),
                                   collected_by=self.user)

    def test_the_receipt_is_flagged_not_removed(self):
        reverse_payment(self.payment, reason='Wrong student', actor=self.user)
        self.payment.refresh_from_db()

        self.assertTrue(Payment.objects.filter(pk=self.payment.pk).exists())
        self.assertTrue(self.payment.is_reversed)
        self.assertEqual(self.payment.reversed_by, self.user)
        self.assertEqual(self.payment.reverse_reason, 'Wrong student')
        self.assertIsNotNone(self.payment.reversed_at)
        # The receipt number stays taken. Re-issuing it would put two different
        # transactions on one number in a series whose only promise is that it
        # has none.
        self.assertTrue(self.payment.receipt_no)

    def test_the_invoice_goes_back_to_unpaid(self):
        self.fee.refresh_from_db()
        self.assertEqual(self.fee.status, FeeStatus.PAID)

        reverse_payment(self.payment, reason='Wrong student', actor=self.user)
        self.fee.refresh_from_db()

        self.assertEqual(self.fee.paid_amount, Decimal('0.00'))
        self.assertEqual(self.fee.balance, Decimal('500.00'))
        self.assertEqual(self.fee.status, FeeStatus.UNPAID)

    def test_paid_falls_back_to_partial_when_another_receipt_stands(self):
        """The diagram's `paid → partial` edge (docs/06 #8)."""
        fee = make_fee(self.branch, self.session, student=self.student,
                       code='BOK', amount='500.00', period='2026-04')
        first = collect_fee(fee=fee, amount=Decimal('200.00'), collected_by=self.user)
        collect_fee(fee=fee, amount=Decimal('300.00'), collected_by=self.user)
        fee.refresh_from_db()
        self.assertEqual(fee.status, FeeStatus.PAID)

        reverse_payment(first, reason='Duplicate entry', actor=self.user)
        fee.refresh_from_db()

        self.assertEqual(fee.paid_amount, Decimal('300.00'))
        self.assertEqual(fee.status, FeeStatus.PARTIAL)

    def test_the_income_row_is_reversed_too_and_still_exists(self):
        income_id = self.payment.income_id
        reverse_payment(self.payment, reason='Wrong student', actor=self.user)

        income = Income.objects.get(pk=income_id)
        self.assertTrue(income.is_reversed)
        self.assertEqual(income.reversed_by, self.user)
        self.assertIn('Wrong student', income.reverse_reason)
        self.assertIn(self.payment.receipt_no, income.reverse_reason)
        # Still in the table: deleting it would make a closed month's P&L change
        # retrospectively with nothing to say why.
        self.assertEqual(Income.objects.count(), 1)

    def test_reversing_twice_is_refused(self):
        reverse_payment(self.payment, reason='Wrong student', actor=self.user)

        with self.assertRaises(CodedError) as caught:
            reverse_payment(self.payment, reason='Again', actor=self.user)
        self.assertEqual(caught.exception.default_code, 'already_reversed')

    def test_a_reversal_needs_a_reason(self):
        with self.assertRaises(CodedError) as caught:
            reverse_payment(self.payment, reason='', actor=self.user)
        self.assertEqual(caught.exception.default_code, 'reason_required')

    def test_money_can_be_taken_again_after_a_reversal(self):
        """The whole point: correct the mistake, then issue the right receipt."""
        reverse_payment(self.payment, reason='Wrong student', actor=self.user)
        self.fee.refresh_from_db()

        replacement = collect_fee(fee=self.fee, amount=Decimal('500.00'),
                                  collected_by=self.user)
        self.fee.refresh_from_db()

        self.assertEqual(self.fee.status, FeeStatus.PAID)
        self.assertNotEqual(replacement.receipt_no, self.payment.receipt_no)
        self.assertEqual(Income.objects.filter(is_reversed=False).count(), 1)
