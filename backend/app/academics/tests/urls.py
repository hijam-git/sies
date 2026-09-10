"""A URLconf for this module's API tests — see `staff.tests.urls` for why."""

from django.urls import include, path

urlpatterns = [
    path('api/', include('academics.urls')),
]
