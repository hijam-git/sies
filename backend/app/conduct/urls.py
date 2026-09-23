"""Routes for the conduct app. Included by  under .

The sheet is not a viewset: it is one grid in one request, the same shape the
attendance register takes, and a router would turn it into rows nobody edits
one at a time.

There is no `report-items` route: the questions ARE `forms.Question`, written
on Settings → Questions and served read-only with the template.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (ConductSheetView, MyConductDutiesView,
                    ReportAssignmentViewSet, ReportTemplateViewSet,
                    StudentConductView, StudentReportViewSet)

app_name = 'conduct'

router = DefaultRouter()
router.register('report-templates', ReportTemplateViewSet, basename='report-template')
router.register('report-assignments', ReportAssignmentViewSet,
                basename='report-assignment')
router.register('student-reports', StudentReportViewSet, basename='student-report')

urlpatterns = [
    path('conduct/sheet/', ConductSheetView.as_view(), name='conduct-sheet'),
    path('conduct/my-duties/', MyConductDutiesView.as_view(), name='conduct-my-duties'),
    path('conduct/student/<int:pk>/', StudentConductView.as_view(), name='conduct-student'),
    path('', include(router.urls)),
]
