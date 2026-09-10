"""The viewset every branch-scoped module inherits (CLAUDE.md §5).

Two things happen here and nowhere else: reads are filtered to
`request.branch`, and writes are stamped with it. Both live in one class so the
rule is auditable by reading one file rather than by trusting eleven apps to have
remembered it.
"""

from rest_framework import viewsets
from rest_framework.exceptions import ValidationError

from .middleware import ALL_BRANCHES, get_branch


class BranchScopedMixin:
    """Read filtering and write stamping. Mix into any generic view."""

    def get_queryset(self):
        """`super()`'s queryset, narrowed to this request's branch.

        A row from another branch simply is not in the queryset, so retrieving it
        raises Http404 from `get_object()`. That is the required behaviour and
        not an accident of implementation: 403 would confirm the object exists,
        which is exactly what a probe is looking for (CLAUDE.md §5).
        """
        return super().get_queryset().for_branch(get_branch(self.request))

    def perform_create(self, serializer):
        """Stamp the branch server-side.

        `branch` is passed as a keyword here, which overrides anything the client
        sent — and serializers in this project do not expose the field at all, so
        there are two independent reasons a `branch` in a POST body does nothing.
        That is the point: without it, a branch user could write INTO another
        institution even though they could never read it back.

        A platform admin posting without `?branch=` has not said WHICH
        institution to create the row in, and "create this in every institution"
        has no meaning. Left alone that reaches the FK as the string 'ALL' and
        fails as a database type error — a 500 with a traceback, for what is
        really a missing parameter. So it is caught here and answered as the 400
        it is, in a sentence the caller can act on.
        """
        branch = get_branch(self.request)
        if branch is None or branch == ALL_BRANCHES:
            raise ValidationError({
                'branch': (
                    'Choose an institution before creating this. '
                    'Add ?branch=<id> to the request.'
                ),
            })
        serializer.save(branch=branch, created_by=self.request.user)

    def perform_update(self, serializer):
        # branch is not re-stamped: moving a student between institutions is not
        # an edit, and silently allowing it through a PATCH would move their fee
        # history with them.
        serializer.save(updated_by=self.request.user)


class BranchScopedViewSet(BranchScopedMixin, viewsets.ModelViewSet):
    """The default base for a branch-scoped module's CRUD endpoints."""


class BranchScopedReadOnlyViewSet(BranchScopedMixin, viewsets.ReadOnlyModelViewSet):
    """Same scoping for lookups the API exposes but does not let anyone edit."""
