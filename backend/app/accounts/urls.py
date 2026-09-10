"""Accounts URLs — mounted at `/api/` by `core/urls.py`.

Three families, deliberately separate paths rather than one router prefix:

* `/api/auth/…`     what an unauthenticated or just-authenticated client needs
* `/api/accounts/…` the staff-facing administration of accounts and roles
* `/api/activity/`  the live feed (docs/08 D8), which is its own screen and its
                    own permission and does not belong under `accounts`
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (ActivityLogViewSet, ChangePasswordView, LoginView,
                    LogoutView, MeView, PermissionCatalogView, RefreshView,
                    RoleViewSet, UserViewSet)

app_name = 'accounts'

accounts_router = DefaultRouter()
accounts_router.register('users', UserViewSet, basename='user')
accounts_router.register('roles', RoleViewSet, basename='role')

activity_router = DefaultRouter()
activity_router.register('activity', ActivityLogViewSet, basename='activity')

urlpatterns = [
    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/refresh/', RefreshView.as_view(), name='refresh'),
    path('auth/logout/', LogoutView.as_view(), name='logout'),
    path('auth/me/', MeView.as_view(), name='me'),
    path('auth/change-password/', ChangePasswordView.as_view(), name='change-password'),

    # Before the router include, or the router's `users/<pk>/` pattern would
    # never see it — DefaultRouter registers a catch-all detail route.
    path('accounts/permission-catalog/', PermissionCatalogView.as_view(),
         name='permission-catalog'),
    path('accounts/', include(accounts_router.urls)),

    path('', include(activity_router.urls)),
]
