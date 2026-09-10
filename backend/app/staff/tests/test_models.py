"""What D5 actually decided: two models, two tables, one abstract base.

This is worth a test rather than a comment because the failure mode is silent.
Someone "simplifying" `PersonProfile` into a concrete parent would turn every
Teacher read into a join and every Teacher insert into two inserts, and nothing
in the API would look different until the day a shared row went missing.
"""

from django.test import TestCase

from staff.models import Employee, PersonProfile, Teacher

from .factories import make_branch, make_employee, make_teacher


class AbstractBaseTests(TestCase):
    def test_person_profile_has_no_table(self):
        self.assertTrue(PersonProfile._meta.abstract)

    def test_teacher_and_employee_are_separate_tables(self):
        self.assertNotEqual(Teacher._meta.db_table, Employee._meta.db_table)

    def test_neither_inherits_from_a_concrete_parent(self):
        """Abstract inheritance, not multi-table inheritance (docs/08 D5).

        `parents` is empty for abstract inheritance and holds the parent model
        for MTI — which is the difference between one clean table and a hidden
        join on every single read.
        """
        self.assertEqual(Teacher._meta.parents, {})
        self.assertEqual(Employee._meta.parents, {})

    def test_both_carry_every_shared_field(self):
        shared = {f.name for f in PersonProfile._meta.get_fields()}
        teacher_fields = {f.name for f in Teacher._meta.get_fields()}
        employee_fields = {f.name for f in Employee._meta.get_fields()}

        self.assertTrue(shared <= teacher_fields)
        self.assertTrue(shared <= employee_fields)

    def test_salary_columns_are_decimal_not_float(self):
        """CLAUDE.md §1. A binary float cannot represent 0.10, so a payroll built
        on one drifts by paisa per row and stops reconciling."""
        for model in (Teacher, Employee):
            for name in ('basic_salary', 'allowances', 'deductions'):
                field = model._meta.get_field(name)
                self.assertEqual(field.get_internal_type(), 'DecimalField', name)
                self.assertEqual(field.max_digits, 12)
                self.assertEqual(field.decimal_places, 2)


class ProfileBehaviourTests(TestCase):
    def setUp(self):
        self.branch = make_branch()

    def test_a_teacher_and_an_employee_can_share_a_name_and_a_phone(self):
        """The same person moving from teaching to non-teaching gets a second
        row, not an edited one (docs/08 D5)."""
        teacher = make_teacher(self.branch, name='Same Person', phone='01711111111')
        employee = make_employee(self.branch, name='Same Person', phone='01711111111')

        self.assertNotEqual(teacher.pk, employee.pk)
        self.assertNotEqual(teacher.teacher_id, employee.employee_id)

    def test_gross_salary_is_basic_plus_allowances_minus_deductions(self):
        from decimal import Decimal

        teacher = make_teacher(
            self.branch, basic_salary=Decimal('12000.50'),
            allowances=Decimal('2000.25'), deductions=Decimal('500.75'),
        )
        self.assertEqual(teacher.gross_salary, Decimal('13500.00'))
