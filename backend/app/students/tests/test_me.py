"""`/api/me/` — self-service, and the id a student must never be able to change.

docs/02 §2.5 and docs/08 D4. These endpoints are not a weak `students.view`:
the queryset is `request.user`'s own record. The tests that matter here are the
negative ones — a student reaching for somebody else's row, and getting nothing.
"""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from students.models import Document
from students.services import enable_student_login

from . import factories as f


class SelfServiceTests(TestCase):
    def setUp(self):
        self.branch = f.make_branch()

        self.me = f.make_student(self.branch, name='Abdullah', phone='01712345678')
        self.other = f.make_student(self.branch, name='Bilal', phone='01712345679')

        self.my_user = enable_student_login(self.me, password='pass-phrase-1234')
        enable_student_login(self.other, password='pass-phrase-1234')

        self.my_guardian = f.make_guardian(self.branch, name='Golam Rasul',
                                           phone='01799000001', nid='1234567890',
                                           monthly_income='25000.00')
        f.link(self.me, self.my_guardian)

        self.my_document = self._document(self.me, 'My birth certificate')
        self.other_document = self._document(self.other, 'Their birth certificate')

        self.client = APIClient()
        self.client.force_authenticate(user=self.my_user)

    def _document(self, student, title):
        return Document.objects.create(
            branch=student.branch, student=student, owner_type='student',
            doc_type='birth_certificate', title=title,
            file=SimpleUploadedFile('bc.txt', b'scan', content_type='text/plain'),
        )

    def test_profile_returns_the_callers_own_record(self):
        response = self.client.get('/api/me/profile/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['student_id'], self.me.student_id)
        self.assertEqual(response.data['name'], 'Abdullah')

    def test_a_student_cannot_reach_another_students_document_by_id(self):
        """The whole point of docs/02 §2.5, tested directly."""
        response = self.client.get(f'/api/me/documents/{self.other_document.pk}/')
        self.assertEqual(response.status_code, 404)

        download = self.client.get(
            f'/api/me/documents/{self.other_document.pk}/download/')
        self.assertEqual(download.status_code, 404)

    def test_the_document_list_holds_only_the_callers_own(self):
        response = self.client.get('/api/me/documents/')

        self.assertEqual(response.status_code, 200)
        titles = [row['title'] for row in response.data]
        self.assertEqual(titles, ['My birth certificate'])

    def test_a_student_can_download_their_own_document(self):
        response = self.client.get(f'/api/me/documents/{self.my_document.pk}/download/')
        self.assertEqual(response.status_code, 200)

    def test_guardians_show_contact_details_and_not_the_private_ones(self):
        """A student may see who is phoned about them, not their father's NID."""
        response = self.client.get('/api/me/guardians/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]['phone'], '01799000001')
        self.assertNotIn('nid', response.data[0])
        self.assertNotIn('monthly_income', response.data[0])

    def test_self_service_grants_nothing_on_the_staff_endpoints(self):
        """A student holds no catalogue permission, and `/api/me/` gives them none."""
        for path in ('/api/students/', f'/api/students/{self.other.pk}/',
                     '/api/guardians/', '/api/admissions/', '/api/documents/'):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 403)

    def test_a_staff_account_with_no_student_record_gets_404(self):
        """404 and not 403: whether an account has a student profile is not
        something these endpoints should confirm either way."""
        staff = f.make_user(self.branch, permissions=['students.view'])
        client = APIClient()
        client.force_authenticate(user=staff)

        self.assertEqual(client.get('/api/me/profile/').status_code, 404)
        self.assertEqual(client.get('/api/me/documents/').status_code, 404)

    def test_an_anonymous_request_reaches_nothing(self):
        self.assertIn(APIClient().get('/api/me/profile/').status_code, (401, 403))

    def test_a_deactivated_student_record_is_not_reachable(self):
        """Soft delete means gone from the API, not merely hidden from a list."""
        self.me.is_active = False
        self.me.save(update_fields=['is_active'])

        self.assertEqual(self.client.get('/api/me/profile/').status_code, 404)


class EnableLoginTests(TestCase):
    """docs/08 D4 — the login is an action on the record, never a step in admission."""

    def setUp(self):
        self.branch = f.make_branch()
        self.student = f.make_student(self.branch, name='Abdullah')

    def test_a_student_starts_with_no_account(self):
        self.assertIsNone(self.student.user_id)

    def test_enabling_a_login_creates_an_account_that_must_change_its_password(self):
        user = enable_student_login(self.student, phone='01712345678',
                                    password='pass-phrase-1234')

        self.student.refresh_from_db()
        self.assertEqual(self.student.user_id, user.pk)
        self.assertEqual(self.student.phone, '01712345678')
        self.assertEqual(user.user_type, 'student')
        self.assertEqual(user.branch_id, self.branch.pk)
        self.assertTrue(user.must_change_password)

    def test_a_phone_that_already_has_an_account_is_refused(self):
        """Attaching to somebody else's account would hand over their records."""
        f.make_user(self.branch, phone='01712345678')

        with self.assertRaises(Exception):
            enable_student_login(self.student, phone='01712345678')

        self.student.refresh_from_db()
        self.assertIsNone(self.student.user_id)

    def test_a_number_that_is_not_a_bd_mobile_is_refused(self):
        with self.assertRaises(Exception):
            enable_student_login(self.student, phone='12345')
