"""Routes for the forms app. Included by `core.urls` under `/api/`.

The two `admissions/<id>/…` paths live here rather than as `@action`s on the
students app's `AdmissionViewSet`, and that is the dependency direction doing
its job (docs/06 §2): `forms` imports `students`, never the reverse. Mounted
under `/api/`, they produce exactly the URL docs/07 §8 specifies —
`/api/admissions/<id>/form/`.
"""

from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (AdmissionAnswersView, AdmissionAnswerViewSet,
                    AdmissionFormView, FormTemplateViewSet, PrintedFormViewSet,
                    QuestionViewSet)

app_name = 'forms'

router = DefaultRouter()
router.register('form-templates', FormTemplateViewSet, basename='form-template')
router.register('questions', QuestionViewSet, basename='question')
router.register('admission-answers', AdmissionAnswerViewSet, basename='admission-answer')
router.register('printed-forms', PrintedFormViewSet, basename='printed-form')

urlpatterns = [
    path('admissions/<int:pk>/form/', AdmissionFormView.as_view(), name='admission-form'),
    path('admissions/<int:pk>/answers/', AdmissionAnswersView.as_view(),
         name='admission-answers'),
    *router.urls,
]
