from django.urls import path

from . import views

urlpatterns = [
    path('webhooks/paystack/', views.PaystackWebhookView.as_view(), name='paystack-webhook'),
    path('payments/banks/', views.BankListView.as_view(), name='paystack-banks'),
    path('payments/resolve-account/', views.ResolveAccountView.as_view(), name='paystack-resolve-account'),
]
