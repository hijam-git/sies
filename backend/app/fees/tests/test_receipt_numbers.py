"""Receipt-number concurrency (CLAUDE.md §4.4, §8.4).

The situation this defends against is real and ordinary: two counter clerks
taking money at the same second on the first day of the month. `max() + 1`
issues 412 twice, and the duplicate surfaces on a printed receipt in a
guardian's hand.

**`TransactionTestCase`, not `TestCase`.** `TestCase` wraps every test in a
transaction that is rolled back, so a second thread would never see the first
thread's rows and `select_for_update` would have nothing to block on — the test
would pass without testing anything. This class lets each thread commit for
real, which is the only way the row lock is exercised.
"""

import threading
from decimal import Decimal

from django.db import connections
from django.test import TransactionTestCase

from fees.models import Fee, Payment
from fees.services import collect_fee

from .factories import FeeFixture, make_fee, make_student


class ReceiptNumberConcurrencyTests(FeeFixture, TransactionTestCase):
    # Each test commits for real, so the tables are truncated between tests.
    # Resetting the sequences keeps a failure message's ids readable rather
    # than climbing with every test that ran before it.
    reset_sequences = True

    def setUp(self):
        self.build_fixture()

    def _collect_in_thread(self, fee_id, errors, receipts, amount=None):
        try:
            fee = Fee.objects.get(pk=fee_id)
            payment = collect_fee(fee=fee, amount=amount or Decimal('100.00'),
                                  collected_by=self.user)
            receipts.append(payment.receipt_no)
        except Exception as error:  # noqa: BLE001 — reported, then asserted on
            errors.append(error)
        finally:
            # Each thread gets its own connection; leaking them exhausts
            # Postgres' connection slots long before the suite finishes.
            connections.close_all()

    def test_eight_simultaneous_collections_get_eight_consecutive_numbers(self):
        """Distinct, consecutive, no gaps, no duplicates.

        Eight separate invoices rather than eight payments against one, so the
        only thing the threads contend on is the *counter* — contention on a
        single invoice is the over-collection test's job, not this one.
        """
        fees = [
            make_fee(self.branch, self.session,
                     student=make_student(self.branch, name=f'Student {i}'),
                     code='MON', amount='500.00', period=f'2026-{i + 1:02d}')
            for i in range(8)
        ]

        errors, receipts = [], []
        threads = [
            threading.Thread(target=self._collect_in_thread,
                             args=(fee.pk, errors, receipts))
            for fee in fees
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        self.assertEqual(errors, [], f'threads raised: {errors}')
        self.assertEqual(len(receipts), 8)

        # No duplicates.
        self.assertEqual(len(set(receipts)), 8)

        # No gaps: the numeric tails are exactly 1..8.
        tails = sorted(int(no.rsplit('-', 1)[1]) for no in receipts)
        self.assertEqual(tails, list(range(1, 9)))

        # And the branch code is in every one of them, because that is what a
        # person reads out to say which institution issued the receipt.
        for receipt_no in receipts:
            self.assertTrue(receipt_no.startswith(f'RCP-{self.branch.code}-'))

        self.assertEqual(Payment.objects.count(), 8)

    def test_two_clerks_cannot_over_collect_the_same_invoice(self):
        """The invoice row lock, not the counter lock.

        Both threads read a 500 taka balance and both try to take 400. Without
        the `select_for_update` on the Fee they would both succeed and the
        invoice would hold 800 against a 500 charge — money that is real, so
        the error surfaces as an over-collection nobody can explain rather than
        as a failed request.
        """
        fee = make_fee(self.branch, self.session, student=self.student,
                       amount='500.00')

        errors, receipts = [], []
        threads = [
            threading.Thread(target=self._collect_in_thread,
                             args=(fee.pk, errors, receipts, Decimal('400.00')))
            for _ in range(2)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        # One receipt, one refusal. Never two receipts.
        self.assertEqual(len(receipts), 1, f'both threads collected: {receipts}')
        self.assertEqual(len(errors), 1)
        self.assertEqual(getattr(errors[0], 'default_code', None), 'over_collection')

        fee.refresh_from_db()
        self.assertEqual(fee.paid_amount, Decimal('400.00'))
        self.assertLessEqual(fee.paid_amount, fee.payable)
