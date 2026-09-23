from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register('game-days', views.GameDayViewSet, basename='gameday')
router.register('games', views.GameViewSet, basename='game')
router.register('tables', views.TableViewSet, basename='table')
router.register('conversion-rates', views.ConversionRateViewSet, basename='conversionrate')
router.register('transactions', views.TransactionViewSet, basename='transaction')

urlpatterns = [
    path('club-settings/', views.ClubSettingsView.as_view(), name='club-settings'),
    path('outstanding/', views.OutstandingLedgerView.as_view(), name='outstanding-ledger'),
    path('main-account/ledger/', views.MainAccountLedgerView.as_view(), name='main-account-ledger'),
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),
    path('deals/transfer/', views.DealTransferView.as_view(), name='deal-transfer'),
    path('deals/profit-split/', views.ProfitSplitArrangementView.as_view(), name='profit-split-create'),
    path(
        'deals/profit-split/<int:player_pk>/', views.PlayerProfitSplitStatusView.as_view(),
        name='profit-split-status',
    ),
    path(
        'deals/profit-split/<int:pk>/deactivate/', views.DeactivateProfitSplitArrangementView.as_view(),
        name='profit-split-deactivate',
    ),
] + router.urls
