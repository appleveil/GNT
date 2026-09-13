from rest_framework import serializers

from accounts.models import Player

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
