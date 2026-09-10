"""`admit_student()` — the transaction the whole module exists for (docs/02 §4.1)."""

from datetime import date

from django.test import TestCase, override_settings

from accounts.models import ActivityLog
from students.models import (Admission, AdmissionStatus, Guardian, Student,
                             StudentGuardian, StudentStatus)
from students.services import admit_student, readmit_student

from . import factories as f


@override_settings(SIES_ENROLMENT_SERVICE=f.stub_enrolment)
class AdmitStudentTests(TestCase):
    def setUp(self):
        f.reset_enrolment_calls()
        self.branch = f.make_branch()
        self.session = f.make_session(self.branch)
        self.academic_class = f.make_class(self.branch, self.session)
        self.actor = f.make_user(self.branch)

    def test_admission_writes_student_enrolment_guardian_and_closes_application(self):
        application = f.make_application(
            self.branch, self.session, self.academic_class,
            applicant_name='Yusuf Ahmed', guardian_phone='01712345678',
            village='Bakshiganj', post_office='Kamalpur',
            upazila='Bakshiganj', district='Jamalpur',
        )

        student, enrolment = admit_student(application, actor=self.actor)

        self.assertTrue(student.student_id.startswith('SIES-'))
        self.assertEqual(student.status, StudentStatus.ACTIVE)
        # The four structured boxes are copied forward, which is the reason both
        # models carry them (docs/07 §4).
        self.assertEqual(student.upazila, 'Bakshiganj')
        self.assertEqual(student.district, 'Jamalpur')

        self.assertEqual(enrolment.academic_class, self.academic_class)
        self.assertEqual(enrolment.session, self.session)

        guardian = Guardian.objects.get(branch=self.branch, phone='01712345678')
        self.assertTrue(StudentGuardian.objects.filter(
            student=student, guardian=guardian, is_primary=True).exists())

        application.refresh_from_db()
        self.assertEqual(application.status, AdmissionStatus.ADMITTED)
        self.assertEqual(application.student_id, student.pk)
        self.assertEqual(application.processed_by, self.actor)
        self.assertIsNotNone(application.processed_at)

        self.assertTrue(ActivityLog.objects.filter(
            model='Student', object_id=str(student.pk)).exists())

    def test_a_student_with_no_login_is_admitted_normally(self):
        """docs/08 D4 — most young students have no phone at all."""
        application = f.make_application(self.branch, self.session, self.academic_class)

        student, _ = admit_student(application, actor=self.actor)

        self.assertIsNone(student.user_id)
        self.assertEqual(student.phone, '')

    def test_a_sibling_reuses_the_existing_guardian(self):
        """One guardian row, two children — the reason Guardian is its own table."""
        first = f.make_application(self.branch, self.session, self.academic_class,
                                   applicant_name='Yusuf',
                                   guardian_name='Golam Rasul',
                                   guardian_phone='01712345678')
        second = f.make_application(self.branch, self.session, self.academic_class,
                                    applicant_name='Maryam',
                                    # Same man, spelled differently on the second
                                    # form — which is why the match is on phone.
                                    guardian_name='Golam Rosul',
                                    guardian_phone='+8801712345678')

        elder, _ = admit_student(first, actor=self.actor)
        younger, _ = admit_student(second, actor=self.actor)

        guardians = Guardian.objects.filter(branch=self.branch, phone='01712345678')
        self.assertEqual(guardians.count(), 1)
        self.assertEqual(guardians.first().name, 'Golam Rasul')
        self.assertEqual(
            set(StudentGuardian.objects.filter(guardian=guardians.first())
                .values_list('student_id', flat=True)),
            {elder.pk, younger.pk},
        )

    def test_the_same_phone_in_another_institution_is_a_different_guardian(self):
        """Guardian uniqueness is per branch — two institutions share nothing."""
        other = f.make_branch(code='CTG', name='Chittagong Madrasah')
        other_session = f.make_session(other)
        other_class = f.make_class(other, other_session)

        here = f.make_application(self.branch, self.session, self.academic_class,
                                  guardian_phone='01712345678')
        there = f.make_application(other, other_session, other_class,
                                   guardian_phone='01712345678')

        admit_student(here, actor=self.actor)
        admit_student(there, actor=self.actor)

        self.assertEqual(Guardian.objects.filter(phone='01712345678').count(), 2)

    @override_settings(SIES_ENROLMENT_SERVICE=f.failing_enrolment)
    def test_a_failure_partway_writes_nothing_at_all(self):
        """All of it, or none of it.

        The failure is placed where it hurts: after the Student row and before
        the enrolment. Without one transaction around the lot, this leaves a
        child on the roll who owes no fees and appears in no register — and
        nobody finds out until March.
        """
        application = f.make_application(self.branch, self.session, self.academic_class,
                                         guardian_phone='01712345678')
        before_students = Student.objects.count()
        before_guardians = Guardian.objects.count()
        before_logs = ActivityLog.objects.count()

        with self.assertRaises(RuntimeError):
            admit_student(application, actor=self.actor)

        self.assertEqual(Student.objects.count(), before_students)
        self.assertEqual(Guardian.objects.count(), before_guardians)
        self.assertEqual(StudentGuardian.objects.count(), 0)
        self.assertEqual(ActivityLog.objects.count(), before_logs)

        application.refresh_from_db()
        self.assertEqual(application.status, AdmissionStatus.ACCEPTED)
        self.assertIsNone(application.student_id)

    def test_an_application_cannot_be_admitted_twice(self):
        application = f.make_application(self.branch, self.session, self.academic_class)
        admit_student(application, actor=self.actor)

        application.refresh_from_db()
        with self.assertRaises(Exception):
            admit_student(application, actor=self.actor)

        self.assertEqual(Student.objects.filter(branch=self.branch).count(), 1)

    def test_a_rejected_application_cannot_be_admitted(self):
        application = f.make_application(self.branch, self.session, self.academic_class,
                                         status=AdmissionStatus.REJECTED)
        with self.assertRaises(Exception):
            admit_student(application, actor=self.actor)
        self.assertEqual(Student.objects.count(), 0)


@override_settings(SIES_ENROLMENT_SERVICE=f.stub_enrolment)
class ReadmissionTests(TestCase):
    """docs/02 §4.1 — the next session is a new Enrolment, never a new Student."""

    def setUp(self):
        f.reset_enrolment_calls()
        self.branch = f.make_branch()
        self.session = f.make_session(self.branch)
        self.academic_class = f.make_class(self.branch, self.session)
        self.actor = f.make_user(self.branch)

    def test_readmission_creates_a_second_enrolment_and_no_second_student(self):
        application = f.make_application(self.branch, self.session, self.academic_class)
        student, _ = admit_student(application, actor=self.actor)

        next_session = f.make_session(self.branch, name='2027')
        next_class = f.make_class(self.branch, next_session, name='Class 2', level_order=2)

        readmit_student(student, session=next_session, academic_class=next_class,
                        actor=self.actor)

        self.assertEqual(Student.objects.filter(branch=self.branch).count(), 1)
        self.assertEqual(len(f.enrolment_calls), 2)
        self.assertEqual(f.enrolment_calls[1]['session'], next_session)
        self.assertEqual(f.enrolment_calls[1]['academic_class'], next_class)

        student.refresh_from_db()
        # The permanent ID and the first admission date do not move.
        self.assertEqual(student.admitted_on, date.today())
        self.assertTrue(student.student_id.startswith('SIES-'))

    def test_readmitting_a_withdrawn_student_makes_them_active_again(self):
        student = f.make_student(self.branch, status=StudentStatus.WITHDRAWN)
        next_session = f.make_session(self.branch, name='2027')
        next_class = f.make_class(self.branch, next_session, name='Class 2', level_order=2)

        readmit_student(student, session=next_session, academic_class=next_class,
                        actor=self.actor)

        student.refresh_from_db()
        self.assertEqual(student.status, StudentStatus.ACTIVE)
        self.assertEqual(Admission.objects.count(), 0)
