"""A teacher reads the students of their own classes (docs/08 D6).

The attendance register was scoped by assignment and the student record behind
it was not, so `students.view` — which a teacher needs to see their own roster —
returned every student in the institution: phone, NID, address, and the
guardians' numbers with them.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from academics.services import enrol_student
from academics.models import SubjectAssignment
from academics.models import Subject
from staff.services import create_teacher

from .factories import (make_branch, make_class, make_session, make_student,
                        make_user)


class TeacherScopedStudentTests(TestCase):
    def setUp(self):
        from datetime import date

        self.branch = make_branch()
        self.session = make_session(self.branch)
        self.mine = make_class(self.branch, self.session, name='Class 5')
        self.theirs = make_class(self.branch, self.session, name='Class 9')

        self.teacher_user = make_user(self.branch, user_type='teacher',
                                      permissions=['students.view'])
        teacher = create_teacher(branch=self.branch, name='Abdul Karim',
                                 user=self.teacher_user)
        subject = Subject.objects.create(
            branch=self.branch, stream=self.mine.stream, academic_class=self.mine,
            name='Arabic',
        )
        SubjectAssignment.objects.create(
            branch=self.branch, session=self.session, teacher=teacher,
            subject=subject, academic_class=self.mine,
        )

        self.ours = make_student(self.branch, name='In My Class')
        self.other = make_student(self.branch, name='Not My Class')
        enrol_student(branch=self.branch, student=self.ours, session=self.session,
                      academic_class=self.mine, enrolled_on=date(2026, 1, 5))
        enrol_student(branch=self.branch, student=self.other, session=self.session,
                      academic_class=self.theirs, enrolled_on=date(2026, 1, 5))

        self.client = APIClient()
        self.client.force_authenticate(self.teacher_user)

    def test_the_list_holds_only_their_own_classes_students(self):
        response = self.client.get('/api/students/')

        self.assertEqual([row['name'] for row in response.data['results']],
                         ['In My Class'])

    def test_another_classs_student_is_404_not_403(self):
        """404, because 403 confirms the record exists (CLAUDE.md §5)."""
        response = self.client.get(f'/api/students/{self.other.pk}/')

        self.assertEqual(response.status_code, 404)

    def test_their_own_students_record_is_readable(self):
        response = self.client.get(f'/api/students/{self.ours.pk}/')

        self.assertEqual(response.status_code, 200)

    def test_the_principal_sees_the_whole_institution(self):
        """The scope is about teachers; an office account is not narrowed."""
        self.client.force_authenticate(make_user(self.branch, user_type='principal',
                                                 permissions=['students.view']))

        response = self.client.get('/api/students/')

        self.assertEqual(
            sorted(row['name'] for row in response.data['results']),
            ['In My Class', 'Not My Class'],
        )
