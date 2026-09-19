"""API behaviour: who may see what, and who may change it.

The two negatives here are the ones CLAUDE.md §8 requires of every module:
**a branch-A user asking for a branch-B row gets 404, not 403** — 403 confirms
the row exists, which is exactly what a probe wants — and a branch user cannot
write to the Branch table at all.

Every test that turns on *permission* runs with a resolver granting everything
(`factories.all_permissions`), so a refusal proves the branch check refused it
and not that the account happened to lack a permission string.
"""

import unittest

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from branches.models import Branch

from .factories import (
    USER_HAS_BRANCH,
    all_permissions,
    make_branch,
    make_branch_user,
    make_platform_admin,
    make_session,
)

needs_user_branch = unittest.skipUnless(
    USER_HAS_BRANCH,
    'The user model has no `branch` column until the accounts app lands, so '
    'every account reads as a platform admin and this distinction cannot exist.',
)


@override_settings(ROOT_URLCONF='branches.tests.urls',
                   SIES_PERMISSION_RESOLVER=all_permissions)
class BranchIsolationTests(TestCase):
    """A branch user must not reach another institution's rows — in either direction."""

    def setUp(self):
        self.a = make_branch(code='DHK', name='Dhaka Madrasah')
        self.b = make_branch(code='CTG', name='Chittagong Madrasah')
        self.a_session = make_session(self.a, name='2026')
        self.b_session = make_session(self.b, name='2026')
        self.client = APIClient()

    @needs_user_branch
    def test_another_branchs_stream_is_404_not_403(self):
        self.client.force_authenticate(make_branch_user(self.a))
        other_stream = self.b.stream_set.first()

        response = self.client.get(f'/api/streams/{other_stream.pk}/')

        self.assertEqual(response.status_code, 404)

    @needs_user_branch
    def test_another_branchs_session_is_404_not_403(self):
        self.client.force_authenticate(make_branch_user(self.a))

        response = self.client.get(f'/api/sessions/{self.b_session.pk}/')

        self.assertEqual(response.status_code, 404)

    @needs_user_branch
    def test_another_branchs_stream_cannot_be_written_either(self):
        """404 on read is only half of it: writing into an invisible row is worse."""
        self.client.force_authenticate(make_branch_user(self.a))
        other_stream = self.b.stream_set.first()

        response = self.client.patch(
            f'/api/streams/{other_stream.pk}/', {'name': 'Renamed'}, format='json',
        )

        self.assertEqual(response.status_code, 404)
        other_stream.refresh_from_db()
        self.assertNotEqual(other_stream.name, 'Renamed')

    @needs_user_branch
    def test_the_stream_list_shows_only_the_users_own_institution(self):
        self.client.force_authenticate(make_branch_user(self.a))

        response = self.client.get('/api/streams/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), self.a.stream_set.count())

    @needs_user_branch
    def test_a_stream_is_stamped_with_the_callers_branch_not_the_posted_one(self):
        """`branch` in a POST body is ignored (CLAUDE.md §1)."""
        self.client.force_authenticate(make_branch_user(self.a))

        response = self.client.post(
            '/api/streams/',
            {'code': 'adult', 'name': 'Adult Education', 'branch': self.b.pk},
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(self.a.stream_set.filter(code='adult').exists())
        self.assertFalse(self.b.stream_set.filter(code='adult').exists())

    @needs_user_branch
    def test_a_session_cannot_point_at_another_institutions_stream(self):
        self.client.force_authenticate(make_branch_user(self.a))

        response = self.client.post(
            '/api/sessions/',
            {
                'name': '2027',
                'streams': [self.b.stream_set.first().pk],
                'starts_on': '2027-01-01',
                'ends_on': '2027-12-31',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('streams', response.data.get('errors', response.data))


@override_settings(ROOT_URLCONF='branches.tests.urls',
                   SIES_PERMISSION_RESOLVER=all_permissions)
class BranchAccessTests(TestCase):
    """Only the platform admin may list every institution, or create or edit one."""

    def setUp(self):
        self.a = make_branch(code='DHK', name='Dhaka Madrasah')
        self.b = make_branch(code='CTG', name='Chittagong Madrasah')
        self.client = APIClient()

    @needs_user_branch
    def test_a_branch_user_reads_only_their_own_institution(self):
        self.client.force_authenticate(make_branch_user(self.a))

        listed = self.client.get('/api/branches/')
        theirs = self.client.get(f'/api/branches/{self.a.pk}/')
        other = self.client.get(f'/api/branches/{self.b.pk}/')

        self.assertEqual([row['code'] for row in listed.data['results']], ['DHK'])
        self.assertEqual(theirs.status_code, 200)
        self.assertEqual(other.status_code, 404)

    @needs_user_branch
    def test_a_branch_user_cannot_create_an_institution(self):
        self.client.force_authenticate(make_branch_user(self.a))

        response = self.client.post(
            '/api/branches/', {'name': 'Sneaky Madrasah', 'code': 'SNK'}, format='json',
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Branch.objects.filter(code='SNK').exists())

    @needs_user_branch
    def test_a_branch_user_cannot_rename_even_their_own_institution(self):
        """Renaming an institution is the platform operator's job (docs/08 D1).

        Its *settings* are a different question, and the test below is the other
        half of the line: the identity is the platform's record of who its
        customer is, and a rename would follow onto every receipt printed since.
        """
        self.client.force_authenticate(make_branch_user(self.a))

        response = self.client.patch(
            f'/api/branches/{self.a.pk}/', {'name': 'Renamed'}, format='json',
        )

        self.assertEqual(response.status_code, 403)
        self.a.refresh_from_db()
        self.assertEqual(self.a.name, 'Dhaka Madrasah')

    @needs_user_branch
    def test_a_principal_runs_their_own_institutions_settings(self):
        """`branches.update` is in the Principal preset for this.

        `fine_rule` and `restrict_teachers_to_assigned_classes` are edited on
        Settings → Institution and there is no second endpoint, so a blanket
        platform-admin check on update made an institution's own policy
        unreachable for the one person it exists for.
        """
        self.client.force_authenticate(make_branch_user(self.a))

        response = self.client.patch(
            f'/api/branches/{self.a.pk}/',
            {'restrict_teachers_to_assigned_classes': False}, format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.a.refresh_from_db()
        self.assertFalse(self.a.restrict_teachers_to_assigned_classes)
        self.assertEqual(self.a.name, 'Dhaka Madrasah')

    @needs_user_branch
    def test_a_principal_still_cannot_touch_another_institution(self):
        """404, not 403 — the id must not confirm the institution exists."""
        self.client.force_authenticate(make_branch_user(self.a))

        response = self.client.patch(
            f'/api/branches/{self.b.pk}/',
            {'restrict_teachers_to_assigned_classes': False}, format='json',
        )

        self.assertEqual(response.status_code, 404)

    def test_a_platform_admin_lists_every_institution(self):
        self.client.force_authenticate(make_platform_admin())

        response = self.client.get('/api/branches/')

        self.assertEqual(
            sorted(row['code'] for row in response.data['results']), ['CTG', 'DHK'],
        )

    def test_a_platform_admins_branch_filter_does_not_shrink_the_switcher(self):
        """`lib/api.ts` appends `?branch=` to every request, this one included.

        Honouring it here would leave the branch switcher able to offer only the
        branch already chosen — which is the one list it must not filter.
        """
        self.client.force_authenticate(make_platform_admin())

        response = self.client.get(f'/api/branches/?branch={self.a.pk}')

        self.assertEqual(len(response.data['results']), 2)

    def test_a_platform_admin_creates_a_seeded_institution(self):
        self.client.force_authenticate(make_platform_admin())

        response = self.client.post(
            '/api/branches/',
            {'name': 'New College', 'code': 'col', 'institution_type': 'college'},
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.data)
        created = Branch.objects.get(code='COL')
        # The point of creating through the service: an institution arrives
        # usable, not empty (docs/08 D1 consequence 2).
        self.assertEqual(
            sorted(created.stream_set.values_list('code', flat=True)),
            ['arts', 'commerce', 'science'],
        )

    def test_a_platform_admin_updates_an_institution(self):
        self.client.force_authenticate(make_platform_admin())

        response = self.client.patch(
            f'/api/branches/{self.a.pk}/',
            {'attendance_window_minutes': 15}, format='json',
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.a.refresh_from_db()
        self.assertEqual(self.a.attendance_window_minutes, 15)

    def test_a_duplicate_code_is_a_field_error_not_an_integrity_error(self):
        self.client.force_authenticate(make_platform_admin())

        response = self.client.post(
            '/api/branches/', {'name': 'Clash', 'code': 'dhk'}, format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('code', response.data.get('errors', response.data))

    def test_an_anonymous_request_sees_nothing(self):
        response = APIClient().get('/api/branches/')
        self.assertIn(response.status_code, (401, 403))


@override_settings(ROOT_URLCONF='branches.tests.urls',
                   SIES_PERMISSION_RESOLVER=all_permissions)
class MineEndpointTests(TestCase):
    """`GET /api/branches/mine/` — what fills the header's branch switcher."""

    def setUp(self):
        self.a = make_branch(code='DHK', name='Dhaka Madrasah')
        self.b = make_branch(code='CTG', name='Chittagong Madrasah')
        self.closed = make_branch(code='OLD', name='Closed Madrasah', is_active=False)
        self.client = APIClient()

    def test_a_platform_admin_gets_every_active_institution(self):
        self.client.force_authenticate(make_platform_admin())

        response = self.client.get('/api/branches/mine/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(sorted(row['code'] for row in response.data), ['CTG', 'DHK'])

    def test_a_closed_institution_is_not_offered(self):
        """Nobody should be able to switch into an institution that has closed."""
        self.client.force_authenticate(make_platform_admin())

        response = self.client.get('/api/branches/mine/')

        self.assertNotIn('OLD', [row['code'] for row in response.data])

    @needs_user_branch
    def test_a_branch_user_gets_only_their_own(self):
        self.client.force_authenticate(make_branch_user(self.a))

        response = self.client.get('/api/branches/mine/')

        self.assertEqual([row['code'] for row in response.data], ['DHK'])
