from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

router = DefaultRouter()
router.register('staff-users', views.StaffUserViewSet, basename='staffuser')
router.register('floor-managers', views.FloorManagerViewSet, basename='floormanager')
router.register('players', views.PlayerViewSet, basename='player')

bank_accounts = views.PlayerBankAccountViewSet
urlpatterns = [
    path('auth/login/', views.StaffLoginView.as_view(), name='staff-login'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('auth/logout/', views.LogoutView.as_view(), name='staff-logout'),
    path(
        'players/<int:player_pk>/bank-accounts/',
        bank_accounts.as_view({'get': 'list', 'post': 'create'}),
        name='player-bank-accounts',
    ),
    path(
        'players/<int:player_pk>/bank-accounts/<int:pk>/',
        bank_accounts.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}),
        name='player-bank-account-detail',
    ),
] + router.urls
