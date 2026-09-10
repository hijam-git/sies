"""Money arithmetic and the fee state machine (docs/06 #8).

Every number here is a `Decimal` and every assertion compares against one. A
test that asserted `float(fee.payable) == 500.0` would pass while the column
drifted, which is the failure mode the whole Decimal rule exists to prevent.
"""

from decimal import Decimal

from django.test import TestCase

from accounts.services import CodedError
from fees.models import FeeStatus, PaymentMethod
from fees.services import (accrue_fines, collect_fee, recalculate_fee,
                           waive_fee)

from .factories import FeeFixture, make_fee


class MoneyArithmeticTests(FeeFixture, TestCase):
    def setUp(self):
        self.build_fixture()
        self.fee = make_fee(self.branch, self.session, student=self.student,
                            amount='500.00', enrolment=self.enrolment)

    def test_payable_is_amount_minus_discount_plus_fine(self):
        self.fee.amount = Decimal('500.00')
        self.fee.discount = Decimal('50.00')
        self.fee.fine = Decimal('20.00')
        recalculate_fee(self.fee)

        self.assertEqual(self.fee.payable, Decimal('470.00'))
        self.assertEqual(self.fee.balance, Decimal('470.00'))

    def test_a_part_payment_leaves_the_invoice_partial(self):
        collect_fee(fee=self.fee, amount=Decimal('200.00'),
                    collected_by=self.user)
        self.fee.refresh_from_db()

        self.assertEqual(self.fee.paid_amount, Decimal('200.00'))
        self.assertEqual(self.fee.balance, Decimal('300.00'))
        self.assertEqual(self.fee.status, FeeStatus.PARTIAL)

    def test_part_payments_add_up_to_paid(self):
        """`unpaid → partial → partial → paid`, the diagram's main line."""
        collect_fee(fee=self.fee, amount=Decimal('200.00'), collected_by=self.user)
        self.fee.refresh_from_db()
        self.assertEqual(self.fee.status, FeeStatus.PARTIAL)

        collect_fee(fee=self.fee, amount=Decimal('150.50'), collected_by=self.user)
        self.fee.refresh_from_db()
        self.assertEqual(self.fee.paid_amount, Decimal('350.50'))
        self.assertEqual(self.fee.status, FeeStatus.PARTIAL)

        collect_fee(fee=self.fee, amount=Decimal('149.50'), collected_by=self.user)
        self.fee.refresh_from_db()
        self.assertEqual(self.fee.paid_amount, Decimal('500.00'))
        self.assertEqual(self.fee.balance, Decimal('0.00'))
        self.assertEqual(self.fee.status, FeeStatus.PAID)
        self.assertEqual(self.fee.payments.count(), 3)

    def test_paying_the_whole_balance_at_once_goes_straight_to_paid(self):
        collect_fee(fee=self.fee, amount=Decimal('500.00'), collected_by=self.user)
        self.fee.refresh_from_db()
        self.assertEqual(self.fee.status, FeeStatus.PAID)

    def test_over_collection_is_refused_not_clamped(self):
        """Recording ৳500 against a ৳600 payment hands out a wrong receipt."""
        with self.assertRaises(CodedError) as caught:
            collect_fee(fee=self.fee, amount=Decimal('600.00'),
                        collected_by=self.user)

        self.assertEqual(caught.exception.default_code, 'over_collection')
        self.fee.refresh_from_db()
        self.assertEqual(self.fee.paid_amount, Decimal('0.00'))
        self.assertEqual(self.fee.payments.count(), 0)

    def test_over_collection_is_measured_against_the_remaining_balance(self):
        collect_fee(fee=self.fee, amount=Decimal('300.00'), collected_by=self.user)

        with self.assertRaises(CodedError):
            collect_fee(fee=self.fee, amount=Decimal('300.00'),
                        collected_by=self.user)

        self.fee.refresh_from_db()
        self.assertEqual(self.fee.paid_amount, Decimal('300.00'))

    def test_a_fully_paid_invoice_refuses_more_money(self):
        collect_fee(fee=self.fee, amount=Decimal('500.00'), collected_by=self.user)

        with self.assertRaises(CodedError) as caught:
            collect_fee(fee=self.fee, amount=Decimal('10.00'),
                        collected_by=self.user)
        self.assertEqual(caught.exception.default_code, 'already_paid')

    def test_zero_and_negative_amounts_are_refused(self):
        for amount in (Decimal('0.00'), Decimal('-100.00')):
            with self.subTest(amount=amount):
                with self.assertRaises(CodedError):
                    collect_fee(fee=self.fee, amount=amount,
                                collected_by=self.user)

    def test_the_discount_reduces_what_is_collectable(self):
        """V1's discount is per invoice (docs/05 §5.4 — standing Discount is V2)."""
        discounted = make_fee(self.branch, self.session, student=self.student,
                              code='BOK', amount='1000.00', discount='250.00',
                              period='2026-03')
        self.assertEqual(discounted.payable, Decimal('750.00'))

        collect_fee(fee=discounted, amount=Decimal('750.00'), collected_by=self.user)
        discounted.refresh_from_db()
        self.assertEqual(discounted.status, FeeStatus.PAID)

    def test_a_fine_increases_what_is_collectable(self):
        # `fine` is an input, not a derived value — `recalculate_fee()` reads it
        # and does not save it, so the caller that changed it saves it.
        self.fee.fine = Decimal('50.00')
        self.fee.save(update_fields=['fine'])
        recalculate_fee(self.fee)

        collect_fee(fee=self.fee, amount=Decimal('550.00'), collected_by=self.user)
        self.fee.refresh_from_db()
        self.assertEqual(self.fee.payable, Decimal('550.00'))
        self.assertEqual(self.fee.status, FeeStatus.PAID)

    def test_every_stored_amount_is_a_decimal(self):
        """The rule that has to hold in the database, not only in Python."""
        payment = collect_fee(fee=self.fee, amount=Decimal('123.45'),
                              method=PaymentMethod.BKASH,
                              transaction_id='TRX1', collected_by=self.user)
        self.fee.refresh_from_db()
        payment.refresh_from_db()

        for value in (self.fee.amount, self.fee.discount, self.fee.fine,
                      self.fee.payable, self.fee.paid_amount, payment.amount):
            self.assertIsInstance(value, Decimal)
        self.assertEqual(payment.amount, Decimal('123.45'))

    def test_a_string_amount_is_read_as_the_number_it_says(self):
        """`Decimal(str(x))`, never `Decimal(float)` — 0.1 must stay 0.10."""
        collect_fee(fee=self.fee, amount='0.10', collected_by=self.user)
        self.fee.refresh_from_db()
        self.assertEqual(self.fee.paid_amount, Decimal('0.10'))


class StatusTransitionTests(FeeFixture, TestCase):
    """Every edge of docs/06 #8 that money or time can walk."""

    def setUp(self):
        self.build_fixture()
        self.branch.fine_rule = {'per_day': 10, 'grace_days': 0, 'max': 100}
        self.branch.save(update_fields=['fine_rule'])
        self.fee = make_fee(self.branch, self.session, student=self.student,
                            amount='500.00')

    def test_unpaid_to_overdue_when_the_due_date_passes(self):
        from datetime import date

        accrue_fines(self.branch, on_date=date(2026, 3, 15))
        self.fee.refresh_from_db()
        self.assertEqual(self.fee.status, FeeStatus.OVERDUE)

    def test_overdue_to_partial_when_a_part_payment_arrives(self):
        """The diagram's `overdue → partial`. The counter should show the money."""
        from datetime import date

        accrue_fines(self.branch, on_date=date(2026, 3, 15))
        self.fee.refresh_from_db()

        collect_fee(fee=self.fee, amount=Decimal('100.00'), collected_by=self.user)
        self.fee.refresh_from_db()
        self.assertEqual(self.fee.status, FeeStatus.PARTIAL)

    def test_overdue_to_paid_when_the_balance_clears(self):
        from datetime import date

        accrue_fines(self.branch, on_date=date(2026, 3, 15))
        self.fee.refresh_from_db()

        collect_fee(fee=self.fee, amount=self.fee.balance, collected_by=self.user)
        self.fee.refresh_from_db()
        self.assertEqual(self.fee.status, FeeStatus.PAID)

    def test_unpaid_to_waived_and_waived_is_terminal(self):
        waive_fee(self.fee, reason='Orphan; approved by the principal',
                  actor=self.user)
        self.fee.refresh_from_db()

        self.assertEqual(self.fee.status, FeeStatus.WAIVED)
        self.assertEqual(self.fee.waived_by, self.user)
        self.assertTrue(self.fee.waive_reason)

        with self.assertRaises(CodedError) as caught:
            collect_fee(fee=self.fee, amount=Decimal('100.00'),
                        collected_by=self.user)
        self.assertEqual(caught.exception.default_code, 'fee_waived')

    def test_partial_to_waived_keeps_the_payments_already_taken(self):
        collect_fee(fee=self.fee, amount=Decimal('200.00'), collected_by=self.user)
        waive_fee(self.fee, reason='Family hardship', actor=self.user)
        self.fee.refresh_from_db()

        self.assertEqual(self.fee.status, FeeStatus.WAIVED)
        self.assertEqual(self.fee.paid_amount, Decimal('200.00'))
        self.assertEqual(self.fee.payments.count(), 1)

    def test_a_waiver_needs_a_reason(self):
        with self.assertRaises(CodedError) as caught:
            waive_fee(self.fee, reason='', actor=self.user)
        self.assertEqual(caught.exception.default_code, 'reason_required')

    def test_status_is_never_taken_from_the_caller(self):
        """Setting it by hand does not survive the next recompute."""
        self.fee.status = FeeStatus.PAID
        self.fee.save(update_fields=['status'])

        recalculate_fee(self.fee)
        self.assertEqual(self.fee.status, FeeStatus.UNPAID)
