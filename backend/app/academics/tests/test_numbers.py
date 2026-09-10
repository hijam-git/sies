"""Admission numbers and rolls — gapless, per branch, per session.

The counter mechanism itself is tested in `staff.tests.test_numbers`; this module
covers what `academics` puts on top of it: the printed format, the per-session
reset, and the per-(class, section) roll scope.

`enrol_student()` is not exercised end to end here because `Enrolment` points at
`students.Student`, which is built in parallel. Everything up to the moment the
row is written is covered.
"""

from django.db import transaction
from django.test import TestCase

from academics.services import next_admission_number, next_roll

from .factories import make_branch, make_class, make_section, make_session


class AdmissionNumberTests(TestCase):
    def setUp(self):
        self.branch = make_branch(code='DHK')
        self.session = make_session(self.branch, name='2026')

    def test_the_format_is_the_one_printed_on_the_slip(self):
        with transaction.atomic():
            number = next_admission_number(branch=self.branch, session=self.session)
        self.assertEqual(number, 'ADM-DHK-2026-00001')

    def test_numbers_are_consecutive_and_gapless(self):
        with transaction.atomic():
            issued = [next_admission_number(branch=self.branch, session=self.session)
                      for _ in range(3)]
        self.assertEqual(issued, ['ADM-DHK-2026-00001',
                                  'ADM-DHK-2026-00002',
                                  'ADM-DHK-2026-00003'])

    def test_the_counter_resets_per_session(self):
        """"The 417th admission of 2026" is what makes the number readable; the
        year in the string is what stops 2027's 417 colliding with it."""
        next_year = make_session(self.branch, name='2027',
                                 starts_on=self.session.starts_on.replace(year=2027),
                                 ends_on=self.session.ends_on.replace(year=2027))
        with transaction.atomic():
            next_admission_number(branch=self.branch, session=self.session)
            next_admission_number(branch=self.branch, session=self.session)
            first_of_2027 = next_admission_number(branch=self.branch, session=next_year)

        self.assertEqual(first_of_2027, 'ADM-DHK-2027-00001')

    def test_two_institutions_count_independently(self):
        other = make_branch(code='CTG', name='Chittagong Madrasah')
        other_session = make_session(other, name='2026')

        with transaction.atomic():
            mine = next_admission_number(branch=self.branch, session=self.session)
            theirs = next_admission_number(branch=other, session=other_session)

        self.assertEqual(mine, 'ADM-DHK-2026-00001')
        self.assertEqual(theirs, 'ADM-CTG-2026-00001')


class RollTests(TestCase):
    def setUp(self):
        self.branch = make_branch(code='DHK')
        self.session = make_session(self.branch, name='2026')
        self.class_five = make_class(self.branch, self.session, name='Class 5')

    def test_rolls_start_at_one_and_have_no_gaps(self):
        with transaction.atomic():
            rolls = [next_roll(branch=self.branch, session=self.session,
                               academic_class=self.class_five)
                     for _ in range(4)]
        self.assertEqual(rolls, [1, 2, 3, 4])

    def test_each_section_has_its_own_roll_series(self):
        section_a = make_section(self.class_five, name='A')
        section_b = make_section(self.class_five, name='B')

        with transaction.atomic():
            next_roll(branch=self.branch, session=self.session,
                      academic_class=self.class_five, section=section_a)
            first_in_b = next_roll(branch=self.branch, session=self.session,
                                   academic_class=self.class_five, section=section_b)

        self.assertEqual(first_in_b, 1)

    def test_each_class_has_its_own_roll_series(self):
        class_six = make_class(self.branch, self.session, name='Class 6')

        with transaction.atomic():
            next_roll(branch=self.branch, session=self.session,
                      academic_class=self.class_five)
            first_in_six = next_roll(branch=self.branch, session=self.session,
                                     academic_class=class_six)

        self.assertEqual(first_in_six, 1)

    def test_a_new_session_restarts_the_roll(self):
        next_year = make_session(self.branch, name='2027',
                                 starts_on=self.session.starts_on.replace(year=2027),
                                 ends_on=self.session.ends_on.replace(year=2027))
        with transaction.atomic():
            next_roll(branch=self.branch, session=self.session,
                      academic_class=self.class_five)
            first_next_year = next_roll(branch=self.branch, session=next_year,
                                        academic_class=self.class_five)

        self.assertEqual(first_next_year, 1)
