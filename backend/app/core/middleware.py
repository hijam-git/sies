"""Branch scoping — the middleware half.

`request.branch` is the single answer to "which institution is this request
about", and every branch-scoped queryset in the project is filtered by it
(docs/01 §5.2, docs/02 §3). The rules:

    user.branch is set     → that branch, and ?branch= is IGNORED. Not an
                             error — ignored, so a platform admin's URL pasted
                             into a branch user's browser degrades to their own
                             branch instead of a 400 nobody can act on.
    user.branch is NULL    → the platform admin: ?branch=<id> if given, else the
                             sentinel ALL_BRANCHES, meaning every institution.
    not authenticated      → None, and no database query.

Note what is NOT here: nothing widens the scope beyond the user's own branch
except a NULL branch. BranchAccess (docs/03 §1, a multi-branch grant) is V2; when
it arrives it widens `resolve_branch` and nothing else.
"""

from django.utils.functional import LazyObject, SimpleLazyObject, empty

# A platform admin who has not filtered sees everything. A string sentinel rather
# than None so that "no branch at all" and "every branch" can never be confused
# by a falsy check — they are the two ends of the permission range, and mixing
# them up leaks one institution's data to another.
ALL_BRANCHES = 'ALL'


def resolve_branch(request):
    """The branch this request is about. See the module docstring for the rules."""
    user = getattr(request, 'user', None)

    # No user, or an anonymous one: no scope, and no query. `is_authenticated` on
    # AnonymousUser is a constant, so this returns without touching the database.
    if user is None or not user.is_authenticated:
        return None

    # `branch` only exists once the accounts app defines it (Phase 1). Until then
    # every authenticated user reads as a platform admin, which is true: the only
    # accounts that exist in Phase 0 are superusers.
    branch = getattr(user, 'branch', None)
    if branch is not None:
        return branch

    requested = request.GET.get('branch', '').strip()
    if requested:
        # Not validated here. Middleware runs before any permission check, so
        # raising on a bad id would answer an unauthenticated-in-DRF-terms
        # request with a database lookup. An id that matches nothing simply
        # filters to nothing, which is the correct answer to "show me branch
        # 9999" from someone allowed to ask.
        return requested

    return ALL_BRANCHES


def get_branch(request):
    """`request.branch` with the laziness stripped off.

    `request.branch` is a SimpleLazyObject, so `request.branch is None` is False
    even when the branch is None — the proxy is not the thing. Core code that
    needs an identity check goes through here; everything else can use
    `request.branch` directly, where `==` and attribute access behave normally.
    """
    branch = getattr(request, 'branch', None)
    if isinstance(branch, LazyObject):
        if branch._wrapped is empty:
            branch._setup()
        return branch._wrapped
    return branch


def is_all_branches(branch):
    """True for the platform admin's unfiltered scope."""
    return branch == ALL_BRANCHES


class BranchScopeMiddleware:
    """Attaches `request.branch`, lazily.

    Lazily, because of where authentication actually happens. Django's
    AuthenticationMiddleware resolves a SESSION user, but the SPA authenticates
    with JWT and DRF does that inside the view — after every middleware has run.
    Resolving eagerly here would read AnonymousUser for every API request and
    scope the whole API to None.

    Deferring the work to first access also satisfies the other requirement: an
    unauthenticated request that never touches `request.branch` performs no query
    and no work at all.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.branch = SimpleLazyObject(lambda: resolve_branch(request))
        return self.get_response(request)
