"""Who may send, and who may read what was sent (CLAUDE.md §5).

The send is the interesting one. It costs **`exams.publish`** — the principal's
permission — because releasing a result to a handset is the same decision as
releasing it to a screen, and a teacher who may enter marks may not make it.
Everything else here is the ordinary rule: another institution's rows are 404,
never 403.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from exams.services import publish_exam, save_marks
from exams.tests import factories as f
from notifications.models import (NotificationChannel, NotificationEvent,
                                  NotificationTemplate, SmsMessage)
from notifications.tests.test_result_sms import add_guardian


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


class SendApiTests(TestCase):
    def setUp(self):
        self.world = f.small_world()
        w = self.world
        for subject in (w['arabic'], w['fiqh']):
            save_marks(exam=w['exam'], subject=subject, actor=w['principal'],
                       rows=[{'enrolment': e.pk, 'obtained': '75'} for e in w['enrolments']])
        publish_exam(w['exam'], actor=w['principal'])
        add_guardian(w['students'][0], name='Father One', phone='01712000001')
        self.exam = w['exam']

    def test_the_principal_sends_and_gets_the_count_back(self):
        response = client_for(self.world['principal']).post(
            f'/api/exams/{self.exam.pk}/send-results-sms/', {}, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['queued'], 1)
        self.assertEqual(response.data['missing_phone'], 1)
        self.assertEqual(SmsMessage.objects.filter(status='queued').count(), 1)

    def test_a_teacher_who_may_enter_marks_may_not_send_results(self):
        """The gate that matters: `marks.enter` is not a licence to text four
        hundred guardians."""
        teacher = f.make_user(self.world['branch'], phone='01711000042',
                              user_type='teacher',
                              permissions=['marks.view', 'marks.enter', 'exams.view'])

        response = client_for(teacher).post(
            f'/api/exams/{self.exam.pk}/send-results-sms/', {}, format='json')

        self.assertEqual(response.status_code, 403)
        self.assertFalse(SmsMessage.objects.exists())

    def test_another_institutions_exam_is_404(self):
        other = f.small_world(code='CTG', phone='01722000001')

        response = client_for(other['principal']).post(
            f'/api/exams/{self.exam.pk}/send-results-sms/', {}, format='json')

        self.assertEqual(response.status_code, 404)
        self.assertFalse(SmsMessage.objects.exists())

    def test_an_unpublished_exam_is_a_400_not_a_500(self):
        from exams.services import unpublish_exam

        unpublish_exam(self.exam, actor=self.world['principal'])

        response = client_for(self.world['principal']).post(
            f'/api/exams/{self.exam.pk}/send-results-sms/', {}, format='json')

        self.assertEqual(response.status_code, 400)

    def test_the_preview_sends_nothing(self):
        response = client_for(self.world['principal']).get(
            f'/api/exams/{self.exam.pk}/results-sms/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['recipients'], 1)
        self.assertEqual(len(response.data['missing_phone']), 1)
        self.assertFalse(SmsMessage.objects.exists())


class OutboxApiTests(TestCase):
    def setUp(self):
        self.world = f.small_world()
        self.other = f.small_world(code='CTG', phone='01722000001')
        self.mine = SmsMessage.objects.create(
            branch=self.world['branch'], event=NotificationEvent.RESULT_PUBLISHED,
            to_phone='01712000001', body='mine', status='sent',
        )
        self.theirs = SmsMessage.objects.create(
            branch=self.other['branch'], event=NotificationEvent.RESULT_PUBLISHED,
            to_phone='01712000002', body='theirs', status='sent',
        )

    def test_the_outbox_holds_only_this_institutions_messages(self):
        response = client_for(self.world['principal']).get('/api/sms/')

        self.assertEqual([row['id'] for row in response.data['results']], [self.mine.pk])

    def test_another_institutions_message_is_404_not_403(self):
        response = client_for(self.world['principal']).get(f'/api/sms/{self.theirs.pk}/')

        self.assertEqual(response.status_code, 404)

    def test_the_outbox_cannot_be_edited_through_the_api(self):
        """It is the record that answers a guardian who says nothing arrived."""
        response = client_for(self.world['principal']).patch(
            f'/api/sms/{self.mine.pk}/', {'status': 'failed'}, format='json')

        self.assertEqual(response.status_code, 405)


class TemplateApiTests(TestCase):
    def setUp(self):
        self.world = f.small_world()

    def test_an_institution_writes_its_own_wording(self):
        response = client_for(self.world['principal']).post(
            '/api/message-templates/',
            {'event': NotificationEvent.RESULT_PUBLISHED,
             'channel': NotificationChannel.SMS, 'language': 'bn',
             'body': '{student} — {exam}: {grade}'},
            format='json')

        self.assertEqual(response.status_code, 201)
        template = NotificationTemplate.objects.get()
        self.assertEqual(template.branch, self.world['branch'])
        # The cost of what they just wrote, so the screen can say "1 SMS".
        self.assertEqual(response.data['cost']['parts'], 1)

    def test_an_empty_body_is_refused(self):
        response = client_for(self.world['principal']).post(
            '/api/message-templates/',
            {'event': NotificationEvent.RESULT_PUBLISHED, 'language': 'bn', 'body': '  '},
            format='json')

        self.assertEqual(response.status_code, 400)

    def test_the_placeholders_come_from_the_renderer_not_from_a_list_on_a_screen(self):
        response = client_for(self.world['principal']).get(
            '/api/message-templates/placeholders/')

        self.assertEqual(response.status_code, 200)
        names = [p['name'] for p in
                 response.data['placeholders'][NotificationEvent.RESULT_PUBLISHED]]
        self.assertIn('student', names)
        self.assertIn('grade', names)

    def test_an_accountant_may_not_rewrite_what_guardians_are_told(self):
        accountant = f.make_user(self.world['branch'], phone='01711000043',
                                 user_type='accountant',
                                 permissions=['fees.view', 'fees.collect'])

        response = client_for(accountant).post(
            '/api/message-templates/',
            {'event': NotificationEvent.RESULT_PUBLISHED, 'language': 'bn', 'body': 'x'},
            format='json')

        self.assertEqual(response.status_code, 403)
