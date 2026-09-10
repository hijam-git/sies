"""Idempotency — the test this phase exists for (docs/06 #9).

The monthly job is retried by Celery, fired by beat on two workers during a
rolling deploy, and triggered by hand from a management command by an
accountant who is not sure it ran. All three must produce one invoice per
student per category per period. The guarantee is a unique constraint, and this
is where it is held down.
"""

from decimal import Decimal

from django.test import TestCase

from fees.models import Fee, FeeStatus, GeneratedBy
from fees.services import generate_monthly_fees

from .factories import (FeeFixture, category, make_branch, make_class,
                        make_enrolment, make_session)


class MonthlyGenerationTests(FeeFixture, TestCase):
    def setUp(self):
        self.build_fixture()
        # Two more students, so "one invoice each" is a real assertion rather
        # than a count of one.
        self.second = make_enrolment(self.branch, self.session, self.academic_class)
        self.third = make_enrolment(self.branch, self.session, self.academic_class)

    def test_running_twice_writes_one_invoice_per_student(self):
        first = generate_monthly_fees(self.branch, period='2026-03')
        second = generate_monthly_fees(self.branch, period='2026-03')

        self.assertEqual(first['created'], 3)
        self.assertEqual(second['created'], 0)
        self.assertEqual(second['skipped'], 3)

        mon = category(self.branch, 'MON')
        for enrolment in (self.enrolment, self.second, self.third):
            self.assertEqual(
                Fee.objects.filter(student=enrolment.student, category=mon,
                                   period='2026-03', session=self.session).count(),
                1,
            )
        self.assertEqual(Fee.objects.count(), 3)

    def test_the_price_comes_from_the_class_monthly_fee(self):
        """V1 has no FeeStructure (docs/05 §5.4) — the class carries the price."""
        generate_monthly_fees(self.branch, period='2026-03')
        fee = Fee.objects.get(student=self.student)

        self.assertEqual(fee.amount, Decimal('500.00'))
        self.assertEqual(fee.payable, Decimal('500.00'))
        self.assertEqual(fee.paid_amount, Decimal('0.00'))
        self.assertEqual(fee.status, FeeStatus.UNPAID)
        self.assertEqual(fee.generated_by, GeneratedBy.SYSTEM)
        self.assertEqual(fee.period, '2026-03')

    def test_a_different_month_is_a_different_invoice(self):
        """The constraint keys on `period`, or February would block March."""
        generate_monthly_fees(self.branch, period='2026-03')
        generate_monthly_fees(self.branch, period='2026-04')

        periods = set(Fee.objects.filter(student=self.student)
                      .values_list('period', flat=True))
        self.assertEqual(periods, {'2026-03', '2026-04'})

    def test_hostel_and_transport_categories_follow_the_enrolment_flags(self):
        """docs/06 #9 — `applies_to`, read against the enrolment, not the student.

        Priced through the `amounts` override because V1 stores no price for
        these heads (see `monthly_amount()` and the phase report).
        """
        resident = make_enrolment(self.branch, self.session, self.academic_class,
                                  is_hostel=True)
        commuter_with_bus = make_enrolment(self.branch, self.session,
                                           self.academic_class, is_transport=True)

        generate_monthly_fees(
            self.branch, period='2026-03',
            amounts={'HOS': Decimal('800.00'), 'TRN': Decimal('300.00'),
                     'FOD': Decimal('1200.00')},
        )

        def codes_for(enrolment):
            return set(Fee.objects.filter(student=enrolment.student)
                       .values_list('category__code', flat=True))

        self.assertEqual(codes_for(resident), {'MON', 'HOS', 'FOD'})
        self.assertEqual(codes_for(commuter_with_bus), {'MON', 'TRN'})
        # The plain day student gets tuition and nothing else.
        self.assertEqual(codes_for(self.enrolment), {'MON'})

    def test_an_unpriced_category_raises_nothing_rather_than_a_zero_invoice(self):
        """A ৳0 hostel invoice looks paid on every screen — see `monthly_amount()`."""
        make_enrolment(self.branch, self.session, self.academic_class,
                       is_hostel=True)
        result = generate_monthly_fees(self.branch, period='2026-03')

        self.assertFalse(Fee.objects.filter(category__code='HOS').exists())
        self.assertGreater(result['unpriced'], 0)

    def test_only_the_current_session_is_billed(self):
        """Last year's enrolments must not be raised this month's fees."""
        old_session = make_session(self.branch, name='2025', is_current=False)
        old_class = make_class(self.branch, old_session, name='Class 4')
        stale = make_enrolment(self.branch, old_session, old_class)

        generate_monthly_fees(self.branch, period='2026-03')

        self.assertFalse(Fee.objects.filter(student=stale.student).exists())

    def test_generation_across_branches_does_not_cross_institutions(self):
        other = make_branch(code='CTG', name='Chittagong Madrasah')
        other_session = make_session(other)
        other_class = make_class(other, other_session, monthly_fee='700.00')
        other_enrolment = make_enrolment(other, other_session, other_class)

        generate_monthly_fees(period='2026-03')

        self.assertEqual(
            Fee.objects.get(student=other_enrolment.student).amount,
            Decimal('700.00'),
        )
        self.assertEqual(Fee.objects.get(student=self.student).amount,
                         Decimal('500.00'))
        self.assertEqual(Fee.objects.filter(branch=other).count(), 1)


class SeedingTests(TestCase):
    """Branch creation seeds the heads a collection needs (docs/03 §7–§8)."""

    def test_a_new_branch_gets_eleven_fee_categories_and_its_income_heads(self):
        from branches.seeding import seed_branch
        from fees.models import FeeCategory
        from finance.models import ExpenseCategory, IncomeCategory

        branch = make_branch()

        self.assertEqual(FeeCategory.objects.filter(branch=branch).count(), 11)
        self.assertEqual(IncomeCategory.objects.filter(branch=branch).count(), 9)
        self.assertEqual(ExpenseCategory.objects.filter(branch=branch).count(), 13)

        # The link that makes auto-posting work.
        monthly_head = IncomeCategory.objects.get(branch=branch, code='INC-MON')
        self.assertEqual(monthly_head.fee_category.code, 'MON')

        # Idempotent: `fresh_deploy.sh` runs `seed_categories` on every deploy.
        again = seed_branch(branch)
        self.assertEqual(again['fee_categories'], 0)
        self.assertEqual(again['income_categories'], 0)
        self.assertEqual(again['expense_categories'], 0)
        self.assertEqual(FeeCategory.objects.filter(branch=branch).count(), 11)

    def test_reseeding_keeps_the_institutions_own_edits(self):
        """An institution that renamed a head keeps that name across a re-seed."""
        from branches.seeding import seed_branch
        from fees.models import FeeCategory

        branch = make_branch()
        head = FeeCategory.objects.get(branch=branch, code='MON')
        head.name_bn = 'বেতন'
        head.save(update_fields=['name_bn'])

        seed_branch(branch)
        head.refresh_from_db()
        self.assertEqual(head.name_bn, 'বেতন')

    def test_hostel_and_transport_heads_are_seeded_restricted(self):
        branch = make_branch()

        self.assertTrue(category(branch, 'HOS').applies_to['hostel_only'])
        self.assertTrue(category(branch, 'TRN').applies_to['transport_only'])
        self.assertFalse(category(branch, 'MON').applies_to['hostel_only'])
