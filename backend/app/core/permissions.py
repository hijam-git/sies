"""Permission checking, without the catalogue.

The permission *catalogue* — which resources exist, which actions each has, and
what each role's preset grants — lives in the accounts app (Phase 1), because it
is domain knowledge and the SPA fetches it to render its checkboxes. This module
holds only the mechanism, so `core` keeps depending on nothing (docs/06 §2).

The rule it enforces, copied from awliaa's accounts/permissions.py because it is
the one worth copying: **an explicitly saved list wins; an empty list falls back
to the role preset.** An account whose list was never set keeps working, and an
owner who ticks "orders but not prices" gets exactly that. Note that an admin who
deliberately grants nothing still gets the preset back — the safer failure, since
someone who can see too little files a support ticket while someone who can see
too much never says a word. "No access at all" is deactivation.

Usage:

    class PaymentViewSet(BranchScopedViewSet):
        permission_classes = [IsAuthenticated, HasPermission('fees.collect')]
"""

from django.conf import settings
from django.utils.module_loading import import_string
from rest_framework.permissions import BasePermission

# Which callable answers "what may this user do". Overridable so a test can pin
# a fixed set without building a User, a Role and a permission catalogue first.
RESOLVER_SETTING = 'SIES_PERMISSION_RESOLVER'
DEFAULT_RESOLVER = 'core.permissions.default_permission_resolver'


def default_permission_resolver(user):
    """Every "resource.action" string this user actually holds.

    Reads `user.permissions` and `user.role` by attribute rather than importing
    the accounts models, so core does not depend on an app that depends on core.
    Both attributes are absent in Phase 0 and the function still answers.
    """
    explicit = getattr(user, 'permissions', None) or []
    if explicit:
        return {p for p in explicit if isinstance(p, str)}

    # Nothing explicit: fall back to the role's preset. Role.permission_matrix is
    # {"fees": ["view", "collect"], …} (docs/03 §1) — flattened here into the
    # same "resource.action" strings so callers only ever see one shape.
    role = getattr(user, 'role', None)
    matrix = getattr(role, 'permission_matrix', None) or {}
    if not isinstance(matrix, dict):
        return set()

    return {
        f'{resource}.{action}'
        for resource, actions in matrix.items()
        if isinstance(actions, (list, tuple, set))
        for action in actions
        if isinstance(action, str)
    }


def effective_permissions(user):
    """The resolver's answer for *user*, empty for anyone not logged in."""
    if user is None or not user.is_authenticated:
        return set()

    resolver = getattr(settings, RESOLVER_SETTING, DEFAULT_RESOLVER)
    if isinstance(resolver, str):
        resolver = import_string(resolver)
    return set(resolver(user))


def user_has_permission(user, permission):
    """True if *user* holds "resource.action", or is a superuser."""
    if user is None or not user.is_authenticated:
        return False

    # The superuser bypass is Django's own contract, and `create_admin` uses it
    # to make the first account on a fresh install — which necessarily exists
    # before any role or catalogue does.
    if getattr(user, 'is_superuser', False):
        return True

    return permission in effective_permissions(user)


def HasPermission(permission):  # noqa: N802 — a factory that returns a class
    """A DRF permission class demanding one "resource.action" string.

    A factory rather than a `required_permission` attribute on the view, so the
    requirement is visible in the `permission_classes` line itself and cannot be
    lost when a subclass overrides an attribute it did not know about.
    """

    class _HasPermission(BasePermission):
        message = f'You do not have the "{permission}" permission.'

        def has_permission(self, request, view):
            return user_has_permission(request.user, permission)

        def has_object_permission(self, request, view, obj):
            # Object-level access is branch scoping's job, not this class's:
            # BranchScopedViewSet already made another institution's rows
            # invisible, so a 404 answers before this is ever consulted.
            return True

    _HasPermission.__name__ = f'HasPermission_{permission.replace(".", "_")}'
    return _HasPermission
