"""Routes for the finance app. Included by `core.urls` under `/api/`."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (ExpenseCategoryViewSet, ExpenseViewSet,
                    IncomeCategoryViewSet, IncomeViewSet)

app_name = 'finance'

router = DefaultRouter()
router.register('income-categories', IncomeCategoryViewSet, basename='income-category')
router.register('expense-categories', ExpenseCategoryViewSet, basename='expense-category')
router.register('income', IncomeViewSet, basename='income')
router.register('expenses', ExpenseViewSet, basename='expense')

urlpatterns = [
    path('', include(router.urls)),
]
