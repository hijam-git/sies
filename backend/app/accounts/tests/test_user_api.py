"""UserViewSet: branch isolation, and the permission-setting action.

The branch-isolation assertion is the required one (CLAUDE.md §8 rule 4): a
branch-A user asking for a branch-B account must get **404, not 403**, because
403 confirms the row exists and that is exactly what a probe is looking for.
"""

from django.test import TestCase
from django.urls import reverse

from accounts.models import ActivityAction, ActivityLog, User
from accounts.permissions import preset_for

from .factories import make_branch, make_platform_admin, make_role, make_user


class BranchIsolationTests(TestCase):
    def setUp(self):
        self.branch_a = make_branch(name='Dhaka', code='DHK')
        self.branch_b = make_branch(name='Chittagong', code='CTG')

        self.users_role = make_role('Institution Admin',
                                    matrix={'users': ['view', 'create', 'update']})

        self.admin_a = make_user(branch=self.branch_a, user_type='principal',
                                 role=self.users_role, name='Principal A')
        self.staff_b = make_user(branch=self.branch_b, name='Teacher B')

    def test_a_branch_a_user_gets_404_for_a_branch_b_account(self):
        self.client.force_login(self.admin_a)
        url = reverse('accounts:user-detail', args=[self.staff_b.pk])

        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['code'], 'not_found')

    def test_the_same_holds_for_a_write(self):
        self.client.force_login(self.admin_a)
        url = reverse('accounts:user-detail', args=[self.staff_b.pk])

        response = self.client.patch(url, {'name': 'Renamed'},
                                     content_type='application/json')
        self.assertEqual(response.status_code, 404)

        self.staff_b.refresh_from_db()
        self.assertEqual(self.staff_b.name, 'Teacher B')

    def test_the_list_shows_only_this_institution(self):
        self.client.force_login(self.admin_a)
        body = self.client.get(reverse('accounts:user-list')).json()
        phones = {row['phone'] for row in body['results']}

        self.assertIn(self.admin_a.phone, phones)
        self.assertNotIn(self.staff_b.phone, phones)

    def test_a_platform_admin_sees_every_institution(self):
        self.client.force_login(make_platform_admin())
        body = self.client.get(reverse('accounts:user-list')).json()
        phones = {row['phone'] for row in body['results']}

        self.assertIn(self.admin_a.phone, phones)
        self.assertIn(self.staff_b.phone, phones)

    def test_a_branch_id_in_the_body_is_ignored_on_create(self):
        """The client never supplies `branch` (CLAUDE.md §1)."""
        self.client.force_login(self.admin_a)

        response = self.client.post(
            reverse('accounts:user-list'),
            {'phone': '01755000111', 'name': 'New Clerk', 'user_type': 'employee',
             'branch': self.branch_b.pk, 'password': 'a-decent-password-1'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)

        created = User.objects.get(phone='01755000111')
        self.assertEqual(created.branch, self.branch_a)

    def test_creating_an_account_logs_it(self):
        self.client.force_login(self.admin_a)
        self.client.post(
            reverse('accounts:user-list'),
            {'phone': '01755000222', 'name': 'Another', 'user_type': 'employee',
             'password': 'a-decent-password-1'},
            content_type='application/json',
        )
        self.assertTrue(
            ActivityLog.objects.filter(action=ActivityAction.CREATE,
                                       model='User').exists())

    def test_an_admin_created_account_must_change_its_password(self):
        self.client.force_login(self.admin_a)
        self.client.post(
            reverse('accounts:user-list'),
            {'phone': '01755000333', 'name': 'Third', 'user_type': 'employee',
             'password': 'a-decent-password-1'},
            content_type='application/json',
        )
        self.assertTrue(User.objects.get(phone='01755000333').must_change_password)


class PermissionActionTests(TestCase):
    """`POST …/users/<id>/permissions/` — docs/02 §2.3."""

    def setUp(self):
        self.branch = make_branch()
        self.admin = make_user(
            branch=self.branch, user_type='principal', name='Principal',
            role=make_role('Institution Admin',
                           matrix={'users': ['view', 'create', 'update']}),
        )
        self.teacher = make_user(branch=self.branch, role=make_role('Teacher'),
                                 name='Teacher')
        self.url = reverse('accounts:user-permissions', args=[self.teacher.pk])

    def post(self, permissions):
        self.client.force_login(self.admin)
        return self.client.post(self.url, {'permissions': permissions},
                                content_type='application/json')

    def test_setting_a_list_replaces_the_preset_entirely(self):
        response = self.post(['fees.collect', 'dashboard.view'])
        self.assertEqual(response.status_code, 200)

        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.permissions, ['dashboard.view', 'fees.collect'])
        self.assertEqual(set(self.teacher.effective_permissions),
                         {'dashboard.view', 'fees.collect'})

    def test_unknown_strings_are_dropped_before_they_are_stored(self):
        self.post(['fees.collect', 'fees.teleport', 'orders.view'])
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.permissions, ['fees.collect'])

    def test_an_empty_list_puts_them_back_on_the_preset(self):
        self.post(['fees.collect'])
        self.post([])

        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.permissions, [])
        self.assertEqual(set(self.teacher.effective_permissions),
                         set(preset_for('Teacher')))

    def test_the_change_is_logged_with_before_and_after(self):
        self.post(['fees.collect'])

        entry = (ActivityLog.objects
                 .filter(model='User', action=ActivityAction.UPDATE)
                 .order_by('-id').first())
        self.assertEqual(entry.user, self.admin)
        self.assertEqual(entry.before, {'permissions': []})
        self.assertEqual(entry.after, {'permissions': ['fees.collect']})

    def test_a_user_without_users_update_cannot_set_permissions(self):
        """POST on a custom action means UPDATE, not create (docs/WORKLOG F1).

        The teacher below holds `users.view` and `users.create` but not
        `users.update`. Without POST_IS_AN_UPDATE the custom action would have
        been authorised by `users.create`, which is a different decision.
        """
        weak = make_user(
            branch=self.branch, name='Weak',
            role=make_role('Weak role', matrix={'users': ['view', 'create']}),
        )
        self.client.force_login(weak)

        response = self.client.post(self.url, {'permissions': ['fees.collect']},
                                    content_type='application/json')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['code'], 'permission_denied')

    def test_a_branch_b_target_is_404_here_too(self):
        other = make_user(branch=make_branch(name='Chittagong', code='CTG'))
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse('accounts:user-permissions', args=[other.pk]),
            {'permissions': ['fees.collect']},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 404)


class PermissionCatalogEndpointTests(TestCase):
    def test_it_serves_the_catalogue_and_the_presets(self):
        self.client.force_login(make_platform_admin())
        body = self.client.get(reverse('accounts:permission-catalog')).json()['data']

        self.assertEqual(len(body['resources']), 20)
        self.assertTrue(body['presets'])

        # The reason this endpoint exists: the SPA's checkboxes are generated
        # from what the backend enforces, so they cannot drift from it.
        catalogue = {f"{r['resource']}.{a}" for r in body['resources']
                     for a in r['actions']}
        for preset in body['presets']:
            self.assertTrue(set(preset['permissions']) <= catalogue,
                            f"{preset['name']} grants something uncatalogued")
