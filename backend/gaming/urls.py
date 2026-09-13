from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register('game-days', views.GameDayViewSet, basename='gameday')
router.register('conversion-rates', views.ConversionRateViewSet, basename='conversionrate')
router.register('transactions', views.TransactionViewSet, basename='transaction')

urlpatterns = [
    path('outstanding/', views.OutstandingLedgerView.as_view(), name='outstanding-ledger'),
    path('main-account/ledger/', views.MainAccountLedgerView.as_view(), name='main-account-ledger'),
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),
] + router.urls
