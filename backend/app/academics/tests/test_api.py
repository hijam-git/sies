"""Branch isolation on every academics endpoint — 404, not 403 (CLAUDE.md §5).

Enrolment is deliberately absent: it points at `students.Student`, which is
written in parallel, and a fixture that needed it would make this whole module
unrunnable. Its numbering guarantee is covered in `test_numbers.py`, where the
guarantee actually lives.
"""

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from academics.models import AcademicClass

from .factories import (make_branch, make_class, make_period,
                        make_section, make_session, make_subject, make_teacher,
                        make_user)


@override_settings(ROOT_URLCONF='academics.tests.urls')
class AcademicsBranchIsolationTests(TestCase):
    def setUp(self):
        self.a = make_branch(code='DHK', name='Dhaka Madrasah')
        self.b = make_branch(code='CTG', name='Chittagong Madrasah')
        self.a_session = make_session(self.a)
        self.b_session = make_session(self.b)

        self.a_class = make_class(self.a, self.a_session, name='Class 5')
        self.b_class = make_class(self.b, self.b_session, name='Class 5')
        self.b_section = make_section(self.b_class, name='A')
        self.b_subject = make_subject(self.b_class, name='Arabic')
        self.b_period = make_period(self.b, order=1)

        self.client = APIClient()
        self.client.force_authenticate(make_user(self.a, phone='01711000001'))

    def test_every_detail_route_is_404_for_another_institution(self):
        for path in (
            f'/api/classes/{self.b_class.pk}/',
            f'/api/sections/{self.b_section.pk}/',
            f'/api/subjects/{self.b_subject.pk}/',
            f'/api/periods/{self.b_period.pk}/',
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_another_institutions_class_cannot_be_written(self):
        response = self.client.patch(f'/api/classes/{self.b_class.pk}/',
                                     {'name': 'Renamed'}, format='json')

        self.assertEqual(response.status_code, 404)
        self.b_class.refresh_from_db()
        self.assertEqual(self.b_class.name, 'Class 5')

    def test_another_institutions_class_cannot_be_deleted(self):
        response = self.client.delete(f'/api/classes/{self.b_class.pk}/')

        self.assertEqual(response.status_code, 404)
        self.assertTrue(AcademicClass.objects.filter(pk=self.b_class.pk).exists())

    def test_lists_show_only_the_callers_own_institution(self):
        response = self.client.get('/api/classes/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['id'] for row in response.data['results']],
                         [self.a_class.pk])

    def test_a_class_cannot_be_pointed_at_another_institutions_session(self):
        """A scoped queryset controls what you can *read*; nothing about a plain
        FK stops you writing a pointer at somebody else's academic year."""
        response = self.client.post('/api/classes/', {
            'name': 'Class 9',
            'stream': self.a.stream_set.first().pk,
            'session': self.b_session.pk,
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('session', response.data.get('errors', response.data))

    def test_a_class_cannot_take_another_institutions_teacher_as_class_teacher(self):
        foreign_teacher = make_teacher(self.b, name='Chittagong Teacher')

        response = self.client.post('/api/classes/', {
            'name': 'Class 9',
            'stream': self.a.stream_set.first().pk,
            'session': self.a_session.pk,
            'class_teacher': foreign_teacher.pk,
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('class_teacher', response.data.get('errors', response.data))

    def test_a_client_supplied_branch_is_ignored(self):
        response = self.client.post('/api/classes/', {
            'name': 'Class 9',
            'stream': self.a.stream_set.first().pk,
            'session': self.a_session.pk,
            'branch': self.b.pk,
        }, format='json')

        self.assertEqual(response.status_code, 201, response.data)
        created = AcademicClass.objects.get(pk=response.data['id'])
        self.assertEqual(created.branch_id, self.a.pk)

    def test_the_year_is_denormalised_from_the_session(self):
        response = self.client.post('/api/classes/', {
            'name': 'Class 9',
            'stream': self.a.stream_set.first().pk,
            'session': self.a_session.pk,
        }, format='json')

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['year'], self.a_session.starts_on.year)
