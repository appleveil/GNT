from django.conf import settings
from django.db import models

from accounts.models import FloorManager, Player, StaffUser


class GameDay(models.Model):
    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Open'
        CLOSED = 'CLOSED', 'Closed'

    number = models.PositiveIntegerField(unique=True)
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)

    # Opening requires the Owner or a Floor Manager PIN — Cashier can't open one solo.
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='game_days_opened',
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

    # Owner or a Floor Manager PIN can set this — Cashier/Accountant cannot.
    set_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='fx_rates_set')
    set_by_floor_manager = models.ForeignKey(
        FloorManager, on_delete=models.PROTECT, null=True, blank=True, related_name='fx_rates_set',
    )

    # Immutable once created — a rate change is a new row, never an edit.
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        scope = f'game-day {self.game_day.number}' if self.game_day_id else 'standing'
        return f'{self.currency} @ {self.rate_to_naira} ({scope})'


class Transaction(models.Model):
    """
    The master ledger. Every Game-day, Player game-day, Outstanding, and Main
    account ledger is a filtered view over this single table — see SCHEMA.md.
    """

    class Type(models.TextChoices):
        CHIPS_OUT = 'CHIPS_OUT', 'Chips out'
        CHIPS_IN = 'CHIPS_IN', 'Chips in'
        CHIPS_OFFSITE_OUT = 'CHIPS_OFFSITE_OUT', 'Chips taken off-site'
        CHIPS_OFFSITE_RETURN = 'CHIPS_OFFSITE_RETURN', 'Off-site chips returned'
        PAYMENT_CASH = 'PAYMENT_CASH', 'Cash payment'
        PAYMENT_TRANSFER = 'PAYMENT_TRANSFER', 'Transfer payment'
        PAYMENT_POS = 'PAYMENT_POS', 'POS payment'
        PAYMENT_DEAL = 'PAYMENT_DEAL', 'Deal'
        PAYOUT = 'PAYOUT', 'Payout to player'
        WRITE_OFF = 'WRITE_OFF', 'Write-off / credit'
        RAKE = 'RAKE', 'Rake'
        TIP = 'TIP', 'Tip'

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

    # null = between-game-day entry (feeds the Outstanding ledger only)
    game_day = models.ForeignKey(
        GameDay, on_delete=models.PROTECT, null=True, blank=True, related_name='transactions',
    )
    player = models.ForeignKey(
        Player, on_delete=models.PROTECT, null=True, blank=True, related_name='transactions',
    )  # null only for RAKE/TIP
    type = models.CharField(max_length=25, choices=Type.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)  # always positive, Naira-equivalent value

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
    chips_out_total = models.DecimalField(max_digits=14, decimal_places=2)
    chips_in_total = models.DecimalField(max_digits=14, decimal_places=2)
    rake_total = models.DecimalField(max_digits=14, decimal_places=2)
    tips_total = models.DecimalField(max_digits=14, decimal_places=2)
    chips_outstanding = models.DecimalField(max_digits=14, decimal_places=2)
    total_payments = models.DecimalField(max_digits=14, decimal_places=2)
    game_balance = models.DecimalField(max_digits=14, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Summary — Game-day {self.game_day.number}'
