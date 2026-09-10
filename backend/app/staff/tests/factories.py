"""A small, fast fixture for this module (CLAUDE.md §4a).

One or two institutions and a handful of staff — enough to exercise every path in
`staff`, small enough to build in milliseconds. Nothing here loads `seed_demo`.
"""

from django.contrib.auth import get_user_model

from accounts.permissions import VALID_PERMISSIONS
from branches.models import InstitutionType
from branches.services import create_branch

from staff.services import create_employee, create_teacher


def make_branch(code='DHK', name='Dhaka Madrasah', **extra):
    """A seeded institution, created the way production creates one."""
    return create_branch(
        name=name,
        name_bn=extra.pop('name_bn', 'ঢাকা মাদ্রাসা'),
        code=code,
        institution_type=extra.pop('institution_type', InstitutionType.MADRASAH),
        **extra,
    )


def make_user(branch, phone='01711000001', user_type='principal', **extra):
    """An account holding every permission in the catalogue, unless told otherwise.

    Full permissions by default so that a refusal in these tests proves the
    *branch* or the *scope* refused it, and not that the account happened to lack
    `teachers.view`. A test about permissions passes its own list.
    """
    User = get_user_model()
    return User.objects.create_user(
        phone=phone,
        password='pass-phrase-1234',
        name=extra.pop('name', f'User {phone}'),
        branch=branch,
        user_type=user_type,
        permissions=extra.pop('permissions', sorted(VALID_PERMISSIONS)),
        **extra,
    )


def make_teacher(branch, name='Abdul Karim', **extra):
    return create_teacher(branch=branch, name=name, **extra)


def make_employee(branch, name='Rafiq Mia', **extra):
    return create_employee(branch=branch, name=name, **extra)
