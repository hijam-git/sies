"""Business logic for accounts, and the one function that writes the audit trail.

`log_activity` is called from **services and views, never from a signal**. A
signal fires during `loaddata` and during test fixture setup, so an audit trail
written from one records events that never happened, attributed to nobody
(CLAUDE.md §4.3).
"""

import logging

from django.contrib.auth import authenticate
from django.db import transaction
from rest_framework.exceptions import APIException
from rest_framework import status

from core.middleware import ALL_BRANCHES, get_branch

from .models import ActivityAction, ActivityLog, User
from .permissions import clean_permissions, effective_permissions
from .phone import normalize_bd_phone

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Error codes the SPA maps to sentences — docs/WORKLOG F15. `lib/apiErrors.ts`
# switches on these exact strings, so adding one here means adding its two
# translations there. They are constants rather than literals at the raise site
# so a typo is an ImportError instead of a generic message in production.
# ─────────────────────────────────────────────────────────────────────────────
CODE_INVALID_PHONE = 'invalid_phone'
CODE_INVALID_CREDENTIALS = 'invalid_credentials'
CODE_ACCOUNT_INACTIVE = 'account_inactive'
CODE_PERMISSION_DENIED = 'permission_denied'
CODE_NOT_FOUND = 'not_found'
CODE_OUT_OF_SCOPE = 'out_of_scope'
CODE_DUPLICATE = 'duplicate'
CODE_PROTECTED_REFERENCE = 'protected_reference'


class CodedError(APIException):
    """A failure that names its own SPA-facing code.

    Deliberately not a DRF `ValidationError`: that class runs its detail through
    `as_serializer_error`, which wraps every value in a list — so the same error
    would reach the SPA as a string from one place and as a one-element list from
    another. `core.exception_handlers` reads `default_code` off the exception, so
    setting it per subclass is all that is needed for the code to survive.
    """

    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, detail, code, status_code=None):
        if status_code is not None:
            self.status_code = status_code
        super().__init__(detail)
        # `default_code` is what the exception handler reads; `self.code` alone
        # would be dropped.
        self.default_code = code
        self.detail_code = code


class InvalidPhone(CodedError):
    def __init__(self, detail='Enter an 11-digit mobile number, e.g. 01712345678.'):
        super().__init__(detail, CODE_INVALID_PHONE)


class InvalidCredentials(CodedError):
    """Deliberately does not say which half was wrong.

    Telling a stranger that the phone exists but the password does not is telling
    them half the answer, and the half that is worth having.
    """

    status_code = status.HTTP_401_UNAUTHORIZED

    def __init__(self, detail='This phone number and password do not match an account.'):
        super().__init__(detail, CODE_INVALID_CREDENTIALS,
                         status_code=status.HTTP_401_UNAUTHORIZED)


class AccountInactive(CodedError):
    status_code = status.HTTP_403_FORBIDDEN

    def __init__(self, detail="This account has been switched off. Ask your institution's admin."):
        super().__init__(detail, CODE_ACCOUNT_INACTIVE,
                         status_code=status.HTTP_403_FORBIDDEN)


class OutOfScope(CodedError):
    """A row that exists but is not this user's to touch — docs/02 §2.4.

    Distinct from `not_found`, and only for the *assignment* gate: a teacher
    reaching a class that is not theirs is told to ask the admin, because the
    class plainly exists and pretending otherwise would just make them retry. A
    wrong-*institution* row still answers 404 (CLAUDE.md §5).
    """

    status_code = status.HTTP_403_FORBIDDEN

    def __init__(self, detail='This is not one of yours. Ask the admin to assign it to you.'):
        super().__init__(detail, CODE_OUT_OF_SCOPE, status_code=status.HTTP_403_FORBIDDEN)


class Duplicate(CodedError):
    def __init__(self, detail='Something with this name or number already exists.'):
        super().__init__(detail, CODE_DUPLICATE)


class ProtectedReference(CodedError):
    def __init__(self, detail=('Other records point at this one, so it cannot be deleted. '
                               'Switch it off instead.')):
        super().__init__(detail, CODE_PROTECTED_REFERENCE)


# ─────────────────────────────────────────────────────────────────────────────
# The audit trail
# ─────────────────────────────────────────────────────────────────────────────

def client_ip(request):
    """The caller's address, trusting the proxy we actually run behind.

    Traefik is the only exposed port (CLAUDE.md §1), so `X-Forwarded-For`'s FIRST
    entry is the client and everything after it is our own hop. Reading the last
    entry — the usual mistake — would record Traefik's address for every request
    and make the column useless.
    """
    if request is None:
        return None
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip() or None
    return request.META.get('REMOTE_ADDR') or None


def _branch_for_log(request, user, branch):
    """Which institution this event belongs to, or None for a platform event."""
    if branch is not None:
        return None if branch == ALL_BRANCHES else branch

    if request is not None:
        resolved = get_branch(request)
        if resolved is not None and resolved != ALL_BRANCHES:
            # A raw `?branch=` id is a string; the FK wants an object or an id,
            # and only an id can be assigned to `branch_id`. Anything that is not
            # a Branch instance is handled by the caller passing one.
            if not isinstance(resolved, str):
                return resolved

    return getattr(user, 'branch', None)


def log_activity(*, action, user=None, request=None, branch=None, obj=None,
                 model=None, object_id=None, object_label=None,
                 summary='', summary_bn='', before=None, after=None,
                 user_label=None, atomic=True):
    """Write one ActivityLog row. Returns it, or None if the write failed.

    **This must never break the operation it records.** Two modes, and the caller
    picks by what it is recording:

    * `atomic=True` (default) — the write joins the caller's transaction. Correct
      for money: a payment whose log entry could not be written is a payment that
      happened with no record of who took it, and rolling both back is the right
      answer.
    * `atomic=False` — failures are swallowed to the error log. Correct for
      everything else, and for logins in particular: nobody should be unable to
      sign in because the audit table is full.

    Called from services and views. Never from a signal.
    """
    if obj is not None:
        model = model or obj.__class__.__name__
        object_id = object_id if object_id is not None else obj.pk
        object_label = object_label or str(obj)

    resolved_user = user if user is not None and getattr(user, 'is_authenticated', False) else None

    entry = ActivityLog(
        user=resolved_user,
        user_label=(user_label
                    or (f'{resolved_user.name} ({resolved_user.phone})' if resolved_user else '')),
        branch=_branch_for_log(request, resolved_user, branch),
        action=action,
        model=model or '',
        object_id='' if object_id is None else str(object_id),
        object_label=(object_label or '')[:200],
        summary=summary[:255],
        summary_bn=summary_bn[:255],
        before=before,
        after=after,
        ip=client_ip(request),
        user_agent=(request.META.get('HTTP_USER_AGENT', '')[:255] if request is not None else ''),
    )

    if atomic:
        entry.save()
        return entry

    try:
        entry.save()
        return entry
    except Exception:
        # Swallowed on purpose, and loudly: the log line is how a broken audit
        # table gets noticed, and refusing the login instead would take the whole
        # institution offline for a reporting problem.
        logger.exception('Could not write ActivityLog (%s %s)', action, model)
        return None


class ActivityLogMixin:
    """Ordinary CRUD, logged. Mix into a `BranchScopedViewSet`.

        class StudentViewSet(ActivityLogMixin, BranchScopedViewSet):
            activity_model = 'Student'

    Covers create / update / delete only. Anything that moves money or spans two
    models does not go through `perform_*` at all — it goes through a service,
    which calls `log_activity` itself, inside the same transaction (CLAUDE.md
    §4.3). This mixin exists so the boring three-quarters of the API does not
    each hand-roll the same three calls.
    """

    #: Overridden when the class name is not what an admin would recognise.
    activity_model = None

    def _activity_model_name(self):
        if self.activity_model:
            return self.activity_model
        queryset = getattr(self, 'queryset', None)
        return queryset.model.__name__ if queryset is not None else ''

    def save_new(self, serializer):
        """How a new row is written. Overridden where the base stamping is wrong.

        A hook rather than an override of `perform_create` itself, because a
        viewset that needed different stamping — `User` has no `created_by` for
        `BranchScopedMixin` to set — would otherwise have to shadow
        `perform_create` and silently lose the logging below.
        """
        super().perform_create(serializer)

    def perform_create(self, serializer):
        self.save_new(serializer)
        log_activity(
            action=ActivityAction.CREATE,
            user=self.request.user,
            request=self.request,
            obj=serializer.instance,
            model=self._activity_model_name(),
            summary=f'Created {self._activity_model_name()} {serializer.instance}',
            summary_bn=f'{self._activity_model_name()} তৈরি করা হয়েছে',
            after=_serialized_snapshot(serializer),
            atomic=False,
        )

    def perform_update(self, serializer):
        # Read before the write, or `before` and `after` are the same thing —
        # the instance is mutated in place by `serializer.save()`.
        before = _instance_snapshot(serializer.instance, serializer)
        super().perform_update(serializer)
        log_activity(
            action=ActivityAction.UPDATE,
            user=self.request.user,
            request=self.request,
            obj=serializer.instance,
            model=self._activity_model_name(),
            summary=f'Updated {self._activity_model_name()} {serializer.instance}',
            summary_bn=f'{self._activity_model_name()} হালনাগাদ করা হয়েছে',
            before=before,
            after=_serialized_snapshot(serializer),
            atomic=False,
        )

    def perform_destroy(self, instance):
        snapshot = _instance_snapshot(instance, self.get_serializer(instance))
        label = str(instance)
        pk = instance.pk
        super().perform_destroy(instance)
        log_activity(
            action=ActivityAction.DELETE,
            user=self.request.user,
            request=self.request,
            model=self._activity_model_name(),
            object_id=pk,
            object_label=label,
            summary=f'Deleted {self._activity_model_name()} {label}',
            summary_bn=f'{self._activity_model_name()} মুছে ফেলা হয়েছে',
            before=snapshot,
            atomic=False,
        )


def _serialized_snapshot(serializer):
    """A JSON-safe copy of what the serializer represents, minus secrets."""
    try:
        return _redact(dict(serializer.data))
    except Exception:
        # A serializer whose `.data` raises (a broken SerializerMethodField, a
        # deleted relation) must not take the write down with it.
        return None


def _instance_snapshot(instance, serializer):
    try:
        return _redact(dict(serializer.__class__(instance).data))
    except Exception:
        return None


_SECRET_FIELDS = {'password', 'new_password', 'current_password', 'token',
                  'access', 'refresh'}


def _redact(data):
    """Never write a credential into a table people are meant to read."""
    return {k: v for k, v in data.items() if k not in _SECRET_FIELDS}


# ─────────────────────────────────────────────────────────────────────────────
# Authentication
# ─────────────────────────────────────────────────────────────────────────────

def login_user(*, phone, password, request=None):
    """Authenticate by phone + password. Returns the User, or raises a coded error.

    Every outcome is logged, success and failure alike. A failed attempt is the
    only signal this system has that someone is guessing a counter clerk's
    password, and it is worthless unless the number that was tried is recorded —
    which is why `user_label` carries the raw phone even when no account matches.

    Not wrapped in a transaction: nothing here writes except the log, and a login
    that failed must still leave its trace behind.
    """
    canonical = normalize_bd_phone(phone)
    if not canonical:
        _log_failed_login(phone, 'Invalid phone format', 'ভুল ফরম্যাটের নম্বর', request)
        raise InvalidPhone()

    # `authenticate()` reaches the manager's `get_by_natural_key`, which
    # normalises again — harmless, and it keeps the Django admin login honest too.
    #
    # ModelBackend refuses an inactive user by returning None, which would report
    # "wrong password" to someone whose account was merely switched off. So the
    # row is looked up first and the inactive case answered on its own terms.
    existing = User.objects.filter(phone=canonical).first()
    if existing is not None and not existing.is_active:
        _log_failed_login(canonical, 'Account is inactive', 'অ্যাকাউন্ট বন্ধ আছে',
                          request, user_label=f'{existing.name} ({existing.phone})')
        raise AccountInactive()

    user = authenticate(request=request, phone=canonical, password=password)
    if user is None:
        _log_failed_login(canonical, 'Wrong phone or password', 'ভুল নম্বর বা পাসওয়ার্ড', request)
        raise InvalidCredentials()

    ip = client_ip(request)
    if ip:
        # `update_fields` so a concurrent permission change on the same row is
        # not clobbered by a login writing the whole object back.
        user.last_login_ip = ip
        user.save(update_fields=['last_login_ip'])

    log_activity(
        action=ActivityAction.LOGIN,
        user=user,
        request=request,
        summary='Signed in',
        summary_bn='সাইন ইন করেছেন',
        atomic=False,
    )
    return user


def _log_failed_login(phone_attempted, summary, summary_bn, request, user_label=None):
    log_activity(
        action=ActivityAction.LOGIN_FAILED,
        user=None,
        request=request,
        # No user row, so the number that was typed is the only identity there
        # is. Truncated to the column, and never the password.
        user_label=user_label or str(phone_attempted)[:160],
        summary=summary,
        summary_bn=summary_bn,
        after={'phone': str(phone_attempted)[:32]},
        atomic=False,
    )


@transaction.atomic
def change_password(*, user, new_password, request=None):
    """Set a new password and clear the forced-change flag.

    In a transaction because the flag and the hash must move together: a crash
    between them leaves an account that either keeps demanding a change it
    already made, or stops demanding one it never did.
    """
    user.set_password(new_password)
    user.must_change_password = False
    user.save(update_fields=['password', 'must_change_password', 'updated_at'])

    log_activity(
        action=ActivityAction.UPDATE,
        user=user,
        request=request,
        obj=user,
        model='User',
        summary='Changed their password',
        summary_bn='পাসওয়ার্ড পরিবর্তন করেছেন',
        atomic=False,
    )
    return user


@transaction.atomic
def set_user_permissions(*, target, permissions, actor, request=None):
    """Replace a user's explicit permission list. docs/02 §2.3.

    Atomic with its log entry, unlike most non-money writes: "who gave the office
    assistant access to the accounts" is precisely the question this table exists
    to answer (docs/02 §2.3), so a permission change with no audit row is not an
    acceptable outcome — better that the change fails and is retried.

    An empty list is meaningful and is honoured: it puts the person back on their
    role's preset, which is how the UI's "reset to role" works.
    """
    before = list(target.permissions or [])
    cleaned = clean_permissions(permissions)

    target.permissions = cleaned
    target.save(update_fields=['permissions', 'updated_at'])

    log_activity(
        action=ActivityAction.UPDATE,
        user=actor,
        request=request,
        obj=target,
        model='User',
        summary=f'Changed permissions for {target.name}',
        summary_bn=f'{target.name}-এর অনুমতি পরিবর্তন করা হয়েছে',
        before={'permissions': before},
        after={'permissions': cleaned},
        atomic=True,
    )
    return target


def user_payload(user):
    """The `user` object every auth endpoint returns.

    The effective permissions are computed here rather than being read off the
    column, so the SPA is told what is actually ENFORCED — preset fallback,
    stale-string filtering and the inactive rule included. A client that read
    `user.permissions` directly would show an empty checkbox screen for everyone
    still on their role's preset.
    """
    return {
        'id': user.id,
        'phone': user.phone,
        'name': user.name,
        'name_bn': user.name_bn,
        'email': user.email,
        'user_type': user.user_type,
        'branch': user.branch_id,
        'branch_name': user.branch.name if user.branch_id else None,
        'role': user.role_id,
        'role_name': user.role.name if user.role_id else None,
        'permissions': sorted(effective_permissions(user)),
        'language': user.language,
        'photo': user.photo.url if user.photo else None,
        'is_platform_admin': user.is_platform_admin,
        'is_superuser': user.is_superuser,
        'must_change_password': user.must_change_password,
    }
