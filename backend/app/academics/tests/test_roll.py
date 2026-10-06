"""The class roll — issued per class, changed per student, swapped on collision.

The roll is the student's number *in one class* (শ্রেণি রোল): Class One counts
1, 2, 3 and Class Two starts again at 1. It is unique per section when the
student is in one and per class otherwise, and every test here holds a move or
a swap inside that one series.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import ActivityLog
from academics.models import Enrolment
from academics.services import RollTaken, change_roll, next_roll

from .factories import (enrol, make_assignment, make_branch, make_class,
                        make_section, make_session, make_student, make_subject,
                        make_teacher, make_user)

URLS = 'academics.tests.urls'


def rolls(*enrolments):
    return [Enrolment.objects.get(pk=e.pk).roll for e in enrolments]


class NextRollTests(TestCase):
    """A new enrolment gets the next FREE roll in its class without asking."""

    def setUp(self):
        self.branch = make_branch()
        self.session = make_session(self.branch)
        self.class_one = make_class(self.branch, self.session, name='Class 1')
        self.class_two = make_class(self.branch, self.session, name='Class 2')

    def test_each_class_counts_from_one(self):
        a = enrol(make_student(self.branch, 'A'), session=self.session,
                  academic_class=self.class_one)
        b = enrol(make_student(self.branch, 'B'), session=self.session,
                  academic_class=self.class_one)
        c = enrol(make_student(self.branch, 'C'), session=self.session,
                  academic_class=self.class_two)
        self.assertEqual(rolls(a, b, c), [1, 2, 1])

    def test_a_typed_in_roll_is_skipped_rather_than_reissued(self):
        """Roll 2 typed at admission used to be handed out again by the
        counter, and the next admission died on the unique constraint."""
        enrol(make_student(self.branch, 'Typed'), session=self.session,
              academic_class=self.class_one, roll=2)
        first = enrol(make_student(self.branch, 'A'), session=self.session,
                      academic_class=self.class_one)
        second = enrol(make_student(self.branch, 'B'), session=self.session,
                       academic_class=self.class_one)
        self.assertEqual(rolls(first, second), [1, 3])

    def test_an_imported_class_jumps_past_its_highest_roll(self):
        for number in range(1, 31):
            enrol(make_student(self.branch, f'Imported {number}'),
                  session=self.session, academic_class=self.class_one, roll=number)
        with transaction.atomic():
            issued = next_roll(branch=self.branch, session=self.session,
                               academic_class=self.class_one)
        self.assertEqual(issued, 31)

    def test_sections_count_separately(self):
        a_section = make_section(self.class_one, name='A')
        b_section = make_section(self.class_one, name='B')
        a = enrol(make_student(self.branch, 'A'), session=self.session,
                  academic_class=self.class_one, section=a_section)
        b = enrol(make_student(self.branch, 'B'), session=self.session,
                  academic_class=self.class_one, section=b_section)
        self.assertEqual(rolls(a, b), [1, 1])


class ChangeRollServiceTests(TestCase):

    def setUp(self):
        self.branch = make_branch()
        self.session = make_session(self.branch)
        self.klass = make_class(self.branch, self.session)
        self.user = make_user(self.branch)
        self.e1, self.e2, self.e3 = [
            enrol(make_student(self.branch, name), session=self.session,
                  academic_class=self.klass)
            for name in ('Abdullah', 'Bilal', 'Umar')
        ]

    def test_a_free_roll_is_simply_taken(self):
        enrolment, swapped = change_roll(self.e1, roll=9, updated_by=self.user)
        self.assertEqual(enrolment.roll, 9)
        self.assertIsNone(swapped)
        self.assertEqual(rolls(self.e1, self.e2, self.e3), [9, 2, 3])
        self.assertEqual(Enrolment.objects.get(pk=self.e1.pk).updated_by, self.user)

    def test_a_taken_roll_names_the_holder_and_writes_nothing(self):
        with self.assertRaises(RollTaken) as caught:
            change_roll(self.e3, roll=1)
        self.assertEqual(caught.exception.holder.pk, self.e1.pk)
        self.assertEqual(rolls(self.e1, self.e2, self.e3), [1, 2, 3])

    def test_swap_exchanges_the_two_rolls(self):
        enrolment, swapped = change_roll(self.e3, roll=1, swap=True)
        self.assertEqual(swapped.pk, self.e1.pk)
        self.assertEqual(rolls(self.e1, self.e2, self.e3), [3, 2, 1])

    def test_the_same_roll_is_a_no_op(self):
        enrolment, swapped = change_roll(self.e2, roll=2)
        self.assertEqual(enrolment.roll, 2)
        self.assertIsNone(swapped)

    def test_zero_and_negative_are_refused(self):
        for bad in (0, -4, None, 'x'):
            with self.assertRaises(ValidationError):
                change_roll(self.e1, roll=bad)

    def test_roll_3_in_another_class_is_not_a_collision(self):
        other_class = make_class(self.branch, self.session, name='Class 6')
        other = enrol(make_student(self.branch, 'Yusuf'), session=self.session,
                      academic_class=other_class)
        change_roll(other, roll=3)
        self.assertEqual(rolls(other, self.e3), [3, 3])

    def test_a_swap_never_reaches_into_another_section(self):
        section_a = make_section(self.klass, name='A')
        section_b = make_section(self.klass, name='B')
        in_a = enrol(make_student(self.branch, 'In A'), session=self.session,
                     academic_class=self.klass, section=section_a)
        in_b = enrol(make_student(self.branch, 'In B'), session=self.session,
                     academic_class=self.klass, section=section_b)
        # Both are roll 1 of their own section. Moving A's student to 1 again
        # is a no-op; moving to 2 is free in A even though B could have a 2.
        enrol(make_student(self.branch, 'B two'), session=self.session,
              academic_class=self.klass, section=section_b)
        change_roll(in_a, roll=2)
        self.assertEqual(rolls(in_a, in_b), [2, 1])

    def test_after_a_change_the_next_admission_still_gets_a_free_roll(self):
        change_roll(self.e1, roll=4)
        newcomer = enrol(make_student(self.branch, 'Newcomer'),
                         session=self.session, academic_class=self.klass)
        self.assertEqual(newcomer.roll, 5)


@override_settings(ROOT_URLCONF=URLS)
class ChangeRollEndpointTests(TestCase):

    def setUp(self):
        self.branch = make_branch()
        self.session = make_session(self.branch)
        self.klass = make_class(self.branch, self.session)
        self.e1, self.e2 = [
            enrol(make_student(self.branch, name), session=self.session,
                  academic_class=self.klass)
            for name in ('Abdullah', 'Bilal')
        ]
        self.user = make_user(self.branch)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def url(self, enrolment):
        return f'/api/enrolments/{enrolment.pk}/roll/'

    def test_changes_the_roll_and_logs_it(self):
        response = self.client.post(self.url(self.e1), {'roll': 7}, format='json')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['enrolment']['roll'], 7)
        self.assertIsNone(response.data['swapped_with'])
        log = ActivityLog.objects.get(model='Enrolment', object_id=str(self.e1.pk))
        self.assertEqual(log.before, {'roll': 1})
        self.assertEqual(log.after['roll'], 7)

    def test_a_collision_is_a_400_naming_the_holder_not_a_500(self):
        response = self.client.post(self.url(self.e2), {'roll': 1}, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'roll_taken')
        self.assertEqual(response.data['errors']['holder_name'], ['Abdullah'])
        self.assertEqual(response.data['errors']['holder_enrolment'], [str(self.e1.pk)])
        self.assertEqual(rolls(self.e1, self.e2), [1, 2])

    def test_swap_true_exchanges_them_and_reports_who(self):
        response = self.client.post(self.url(self.e2), {'roll': 1, 'swap': True},
                                    format='json')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['swapped_with']['id'], self.e1.pk)
        self.assertEqual(response.data['swapped_with']['roll'], 2)
        self.assertEqual(rolls(self.e1, self.e2), [2, 1])
        log = ActivityLog.objects.get(model='Enrolment', object_id=str(self.e2.pk))
        self.assertEqual(log.after['swapped_with']['enrolment'], self.e1.pk)

    def test_a_bad_roll_is_a_400(self):
        response = self.client.post(self.url(self.e1), {'roll': 0}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_branch_is_not_writable_through_the_body(self):
        other = make_branch(code='CTG', name='Chittagong Madrasah')
        self.client.post(self.url(self.e1), {'roll': 5, 'branch': other.pk},
                         format='json')
        self.assertEqual(Enrolment.objects.get(pk=self.e1.pk).branch_id, self.branch.pk)

    def test_another_institutions_enrolment_is_404(self):
        other = make_branch(code='CTG', name='Chittagong Madrasah')
        other_session = make_session(other)
        other_class = make_class(other, other_session)
        theirs = enrol(make_student(other, 'Theirs'), session=other_session,
                       academic_class=other_class)

        response = self.client.post(self.url(theirs), {'roll': 9}, format='json')

        self.assertEqual(response.status_code, 404)
        self.assertEqual(rolls(theirs), [1])

    def test_needs_students_academics_or_admissions_update(self):
        reader = make_user(self.branch, phone='01711000002',
                           permissions=['students.view', 'academics.view',
                                        'admissions.view'])
        self.client.force_authenticate(reader)
        response = self.client.post(self.url(self.e1), {'roll': 9}, format='json')
        self.assertEqual(response.status_code, 403)

        for phone, grant in (('01711000011', 'students.update'),
                             ('01711000012', 'academics.update'),
                             ('01711000013', 'admissions.update')):
            holder = make_user(self.branch, phone=phone,
                               permissions=['students.view', grant])
            self.client.force_authenticate(holder)
            response = self.client.post(self.url(self.e1), {'roll': 20}, format='json')
            self.assertEqual(response.status_code, 200, (grant, response.data))
            change_roll(Enrolment.objects.get(pk=self.e1.pk), roll=1)


@override_settings(ROOT_URLCONF=URLS)
class ChangeRollTeacherScopeTests(TestCase):
    """A teacher who may edit students reaches only their own classes' rolls."""

    def setUp(self):
        self.branch = make_branch()
        self.session = make_session(self.branch)
        self.teacher_user = make_user(
            self.branch, phone='01711000009', user_type='teacher',
            permissions=['students.view', 'students.update'],
        )
        self.teacher = make_teacher(self.branch, user=self.teacher_user)

        self.own = make_class(self.branch, self.session, name='Class 5')
        self.other = make_class(self.branch, self.session, name='Class 6')
        subject = make_subject(self.own, name='Arabic')
        make_assignment(session=self.session, teacher=self.teacher,
                        subject=subject, academic_class=self.own)

        self.mine = enrol(make_student(self.branch, 'Mine'), session=self.session,
                          academic_class=self.own)
        self.not_mine = enrol(make_student(self.branch, 'Not mine'),
                              session=self.session, academic_class=self.other)

        self.client = APIClient()
        self.client.force_authenticate(self.teacher_user)

    def test_own_class_roll_can_be_changed(self):
        response = self.client.post(f'/api/enrolments/{self.mine.pk}/roll/',
                                    {'roll': 4}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(rolls(self.mine), [4])

    def test_another_class_is_404_not_403(self):
        response = self.client.post(f'/api/enrolments/{self.not_mine.pk}/roll/',
                                    {'roll': 4}, format='json')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(rolls(self.not_mine), [1])
