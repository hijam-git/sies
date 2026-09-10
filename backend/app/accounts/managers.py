"""Managers for the accounts app.

`UserManager` exists because `USERNAME_FIELD` is `phone`, not `username`:
Django's own `BaseUserManager` hard-codes the username argument, and
`createsuperuser` calls `create_superuser(**{USERNAME_FIELD: …})`. Both have to
agree, and both have to canonicalise the number before it is stored — otherwise
`createsuperuser` writes `+8801712345678` and the login screen, which normalises,
can never match it again.
"""

from django.contrib.auth.models import BaseUserManager
from django.core.exceptions import ValidationError
from django.db import models

from .phone import INVALID_PHONE_MESSAGE, normalize_bd_phone


class UserQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def for_branch(self, branch):
        """Users this request may see. Mirrors `core.managers.for_branch`.

        User is a global model — a person is one person, and their phone is
        unique across the platform (docs/03 §1) — so it does not inherit
        `BranchScopedManager`. But the *list endpoint* still has to be scoped, or
        a principal could enumerate every account on the platform. The rule is
        the same one, written here because the base class does not apply.

        Platform admins (branch NULL) are excluded from a single branch's list:
        they do not belong to that institution and showing them there invites a
        principal to try editing one.
        """
        from core.middleware import ALL_BRANCHES

        if branch is None:
            return self.none()
        if branch == ALL_BRANCHES:
            return self
        return self.filter(branch=branch)


class UserManager(BaseUserManager.from_queryset(UserQuerySet)):
    """Creates users keyed on a canonical BD mobile number."""

    use_in_migrations = True

    def _create_user(self, phone, password, **extra_fields):
        canonical = normalize_bd_phone(phone)
        if not canonical:
            # ValidationError rather than ValueError: this is reached from
            # `createsuperuser`, from `create_admin`, and from the API, and only
            # the last of those wants a traceback suppressed. DRF turns it into
            # a 400 with the field named; the shell prints the sentence.
            raise ValidationError({'phone': INVALID_PHONE_MESSAGE})

        user = self.model(phone=canonical, **extra_fields)
        # set_password hashes; assigning to .password would store the plaintext,
        # and nothing downstream would notice until a login failed.
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, phone, password=None, **extra_fields):
        """A normal account. Staff/superuser flags default off."""
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(phone, password, **extra_fields)

    def create_superuser(self, phone, password=None, **extra_fields):
        """The platform operator's own account.

        `branch` stays NULL by default and that is the meaning of the field: a
        NULL branch is the platform admin who sees every institution
        (docs/03 §1). A superuser pinned to one branch would be scoped to it by
        the middleware, which is almost never what someone typing
        `createsuperuser` wants.
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('user_type', 'platform_admin')
        # An account created at the console is not asked to change its password
        # on first login; the person who set it is the person who will use it.
        extra_fields.setdefault('must_change_password', False)

        if extra_fields['is_staff'] is not True:
            raise ValueError('A superuser must have is_staff=True.')
        if extra_fields['is_superuser'] is not True:
            raise ValueError('A superuser must have is_superuser=True.')

        return self._create_user(phone, password, **extra_fields)

    def get_by_natural_key(self, username):
        """Log in by whichever form of the number was typed.

        `authenticate()` reaches here with the raw string. Normalising it means
        `+8801712345678`, `8801712345678` and `01712-345678` all resolve to the
        one row, which is the whole point of storing a canonical phone.
        """
        return self.get(**{self.model.USERNAME_FIELD: normalize_bd_phone(username) or username})
