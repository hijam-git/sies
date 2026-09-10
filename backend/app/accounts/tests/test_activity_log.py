"""ActivityLog is append-only, and its feed is scoped.

A tamper-proof trail is the entire value of this table: if the person who
deleted a payment can also edit the line that says so, the line proves nothing
(docs/08 D8).
"""

from unittest import mock

from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.test import TestCase
from django.urls import reverse

from accounts.models import ActivityAction, ActivityLog
from accounts.services import log_activity

from .factories import (make_activity, make_branch, make_platform_admin,
                        make_role, make_user)

PASSWORD = 'correct-horse-9'


class AppendOnlyTests(TestCase):
    def setUp(self):
        self.branch = make_branch()
        self.entry = make_activity(branch=self.branch, summary='Something happened')

    def test_an_existing_entry_cannot_be_changed(self):
        self.entry.summary = 'Nothing happened, honest'
        with self.assertRaises(ValidationError):
            self.entry.save()

        self.entry.refresh_from_db()
        self.assertEqual(self.entry.summary, 'Something happened')

    def test_an_entry_cannot_be_deleted(self):
        with self.assertRaises(ValidationError):
            self.entry.delete()
        self.assertTrue(ActivityLog.objects.filter(pk=self.entry.pk).exists())

    def test_the_api_offers_no_write_at_all(self):
        admin = make_platform_admin()
        self.client.force_login(admin)

        detail = reverse('accounts:activity-detail', args=[self.entry.pk])

        # 403 rather than 405: DRF runs permission checks before it works out
        # that the method has no handler, and `activity` has only a `view`
        # action in the catalogue, so a write asks for a permission that cannot
        # exist. Either answer is a refusal; asserting both means this test
        # keeps proving "no write gets through" if DRF ever reorders the two.
        self.assertIn(self.client.delete(detail).status_code, (403, 405))
        self.assertIn(
            self.client.patch(detail, {'summary': 'x'},
                              content_type='application/json').status_code,
            (403, 405),
        )
        self.assertIn(
            self.client.post(reverse('accounts:activity-list'), {},
                             content_type='application/json').status_code,
            (403, 405),
        )


class LogActivityTests(TestCase):
    def setUp(self):
        self.branch = make_branch()
        self.user = make_user(branch=self.branch, name='Karim')

    def test_it_records_who_what_and_where(self):
        entry = log_activity(
            action=ActivityAction.COLLECT,
            user=self.user,
            branch=self.branch,
            model='Payment',
            object_id=17,
            object_label='RCP-DHK-0001',
            summary='Collected 500 taka',
            summary_bn='৫০০ টাকা আদায় করা হয়েছে',
        )

        self.assertEqual(entry.user, self.user)
        self.assertEqual(entry.branch, self.branch)
        self.assertEqual(entry.object_id, '17')
        self.assertIn('Karim', entry.user_label)
        self.assertTrue(entry.summary_bn)

    def test_a_non_atomic_failure_does_not_reach_the_caller(self):
        """A broken audit table must never take a login down with it.

        The failure is injected rather than provoked with bad data, because what
        is being tested is the swallow, not any particular way of breaking the
        insert — and the realistic causes (a full disk, a lock timeout) cannot be
        produced from a test.
        """
        with mock.patch.object(ActivityLog, 'save',
                               side_effect=DatabaseError('disk full')):
            entry = log_activity(action=ActivityAction.LOGIN, user=self.user,
                                 atomic=False)
        self.assertIsNone(entry)

    def test_an_atomic_failure_does_reach_the_caller(self):
        """For money, the operation and its record stand or fall together."""
        with mock.patch.object(ActivityLog, 'save',
                               side_effect=DatabaseError('disk full')):
            with self.assertRaises(DatabaseError):
                log_activity(action=ActivityAction.COLLECT, user=self.user,
                             atomic=True)

    def test_an_anonymous_actor_is_stored_as_no_user(self):
        from django.contrib.auth.models import AnonymousUser

        entry = log_activity(action=ActivityAction.LOGIN_FAILED,
                             user=AnonymousUser(), user_label='01799999999')
        self.assertIsNone(entry.user)
        self.assertEqual(entry.user_label, '01799999999')


class ActivityFeedTests(TestCase):
    """`GET /api/activity/?since=` — docs/08 D8's cursor feed."""

    def setUp(self):
        self.branch_a = make_branch(name='Dhaka', code='DHK')
        self.branch_b = make_branch(name='Chittagong', code='CTG')

        self.admin = make_platform_admin()
        self.principal = make_user(
            branch=self.branch_a, user_type='principal',
            role=make_role('Principal-with-activity',
                           matrix={'activity': ['view']}),
        )

        self.a1 = make_activity(branch=self.branch_a, summary='A one')
        self.b1 = make_activity(branch=self.branch_b, summary='B one')
        self.platform = make_activity(branch=None, summary='Platform event')

    def get(self, user, query=''):
        self.client.force_login(user)
        return self.client.get(reverse('accounts:activity-list') + query)

    def test_a_platform_admin_sees_every_institution_and_the_platform_rows(self):
        body = self.get(self.admin).json()
        summaries = {item['summary'] for item in body['items']}
        self.assertEqual(summaries, {'A one', 'B one', 'Platform event'})

    def test_a_principal_sees_only_their_own_institution(self):
        body = self.get(self.principal).json()
        summaries = {item['summary'] for item in body['items']}
        self.assertEqual(summaries, {'A one'})

    def test_last_id_is_the_newest_row_so_the_cursor_moves_forward(self):
        body = self.get(self.admin).json()
        self.assertEqual(body['last_id'], self.platform.id)

        later = make_activity(branch=self.branch_a, summary='A two')
        follow = self.get(self.admin, f'?since={body["last_id"]}').json()

        self.assertEqual([item['summary'] for item in follow['items']], ['A two'])
        self.assertEqual(follow['last_id'], later.id)

    def test_an_empty_poll_keeps_the_cursor_where_it_was(self):
        body = self.get(self.admin).json()
        follow = self.get(self.admin, f'?since={body["last_id"]}').json()
        self.assertEqual(follow['items'], [])
        self.assertEqual(follow['last_id'], body['last_id'])

    def test_a_junk_cursor_starts_from_the_top_rather_than_failing(self):
        response = self.get(self.admin, '?since=tomorrow')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['items'])

    def test_the_action_filter(self):
        make_activity(branch=self.branch_a, action=ActivityAction.LOGIN,
                      summary='Signed in')
        body = self.get(self.admin, '?action=login').json()
        self.assertEqual([item['summary'] for item in body['items']], ['Signed in'])

    def test_a_user_without_activity_view_is_refused(self):
        nobody = make_user(branch=self.branch_a, role=make_role('Teacher'))
        response = self.get(nobody)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['code'], 'permission_denied')
