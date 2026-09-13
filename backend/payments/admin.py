from django.contrib import admin

from .models import DedicatedVirtualAccount, PaystackAccount


class DedicatedVirtualAccountInline(admin.TabularInline):
    model = DedicatedVirtualAccount
    extra = 0


@admin.register(PaystackAccount)
class PaystackAccountAdmin(admin.ModelAdmin):
    list_display = ('integration_name', 'account_type', 'player', 'created_at')
    list_filter = ('account_type',)
    inlines = [DedicatedVirtualAccountInline]
