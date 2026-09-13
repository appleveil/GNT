from django.contrib import admin

from .models import ConversionRate, GameDay, GameDaySummary, Transaction


@admin.register(GameDay)
class GameDayAdmin(admin.ModelAdmin):
    list_display = ('number', 'status', 'started_at', 'ended_at', 'opened_by', 'closed_by')
    list_filter = ('status',)


@admin.register(ConversionRate)
class ConversionRateAdmin(admin.ModelAdmin):
    list_display = ('currency', 'rate_to_naira', 'game_day', 'set_by', 'created_at')
    list_filter = ('currency',)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'type', 'player', 'amount', 'channel', 'game_day', 'status', 'is_voided', 'created_at',
    )
    list_filter = ('type', 'channel', 'status', 'is_voided')
    search_fields = ('player__account_code', 'player__display_name', 'external_reference')
    autocomplete_fields = ('player',)


@admin.register(GameDaySummary)
class GameDaySummaryAdmin(admin.ModelAdmin):
    list_display = ('game_day', 'num_players', 'game_balance', 'created_at')
