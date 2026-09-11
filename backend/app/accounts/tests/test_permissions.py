"""Permission resolution — docs/02 §2.3 and docs/WORKLOG F1.

These four cases are the whole rule, and each of them is a way the system could
quietly grant access nobody meant to give.
"""

from django.test import TestCase

from accounts.permissions import (PERMISSION_CATALOG, ROLE_PRESETS,
                                  VALID_PERMISSIONS, clean_permissions,
                                  effective_permissions, has_permission,
                                  preset_for)

from .factories import make_branch, make_platform_admin, make_role, make_user


class CatalogueTests(TestCase):
    def test_the_catalogue_matches_the_twenty_resources_of_the_docs(self):
        resources = [entry['resource'] for entry in PERMISSION_CATALOG]
        self.assertEqual(len(resources), 20)
        self.assertEqual(len(set(resources)), 20, 'a resource is listed twice')
        self.assertEqual(resources, [
            'dashboard', 'branches', 'academics', 'students', 'admissions',
            'teachers', 'employees', 'attendance', 'fees', 'income', 'expenses',
            'salary',
            'exams', 'marks', 'reports', 'notices', 'documents', 'settings',
            'users', 'activity',
        ])

    def test_every_entry_is_bilingual(self):
        # A user-facing string with no Bangla is a screen that falls back to
        # English for most of this system's users (CLAUDE.md §8 rule 9).
        for entry in PERMISSION_CATALOG:
            with self.subTest(resource=entry['resource']):
                for key in ('label', 'label_bn', 'hint', 'hint_bn'):
                    self.assertTrue(entry[key].strip(), f'{key} is empty')
                self.assertTrue(entry['actions'])

    def test_every_preset_only_grants_permissions_that_exist(self):
        for name in ROLE_PRESETS:
            with self.subTest(preset=name):
                self.assertTrue(set(preset_for(name)) <= VALID_PERMISSIONS)

    def test_the_documented_preset_shapes(self):
        # Spot-checks of the distinctions docs/02 §2.2 makes on purpose.
        self.assertNotIn('branches.create', preset_for('Principal'))
        self.assertNotIn('activity.view', preset_for('Principal'))
        self.assertNotIn('salary.view', preset_for('Accountant'))
        self.assertNotIn('exams.publish', preset_for('Teacher'))
        self.assertIn('marks.enter', preset_for('Teacher'))
        # take, but not update: correcting the register is the class teacher's.
        self.assertNotIn('attendance.update', preset_for('Teacher'))
        self.assertIn('attendance.update', preset_for('Class Teacher'))
        self.assertEqual(preset_for('General Employee'), ['dashboard.view'])

    def test_each_clerk_records_one_side_of_the_ledger_only(self):
        income_clerk = preset_for('Income Clerk')
        self.assertIn('income.create', income_clerk)
        self.assertNotIn('income.update', income_clerk)
        self.assertFalse([p for p in income_clerk if p.startswith('expenses.')])

        expense_clerk = preset_for('Expense Clerk')
        self.assertIn('expenses.create', expense_clerk)
        self.assertNotIn('expenses.update', expense_clerk)
        self.assertFalse([p for p in expense_clerk if p.startswith('income.')])

        # The accountant still holds both sides.
        for permission in ('income.update', 'expenses.update'):
            self.assertIn(permission, preset_for('Accountant'))


class CleanPermissionsTests(TestCase):
    def test_unknown_strings_are_dropped(self):
        self.assertEqual(
            clean_permissions(['fees.collect', 'fees.teleport', 'nonsense', 42, None]),
            ['fees.collect'],
        )

    def test_a_non_list_is_an_empty_list(self):
        for raw in [None, 'fees.collect', 17, {'fees': ['collect']}]:
            with self.subTest(raw=raw):
                self.assertEqual(clean_permissions(raw), [])


class EffectivePermissionsTests(TestCase):
    def setUp(self):
        self.branch = make_branch()
        self.role = make_role('Teacher')

    def test_empty_list_falls_back_to_the_role_preset(self):
        user = make_user(branch=self.branch, role=self.role, permissions=[])
        self.assertEqual(effective_permissions(user), set(preset_for('Teacher')))

    def test_an_explicit_list_wins_and_is_not_merged_with_the_preset(self):
        """The single most important assertion in this file.

        Merging would mean unticking a box the preset grants does nothing at all
        — the admin believes they revoked access and did not (docs/02 §2.3).
        """
        user = make_user(branch=self.branch, role=self.role,
                         permissions=['fees.collect'])

        self.assertEqual(effective_permissions(user), {'fees.collect'})
        self.assertNotIn('marks.enter', effective_permissions(user),
                         'the preset leaked through the explicit list')
        self.assertTrue(has_permission(user, 'fees', 'collect'))
        self.assertFalse(has_permission(user, 'marks', 'enter'))

    def test_an_inactive_user_has_nothing_not_the_preset(self):
        """A dismissed employee must not keep working access (docs/WORKLOG F1)."""
        user = make_user(branch=self.branch, role=self.role, is_active=False)
        self.assertEqual(effective_permissions(user), set())
        self.assertFalse(has_permission(user, 'dashboard', 'view'))

    def test_an_inactive_user_with_an_explicit_list_also_has_nothing(self):
        user = make_user(branch=self.branch, role=self.role,
                         permissions=['fees.collect'], is_active=False)
        self.assertEqual(effective_permissions(user), set())

    def test_a_stale_permission_string_is_dropped_not_granted(self):
        """A string from an older release must not grant anything (F1)."""
        user = make_user(branch=self.branch, role=self.role,
                         permissions=['fees.collect', 'storefront.publish',
                                      'orders.view'])
        self.assertEqual(effective_permissions(user), {'fees.collect'})

    def test_a_stale_string_in_a_role_matrix_is_also_dropped(self):
        role = make_role('Odd', matrix={'orders': ['view'], 'fees': ['view']})
        user = make_user(branch=self.branch, role=role)
        self.assertEqual(effective_permissions(user), {'fees.view'})

    def test_no_role_and_no_list_is_no_access(self):
        user = make_user(branch=self.branch, role=None, permissions=[])
        self.assertEqual(effective_permissions(user), set())

    def test_a_superuser_holds_the_whole_catalogue(self):
        admin = make_platform_admin()
        self.assertEqual(effective_permissions(admin), VALID_PERMISSIONS)

    def test_an_inactive_superuser_holds_nothing(self):
        admin = make_platform_admin()
        admin.is_active = False
        admin.save()
        self.assertEqual(effective_permissions(admin), set())

    def test_anonymous_holds_nothing(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertEqual(effective_permissions(AnonymousUser()), set())
        self.assertEqual(effective_permissions(None), set())
