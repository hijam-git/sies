"""Where an invoice's price comes from, and in which order.

A head priced on Fees → Fee setup has to raise an invoice for that amount.
`FeeCategory.default_amount` was served by the API and editable on that screen
long before anything read it, so an accountant could set ৳500 against Transport
Fee and watch the monthly job skip it as unpriced — silently, because from the
job's point of view nothing was wrong.

The order is: what the caller passed for this run, then the class's own monthly
tuition (general heads only), then the head's standing price. Nothing priced
raises nothing — never a ৳0 invoice, which looks paid on every screen.
"""

from decimal import Decimal

from django.test import TestCase

from fees.models import Fee, FeeCategory, Recurrence
from fees.services import generate_monthly_fees, raise_admission_fees

from .factories import FeeFixture, category, make_enrolment


def price(branch, code, amount):
    head = category(branch, code)
    head.default_amount = Decimal(amount)
    head.save(update_fields=['default_amount'])
    return head


class MonthlyPriceSourceTests(FeeFixture, TestCase):
    def setUp(self):
        self.build_fixture()

    def test_a_restricted_head_is_raised_from_its_own_price(self):
        """The bug this file exists for: Transport Fee priced on the screen."""
        price(self.branch, 'TRN', '300.00')
        commuter = make_enrolment(self.branch, self.session, self.academic_class,
                                  is_transport=True)

        generate_monthly_fees(self.branch, period='2026-03')

        fee = Fee.objects.get(student=commuter.student, category__code='TRN')
        self.assertEqual(fee.amount, Decimal('300.00'))

    def test_the_class_tuition_still_wins_for_a_general_head(self):
        """`monthly_fee` is the per-class price and stays more specific."""
        price(self.branch, 'MON', '999.00')

        generate_monthly_fees(self.branch, period='2026-03')

        fee = Fee.objects.get(student=self.enrolment.student, category__code='MON')
        self.assertEqual(fee.amount, self.academic_class.monthly_fee)

    def test_a_general_head_falls_back_to_its_own_price(self):
        """A class with no tuition set: the head's price is the only one left."""
        self.academic_class.monthly_fee = None
        self.academic_class.save(update_fields=['monthly_fee'])
        price(self.branch, 'MON', '750.00')

        generate_monthly_fees(self.branch, period='2026-03')

        fee = Fee.objects.get(student=self.enrolment.student, category__code='MON')
        self.assertEqual(fee.amount, Decimal('750.00'))

    def test_the_runs_own_figure_beats_both(self):
        price(self.branch, 'TRN', '300.00')
        commuter = make_enrolment(self.branch, self.session, self.academic_class,
                                  is_transport=True)

        generate_monthly_fees(self.branch, period='2026-03',
                              amounts={'TRN': Decimal('450.00')})

        fee = Fee.objects.get(student=commuter.student, category__code='TRN')
        self.assertEqual(fee.amount, Decimal('450.00'))

    def test_a_head_priced_nowhere_still_raises_nothing(self):
        """The ৳0 invoice this whole rule exists to avoid."""
        make_enrolment(self.branch, self.session, self.academic_class, is_hostel=True)

        result = generate_monthly_fees(self.branch, period='2026-03')

        self.assertFalse(Fee.objects.filter(category__code='HOS').exists())
        self.assertGreater(result['unpriced'], 0)


class AdmissionPriceSourceTests(FeeFixture, TestCase):
    def setUp(self):
        self.build_fixture()

    def test_admission_and_session_fees_come_from_the_heads_own_price(self):
        price(self.branch, 'ADM', '1500.00')
        price(self.branch, 'SES', '1000.00')
        enrolment = make_enrolment(self.branch, self.session, self.academic_class)

        raised = raise_admission_fees(enrolment=enrolment)

        self.assertEqual(
            {f.category.code: f.amount for f in raised},
            {'ADM': Decimal('1500.00'), 'SES': Decimal('1000.00')},
        )

    def test_this_admissions_own_figure_wins(self):
        price(self.branch, 'ADM', '1500.00')
        enrolment = make_enrolment(self.branch, self.session, self.academic_class)

        raised = raise_admission_fees(enrolment=enrolment,
                                      amounts={'ADM': Decimal('500.00')})

        admission = next(f for f in raised if f.category.code == 'ADM')
        self.assertEqual(admission.amount, Decimal('500.00'))

    def test_an_unpriced_head_raises_nothing(self):
        enrolment = make_enrolment(self.branch, self.session, self.academic_class)

        self.assertEqual(raise_admission_fees(enrolment=enrolment), [])
        self.assertFalse(Fee.objects.filter(category__code__in=('ADM', 'SES')).exists())

    def test_a_stand_in_enrolment_raises_nothing_rather_than_failing(self):
        """`admit_student()`'s own tests substitute the enrolment service."""
        from types import SimpleNamespace

        stand_in = SimpleNamespace(pk=1, student=None, session=self.session)
        self.assertEqual(raise_admission_fees(enrolment=stand_in), [])


class SecondMonthlyHeadTests(FeeFixture, TestCase):
    """The class tuition prices the tuition, and only the tuition.

    "General head" used to mean "not hostel and not transport", so an
    institution that added a second monthly head — Electricity at ৳200, priced
    on Fees → Fee setup — had every student billed the class's ৳500 tuition for
    it instead, every month, with nothing on any screen to say so.
    """

    def setUp(self):
        self.build_fixture()
        self.electricity = FeeCategory.objects.create(
            branch=self.branch, code='ELC', name='Electricity', name_bn='বিদ্যুৎ বিল',
            recurrence=Recurrence.MONTHLY, default_amount=Decimal('200.00'),
        )

    def test_a_second_monthly_head_is_priced_from_its_own_figure(self):
        generate_monthly_fees(self.branch, period='2026-03')

        fee = Fee.objects.get(student=self.enrolment.student, category=self.electricity)
        self.assertEqual(fee.amount, Decimal('200.00'))

    def test_the_tuition_head_still_takes_the_class_price(self):
        generate_monthly_fees(self.branch, period='2026-03')

        fee = Fee.objects.get(student=self.enrolment.student, category__code='MON')
        self.assertEqual(fee.amount, self.academic_class.monthly_fee)


class CancelledInvoiceTests(FeeFixture, TestCase):
    """A month cancelled by mistake has to be raisable again.

    The pre-check and the unique constraint both counted cancelled rows, so
    `generate_monthly_fees` skipped that (student, category, period) for good —
    a soft delete that quietly took the month with it.
    """

    def setUp(self):
        self.build_fixture()

    def test_a_cancelled_invoice_does_not_block_the_month(self):
        generate_monthly_fees(self.branch, period='2026-03')
        fee = Fee.objects.get(student=self.enrolment.student, category__code='MON')
        fee.is_active = False
        fee.save(update_fields=['is_active'])

        generate_monthly_fees(self.branch, period='2026-03')

        live = Fee.objects.filter(student=self.enrolment.student,
                                  category__code='MON', is_active=True)
        self.assertEqual(live.count(), 1)
        self.assertNotEqual(live.first().pk, fee.pk)
        # The cancelled row is still there: it is the record of the cancellation.
        self.assertTrue(Fee.objects.filter(pk=fee.pk, is_active=False).exists())

    def test_a_live_invoice_still_blocks_a_second_one(self):
        generate_monthly_fees(self.branch, period='2026-03')
        generate_monthly_fees(self.branch, period='2026-03')

        self.assertEqual(
            Fee.objects.filter(student=self.enrolment.student,
                               category__code='MON').count(),
            1,
        )
