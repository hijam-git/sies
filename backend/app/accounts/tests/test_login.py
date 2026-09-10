"""Login, and the error codes it must emit.

The codes are a contract with the SPA (docs/WORKLOG F15): `lib/apiErrors.ts`
switches on them to pick a Bangla sentence, so a wrong code is a screen showing
"Could not sign in" when it knows perfectly well that the account was switched
off. Asserting the code, not the message, is the point of these tests.
"""

from django.test import TestCase
from django.urls import reverse

from accounts.models import ActivityAction, ActivityLog

from .factories import make_branch, make_user

PASSWORD = 'correct-horse-9'


class LoginTests(TestCase):
    def setUp(self):
        self.branch = make_branch()
        self.url = reverse('accounts:login')
        self.user = make_user(branch=self.branch, phone='01712345678',
                              password=PASSWORD, name='Rahim Uddin')

    def post(self, **body):
        return self.client.post(self.url, body, content_type='application/json')

    # ── Success ──────────────────────────────────────────────────────────────

    def test_success_returns_tokens_and_the_effective_permissions(self):
        response = self.post(phone='01712345678', password=PASSWORD)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['access'])
        self.assertTrue(body['refresh'])
        self.assertEqual(body['user']['phone'], '01712345678')
        # Effective, not the raw column: a user on their role's preset must not
        # be told they have no permissions.
        self.assertIn('permissions', body['user'])

    def test_any_written_form_of_the_number_signs_in(self):
        for raw in ['+8801712345678', '8801712345678', '01712-345678']:
            with self.subTest(raw=raw):
                self.assertEqual(self.post(phone=raw, password=PASSWORD).status_code, 200)

    def test_success_writes_a_login_entry(self):
        self.post(phone='01712345678', password=PASSWORD)
        entry = ActivityLog.objects.filter(action=ActivityAction.LOGIN).get()
        self.assertEqual(entry.user, self.user)
        self.assertEqual(entry.branch, self.branch)

    # ── Failure, each with its own code ──────────────────────────────────────

    def test_wrong_password_is_invalid_credentials(self):
        response = self.post(phone='01712345678', password='wrong')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['code'], 'invalid_credentials')

    def test_an_unknown_number_is_also_invalid_credentials(self):
        # Deliberately the same answer as a wrong password. Telling a stranger
        # that the phone exists is telling them half the answer.
        response = self.post(phone='01799999999', password=PASSWORD)
        self.assertEqual(response.json()['code'], 'invalid_credentials')

    def test_a_badly_formatted_number_is_invalid_phone(self):
        for raw in ['0171234567', '01212345678', 'hello']:
            with self.subTest(raw=raw):
                response = self.post(phone=raw, password=PASSWORD)
                self.assertEqual(response.json()['code'], 'invalid_phone')

    def test_a_switched_off_account_is_account_inactive(self):
        self.user.is_active = False
        self.user.save()

        response = self.post(phone='01712345678', password=PASSWORD)
        self.assertEqual(response.status_code, 403)
        # Not invalid_credentials: the password was right, and telling the person
        # to check it would send them round in circles.
        self.assertEqual(response.json()['code'], 'account_inactive')

    def test_every_failure_writes_a_login_failed_entry_naming_the_number(self):
        self.post(phone='01712345678', password='wrong')
        self.post(phone='01799999999', password=PASSWORD)
        self.post(phone='nonsense', password=PASSWORD)

        entries = ActivityLog.objects.filter(action=ActivityAction.LOGIN_FAILED)
        self.assertEqual(entries.count(), 3)
        self.assertTrue(all(e.user is None for e in entries))
        self.assertIn('01799999999', [e.user_label for e in entries])

    def test_a_failed_login_never_records_the_password(self):
        self.post(phone='01712345678', password='hunter2')
        entry = ActivityLog.objects.filter(action=ActivityAction.LOGIN_FAILED).get()
        self.assertNotIn('hunter2', str(entry.after))
        self.assertNotIn('hunter2', entry.user_label)


class SessionEndpointTests(TestCase):
    def setUp(self):
        self.branch = make_branch()
        self.user = make_user(branch=self.branch, password=PASSWORD)
        response = self.client.post(
            reverse('accounts:login'),
            {'phone': self.user.phone, 'password': PASSWORD},
            content_type='application/json',
        )
        self.tokens = response.json()

    def auth(self):
        return {'HTTP_AUTHORIZATION': f'Bearer {self.tokens["access"]}'}

    def test_me_returns_the_caller(self):
        response = self.client.get(reverse('accounts:me'), **self.auth())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['id'], self.user.id)

    def test_me_requires_a_token(self):
        self.assertEqual(self.client.get(reverse('accounts:me')).status_code, 401)

    def test_refresh_issues_a_new_access_token(self):
        response = self.client.post(
            reverse('accounts:refresh'),
            {'refresh': self.tokens['refresh']},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['access'])

    def test_refresh_rejects_rubbish_in_this_project_s_error_shape(self):
        response = self.client.post(
            reverse('accounts:refresh'),
            {'refresh': 'not-a-token'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn('code', response.json())

    def test_logout_blacklists_the_refresh_token(self):
        logout = self.client.post(
            reverse('accounts:logout'),
            {'refresh': self.tokens['refresh']},
            content_type='application/json',
            **self.auth(),
        )
        self.assertEqual(logout.status_code, 200)

        reused = self.client.post(
            reverse('accounts:refresh'),
            {'refresh': self.tokens['refresh']},
            content_type='application/json',
        )
        self.assertEqual(reused.status_code, 401)

    def test_change_password_clears_the_forced_change_flag(self):
        self.user.must_change_password = True
        self.user.save()

        response = self.client.post(
            reverse('accounts:change-password'),
            {'current_password': PASSWORD, 'new_password': 'another-good-one-42'},
            content_type='application/json',
            **self.auth(),
        )
        self.assertEqual(response.status_code, 200)

        self.user.refresh_from_db()
        self.assertFalse(self.user.must_change_password)
        self.assertTrue(self.user.check_password('another-good-one-42'))

    def test_change_password_refuses_a_wrong_current_password(self):
        response = self.client.post(
            reverse('accounts:change-password'),
            {'current_password': 'wrong', 'new_password': 'another-good-one-42'},
            content_type='application/json',
            **self.auth(),
        )
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))
