"""The two automatic events: a student is admitted, and money is taken.

These ride on `admit_student()` and `collect_fee()` rather than on a button, so
the properties that matter are different from the result SMS:

1. **Off by default.** A send on every admission and every receipt is money
   leaving without a decision; the institution opts in per event.
2. **It never breaks what it reports.** A gateway outage, a template that will
   not render, anything — the admission stands and the receipt stands.
3. **The outbox row is inside the same transaction.** An admission that rolls
   back takes its message with it; there is no SMS about a student who does not
   exist.
4. **Three instalments are three receipts**, so the idempotency key is the
   payment and not the invoice.
"""

from decimal import Decimal
from unittest.mock import patch

from django.db import transaction
from django.test import TestCase

from fees.models import Payment
from fees.services import collect_fee
from fees.tests.factories import (FeeFixture, make_fee, make_student)
from notifications.models import NotificationEvent, SmsMessage, SmsStatus
from students.models import Guardian, StudentGuardian


def give_guardian(student, phone='01712000001', name='Father'):
    guardian = Guardian.objects.create(branch=student.branch, name=name,
                                       phone=phone, relation='father')
    StudentGuardian.objects.create(branch=student.branch, student=student,
                                   guardian=guardian, is_primary=True)
    return guardian


class PaymentSmsTests(FeeFixture, TestCase):
    def setUp(self):
        self.build_fixture()
        give_guardian(self.student)
        self.fee = make_fee(self.branch, self.session, student=self.student,
                            amount='1500.00', enrolment=self.enrolment)

    def enable(self):
        self.branch.sms_on_payment = True
        self.branch.save(update_fields=['sms_on_payment'])

    def test_nothing_is_sent_until_the_institution_asks(self):
        """Default off: money must not leave without a decision."""
        collect_fee(fee=self.fee, amount=Decimal('500.00'))

        self.assertFalse(SmsMessage.objects.exists())

    def test_a_receipt_reaches_the_guardian_with_what_is_left(self):
        self.enable()

        payment = collect_fee(fee=self.fee, amount=Decimal('500.00'))

        message = SmsMessage.objects.get()
        self.assertEqual(message.event, NotificationEvent.FEE_RECEIVED)
        self.assertEqual(message.to_phone, '01712000001')
        self.assertEqual(message.status, SmsStatus.QUEUED)
        self.assertIn(payment.receipt_no, message.body)
        # What was paid, and — the reason the message is worth sending — what
        # is still owed on this invoice.
        self.assertIn('৳500', message.body)
        self.assertIn('৳1,000', message.body)
        self.assertEqual(message.parts, 1, message.body)

    def test_three_instalments_are_three_messages(self):
        """The key is the payment, not the invoice."""
        self.enable()

        for _ in range(3):
            collect_fee(fee=self.fee, amount=Decimal('500.00'))

        self.assertEqual(SmsMessage.objects.count(), 3)
        self.assertEqual(
            SmsMessage.objects.values('reference').distinct().count(), 3)

    def test_a_student_with_no_guardian_number_is_recorded_not_lost(self):
        self.enable()
        other = make_student(self.branch, name='No Guardian')
        fee = make_fee(self.branch, self.session, student=other, amount='100.00')

        collect_fee(fee=fee, amount=Decimal('100.00'))

        message = SmsMessage.objects.get(student=other)
        self.assertEqual(message.status, SmsStatus.SKIPPED)
        self.assertEqual(message.skip_reason, 'no_phone')

    def test_a_failing_send_never_costs_the_receipt(self):
        """The money is the money; the SMS is a courtesy about the money."""
        self.enable()

        with patch('notifications.services.queue_sms',
                   side_effect=RuntimeError('gateway on fire')):
            payment = collect_fee(fee=self.fee, amount=Decimal('500.00'))

        self.assertTrue(Payment.objects.filter(pk=payment.pk).exists())
        payment.refresh_from_db()
        # And the income row it writes in the same transaction is still there.
        self.assertIsNotNone(payment.income_id)
        self.assertFalse(SmsMessage.objects.exists())

    def test_the_institution_switch_beats_the_event_switch(self):
        self.enable()
        self.branch.sms_enabled = False
        self.branch.save(update_fields=['sms_enabled'])

        collect_fee(fee=self.fee, amount=Decimal('500.00'))

        self.assertFalse(SmsMessage.objects.exists())


class AdmissionSmsTests(FeeFixture, TestCase):
    """Admission goes through `students.services.admit_student()`, so these
    build an application and admit it the way the screen does."""

    def setUp(self):
        self.build_fixture()

    def admit(self, *, phone='01712000005'):
        from datetime import date

        from students.models import Admission, AdmissionStatus
        from students.services import admit_student

        application = Admission.objects.create(
            branch=self.branch, session=self.session,
            academic_class=self.academic_class, stream=self.academic_class.stream,
            applicant_name='Newly Admitted', applicant_name_bn='নতুন শিক্ষার্থী',
            application_no=f'APP-{date.today().year}-0001',
            status=AdmissionStatus.ACCEPTED,
            guardian_name='Father', guardian_phone=phone,
        )
        return admit_student(application, academic_class=self.academic_class)

    def test_nothing_is_sent_until_the_institution_asks(self):
        self.admit()

        self.assertFalse(SmsMessage.objects.exists())

    def test_the_guardian_gets_the_numbers_they_will_be_asked_for(self):
        self.branch.sms_on_admission = True
        self.branch.save(update_fields=['sms_on_admission'])

        student, enrolment = self.admit()

        message = SmsMessage.objects.get(event=NotificationEvent.ADMISSION)
        self.assertEqual(message.student_id, student.pk)
        self.assertIn(student.student_id, message.body)
        self.assertIn(str(enrolment.roll), message.body)
        self.assertEqual(message.parts, 1, message.body)

    def test_a_failing_send_never_costs_the_admission(self):
        self.branch.sms_on_admission = True
        self.branch.save(update_fields=['sms_on_admission'])

        with patch('notifications.services.queue_sms',
                   side_effect=RuntimeError('gateway on fire')):
            student, enrolment = self.admit()

        self.assertIsNotNone(student.pk)
        self.assertIsNotNone(enrolment.pk)
        self.assertFalse(SmsMessage.objects.exists())

    def test_an_admission_that_rolls_back_takes_its_message_with_it(self):
        """The outbox row is written inside the admission's own transaction."""
        self.branch.sms_on_admission = True
        self.branch.save(update_fields=['sms_on_admission'])

        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.admit()
                raise RuntimeError('something later in the request failed')

        self.assertFalse(SmsMessage.objects.exists())
