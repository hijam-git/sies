"""Demo data — for looking at the app by hand.

**Tests must not depend on this** (CLAUDE.md §4a). A shared demo dataset that the
suite asserts against becomes a thing nobody dares change; each module builds its
own small fixture in `<app>/tests/factories.py` instead. This exists so that a
developer, a reviewer or the owner can open the SPA and see something shaped like
a real institution.

Phase 1 seeds what Phase 1 has: one madrasah, its three streams (via the ordinary
branch-creation service, so the demo exercises the same path production does) and
a current session. Later phases add classes, students, teachers, a month of
attendance and part-collected fees — `scripts/seed_demo.sh` in CLAUDE.md §6
describes the finished shape.

**How to extend it:** append a step function to `STEPS`. Each takes the branch,
is idempotent on its own natural key, and returns a one-line summary. That is the
whole contract — Phase 2 adds `seed_classes`, Phase 5 adds `seed_fees`, and
nobody has to rewrite `handle()`.
"""

from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction

from branches.models import Branch, InstitutionType, Session
from branches.seeding import seed_branch
from branches.services import create_branch, set_current_session

DEMO_BRANCH_CODE = 'DEMO'


class Command(BaseCommand):
    help = 'Create a demo institution with realistic data, for manual inspection.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--code', default=DEMO_BRANCH_CODE,
            help=f'Institution code to create or reuse (default {DEMO_BRANCH_CODE}).',
        )
        parser.add_argument(
            '--year', type=int, default=date.today().year,
            help='Academic year for the current session (default: this year).',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        branch = self._branch(options['code'])

        for step in STEPS:
            self.stdout.write(f'  {step(branch, options)}')

        self.stdout.write(self.style.SUCCESS(
            f'Demo institution {branch.code} is ready — open /myadmin and pick it.'
        ))

    def _branch(self, code):
        """Create the institution, or reuse the one already there.

        Re-running must not fail and must not make a second demo madrasah, so
        this matches on the code and falls back to `seed_branch()` for a branch
        that predates a newly-added seed row.
        """
        code = code.strip().upper()
        existing = Branch.objects.filter(code=code).first()
        if existing is not None:
            seed_branch(existing)
            self.stdout.write(f'  reusing {existing.name} ({code})')
            return existing

        branch = create_branch(
            name='Darul Uloom Model Madrasah',
            name_bn='দারুল উলূম মডেল মাদ্রাসা',
            name_ar='دار العلوم النموذجية',
            institution_type=InstitutionType.MADRASAH,
            code=code,
            established_year=1998,
            address='Mirpur 10, Dhaka 1216',
            address_bn='মিরপুর ১০, ঢাকা ১২১৬',
            district='Dhaka',
            thana='Mirpur',
            phone='01711000000',
            email='office@demo-madrasah.test',
        )
        self.stdout.write(f'  created {branch.name} ({code}) with its seeded streams')
        return branch


def seed_session(branch, options):
    """One current session covering every stream the branch has.

    Through `set_current_session()` rather than `is_current=True` on the create,
    because that service is what enforces the one-current-per-stream rule and
    points `Branch.current_session` at it — the demo should exercise the real
    path, not a shortcut around it.
    """
    year = options['year']
    session, created = Session.objects.get_or_create(
        branch=branch,
        name=str(year),
        defaults={
            'starts_on': date(year, 1, 1),
            'ends_on': date(year, 12, 31),
        },
    )
    session.streams.set(branch.stream_set.all())
    set_current_session(session)
    return f'session {session.name} {"created" if created else "reused"} and made current'


# Append later phases here; see the module docstring for the contract.
STEPS = [
    seed_session,
]
