"""Routes for the academics app. Included by `core.urls` under `/api/`."""

from rest_framework.routers import DefaultRouter

from .views import (AcademicClassViewSet, ClassRoutineViewSet, EnrolmentViewSet,
                    PeriodViewSet, SectionViewSet, SubjectAssignmentViewSet,
                    SubjectViewSet)

app_name = 'academics'

router = DefaultRouter()
# `classes` rather than `academic-classes`: the SPA's URL is what a user sees in
# their address bar, and the model name is a Django detail — `class` is a Python
# keyword, which is the only reason the model is not called that.
router.register('classes', AcademicClassViewSet, basename='academic-class')
router.register('sections', SectionViewSet, basename='section')
router.register('subjects', SubjectViewSet, basename='subject')
router.register('periods', PeriodViewSet, basename='period')
router.register('class-routines', ClassRoutineViewSet, basename='class-routine')
router.register('enrolments', EnrolmentViewSet, basename='enrolment')
router.register('subject-assignments', SubjectAssignmentViewSet,
                basename='subject-assignment')

urlpatterns = router.urls
