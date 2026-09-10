"""Re-run branch seeding.

`scripts/fresh_deploy.sh` step 8 calls this with **no arguments** on every fresh
deploy, and its comment states the contract this command must keep: *"idempotent
by design … running it twice is a no-op, which is why it is safe to leave in a
script people re-run."* So no arguments means every branch, a database with no
branches yet is a success and not an error, and the exit code is 0 unless
something actually failed.

The name is the one the scripts and CLAUDE.md §6 already use. It says
"categories" because fee and finance categories are the bulk of what it will
seed once Phase 5 lands; today it seeds streams, through the same
`seed_branch()` the branch-creation service calls.
"""

from django.core.management.base import BaseCommand, CommandError

from branches.models import Branch
from branches.seeding import seed_branch


class Command(BaseCommand):
    help = 'Seed default streams and categories for one branch, or for all of them.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--branch',
            help='Institution code (DHK) or numeric id. Omit to seed every branch.',
        )

    def handle(self, *args, **options):
        branches = self._select(options.get('branch'))

        if not branches:
            # Not an error. fresh_deploy.sh runs this immediately after the first
            # migrate, before anyone has created an institution; failing there
            # would abort a deploy over nothing.
            self.stdout.write(self.style.WARNING(
                'No branches to seed yet — create one first '
                '(POST /api/branches/, or scripts/create_branch.sh).'
            ))
            return

        for branch in branches:
            created = seed_branch(branch)
            total = sum(created.values())
            summary = ', '.join(f'{count} {what}' for what, count in sorted(created.items()))
            if total:
                self.stdout.write(self.style.SUCCESS(f'{branch.code}: created {summary}'))
            else:
                # The expected output on a re-run, and the reason this is safe
                # to leave in a deploy script.
                self.stdout.write(f'{branch.code}: already seeded ({summary})')

    def _select(self, identifier):
        if not identifier:
            return list(Branch.objects.all())

        # Code or id, because a human types DHK and a script has the id to hand.
        branch = Branch.objects.filter(code=identifier.strip().upper()).first()
        if branch is None and identifier.isdigit():
            branch = Branch.objects.filter(pk=int(identifier)).first()
        if branch is None:
            raise CommandError(f'No branch with code or id "{identifier}".')
        return [branch]
