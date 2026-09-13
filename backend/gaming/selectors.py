"""
Read-only ledger views over Transaction — see SCHEMA.md's "four ledgers, as
queries over Transaction" table. Nothing here is stored; every balance is
computed at query time.
"""

from decimal import Decimal

from django.db.models import Case, DecimalField, F, Q, Sum, Value, When, Window
from django.db.models.functions import Coalesce

from .models import Transaction

ZERO = Value(0, output_field=DecimalField(max_digits=14, decimal_places=2))

# Debits reduce a player's balance (chips issued, chips taken off-site, money paid out to them).
DEBIT_TYPES = {
    Transaction.Type.CHIPS_OUT,
    Transaction.Type.CHIPS_OFFSITE_OUT,
    Transaction.Type.PAYOUT,
}
# Credits increase a player's balance (chips returned, any form of payment, write-offs).
CREDIT_TYPES = {
    Transaction.Type.CHIPS_IN,
    Transaction.Type.CHIPS_OFFSITE_RETURN,
    Transaction.Type.PAYMENT_CASH,
    Transaction.Type.PAYMENT_TRANSFER,
    Transaction.Type.PAYMENT_POS,
    Transaction.Type.PAYMENT_DEAL,
    Transaction.Type.WRITE_OFF,
}
# Rake/tips have no player and never touch a player or game-day balance.
EXCLUDED_FROM_GAME_DAY_LEDGER = {Transaction.Type.RAKE, Transaction.Type.TIP}

# The only rows that actually touch the bank (see SCHEMA.md's Main account ledger filter).
MAIN_ACCOUNT_FILTER = Q(channel=Transaction.Channel.TRANSFER_DVA) | Q(type=Transaction.Type.PAYOUT)


def _with_signed_amount(queryset):
    return queryset.annotate(
        signed_amount=Case(
            When(type__in=DEBIT_TYPES, then=-F('amount')),
            When(type__in=CREDIT_TYPES, then=F('amount')),
            default=ZERO,
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )
    )


def _with_running_balance(queryset, partition_by=None):
    queryset = _with_signed_amount(queryset).order_by('created_at')
    return queryset.annotate(
        running_balance=Window(
            expression=Sum('signed_amount'),
            partition_by=partition_by,
            order_by=F('created_at').asc(),
        )
    )


def game_day_ledger(game_day):
    """All chip/payment activity for one game-day, in order, with the club's running balance."""
    qs = Transaction.objects.filter(game_day=game_day, is_voided=False).exclude(
        type__in=EXCLUDED_FROM_GAME_DAY_LEDGER
    )
    return _with_running_balance(qs)


def player_game_day_ledger(game_day, player):
    """One player's activity within a single game-day."""
    qs = Transaction.objects.filter(game_day=game_day, player=player, is_voided=False).exclude(
        type__in=EXCLUDED_FROM_GAME_DAY_LEDGER
    )
    return _with_running_balance(qs)


def outstanding_ledger(player=None):
    """Between-game-day activity (payments/deals) — running balance kept per player."""
    qs = Transaction.objects.filter(game_day__isnull=True, is_voided=False)
    if player is not None:
        qs = qs.filter(player=player)
    return _with_running_balance(qs, partition_by=[F('player')])


def main_account_ledger():
    """Only DVA sweep-ins and payouts — the rows that actually touch the bank."""
    qs = Transaction.objects.filter(MAIN_ACCOUNT_FILTER, is_voided=False)
    return _with_running_balance(qs)


def player_balance(player):
    """A player's lifetime balance across every game-day and outstanding period."""
    qs = _with_signed_amount(Transaction.objects.filter(player=player, is_voided=False))
    return qs.aggregate(total=Coalesce(Sum('signed_amount'), ZERO))['total']


def main_account_balance():
    qs = _with_signed_amount(Transaction.objects.filter(MAIN_ACCOUNT_FILTER, is_voided=False))
    return qs.aggregate(total=Coalesce(Sum('signed_amount'), ZERO))['total']


def dashboard_totals():
    """
    (total owed BY players, total owed TO players, debtor count) across every
    player, in a single grouped query — feeds the Accountant/Owner dashboard.
    """
    per_player = (
        _with_signed_amount(Transaction.objects.filter(is_voided=False, player__isnull=False))
        .values('player')
        .annotate(balance=Sum('signed_amount'))
    )
    total_debt = sum((-row['balance'] for row in per_player if row['balance'] < 0), Decimal('0'))
    total_credit = sum((row['balance'] for row in per_player if row['balance'] > 0), Decimal('0'))
    debtor_count = sum(1 for row in per_player if row['balance'] < 0)
    return total_debt, total_credit, debtor_count
