"""The photo and the certificates handed in at the admission counter.

They arrive WITH the child. Everything here is about that being one transaction
with the admission rather than a second visit to the student record: a roll half
without photographs is what "add it later" produces every time.
"""

import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from students.models import Document, DocumentOwner, DocumentType, Student
from students.services import admit_student

from . import factories as f

# A 1×1 transparent GIF — the smallest thing Pillow will accept as an image, so
# `ImageField` validation runs for real without a fixture file on disk.
GIF = (b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!'
       b'\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00'
       b'\x00\x02\x02D\x01\x00;')


def a_photo(name='yusuf.gif'):
    return SimpleUploadedFile(name, GIF, content_type='image/gif')


def a_file(name='birth.pdf', body=b'%PDF-1.4 scan'):
    return SimpleUploadedFile(name, body, content_type='application/pdf')


MEDIA = tempfile.mkdtemp(prefix='sies-admit-files-')


@override_settings(MEDIA_ROOT=MEDIA, SIES_ENROLMENT_SERVICE=f.stub_enrolment)
class AdmitWithFilesTests(TestCase):
    """The service half — `admit_student(photo=…, documents=…)`."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        f.reset_enrolment_calls()
        self.branch = f.make_branch()
        self.session = f.make_session(self.branch)
        self.academic_class = f.make_class(self.branch, self.session)
        self.actor = f.make_user(self.branch)

    def test_the_photo_lands_on_both_the_application_and_the_student(self):
        application = f.make_application(self.branch, self.session, self.academic_class)

        student, _ = admit_student(application, actor=self.actor, photo=a_photo())

        application.refresh_from_db()
        self.assertTrue(application.photo)
        # One stored file, two rows pointing at it: the admission form reprints
        # with the picture and nothing has to decide which copy is current.
        self.assertEqual(student.photo.name, application.photo.name)

    def test_the_certificates_are_stored_against_the_new_student(self):
        application = f.make_application(self.branch, self.session, self.academic_class)

        student, _ = admit_student(
            application, actor=self.actor,
            documents=[
                {'doc_type': DocumentType.BIRTH_CERTIFICATE, 'title': 'জন্ম নিবন্ধন',
                 'file': a_file()},
                {'doc_type': DocumentType.TESTIMONIAL, 'title': '',
                 'file': a_file('testimonial.pdf')},
            ],
        )

        documents = Document.objects.filter(student=student).order_by('doc_type')
        self.assertEqual(documents.count(), 2)
        for document in documents:
            self.assertEqual(document.branch, self.branch)
            self.assertEqual(document.owner_type, DocumentOwner.STUDENT)
            self.assertEqual(document.uploaded_by, self.actor)
            self.assertTrue(document.title)

    @override_settings(SIES_ENROLMENT_SERVICE=f.failing_enrolment)
    def test_a_failure_after_the_files_admits_nobody_and_stores_no_row(self):
        """The whole point of doing this inside the admission's transaction.

        The enrolment blows up after the photo and the certificates were
        written. A student on the roll with no enrolment is the outcome the
        transaction exists to prevent, and a Document pointing at a student who
        was rolled back would be a scan of a minor's birth certificate with
        nobody attached to it.
        """
        application = f.make_application(self.branch, self.session, self.academic_class)

        with self.assertRaises(RuntimeError):
            admit_student(application, actor=self.actor, photo=a_photo(),
                          documents=[{'doc_type': DocumentType.NID, 'title': 'NID',
                                      'file': a_file()}])

        self.assertEqual(Student.objects.count(), 0)
        self.assertEqual(Document.objects.count(), 0)
        application.refresh_from_db()
        self.assertIsNone(application.student_id)


@override_settings(MEDIA_ROOT=MEDIA, SIES_ENROLMENT_SERVICE=f.stub_enrolment)
class AdmitUploadApiTests(TestCase):
    """`POST /api/admissions/<id>/admit/` as multipart."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        f.reset_enrolment_calls()
        self.branch = f.make_branch(code='DHK')
        self.other = f.make_branch(code='CTG', name='Chittagong Madrasah')
        self.session = f.make_session(self.branch)
        self.academic_class = f.make_class(self.branch, self.session)
        self.other_session = f.make_session(self.other)
        self.other_class = f.make_class(self.other, self.other_session)

    def client_with(self, permissions, branch=None):
        user = f.make_user(branch or self.branch, permissions=list(permissions))
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def body(self, **extra):
        return {
            'academic_class': self.academic_class.pk,
            'photo': a_photo(),
            'document_files': [a_file(), a_file('tc.pdf')],
            'document_types': [DocumentType.BIRTH_CERTIFICATE,
                               DocumentType.TRANSFER_CERTIFICATE],
            'document_titles': ['জন্ম নিবন্ধন', ''],
            **extra,
        }

    def test_multipart_admit_attaches_the_photo_and_the_documents(self):
        application = f.make_application(self.branch, self.session, self.academic_class)
        client = self.client_with(['admissions.update', 'documents.upload'])

        response = client.post(f'/api/admissions/{application.pk}/admit/',
                               self.body(), format='multipart')

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['documents_attached'], 2)
        self.assertEqual(response.data['documents_skipped'], 0)

        student = Student.objects.get(pk=response.data['student']['id'])
        self.assertTrue(student.photo)
        self.assertEqual(Document.objects.filter(student=student).count(), 2)
        # A blank title falls back to the type's own label rather than failing:
        # the type already says what the paper is.
        self.assertTrue(all(d.title for d in Document.objects.filter(student=student)))

    def test_a_clerk_without_documents_upload_still_admits(self):
        """The files degrade; the admission does not.

        Refusing the whole admission because the counter clerk's role cannot
        file papers would punish the child for the role.
        """
        application = f.make_application(self.branch, self.session, self.academic_class)
        client = self.client_with(['admissions.update'])

        response = client.post(f'/api/admissions/{application.pk}/admit/',
                               self.body(), format='multipart')

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['documents_attached'], 0)
        self.assertEqual(response.data['documents_skipped'], 2)
        self.assertEqual(Document.objects.count(), 0)
        # The photo is part of the student record itself, so it rides with the
        # admission permission and is kept.
        self.assertTrue(Student.objects.get(pk=response.data['student']['id']).photo)

    def test_another_institutions_application_is_404_not_403(self):
        theirs = f.make_application(self.other, self.other_session, self.other_class)
        client = self.client_with(['admissions.update', 'documents.upload'])

        response = client.post(f'/api/admissions/{theirs.pk}/admit/',
                               self.body(), format='multipart')

        self.assertEqual(response.status_code, 404)
        self.assertEqual(Document.objects.count(), 0)
        self.assertEqual(Student.objects.count(), 0)

    def test_an_unknown_document_type_is_a_field_error_and_admits_nobody(self):
        application = f.make_application(self.branch, self.session, self.academic_class)
        client = self.client_with(['admissions.update', 'documents.upload'])

        response = client.post(
            f'/api/admissions/{application.pk}/admit/',
            self.body(document_types=['passport', DocumentType.NID]),
            format='multipart',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Student.objects.count(), 0)
