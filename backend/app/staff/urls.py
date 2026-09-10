"""Routes for the staff app. Included by `core.urls` under `/api/`."""

from rest_framework.routers import DefaultRouter

from .views import EmployeeViewSet, TeacherQualificationViewSet, TeacherViewSet

app_name = 'staff'

router = DefaultRouter()
# Two resources and not one `staff/`, matching the two permission checkboxes in
# docs/02 §2.1 and the two screens the brief lists.
router.register('teachers', TeacherViewSet, basename='teacher')
router.register('employees', EmployeeViewSet, basename='employee')
router.register('teacher-qualifications', TeacherQualificationViewSet,
                basename='teacher-qualification')

urlpatterns = router.urls
