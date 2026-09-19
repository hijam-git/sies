"""Writing a pointer at another institution's row (CLAUDE.md §5).

A branch-scoped queryset decides what a caller can **read**. Nothing about a
plain `PrimaryKeyRelatedField` stops them **writing** one: these tests are the
POST and PATCH half of branch isolation, which the read tests next door cannot
see. The invoice case is the one that mattered — an invoice raised in my branch
against another institution's student, which `collect/` would then take money
on and post to my income.
"""

from decimal import Decimal

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from fees.models import Fee

from .factories import (category, make_branch, make_class, make_enrolment,
                        make_fee, make_session, make_user)


@override_settings(ROOT_URLCONF='fees.tests.urls')
class ForeignKeyWriteTests(TestCase):
    def setUp(self):
        self.a = make_branch(code='DHK', name='Dhaka Madrasah')
        self.b = make_branch(code='CTG', name='Chittagong Madrasah')

        self.a_session = make_session(self.a)
        self.a_class = make_class(self.a, self.a_session)
        self.a_enrolment = make_enrolment(self.a, self.a_session, self.a_class)

        self.b_session = make_session(self.b)
        self.b_class = make_class(self.b, self.b_session)
        self.b_enrolment = make_enrolment(self.b, self.b_session, self.b_class)

        self.client = APIClient()
        self.client.force_authenticate(make_user(self.a))

    def test_an_invoice_cannot_be_raised_against_another_institutions_student(self):
        response = self.client.post(
            '/api/fees/',
            {
                'student': self.b_enrolment.student_id,
                'category': category(self.a, 'MON').pk,
                'session': self.a_session.pk,
                'amount': '500.00',
                'due_date': '2026-03-10',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('student', response.data.get('errors', response.data))
        self.assertFalse(Fee.objects.filter(student=self.b_enrolment.student).exists())

    def test_an_invoice_cannot_be_repointed_at_another_institutions_student(self):
        """PATCH, not POST: the same hole, through the other verb."""
        fee = make_fee(self.a, self.a_session, student=self.a_enrolment.student)

        response = self.client.patch(
            f'/api/fees/{fee.pk}/',
            {'student': self.b_enrolment.student_id}, format='json',
        )

        self.assertEqual(response.status_code, 400)
        fee.refresh_from_db()
        self.assertEqual(fee.student_id, self.a_enrolment.student_id)

    def test_an_invoice_cannot_be_billed_under_another_institutions_head(self):
        response = self.client.post(
            '/api/fees/',
            {
                'student': self.a_enrolment.student_id,
                'category': category(self.b, 'MON').pk,
                'session': self.a_session.pk,
                'amount': '500.00',
                'due_date': '2026-03-10',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('category', response.data.get('errors', response.data))

    def test_a_ledger_row_cannot_be_posted_under_another_institutions_head(self):
        response = self.client.post(
            '/api/expenses/',
            {
                'category': self.b.expensecategory_set.first().pk,
                'amount': '100.00',
                'date': '2026-03-10',
                'description': 'Chalk',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('category', response.data.get('errors', response.data))

    def test_a_voucher_cannot_approve_itself(self):
        """`is_approved` is read-only: an approval with no approver is worse
        than none, because the ledger claims one happened."""
        response = self.client.post(
            '/api/expenses/',
            {
                'category': self.a.expensecategory_set.first().pk,
                'amount': '100.00',
                'date': '2026-03-10',
                'description': 'Chalk',
                'is_approved': True,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.data['is_approved'])

    def test_a_platform_admins_branch_parameter_is_the_branch_that_is_checked(self):
        """The trap the per-module copies of this check fell into.

        `?branch=5` arrives as a **string**, `getattr(branch, 'pk', None)` read
        None for it, and the guard concluded it could not tell — so every FK went
        unchecked for exactly the account that can reach every institution.
        """
        self.client.force_authenticate(make_user(None, user_type='platform_admin'))

        response = self.client.post(
            f'/api/fees/?branch={self.a.pk}',
            {
                'student': self.b_enrolment.student_id,
                'category': category(self.a, 'MON').pk,
                'session': self.a_session.pk,
                'amount': '500.00',
                'due_date': '2026-03-10',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Fee.objects.filter(student=self.b_enrolment.student).exists())
