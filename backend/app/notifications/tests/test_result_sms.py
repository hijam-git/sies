"""Sending an exam's results to the guardians (docs/02 §4.9).

The properties that matter, in the order they matter:

1. **It goes to the right number.** The primary guardian, then any guardian,
   then the student's own phone — never whichever row came back first.
2. **Pressing send twice sends once.** Results day is a room of people watching;
   somebody will press it twice.
3. **A student with no number is a name on a list**, not a silent nothing.
4. **An unpublished exam refuses.** A screen can be corrected; a handset cannot.
"""

from django.test import TestCase, override_settings

from exams.services import publish_exam, save_marks
from exams.tests import factories as f
from notifications.models import SkipReason, SmsMessage, SmsStatus
from notifications.services import (preview_result_sms, recipient_for,
                                    result_reference, send_result_sms)
from students.models import Guardian, StudentGuardian


def add_guardian(student, *, name, phone, relation='father', primary=True):
    guardian = Guardian.objects.create(
        branch=student.branch, name=name, phone=phone, relation=relation,
    )
    StudentGuardian.objects.create(
        branch=student.branch, student=student, guardian=guardian, is_primary=primary,
    )
    return guardian


class PublishedWorld(TestCase):
    """One exam, two students, marks entered and results published."""

    def setUp(self):
        self.world = f.small_world()
        w = self.world
        for subject in (w['arabic'], w['fiqh']):
            save_marks(exam=w['exam'], subject=subject, actor=w['principal'],
                       rows=[{'enrolment': e.pk, 'obtained': '80'} for e in w['enrolments']])
        publish_exam(w['exam'], actor=w['principal'])
        self.exam = w['exam']
        self.students = w['students']


class RecipientTests(PublishedWorld):
    def test_the_primary_guardian_gets_it(self):
        add_guardian(self.students[0], name='Local Uncle', phone='01712000002',
                     relation='other', primary=False)
        add_guardian(self.students[0], name='Father', phone='01712000001',
                     relation='father', primary=True)

        phone, label = recipient_for(self.students[0])

        self.assertEqual(phone, '01712000001')
        self.assertIn('Father', label)

    def test_a_non_primary_guardian_is_better_than_nobody(self):
        add_guardian(self.students[0], name='Local Uncle', phone='01712000002',
                     relation='other', primary=False)

        phone, _label = recipient_for(self.students[0])

        self.assertEqual(phone, '01712000002')

    def test_the_students_own_phone_is_the_last_resort(self):
        """docs/08 D4 gives students a phone login, so an older student often
        has a number and no guardian on file."""
        student = self.students[0]
        student.phone = '01712000009'
        student.save(update_fields=['phone'])

        phone, label = recipient_for(student)

        self.assertEqual(phone, '01712000009')
        self.assertEqual(label, student.name_bn or student.name)

    def test_a_guardian_phone_is_normalised_on_the_way_out(self):
        add_guardian(self.students[0], name='Father', phone='+8801712000001')

        phone, _label = recipient_for(self.students[0])

        self.assertEqual(phone, '01712000001')


class SendTests(PublishedWorld):
    def setUp(self):
        super().setUp()
        add_guardian(self.students[0], name='Father One', phone='01712000001')
        add_guardian(self.students[1], name='Father Two', phone='01712000002')

    def test_every_guardian_gets_one_message(self):
        summary = send_result_sms(self.exam, actor=self.world['principal'])

        self.assertEqual(summary['queued'], 2)
        self.assertEqual(
            sorted(SmsMessage.objects.values_list('to_phone', flat=True)),
            ['01712000001', '01712000002'],
        )

    def test_the_body_carries_this_students_own_result(self):
        send_result_sms(self.exam, actor=self.world['principal'])

        message = SmsMessage.objects.get(to_phone='01712000001')
        from exams.models import Result

        result = Result.objects.get(exam=self.exam, student=self.students[0])
        self.assertIn(self.students[0].name, message.body)
        self.assertIn(self.exam.name, message.body)
        # The Bengali grade, because the body is the Bengali template: a
        # guardian reading এ+ must not be sent A+ by a screen that forgot.
        self.assertIn(result.grade_bn or result.grade, message.body)
        self.assertIn('উত্তীর্ণ', message.body)
        self.assertEqual(message.parts, 1)

    def test_pressing_send_twice_sends_once(self):
        """The room is watching and somebody will press it twice."""
        send_result_sms(self.exam, actor=self.world['principal'])
        summary = send_result_sms(self.exam, actor=self.world['principal'])

        self.assertEqual(summary['queued'], 0)
        self.assertEqual(summary['already_sent'], 2)
        self.assertEqual(
            SmsMessage.objects.filter(status=SmsStatus.QUEUED).count(), 2)

    def test_a_student_with_no_number_is_reported_not_dropped(self):
        StudentGuardian.objects.filter(student=self.students[1]).delete()

        summary = send_result_sms(self.exam, actor=self.world['principal'])

        self.assertEqual(summary['queued'], 1)
        self.assertEqual(summary['missing_phone'], 1)
        skipped = SmsMessage.objects.get(status=SmsStatus.SKIPPED)
        self.assertEqual(skipped.skip_reason, SkipReason.NO_PHONE)
        self.assertEqual(skipped.student_id, self.students[1].pk)

    def test_the_missing_number_can_be_sent_once_the_office_fixes_it(self):
        """A SKIPPED row must not block the send that follows the fix — which is
        why the unique constraint covers only queued and sent."""
        StudentGuardian.objects.filter(student=self.students[1]).delete()
        send_result_sms(self.exam, actor=self.world['principal'])

        add_guardian(self.students[1], name='Found Him', phone='01712000003')
        summary = send_result_sms(self.exam, actor=self.world['principal'])

        self.assertEqual(summary['queued'], 1)
        self.assertTrue(SmsMessage.objects.filter(to_phone='01712000003',
                                                  status=SmsStatus.QUEUED).exists())

    def test_an_institution_with_sms_switched_off_sends_nothing(self):
        branch = self.exam.branch
        branch.sms_enabled = False
        branch.save(update_fields=['sms_enabled'])

        summary = send_result_sms(self.exam, actor=self.world['principal'])

        self.assertEqual(summary['queued'], 0)
        self.assertEqual(
            set(SmsMessage.objects.values_list('skip_reason', flat=True)),
            {SkipReason.SMS_OFF},
        )

    def test_an_unpublished_exam_refuses(self):
        from exams.services import unpublish_exam

        unpublish_exam(self.exam, actor=self.world['principal'])

        with self.assertRaises(ValueError):
            send_result_sms(self.exam, actor=self.world['principal'])
        self.assertFalse(SmsMessage.objects.exists())

    def test_one_class_at_a_time(self):
        """Results come in class by class, so the send does too."""
        other_class = f.make_class(self.world['branch'], self.world['session'],
                                   name='Class 9')

        summary = send_result_sms(self.exam, academic_class=other_class,
                                  actor=self.world['principal'])

        self.assertEqual(summary['queued'], 0)

    def test_the_reference_ties_the_message_to_the_exam(self):
        send_result_sms(self.exam, actor=self.world['principal'])

        self.assertEqual(
            set(SmsMessage.objects.values_list('reference', flat=True)),
            {result_reference(self.exam)},
        )


class PreviewTests(PublishedWorld):
    def setUp(self):
        super().setUp()
        add_guardian(self.students[0], name='Father One', phone='01712000001')

    def test_the_preview_costs_the_send_before_it_happens(self):
        preview = preview_result_sms(self.exam)

        self.assertEqual(preview['recipients'], 1)
        self.assertEqual(preview['parts_total'], 1)
        self.assertEqual([m['name'] for m in preview['missing_phone']],
                         [self.students[1].name_bn or self.students[1].name])
        self.assertIn(self.exam.name, preview['sample'])
        self.assertFalse(SmsMessage.objects.exists())

    def test_the_preview_counts_what_has_already_gone(self):
        send_result_sms(self.exam, actor=self.world['principal'])

        preview = preview_result_sms(self.exam)

        self.assertEqual(preview['recipients'], 0)
        self.assertEqual(preview['already_sent'], 1)


@override_settings(SMS_PROVIDER='console')
class DeliveryTests(PublishedWorld):
    """The worker's half: the row records what the gateway said."""

    def setUp(self):
        super().setUp()
        add_guardian(self.students[0], name='Father One', phone='01712000001')
        add_guardian(self.students[1], name='Father Two', phone='01712000002')

    def test_delivery_marks_the_row_sent_and_keeps_the_providers_answer(self):
        from notifications.services import deliver

        send_result_sms(self.exam, actor=self.world['principal'])
        message = SmsMessage.objects.filter(status=SmsStatus.QUEUED).first()

        self.assertTrue(deliver(message))

        message.refresh_from_db()
        self.assertEqual(message.status, SmsStatus.SENT)
        self.assertEqual(message.provider, 'console')
        self.assertEqual(message.attempts, 1)
        self.assertIsNotNone(message.sent_at)

    def test_a_refusing_gateway_leaves_the_row_failed_and_says_why(self):
        from unittest.mock import patch

        from notifications.gateways.base import SmsResult
        from notifications.services import deliver

        send_result_sms(self.exam, actor=self.world['principal'])
        message = SmsMessage.objects.filter(status=SmsStatus.QUEUED).first()

        with patch('notifications.gateways.console.ConsoleGateway.send',
                   return_value=SmsResult(False, code='1007',
                                          message='Balance Insufficient')):
            self.assertFalse(deliver(message))

        message.refresh_from_db()
        self.assertEqual(message.status, SmsStatus.FAILED)
        self.assertEqual(message.provider_code, '1007')
        self.assertEqual(message.provider_message, 'Balance Insufficient')

    def test_the_branchs_sender_id_is_what_the_handset_shows(self):
        from unittest.mock import patch

        from notifications.services import deliver

        branch = self.exam.branch
        branch.sms_sender_id = 'DHAKAMAD'
        branch.save(update_fields=['sms_sender_id'])
        send_result_sms(self.exam, actor=self.world['principal'])
        message = SmsMessage.objects.filter(status=SmsStatus.QUEUED).first()

        with patch('notifications.gateways.console.ConsoleGateway.send') as send:
            send.return_value.success = True
            send.return_value.code = 'console'
            send.return_value.message = ''
            deliver(message)

        self.assertEqual(send.call_args.kwargs['sender_id'], 'DHAKAMAD')
