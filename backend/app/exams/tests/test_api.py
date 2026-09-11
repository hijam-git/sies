"""The exams API: branch isolation and result visibility.

Every account here holds the full permission list for the resource it touches,
so a passing test cannot be passing because the user lacked a permission —
which would prove nothing about scoping at all.
"""

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from exams.services import publish_exam, save_marks

from . import factories as f


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@override_settings(ROOT_URLCONF='exams.tests.urls')
class BranchIsolationTests(TestCase):
    """Another institution's exam is **404, never 403** (CLAUDE.md §5).

    403 confirms the row exists, which is precisely what a probe is looking for.
    So the status code is asserted, not merely "was refused".
    """

    def setUp(self):
        self.dhaka = f.small_world(code='DHK', phone='01711000001')
        self.ctg = f.small_world(code='CTG', phone='01722000001')

    def test_another_branchs_exam_is_404(self):
        response = client_for(self.dhaka['principal']).get(
            f'/api/exams/{self.ctg["exam"].pk}/',
        )
        self.assertEqual(response.status_code, 404)

    def test_the_list_shows_only_this_institutions_exams(self):
        response = client_for(self.dhaka['principal']).get('/api/exams/')
        self.assertEqual(response.status_code, 200)
        ids = {row['id'] for row in response.json()['results']}
        self.assertEqual(ids, {self.dhaka['exam'].pk})

    def test_marks_cannot_be_saved_into_another_institution(self):
        response = client_for(self.dhaka['principal']).post(
            f'/api/exams/{self.ctg["exam"].pk}/marks/',
            {'subject': self.ctg['arabic'].pk, 'rows': []}, format='json',
        )
        self.assertEqual(response.status_code, 404)

    def test_publishing_another_institutions_exam_is_404(self):
        response = client_for(self.dhaka['principal']).post(
            f'/api/exams/{self.ctg["exam"].pk}/publish/',
        )
        self.assertEqual(response.status_code, 404)


@override_settings(ROOT_URLCONF='exams.tests.urls')
class MarkVisibilityTests(TestCase):
    """A student sees nothing until the exam is published (docs/02 §4.7).

    Marks land subject by subject over a fortnight. A student reading them as
    they arrive sees a half-finished result, compares it with a classmate's, and
    the office spends the week explaining arithmetic that is not finished.
    """

    def setUp(self):
        self.world = f.small_world()
        save_marks(
            exam=self.world['exam'], subject=self.world['arabic'],
            rows=[{'enrolment': self.world['enrolments'][0].pk, 'obtained': '90'}],
            actor=self.world['principal'],
        )
        self.student = self.world['students'][0]
        self.student_user = f.make_user(
            self.world['branch'], phone='01799000001', user_type='student',
            permissions=['marks.view', 'exams.view'],
        )
        self.student.user = self.student_user
        self.student.save(update_fields=['user'])

    def test_marks_are_invisible_to_a_student_before_publish(self):
        response = client_for(self.student_user).get('/api/marks/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'], [])

    def test_the_result_endpoint_is_404_before_publish(self):
        response = client_for(self.student_user).get(
            f'/api/exams/{self.world["exam"].pk}/result/?student={self.student.pk}',
        )
        self.assertEqual(response.status_code, 404)

    def test_staff_see_marks_throughout(self):
        """Entering them is the point; the restriction is on students only."""
        response = client_for(self.world['principal']).get('/api/marks/')
        self.assertEqual(len(response.json()['results']), 1)

    def test_marks_appear_to_the_student_once_published(self):
        publish_exam(self.world['exam'], actor=self.world['principal'])
        response = client_for(self.student_user).get('/api/marks/')
        self.assertEqual(len(response.json()['results']), 1)

    def test_a_student_cannot_read_a_classmates_result(self):
        publish_exam(self.world['exam'], actor=self.world['principal'])
        response = client_for(self.student_user).get(
            f'/api/exams/{self.world["exam"].pk}/result/'
            f'?student={self.world["students"][1].pk}',
        )
        self.assertEqual(response.status_code, 404)


@override_settings(ROOT_URLCONF='exams.tests.urls')
class PublishPermissionApiTests(TestCase):
    def setUp(self):
        self.world = f.small_world()

    def test_a_teacher_with_marks_permissions_gets_403_from_publish(self):
        teacher_user = f.make_user(
            self.world['branch'], phone='01711000009', user_type='teacher',
            permissions=['marks.view', 'marks.enter', 'exams.view', 'exams.update'],
        )
        response = client_for(teacher_user).post(
            f'/api/exams/{self.world["exam"].pk}/publish/',
        )
        self.assertEqual(response.status_code, 403)

    def test_status_cannot_be_published_by_a_patch(self):
        """The only route to PUBLISHED is the gated action."""
        response = client_for(self.world['principal']).patch(
            f'/api/exams/{self.world["exam"].pk}/',
            {'status': 'published'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.world['exam'].refresh_from_db()
        self.assertEqual(self.world['exam'].status, 'draft')


@override_settings(ROOT_URLCONF='exams.tests.urls')
class StudentReportApiTests(TestCase):
    """Every result of one student, found from the student alone."""

    def setUp(self):
        self.world = f.small_world()
        w = self.world
        save_marks(
            exam=w['exam'], subject=w['arabic'], actor=w['principal'],
            rows=[{'enrolment': w['enrolments'][0].pk, 'obtained': '90'},
                  {'enrolment': w['enrolments'][1].pk, 'obtained': '60'}],
        )
        self.url = f'/api/exams/student-report/?student={w["students"][0].pk}'

    def test_staff_see_every_exam_with_its_rank(self):
        response = client_for(self.world['principal']).get(self.url)

        self.assertEqual(response.status_code, 200, response.content)
        lines = response.json()['exams']
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]['exam'], self.world['exam'].pk)
        self.assertEqual(lines[0]['rank_in_class'], 1)
        self.assertEqual(lines[0]['class_size'], 2)

    def test_another_institutions_student_is_404(self):
        other = f.make_branch(code='CTG', name='Chittagong Madrasah')
        stranger = f.make_student(other, name='Elsewhere')

        response = client_for(self.world['principal']).get(
            f'/api/exams/student-report/?student={stranger.pk}',
        )
        self.assertEqual(response.status_code, 404)

    def test_a_student_sees_no_result_until_it_is_published(self):
        w = self.world
        user = f.make_user(w['branch'], phone='01799000002', user_type='student',
                           permissions=['marks.view', 'exams.view'])
        student = w['students'][0]
        student.user = user
        student.save(update_fields=['user'])
        client = client_for(user)

        self.assertEqual(client.get(self.url).json()['exams'], [])
        publish_exam(w['exam'], actor=w['principal'])
        self.assertEqual(len(client.get(self.url).json()['exams']), 1)

    def test_a_student_cannot_read_a_classmates_report(self):
        w = self.world
        user = f.make_user(w['branch'], phone='01799000003', user_type='student',
                           permissions=['marks.view', 'exams.view'])
        student = w['students'][0]
        student.user = user
        student.save(update_fields=['user'])

        response = client_for(user).get(
            f'/api/exams/student-report/?student={w["students"][1].pk}',
        )
        self.assertEqual(response.status_code, 404)

