"""A small, fast fixture for this module (CLAUDE.md §4a).

One or two institutions, their seeded streams and a session — enough to exercise
every path in `branches`, small enough to build in milliseconds. Nothing here
reaches into another app's data, and no test in this package uses `seed_demo`.

The user helpers go through `get_user_model()` and never import `accounts`, so
these tests describe the *contract* the middleware relies on — "an authenticated
user object with an optional `branch`" — rather than one app's implementation of
it.
"""

from datetime import date

from django.contrib.auth import get_user_model

from branches.models import Branch, InstitutionType, Session
from branches.services import create_branch

# Whether the project's user model carries a `branch` column yet. It does the
# moment the accounts app lands; until then `auth.User` stands in (see
# core/settings.py) and every account reads as a platform admin, so the tests
# that turn on the difference skip rather than pass for the wrong reason.
USER_HAS_BRANCH = any(
    field.name == 'branch' for field in get_user_model()._meta.get_fields()
)


def make_branch(code='DHK', name='Dhaka Madrasah',
                institution_type=InstitutionType.MADRASAH, **extra):
    """A seeded institution, created the way production creates one."""
    return create_branch(
        name=name,
        name_bn=extra.pop('name_bn', 'ঢাকা মাদ্রাসা'),
        code=code,
        institution_type=institution_type,
        **extra,
    )


def make_bare_branch(code='BARE', name='Unseeded Institution', **extra):
    """A branch created without seeding — for testing the seeder in isolation."""
    return Branch.objects.create(
        name=name, code=code,
        institution_type=extra.pop('institution_type', InstitutionType.MADRASAH),
        **extra,
    )


def make_session(branch, name='2026', streams=None, is_current=False,
                 starts_on=None, ends_on=None):
    session = Session.objects.create(
        branch=branch,
        name=name,
        starts_on=starts_on or date(2026, 1, 1),
        ends_on=ends_on or date(2026, 12, 31),
        is_current=is_current,
    )
    session.streams.set(branch.stream_set.all() if streams is None else streams)
    return session


def _user_field_names():
    return {field.name for field in get_user_model()._meta.get_fields()}


def _new_user(username, branch, user_type, **extra):
    """An account, built against whatever the project's user model actually is.

    Every optional field is set only if the model has it. That is what lets this
    module test the middleware's contract — "an authenticated user with an
    optional `branch`" — without importing `accounts`, and what stops these
    tests breaking every time that app gains a column.
    """
    User = get_user_model()
    names = _user_field_names()
    fields = {User.USERNAME_FIELD: username, **extra}

    if 'branch' in names:
        fields['branch'] = branch
    # accounts.User has a check constraint tying user_type to branch: a
    # platform_admin has no branch and everyone else must have one.
    if 'user_type' in names:
        fields.setdefault('user_type', user_type)
    if 'name' in names:
        fields.setdefault('name', f'Test {username}')

    return User.objects.create_user(password='pass-phrase-1234', **fields)


def make_branch_user(branch, username='01711000001', **extra):
    """Someone who belongs to one institution."""
    return _new_user(username, branch, 'principal', **extra)


def make_platform_admin(username='01711000000', **extra):
    """The operator of the platform: no branch of their own (docs/01 §5.2)."""
    return _new_user(username, None, 'platform_admin', **extra)


def all_permissions(user):
    """A resolver that grants everything.

    Used with `override_settings(SIES_PERMISSION_RESOLVER=all_permissions)` so a
    test can prove that a *branch* check refuses something even when the
    permission check would have allowed it. Without it these tests could pass
    because the user lacked `branches.create`, which is not what they claim.
    """
    return {
        'branches.view', 'branches.create', 'branches.update',
        'academics.view', 'academics.create', 'academics.update', 'academics.delete',
    }


def no_permissions(user):
    return set()
