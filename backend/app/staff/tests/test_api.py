"""Branch isolation on every staff endpoint — 404, not 403.

403 confirms the row exists, which is exactly what a probe is looking for
(CLAUDE.md §5). Every account here holds the whole permission catalogue, so a
refusal proves the *branch* check refused it and not that the account happened to
lack `teachers.view`.
"""

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from staff.models import Employee, Teacher

from .factories import (make_branch, make_employee, make_teacher,
                        make_user)


@override_settings(ROOT_URLCONF='staff.tests.urls')
class StaffBranchIsolationTests(TestCase):
    def setUp(self):
        self.a = make_branch(code='DHK', name='Dhaka Madrasah')
        self.b = make_branch(code='CTG', name='Chittagong Madrasah')
        self.a_teacher = make_teacher(self.a, name='Dhaka Teacher')
        self.b_teacher = make_teacher(self.b, name='Chittagong Teacher')
        self.b_employee = make_employee(self.b, name='Chittagong Cook')

        self.client = APIClient()
        self.client.force_authenticate(make_user(self.a, phone='01711000001'))

    def test_another_branchs_teacher_is_404(self):
        response = self.client.get(f'/api/teachers/{self.b_teacher.pk}/')
        self.assertEqual(response.status_code, 404)

    def test_another_branchs_employee_is_404(self):
        response = self.client.get(f'/api/employees/{self.b_employee.pk}/')
        self.assertEqual(response.status_code, 404)

    def test_another_branchs_teacher_cannot_be_written_either(self):
        """404 on read is only half of it: writing into an invisible row is worse."""
        response = self.client.patch(
            f'/api/teachers/{self.b_teacher.pk}/', {'name': 'Renamed'}, format='json',
        )
        self.assertEqual(response.status_code, 404)
        self.b_teacher.refresh_from_db()
        self.assertNotEqual(self.b_teacher.name, 'Renamed')

    def test_another_branchs_teacher_cannot_be_deleted_either(self):
        response = self.client.delete(f'/api/teachers/{self.b_teacher.pk}/')
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Teacher.objects.filter(pk=self.b_teacher.pk).exists())

    def test_the_list_shows_only_the_callers_own_institution(self):
        response = self.client.get('/api/teachers/')
        self.assertEqual(response.status_code, 200)
        names = {row['name'] for row in response.data['results']}
        self.assertEqual(names, {'Dhaka Teacher'})

    def test_the_qualifications_action_is_404_for_another_branchs_teacher(self):
        response = self.client.get(f'/api/teachers/{self.b_teacher.pk}/qualifications/')
        self.assertEqual(response.status_code, 404)


@override_settings(ROOT_URLCONF='staff.tests.urls')
class StaffCreationTests(TestCase):
    def setUp(self):
        self.branch = make_branch(code='DHK')
        self.client = APIClient()
        self.client.force_authenticate(make_user(self.branch, phone='01711000001'))

    def test_creating_a_teacher_issues_the_id_server_side(self):
        response = self.client.post(
            '/api/teachers/', {'name': 'New Teacher', 'phone': '01712000002'},
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['teacher_id'], 'TCH-DHK-0001')

    def test_a_client_supplied_teacher_id_is_ignored(self):
        """A client-chosen id is a client-chosen collision (CLAUDE.md §4.4)."""
        response = self.client.post(
            '/api/teachers/',
            {'name': 'New Teacher', 'teacher_id': 'TCH-DHK-9999'},
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['teacher_id'], 'TCH-DHK-0001')

    def test_a_client_supplied_branch_is_ignored(self):
        """CLAUDE.md §1: the branch is stamped server-side, never sent."""
        other = make_branch(code='CTG', name='Chittagong Madrasah')

        response = self.client.post(
            '/api/employees/', {'name': 'New Cook', 'branch': other.pk}, format='json',
        )

        self.assertEqual(response.status_code, 201, response.data)
        created = Employee.objects.get(pk=response.data['id'])
        self.assertEqual(created.branch_id, self.branch.pk)

    def test_a_login_from_another_institution_is_rejected(self):
        other = make_branch(code='CTG', name='Chittagong Madrasah')
        foreign_user = make_user(other, phone='01799000009')

        response = self.client.post(
            '/api/teachers/', {'name': 'New Teacher', 'user': foreign_user.pk},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('user', response.data.get('errors', response.data))
