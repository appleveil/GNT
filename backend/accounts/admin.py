from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import FloorManager, Player, PlayerBankAccount, StaffUser


@admin.register(StaffUser)
class StaffUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (('Role', {'fields': ('role',)}),)
    list_display = ('username', 'get_full_name', 'role', 'is_active')
    list_filter = ('role', 'is_active')


@admin.register(FloorManager)
class FloorManagerAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'created_by', 'created_at')
    list_filter = ('is_active',)


class PlayerBankAccountInline(admin.TabularInline):
    model = PlayerBankAccount
    extra = 0


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ('account_code', 'display_name', 'is_active', 'created_at')
    search_fields = ('account_code', 'display_name')
    inlines = [PlayerBankAccountInline]
