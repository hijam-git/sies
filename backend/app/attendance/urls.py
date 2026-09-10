"""Routes for the attendance app. Included by `core.urls` under `/api/`.

No DRF router here, and that is the whole shape of this module: none of these
four endpoints is CRUD over a row. The register is a *grid* — a month of one
class in one response — and the bulk save is a *batch*, because 1,800 cells
cannot be 1,800 requests (docs/02 §5.1). A router would give six endpoints
nobody calls and none of the four that are actually needed.

The paths are docs/02 §5.1's own, character for character. They are the SPA's
contract and appear in `docs/06` #11.
"""

from django.urls import path

from .views import (ClassAttendanceView, MyDayView, RegisterBulkView,
                    RegisterView)

app_name = 'attendance'

urlpatterns = [
    path('attendance/register/', RegisterView.as_view(), name='register'),
    path('attendance/register/bulk/', RegisterBulkView.as_view(),
         name='register-bulk'),
    path('attendance/my-day/', MyDayView.as_view(), name='my-day'),
    path('attendance/class/', ClassAttendanceView.as_view(), name='class'),
]
