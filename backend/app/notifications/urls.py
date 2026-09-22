"""Routes for the notifications app. Included by  under .

The send action is not here — it hangs off the exam ().
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import NotificationTemplateViewSet, SmsMessageViewSet

app_name = 'notifications'

router = DefaultRouter()
router.register('sms', SmsMessageViewSet, basename='sms')
router.register('message-templates', NotificationTemplateViewSet, basename='message-template')

urlpatterns = [
    path('', include(router.urls)),
]
