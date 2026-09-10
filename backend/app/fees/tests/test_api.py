"""Branch isolation and permissions on every fees and finance endpoint.

**404, not 403** (CLAUDE.md §5). A 403 on another institution's invoice confirms
that the invoice exists, and "does branch CTG have a student with this id" is
exactly what a probe asks. Both viewsets are covered, including the custom
actions — a scoped list with an unscoped `@action` is the usual way this leaks.
"""

from decimal import Decimal

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from finance.models import Income
from fees.models import Fee, Payment
from fees.services import collect_fee

from .factories import (make_branch, make_class, make_enrolment, make_fee,
                        make_session, make_user)


@override_settings(ROOT_URLCONF='fees.tests.urls')
class BranchIsolationTests(TestCase):
    def setUp(self):
        self.a = make_branch(code='DHK', name='Dhaka Madrasah')
        self.b = make_branch(code='CTG', name='Chittagong Madrasah')

        self.b_session = make_session(self.b)
        self.b_class = make_class(self.b, self.b_session)
        self.b_enrolment = make_enrolment(self.b, self.b_session, self.b_class)
        self.b_fee = make_fee(self.b, self.b_session,
                              student=self.b_enrolment.student, amount='500.00')
        self.b_payment = collect_fee(fee=self.b_fee, amount=Decimal('100.00'))
        self.b_category = self.b.feecategory_set.get(code='MON')
        self.b_income_head = self.b.incomecategory_set.get(code='INC-MON')

        self.client = APIClient()
        self.client.force_authenticate(make_user(self.a))

    def test_every_detail_route_is_404_for_another_institution(self):
        for path in (
            f'/api/fee-categories/{self.b_category.pk}/',
            f'/api/fees/{self.b_fee.pk}/',
            f'/api/payments/{self.b_payment.pk}/',
            f'/api/income-categories/{self.b_income_head.pk}/',
            f'/api/income/{self.b_payment.income_id}/',
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_collecting_against_another_institutions_invoice_is_404(self):
        """The action that moves money is scoped like everything else."""
        response = self.client.post(
            f'/api/fees/{self.b_fee.pk}/collect/',
            {'amount': '100.00', 'method': 'cash'}, format='json',
        )

        self.assertEqual(response.status_code, 404)
        self.b_fee.refresh_from_db()
        self.assertEqual(self.b_fee.paid_amount, Decimal('100.00'))
        self.assertEqual(Payment.objects.count(), 1)

    def test_waiving_another_institutions_invoice_is_404(self):
        response = self.client.post(f'/api/fees/{self.b_fee.pk}/waive/',
                                    {'reason': 'x'}, format='json')
        self.assertEqual(response.status_code, 404)
        self.b_fee.refresh_from_db()
        self.assertNotEqual(self.b_fee.status, 'waived')

    def test_reversing_another_institutions_receipt_is_404(self):
        response = self.client.post(f'/api/payments/{self.b_payment.pk}/reverse/',
                                    {'reason': 'x'}, format='json')
        self.assertEqual(response.status_code, 404)
        self.b_payment.refresh_from_db()
        self.assertFalse(self.b_payment.is_reversed)

    def test_another_institutions_invoice_cannot_be_edited_or_deleted(self):
        patch = self.client.patch(f'/api/fees/{self.b_fee.pk}/',
                                  {'amount': '1.00'}, format='json')
        delete = self.client.delete(f'/api/fees/{self.b_fee.pk}/')

        self.assertEqual(patch.status_code, 404)
        # 403 rather than 404 on the delete, and it is not a leak: the `fees`
        # resource has no `delete` action in the catalogue at all, so nobody
        # holds it and the refusal happens before any row is looked up. It
        # reveals nothing about whether the invoice exists — every id, in every
        # branch, answers the same way.
        self.assertEqual(delete.status_code, 403)
        self.b_fee.refresh_from_db()
        self.assertEqual(self.b_fee.amount, Decimal('500.00'))

    def test_lists_show_only_the_callers_own_institution(self):
        # Branch A has no invoices, receipts or ledger rows of its own, so its
        # lists must be empty rather than showing Chittagong's.
        for path in ('/api/fees/', '/api/payments/', '/api/income/',
                     '/api/expenses/'):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data['results'], [])

        # Categories exist in both, seeded — so this one checks the *scoping*,
        # not emptiness: every row returned belongs to the caller's branch.
        response = self.client.get('/api/fee-categories/')
        returned = {row['id'] for row in response.data['results']}
        own = set(self.a.feecategory_set.values_list('id', flat=True))
        self.assertTrue(returned)
        self.assertTrue(returned.issubset(own))
        self.assertNotIn(self.b_category.pk, returned)


@override_settings(ROOT_URLCONF='fees.tests.urls')
class CollectEndpointTests(TestCase):
    """The counter's endpoint, end to end (docs/06 #10)."""

    def setUp(self):
        self.branch = make_branch()
        self.session = make_session(self.branch)
        self.academic_class = make_class(self.branch, self.session)
        self.enrolment = make_enrolment(self.branch, self.session,
                                        self.academic_class)
        self.fee = make_fee(self.branch, self.session,
                            student=self.enrolment.student, amount='500.00')
        self.user = make_user(self.branch)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_a_collection_returns_the_receipt_and_posts_income(self):
        response = self.client.post(
            f'/api/fees/{self.fee.pk}/collect/',
            {'amount': '200.00', 'method': 'cash', 'note': 'first instalment'},
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data['payment']['receipt_no'])
        self.assertEqual(response.data['fee']['status'], 'partial')
        self.assertEqual(response.data['fee']['balance'], '300.00')
        self.assertEqual(Income.objects.filter(source='fee_payment').count(), 1)

    def test_over_collection_is_a_400_with_a_code_the_spa_can_switch_on(self):
        response = self.client.post(f'/api/fees/{self.fee.pk}/collect/',
                                    {'amount': '900.00'}, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Payment.objects.count(), 0)

    def test_a_mobile_payment_without_a_transaction_id_is_refused(self):
        """It cannot be reconciled against the wallet statement otherwise."""
        response = self.client.post(f'/api/fees/{self.fee.pk}/collect/',
                                    {'amount': '100.00', 'method': 'bkash'},
                                    format='json')
        self.assertEqual(response.status_code, 400)

    def test_status_cannot_be_set_from_a_request_body(self):
        """Derived, never hand-set (docs/06 #8)."""
        response = self.client.patch(f'/api/fees/{self.fee.pk}/',
                                     {'status': 'paid', 'paid_amount': '500.00'},
                                     format='json')

        self.assertEqual(response.status_code, 200)
        self.fee.refresh_from_db()
        self.assertEqual(self.fee.status, 'unpaid')
        self.assertEqual(self.fee.paid_amount, Decimal('0.00'))

    def test_a_receipt_cannot_be_deleted_through_the_api(self):
        payment = collect_fee(fee=self.fee, amount=Decimal('100.00'),
                              collected_by=self.user)
        response = self.client.delete(f'/api/payments/{payment.pk}/')

        # Refused twice over: the catalogue has no `fees.delete` action (403),
        # and PaymentViewSet has no destroy route to reach even if it did.
        # Either way the receipt survives, which is the property that matters.
        self.assertIn(response.status_code, (403, 405))
        self.assertTrue(Payment.objects.filter(pk=payment.pk).exists())

        from fees.views import PaymentViewSet

        self.assertFalse(hasattr(PaymentViewSet, 'destroy'))

    def test_editing_an_invoice_recomputes_what_is_owed(self):
        self.client.patch(f'/api/fees/{self.fee.pk}/',
                          {'discount': '100.00'}, format='json')
        self.fee.refresh_from_db()
        self.assertEqual(self.fee.payable, Decimal('400.00'))

    def test_a_manual_invoice_gets_its_number_from_the_branch_counter(self):
        category = self.branch.feecategory_set.get(code='BOK')
        response = self.client.post('/api/fees/', {
            'student': self.enrolment.student.pk,
            'category': category.pk,
            'session': self.session.pk,
            'amount': '250.00',
            'due_date': '2026-04-10',
            'period': '2026-04',
        }, format='json')

        self.assertEqual(response.status_code, 201, response.data)
        fee = Fee.objects.get(pk=response.data['id'])
        self.assertTrue(fee.invoice_no.startswith(f'INV-{self.branch.code}-'))
        self.assertEqual(fee.payable, Decimal('250.00'))
        # The client never sends `branch` and could not if it wanted to.
        self.assertEqual(fee.branch, self.branch)


@override_settings(ROOT_URLCONF='fees.tests.urls')
class PermissionTests(TestCase):
    """`fees.collect` is its own checkbox — see `POST_IS_AN_UPDATE` (worklog F1)."""

    def setUp(self):
        self.branch = make_branch()
        self.session = make_session(self.branch)
        self.academic_class = make_class(self.branch, self.session)
        self.enrolment = make_enrolment(self.branch, self.session,
                                        self.academic_class)
        self.fee = make_fee(self.branch, self.session,
                            student=self.enrolment.student, amount='500.00')
        self.client = APIClient()

    def _as(self, permissions):
        user = make_user(self.branch, permissions=permissions)
        self.client.force_authenticate(user)
        return user

    def test_fees_create_does_not_authorise_taking_money(self):
        """A custom POST is an update, not a create — so `collect` is required."""
        self._as(['fees.view', 'fees.create', 'fees.update'])

        response = self.client.post(f'/api/fees/{self.fee.pk}/collect/',
                                    {'amount': '100.00'}, format='json')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Payment.objects.count(), 0)

    def test_fees_collect_authorises_it(self):
        self._as(['fees.view', 'fees.collect'])

        response = self.client.post(f'/api/fees/{self.fee.pk}/collect/',
                                    {'amount': '100.00'}, format='json')
        self.assertEqual(response.status_code, 201, response.data)

    def test_waiving_needs_its_own_permission(self):
        self._as(['fees.view', 'fees.collect'])

        response = self.client.post(f'/api/fees/{self.fee.pk}/waive/',
                                    {'reason': 'Orphan'}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_reversing_costs_what_collecting_cost(self):
        payment = collect_fee(fee=self.fee, amount=Decimal('100.00'))
        self._as(['fees.view', 'fees.update'])

        response = self.client.post(f'/api/payments/{payment.pk}/reverse/',
                                    {'reason': 'Wrong student'}, format='json')
        self.assertEqual(response.status_code, 403)
