"""Who may read a result, and for whom (docs/02 §4.7, docs/08 D6).

Three gates, and each was reachable past one of them:

* a **guardian**-typed account was not the account type the own-student check
  tested, so `exams.view` plus an id read any child's marksheet;
* the result endpoints are custom `@action`s, which `TeacherScopedMixin` — a
  queryset filter — never touched, so a Class 5 teacher could pull Class 9's
  merit sheet by changing one query parameter;
* and a published exam could not be corrected at all, because `save_marks`
  refuses one and nothing could take it back down.
"""

from django.test import TestCase, override_settings

from exams.models import ExamStatus, Result
from exams.services import publish_exam, save_marks

from . import factories as f
from .test_api import client_for


@override_settings(ROOT_URLCONF='exams.tests.urls')
class OwnStudentTests(TestCase):
    def setUp(self):
        self.world = f.small_world()
        w = self.world
        save_marks(exam=w['exam'], subject=w['arabic'], actor=w['principal'],
                   rows=[{'enrolment': e.pk, 'obtained': '80'} for e in w['enrolments']])
        save_marks(exam=w['exam'], subject=w['fiqh'], actor=w['principal'],
                   rows=[{'enrolment': e.pk, 'obtained': '70'} for e in w['enrolments']])
        publish_exam(w['exam'], actor=w['principal'])

    def guardian_account(self):
        return f.make_user(
            self.world['branch'], phone='01711000077', user_type='guardian',
            permissions=['exams.view', 'marks.view'],
        )

    def test_a_guardian_account_cannot_read_a_students_result(self):
        response = client_for(self.guardian_account()).get(
            f'/api/exams/{self.world["exam"].pk}/result/',
            {'student': self.world['students'][0].pk},
        )

        self.assertEqual(response.status_code, 404)

    def test_a_guardian_account_cannot_read_a_students_report(self):
        response = client_for(self.guardian_account()).get(
            '/api/exams/student-report/', {'student': self.world['students'][0].pk},
        )

        self.assertEqual(response.status_code, 404)

    def test_the_principal_still_reads_it(self):
        """The gate above must refuse the account type, not the endpoint."""
        response = client_for(self.world['principal']).get(
            f'/api/exams/{self.world["exam"].pk}/result/',
            {'student': self.world['students'][0].pk},
        )

        self.assertEqual(response.status_code, 200)


@override_settings(ROOT_URLCONF='exams.tests.urls')
class TeacherScopeTests(TestCase):
    """D6 applies to the result sheets too, not only to the entry grid."""

    def setUp(self):
        self.world = f.small_world()
        w = self.world
        self.other_class = f.make_class(w['branch'], w['session'], name='Class 9')
        self.other_subject = f.make_subject(self.other_class, name='Hadith')
        f.make_schedule(exam=w['exam'], academic_class=self.other_class,
                        subject=self.other_subject)

        self.teacher_user = f.make_user(
            w['branch'], phone='01711000055', user_type='teacher',
            permissions=['exams.view', 'marks.view', 'marks.enter'],
        )
        teacher = f.make_teacher(w['branch'], name='Own Class Only',
                                 user=self.teacher_user)
        f.make_assignment(session=w['session'], teacher=teacher,
                          subject=w['arabic'], academic_class=w['class'])

    def test_a_teacher_cannot_tabulate_a_class_that_is_not_theirs(self):
        response = client_for(self.teacher_user).get(
            f'/api/exams/{self.world["exam"].pk}/tabulation/',
            {'academic_class': self.other_class.pk},
        )

        self.assertEqual(response.status_code, 404)

    def test_a_teacher_tabulates_their_own_class(self):
        response = client_for(self.teacher_user).get(
            f'/api/exams/{self.world["exam"].pk}/tabulation/',
            {'academic_class': self.world['class'].pk},
        )

        self.assertEqual(response.status_code, 200)

    def test_a_teacher_cannot_read_a_result_of_a_student_they_do_not_teach(self):
        student = f.make_student(self.world['branch'], name='Someone Else')
        f.make_enrolment(student=student, session=self.world['session'],
                         academic_class=self.other_class, roll=9,
                         admission_number='DHK-0009')

        response = client_for(self.teacher_user).get(
            '/api/exams/student-report/', {'student': student.pk},
        )

        self.assertEqual(response.status_code, 404)


@override_settings(ROOT_URLCONF='exams.tests.urls')
class UnpublishTests(TestCase):
    """One mistyped mark at publish time was permanent: marks entry refuses a
    published exam, and nothing could take one back down."""

    def setUp(self):
        self.world = f.small_world()
        w = self.world
        save_marks(exam=w['exam'], subject=w['arabic'], actor=w['principal'],
                   rows=[{'enrolment': w['enrolments'][0].pk, 'obtained': '80'}])
        publish_exam(w['exam'], actor=w['principal'])

    def test_unpublishing_reopens_marks_entry_and_drops_the_frozen_rows(self):
        response = client_for(self.world['principal']).post(
            f'/api/exams/{self.world["exam"].pk}/unpublish/',
        )

        self.assertEqual(response.status_code, 200)
        self.world['exam'].refresh_from_db()
        self.assertEqual(self.world['exam'].status, ExamStatus.MARKS_ENTRY)
        self.assertIsNone(self.world['exam'].published_at)
        self.assertFalse(Result.objects.filter(exam=self.world['exam']).exists())

        # The point of it: the mark can now be corrected.
        save_marks(exam=self.world['exam'], subject=self.world['arabic'],
                   actor=self.world['principal'],
                   rows=[{'enrolment': self.world['enrolments'][0].pk, 'obtained': '85'}])

    def test_unpublishing_costs_the_publish_permission(self):
        teacher_user = f.make_user(
            self.world['branch'], phone='01711000066', user_type='teacher',
            permissions=['marks.view', 'marks.enter', 'exams.view', 'exams.update'],
        )

        response = client_for(teacher_user).post(
            f'/api/exams/{self.world["exam"].pk}/unpublish/',
        )

        self.assertEqual(response.status_code, 403)
        self.world['exam'].refresh_from_db()
        self.assertEqual(self.world['exam'].status, ExamStatus.PUBLISHED)
