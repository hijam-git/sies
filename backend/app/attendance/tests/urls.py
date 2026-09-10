"""A URLconf for this module's API tests — see `staff.tests.urls` for why.

`core/urls.py` includes each app's routes in the phase that wires it, so these
tests would otherwise depend on a line in another file being uncommented before
they could run at all. Mounting under the same `/api/` prefix tests what the app
actually exposes and keeps the failure inside this app.
"""

from django.urls import include, path

urlpatterns = [
    path('api/', include('attendance.urls')),
]
