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

        A platform admin who DID pass `?branch=5` has `request.branch` as the
        string `'5'` — the middleware deliberately does not resolve it, because
        it runs before authentication and must not query (docs/01 §5.2). So it
        is saved as `branch_id`, which is what a raw key is, rather than as
        `branch`, which expects an instance. Getting this wrong is a 500 on
        every create a platform admin attempts, while a branch user's identical
        request succeeds — the two paths differ only in the type of this value,
        which is exactly the kind of bug that reaches production.
        """
        # Imported here, not at module scope: core is imported BY branches, and
        # the reverse at import time would be a cycle (docs/06 §2).
        from branches.models import Branch

        branch = get_branch(self.request)
        if branch is None or branch == ALL_BRANCHES:
            raise ValidationError({
                'branch': (
                    'Choose an institution before creating this. '
                    'Add ?branch=<id> to the request.'
                ),
            })

        if isinstance(branch, Branch):
            serializer.save(branch=branch, created_by=self.request.user)
            return

        # A raw id off the query string. Validate it here rather than letting
        # the FK reject it: an unknown institution is a 400 the caller can act
        # on, not an integrity error with a traceback.
        try:
            branch_id = int(branch)
        except (TypeError, ValueError):
            raise ValidationError({'branch': 'Not a valid institution id.'})

        if not Branch.objects.filter(pk=branch_id).exists():
            raise ValidationError({'branch': 'No institution with that id.'})

        serializer.save(branch_id=branch_id, created_by=self.request.user)

    def perform_update(self, serializer):
        # branch is not re-stamped: moving a student between institutions is not
        # an edit, and silently allowing it through a PATCH would move their fee
        # history with them.
        serializer.save(updated_by=self.request.user)


class BranchScopedViewSet(BranchScopedMixin, viewsets.ModelViewSet):
    """The default base for a branch-scoped module's CRUD endpoints."""


class BranchScopedReadOnlyViewSet(BranchScopedMixin, viewsets.ReadOnlyModelViewSet):
    """Same scoping for lookups the API exposes but does not let anyone edit."""
