"""The guarantees marks entry exists to keep (CLAUDE.md §4a, §8 rule 4).

Each test here names one thing that, if it broke, would be found months later on
a printed marksheet rather than in a stack trace.
"""

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from exams.models import ExamStatus, Mark
from exams.services import publish_exam, save_marks, student_result, tabulation

from . import factories as f


class MarkUniquenessTests(TestCase):
    """Two marks for one paper is the bug the unique constraint prevents."""

    def setUp(self):
        self.world = f.small_world()

    def _mark(self, **extra):
        world = self.world
        fields = {
            'branch': world['branch'], 'exam': world['exam'],
            'student': world['students'][0], 'enrolment': world['enrolments'][0],
            'subject': world['arabic'], 'obtained': Decimal('70.00'),
            'entered_at': timezone.now(),
        }
        fields.update(extra)
        return Mark(**fields)

    def test_one_mark_per_exam_student_subject(self):
        self._mark().save()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._mark(obtained=Decimal('80.00')).save()

    def test_same_student_may_have_a_mark_in_another_subject(self):
        self._mark().save()
        mark = self._mark()
        mark.subject = self.world['fiqh']
        mark.save()
        self.assertEqual(Mark.objects.count(), 2)

    def test_absent_and_a_score_cannot_both_be_true(self):
        """The check constraint: two contradictory claims about one student."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._mark(is_absent=True).save()


class SaveMarksTests(TestCase):
    def setUp(self):
        self.world = f.small_world()
        self.actor = self.world['principal']

    def rows(self, first='78.50', second='55.00'):
        return [
            {'enrolment': self.world['enrolments'][0].pk, 'obtained': first},
            {'enrolment': self.world['enrolments'][1].pk, 'obtained': second},
        ]

    def test_batch_upsert_is_idempotent(self):
        """The same grid saved twice writes one row per student, not two.

        A teacher on a slow connection taps Save twice far more often than they
        type a wrong number. If the second save appended, the tabulation would
        sum both rows and silently double a student's total.
        """
        first = save_marks(exam=self.world['exam'], subject=self.world['arabic'],
                           rows=self.rows(), actor=self.actor)
        self.assertEqual(first, {'created': 2, 'updated': 0, 'unchanged': 0})

        second = save_marks(exam=self.world['exam'], subject=self.world['arabic'],
                            rows=self.rows(), actor=self.actor)
        self.assertEqual(second, {'created': 0, 'updated': 0, 'unchanged': 2})
        self.assertEqual(Mark.objects.count(), 2)

    def test_a_correction_overwrites_the_cell(self):
        save_marks(exam=self.world['exam'], subject=self.world['arabic'],
                   rows=self.rows(), actor=self.actor)
        result = save_marks(exam=self.world['exam'], subject=self.world['arabic'],
                            rows=self.rows(first='81.00'), actor=self.actor)

        self.assertEqual(result['updated'], 1)
        self.assertEqual(result['unchanged'], 1)
        self.assertEqual(Mark.objects.count(), 2)
        mark = Mark.objects.get(student=self.world['students'][0])
        self.assertEqual(mark.obtained, Decimal('81.00'))

    def test_absent_clears_any_number_sent_with_it(self):
        save_marks(
            exam=self.world['exam'], subject=self.world['arabic'],
            rows=[{'enrolment': self.world['enrolments'][0].pk,
                   'obtained': '40.00', 'is_absent': True}],
            actor=self.actor,
        )
        mark = Mark.objects.get(student=self.world['students'][0])
        self.assertTrue(mark.is_absent)
        self.assertIsNone(mark.obtained)

    def test_marks_are_decimal_not_float(self):
        save_marks(exam=self.world['exam'], subject=self.world['arabic'],
                   rows=self.rows(first='33.33'), actor=self.actor)
        mark = Mark.objects.get(student=self.world['students'][0])
        self.assertIsInstance(mark.obtained, Decimal)
        self.assertEqual(mark.obtained, Decimal('33.33'))


class TeacherSubjectScopeTests(TestCase):
    """docs/08 D6, at subject granularity — the gate the class scope cannot give."""

    def setUp(self):
        self.world = f.small_world()
        self.teacher_user = f.make_user(
            self.world['branch'], phone='01711000002', user_type='teacher',
        )
        self.teacher = f.make_teacher(self.world['branch'], user=self.teacher_user)
        # Assigned to Arabic only — and made class teacher of the whole class,
        # which is exactly the case that must NOT open Fiqh to them.
        f.make_assignment(session=self.world['session'], teacher=self.teacher,
                          subject=self.world['arabic'],
                          academic_class=self.world['class'])
        self.world['class'].class_teacher = self.teacher
        self.world['class'].save(update_fields=['class_teacher'])

    def rows(self):
        return [{'enrolment': self.world['enrolments'][0].pk, 'obtained': '70'}]

    def test_teacher_may_enter_marks_for_their_own_subject(self):
        save_marks(exam=self.world['exam'], subject=self.world['arabic'],
                   rows=self.rows(), actor=self.teacher_user)
        self.assertEqual(Mark.objects.count(), 1)

    def test_teacher_may_not_enter_marks_for_a_subject_they_do_not_hold(self):
        with self.assertRaises(PermissionDenied):
            save_marks(exam=self.world['exam'], subject=self.world['fiqh'],
                       rows=self.rows(), actor=self.teacher_user)
        self.assertEqual(Mark.objects.count(), 0)

    def test_the_office_is_not_narrowed_by_subject(self):
        """A principal is gated by `marks.enter`, not by an assignment."""
        save_marks(exam=self.world['exam'], subject=self.world['fiqh'],
                   rows=self.rows(), actor=self.world['principal'])
        self.assertEqual(Mark.objects.count(), 1)


class PublishTests(TestCase):
    def setUp(self):
        self.world = f.small_world()

    def test_publish_is_principal_only(self):
        """`exams.publish` and `marks.enter` are different decisions.

        The teacher here holds every marks permission there is. Publishing must
        still refuse: the first teacher to finish their subject would otherwise
        release everybody's result, including the papers nobody has marked.
        """
        teacher_user = f.make_user(
            self.world['branch'], phone='01711000003', user_type='teacher',
            permissions=['marks.view', 'marks.enter', 'marks.update', 'exams.view'],
        )
        with self.assertRaises(PermissionDenied):
            publish_exam(self.world['exam'], actor=teacher_user)
        self.world['exam'].refresh_from_db()
        self.assertEqual(self.world['exam'].status, ExamStatus.DRAFT)

    def test_a_principal_publishes(self):
        exam = publish_exam(self.world['exam'], actor=self.world['principal'])
        self.assertEqual(exam.status, ExamStatus.PUBLISHED)
        self.assertEqual(exam.published_by, self.world['principal'])
        self.assertIsNotNone(exam.published_at)

    def test_publishing_twice_does_not_move_the_timestamp(self):
        exam = publish_exam(self.world['exam'], actor=self.world['principal'])
        published_at = exam.published_at
        again = publish_exam(exam, actor=self.world['principal'])
        self.assertEqual(again.published_at, published_at)

    def test_marks_cannot_be_edited_once_published(self):
        from rest_framework.exceptions import ValidationError

        publish_exam(self.world['exam'], actor=self.world['principal'])
        with self.assertRaises(ValidationError):
            save_marks(exam=self.world['exam'], subject=self.world['arabic'],
                       rows=[{'enrolment': self.world['enrolments'][0].pk,
                              'obtained': '10'}],
                       actor=self.world['principal'])


class ResultComputationTests(TestCase):
    """V1 computes totals and grades on read (docs/05 §5.4)."""

    def setUp(self):
        self.world = f.small_world()
        actor = self.world['principal']
        save_marks(exam=self.world['exam'], subject=self.world['arabic'],
                   rows=[{'enrolment': self.world['enrolments'][0].pk, 'obtained': '90'},
                         {'enrolment': self.world['enrolments'][1].pk, 'obtained': '40'}],
                   actor=actor)
        save_marks(exam=self.world['exam'], subject=self.world['fiqh'],
                   rows=[{'enrolment': self.world['enrolments'][0].pk, 'obtained': '80'},
                         {'enrolment': self.world['enrolments'][1].pk, 'is_absent': True}],
                   actor=actor)

    def test_total_percentage_and_grade(self):
        result = student_result(self.world['exam'], self.world['students'][0])
        self.assertEqual(result['total_marks'], Decimal('200.00'))
        self.assertEqual(result['obtained_marks'], Decimal('170.00'))
        self.assertEqual(result['percentage'], Decimal('85.00'))
        self.assertEqual(result['grade'], 'A+')
        self.assertTrue(result['is_passed'])

    def test_an_absent_paper_still_counts_its_full_marks(self):
        """Otherwise missing your weakest subject raises your percentage."""
        result = student_result(self.world['exam'], self.world['students'][1])
        self.assertEqual(result['total_marks'], Decimal('200.00'))
        self.assertEqual(result['obtained_marks'], Decimal('40.00'))
        self.assertFalse(result['is_passed'])
        self.assertIn('Fiqh', result['failed_subjects'])

    def test_tabulation_ranks_the_class(self):
        sheet = tabulation(self.world['exam'], self.world['class'])
        self.assertEqual(len(sheet['rows']), 2)
        top = next(row for row in sheet['rows'] if row['is_passed'])
        self.assertEqual(top['rank_in_class'], 1)
        failed = next(row for row in sheet['rows'] if not row['is_passed'])
        # A failed student is not ranked. Every printed tabulation sheet in the
        # country reflects that.
        self.assertIsNone(failed['rank_in_class'])


class SectionRankTests(TestCase):
    """One sheet carries the class rank and the section rank side by side."""

    def setUp(self):
        from academics.models import Section

        self.world = f.small_world()
        w = self.world
        self.section_a = Section.objects.create(branch=w['branch'], academic_class=w['class'], name='A')
        self.section_b = Section.objects.create(branch=w['branch'], academic_class=w['class'], name='B')
        third = f.make_student(w['branch'], name='Student 3')
        self.third = f.make_enrolment(student=third, session=w['session'],
                                      academic_class=w['class'], roll=3,
                                      admission_number='DHK-0003')
        first, second = w['enrolments']
        for enrolment, section in ((first, self.section_a), (second, self.section_a),
                                   (self.third, self.section_b)):
            enrolment.section = section
            enrolment.save(update_fields=['section'])

        for subject, marks in ((w['arabic'], ('90', '70', '50')), (w['fiqh'], ('80', '60', '50'))):
            save_marks(exam=w['exam'], subject=subject, actor=w['principal'], rows=[
                {'enrolment': first.pk, 'obtained': marks[0]},
                {'enrolment': second.pk, 'obtained': marks[1]},
                {'enrolment': self.third.pk, 'obtained': marks[2]},
            ])

    def test_each_row_carries_its_class_and_section_rank(self):
        sheet = tabulation(self.world['exam'], self.world['class'])
        by_enrolment = {row['enrolment']: row for row in sheet['rows']}
        first, second = self.world['enrolments']

        self.assertEqual((by_enrolment[first.pk]['rank_in_class'],
                          by_enrolment[first.pk]['rank_in_section']), (1, 1))
        self.assertEqual((by_enrolment[second.pk]['rank_in_class'],
                          by_enrolment[second.pk]['rank_in_section']), (2, 2))
        # Last in the class, first in a section of one.
        self.assertEqual((by_enrolment[self.third.pk]['rank_in_class'],
                          by_enrolment[self.third.pk]['rank_in_section']), (3, 1))
        self.assertEqual(by_enrolment[self.third.pk]['section_name'], 'B')

    def test_the_sheet_lists_the_sections_it_contains(self):
        sheet = tabulation(self.world['exam'], self.world['class'])
        self.assertEqual([row['name'] for row in sheet['sections']], ['A', 'B'])

