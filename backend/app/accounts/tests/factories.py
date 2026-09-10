"""Small, fast fixtures for the accounts tests (CLAUDE.md §4a).

Plain functions, not `factory_boy`: this app needs two branches and a handful of
users, and adding a dependency to build them would be paying for machinery
nobody uses. `seed_demo` is for looking at the app by hand; tests build their own
data so that changing the demo set never breaks a test.
"""

import itertools

from accounts.models import ActivityAction, ActivityLog, Role, User
from accounts.permissions import preset_matrix

# Phone numbers have to be unique across the whole platform, so they are handed
# out from one counter rather than hard-coded per test — two tests that both
# wanted "01712345678" would pass alone and fail together.
_phone_counter = itertools.count(1)


def next_phone():
    """A distinct, valid BD mobile: 017 1000 0001, 017 1000 0002, …"""
    return f'0171{next(_phone_counter):07d}'


def make_branch(name='Dhaka Madrasah', code='DHK', **kwargs):
    """One institution. Imported lazily so this module loads without branches."""
    from branches.models import Branch

    defaults = {
        'name': name,
        'name_bn': kwargs.pop('name_bn', name),
        'code': code,
        'institution_type': kwargs.pop('institution_type', 'madrasah'),
    }
    defaults.update(kwargs)
    return Branch.objects.create(**defaults)


def make_role(name='Teacher', **kwargs):
    """A preset from the shipped catalogue, or a custom matrix via `matrix=`."""
    matrix = kwargs.pop('matrix', None)
    return Role.objects.create(
        name=name,
        name_bn=kwargs.pop('name_bn', ''),
        permission_matrix=matrix if matrix is not None else preset_matrix(name),
        is_system=kwargs.pop('is_system', False),
        **kwargs,
    )


def make_user(branch=None, phone=None, password='correct-horse-9', **kwargs):
    """A staff account. `branch=None` with the default user_type is a platform admin."""
    kwargs.setdefault('name', 'Test User')
    if branch is None:
        kwargs.setdefault('user_type', 'platform_admin')
    else:
        kwargs.setdefault('user_type', 'teacher')

    return User.objects.create_user(
        phone=phone or next_phone(),
        password=password,
        branch=branch,
        **kwargs,
    )


def make_platform_admin(phone=None, password='correct-horse-9', **kwargs):
    """Branch NULL and superuser — what `create_admin` produces."""
    kwargs.setdefault('name', 'Platform Admin')
    return User.objects.create_superuser(
        phone=phone or next_phone(),
        password=password,
        **kwargs,
    )


def make_activity(user=None, branch=None, action=ActivityAction.CREATE, **kwargs):
    """A log row written directly, for the read-side tests."""
    return ActivityLog.objects.create(
        user=user,
        user_label=kwargs.pop('user_label', str(user) if user else ''),
        branch=branch,
        action=action,
        **kwargs,
    )
