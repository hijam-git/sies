"""Branch isolation on every viewset — 404, never 403 (CLAUDE.md §5).

403 confirms the row exists, which is precisely what a probe is looking for. The
tests below therefore assert the status code and not merely "was refused".

Every account here holds the full permission list for the resource it touches,
so a passing test cannot be passing because the user lacked a permission — which
would prove nothing about branch scoping at all.
"""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from students.models import Document, Guardian, Student

from . import factories as f

STUDENT_PERMS = ['students.view', 'students.create', 'students.update', 'students.delete']
ADMISSION_PERMS = ['admissions.view', 'admissions.create', 'admissions.update']
DOCUMENT_PERMS = ['documents.view', 'documents.upload', 'documents.delete']
ALL_PERMS = STUDENT_PERMS + ADMISSION_PERMS + DOCUMENT_PERMS


def staff(branch):
    return f.make_user(branch, permissions=list(ALL_PERMS))


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


class TwoInstitutions(TestCase):
    """Branch A and branch B, each with a student, a guardian and a document."""

    def setUp(self):
        f.reset_enrolment_calls()
        self.a = f.make_branch(code='DHK', name='Dhaka Madrasah')
        self.b = f.make_branch(code='CTG', name='Chittagong Madrasah')

        self.a_session = f.make_session(self.a)
        self.b_session = f.make_session(self.b)
        self.a_class = f.make_class(self.a, self.a_session)
        self.b_class = f.make_class(self.b, self.b_session)

        self.a_user = staff(self.a)
        self.b_user = staff(self.b)
        self.client_a = client_for(self.a_user)

        self.a_student = f.make_student(self.a, name='Abdullah')
        self.b_student = f.make_student(self.b, name='Bilal')

        self.a_guardian = f.make_guardian(self.a, phone='01712345678')
        self.b_guardian = f.make_guardian(self.b, phone='01712345678')

        self.a_application = f.make_application(self.a, self.a_session, self.a_class)
        self.b_application = f.make_application(self.b, self.b_session, self.b_class)

        self.a_document = self._document(self.a, self.a_student)
        self.b_document = self._document(self.b, self.b_student)

    def _document(self, branch, student):
        return Document.objects.create(
            branch=branch, student=student, owner_type='student',
            doc_type='birth_certificate', title='Birth certificate',
            file=SimpleUploadedFile('bc.txt', b'scan', content_type='text/plain'),
        )


@override_settings(SIES_ENROLMENT_SERVICE=f.stub_enrolment)
class BranchIsolationTests(TwoInstitutions):
    def test_student_list_shows_only_this_institution(self):
        response = self.client_a.get('/api/students/')
        self.assertEqual(response.status_code, 200)
        names = [row['name'] for row in response.data['results']]
        self.assertEqual(names, ['Abdullah'])

    def test_another_institutions_student_is_404(self):
        response = self.client_a.get(f'/api/students/{self.b_student.pk}/')
        self.assertEqual(response.status_code, 404)

    def test_another_institutions_student_cannot_be_patched(self):
        response = self.client_a.patch(
            f'/api/students/{self.b_student.pk}/', {'name': 'Renamed'}, format='json')
        self.assertEqual(response.status_code, 404)
        self.b_student.refresh_from_db()
        self.assertEqual(self.b_student.name, 'Bilal')

    def test_another_institutions_guardian_is_404(self):
        response = self.client_a.get(f'/api/guardians/{self.b_guardian.pk}/')
        self.assertEqual(response.status_code, 404)

    def test_another_institutions_application_is_404(self):
        response = self.client_a.get(f'/api/admissions/{self.b_application.pk}/')
        self.assertEqual(response.status_code, 404)

    def test_another_institutions_application_cannot_be_admitted(self):
        response = self.client_a.post(
            f'/api/admissions/{self.b_application.pk}/admit/', {}, format='json')
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Student.objects.filter(branch=self.b, name='Yusuf').exists())

    def test_another_institutions_document_is_404(self):
        response = self.client_a.get(f'/api/documents/{self.b_document.pk}/')
        self.assertEqual(response.status_code, 404)

    def test_another_institutions_document_cannot_be_downloaded(self):
        """The file is only reachable through this view, so this is the whole gate."""
        response = self.client_a.get(f'/api/documents/{self.b_document.pk}/download/')
        self.assertEqual(response.status_code, 404)

    def test_the_branch_is_stamped_server_side_not_from_the_body(self):
        """CLAUDE.md §1 — a `branch` in a POST body is ignored."""
        response = self.client_a.post('/api/students/', {
            'name': 'Ibrahim',
            'stream': f.first_stream(self.a).pk,
            'branch': self.b.pk,
        }, format='json')

        self.assertEqual(response.status_code, 201)
        student = Student.objects.get(name='Ibrahim')
        self.assertEqual(student.branch_id, self.a.pk)
        self.assertTrue(student.student_id.startswith('SIES-'))

    def test_a_relation_from_another_institution_is_rejected(self):
        """A scoped queryset governs reads; only this check governs writes."""
        response = self.client_a.post('/api/students/', {
            'name': 'Ibrahim',
            'stream': f.first_stream(self.b).pk,
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('stream', str(response.data).lower())


@override_settings(SIES_ENROLMENT_SERVICE=f.stub_enrolment)
class StudentApiTests(TwoInstitutions):
    def test_admitting_through_the_api_returns_the_student_and_the_roll(self):
        response = self.client_a.post(
            f'/api/admissions/{self.a_application.pk}/admit/', {}, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data['student']['student_id'].startswith('SIES-'))
        self.assertIsNotNone(response.data['admission_number'])

        self.a_application.refresh_from_db()
        self.assertEqual(self.a_application.status, 'admitted')

    def test_a_guardian_is_attached_and_reused_by_phone(self):
        response = self.client_a.post(
            f'/api/students/{self.a_student.pk}/guardians/',
            {'name': 'Golam Rasul', 'phone': '01712345678'}, format='json')

        self.assertEqual(response.status_code, 201)
        # The branch already had a guardian on that number — no second row.
        self.assertEqual(Guardian.objects.filter(branch=self.a,
                                                 phone='01712345678').count(), 1)
        self.assertTrue(response.data['is_primary'])

    def test_student_id_cannot_be_edited(self):
        original = self.a_student.student_id
        response = self.client_a.patch(
            f'/api/students/{self.a_student.pk}/',
            {'student_id': 'SIES-999999'}, format='json')

        self.assertEqual(response.status_code, 200)
        self.a_student.refresh_from_db()
        self.assertEqual(self.a_student.student_id, original)

    def test_a_duplicate_guardian_phone_is_a_field_error_not_a_500(self):
        response = self.client_a.post('/api/guardians/', {
            'name': 'Someone Else', 'phone': '01712345678',
        }, format='json')
        self.assertEqual(response.status_code, 400)

    def test_the_document_file_url_is_never_exposed(self):
        """docs/01 §8 — a `/media/...` path is a permanent grant to whoever has it."""
        response = self.client_a.get(f'/api/documents/{self.a_document.pk}/')

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('file', response.data)
        self.assertIn('/api/documents/', response.data['download_url'])

    def test_a_document_can_be_downloaded_by_its_own_institution(self):
        response = self.client_a.get(f'/api/documents/{self.a_document.pk}/download/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment', response['Content-Disposition'])


class PermissionTests(TwoInstitutions):
    def test_an_account_without_the_permission_is_refused(self):
        """Branch scoping is not the only gate — the catalogue still applies."""
        nobody = f.make_user(self.a, permissions=['dashboard.view'])
        response = client_for(nobody).get('/api/students/')
        self.assertEqual(response.status_code, 403)

    def test_an_anonymous_request_is_refused(self):
        response = APIClient().get('/api/students/')
        self.assertIn(response.status_code, (401, 403))
