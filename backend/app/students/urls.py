"""Routes for the students app. Included by `core.urls` under `/api/`.

Two families, on deliberately separate paths:

* the staff resources — `students`, `guardians`, `admissions`, `documents`
* `/api/me/…` — self-service (docs/02 §2.5, docs/08 D4)

`/api/me/` is not a prefix on the same routers. It is its own set of views with
its own querysets, because the moment it shares a viewset with the staff
endpoints it also shares a lookup by id, and a student can start guessing.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (AdmissionViewSet, DocumentViewSet, GuardianViewSet,
                    MyDocumentViewSet, MyGuardianView, MyProfileView,
                    StudentViewSet)

app_name = 'students'

router = DefaultRouter()
router.register('students', StudentViewSet, basename='student')
router.register('guardians', GuardianViewSet, basename='guardian')
router.register('admissions', AdmissionViewSet, basename='admission')
router.register('documents', DocumentViewSet, basename='document')

me_router = DefaultRouter()
me_router.register('documents', MyDocumentViewSet, basename='me-document')

urlpatterns = [
    path('', include(router.urls)),

    # Before the me_router include, or nothing would match `me/profile/`: the
    # router registers no such route and a DefaultRouter's API-root view would
    # swallow the request with a 404 that looks like a missing student.
    path('me/profile/', MyProfileView.as_view(), name='me-profile'),
    path('me/guardians/', MyGuardianView.as_view(), name='me-guardians'),
    path('me/', include(me_router.urls)),
]
