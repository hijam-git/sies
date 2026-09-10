"""The timetable clash constraints (docs/03 §3, docs/08 D7).

**A teacher cannot be in two rooms at once.** Timetable clashes are the classic
school-software bug, and the point of putting them in `Meta.constraints` is that
the database refuses them even on the paths that never touch a serializer — the
bulk import, a management command, the Django admin. These tests assert the
database, not the validator.
"""

from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from academics.models import ClassRoutine

from .factories import (make_branch, make_class, make_period,
                        make_routine, make_section, make_session, make_subject,
                        make_teacher, make_user)


class RoutineConstraintTests(TestCase):
    def setUp(self):
        self.branch = make_branch()
        self.session = make_session(self.branch)
        self.period = make_period(self.branch, order=1)
        self.teacher = make_teacher(self.branch, name='Abdul Karim')

        self.class_five = make_class(self.branch, self.session, name='Class 5')
        self.class_six = make_class(self.branch, self.session, name='Class 6')
        self.arabic = make_subject(self.class_five, name='Arabic')
        self.fiqh = make_subject(self.class_five, name='Fiqh')
        self.maths = make_subject(self.class_six, name='Mathematics')

    def test_a_teacher_cannot_be_in_two_rooms_at_once(self):
        """The load-bearing constraint. Same teacher, same day, same period,
        two different classes — refused by the database."""
        make_routine(session=self.session, academic_class=self.class_five,
                     subject=self.arabic, teacher=self.teacher,
                     period=self.period, day_of_week=0)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_routine(session=self.session, academic_class=self.class_six,
                             subject=self.maths, teacher=self.teacher,
                             period=self.period, day_of_week=0)

    def test_the_same_teacher_may_teach_the_same_period_on_another_day(self):
        make_routine(session=self.session, academic_class=self.class_five,
                     subject=self.arabic, teacher=self.teacher,
                     period=self.period, day_of_week=0)
        make_routine(session=self.session, academic_class=self.class_six,
                     subject=self.maths, teacher=self.teacher,
                     period=self.period, day_of_week=1)

        self.assertEqual(ClassRoutine.objects.count(), 2)

    def test_a_class_cannot_have_two_subjects_in_one_period(self):
        make_routine(session=self.session, academic_class=self.class_five,
                     subject=self.arabic, teacher=self.teacher,
                     period=self.period, day_of_week=0)
        other_teacher = make_teacher(self.branch, name='Nurul Islam')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_routine(session=self.session, academic_class=self.class_five,
                             subject=self.fiqh, teacher=other_teacher,
                             period=self.period, day_of_week=0)

    def test_two_sections_of_one_class_clash_only_with_themselves(self):
        """A sectioned class is two rooms, so section A and section B may run the
        same period — with different teachers."""
        section_a = make_section(self.class_five, name='A')
        section_b = make_section(self.class_five, name='B')
        other_teacher = make_teacher(self.branch, name='Nurul Islam')

        make_routine(session=self.session, academic_class=self.class_five,
                     section=section_a, subject=self.arabic, teacher=self.teacher,
                     period=self.period, day_of_week=0)
        make_routine(session=self.session, academic_class=self.class_five,
                     section=section_b, subject=self.arabic, teacher=other_teacher,
                     period=self.period, day_of_week=0)

        self.assertEqual(ClassRoutine.objects.count(), 2)

        third_teacher = make_teacher(self.branch, name='Kamal Uddin')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_routine(session=self.session, academic_class=self.class_five,
                             section=section_a, subject=self.fiqh,
                             teacher=third_teacher, period=self.period,
                             day_of_week=0)

    def test_a_section_less_class_is_still_constrained(self):
        """Postgres treats NULLs as distinct, so a single constraint on
        (class, section, day, period) would let a class with no sections be
        double-booked freely. The partial constraint pair is what prevents it."""
        other_teacher = make_teacher(self.branch, name='Nurul Islam')
        make_routine(session=self.session, academic_class=self.class_six,
                     subject=self.maths, teacher=self.teacher,
                     period=self.period, day_of_week=2)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_routine(session=self.session, academic_class=self.class_six,
                             subject=self.maths, teacher=other_teacher,
                             period=self.period, day_of_week=2)


@override_settings(ROOT_URLCONF='academics.tests.urls')
class RoutineApiTests(TestCase):
    """The serializer says *which* teacher is busy; an IntegrityError cannot."""

    def setUp(self):
        self.branch = make_branch()
        self.session = make_session(self.branch)
        self.period = make_period(self.branch, order=1)
        self.teacher = make_teacher(self.branch, name='Abdul Karim')
        self.class_five = make_class(self.branch, self.session, name='Class 5')
        self.class_six = make_class(self.branch, self.session, name='Class 6')
        self.arabic = make_subject(self.class_five, name='Arabic')
        self.maths = make_subject(self.class_six, name='Mathematics')

        self.client = APIClient()
        self.client.force_authenticate(make_user(self.branch, phone='01711000001'))

    def _payload(self, academic_class, subject):
        return {
            'session': self.session.pk,
            'academic_class': academic_class.pk,
            'subject': subject.pk,
            'teacher': self.teacher.pk,
            'period': self.period.pk,
            'day_of_week': 0,
        }

    def test_a_double_booking_is_a_400_naming_the_teacher(self):
        first = self.client.post('/api/class-routines/',
                                 self._payload(self.class_five, self.arabic),
                                 format='json')
        self.assertEqual(first.status_code, 201, first.data)

        clash = self.client.post('/api/class-routines/',
                                 self._payload(self.class_six, self.maths),
                                 format='json')

        self.assertEqual(clash.status_code, 400)
        self.assertIn('teacher', clash.data.get('errors', clash.data))

    def test_a_subject_from_another_class_is_refused(self):
        response = self.client.post('/api/class-routines/',
                                    self._payload(self.class_five, self.maths),
                                    format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('subject', response.data.get('errors', response.data))


@override_settings(ROOT_URLCONF='academics.tests.urls')
class MyRoutineTests(TestCase):
    """`GET /api/class-routines/my-routine/` — a teacher's own week (docs/08 D7).

    The rule under test is the one that would be a real leak if it broke: this
    action answers *my* week, so nothing a client sends may point it at somebody
    else's. The list endpoint is a different question and is scoped differently.
    """

    def setUp(self):
        self.branch = make_branch()
        self.session = make_session(self.branch)
        self.session.is_current = True
        self.session.save(update_fields=['is_current'])

        self.first = make_period(self.branch, order=1)
        self.second = make_period(self.branch, order=2)

        self.class_five = make_class(self.branch, self.session, name='Class 5')
        self.class_six = make_class(self.branch, self.session, name='Class 6')
        self.arabic = make_subject(self.class_five, name='Arabic')
        self.maths = make_subject(self.class_six, name='Mathematics')

        # Teacher A is class teacher of Class 5, which is what makes the leak
        # possible at all: Class 5 is inside A's D6 scope, so a naive
        # `?teacher=B` on the list endpoint would hand A the rows B teaches
        # there. My routine must not.
        self.user_a = make_user(self.branch, phone='01711000011', user_type='teacher')
        self.teacher_a = make_teacher(self.branch, name='Abdul Karim', user=self.user_a)
        self.class_five.class_teacher = self.teacher_a
        self.class_five.save(update_fields=['class_teacher'])

        self.teacher_b = make_teacher(self.branch, name='Nurul Islam')

        self.mine = make_routine(session=self.session, academic_class=self.class_five,
                                 subject=self.arabic, teacher=self.teacher_a,
                                 period=self.first, day_of_week=0)
        # B teaches inside A's own class, at another hour.
        self.theirs = make_routine(session=self.session, academic_class=self.class_five,
                                   subject=self.arabic, teacher=self.teacher_b,
                                   period=self.second, day_of_week=0)

        self.client = APIClient()
        self.client.force_authenticate(self.user_a)

    def get(self, query=''):
        return self.client.get(f'/api/class-routines/my-routine/{query}')

    def test_a_teacher_sees_their_own_week(self):
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['id'] for row in response.data['rows']], [self.mine.pk])
        self.assertEqual(response.data['session'], self.session.pk)

    def test_asking_for_another_teacher_still_returns_your_own_rows(self):
        """The leak this action exists to close. `?teacher=B` is ignored."""
        response = self.get(f'?teacher={self.teacher_b.pk}')
        self.assertEqual(response.status_code, 200)
        ids = [row['id'] for row in response.data['rows']]
        self.assertEqual(ids, [self.mine.pk])
        self.assertNotIn(self.theirs.pk, ids)

    def test_rows_carry_the_names_the_grid_draws(self):
        row = self.get().data['rows'][0]
        self.assertEqual(row['class_name'], 'Class 5')
        self.assertEqual(row['subject_name'], 'Arabic')
        self.assertEqual(row['period_order'], 1)
        self.assertFalse(row['is_break'])

    def test_a_routine_row_without_a_subject_assignment_still_appears(self):
        """The D6 class scope is the wrong gate for this action: a routine row IS
        the claim on the class, so a teacher with no `SubjectAssignment` must not
        lose a period off their own timetable."""
        make_routine(session=self.session, academic_class=self.class_six,
                     subject=self.maths, teacher=self.teacher_a,
                     period=self.second, day_of_week=1)
        self.assertEqual(len(self.get().data['rows']), 2)

    def test_another_session_is_not_mixed_in(self):
        other = make_session(self.branch, name='2027')
        make_routine(session=other, academic_class=self.class_five,
                     subject=self.arabic, teacher=self.teacher_a,
                     period=self.second, day_of_week=3)

        self.assertEqual(len(self.get().data['rows']), 1)
        self.assertEqual(len(self.get(f'?session={other.pk}').data['rows']), 1)

    def test_another_institutions_session_yields_nothing_rather_than_theirs(self):
        elsewhere = make_branch(code='CTG', name='Chittagong Madrasah')
        their_session = make_session(elsewhere, name='2026')

        response = self.get(f'?session={their_session.pk}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['rows'], [])

    def test_an_account_with_no_teacher_profile_gets_an_empty_week(self):
        principal = make_user(self.branch, phone='01711000012')
        client = APIClient()
        client.force_authenticate(principal)

        response = client.get('/api/class-routines/my-routine/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['rows'], [])
