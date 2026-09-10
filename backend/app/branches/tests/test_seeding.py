"""Branch seeding — decision 1 of the "smart" list (docs/00 §2).

The two properties the deploy scripts rely on are asserted here: seeding is
idempotent, and each `institution_type` gets the streams docs/00 §1 tabulates.
"""

from django.core.management import call_command
from django.test import TestCase

from branches.models import InstitutionType, Stream
from branches.seed_data import (
    EXPENSE_CATEGORY_SEEDS,
    FEE_CATEGORY_SEEDS,
    INCOME_CATEGORY_SEEDS,
    STREAM_SEEDS,
)
from branches.seeding import seed_branch

from .factories import make_bare_branch, make_branch


class SeedStreamsTests(TestCase):
    def test_madrasah_gets_the_three_canonical_streams(self):
        branch = make_bare_branch(institution_type=InstitutionType.MADRASAH)
        seed_branch(branch)

        self.assertEqual(
            list(branch.stream_set.order_by('order').values_list('code', flat=True)),
            ['hifz', 'qaumi', 'general'],
        )

    def test_school_gets_general_only(self):
        branch = make_bare_branch(code='SCH', institution_type=InstitutionType.SCHOOL)
        seed_branch(branch)

        self.assertEqual(
            list(branch.stream_set.values_list('code', flat=True)), ['general'],
        )

    def test_college_gets_science_commerce_arts(self):
        branch = make_bare_branch(code='COL', institution_type=InstitutionType.COLLEGE)
        seed_branch(branch)

        self.assertEqual(
            list(branch.stream_set.order_by('order').values_list('code', flat=True)),
            ['science', 'commerce', 'arts'],
        )

    def test_combined_gets_all_six(self):
        branch = make_bare_branch(code='CMB', institution_type=InstitutionType.COMBINED)
        seed_branch(branch)

        self.assertEqual(
            list(branch.stream_set.order_by('order').values_list('code', flat=True)),
            ['hifz', 'qaumi', 'general', 'science', 'commerce', 'arts'],
        )

    def test_every_institution_type_has_a_seed_list(self):
        """A type with no entry would create a branch nobody can enrol into."""
        self.assertEqual(
            set(STREAM_SEEDS), {choice.value for choice in InstitutionType},
        )

    def test_streams_carry_a_bangla_label(self):
        branch = make_bare_branch(institution_type=InstitutionType.MADRASAH)
        seed_branch(branch)

        for stream in branch.stream_set.all():
            self.assertTrue(stream.name_bn, f'{stream.code} has no Bangla label')


class IdempotencyTests(TestCase):
    """`fresh_deploy.sh` re-runs this on every deploy. Twice must equal once."""

    def test_seeding_twice_creates_one_set(self):
        branch = make_bare_branch(institution_type=InstitutionType.MADRASAH)

        first = seed_branch(branch)
        second = seed_branch(branch)

        self.assertEqual(first['streams'], 3)
        self.assertEqual(second['streams'], 0)
        self.assertEqual(branch.stream_set.count(), 3)

    def test_reseeding_keeps_the_institutions_own_label(self):
        """A madrasah that renamed হিফজ to হাফজ must not have it renamed back.

        Seeding fills gaps; it never overwrites what the institution decided.
        """
        branch = make_branch()
        hifz = branch.stream_set.get(code='hifz')
        hifz.name_bn = 'হাফজ'
        hifz.order = 99
        hifz.save()

        seed_branch(branch)

        hifz.refresh_from_db()
        self.assertEqual(hifz.name_bn, 'হাফজ')
        self.assertEqual(hifz.order, 99)

    def test_management_command_seeds_every_branch(self):
        madrasah = make_bare_branch(code='DHK', institution_type=InstitutionType.MADRASAH)
        college = make_bare_branch(code='CTG', institution_type=InstitutionType.COLLEGE)

        call_command('seed_categories')

        self.assertEqual(madrasah.stream_set.count(), 3)
        self.assertEqual(college.stream_set.count(), 3)

    def test_management_command_accepts_one_branch_by_code(self):
        madrasah = make_bare_branch(code='DHK')
        other = make_bare_branch(code='CTG')

        call_command('seed_categories', branch='dhk')

        self.assertEqual(madrasah.stream_set.count(), 3)
        self.assertEqual(other.stream_set.count(), 0)

    def test_management_command_survives_an_empty_database(self):
        """fresh_deploy.sh runs this before any institution exists."""
        call_command('seed_categories')
        self.assertEqual(Stream.objects.count(), 0)


class SeedDataTests(TestCase):
    """The Phase 5 tables, checked as data even though nothing consumes them yet.

    They are specified in docs/03 §7–§8 and live here (`seed_data.py`) until the
    `fees` and `finance` apps land. Checking their shape now is what stops a typo
    sitting undiscovered until the phase that reads them.
    """

    def test_the_eleven_fee_categories_are_present(self):
        codes = [row['code'] for row in FEE_CATEGORY_SEEDS]
        self.assertEqual(
            codes,
            ['ADM', 'SES', 'MON', 'EXM', 'BOK', 'UNI', 'TRN', 'HOS', 'FOD', 'ACT', 'OTH'],
        )

    def test_every_seeded_category_is_bilingual_and_explained(self):
        for row in FEE_CATEGORY_SEEDS + INCOME_CATEGORY_SEEDS + EXPENSE_CATEGORY_SEEDS:
            self.assertTrue(row['name'], row['code'])
            self.assertTrue(row['name_bn'], row['code'])
            self.assertTrue(row['note'], row['code'])
            self.assertTrue(row['note_bn'], row['code'])

    def test_income_categories_map_to_real_fee_categories(self):
        """The link is what posts a collected fee to the right head by itself."""
        fee_codes = {row['code'] for row in FEE_CATEGORY_SEEDS}
        for row in INCOME_CATEGORY_SEEDS:
            mapped = row['fee_category']
            if mapped is not None:
                self.assertIn(mapped, fee_codes, row['code'])

    def test_codes_are_unique_within_each_seed_list(self):
        for rows in (FEE_CATEGORY_SEEDS, INCOME_CATEGORY_SEEDS, EXPENSE_CATEGORY_SEEDS):
            codes = [row['code'] for row in rows]
            self.assertEqual(len(codes), len(set(codes)))
