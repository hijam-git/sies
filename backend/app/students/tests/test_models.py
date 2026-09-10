"""The constraints — the database is the last line, not the serializer.

Each of these asserts an IntegrityError, which is the point: application code is
not a constraint (CLAUDE.md §4.2). A rule only checked in a serializer is a rule
that does not apply to the Django admin, a management command, or a data fix
typed into `dbshell` at nine at night.
"""

from django.db import IntegrityError, transaction
from django.test import TestCase

from students.models import (Admission, AdmissionStatus, Document, Guardian,
                             StudentGuardian)

from . import factories as f


class GuardianConstraintTests(TestCase):
    def setUp(self):
        self.branch = f.make_branch()

    def test_one_guardian_per_phone_per_institution(self):
        f.make_guardian(self.branch, phone='01712345678')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Guardian.objects.create(branch=self.branch, name='Someone Else',
                                    phone='01712345678')

    def test_the_phone_is_stored_canonically(self):
        guardian = f.make_guardian(self.branch, phone='+88 01712-345678')
        self.assertEqual(guardian.phone, '01712345678')


class StudentGuardianConstraintTests(TestCase):
    def setUp(self):
        self.branch = f.make_branch()
        self.student = f.make_student(self.branch)
        self.father = f.make_guardian(self.branch, name='Golam Rasul',
                                      phone='01712345678')
        self.uncle = f.make_guardian(self.branch, name='Local Guardian',
                                     phone='01712345679')

    def test_a_pair_cannot_be_linked_twice(self):
        f.link(self.student, self.father)
        with self.assertRaises(IntegrityError), transaction.atomic():
            StudentGuardian.objects.create(branch=self.branch, student=self.student,
                                           guardian=self.father)

    def test_only_one_guardian_can_be_primary(self):
        """Two primaries means two SMS per reminder, which the gateway bills for."""
        f.link(self.student, self.father, is_primary=True)
        with self.assertRaises(IntegrityError), transaction.atomic():
            StudentGuardian.objects.create(branch=self.branch, student=self.student,
                                           guardian=self.uncle, is_primary=True)

    def test_a_student_may_have_several_non_primary_guardians(self):
        f.link(self.student, self.father, is_primary=True)
        f.link(self.student, self.uncle, is_primary=False)
        self.assertEqual(self.student.guardian_links.count(), 2)
        self.assertEqual(self.student.primary_guardian, self.father)


class DocumentConstraintTests(TestCase):
    def setUp(self):
        self.branch = f.make_branch()
        self.student = f.make_student(self.branch)

    def test_a_student_document_must_name_a_student(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Document.objects.create(branch=self.branch, owner_type='student',
                                    doc_type='certificate', title='Nobody\'s',
                                    file='documents/2026/01/x.pdf')

    def test_a_document_cannot_claim_a_type_it_does_not_point_at(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Document.objects.create(branch=self.branch, owner_type='teacher',
                                    student=self.student,
                                    doc_type='certificate', title='Mislabelled',
                                    file='documents/2026/01/x.pdf')


class AdmissionConstraintTests(TestCase):
    def setUp(self):
        self.branch = f.make_branch()
        self.session = f.make_session(self.branch)
        self.academic_class = f.make_class(self.branch, self.session)

    def test_an_admitted_application_must_point_at_a_student(self):
        """A click that half happened is not a state this table may hold."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            Admission.objects.create(
                branch=self.branch, session=self.session,
                stream=f.first_stream(self.branch), academic_class=self.academic_class,
                application_no='APP-DHK-2026-00001',
                applicant_name='Yusuf', guardian_name='Golam Rasul',
                guardian_phone='01712345678',
                status=AdmissionStatus.ADMITTED,
            )


class StudentModelTests(TestCase):
    def setUp(self):
        self.branch = f.make_branch()

    def test_the_four_address_boxes_join_into_one_line(self):
        student = f.make_student(self.branch, village='Bakshiganj',
                                 post_office='Kamalpur', upazila='Bakshiganj',
                                 district='Jamalpur')
        self.assertEqual(student.full_address,
                         'Bakshiganj, Kamalpur, Bakshiganj, Jamalpur')

    def test_an_empty_box_is_skipped_rather_than_leaving_a_stray_comma(self):
        student = f.make_student(self.branch, village='Bakshiganj',
                                 district='Jamalpur')
        self.assertEqual(student.full_address, 'Bakshiganj, Jamalpur')

    def test_a_student_with_no_guardian_has_no_primary(self):
        self.assertIsNone(f.make_student(self.branch).primary_guardian)
