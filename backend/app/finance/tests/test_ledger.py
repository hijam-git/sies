"""The ledger: manual entry, voucher numbering, and the read-only rule.

The fixture is `fees.tests.factories` rather than one of this app's own. That
is not laziness: a finance test that could not see a fee collection could not
test the only interesting thing about this module — that a receipt writes its
own income row and that nobody may then edit it (docs/02 §4.6).
"""

from decimal import Decimal

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.services import CodedError
from fees.services import collect_fee
from fees.tests.factories import (make_branch, make_class, make_enrolment,
                                  make_fee, make_session, make_user)
from finance.models import EntrySource, Expense, Income
from finance.services import (record_expense, record_income, reverse_income)


class LedgerServiceTests(TestCase):
    def setUp(self):
        self.branch = make_branch()
        self.session = make_session(self.branch)
        self.user = make_user(self.branch)
        self.donation_head = self.branch.incomecategory_set.get(code='INC-DON')
        self.rent_head = self.branch.expensecategory_set.get(code='EXP-RENT')

    def test_manual_income_gets_a_gapless_voucher_number(self):
        first = record_income(branch=self.branch, category=self.donation_head,
                              amount='5000.00', recorded_by=self.user)
        second = record_income(branch=self.branch, category=self.donation_head,
                               amount='2500.50', recorded_by=self.user)

        self.assertEqual(first.voucher_no, f'RV-{self.branch.code}-000001')
        self.assertEqual(second.voucher_no, f'RV-{self.branch.code}-000002')
        self.assertEqual(first.source, EntrySource.MANUAL)
        self.assertIsInstance(second.amount, Decimal)
        self.assertEqual(second.amount, Decimal('2500.50'))

    def test_income_and_expense_vouchers_run_on_separate_counters(self):
        """Two books. A shared series would make "voucher 41" ambiguous."""
        income = record_income(branch=self.branch, category=self.donation_head,
                               amount='100.00', recorded_by=self.user)
        expense = record_expense(branch=self.branch, category=self.rent_head,
                                 amount='100.00', recorded_by=self.user)

        self.assertEqual(income.voucher_no, f'RV-{self.branch.code}-000001')
        self.assertEqual(expense.voucher_no, f'PV-{self.branch.code}-000001')

    def test_zero_and_negative_entries_are_refused(self):
        for amount in ('0.00', '-10.00'):
            with self.subTest(amount=amount):
                with self.assertRaises(CodedError):
                    record_income(branch=self.branch,
                                  category=self.donation_head, amount=amount)

    def test_reversing_a_row_keeps_it_and_records_why(self):
        entry = record_income(branch=self.branch, category=self.donation_head,
                              amount='9000.00', recorded_by=self.user)
        reverse_income(entry, reason='Cheque bounced', actor=self.user)
        entry.refresh_from_db()

        self.assertTrue(entry.is_reversed)
        self.assertEqual(entry.reverse_reason, 'Cheque bounced')
        self.assertEqual(entry.reversed_by, self.user)
        # Still there. A reversed row that vanished would change a closed
        # month's P&L with nothing to say why.
        self.assertTrue(Income.objects.filter(pk=entry.pk).exists())

    def test_an_expense_records_and_totals_as_a_decimal(self):
        entry = record_expense(branch=self.branch, category=self.rent_head,
                               amount='9000.00', recorded_by=self.user)

        self.assertIsInstance(entry.amount, Decimal)
        self.assertEqual(Expense.objects.get(pk=entry.pk).amount,
                         Decimal('9000.00'))


@override_settings(ROOT_URLCONF='fees.tests.urls')
class AutoPostedRowsAreReadOnlyTests(TestCase):
    """A row the system posted belongs to the document it came from."""

    def setUp(self):
        self.branch = make_branch()
        self.session = make_session(self.branch)
        self.academic_class = make_class(self.branch, self.session)
        self.enrolment = make_enrolment(self.branch, self.session,
                                        self.academic_class)
        self.fee = make_fee(self.branch, self.session,
                            student=self.enrolment.student, amount='500.00')
        self.user = make_user(self.branch)
        self.payment = collect_fee(fee=self.fee, amount=Decimal('500.00'),
                                   collected_by=self.user)

        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_a_fee_payment_row_cannot_be_edited(self):
        response = self.client.patch(f'/api/income/{self.payment.income_id}/',
                                     {'amount': '1.00'}, format='json')

        self.assertEqual(response.status_code, 400)
        self.payment.income.refresh_from_db()
        self.assertEqual(self.payment.income.amount, Decimal('500.00'))

    def test_a_fee_payment_row_cannot_be_deleted(self):
        response = self.client.delete(f'/api/income/{self.payment.income_id}/')

        # 403: the `income` resource has no `delete` action in the catalogue,
        # so the request is refused before the viewset's own rule is reached.
        # The row survives either way, which is the property being held.
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Income.objects.filter(pk=self.payment.income_id,
                                              is_active=True).exists())

    def test_a_fee_payment_row_cannot_be_reversed_directly(self):
        """Reverse the receipt instead — that reverses both, together."""
        response = self.client.post(
            f'/api/income/{self.payment.income_id}/reverse/',
            {'reason': 'oops'}, format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_a_manual_row_created_through_the_api_is_manual_and_editable(self):
        head = self.branch.incomecategory_set.get(code='INC-DON')
        created = self.client.post('/api/income/', {
            'category': head.pk, 'amount': '1000.00', 'date': '2026-03-05',
            'method': 'cash', 'description': 'Eid donation',
        }, format='json')

        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data['source'], 'manual')
        self.assertTrue(created.data['voucher_no'].startswith(f'RV-{self.branch.code}-'))

        edited = self.client.patch(f'/api/income/{created.data["id"]}/',
                                   {'description': 'Eid donation, corrected'},
                                   format='json')
        self.assertEqual(edited.status_code, 200)

    def test_source_cannot_be_forged_from_a_request_body(self):
        head = self.branch.incomecategory_set.get(code='INC-DON')
        created = self.client.post('/api/income/', {
            'category': head.pk, 'amount': '10.00', 'date': '2026-03-05',
            'source': 'fee_payment',
        }, format='json')

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data['source'], 'manual')

    def test_the_summary_excludes_reversed_rows(self):
        from fees.services import reverse_payment

        response = self.client.get('/api/income/summary/')
        self.assertEqual(response.data['total'], '500.00')

        reverse_payment(self.payment, reason='Wrong student', actor=self.user)
        response = self.client.get('/api/income/summary/')
        self.assertEqual(response.data['total'], '0.00')
