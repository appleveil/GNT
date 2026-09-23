from decimal import Decimal

from django.conf import settings
from django.db import models

from accounts.models import FloorManager, Player, StaffMember, StaffUser

# Whole Naira only, no kobo — every DecimalField below that represents an
# actual Naira amount uses decimal_places=0 (added 2026-09-23, a deliberate
# correction: this club never deals in fractional Naira). Rates and
# percentages (ConversionRate.rate_to_naira, Transaction.conversion_rate,
# Table.rake_percentage, ProfitSplitArrangement's *_pct fields) are NOT
# amounts and keep their own precision.


class Game(models.Model):
    """
    A game type the club runs (e.g. Texas Hold'em, Omaha) — step one of the
    "Start game-day" flow (Game → Table → Buy-in). Owner-manageable from a
    dashboard is a deliberate later step; for now rows are seeded via a data
    migration. See PLAN.md's "Game/Table selection + two-step chip custody"
    entry.

    `max_players` (added 2026-09-21) caps active seats at any game-day
    played as this game — Texas Hold'em seats 9, Omaha 8. Was previously one
    hard-coded constant shared by every game
    (gaming.services.MAX_ACTIVE_PLAYERS_PER_GAME_DAY, now the FALLBACK for a
    game-day with no `game` set at all — pre-this-change historical rows
    only; see gaming.selectors.max_active_players, the one place both live
    and hard-coded callers resolve the cap through now).
    """

    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    max_players = models.PositiveSmallIntegerField(default=9)

    def __str__(self):
        return self.name


class Table(models.Model):
    """
    A physical table running one Game — step two of the "Start game-day"
    flow. "One table per game, for now" is a convention, not a DB
    constraint: a second table for the same game later is just a new row,
    no schema change.

    `default_buy_in` only PRE-FILLS the flow's Buy-in step (step three) —
    it's not a hard rule. The amount actually used for a given night is
    snapshotted onto GameDay.buy_in_amount at open time, so a later edit
    here never rewrites what a past game-day used (same "copy now, don't
    re-derive" precedent as Transaction.conversion_rate).

    Added 2026-09-23 — Owner/Floor-Manager-editable settings, via
    ClubSettings' sibling "Settings" screen (see StaffMemberViewSet-style
    get_permissions on TableViewSet): `rake_percentage`/`small_blind`/
    `big_blind` are reference values only (nothing computes off them yet);
    `max_players` overrides `Game.max_players` for this table specifically
    when set (null = fall back to the Game's value — see
    selectors.max_active_players); `max_chips_issuable` caps how much can
    be issued to a player IN ONE GO — a ceiling per CHIPS_OUT, not a
    running/cumulative total (a player can buy in at the cap as many times
    as they like over the night; there's no limit on total chips
    outstanding at once) — see record_transaction's CHIPS_OUT branch. All
    five nullable: null means "no override"/"no cap," matching every table
    that predates this change.
    """

    game = models.ForeignKey(Game, on_delete=models.PROTECT, related_name='tables')
    name = models.CharField(max_length=100)
    default_buy_in = models.DecimalField(max_digits=14, decimal_places=0)
    is_active = models.BooleanField(default=True)
    # decimal_places=2 (a real percentage, e.g. 2.50%) — the one field here
    # that isn't a Naira amount, so the whole-number rule below doesn't apply.
    rake_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    small_blind = models.DecimalField(max_digits=14, decimal_places=0, null=True, blank=True)
    big_blind = models.DecimalField(max_digits=14, decimal_places=0, null=True, blank=True)
    max_players = models.PositiveSmallIntegerField(null=True, blank=True)
    max_chips_issuable = models.DecimalField(max_digits=14, decimal_places=0, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['game', 'name'], name='unique_table_name_per_game'),
        ]

    def __str__(self):
        return f'{self.name} ({self.game.name})'


class ClubSettings(models.Model):
    """
    Owner-only behavior toggles for the club, added 2026-09-23 alongside
    the "Settings" screen. One row per tenant schema — a true singleton via
    the pk=1 convention below, since (unlike PaystackAccount's MAIN/GAMING
    split) there's no discriminator to key off: every field here just
    applies club-wide. Always go through `load()`, never
    `ClubSettings.objects.get(...)` directly, so a club that's never
    touched Settings still gets the documented defaults instead of a
    DoesNotExist.

    Each `require_approval_*` flag governs whether that action needs an
    Owner-or-Floor-Manager (or Floor-Manager-only) PIN at all — see
    gaming.services.open_game_day/close_game_day/record_transaction. Off
    doesn't mean "no confirmation whatsoever," just "no PIN": the frontend
    still shows a plain confirm step (see usePlainConfirm.js).
    `require_approval_close_game_day` only covers the ordinary (fully-
    reconciled) close — a chip-discrepancy close always requires sign-off
    regardless, since that's a genuine anomaly, not the routine case this
    toggle is meant to streamline.
    """

    require_approval_open_game_day = models.BooleanField(default=True)
    require_approval_close_game_day = models.BooleanField(default=True)
    require_approval_issue_chips = models.BooleanField(default=True)
    require_approval_return_chips = models.BooleanField(default=True)
    require_approval_add_tip = models.BooleanField(default=True)
    require_approval_add_rake = models.BooleanField(default=True)
    # A payout at or below this auto-approves (see services._execute_payout_transfer)
    # instead of sitting PENDING_APPROVAL for the Owner to act on.
    payout_auto_approve_threshold = models.DecimalField(max_digits=14, decimal_places=0, default=Decimal('500000'))

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return 'Club settings'


class GameDay(models.Model):
    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Open'
        CLOSED = 'CLOSED', 'Closed'

    number = models.PositiveIntegerField(unique=True)
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)

    # Which game/table this game-day is running, and the buy-in amount
    # chosen (or defaulted) for it at open time — added 2026-09-21 for the
    # "Start game-day" flow. Nullable because every GameDay before this
    # change predates the concept entirely; every new one going forward is
    # expected to set all three. See Game/Table above.
    game = models.ForeignKey(Game, on_delete=models.PROTECT, null=True, blank=True, related_name='game_days')
    table = models.ForeignKey(Table, on_delete=models.PROTECT, null=True, blank=True, related_name='game_days')
    buy_in_amount = models.DecimalField(max_digits=14, decimal_places=0, null=True, blank=True)

    # Opening requires the Owner (login or PIN) or a Floor Manager PIN — a Cashier
    # is never the authorizer, under any circumstance. Nullable because a Floor
    # Manager PIN authorizes the open without any StaffUser row to point to —
    # see opened_by_floor_manager, and CONCEPT.md's "Open Game-Day flow."
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='game_days_opened', limit_choices_to={'role': StaffUser.Role.OWNER},
    )
    opened_by_floor_manager = models.ForeignKey(
        FloorManager, on_delete=models.PROTECT, null=True, blank=True, related_name='game_days_opened',
    )

    # Closing can be done by Cashier, Owner, or a Floor Manager PIN alone.
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='game_days_closed',
    )
    closed_by_floor_manager = models.ForeignKey(
        FloorManager, on_delete=models.PROTECT, null=True, blank=True, related_name='game_days_closed',
    )

    def __str__(self):
        return f'Game-day {self.number}'


class GameDayPlayer(models.Model):
    """
    "Seated at tonight's table" — a player's presence in a game-day, tracked
    independently of whether any Transaction has been recorded for them yet.

    Added 2026-09-13, surfaced while building the Cashier frontend: the brief's
    own Buy-in flow has a real gap between "Cashier adds player, gives them
    DVA details" and "player receives chips" — a player who's been added for
    tonight but hasn't been issued anything yet still needs to show up
    somewhere. There's no way to derive that from Transaction rows alone, so
    this is a genuine new concept, not a computed view like the four ledgers.

    Rows are never deleted — they're the historical record of who was part of
    a given game-day, same as everything else in this schema. A row is
    created explicitly (the "add player" screen — see
    gaming.services.seat_player) or implicitly, as a side effect of recording
    a transaction or a payout for a player+game_day pair that hasn't been
    seated yet (get_or_create in gaming.services._ensure_seated) — so a
    player can never have activity tonight without also appearing seated.
    """

    game_day = models.ForeignKey(GameDay, on_delete=models.CASCADE, related_name='seated_players')
    player = models.ForeignKey(Player, on_delete=models.PROTECT, related_name='game_day_seats')
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='players_seated',
    )
    added_at = models.DateTimeField(auto_now_add=True)
    # Null = still active at the table. Set = "left the table" (see
    # gaming.services.leave_table) — the row itself is NOT deleted, same
    # never-delete rule as everything else here; a departed player just
    # doesn't count toward MAX_ACTIVE_PLAYERS_PER_GAME_DAY any more and is
    # shown differently in the Cashier UI. Re-seating them (seat_player /
    # _ensure_seated) clears this back to null. Added 2026-09-14.
    left_at = models.DateTimeField(null=True, blank=True)
    # A real numbered seat at the table (1..MAX_ACTIVE_PLAYERS_PER_GAME_DAY),
    # added 2026-09-17 — separate from the mere presence this model already
    # tracked. Null = seated but not assigned a specific seat yet (e.g. added
    # via the bulk "+ Add Player" flow) — assignable later via
    # gaming.services.move_seat. Leaving the table frees the seat number
    # automatically: the partial unique constraint below only applies while
    # left_at IS NULL, so a departed row's seat_number stops blocking reuse
    # without any code needing to clear it.
    seat_number = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['game_day', 'player'], name='unique_player_per_game_day_seat'),
            models.UniqueConstraint(
                fields=['game_day', 'seat_number'], condition=models.Q(left_at__isnull=True, seat_number__isnull=False),
                name='unique_active_seat_per_game_day',
            ),
        ]

    def __str__(self):
        return f'{self.player} @ game-day {self.game_day.number}'


class ConversionRate(models.Model):
    class Currency(models.TextChoices):
        USD = 'USD', 'US Dollar'
        GBP = 'GBP', 'British Pound'
        EUR = 'EUR', 'Euro'
        OTHER = 'OTHER', 'Other'

    currency = models.CharField(max_length=10, choices=Currency.choices)
    rate_to_naira = models.DecimalField(max_digits=12, decimal_places=4)
    # null = standing/default rate; set = override for that specific game-day
    game_day = models.ForeignKey(GameDay, on_delete=models.CASCADE, null=True, blank=True, related_name='fx_rates')

    # Owner (login or PIN) or a Floor Manager PIN can set this — Cashier/Accountant
    # cannot. Nullable for the same reason as GameDay.opened_by above.
    set_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='fx_rates_set', limit_choices_to={'role': StaffUser.Role.OWNER},
    )
    set_by_floor_manager = models.ForeignKey(
        FloorManager, on_delete=models.PROTECT, null=True, blank=True, related_name='fx_rates_set',
    )

    # Immutable once created — a rate change is a new row, never an edit.
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        scope = f'game-day {self.game_day.number}' if self.game_day_id else 'standing'
        return f'{self.currency} @ {self.rate_to_naira} ({scope})'


class ProfitSplitArrangement(models.Model):
    """
    "Deals" Profit Split (added 2026-09-20) — a standing arrangement on one
    player: the house covers a percentage of their buy-in (capped, on a
    recurring or one-off basis) and, when they return chips, takes a cut of
    the payout. See CONCEPT.md's Deals section and PLAN.md's entry.

    History is preserved like everywhere else in this schema — a player can
    have many arrangements over time; `is_active` marks the current one.
    Creating a new one for a player automatically deactivates any previous
    active one (see gaming.services.create_profit_split_arrangement) — only
    one is meant to apply at a time, though nothing at the DB level forbids
    two rows both being active, consistent with how this schema generally
    prefers a service-layer rule over a hard constraint where history must
    still be preserved.

    "How much the house has covered so far" is deliberately NOT a field
    here — it's always a live SUM over Transaction rows FK'd to this
    arrangement (PROFIT_SPLIT_STAKE), matching this codebase's "computed,
    not stored" balance philosophy (SCHEMA.md). See
    gaming.selectors.profit_split_status.

    Scope note: only the STAKE side (buy-in funding) is actually applied
    automatically, in gaming.services.record_transaction's CHIPS_OUT branch.
    The payout_basis/payout_split_method/custom_ratio_pct/fixed_amount/
    fixed_offset fields are captured as configuration only for now and are
    not yet wired into initiate_payout's actual math — the concept doc
    itself says the Fixed method's off-set is an input to capture, "not
    actually doing the maths for what goes to whom," and no worked example
    was given for the ratio methods either. Revisit once that math is
    actually wanted.
    """

    class ResetCadence(models.TextChoices):
        ONE_OFF = 'ONE_OFF', 'One-off'
        DAILY = 'DAILY', 'Daily'
        WEEKLY = 'WEEKLY', 'Weekly'
        MONTHLY = 'MONTHLY', 'Monthly'

    class PayoutBasis(models.TextChoices):
        BEFORE_BUYIN = 'BEFORE_BUYIN', 'Before buy-in'
        AFTER_BUYIN = 'AFTER_BUYIN', 'After buy-in'

    class PayoutSplitMethod(models.TextChoices):
        STAKE_RATIO = 'STAKE_RATIO', 'Ratio: according to stake'
        CUSTOM_RATIO = 'CUSTOM_RATIO', 'Ratio: house percentage'
        FIXED = 'FIXED', 'Fixed amount'

    player = models.ForeignKey(Player, on_delete=models.PROTECT, related_name='profit_split_arrangements')

    # Stake — how much of a buy-in the house covers. A cap of 0 effectively
    # means no real stake even with a nonzero percentage, per the concept doc.
    house_stake_pct = models.DecimalField(max_digits=5, decimal_places=2)  # 0-100
    cap_amount = models.DecimalField(max_digits=14, decimal_places=0)  # per-period ceiling
    reset_cadence = models.CharField(max_length=10, choices=ResetCadence.choices, default=ResetCadence.ONE_OFF)
    # The following three only apply when reset_cadence != ONE_OFF, and are
    # all optional — whichever is reached first ends the arrangement.
    ends_at = models.DateTimeField(null=True, blank=True)
    max_resets = models.PositiveIntegerField(null=True, blank=True)
    max_cumulative_value = models.DecimalField(max_digits=14, decimal_places=0, null=True, blank=True)

    # Payout split — configuration only for now, see docstring above.
    payout_basis = models.CharField(max_length=15, choices=PayoutBasis.choices, default=PayoutBasis.AFTER_BUYIN)
    payout_split_method = models.CharField(
        max_length=15, choices=PayoutSplitMethod.choices, default=PayoutSplitMethod.STAKE_RATIO,
    )
    custom_ratio_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    fixed_amount = models.DecimalField(max_digits=14, decimal_places=0, null=True, blank=True)
    fixed_offset = models.DecimalField(max_digits=14, decimal_places=0, null=True, blank=True)

    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='profit_splits_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'Profit split — {self.player.display_name} ({self.house_stake_pct}% stake)'


class Transaction(models.Model):
    """
    The master ledger. Every Game-day, Player game-day, Outstanding, Main
    account, and Table ledger is a filtered view over this single table —
    see SCHEMA.md.
    """

    class Type(models.TextChoices):
        CHIPS_OUT = 'CHIPS_OUT', 'Chips out'
        CHIPS_IN = 'CHIPS_IN', 'Chips in'
        # CHIPS_OFFSITE_OUT / CHIPS_OFFSITE_RETURN removed 2026-09-13 — off-site/excess
        # chips are no longer a per-incident Transaction; they're a computed
        # end-of-day variance on GameDaySummary. See CONCEPT.md's "Off-site chips."
        PAYMENT_CASH = 'PAYMENT_CASH', 'Cash payment'
        PAYMENT_TRANSFER = 'PAYMENT_TRANSFER', 'Transfer payment'
        PAYMENT_POS = 'PAYMENT_POS', 'POS payment'
        PAYMENT_DEAL = 'PAYMENT_DEAL', 'Deal'
        PAYOUT = 'PAYOUT', 'Payout to player'
        WRITE_OFF = 'WRITE_OFF', 'Write-off / credit'
        RAKE = 'RAKE', 'Rake'
        TIP = 'TIP', 'Tip'
        # Added 2026-09-20 — "Deals" Transfer: an internal move of one
        # player's positive balance to another. Always created as a linked
        # pair (see Transaction.linked_transaction) — never one row alone.
        # See gaming.services.record_deal_transfer.
        DEAL_TRANSFER_OUT = 'DEAL_TRANSFER_OUT', 'Deal transfer (out)'
        DEAL_TRANSFER_IN = 'DEAL_TRANSFER_IN', 'Deal transfer (in)'
        # Added 2026-09-20 — "Deals" Profit Split's stake side: the house's
        # own contribution toward a buy-in, never a debit against the
        # player (see selectors.DEBIT_TYPES/CREDIT_TYPES — deliberately in
        # neither, contributes 0 to player_balance). See
        # ProfitSplitArrangement's docstring and services.record_transaction.
        PROFIT_SPLIT_STAKE = 'PROFIT_SPLIT_STAKE', 'Profit split — house stake'
        # TABLE_BUY_IN/TABLE_CASH_OUT (added 2026-09-21, a second tracked
        # step between CHIPS_OUT and a Table) were REMOVED 2026-09-21 —
        # reverted back to one step: CHIPS_OUT alone represents a buy-in.
        # See PLAN.md's dated revert entry.

    class TipCategory(models.TextChoices):
        """
        Added 2026-09-17 — meaningful only when type=TIP. Values renamed
        2026-09-23 (was DEALER/SERVICE) to line up with the roster split the
        Owner actually uses — behavior of each side is unchanged, only the
        label: SERVICE_STAFF stays anonymous/aggregate exactly like every Tip
        did before this (no recipient); MASSEUSE requires a named `masseuse`
        recipient — see gaming.selectors/services for the validation, and
        accounts.models.StaffMember (role=MASSEUSE is the only role this FK
        ever points at). StaffUser briefly grew matching SERVICE/DEALER/
        MASSEUSE login roles the same day, then reverted once it was
        clarified none of the three ever actually log in — see
        StaffUser.Role's own comment.
        """
        SERVICE_STAFF = 'SERVICE_STAFF', 'Service staff'
        MASSEUSE = 'MASSEUSE', 'Masseuse'

    class Channel(models.TextChoices):
        CASHIER = 'CASHIER', 'Cashier'
        TRANSFER_DVA = 'TRANSFER_DVA', 'Transfer (DVA)'
        CASH = 'CASH', 'Cash'
        POS = 'POS', 'POS'
        CHIPS = 'CHIPS', 'Chips'
        DEAL = 'DEAL', 'Deal'
        WRITE_OFF = 'WRITE_OFF', 'Write-off'

    class Status(models.TextChoices):
        POSTED = 'POSTED', 'Posted'
        PENDING_APPROVAL = 'PENDING_APPROVAL', 'Pending approval'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'
        # The Owner approved it but the real Paystack transfer didn't go through
        # (no bank account on file, Paystack error, ...) — added 2026-09-13 when
        # payout approval started actually moving money. Distinct from REJECTED
        # (an Owner's business decision): this is an operational failure, and
        # approve_payout can be retried once the underlying issue is fixed.
        TRANSFER_FAILED = 'TRANSFER_FAILED', 'Transfer failed'

    # null = between-game-day entry (feeds the Outstanding ledger only)
    game_day = models.ForeignKey(
        GameDay, on_delete=models.PROTECT, null=True, blank=True, related_name='transactions',
    )
    player = models.ForeignKey(
        Player, on_delete=models.PROTECT, null=True, blank=True, related_name='transactions',
    )  # null only for RAKE/TIP
    type = models.CharField(max_length=25, choices=Type.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=0)  # always positive, Naira-equivalent value — whole Naira only, no kobo

    # Relevant to PAYMENT_CASH only
    currency = models.CharField(max_length=10, default='NGN')
    conversion_rate = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)  # snapshot value

    channel = models.CharField(max_length=20, choices=Channel.choices)
    notes = models.TextField(blank=True)

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='transactions_recorded',
    )  # null for webhook-auto-captured rows
    floor_manager = models.ForeignKey(
        FloorManager, on_delete=models.PROTECT, null=True, blank=True, related_name='transactions_confirmed',
    )  # set for physical-count types: CHIPS_*, PAYMENT_CASH, RAKE, TIP
    confirmed_at = models.DateTimeField(null=True, blank=True)

    # Meaningful only for type=TIP — see TipCategory. tip_category is required
    # on every TIP; masseuse is required when tip_category=MASSEUSE and
    # must be blank for SERVICE_STAFF (validated in services.record_transaction,
    # which also checks the referenced StaffMember's role is actually
    # MASSEUSE — not at the DB level — same pattern as every other
    # type-conditional field here, e.g. floor_manager/currency). PROTECT so
    # a historical tip never loses who it was attributed to, even if that
    # person is later deactivated.
    tip_category = models.CharField(max_length=15, choices=TipCategory.choices, null=True, blank=True)
    masseuse = models.ForeignKey(
        StaffMember, on_delete=models.PROTECT, null=True, blank=True, related_name='tips_received',
    )

    # Only PAYOUT uses the non-POSTED states — every payout requires Owner approval.
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.POSTED)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='transactions_approved',
        limit_choices_to={'role': StaffUser.Role.OWNER},
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    # Soft-correction trail: Cashier same-day / Owner post-close, per CONCEPT.md.
    is_voided = models.BooleanField(default=False)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='transactions_voided',
    )
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.TextField(blank=True)

    # Paystack transaction ID — unique when set, used for webhook idempotency.
    external_reference = models.CharField(max_length=100, null=True, blank=True, unique=True)

    # Set only on a DEAL_TRANSFER_OUT/DEAL_TRANSFER_IN pair (added 2026-09-20)
    # — each row points at its counterpart so a ledger listing can render
    # "Transfer to <player>" / "Transfer from <player>". SET_NULL, not
    # PROTECT: losing the link on deletion would only weaken display, never
    # the ledger math itself (each row's own amount/type stands alone).
    linked_transaction = models.OneToOneField(
        'self', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )

    # Set only on a PROFIT_SPLIT_STAKE row (and, for display, on the paired
    # CHIPS_OUT row it was split from) — see ProfitSplitArrangement.
    # PROTECT: a historical stake contribution should never lose which
    # arrangement it came from, even if that arrangement is later deactivated.
    profit_split_arrangement = models.ForeignKey(
        ProfitSplitArrangement, on_delete=models.PROTECT, null=True, blank=True, related_name='transactions',
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['game_day', 'player']),
            models.Index(fields=['player', 'created_at']),
        ]

    def __str__(self):
        return f'{self.get_type_display()} — {self.amount} ({self.player or "club"})'


class GameDaySummary(models.Model):
    """Snapshot written once at game-day close — the 'final position,' never recomputed."""

    game_day = models.OneToOneField(GameDay, on_delete=models.CASCADE, related_name='summary')
    num_players = models.PositiveIntegerField()
    chips_out_total = models.DecimalField(max_digits=14, decimal_places=0)
    chips_in_total = models.DecimalField(max_digits=14, decimal_places=0)
    rake_total = models.DecimalField(max_digits=14, decimal_places=0)
    tips_total = models.DecimalField(max_digits=14, decimal_places=0)
    # Signed: chips_out_total - chips_in_total - rake_total - tips_total.
    # Positive = unreturned/off-site chips this game-day; negative = excess chips
    # returned this game-day (off-site chips from an earlier day coming back).
    # Renamed from the never-implemented `chips_outstanding` placeholder — see
    # CONCEPT.md's "Off-site chips."
    chips_variance = models.DecimalField(max_digits=14, decimal_places=0)
    total_payments = models.DecimalField(max_digits=14, decimal_places=0)
    game_balance = models.DecimalField(max_digits=14, decimal_places=0)
    # Set only when chips_variance != 0 at close — a chip discrepancy no
    # longer blocks closing outright (2026-09-22): a player may genuinely
    # have walked off with chips, which isn't something the Cashier can
    # fix on the spot. Instead it must be ACKNOWLEDGED — a reason is
    # required, and authorization widens from Floor-Manager-only to Owner
    # (own login or PIN) OR Floor Manager PIN for that close specifically —
    # see gaming.services.close_game_day/game_day_chip_discrepancy. Blank
    # whenever chips_variance is exactly 0.
    chip_discrepancy_reason = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Summary — Game-day {self.game_day.number}'
