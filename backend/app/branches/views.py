"""The branches API (CLAUDE.md §5).

`Branch` is **not** branch-scoped, so `BranchViewSet` does not inherit
`BranchScopedViewSet` — it is the one viewset in the project that has to write
its own scoping, and the rules it implements are:

    platform admin (user.branch is NULL)  → every institution; may create/update
    a branch user                         → their own institution, read-only

`Stream` and `Session` are ordinary branch-scoped modules and inherit
`BranchScopedViewSet`, which already applies `get_branch()` and the 404-not-403
rule for another institution's rows.
"""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response

from core.middleware import get_branch
from core.permissions import HasPermission
from core.viewsets import BranchScopedViewSet

from .models import Branch, Session, Stream
from .serializers import BranchSerializer, SessionSerializer, StreamSerializer
from .services import create_branch, set_current_session


def own_branch(user):
    """The branch this account belongs to, or None for the platform admin.

    Read off the user rather than off `request.branch`, because the two answer
    different questions. `request.branch` is *which institution is this request
    about* and honours `?branch=` for a platform admin; this is *which
    institution does this person belong to*, which `?branch=` must never change.
    Read by attribute so it also answers before the accounts app exists.
    """
    return getattr(user, 'branch', None)


class IsPlatformAdmin(BasePermission):
    """Only the operator of the platform — the account with no branch of its own.

    docs/08 D1: institutions are unrelated organisations, and creating or
    renaming one is the platform operator's job. A principal holding
    `branches.update` may still not edit another institution, and this is what
    says so.
    """

    message = (
        'Only a platform administrator may do this · '
        'শুধুমাত্র প্ল্যাটফর্ম অ্যাডমিন এটি করতে পারেন।'
    )

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated) and own_branch(request.user) is None


class BranchViewSet(mixins.ListModelMixin,
                    mixins.RetrieveModelMixin,
                    mixins.CreateModelMixin,
                    mixins.UpdateModelMixin,
                    viewsets.GenericViewSet):
    """Institutions.

    No `destroy`: the permission catalogue (docs/02 §2.1) gives `branches` only
    view/create/update, and deleting an institution is not an operation this
    system has — `BranchScopedModel.branch` is `PROTECT` and would refuse
    anyway. Closing one is `is_active = False`.
    """

    queryset = Branch.objects.all()
    serializer_class = BranchSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['institution_type', 'is_active', 'district']
    search_fields = ['name', 'name_bn', 'name_ar', 'code', 'district', 'thana']
    ordering_fields = ['name', 'code', 'created_at']

    def get_permissions(self):
        if self.action == 'create':
            # Creating an institution is the platform's act, not an
            # institution's.
            return [IsAuthenticated(), IsPlatformAdmin(), HasPermission('branches.create')()]
        if self.action in ('update', 'partial_update'):
            # **No `IsPlatformAdmin` here**, and `perform_update` draws the line
            # instead. `branches.update` is in the Principal preset and the
            # settings screen edits `fine_rule` and
            # `restrict_teachers_to_assigned_classes` through this endpoint, so
            # a blanket platform-admin check made an institution's own settings
            # unreachable for the one person they exist for. Editing *another*
            # institution stays impossible: `get_queryset()` returns only their
            # own, so the id answers 404 (CLAUDE.md §5).
            return [IsAuthenticated(), HasPermission('branches.update')()]
        return [IsAuthenticated(), HasPermission('branches.view')()]

    #: What an institution may not change about itself. Its identity is the
    #: platform's record of who its customer is (docs/08 D1) — a principal
    #: renaming their own madrasah renames it in the operator's list and on
    #: every receipt printed since. The settings below the identity are theirs.
    PLATFORM_ONLY_FIELDS = ('name', 'name_bn', 'name_ar', 'code',
                            'institution_type', 'is_active')

    def get_queryset(self):
        """Every institution for the platform admin; their own for anyone else.

        Note what is deliberately NOT done here: a platform admin's `?branch=`
        is ignored. The SPA appends it to *every* request (`lib/api.ts`
        `withBranch`), including this one — and this is the endpoint that
        populates the branch switcher, so honouring the filter would leave the
        switcher able to show only the branch already selected.

        `get_branch()` and not `request.branch`: the latter is a
        `SimpleLazyObject`, so an `is None` check against it is False even when
        the branch is None (CLAUDE.md §5).
        """
        branch = get_branch(self.request)

        if branch is None:
            # Unresolvable scope fails closed, exactly as
            # BranchScopedQuerySet.for_branch does.
            return Branch.objects.none()

        # A Branch instance means a branch user: the middleware resolved it from
        # `user.branch` and ignored any `?branch=`. A string — ALL_BRANCHES, or
        # an id from `?branch=` — means the platform admin.
        if isinstance(branch, Branch):
            return Branch.objects.filter(pk=branch.pk)

        return super().get_queryset()

    def perform_create(self, serializer):
        """Create through the service, so the institution arrives seeded.

        docs/08 D1 consequence 2 — one screen, one transaction. Calling
        `serializer.save()` here instead would produce a branch with no streams,
        which cannot take an admission.
        """
        serializer.instance = create_branch(
            created_by=self.request.user, **serializer.validated_data,
        )

    def perform_update(self, serializer):
        # An institution runs its own settings; the platform owns its identity.
        if own_branch(self.request.user) is not None:
            locked = sorted(
                field for field in self.PLATFORM_ONLY_FIELDS
                if field in serializer.validated_data
            )
            if locked:
                raise PermissionDenied(
                    'Only the platform operator can change an institution’s '
                    'identity · প্রতিষ্ঠানের পরিচয় কেবল প্ল্যাটফর্ম অপারেটর বদলাতে পারেন।'
                )
        serializer.save(updated_by=self.request.user)

    @action(detail=False, methods=['get'], url_path='mine')
    def mine(self, request):
        """The institutions this account may work in — the branch switcher's source.

        Unpaginated and active-only on purpose: it fills a dropdown in the
        header, and a closed institution is not somewhere anyone should be able
        to switch into. Distinct from `GET /api/branches/`, which is the
        administrative list and shows inactive institutions too.
        """
        branches = self.get_queryset().filter(is_active=True)
        serializer = self.get_serializer(branches, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class StreamViewSet(BranchScopedViewSet):
    """An institution's study sectors (docs/08 D2).

    Permission resource is `academics`, not `branches`: docs/02 §2.1 puts
    classes, sections, subjects, sessions, streams and the routine under one
    resource, because they are edited by the same person on the same screens.
    """

    queryset = Stream.objects.all()
    serializer_class = StreamSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active']
    search_fields = ['code', 'name', 'name_bn']
    ordering_fields = ['order', 'name', 'code', 'created_at']

    def get_permissions(self):
        return [IsAuthenticated(), HasPermission(_academics_permission(self.action))()]


class SessionViewSet(BranchScopedViewSet):
    """Academic years."""

    queryset = Session.objects.all().prefetch_related('streams')
    serializer_class = SessionSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_current', 'streams']
    search_fields = ['name']
    ordering_fields = ['starts_on', 'ends_on', 'name', 'created_at']

    def get_permissions(self):
        return [IsAuthenticated(), HasPermission(_academics_permission(self.action))()]

    def perform_create(self, serializer):
        super().perform_create(serializer)
        self._apply_current(serializer)

    def perform_update(self, serializer):
        super().perform_update(serializer)
        self._apply_current(serializer)

    def _apply_current(self, serializer):
        """Route `is_current` through the service that keeps it unique.

        The flag cannot be trusted to a plain field write: docs/03 §2 allows at
        most one current session per (branch, stream), and that rule spans the
        `streams` M2M so no database constraint can hold it (see
        `services.set_current_session`). Saving the field directly would leave
        two sessions current and every default silently reading the wrong one.
        """
        if serializer.instance.is_current:
            set_current_session(serializer.instance)


def _academics_permission(action):
    """The `academics.*` string this action needs (docs/02 §2.1)."""
    if action in ('list', 'retrieve'):
        return 'academics.view'
    if action == 'create':
        return 'academics.create'
    if action == 'destroy':
        return 'academics.delete'
    return 'academics.update'
