"""A URLconf for this module's API tests.

`core/urls.py` still has the exams routes commented out (Phase 6 uncomments
them, and this module must not edit that file), so the API tests point
`ROOT_URLCONF` here instead. Same pattern as `staff.tests.urls`.
"""

from django.urls import include, path

urlpatterns = [
    path('api/', include('exams.urls')),
]
