"""Branch scoping — the queryset half.

`BranchScopedModel` gives every branch-scoped model this manager, so the filter
is one method that can be read and audited in one place (docs/01 §5.1). A viewset
that needs the scope calls `.for_branch(request.branch)`; nothing reconstructs
the rule inline.
"""

from django.db import models

from .middleware import ALL_BRANCHES


class BranchScopedQuerySet(models.QuerySet):
    def for_branch(self, branch):
        """Rows this request may see.

        `branch` is whatever BranchScopeMiddleware resolved: a Branch, a branch
        id from ?branch=, the ALL_BRANCHES sentinel, or None.

        None returns nothing rather than everything. That is the whole point of
        the method: an unauthenticated request, or one whose scope could not be
        worked out, must not fall through to an unfiltered queryset. Failing
        closed here means a viewset that forgets its permission class still
        leaks nothing.
        """
        if branch is None:
            return self.none()

        # The platform admin, unfiltered (docs/01 §5.2). Compared with `==`
        # rather than `is`: the value arrives wrapped in a SimpleLazyObject when
        # it comes straight off the request.
        if branch == ALL_BRANCHES:
            return self

        # Accepts a Branch instance or a raw id — ?branch= yields a string, and
        # Django resolves both against the FK column.
        return self.filter(branch=branch)

    def active(self):
        """Soft-deleted rows excluded (CLAUDE.md §4.2).

        Only meaningful on the models that carry `is_active`; calling it on one
        that does not is a FieldError at the call site, which is the right place
        to find out.
        """
        return self.filter(is_active=True)


class BranchScopedManager(models.Manager.from_queryset(BranchScopedQuerySet)):
    """The default manager on every BranchScopedModel.

    It deliberately does NOT filter by default. A manager that hides rows unless
    asked breaks `dumpdata`, the Django admin, migrations and every management
    command, and — worse — makes an unfiltered read look safe. Scoping is
    explicit, at the one call site that knows the request.
    """
