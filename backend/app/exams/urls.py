"""Routes for the exams app. Included by `core.urls` under `/api/`."""

from rest_framework.routers import DefaultRouter

from .views import (ExamClassViewSet, ExamScheduleViewSet, ExamViewSet,
                    MarkViewSet)

app_name = 'exams'

router = DefaultRouter()
router.register('exams', ExamViewSet, basename='exam')
router.register('exam-classes', ExamClassViewSet, basename='exam-class')
router.register('exam-schedules', ExamScheduleViewSet, basename='exam-schedule')
router.register('marks', MarkViewSet, basename='mark')

urlpatterns = router.urls
