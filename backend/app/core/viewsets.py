"""The viewset every branch-scoped module inherits (CLAUDE.md §5).

Two things happen here and nowhere else: reads are filtered to
`request.branch`, and writes are stamped with it. Both live in one class so the
rule is auditable by reading one file rather than by trusting eleven apps to have
remembered it.
"""

from rest_framework import viewsets
from rest_framework.exceptions import ValidationError

from .middleware import ALL_BRANCHES, get_branch


def writable_branch(request):
    """The branch a write lands in, as a real `Branch`, or a 400 saying why not.

    Three apps each grew their own copy of this and they did not agree. Two
    tested `hasattr(branch, 'pk')` and rejected a platform admin outright,
    because `resolve_branch` hands that user the RAW STRING from `?branch=5` —
    the middleware deliberately does not resolve it, since it runs before
    authentication and must not query (docs/01 §5.2). So "Add teacher" answered
    *"choose an institution"* to someone who had chosen one, while "Add student"
    worked, and the two code paths differed only in that check.

    `get_branch()` and not `request.branch`: the latter is a `SimpleLazyObject`
    and `is None` against it is False even when the branch is None
    (`CLAUDE.md` §5).
    """
    from branches.models import Branch

    branch = get_branch(request)
    if branch is None or branch == ALL_BRANCHES:
        raise ValidationError({
            'branch': ('Choose an institution before creating this. '
                       'Add ?branch=<id> to the request.'),
        })
    if isinstance(branch, Branch):
        return branch

    try:
        return Branch.objects.get(pk=int(branch))
    except (TypeError, ValueError):
        raise ValidationError({'branch': 'Not a valid institution id.'})
    except Branch.DoesNotExist:
        raise ValidationError({'branch': 'No institution with that id.'})


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

        `writable_branch()` above does the resolving and the refusing, so this
        method and every app's custom create action answer identically. They did
        not always: the copies that grew in three apps disagreed about a
        platform admin, and "Add teacher" refused someone that "Add student"
        accepted.
        """
        serializer.save(branch=writable_branch(self.request),
                        created_by=self.request.user)

    def perform_update(self, serializer):
        # branch is not re-stamped: moving a student between institutions is not
        # an edit, and silently allowing it through a PATCH would move their fee
        # history with them.
        serializer.save(updated_by=self.request.user)


class BranchScopedViewSet(BranchScopedMixin, viewsets.ModelViewSet):
    """The default base for a branch-scoped module's CRUD endpoints."""


class BranchScopedReadOnlyViewSet(BranchScopedMixin, viewsets.ReadOnlyModelViewSet):
    """Same scoping for lookups the API exposes but does not let anyone edit."""
