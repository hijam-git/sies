"""The two number series — gapless, unique, and never reused (CLAUDE.md §4.4)."""

from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from core.models import NumberSequence
from students.models import Student
from students.services import (admit_student, allocate_application_no,
                               allocate_student_id, create_application)

from . import factories as f


class StudentIdTests(TestCase):
    def setUp(self):
        self.branch = f.make_branch()

    def test_ids_are_consecutive_and_formatted(self):
        ids = [allocate_student_id() for _ in range(3)]
        serials = [int(value.split('-')[1]) for value in ids]

        self.assertEqual(serials, [serials[0], serials[0] + 1, serials[0] + 2])
        self.assertTrue(all(value.startswith('SIES-') for value in ids))
        self.assertTrue(all(len(value.split('-')[1]) == 6 for value in ids))

    def test_the_series_is_platform_wide_not_per_branch(self):
        """docs/03 §4 makes `student_id` globally unique.

        A per-branch counter would hand SIES-000001 to two institutions on their
        opening day, and the second insert would fail for a clerk who did nothing
        wrong.
        """
        other = f.make_branch(code='CTG', name='Chittagong Madrasah')

        here = f.make_student(self.branch, name='Abdullah')
        there = f.make_student(other, name='Bilal')

        self.assertNotEqual(here.student_id, there.student_id)
        self.assertEqual(NumberSequence.objects.filter(kind=NumberSequence.Kind.STUDENT).count(), 1)

    def test_a_duplicate_student_id_is_refused_by_the_database(self):
        existing = f.make_student(self.branch)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Student.objects.create(
                branch=self.branch, stream=f.first_stream(self.branch),
                student_id=existing.student_id, name='Impostor',
            )

    def test_a_number_is_not_burned_by_a_failed_transaction(self):
        """Gapless means gapless: a rolled-back allocation must not skip a value."""
        before = NumberSequence.objects.get(kind=NumberSequence.Kind.STUDENT).last_number if \
            NumberSequence.objects.filter(kind=NumberSequence.Kind.STUDENT).exists() else 0

        try:
            with transaction.atomic():
                allocate_student_id()
                raise RuntimeError('the insert after it failed')
        except RuntimeError:
            pass

        after = NumberSequence.objects.filter(kind=NumberSequence.Kind.STUDENT).first()
        self.assertEqual(after.last_number if after else 0, before)


@override_settings(SIES_ENROLMENT_SERVICE=f.stub_enrolment)
class ApplicationNumberTests(TestCase):
    def setUp(self):
        f.reset_enrolment_calls()
        self.branch = f.make_branch()
        self.session = f.make_session(self.branch)
        self.academic_class = f.make_class(self.branch, self.session)

    def test_numbers_are_gapless_within_a_branch_and_session(self):
        numbers = [allocate_application_no(self.branch, self.session)
                   for _ in range(3)]
        serials = [int(value.rsplit('-', 1)[1]) for value in numbers]

        self.assertEqual(serials, [1, 2, 3])
        self.assertTrue(all(value.startswith(f'APP-{self.branch.code}-') for value in numbers))

    def test_each_session_restarts_the_count(self):
        """Application 41 of 2026 and of 2027 are different applicants."""
        next_session = f.make_session(self.branch, name='2027')

        first = allocate_application_no(self.branch, self.session)
        second = allocate_application_no(self.branch, next_session)

        self.assertTrue(first.endswith('00001'))
        self.assertTrue(second.endswith('00001'))
        self.assertNotEqual(first, second)

    def test_each_branch_counts_separately(self):
        other = f.make_branch(code='CTG', name='Chittagong Madrasah')
        other_session = f.make_session(other)

        allocate_application_no(self.branch, self.session)
        theirs = allocate_application_no(other, other_session)

        self.assertTrue(theirs.startswith('APP-CTG-'))
        self.assertTrue(theirs.endswith('00001'))

    def test_two_applications_in_one_session_cannot_share_a_number(self):
        application = create_application(
            branch=self.branch, session=self.session,
            stream=f.first_stream(self.branch), academic_class=self.academic_class,
            applicant_name='Yusuf', guardian_name='Golam Rasul',
            guardian_phone='01712345678',
        )
        from students.models import Admission

        with self.assertRaises(IntegrityError), transaction.atomic():
            Admission.objects.create(
                branch=self.branch, session=self.session,
                stream=f.first_stream(self.branch), academic_class=self.academic_class,
                application_no=application.application_no,
                applicant_name='Copy', guardian_name='Somebody',
                guardian_phone='01712345679',
            )

    def test_admission_does_not_reallocate_the_application_number(self):
        application = f.make_application(self.branch, self.session, self.academic_class)
        original = application.application_no

        admit_student(application, actor=f.make_user(self.branch))

        application.refresh_from_db()
        self.assertEqual(application.application_no, original)
