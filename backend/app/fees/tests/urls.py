"""A URLconf for this module's API tests.

`fees.urls` is not yet included by `core.urls` — the coordinator wires that up
with the settings change — so the API tests mount it here and are runnable
today. See `academics.tests.urls` for the same pattern.
"""

from django.urls import include, path

urlpatterns = [
    path('api/', include('fees.urls')),
    path('api/', include('finance.urls')),
]
