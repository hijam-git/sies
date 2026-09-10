"""Model-level guarantees: the constraints, and the one rule that cannot be one."""

from datetime import date

from django.db import IntegrityError, transaction
from django.test import TestCase

from branches.models import Branch, InstitutionType, Session, Stream
from branches.services import create_branch, set_current_session

from .factories import make_branch, make_session


class BranchTests(TestCase):
    def test_code_is_stored_upper_case(self):
        branch = make_branch(code='dhk')
        self.assertEqual(branch.code, 'DHK')

    def test_code_is_unique(self):
        make_branch(code='DHK')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Branch.objects.create(name='Another', code='DHK')

    def test_policy_defaults_match_the_decisions(self):
        branch = make_branch()
        # D7, D6 and D8 respectively. Asserted because each default is a
        # deliberate answer, and a silent change to any of them changes who can
        # take attendance, which classes a teacher reaches, and how long the
        # activity feed remembers.
        self.assertEqual(branch.attendance_window_minutes, 120)
        self.assertTrue(branch.restrict_teachers_to_assigned_classes)
        self.assertEqual(branch.activity_retention_days, 180)
        self.assertEqual(branch.weekly_off_days, ['fri'])

    def test_weekly_off_days_default_is_not_shared_between_branches(self):
        first = make_branch(code='DHK')
        second = make_branch(code='CTG', name='Chittagong Madrasah')

        first.weekly_off_days.append('sat')
        first.save()
        second.refresh_from_db()

        self.assertEqual(second.weekly_off_days, ['fri'])

    def test_create_branch_service_seeds_it(self):
        branch = create_branch(
            name='New School', code='SCH', institution_type=InstitutionType.SCHOOL,
        )
        self.assertEqual(list(branch.stream_set.values_list('code', flat=True)), ['general'])


class StreamTests(TestCase):
    def test_code_is_unique_within_a_branch(self):
        branch = make_branch()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Stream.objects.create(branch=branch, code='hifz', name='Hifz duplicate')

    def test_the_same_code_may_exist_in_another_branch(self):
        first = make_branch(code='DHK')
        second = make_branch(code='CTG', name='Chittagong Madrasah')

        self.assertTrue(first.stream_set.filter(code='hifz').exists())
        self.assertTrue(second.stream_set.filter(code='hifz').exists())

    def test_code_is_stored_lower_case(self):
        branch = make_branch(code='SCH', institution_type=InstitutionType.SCHOOL)
        stream = Stream.objects.create(branch=branch, code='  Science ', name='Science')
        self.assertEqual(stream.code, 'science')


class SessionTests(TestCase):
    def test_name_is_unique_within_a_branch(self):
        branch = make_branch()
        make_session(branch, name='2026')

        with self.assertRaises(IntegrityError), transaction.atomic():
            Session.objects.create(
                branch=branch, name='2026',
                starts_on=date(2026, 6, 1), ends_on=date(2027, 5, 31),
            )

    def test_a_session_cannot_end_before_it_starts(self):
        branch = make_branch()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Session.objects.create(
                branch=branch, name='backwards',
                starts_on=date(2026, 12, 31), ends_on=date(2026, 1, 1),
            )


class CurrentSessionTests(TestCase):
    """docs/03 §2: at most one current session per (branch, stream).

    Service-enforced, not a database constraint — the pair spans the
    `Session.streams` join table and no `UniqueConstraint` can reach through an
    M2M. These tests are therefore the only thing holding the rule, which is why
    they cover the overlap case, the disjoint case and the cross-branch case
    separately.
    """

    def setUp(self):
        self.branch = make_branch()
        self.hifz = self.branch.stream_set.get(code='hifz')
        self.qaumi = self.branch.stream_set.get(code='qaumi')
        self.general = self.branch.stream_set.get(code='general')

    def test_making_one_current_clears_the_other_on_the_same_stream(self):
        old = make_session(self.branch, name='2025', streams=[self.hifz, self.general])
        set_current_session(old)

        new = make_session(self.branch, name='2026', streams=[self.hifz])
        set_current_session(new)

        old.refresh_from_db()
        new.refresh_from_db()
        self.assertFalse(old.is_current)
        self.assertTrue(new.is_current)

    def test_two_sessions_on_disjoint_streams_may_both_be_current(self):
        """A madrasah runs the Hijri year for qaumi and the Gregorian for general."""
        hijri = make_session(self.branch, name='1447', streams=[self.qaumi])
        gregorian = make_session(self.branch, name='2026', streams=[self.general])

        set_current_session(hijri)
        set_current_session(gregorian)

        hijri.refresh_from_db()
        gregorian.refresh_from_db()
        self.assertTrue(hijri.is_current)
        self.assertTrue(gregorian.is_current)

    def test_a_session_with_no_streams_clears_every_other(self):
        """No streams means "the whole institution", so nothing else stays current."""
        scoped = make_session(self.branch, name='2025', streams=[self.hifz])
        set_current_session(scoped)

        whole = make_session(self.branch, name='2026', streams=[])
        set_current_session(whole)

        scoped.refresh_from_db()
        self.assertFalse(scoped.is_current)

    def test_another_institutions_session_is_untouched(self):
        other = make_branch(code='CTG', name='Chittagong Madrasah')
        theirs = make_session(other, name='2026')
        set_current_session(theirs)

        ours = make_session(self.branch, name='2026')
        set_current_session(ours)

        theirs.refresh_from_db()
        self.assertTrue(theirs.is_current)

    def test_the_branch_default_follows_the_current_session(self):
        session = make_session(self.branch, name='2026')
        set_current_session(session)

        self.branch.refresh_from_db()
        self.assertEqual(self.branch.current_session_id, session.pk)
