"""Create a platform admin — the first account on a fresh install.

    python manage.py create_admin --phone 01712345678 --name "Ops" --password s3cret
    python manage.py create_admin                       # interactive

`scripts/fresh_deploy.sh` step 7 makes the first account with Django's own
`createsuperuser`, which needs a TTY and asks for `phone` and `name` because
those are `USERNAME_FIELD` and `REQUIRED_FIELDS`. This command is the
non-interactive half of the same job: it takes every value as an argument, so it
can run under cron, CI or a piped shell, and it is idempotent — running it twice
with the same phone updates the existing account rather than failing on the
unique index.

Idempotence is the point. A deploy script that cannot be re-run safely is a
deploy script somebody runs once and then edits by hand.
"""

import getpass
import sys

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import User, UserType
from accounts.phone import normalize_bd_phone


class Command(BaseCommand):
    help = 'Create or update a platform admin (branch = NULL, sees every institution).'

    def add_arguments(self, parser):
        parser.add_argument('--phone', help='11-digit mobile. +88 and dashed forms are accepted.')
        parser.add_argument('--name', help="The person's name, as it should appear.")
        parser.add_argument('--name-bn', default='', help='The same name in Bangla.')
        parser.add_argument('--email', default='', help='Optional. Never a login credential.')
        parser.add_argument('--password', help='Read from the terminal when omitted.')
        parser.add_argument(
            '--noinput', '--no-input', action='store_true', dest='noinput',
            help='Never prompt. Every required value must be given as an argument.',
        )
        parser.add_argument(
            '--must-change-password', action='store_true',
            help='Force a password change at first login. Use when the password '
                 'was typed into a shared terminal or a deploy log.',
        )

    def handle(self, *args, **options):
        noinput = options['noinput']

        phone = options.get('phone') or ('' if noinput else self._ask('Phone (01XXXXXXXXX): '))
        canonical = normalize_bd_phone(phone)
        if not canonical:
            raise CommandError(
                f'"{phone or ""}" is not a Bangladeshi mobile number. '
                'Expected 11 digits starting 01, e.g. 01712345678.'
            )

        name = options.get('name') or ('' if noinput else self._ask('Name: '))
        if not name.strip():
            raise CommandError('--name is required.')

        password = options.get('password')
        if not password:
            if noinput:
                raise CommandError('--password is required with --noinput.')
            password = self._ask_password()

        existing = User.objects.filter(phone=canonical).first()

        # One transaction: an account that exists with no password, or with
        # platform-admin rights and the wrong password, is worse than no account.
        with transaction.atomic():
            if existing is None:
                try:
                    user = User.objects.create_superuser(
                        phone=canonical,
                        password=password,
                        name=name.strip(),
                        name_bn=options['name_bn'],
                        email=options['email'],
                        must_change_password=options['must_change_password'],
                    )
                except ValidationError as exc:
                    raise CommandError('; '.join(_messages(exc)))
                created = True
            else:
                # Re-running the deploy script must not fail, and must not leave
                # a half-privileged account behind either: everything that makes
                # this a platform admin is re-asserted.
                existing.name = name.strip()
                existing.name_bn = options['name_bn'] or existing.name_bn
                existing.email = options['email'] or existing.email
                existing.user_type = UserType.PLATFORM_ADMIN
                existing.branch = None
                existing.is_active = True
                existing.is_staff = True
                existing.is_superuser = True
                existing.must_change_password = options['must_change_password']
                existing.set_password(password)
                existing.save()
                user = existing
                created = False

        verb = 'Created' if created else 'Updated'
        self.stdout.write(self.style.SUCCESS(
            f'{verb} platform admin {user.name} ({user.phone}). '
            'Branch is NULL, so this account sees every institution.'
        ))

    def _ask(self, prompt):
        if not sys.stdin.isatty():
            raise CommandError(
                'No terminal to ask on. Pass every value as an argument, e.g. '
                'create_admin --noinput --phone 01712345678 --name "Ops" --password …'
            )
        return input(prompt).strip()

    def _ask_password(self):
        if not sys.stdin.isatty():
            raise CommandError('No terminal to ask on. Pass --password.')
        first = getpass.getpass('Password: ')
        second = getpass.getpass('Password (again): ')
        if first != second:
            raise CommandError('The two passwords do not match.')
        if not first:
            raise CommandError('A password is required.')
        return first


def _messages(exc):
    """A Django ValidationError's sentences, however it was raised."""
    if hasattr(exc, 'message_dict'):
        return [f'{field}: {" ".join(msgs)}' for field, msgs in exc.message_dict.items()]
    return list(getattr(exc, 'messages', [str(exc)]))
