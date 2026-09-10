"""Routes for the fees app. Included by `core.urls` under `/api/`.

`payments` is registered as its own resource rather than nested under a fee:
"every receipt this cashier issued today" and "find receipt RCP-DHK-000412" are
both counter questions, and neither knows an invoice id. Collection itself
still goes through `/api/fees/<id>/collect/`, because a receipt without an
invoice is not a thing this system can write.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import FeeCategoryViewSet, FeeViewSet, PaymentViewSet

app_name = 'fees'

router = DefaultRouter()
router.register('fee-categories', FeeCategoryViewSet, basename='fee-category')
router.register('fees', FeeViewSet, basename='fee')
router.register('payments', PaymentViewSet, basename='payment')

urlpatterns = [
    path('', include(router.urls)),
]
