"""Routes for the branches app. Included by `core.urls` under `/api/`."""

from rest_framework.routers import DefaultRouter

from .views import BranchViewSet, SessionViewSet, StreamViewSet

app_name = 'branches'

router = DefaultRouter()
# `branches` and not `institutions`: docs/08 D1 keeps the word because it is the
# owner's, and renaming a URL the SPA already calls is churn with no payoff.
router.register('branches', BranchViewSet, basename='branch')
router.register('streams', StreamViewSet, basename='stream')
router.register('sessions', SessionViewSet, basename='session')

urlpatterns = router.urls
