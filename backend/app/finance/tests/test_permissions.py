"""Income and expenses are separate permissions (docs/02 §2.1).

A clerk trusted to write up donations is not trusted to pay bills, and the
reverse. Each test names a request one clerk must be able to make and the other
must be refused — 403, because both sides are in the same institution and the
row's existence is not the secret here; the permission is.
"""

import importlib

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.permissions import preset_for
from fees.tests.factories import make_branch

migration = importlib.import_module('accounts.migrations.0003_split_finance_permission')


def client_for(branch, phone, permissions):
    user = get_user_model().objects.create_user(
        phone=phone, password='pass-phrase-1234', name=f'Clerk {phone}',
        branch=branch, user_type='teacher', permissions=permissions,
    )
    client = APIClient()
    client.force_authenticate(user)
    return client


@override_settings(ROOT_URLCONF='fees.tests.urls')
class OneSideOfTheLedgerTests(TestCase):
    def setUp(self):
        self.branch = make_branch()
        self.donation = self.branch.incomecategory_set.get(code='INC-DON')
        self.rent = self.branch.expensecategory_set.get(code='EXP-RENT')
        self.income_clerk = client_for(self.branch, '01799100001', preset_for('Income Clerk'))
        self.expense_clerk = client_for(self.branch, '01799100002', preset_for('Expense Clerk'))

    def _income(self, client):
        return client.post('/api/income/', {
            'category': self.donation.pk, 'amount': '500.00', 'date': '2026-03-05',
            'method': 'cash', 'description': 'Donation',
        }, format='json')

    def _expense(self, client):
        return client.post('/api/expenses/', {
            'category': self.rent.pk, 'amount': '800.00', 'date': '2026-03-05',
            'method': 'cash', 'description': 'Rent',
        }, format='json')

    def test_an_income_clerk_records_income_and_nothing_else(self):
        self.assertEqual(self._income(self.income_clerk).status_code, 201)
        self.assertEqual(self._expense(self.income_clerk).status_code, 403)
        self.assertEqual(self.income_clerk.get('/api/expenses/').status_code, 403)

    def test_an_expense_clerk_records_expenses_and_nothing_else(self):
        self.assertEqual(self._expense(self.expense_clerk).status_code, 201)
        self.assertEqual(self._income(self.expense_clerk).status_code, 403)
        self.assertEqual(self.expense_clerk.get('/api/income/').status_code, 403)

    def test_a_clerk_cannot_correct_an_entry(self):
        created = self._expense(self.expense_clerk)
        response = self.expense_clerk.patch(
            f'/api/expenses/{created.data["id"]}/', {'amount': '1.00'}, format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_a_clerk_cannot_add_a_head(self):
        response = self.expense_clerk.post('/api/expense-categories/', {
            'code': 'EXP-NEW', 'name': 'New head', 'name_bn': 'নতুন খাত',
        }, format='json')
        self.assertEqual(response.status_code, 403)

    def test_a_clerk_still_reads_the_heads_they_record_against(self):
        self.assertEqual(self.expense_clerk.get('/api/expense-categories/').status_code, 200)


class SplitMigrationTests(TestCase):
    """The deploy must not silently take the ledger away from anyone."""

    def test_a_users_finance_permissions_become_both_sides(self):
        self.assertEqual(
            migration.split_permissions(['fees.view', 'finance.create', 'finance.view']),
            ['expenses.create', 'expenses.view', 'fees.view', 'income.create', 'income.view'],
        )

    def test_a_roles_matrix_becomes_both_sides(self):
        self.assertEqual(
            migration.split_matrix({'dashboard': ['view'], 'finance': ['view', 'create']}),
            {'dashboard': ['view'], 'income': ['create', 'view'], 'expenses': ['create', 'view']},
        )

    def test_rows_without_finance_are_untouched(self):
        self.assertEqual(migration.split_permissions(['fees.view']), ['fees.view'])
        matrix = {'fees': ['view']}
        self.assertIs(migration.split_matrix(matrix), matrix)

    def test_it_reverses(self):
        split = migration.split_permissions(['finance.view', 'marks.enter'])
        self.assertEqual(migration.merge_permissions(split), ['finance.view', 'marks.enter'])
