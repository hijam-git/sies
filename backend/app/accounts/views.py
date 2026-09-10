"""Auth, users, roles and the activity feed.

Views are thin (CLAUDE.md §4.3): they check a permission, pick a queryset and
call a service. Everything with an audit consequence — login, password change,
permission assignment — is in `services.py`.
"""

from django.db.models import Count
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from core.middleware import ALL_BRANCHES, get_branch
from core.viewsets import BranchScopedMixin

from .models import ActivityLog, Role, User
from .permissions import HasResourcePermission
from .serializers import (ActivityLogSerializer, ChangePasswordSerializer,
                          LoginSerializer, RoleSerializer,
                          UserPermissionsSerializer, UserSerializer,
                          permission_catalog_payload)
from .services import (ActivityLogMixin, ProtectedReference, change_password,
                       login_user, set_user_permissions, user_payload)


def _tokens_for(user):
    """An access/refresh pair. Rotation and blacklisting are settings' business."""
    refresh = RefreshToken.for_user(user)
    return {'access': str(refresh.access_token), 'refresh': str(refresh)}


class LoginView(APIView):
    """`POST /api/auth/login/` — phone + password.

    The one endpoint that is deliberately open. Both outcomes are written to the
    ActivityLog by `login_user`, and its coded exceptions (`invalid_phone`,
    `invalid_credentials`, `account_inactive`) travel to the SPA through the
    project's exception handler unchanged (docs/WORKLOG F15).
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = login_user(
            phone=serializer.validated_data['phone'],
            password=serializer.validated_data['password'],
            request=request,
        )

        return Response({
            'success': True,
            **_tokens_for(user),
            'user': user_payload(user),
        })


class RefreshView(APIView):
    """`POST /api/auth/refresh/` — a fresh access token from a refresh token.

    Hand-written rather than simplejwt's `TokenRefreshView` so the failure has
    this project's error shape. simplejwt answers its own body, which is the one
    place the SPA would otherwise need a second branch.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        token = (request.data.get('refresh') or '').strip()
        if not token:
            return _auth_failed('A refresh token is required.')

        try:
            refresh = RefreshToken(token)
        except TokenError:
            return _auth_failed('Your session has expired. Please sign in again.')

        payload = {'access': str(refresh.access_token)}

        # ROTATE_REFRESH_TOKENS is on and BLACKLIST_AFTER_ROTATION with it
        # (settings.py), so the token just spent is revoked here and the client
        # is handed its replacement. Skipping this would leave a stolen refresh
        # token usable for its full 90 days.
        from django.conf import settings as django_settings

        jwt_settings = getattr(django_settings, 'SIMPLE_JWT', {})
        if jwt_settings.get('ROTATE_REFRESH_TOKENS'):
            if jwt_settings.get('BLACKLIST_AFTER_ROTATION'):
                try:
                    refresh.blacklist()
                except AttributeError:
                    # token_blacklist not installed. Not fatal — rotation still
                    # happens — so it must not turn a refresh into a 500.
                    pass
            refresh.set_jti()
            refresh.set_exp()
            refresh.set_iat()
            payload['refresh'] = str(refresh)

        return Response({'success': True, **payload})


def _auth_failed(message):
    return Response(
        {'success': False, 'message': message, 'errors': {},
         'code': 'invalid_credentials'},
        status=status.HTTP_401_UNAUTHORIZED,
    )


class LogoutView(APIView):
    """`POST /api/auth/logout/` — blacklist the refresh token.

    Answers 200 even when the token is already dead or malformed. Logging out is
    not an operation a client can usefully retry, and a 400 here leaves the SPA
    holding credentials it has already discarded locally.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        token = (request.data.get('refresh') or '').strip()
        if token:
            try:
                RefreshToken(token).blacklist()
            except (TokenError, AttributeError):
                pass
        return Response({'success': True, 'message': 'Signed out.'})


class MeView(APIView):
    """`GET /api/auth/me/` — who am I, and what may I do.

    The permissions here are the EFFECTIVE ones, so the SPA's `canView()` gate
    agrees with the backend's enforcement by construction (docs/02 §2).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({'success': True, 'data': user_payload(request.user)})


class ChangePasswordView(APIView):
    """`POST /api/auth/change-password/` — the caller's own password only.

    Resetting somebody ELSE's password is a `users.update` write on their record,
    not this endpoint. Keeping them apart means a compromised session cannot
    change an account it does not own.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data,
                                              context={'request': request})
        serializer.is_valid(raise_exception=True)
        change_password(
            user=request.user,
            new_password=serializer.validated_data['new_password'],
            request=request,
        )
        return Response({'success': True, 'message': 'Password changed.'})


class PermissionCatalogView(APIView):
    """`GET /api/accounts/permission-catalog/` — the catalogue and the presets.

    Any signed-in user may read it. It describes what CAN be granted, not what
    anyone holds, and the permission screen is not the only consumer: the SPA
    renders resource labels from it wherever a permission is named.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({'success': True, 'data': permission_catalog_payload()})


class UserViewSet(ActivityLogMixin, BranchScopedMixin, viewsets.ModelViewSet):
    """Staff accounts, scoped to the caller's institution.

    `BranchScopedMixin` rather than `BranchScopedViewSet`: `User` is a global
    model (docs/03 §1) and does not inherit `BranchScopedModel`, so it has no
    `created_by` for the base `perform_create` to stamp. The scoping half is
    identical and comes from `UserQuerySet.for_branch`.

    A branch-A user asking for a branch-B account gets **404, not 403** — the row
    is simply not in the queryset, and 403 would confirm it exists
    (CLAUDE.md §5).
    """

    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, HasResourcePermission]
    permission_resource = 'users'
    # `permissions` is a custom @action, so POST would otherwise map to `update`
    # via POST_IS_AN_UPDATE. That is the right answer here and it is declared
    # anyway, because a reader of this class should not have to know the fallback
    # table to know what the endpoint costs.
    permission_action_map = {'permissions': 'update'}
    activity_model = 'User'
    queryset = User.objects.select_related('role', 'branch').all()
    filterset_fields = ['user_type', 'role', 'is_active']
    search_fields = ['name', 'name_bn', 'phone', 'email']
    ordering_fields = ['name', 'created_at', 'last_login']

    def save_new(self, serializer):
        """Stamp the branch from the request; never from the body.

        `save_new` rather than `perform_create` so `ActivityLogMixin` still
        writes the audit entry: overriding `perform_create` here would shadow it.
        The base `BranchScopedMixin.perform_create` cannot be used at all,
        because it also stamps `created_by`, which `User` does not have.

        A platform admin creating another PLATFORM admin is the one case with no
        institution to stamp — no `?branch=`, and `user_type=platform_admin` says
        what they mean. Anything else without a branch is a missing parameter,
        answered as the 400 it is rather than reaching the FK as the string 'ALL'.
        """
        branch = get_branch(self.request)
        user_type = serializer.validated_data.get('user_type')

        if branch is None or branch == ALL_BRANCHES:
            if user_type != 'platform_admin':
                raise ValidationError({
                    'branch': ('Choose an institution before creating this account. '
                               'Add ?branch=<id> to the request.'),
                })
            serializer.save(branch=None)
        elif isinstance(branch, str):
            # `?branch=<id>` arrives as a string; the middleware deliberately
            # does not validate it (it runs before authentication). Assigning to
            # `branch_id` lets the FK constraint be the one that rejects an id
            # that names nothing, which is where that answer belongs.
            serializer.save(branch_id=branch)
        else:
            serializer.save(branch=branch)

    @action(detail=True, methods=['post'], url_path='permissions')
    def permissions(self, request, pk=None):
        """`POST …/users/<id>/permissions/` — replace the explicit list.

        The whole list, every time. A patch-shaped "add these, remove those" API
        cannot express "this person is back on their role's preset", which is an
        empty list here and is the reset button on the permission screen
        (docs/02 §2.3).
        """
        target = self.get_object()
        serializer = UserPermissionsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        set_user_permissions(
            target=target,
            permissions=serializer.validated_data['permissions'],
            actor=request.user,
            request=request,
        )
        return Response({'success': True, 'data': UserSerializer(target).data})


class RoleViewSet(ActivityLogMixin, viewsets.ModelViewSet):
    """Role presets. Global, so not branch-scoped — a preset is platform vocabulary.

    Gated on `users.*` rather than a `roles` resource of its own: docs/02 §2.1
    puts "roles and permission assignment" under `users`, and splitting it here
    would create a permission the catalogue does not describe and the SPA cannot
    render a checkbox for.
    """

    serializer_class = RoleSerializer
    permission_classes = [IsAuthenticated, HasResourcePermission]
    permission_resource = 'users'
    activity_model = 'Role'
    queryset = Role.objects.annotate(user_count=Count('users')).all()
    filterset_fields = ['is_system', 'is_active']
    search_fields = ['name', 'name_bn']
    ordering_fields = ['name']

    def save_new(self, serializer):
        # `is_system` is read-only on the serializer; a role created through the
        # API is the institution's own and must stay deletable.
        serializer.save(is_system=False)

    def perform_destroy(self, instance):
        if instance.is_system:
            # A system preset is referenced by `seed_roles` and by every user
            # still on it. Deactivating is the supported way to retire one.
            raise ProtectedReference(
                'This is a system role and cannot be deleted. Switch it off instead.')
        super().perform_destroy(instance)


class ActivityLogViewSet(viewsets.ReadOnlyModelViewSet):
    """`GET /api/activity/` — the live feed and its history. docs/08 D8.

    Read-only, because the table is append-only: there is no create, update or
    destroy to expose, and a viewset that offered them would be the one path
    around `ActivityLog.save()`'s refusal.

    **Cursor pagination, not page numbers.** The SPA polls this every five
    seconds with `?since=<last_id>`, and a page number over a table that grows
    while you read it returns the same row twice and skips another. `id` is the
    cursor because it is strictly monotonic — two rows written in the same
    millisecond still have an order, which `created_at` cannot promise.
    """

    serializer_class = ActivityLogSerializer
    permission_classes = [IsAuthenticated, HasResourcePermission]
    permission_resource = 'activity'
    queryset = ActivityLog.objects.select_related('user', 'branch').all()
    # Paginated by the cursor below, not by the project's page-number class.
    pagination_class = None

    #: How many rows one poll may return. A client that has been closed for a day
    #: must not pull the whole table back in one response.
    max_page = 200

    def get_queryset(self):
        """Scoped by hand: ActivityLog's branch is nullable, so `for_branch` does
        not apply.

        A platform admin sees everything, including the platform-level rows that
        belong to no institution. A principal sees only their own institution —
        and specifically NOT the NULL-branch rows, which are the platform
        operator's own logins and institution-creation events.
        """
        queryset = super().get_queryset()
        branch = get_branch(self.request)

        if branch is None:
            return queryset.none()
        if branch == ALL_BRANCHES:
            return queryset
        return queryset.filter(branch=branch)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_feed(self.get_queryset(), request)

        rows = list(queryset[:self._page_size(request)])
        serializer = self.get_serializer(rows, many=True)

        # `last_id` is the MAXIMUM id in this response, not the last element's:
        # the feed is ordered newest-first for display, so the last element is
        # the oldest. Handing that back as the cursor would replay the page
        # forever.
        last_id = max((row.id for row in rows), default=self._since(request) or 0)

        return Response({'items': serializer.data, 'last_id': last_id})

    def filter_feed(self, queryset, request):
        """`?since=`, `?branch=`, `?user=`, `?action=`.

        `?branch=` narrows within what the caller may already see; it never
        widens. For a branch user `get_queryset()` has already pinned the branch,
        so the parameter is a no-op rather than an error — the same degrade-safely
        rule the middleware applies to a pasted platform-admin URL (docs/02 §3).
        """
        since = self._since(request)
        if since:
            queryset = queryset.filter(id__gt=since)

        branch = request.query_params.get('branch')
        if branch and get_branch(request) == ALL_BRANCHES:
            queryset = queryset.filter(branch_id=branch)

        user_id = request.query_params.get('user')
        if user_id:
            queryset = queryset.filter(user_id=user_id)

        action_name = request.query_params.get('action')
        if action_name:
            queryset = queryset.filter(action=action_name)

        return queryset

    def _since(self, request):
        raw = request.query_params.get('since')
        try:
            return int(raw) if raw else None
        except (TypeError, ValueError):
            # A junk cursor means "start from the top", not a 400. The feed is a
            # polling widget; failing it hard would leave a blank panel on the
            # dashboard for a query string nobody typed.
            return None

    def _page_size(self, request):
        try:
            requested = int(request.query_params.get('limit', 50))
        except (TypeError, ValueError):
            requested = 50
        return max(1, min(requested, self.max_page))
