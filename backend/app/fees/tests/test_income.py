"""Income auto-posting — the one cross-module write (docs/02 §4.6, docs/06 #10).

Two properties, and the second is the one that is easy to get wrong:

1. a collection writes **exactly one** Income row, `source='fee_payment'`,
   linked to the payment and posted to the head mapped from the fee category;
2. a collection that **rolls back writes neither** — no receipt, and no income.

Property 2 is why `post_payment_income()` has no `transaction.atomic()` of its
own. Give it one and it becomes a savepoint that can commit while the payment
rolls back, and the ledger gains income for money nobody received.
"""

from decimal import Decimal

from django.db import transaction
from django.test import TestCase

from finance.models import EntrySource, Income
from fees.models import Payment
from fees.services import collect_fee

from .factories import FeeFixture, make_fee


class IncomeAutoPostingTests(FeeFixture, TestCase):
    def setUp(self):
        self.build_fixture()
        self.fee = make_fee(self.branch, self.session, student=self.student,
                            code='MON', amount='500.00')

    def test_a_collection_writes_exactly_one_linked_income_row(self):
        payment = collect_fee(fee=self.fee, amount=Decimal('500.00'),
                              collected_by=self.user)

        rows = Income.objects.filter(payment=payment)
        self.assertEqual(rows.count(), 1)

        income = rows.get()
        self.assertEqual(income.source, EntrySource.FEE_PAYMENT)
        self.assertEqual(income.amount, Decimal('500.00'))
        self.assertEqual(income.branch, self.branch)
        self.assertEqual(income.session, self.session)
        self.assertEqual(income.recorded_by, self.user)
        # The back-link both ways: the SPA's receipt screen reads one, the
        # ledger screen reads the other.
        self.assertEqual(payment.income, income)

    def test_it_posts_to_the_head_mapped_from_the_fee_category(self):
        """The `fee_category` link on IncomeCategory is what makes this work."""
        payment = collect_fee(fee=self.fee, amount=Decimal('500.00'),
                              collected_by=self.user)

        self.assertEqual(payment.income.category.code, 'INC-MON')
        self.assertEqual(payment.income.category.fee_category.code, 'MON')

    def test_an_unmapped_category_lands_in_the_catch_all_not_a_null_head(self):
        """Uniform Fee has no seeded income head of its own (docs/03 §8)."""
        uniform = make_fee(self.branch, self.session, student=self.student,
                           code='UNI', amount='300.00', period='2026-03')
        payment = collect_fee(fee=uniform, amount=Decimal('300.00'),
                              collected_by=self.user)

        self.assertEqual(payment.income.category.code, 'INC-OTH')

    def test_the_income_carries_the_receipt_number_for_tracing(self):
        payment = collect_fee(fee=self.fee, amount=Decimal('500.00'),
                              collected_by=self.user)
        self.assertEqual(payment.income.reference, payment.receipt_no)
        self.assertIn(payment.receipt_no, payment.income.description)

    def test_part_payments_post_one_income_row_each(self):
        first = collect_fee(fee=self.fee, amount=Decimal('200.00'),
                            collected_by=self.user)
        second = collect_fee(fee=self.fee, amount=Decimal('300.00'),
                             collected_by=self.user)

        self.assertEqual(Income.objects.count(), 2)
        self.assertEqual(first.income.amount, Decimal('200.00'))
        self.assertEqual(second.income.amount, Decimal('300.00'))
        self.assertNotEqual(first.income_id, second.income_id)

    def test_a_rolled_back_collection_writes_neither_row(self):
        """The property the single transaction exists for.

        The outer `atomic` is rolled back after a successful collection, which
        is what a failure *after* `collect_fee()` returns looks like — a
        validation error later in the request, a failed audit write, a crash.
        Neither the receipt nor the income may survive it.
        """
        try:
            with transaction.atomic():
                collect_fee(fee=self.fee, amount=Decimal('500.00'),
                            collected_by=self.user)
                self.assertEqual(Payment.objects.count(), 1)
                self.assertEqual(Income.objects.count(), 1)
                raise RuntimeError('something later in the request failed')
        except RuntimeError:
            pass

        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(Income.objects.count(), 0)
        self.fee.refresh_from_db()
        self.assertEqual(self.fee.paid_amount, Decimal('0.00'))

    def test_a_refused_collection_writes_neither_row(self):
        """The everyday version: the amount is wrong, so nothing happens."""
        from accounts.services import CodedError

        with self.assertRaises(CodedError):
            collect_fee(fee=self.fee, amount=Decimal('900.00'),
                        collected_by=self.user)

        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(Income.objects.count(), 0)

    def test_income_totals_use_decimals(self):
        from django.db.models import DecimalField, Sum

        collect_fee(fee=self.fee, amount=Decimal('333.33'), collected_by=self.user)
        total = Income.objects.aggregate(
            total=Sum('amount', output_field=DecimalField(max_digits=12,
                                                          decimal_places=2)),
        )['total']

        self.assertIsInstance(total, Decimal)
        self.assertEqual(total, Decimal('333.33'))
