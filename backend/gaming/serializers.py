from decimal import Decimal

from rest_framework import serializers

from accounts.models import Player, StaffMember
from accounts.serializers import PlayerBankAccountSerializer

from . import selectors
from .models import ClubSettings, ConversionRate, Game, GameDay, GameDaySummary, ProfitSplitArrangement, Table, Transaction


class GameSerializer(serializers.ModelSerializer):
    class Meta:
        model = Game
        fields = ['id', 'name', 'is_active', 'max_players']
        read_only_fields = fields


class TableSerializer(serializers.ModelSerializer):
    """
    id/game/name/is_active stay locked (row identity — see TableViewSet's
    own comment); everything else here is the Owner/Floor-Manager-editable
    "Settings" screen fields added 2026-09-23 — see Table's own docstring.
    """

    class Meta:
        model = Table
        fields = [
            'id', 'game', 'name', 'default_buy_in', 'is_active',
            'rake_percentage', 'small_blind', 'big_blind', 'max_players', 'max_chips_issuable',
        ]
        read_only_fields = ['id', 'game', 'name', 'is_active']


class ClubSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClubSettings
        fields = [
            'require_approval_open_game_day', 'require_approval_close_game_day', 'require_approval_issue_chips',
            'require_approval_return_chips', 'require_approval_add_tip', 'require_approval_add_rake',
            'payout_auto_approve_threshold', 'owner_dashboard_game_day_enabled',
        ]


class GameDaySummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = GameDaySummary
        fields = [
            'num_players', 'chips_out_total', 'chips_in_total', 'rake_total', 'tips_total',
            'chips_variance', 'total_payments', 'game_balance', 'chip_discrepancy_reason', 'created_at',
        ]


class ChipDiscrepancySerializer(serializers.Serializer):
    """gaming.services.game_day_chip_discrepancy's return shape — None
    (omitted) once chips reconcile. Added 2026-09-22."""

    chips_out_total = serializers.DecimalField(max_digits=14, decimal_places=0)
    chips_in_total = serializers.DecimalField(max_digits=14, decimal_places=0)
    rake_total = serializers.DecimalField(max_digits=14, decimal_places=0)
    tips_total = serializers.DecimalField(max_digits=14, decimal_places=0)
    amount = serializers.DecimalField(max_digits=14, decimal_places=0)
    direction = serializers.ChoiceField(choices=['short', 'excess'])


class GameDayChipsTotalsSerializer(serializers.Serializer):
    """
    selectors.game_day_chips_totals' return shape, live (not the frozen
    close-time summary). Added 2026-09-23 for the Cashier's persistent
    chips-caption — it needs rake_total/tips_total too (the same figures
    record_transaction's CHIPS_IN ceiling nets out), which neither `ledger`
    nor `activity` can supply: both exclude RAKE/TIP rows entirely (see
    EXCLUDED_FROM_GAME_DAY_LEDGER — they're day-level entries, not scoped to
    any one player), so a caption built only from those two feeds could
    never reflect them however it filtered its own data client-side.
    """

    chips_out_total = serializers.DecimalField(max_digits=14, decimal_places=0)
    chips_in_total = serializers.DecimalField(max_digits=14, decimal_places=0)
    rake_total = serializers.DecimalField(max_digits=14, decimal_places=0)
    tips_total = serializers.DecimalField(max_digits=14, decimal_places=0)


class GameDaySerializer(serializers.ModelSerializer):
    # None until the game-day is closed — see gaming.services.close_game_day.
    summary = serializers.SerializerMethodField()
    # The active-seat cap for tonight's game (selectors.max_active_players —
    # Texas Hold'em 9, Omaha 8, ...) — exposed directly so the frontend can
    # size its seat grid without a second round-trip to /games/. Added
    # 2026-09-21 alongside Game.max_players.
    max_players = serializers.SerializerMethodField()

    class Meta:
        model = GameDay
        fields = [
            'id', 'number', 'started_at', 'ended_at', 'status',
            'opened_by', 'opened_by_floor_manager', 'closed_by', 'closed_by_floor_manager', 'summary',
            # Added 2026-09-21 — see Game/Table/GameDay.buy_in_amount.
            'game', 'table', 'buy_in_amount', 'max_players',
        ]
        read_only_fields = fields

    def get_summary(self, obj):
        try:
            return GameDaySummarySerializer(obj.summary).data
        except GameDaySummary.DoesNotExist:
            return None

    def get_max_players(self, obj):
        return selectors.max_active_players(obj)


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
    chips_out_total = serializers.DecimalField(max_digits=14, decimal_places=0)
    chips_in_total = serializers.DecimalField(max_digits=14, decimal_places=0)
    rake_total = serializers.DecimalField(max_digits=14, decimal_places=0)
    tips_total = serializers.DecimalField(max_digits=14, decimal_places=0)
    chips_variance = serializers.DecimalField(max_digits=14, decimal_places=0)
    total_payments = serializers.DecimalField(max_digits=14, decimal_places=0)
    game_balance = serializers.DecimalField(max_digits=14, decimal_places=0)
    outstanding_chips_after_close = serializers.DecimalField(max_digits=14, decimal_places=0)
    # Added 2026-09-22 alongside services.close_game_day's new close-time
    # rules — lets the Cashier see these up front, in the same words the
    # service itself would use, rather than only discovering them after
    # entering a PIN. close_blocked_reason is the HARD block (active
    # players still seated — not overridable); chip_discrepancy is the
    # ACKNOWLEDGE-and-sign-off condition (see gaming.services for both).
    active_players_count = serializers.IntegerField()
    close_blocked_reason = serializers.CharField(allow_null=True)
    chip_discrepancy = ChipDiscrepancySerializer(allow_null=True)


class OpenGameDaySerializer(serializers.Serializer):
    number = serializers.IntegerField()
    started_at = serializers.DateTimeField(required=False)
    floor_manager_id = serializers.IntegerField(required=False, allow_null=True)
    floor_manager_pin = serializers.CharField(required=False, allow_blank=True)
    owner_id = serializers.IntegerField(required=False, allow_null=True)
    owner_pin = serializers.CharField(required=False, allow_blank=True)
    # Added 2026-09-21 — the "Start game-day" flow's three steps. All
    # optional so a game-day can still be opened without them, same as
    # before this change. buy_in_amount defaults server-side to
    # table.default_buy_in when a table is given but no amount is set —
    # see gaming.services.open_game_day.
    game_id = serializers.PrimaryKeyRelatedField(
        source='game', queryset=Game.objects.all(), required=False, allow_null=True,
    )
    table_id = serializers.PrimaryKeyRelatedField(
        source='table', queryset=Table.objects.all(), required=False, allow_null=True,
    )
    buy_in_amount = serializers.DecimalField(max_digits=14, decimal_places=0, required=False, allow_null=True)


class CloseGameDaySerializer(serializers.Serializer):
    floor_manager_id = serializers.IntegerField(required=False, allow_null=True)
    floor_manager_pin = serializers.CharField(required=False, allow_blank=True)
    # owner_id/owner_pin only come into play when there's a chip
    # discrepancy to acknowledge — an ordinary close stays Floor-Manager-
    # PIN-only. discrepancy_reason is required server-side (see
    # services.close_game_day) exactly when a discrepancy exists, not
    # unconditionally here — this serializer just needs to accept it.
    owner_id = serializers.IntegerField(required=False, allow_null=True)
    owner_pin = serializers.CharField(required=False, allow_blank=True)
    discrepancy_reason = serializers.CharField(required=False, allow_blank=True, default='')


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
    # Added 2026-09-25 so a ledger row can show WHO auto-approved a payout
    # stood in for — "Auto-<Cashier Name>" replaces the old generic
    # "Auto-approved" badge (see LedgerTable.vue/PayoutsView.vue). Only ever
    # meaningful for status=APPROVED + approved_by=None (the auto-approval
    # marker, see services._execute_payout_transfer), but resolved for every
    # row since who recorded any entry is generally useful, not payout-only.
    recorded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = [
            'id', 'game_day', 'player', 'type', 'amount', 'currency', 'conversion_rate',
            'channel', 'notes', 'recorded_by', 'recorded_by_name', 'floor_manager', 'confirmed_at', 'status',
            'approved_by', 'approved_at', 'is_voided', 'voided_by', 'voided_at', 'void_reason',
            'external_reference', 'created_at', 'tip_category', 'masseuse',
            'linked_transaction', 'profit_split_arrangement',
        ]
        read_only_fields = [f for f in fields if f not in ('game_day', 'player', 'type', 'amount', 'notes')]

    def get_recorded_by_name(self, obj):
        if obj.recorded_by_id is None:
            return None
        return obj.recorded_by.get_full_name() or obj.recorded_by.username


class LedgerEntrySerializer(TransactionSerializer):
    """A Transaction row annotated with the computed signed amount and running balance."""

    signed_amount = serializers.DecimalField(max_digits=14, decimal_places=0)
    running_balance = serializers.DecimalField(max_digits=14, decimal_places=0)

    class Meta(TransactionSerializer.Meta):
        fields = TransactionSerializer.Meta.fields + ['signed_amount', 'running_balance']


class RecordTransactionSerializer(serializers.Serializer):
    game_day = serializers.PrimaryKeyRelatedField(queryset=GameDay.objects.all(), required=False, allow_null=True)
    player = serializers.PrimaryKeyRelatedField(queryset=Player.objects.all(), required=False, allow_null=True)
    type = serializers.ChoiceField(choices=Transaction.Type.choices)
    amount = serializers.DecimalField(max_digits=14, decimal_places=0)
    currency = serializers.CharField(required=False, default='NGN')
    conversion_rate = serializers.DecimalField(
        max_digits=12, decimal_places=4, required=False, allow_null=True,
    )
    notes = serializers.CharField(required=False, allow_blank=True, default='')
    floor_manager_id = serializers.IntegerField(required=False, allow_null=True)
    floor_manager_pin = serializers.CharField(required=False, allow_blank=True)
    # Meaningful only for type=TIP — see Transaction.TipCategory. Further
    # cross-field validation (required for a TIP, MASSEUSE needs an active
    # masseuse, SERVICE_STAFF must not have one) happens in
    # gaming.services.record_transaction, not here — same pattern as this
    # serializer's other type-conditional fields.
    tip_category = serializers.ChoiceField(choices=Transaction.TipCategory.choices, required=False, allow_null=True)
    masseuse = serializers.PrimaryKeyRelatedField(
        queryset=StaffMember.objects.filter(role=StaffMember.Role.MASSEUSE), required=False, allow_null=True,
    )


class VoidTransactionSerializer(serializers.Serializer):
    reason = serializers.CharField()


class InitiatePayoutSerializer(serializers.Serializer):
    player = serializers.PrimaryKeyRelatedField(queryset=Player.objects.all())
    amount = serializers.DecimalField(max_digits=14, decimal_places=0)
    game_day = serializers.PrimaryKeyRelatedField(queryset=GameDay.objects.all(), required=False, allow_null=True)


class InitiateDirectPayoutSerializer(serializers.Serializer):
    """
    Input for the Owner's direct-payout action (2026-09-24) — see
    gaming.services.initiate_direct_payout. No game_day: this pays out a
    player's lifetime outstanding balance, not a specific game-day's
    winnings.
    """

    player = serializers.PrimaryKeyRelatedField(queryset=Player.objects.all())
    amount = serializers.DecimalField(max_digits=14, decimal_places=0)


class DealTransferSerializer(serializers.Serializer):
    """Input for the "Deals" Transfer action — see gaming.services.record_deal_transfer."""

    source_player = serializers.PrimaryKeyRelatedField(queryset=Player.objects.all())
    destination_player = serializers.PrimaryKeyRelatedField(queryset=Player.objects.all())
    amount = serializers.DecimalField(max_digits=14, decimal_places=0)
    reason = serializers.CharField()


class ProfitSplitArrangementSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProfitSplitArrangement
        fields = [
            'id', 'player', 'house_stake_pct', 'cap_amount', 'reset_cadence', 'ends_at',
            'max_resets', 'max_cumulative_value', 'payout_basis', 'payout_split_method',
            'custom_ratio_pct', 'fixed_amount', 'fixed_offset', 'is_active',
            'created_by', 'created_at', 'deactivated_at',
        ]
        read_only_fields = ['id', 'player', 'is_active', 'created_by', 'created_at', 'deactivated_at']


class CreateProfitSplitArrangementSerializer(serializers.Serializer):
    """Input for setting up a "Deals" Profit Split — see gaming.services.create_profit_split_arrangement."""

    player = serializers.PrimaryKeyRelatedField(queryset=Player.objects.all())
    house_stake_pct = serializers.DecimalField(max_digits=5, decimal_places=2)
    cap_amount = serializers.DecimalField(max_digits=14, decimal_places=0)
    reset_cadence = serializers.ChoiceField(
        choices=ProfitSplitArrangement.ResetCadence.choices,
        required=False, default=ProfitSplitArrangement.ResetCadence.ONE_OFF,
    )
    ends_at = serializers.DateTimeField(required=False, allow_null=True)
    max_resets = serializers.IntegerField(required=False, allow_null=True)
    max_cumulative_value = serializers.DecimalField(
        max_digits=14, decimal_places=0, required=False, allow_null=True,
    )
    payout_basis = serializers.ChoiceField(
        choices=ProfitSplitArrangement.PayoutBasis.choices,
        required=False, default=ProfitSplitArrangement.PayoutBasis.AFTER_BUYIN,
    )
    payout_split_method = serializers.ChoiceField(
        choices=ProfitSplitArrangement.PayoutSplitMethod.choices,
        required=False, default=ProfitSplitArrangement.PayoutSplitMethod.STAKE_RATIO,
    )
    custom_ratio_pct = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)
    fixed_amount = serializers.DecimalField(max_digits=14, decimal_places=0, required=False, allow_null=True)
    fixed_offset = serializers.DecimalField(max_digits=14, decimal_places=0, required=False, allow_null=True)


class ProfitSplitStatusSerializer(serializers.Serializer):
    """What gaming.selectors.profit_split_status computes, plus the arrangement itself."""

    arrangement = ProfitSplitArrangementSerializer()
    period_start = serializers.DateTimeField()
    periods_elapsed = serializers.IntegerField()
    covered_this_period = serializers.DecimalField(max_digits=14, decimal_places=0)
    cumulative_covered = serializers.DecimalField(max_digits=14, decimal_places=0)
    is_exhausted = serializers.BooleanField()
    exhausted_reason = serializers.CharField(allow_null=True)
    available_stake_this_period = serializers.DecimalField(max_digits=14, decimal_places=0)


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
        source='player.chips_limit', max_digits=14, decimal_places=0, allow_null=True,
    )
    bank_accounts = PlayerBankAccountSerializer(source='player.bank_accounts', many=True)
    balance = serializers.SerializerMethodField()
    chips_used_today = serializers.SerializerMethodField()
    gaming_account = serializers.SerializerMethodField()
    added_at = serializers.DateTimeField()
    # Null = still active at the table; set = "left the table" — see
    # gaming.services.leave_table. Added 2026-09-14.
    left_at = serializers.DateTimeField(allow_null=True)
    # Null = seated but not assigned a specific numbered seat yet — see
    # gaming.services.seat_player/move_seat. Added 2026-09-17.
    seat_number = serializers.IntegerField(allow_null=True)
    # True while this player has a payout stuck at TRANSFER_FAILED tonight
    # — see selectors.player_has_failed_payout's own comment. Added
    # 2026-09-23 so the Cashier isn't the last to know a payout they
    # initiated didn't actually go through.
    payout_failed = serializers.SerializerMethodField()

    def get_payout_failed(self, obj):
        from . import selectors
        return selectors.player_has_failed_payout(obj.player, obj.game_day)

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
    existing club player) or `display_name` (create a new one and seat it
    in the same call). See CONCEPT.md's Buy-in flow.

    `account_code` was dropped from this input 2026-09-25 — a new player's
    code is now auto-assigned from the AccountCode pool (see
    gaming.services._assign_next_account_code), not typed in by hand.
    """

    player_id = serializers.PrimaryKeyRelatedField(source='player', queryset=Player.objects.all(), required=False)
    display_name = serializers.CharField(required=False)
    # Optional — the specific seat tapped on the Cashier's screen. Omitted
    # (e.g. the bulk "+ Add Player" flow) leaves the player unassigned.
    seat_number = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, data):
        has_existing = 'player' in data
        has_new_fields = 'display_name' in data
        if not has_existing and not has_new_fields:
            raise serializers.ValidationError(
                'Provide either player_id (existing player) or display_name (new player).'
            )
        if has_existing and has_new_fields:
            raise serializers.ValidationError('Provide player_id OR display_name, not both.')
        return data
