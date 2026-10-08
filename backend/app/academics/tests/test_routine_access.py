"""The routine is the source of a teacher's subject access (docs/08 D6, 2026-10).

The Teachers → Assignments board is gone, so an admin says who teaches what in
exactly two places: the routine (subject teachers) and the class and section
forms (class teacher, in charge). These tests go through the API those screens
call, because the sync lives in the viewset's write hooks, and they assert
`teacher_class_scope` and `teacher_subject_scope`, which is what a teacher
actually feels.
"""

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from academics.models import SubjectAssignment
from academics.services import teacher_class_scope, teacher_subject_scope

from .factories import (make_assignment, make_branch, make_class, make_period,
                        make_routine, make_section, make_session, make_subject,
                        make_teacher, make_user)


@override_settings(ROOT_URLCONF='academics.tests.urls')
class RoutineAccessSyncTests(TestCase):
    def setUp(self):
        self.branch = make_branch()
        self.session = make_session(self.branch)
        self.class_five = make_class(self.branch, self.session, name='Class 5')
        self.arabic = make_subject(self.class_five, name='Arabic')
        self.fiqh = make_subject(self.class_five, name='Fiqh')
        self.karim = make_teacher(self.branch, name='Abdul Karim')
        self.rahim = make_teacher(self.branch, name='Abdur Rahim')
        self.p1 = make_period(self.branch, order=1)
        self.p2 = make_period(self.branch, order=2)

        self.client = APIClient()
        self.client.force_authenticate(make_user(self.branch, phone='01711000001'))

    def _cell(self, *, teacher, subject, period, day_of_week=0, section=None):
        response = self.client.post('/api/class-routines/', {
            'session': self.session.pk,
            'academic_class': self.class_five.pk,
            'section': section.pk if section else None,
            'subject': subject.pk,
            'teacher': teacher.pk,
            'period': period.pk,
            'day_of_week': day_of_week,
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data['id']

    def _scope(self, teacher):
        return (teacher_class_scope(teacher, session=self.session),
                teacher_subject_scope(teacher, session=self.session))

    def test_a_routine_cell_grants_access(self):
        self._cell(teacher=self.karim, subject=self.arabic, period=self.p1)

        classes, subjects = self._scope(self.karim)
        self.assertEqual(classes, {self.class_five.pk})
        self.assertEqual(subjects, {self.arabic.pk})

    def test_removing_the_last_covering_cell_revokes(self):
        cell = self._cell(teacher=self.karim, subject=self.arabic, period=self.p1)

        response = self.client.delete(f'/api/class-routines/{cell}/')

        self.assertEqual(response.status_code, 204)
        self.assertEqual(self._scope(self.karim), (set(), set()))
        # Deactivated, not deleted: the row is the record that he taught it.
        row = SubjectAssignment.objects.get(teacher=self.karim, subject=self.arabic)
        self.assertFalse(row.is_active)

    def test_removing_one_of_two_covering_cells_keeps_access(self):
        self._cell(teacher=self.karim, subject=self.arabic, period=self.p1)
        monday = self._cell(teacher=self.karim, subject=self.arabic,
                            period=self.p1, day_of_week=2)

        self.client.delete(f'/api/class-routines/{monday}/')

        self.assertEqual(self._scope(self.karim), ({self.class_five.pk}, {self.arabic.pk}))

    def test_changing_a_cells_teacher_moves_access(self):
        cell = self._cell(teacher=self.karim, subject=self.arabic, period=self.p1)

        response = self.client.patch(f'/api/class-routines/{cell}/',
                                     {'teacher': self.rahim.pk}, format='json')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self._scope(self.karim), (set(), set()))
        self.assertEqual(self._scope(self.rahim), ({self.class_five.pk}, {self.arabic.pk}))

    def test_changing_a_cells_subject_moves_the_subject_not_the_class(self):
        cell = self._cell(teacher=self.karim, subject=self.arabic, period=self.p1)

        self.client.patch(f'/api/class-routines/{cell}/',
                          {'subject': self.fiqh.pk}, format='json')

        self.assertEqual(self._scope(self.karim), ({self.class_five.pk}, {self.fiqh.pk}))

    def test_switching_a_cell_off_revokes_and_back_on_restores(self):
        cell = self._cell(teacher=self.karim, subject=self.arabic, period=self.p1)

        self.client.patch(f'/api/class-routines/{cell}/', {'is_active': False}, format='json')
        self.assertEqual(self._scope(self.karim), (set(), set()))

        self.client.patch(f'/api/class-routines/{cell}/', {'is_active': True}, format='json')
        self.assertEqual(self._scope(self.karim), ({self.class_five.pk}, {self.arabic.pk}))
        # Reactivated in place rather than a second row beside the old one.
        self.assertEqual(SubjectAssignment.objects.filter(
            teacher=self.karim, subject=self.arabic).count(), 1)

    def test_a_cell_in_another_section_does_not_keep_this_sections_access(self):
        """Coverage is the exact key: same class but another শাখা is a different
        grant, and must not keep a removed section's access alive."""
        a = make_section(self.class_five, name='A')
        b = make_section(self.class_five, name='B')
        cell_a = self._cell(teacher=self.karim, subject=self.arabic, period=self.p1, section=a)
        self._cell(teacher=self.karim, subject=self.arabic, period=self.p2, section=b)

        self.client.delete(f'/api/class-routines/{cell_a}/')

        live = SubjectAssignment.objects.filter(teacher=self.karim, is_active=True)
        self.assertEqual(list(live.values_list('section_id', flat=True)), [b.pk])

    def test_editing_a_cell_never_touches_an_unrelated_assignment(self):
        """Rows made before the routine owned access — the old board, a script —
        are left alone unless a cell with exactly their key is moved away."""
        make_assignment(session=self.session, teacher=self.karim,
                        subject=self.fiqh, academic_class=self.class_five)
        cell = self._cell(teacher=self.karim, subject=self.arabic, period=self.p1)

        self.client.delete(f'/api/class-routines/{cell}/')

        self.assertEqual(self._scope(self.karim), ({self.class_five.pk}, {self.fiqh.pk}))

    def test_the_class_form_sets_the_class_teacher_and_that_grants_the_class(self):
        response = self.client.patch(f'/api/classes/{self.class_five.pk}/',
                                     {'class_teacher': self.rahim.pk}, format='json')

        self.assertEqual(response.status_code, 200, response.data)
        classes, subjects = self._scope(self.rahim)
        self.assertEqual(classes, {self.class_five.pk})
        # Class responsibility is not a licence to enter its marks (D6).
        self.assertEqual(subjects, set())

    def test_the_section_form_sets_the_in_charge_and_that_grants_the_class(self):
        section = make_section(self.class_five, name='A')

        response = self.client.patch(f'/api/sections/{section.pk}/',
                                     {'in_charge': self.rahim.pk}, format='json')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self._scope(self.rahim)[0], {self.class_five.pk})

    def test_removing_a_cell_does_not_touch_class_responsibility(self):
        self.class_five.class_teacher = self.karim
        self.class_five.save(update_fields=['class_teacher'])
        cell = self._cell(teacher=self.karim, subject=self.arabic, period=self.p1)

        self.client.delete(f'/api/class-routines/{cell}/')

        self.assertEqual(self._scope(self.karim), ({self.class_five.pk}, set()))


class GrantServiceTests(TestCase):
    """The service directly, for the paths that never touch the API."""

    def test_an_inactive_cell_grants_nothing(self):
        from academics.services import grant_from_routine
        branch = make_branch()
        session = make_session(branch)
        klass = make_class(branch, session)
        cell = make_routine(session=session, academic_class=klass,
                            subject=make_subject(klass), teacher=make_teacher(branch),
                            period=make_period(branch), is_active=False)

        self.assertIsNone(grant_from_routine(cell))
        self.assertFalse(SubjectAssignment.objects.exists())
