"""Who may set what a month costs.

A fee head is the institution's price list — `default_amount` is raised onto
every invoice generated from it. Writing one is therefore `settings.update`,
which the permission catalogue's own hint says covers fee categories, and not
`fees.create`, which an admission officer holds in order to take an admission.
Reading stays `fees.view`: every collection screen needs the list.
"""

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .factories import category, make_branch, make_user


@override_settings(ROOT_URLCONF='fees.tests.urls')
class FeeHeadPermissionTests(TestCase):
    def setUp(self):
        self.branch = make_branch()
        self.head = category(self.branch, 'MON')

    def client_with(self, permissions):
        client = APIClient()
        client.force_authenticate(make_user(self.branch, permissions=permissions))
        return client

    def test_an_admission_officer_may_read_the_heads(self):
        response = self.client_with(['fees.view', 'fees.create']).get('/api/fee-categories/')

        self.assertEqual(response.status_code, 200)

    def test_an_admission_officer_may_not_reprice_one(self):
        response = self.client_with(['fees.view', 'fees.create']).patch(
            f'/api/fee-categories/{self.head.pk}/', {'default_amount': '9999.00'},
            format='json',
        )

        self.assertEqual(response.status_code, 403)
        self.head.refresh_from_db()
        self.assertNotEqual(self.head.default_amount, 9999)

    def test_an_admission_officer_may_not_add_a_head(self):
        response = self.client_with(['fees.view', 'fees.create']).post(
            '/api/fee-categories/',
            {'code': 'ELC', 'name': 'Electricity', 'recurrence': 'monthly'},
            format='json',
        )

        self.assertEqual(response.status_code, 403)

    def test_whoever_runs_the_institutions_settings_may(self):
        response = self.client_with(['fees.view', 'settings.view', 'settings.update']).patch(
            f'/api/fee-categories/{self.head.pk}/', {'default_amount': '750.00'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.head.refresh_from_db()
        self.assertEqual(str(self.head.default_amount), '750.00')
