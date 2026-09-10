"""Branch-scope resolution — the rules in docs/01 §5.2 and docs/02 §3.

These are the tests for the one decision the whole data model rests on: which
institution a request is about. Everything else in the project trusts
`request.branch`, so each rule is asserted separately, including the two negative
ones — a branch user's `?branch=` being ignored rather than honoured, and an
anonymous request costing no query.

`user.branch` and the Branch model belong to Phase 1, so the users here are
stand-ins carrying only the attribute the middleware reads. That is deliberate
and not a shortcut: the middleware's contract is exactly "an authenticated user
object with an optional `branch`", and testing it against a stub is what proves
it does not depend on anything more.
"""

from django.test import RequestFactory, SimpleTestCase

from core.middleware import (
    ALL_BRANCHES,
    BranchScopeMiddleware,
    get_branch,
    is_all_branches,
    resolve_branch,
)


class StubUser:
    """The minimum the middleware reads: is_authenticated, and maybe branch."""

    is_authenticated = True

    def __init__(self, branch=None):
        self.branch = branch


class StubAnonymousUser:
    is_authenticated = False


class StubBranch:
    """Stands in for branches.Branch, which Phase 1 creates."""

    def __init__(self, pk, name):
        self.pk = pk
        self.name = name

    def __repr__(self):
        return f'<StubBranch {self.name}>'


def build_request(query_string='', user=None):
    request = RequestFactory().get(f'/api/students/?{query_string}')
    if user is not None:
        request.user = user
    return request


def run_middleware(request):
    """Push the request through the middleware and return the resolved branch."""
    called = {}

    def get_response(req):
        called['branch'] = get_branch(req)
        return 'response'

    BranchScopeMiddleware(get_response)(request)
    return called['branch']


class BranchScopeMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.dhaka = StubBranch(1, 'Dhaka')

    # ── A branch user is pinned to their own branch ─────────────────────────

    def test_branch_user_gets_their_own_branch(self):
        branch = run_middleware(build_request(user=StubUser(branch=self.dhaka)))
        self.assertIs(branch, self.dhaka)

    def test_branch_query_param_is_ignored_for_a_branch_user(self):
        """Ignored, not rejected.

        A platform admin's URL pasted into a principal's browser must degrade to
        their own branch rather than answer 400 — a copied link is a support
        call, not an attack, and the scoping is what keeps it safe either way.
        """
        branch = run_middleware(
            build_request('branch=99', user=StubUser(branch=self.dhaka))
        )
        self.assertIs(branch, self.dhaka)

    def test_branch_query_param_naming_their_own_branch_is_also_ignored(self):
        # Same path, no special case: the parameter is never read for this user.
        branch = run_middleware(
            build_request('branch=1', user=StubUser(branch=self.dhaka))
        )
        self.assertIs(branch, self.dhaka)

    # ── A platform admin has no branch of their own ─────────────────────────

    def test_platform_admin_without_a_filter_sees_all_branches(self):
        branch = run_middleware(build_request(user=StubUser(branch=None)))
        self.assertEqual(branch, ALL_BRANCHES)
        self.assertTrue(is_all_branches(branch))

    def test_platform_admin_may_filter_with_the_query_param(self):
        branch = run_middleware(build_request('branch=7', user=StubUser(branch=None)))
        self.assertEqual(branch, '7')

    def test_platform_admin_empty_filter_is_not_a_filter(self):
        """`?branch=` with nothing after it means "no filter", not "branch ''".

        A blank value is what the SPA sends when its institution picker is reset,
        and filtering on an empty string would return nothing at all.
        """
        branch = run_middleware(build_request('branch=', user=StubUser(branch=None)))
        self.assertEqual(branch, ALL_BRANCHES)

    def test_platform_admin_filter_is_whitespace_stripped(self):
        branch = run_middleware(build_request('branch=%20%20', user=StubUser(branch=None)))
        self.assertEqual(branch, ALL_BRANCHES)

    # ── Anonymous ───────────────────────────────────────────────────────────

    def test_anonymous_request_has_no_branch(self):
        branch = run_middleware(build_request(user=StubAnonymousUser()))
        self.assertIsNone(branch)

    def test_anonymous_request_with_a_branch_param_still_has_no_branch(self):
        """Not authenticated is not a scope, whatever the URL asks for."""
        branch = run_middleware(build_request('branch=1', user=StubAnonymousUser()))
        self.assertIsNone(branch)

    def test_request_without_a_user_attribute_has_no_branch(self):
        """A view reached before AuthenticationMiddleware ran must not crash."""
        branch = run_middleware(build_request())
        self.assertIsNone(branch)

    def test_anonymous_resolution_makes_no_database_query(self):
        """No query for a request that is not logged in.

        The assertion is the base class. SimpleTestCase turns any database access
        into DatabaseOperationForbidden, so resolving to completion here IS the
        proof — and it covers every future addition to resolve_branch, which an
        explicit query count around this one call would not.

        It matters because unauthenticated traffic is the traffic there is most
        of: the SPA's own assets and every probe reach middleware, and a lookup
        per request for a scope nobody will read is a query per visitor.
        """
        self.assertIsNone(run_middleware(build_request(user=StubAnonymousUser())))

    # ── Laziness ────────────────────────────────────────────────────────────

    def test_branch_is_not_resolved_until_it_is_read(self):
        """The value has to be lazy, or JWT requests scope to nobody.

        DRF authenticates inside the view, long after every middleware has run.
        Resolving eagerly here would read AnonymousUser on every API request and
        filter the whole API to None — so this test is guarding the reason for
        the design, not an optimisation.
        """
        resolved = []

        class WatchedUser(StubUser):
            @property
            def branch(self):
                resolved.append(True)
                return None

            @branch.setter
            def branch(self, value):
                pass

        request = build_request(user=WatchedUser())
        BranchScopeMiddleware(lambda req: 'response')(request)
        self.assertEqual(resolved, [], 'branch was resolved before it was read')

        get_branch(request)
        self.assertEqual(len(resolved), 1)

    def test_get_branch_returns_a_real_none_not_a_lazy_proxy(self):
        """`request.branch is None` is False on the proxy; get_branch fixes that.

        Core code does identity checks against None, so this is the reason
        get_branch exists rather than callers touching request.branch directly.
        """
        request = build_request(user=StubAnonymousUser())
        BranchScopeMiddleware(lambda req: 'response')(request)

        self.assertIsNotNone(request.branch)
        self.assertIsNone(get_branch(request))

    def test_get_branch_passes_through_an_unwrapped_value(self):
        """A test or a management command may set request.branch directly."""
        request = build_request()
        request.branch = self.dhaka
        self.assertIs(get_branch(request), self.dhaka)


class ResolveBranchTests(SimpleTestCase):
    """resolve_branch on its own, for callers that are not requests-in-flight."""

    def test_missing_user_attribute(self):
        self.assertIsNone(resolve_branch(RequestFactory().get('/api/')))

    def test_sentinel_is_not_a_falsy_value(self):
        """ALL_BRANCHES must never be confused with "no branch".

        They are opposite ends of the access range — every institution, and none
        — so a truthiness check that treated them alike would hand one
        institution's data to an unauthenticated caller.
        """
        self.assertTrue(bool(ALL_BRANCHES))
        self.assertFalse(is_all_branches(None))
