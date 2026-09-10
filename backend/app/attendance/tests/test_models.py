"""The two guarantees the database itself has to make (docs/03 §6 and §13).

Both are tested against the database and not against a serializer, because that
is the claim: application code is not a constraint, and the row must be
impossible to write however it is reached — a management command, a shell, a
future import script.
"""

from datetime import date

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from attendance.models import (AttendanceStatus, DailyAttendance, PersonType)

from .factories import (make_branch, make_session, make_student, make_teacher,
                        make_user)


class ExactlyOnePersonTests(TestCase):
    """`dailyatt_exactly_one_person` — docs/08 D5 raised this from two FKs to three."""

    @classmethod
    def setUpTestData(cls):
        cls.branch = make_branch()
        cls.session = make_session(cls.branch)
        cls.user = make_user(cls.branch)
        cls.student = make_student(cls.branch)
        cls.teacher = make_teacher(cls.branch)

    def row(self, **overrides):
        fields = {
            'branch': self.branch,
            'date': date(2026, 3, 2),
            'person_type': PersonType.STUDENT,
            'status': AttendanceStatus.PRESENT,
            'taken_by': self.user,
            'taken_at': timezone.now(),
        }
        fields.update(overrides)
        return DailyAttendance(**fields)

    def test_all_three_null_is_refused(self):
        """An orphan attendance row belongs to nobody and can never be found again."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.row().save()

    def test_two_people_at_once_is_refused(self):
        """Double-owned: the register would count one absence against two people."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.row(student=self.student, teacher=self.teacher).save()

    def test_person_type_must_agree_with_the_fk(self):
        """A row typed `student` while pointing at a teacher is invisible to every
        register query, so the constraint folds the discriminator in."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.row(person_type=PersonType.STUDENT, teacher=self.teacher).save()

    def test_exactly_one_is_accepted(self):
        self.row(student=self.student).save()
        self.row(person_type=PersonType.TEACHER, teacher=self.teacher).save()
        self.assertEqual(DailyAttendance.objects.count(), 2)


class OneRowPerPersonPerDayTests(TestCase):
    """`dailyatt_unique_student_day` — two conflicting records for one day.

    The doc writes the key as the full six-column tuple, which Postgres does not
    enforce for a student row because teacher and employee are NULL and NULLs
    compare as distinct. These tests are against the behaviour, not the
    constraint name, so they hold whichever constraint is doing the work.
    """

    @classmethod
    def setUpTestData(cls):
        cls.branch = make_branch()
        cls.session = make_session(cls.branch)
        cls.user = make_user(cls.branch)
        cls.student = make_student(cls.branch)
        cls.day = date(2026, 3, 2)

    def mark(self, status):
        return DailyAttendance.objects.create(
            branch=self.branch, date=self.day,
            person_type=PersonType.STUDENT, student=self.student,
            status=status, taken_by=self.user, taken_at=timezone.now(),
        )

    def test_a_second_row_for_the_same_day_is_refused(self):
        self.mark(AttendanceStatus.PRESENT)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.mark(AttendanceStatus.ABSENT)

    def test_a_correction_updates_the_row_rather_than_duplicating_it(self):
        """docs/08 D3: corrections overwrite in place, and the upsert is what the
        service does — `update_or_create` on the same key the database enforces."""
        self.mark(AttendanceStatus.PRESENT)

        row, created = DailyAttendance.objects.update_or_create(
            branch=self.branch, date=self.day,
            person_type=PersonType.STUDENT, student=self.student,
            defaults={'status': AttendanceStatus.ABSENT,
                      'taken_by': self.user, 'taken_at': timezone.now()},
        )

        self.assertFalse(created)
        self.assertEqual(DailyAttendance.objects.count(), 1)
        self.assertEqual(row.status, AttendanceStatus.ABSENT)

    def test_another_day_is_a_different_row(self):
        self.mark(AttendanceStatus.PRESENT)
        self.day = date(2026, 3, 3)
        self.mark(AttendanceStatus.ABSENT)
        self.assertEqual(DailyAttendance.objects.count(), 2)

    def test_another_institution_may_mark_the_same_person_the_same_day(self):
        """The key is per branch. A student who transferred mid-year has a row in
        each institution for the handover day, and neither may block the other."""
        self.mark(AttendanceStatus.PRESENT)
        other = make_branch(code='CTG', name='Chittagong Madrasah')

        DailyAttendance.objects.create(
            branch=other, date=self.day,
            person_type=PersonType.STUDENT, student=self.student,
            status=AttendanceStatus.ABSENT,
            taken_by=self.user, taken_at=timezone.now(),
        )
        self.assertEqual(DailyAttendance.objects.count(), 2)
