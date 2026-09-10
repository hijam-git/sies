"""Teacher scoping — the second gate (docs/08 D6).

A permission answers *what verb*; an assignment answers *which classes*. Without
the second gate, `attendance.take` lets a teacher mark every class in the
institution. These tests hold that gate in place, including its off switch and
the people it must never apply to.

Every test runs with a resolver granting everything, so a refusal here proves the
*scope* refused it and not that the account lacked a permission string.
"""

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from academics.services import teacher_class_scope, teacher_subject_scope

from .factories import (make_assignment, make_branch, make_class,
                        make_section, make_session, make_subject, make_teacher,
                        make_user)


class ScopeServiceTests(TestCase):
    """`teacher_class_scope` is the single definition of "which classes"."""

    def setUp(self):
        self.branch = make_branch()
        self.session = make_session(self.branch)
        self.teacher = make_teacher(self.branch, name='Abdul Karim')

        self.responsible_for = make_class(self.branch, self.session, name='Class 5')
        self.teaches_in = make_class(self.branch, self.session, name='Class 6')
        self.unrelated = make_class(self.branch, self.session, name='Class 7')

        self.responsible_for.class_teacher = self.teacher
        self.responsible_for.save(update_fields=['class_teacher'])

        self.maths = make_subject(self.teaches_in, name='Mathematics')
        make_assignment(session=self.session, teacher=self.teacher,
                        subject=self.maths, academic_class=self.teaches_in)

    def test_the_scope_is_responsibility_union_assignment(self):
        scope = teacher_class_scope(self.teacher, session=self.session)
        self.assertEqual(scope, {self.responsible_for.pk, self.teaches_in.pk})
        self.assertNotIn(self.unrelated.pk, scope)

    def test_section_in_charge_also_grants_the_class(self):
        section = make_section(self.unrelated, name='A')
        section.in_charge = self.teacher
        section.save(update_fields=['in_charge'])

        self.assertIn(self.unrelated.pk,
                      teacher_class_scope(self.teacher, session=self.session))

    def test_scope_is_per_session(self):
        """A teacher who was class teacher of Class 5 in 2026 must not still
        reach it in 2027 (docs/08 D6)."""
        next_session = make_session(self.branch, name='2027')
        self.assertEqual(teacher_class_scope(self.teacher, session=next_session), set())

    def test_the_subject_scope_is_narrower_than_the_class_scope(self):
        """Being class teacher of Class 5 means seeing its students, not entering
        its mathematics marks."""
        arabic = make_subject(self.responsible_for, name='Arabic')
        subjects = teacher_subject_scope(self.teacher, session=self.session)

        self.assertEqual(subjects, {self.maths.pk})
        self.assertNotIn(arabic.pk, subjects)

    def test_a_teacher_with_no_assignments_reaches_nothing(self):
        stranger = make_teacher(self.branch, name='Nurul Islam')
        self.assertEqual(teacher_class_scope(stranger, session=self.session), set())


@override_settings(ROOT_URLCONF='academics.tests.urls')
class ScopedApiTests(TestCase):
    def setUp(self):
        self.branch = make_branch()
        self.session = make_session(self.branch)

        self.teacher_user = make_user(self.branch, phone='01711000002',
                                      user_type='teacher')
        self.teacher = make_teacher(self.branch, name='Abdul Karim',
                                    user=self.teacher_user)

        self.mine = make_class(self.branch, self.session, name='Class 5')
        self.mine.class_teacher = self.teacher
        self.mine.save(update_fields=['class_teacher'])
        self.theirs = make_class(self.branch, self.session, name='Class 7')

        self.client = APIClient()

    def test_a_teacher_lists_only_their_own_classes(self):
        self.client.force_authenticate(self.teacher_user)

        response = self.client.get('/api/classes/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['name'] for row in response.data['results']], ['Class 5'])

    def test_an_out_of_scope_class_is_404_not_403(self):
        """404, because 403 would confirm the class exists — and because the
        restriction should read as a shorter list, not as an error (D6)."""
        self.client.force_authenticate(self.teacher_user)

        response = self.client.get(f'/api/classes/{self.theirs.pk}/')

        self.assertEqual(response.status_code, 404)

    def test_an_out_of_scope_class_cannot_be_written_either(self):
        self.client.force_authenticate(self.teacher_user)

        response = self.client.patch(f'/api/classes/{self.theirs.pk}/',
                                     {'name': 'Renamed'}, format='json')

        self.assertEqual(response.status_code, 404)
        self.theirs.refresh_from_db()
        self.assertEqual(self.theirs.name, 'Class 7')

    def test_turning_the_switch_off_gives_the_teacher_everything(self):
        """A small madrasah where three teachers cover everything (D6)."""
        self.branch.restrict_teachers_to_assigned_classes = False
        self.branch.save(update_fields=['restrict_teachers_to_assigned_classes'])
        self.client.force_authenticate(self.teacher_user)

        response = self.client.get('/api/classes/')

        self.assertEqual(
            sorted(row['name'] for row in response.data['results']),
            ['Class 5', 'Class 7'],
        )

    def test_a_principal_is_never_scoped(self):
        """Principals, accountants and the platform admin see the whole
        institution — the scope applies to the `teacher` user type (D6)."""
        self.client.force_authenticate(make_user(self.branch, phone='01711000003'))

        response = self.client.get('/api/classes/')

        self.assertEqual(
            sorted(row['name'] for row in response.data['results']),
            ['Class 5', 'Class 7'],
        )

    def test_a_teacher_typed_account_with_no_profile_sees_nothing(self):
        """The safe failure: an empty class list files a support ticket, an
        unfiltered one never gets mentioned."""
        orphan = make_user(self.branch, phone='01711000004', user_type='teacher')
        self.client.force_authenticate(orphan)

        response = self.client.get('/api/classes/')

        self.assertEqual(response.data['results'], [])

    def test_the_subject_assignment_screen_is_not_teacher_scoped(self):
        """It is the admin screen that grants the scope; scoping it by the scope
        it grants would be circular."""
        maths = make_subject(self.theirs, name='Mathematics')
        other = make_teacher(self.branch, name='Nurul Islam')
        make_assignment(session=self.session, teacher=other, subject=maths,
                        academic_class=self.theirs)
        self.client.force_authenticate(self.teacher_user)

        response = self.client.get('/api/subject-assignments/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
