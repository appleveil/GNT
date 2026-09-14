from decimal import Decimal

from rest_framework import serializers

from accounts.models import Player
from accounts.serializers import PlayerBankAccountSerializer

from .models import ConversionRate, GameDay, GameDaySummary, Transaction


class GameDaySummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = GameDaySummary
        fields = [
            'num_players', 'chips_out_total', 'chips_in_total', 'rake_total', 'tips_total',
            'chips_variance', 'total_payments', 'game_balance', 'created_at',
        ]


class GameDaySerializer(serializers.ModelSerializer):
    # None until the game-day is closed — see gaming.services.close_game_day.
    summary = serializers.SerializerMethodField()

    class Meta:
        model = GameDay
        fields = [
            'id', 'number', 'started_at', 'ended_at', 'status',
            'opened_by', 'opened_by_floor_manager', 'closed_by', 'closed_by_floor_manager', 'summary',
        ]
        read_only_fields = fields

    def get_summary(self, obj):
        try:
            return GameDaySummarySerializer(obj.summary).data
        except GameDaySummary.DoesNotExist:
            return None


class GameDaySummaryPreviewSerializer(serializers.Serializer):
    """
    What close() would write to GameDaySummary, computed live — see
    gaming.selectors.game_day_summary_data. A plain Serializer (not
    ModelSerializer) since there's no model instance yet to serialize, only
    a dict; DRF's field/attribute resolution works the same way for both.
    Mirrors GameDaySummarySerializer's DecimalField string-coercion so a
    preview and the eventual real summary look identical over the wire.
    """

    num_players = serializers.IntegerField()
    num_players_seated = serializers.IntegerField()
    chips_out_total = serializers.DecimalField(max_digits=14, decimal_places=2)
    chips_in_total = serializers.DecimalField(max_digits=14, decimal_places=2)
    rake_total = serializers.DecimalField(max_digits=14, decimal_places=2)
    tips_total = serializers.DecimalField(max_digits=14, decimal_places=2)
    chips_variance = serializers.DecimalField(max_digits=14, decimal_places=2)
    total_payments = serializers.DecimalField(max_digits=14, decimal_places=2)
    game_balance = serializers.DecimalField(max_digits=14, decimal_places=2)
    outstanding_chips_after_close = serializers.DecimalField(max_digits=14, decimal_places=2)


class OpenGameDaySerializer(serializers.Serializer):
    number = serializers.IntegerField()
    started_at = serializers.DateTimeField(required=False)
    floor_manager_id = serializers.IntegerField(required=False, allow_null=True)
    floor_manager_pin = serializers.CharField(required=False, allow_blank=True)
    owner_id = serializers.IntegerField(required=False, allow_null=True)
    owner_pin = serializers.CharField(required=False, allow_blank=True)


class CloseGameDaySerializer(serializers.Serializer):
    floor_manager_id = serializers.IntegerField(required=False, allow_null=True)
    floor_manager_pin = serializers.CharField(required=False, allow_blank=True)


class ConversionRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConversionRate
        fields = ['id', 'currency', 'rate_to_naira', 'game_day', 'set_by', 'set_by_floor_manager', 'created_at']
        read_only_fields = fields


class SetConversionRateSerializer(serializers.Serializer):
    currency = serializers.ChoiceField(choices=ConversionRate.Currency.choices)
    rate_to_naira = serializers.DecimalField(max_digits=12, decimal_places=4)
    game_day = serializers.PrimaryKeyRelatedField(queryset=GameDay.objects.all(), required=False, allow_null=True)
    floor_manager_id = serializers.IntegerField(required=False, allow_null=True)
    floor_manager_pin = serializers.CharField(required=False, allow_blank=True)
    owner_id = serializers.IntegerField(required=False, allow_null=True)
    owner_pin = serializers.CharField(required=False, allow_blank=True)


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = [
            'id', 'game_day', 'player', 'type', 'amount', 'currency', 'conversion_rate',
            'channel', 'notes', 'recorded_by', 'floor_manager', 'confirmed_at', 'status',
            'approved_by', 'approved_at', 'is_voided', 'voided_by', 'voided_at', 'void_reason',
            'external_reference', 'created_at',
        ]
        read_only_fields = [f for f in fields if f not in ('game_day', 'player', 'type', 'amount', 'notes')]


class LedgerEntrySerializer(TransactionSerializer):
    """A Transaction row annotated with the computed signed amount and running balance."""

    signed_amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    running_balance = serializers.DecimalField(max_digits=14, decimal_places=2)

    class Meta(TransactionSerializer.Meta):
        fields = TransactionSerializer.Meta.fields + ['signed_amount', 'running_balance']


class RecordTransactionSerializer(serializers.Serializer):
    game_day = serializers.PrimaryKeyRelatedField(queryset=GameDay.objects.all(), required=False, allow_null=True)
    player = serializers.PrimaryKeyRelatedField(queryset=Player.objects.all(), required=False, allow_null=True)
    type = serializers.ChoiceField(choices=Transaction.Type.choices)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField(required=False, default='NGN')
    conversion_rate = serializers.DecimalField(
        max_digits=12, decimal_places=4, required=False, allow_null=True,
    )
    notes = serializers.CharField(required=False, allow_blank=True, default='')
    floor_manager_id = serializers.IntegerField(required=False, allow_null=True)
    floor_manager_pin = serializers.CharField(required=False, allow_blank=True)


class VoidTransactionSerializer(serializers.Serializer):
    reason = serializers.CharField()


class InitiatePayoutSerializer(serializers.Serializer):
    player = serializers.PrimaryKeyRelatedField(queryset=Player.objects.all())
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    game_day = serializers.PrimaryKeyRelatedField(queryset=GameDay.objects.all(), required=False, allow_null=True)


class GameDaySeatedPlayerSerializer(serializers.Serializer):
    """
    One row of gaming.selectors.game_day_players(game_day) — a GameDayPlayer
    (see that model) flattened with THIS specific game-day's balance, never
    lifetime. Added 2026-09-13 for the Cashier's "current game-day players
    only" list — see CONCEPT.md's "Cashier player-history visibility."
    """

    id = serializers.IntegerField(source='player.id')
    account_code = serializers.CharField(source='player.account_code')
    display_name = serializers.CharField(source='player.display_name')
    chips_limit = serializers.DecimalField(
        source='player.chips_limit', max_digits=14, decimal_places=2, allow_null=True,
    )
    bank_accounts = PlayerBankAccountSerializer(source='player.bank_accounts', many=True)
    balance = serializers.SerializerMethodField()
    chips_used_today = serializers.SerializerMethodField()
    gaming_account = serializers.SerializerMethodField()
    added_at = serializers.DateTimeField()
    # Null = still active at the table; set = "left the table" — see
    # gaming.services.leave_table. Added 2026-09-14.
    left_at = serializers.DateTimeField(allow_null=True)

    def get_balance(self, obj):
        from . import selectors
        return selectors.player_game_day_balance(obj.player, obj.game_day)

    def get_chips_used_today(self, obj):
        if obj.player.chips_limit is None:
            return None
        balance = self.get_balance(obj)
        return -balance if balance < 0 else Decimal('0')

    def get_gaming_account(self, obj):
        # None until provisioned — mirrors accounts.PlayerSerializer.get_gaming_account.
        from payments.models import PaystackAccount
        from payments.serializers import PaystackAccountSerializer

        try:
            account = obj.player.gaming_account
        except PaystackAccount.DoesNotExist:
            return None
        return PaystackAccountSerializer(account).data


class SeatPlayerSerializer(serializers.Serializer):
    """
    Input for "add a player for tonight" — either `player_id` (seat an
    existing club player) or `account_code` + `display_name` (create a new
    one and seat it in the same call). See CONCEPT.md's Buy-in flow.
    """

    player_id = serializers.PrimaryKeyRelatedField(source='player', queryset=Player.objects.all(), required=False)
    account_code = serializers.CharField(required=False)
    display_name = serializers.CharField(required=False)

    def validate(self, data):
        has_existing = 'player' in data
        has_new_fields = 'account_code' in data or 'display_name' in data
        if not has_existing and not has_new_fields:
            raise serializers.ValidationError(
                'Provide either player_id (existing player) or account_code + display_name (new player).'
            )
        if has_existing and has_new_fields:
            raise serializers.ValidationError('Provide player_id OR new-player fields, not both.')
        if has_new_fields and not ('account_code' in data and 'display_name' in data):
            raise serializers.ValidationError('A new player needs both account_code and display_name.')
        return data
