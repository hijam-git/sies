"""Write the shipped role presets into the `Role` table.

    python manage.py seed_roles

`ROLE_PRESETS` is the definition; `Role` rows are what a user's FK points at, so
one has to become the other before anyone can be given a role at all.

Idempotent, and deliberately conservative about overwriting: a system role's
matrix is refreshed on every run, because that is how a preset change reaches
the institutions still on it (docs/02 §2.3). An institution's OWN roles are
never touched — they are not in `ROLE_PRESETS` and this command does not delete
anything.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Role
from accounts.permissions import ROLE_NAMES_BN, ROLE_PRESETS, preset_matrix


class Command(BaseCommand):
    help = 'Create or refresh the system role presets (docs/02 §2.2).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--keep-matrix', action='store_true',
            help='Create missing roles but leave existing matrices alone. Use on an '
                 'installation whose admin has hand-edited a system preset.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        created = updated = 0

        for name in ROLE_PRESETS:
            role, was_created = Role.objects.get_or_create(
                name=name,
                defaults={
                    'name_bn': ROLE_NAMES_BN.get(name, ''),
                    'permission_matrix': preset_matrix(name),
                    'is_system': True,
                },
            )
            if was_created:
                created += 1
                continue

            if options['keep_matrix']:
                continue

            role.name_bn = role.name_bn or ROLE_NAMES_BN.get(name, '')
            role.permission_matrix = preset_matrix(name)
            role.is_system = True
            role.save(update_fields=['name_bn', 'permission_matrix', 'is_system',
                                     'updated_at'])
            updated += 1

        self.stdout.write(self.style.SUCCESS(
            f'Roles seeded: {created} created, {updated} refreshed, '
            f'{len(ROLE_PRESETS)} system presets in total.'
        ))
