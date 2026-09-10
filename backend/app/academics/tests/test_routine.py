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
