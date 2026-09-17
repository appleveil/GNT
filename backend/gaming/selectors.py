"""
Read-only ledger views over Transaction — see SCHEMA.md's "four ledgers, as
queries over Transaction" table. Nothing here is stored; every balance is
computed at query time.
"""

from decimal import Decimal

from django.db.models import Case, DecimalField, F, Q, Sum, Value, When, Window
from django.db.models.functions import Coalesce

from .models import GameDay, GameDayPlayer, GameDaySummary, Transaction

ZERO = Value(0, output_field=DecimalField(max_digits=14, decimal_places=2))

# Debits reduce a player's balance (chips issued, money paid out to them).
DEBIT_TYPES = {
    Transaction.Type.CHIPS_OUT,
    Transaction.Type.PAYOUT,
}
# Credits increase a player's balance (chips returned, any form of payment, write-offs).
CREDIT_TYPES = {
    Transaction.Type.CHIPS_IN,
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
    """
    signed_amount is a row's TRUE value regardless of is_voided — the ledger
    LISTING functions below (_with_running_balance's callers) want a voided
    row's real original amount to display struck through, not zeroed out. The
    BALANCE/aggregate functions (player_balance, player_game_day_balance,
    game_day_summary_data, dashboard_totals, ...) call this directly on a
    queryset they've already filtered to is_voided=False themselves, so a
    voided row never actually reaches Sum() in those — this annotation being
    voided-agnostic is safe there too.
    """
    return queryset.annotate(
        signed_amount=Case(
            When(type__in=DEBIT_TYPES, then=-F('amount')),
            When(type__in=CREDIT_TYPES, then=F('amount')),
            default=ZERO,
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )
    )


def _with_running_balance(queryset, partition_by=None):
    """
    Found live 2026-09-14: a voided row was being filtered out of every
    ledger listing entirely, contradicting HiFiVoidEntry.dc.html's own text
    ("This stays visible in the ledger... for audit — it isn't deleted") and
    this file's own frozen hi-fi mockups (HiFiGameDayLedger.dc.html shows a
    voided row inline, struck through, "VOIDED" in place of a balance).
    Callers must stop filtering is_voided=False out of their queryset — a
    voided row still needs to be a row here. Its real amount stays visible
    via signed_amount (see _with_signed_amount), but it must contribute
    ZERO to the running balance, via this separate `contribution` annotation
    the window function sums over instead of summing signed_amount directly.
    """
    queryset = _with_signed_amount(queryset).order_by('created_at')
    queryset = queryset.annotate(
        contribution=Case(
            When(is_voided=True, then=ZERO),
            default=F('signed_amount'),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )
    )
    return queryset.annotate(
        running_balance=Window(
            expression=Sum('contribution'),
            partition_by=partition_by,
            order_by=F('created_at').asc(),
        )
    )


def game_day_ledger(game_day):
    """
    All chip/payment activity for one game-day, in order, with the CLUB'S
    running balance — a single cumulative total across every player's
    interleaved transactions, matching CONCEPT.md's "Game-day ledger" worked
    example exactly (see LedgerMathTests). This is NOT any individual
    player's balance — see game_day_activity_feed below for that.
    """
    # Voided rows stay in (see _with_running_balance) — not filtered here.
    qs = Transaction.objects.filter(game_day=game_day).exclude(type__in=EXCLUDED_FROM_GAME_DAY_LEDGER)
    return _with_running_balance(qs)


def game_day_activity_feed(game_day):
    """
    Same rows as game_day_ledger (all players, ordered by time), but each
    row's running_balance is scoped to THAT ROW'S PLAYER only — added
    2026-09-14 for the Cashier's live "today's activity" feed on the Active
    Game-Day working screen, where "bal" next to a player's name means their
    own balance, not the club's aggregate net position. Conflating the two
    was a real bug: game_day_ledger's unpartitioned running_balance is
    correct for (and only for) the separate, spec'd Game-Day Ledger view.
    """
    # Voided rows stay in (see _with_running_balance) — not filtered here.
    qs = Transaction.objects.filter(game_day=game_day).exclude(type__in=EXCLUDED_FROM_GAME_DAY_LEDGER)
    return _with_running_balance(qs, partition_by=[F('player')])


def player_game_day_ledger(game_day, player):
    """One player's activity within a single game-day. Voided rows stay in — see _with_running_balance."""
    qs = Transaction.objects.filter(game_day=game_day, player=player).exclude(
        type__in=EXCLUDED_FROM_GAME_DAY_LEDGER
    )
    return _with_running_balance(qs)


def outstanding_ledger(player=None):
    """Between-game-day activity (payments/deals) — running balance kept per player.
    Voided rows stay in — see _with_running_balance."""
    qs = Transaction.objects.filter(game_day__isnull=True)
    if player is not None:
        qs = qs.filter(player=player)
    return _with_running_balance(qs, partition_by=[F('player')])


def main_account_ledger():
    """Only DVA sweep-ins and payouts — the rows that actually touch the bank.
    Voided rows stay in — see _with_running_balance."""
    qs = Transaction.objects.filter(MAIN_ACCOUNT_FILTER)
    return _with_running_balance(qs)


def player_balance(player):
    """A player's lifetime balance across every game-day and outstanding period."""
    qs = _with_signed_amount(Transaction.objects.filter(player=player, is_voided=False))
    return qs.aggregate(total=Coalesce(Sum('signed_amount'), ZERO))['total']


def player_game_day_balance(player, game_day):
    """
    A player's signed balance within a single game-day only — not lifetime.
    Feeds both chips-limit enforcement (current game-day debt) and the
    Cashier-facing "today's balance" view (see CONCEPT.md's "Chips limit" and
    "Cashier player-history visibility").
    """
    qs = _with_signed_amount(Transaction.objects.filter(game_day=game_day, player=player, is_voided=False))
    return qs.aggregate(total=Coalesce(Sum('signed_amount'), ZERO))['total']


def main_account_balance():
    qs = _with_signed_amount(Transaction.objects.filter(MAIN_ACCOUNT_FILTER, is_voided=False))
    return qs.aggregate(total=Coalesce(Sum('signed_amount'), ZERO))['total']


def current_open_game_day():
    """The most recently opened game-day still in progress, or None if none is open."""
    return GameDay.objects.filter(status=GameDay.Status.OPEN).order_by('-started_at').first()


def game_day_players(game_day):
    """
    Players seated at a given game-day (see GameDayPlayer) — the Cashier-facing
    Players list, added 2026-09-13. Distinct from the full club roster
    (accounts.PlayerSerializer's plain queryset), which is still what a
    "seat an existing player" search should use. Includes departed players
    (left_at set) — "total" seated, not "active"; see active_game_day_players_count.
    """
    return GameDayPlayer.objects.filter(game_day=game_day).select_related('player').order_by('added_at')


def active_game_day_players_count(game_day):
    """Seated AND still at the table (left_at is null) — what
    gaming.services.MAX_ACTIVE_PLAYERS_PER_GAME_DAY caps. Added 2026-09-14."""
    return GameDayPlayer.objects.filter(game_day=game_day, left_at__isnull=True).count()


# Mirrors gaming.services.MAX_ACTIVE_PLAYERS_PER_GAME_DAY — same duplicated-
# constant convention already used by AddPlayerModal.vue's MAX_ACTIVE_PLAYERS,
# to avoid a circular import (services.py already imports this module).
_MAX_SEAT_NUMBER = 9


def free_seat_numbers(game_day):
    """
    Every seat number (1..MAX) NOT currently held by an active (left_at is
    null) seat — what the Cashier's "empty seat" pills are built from, and
    what a move/swap picker offers as valid destinations. Added 2026-09-17.
    """
    occupied = set(
        GameDayPlayer.objects.filter(
            game_day=game_day, left_at__isnull=True, seat_number__isnull=False,
        ).values_list('seat_number', flat=True)
    )
    return sorted(set(range(1, _MAX_SEAT_NUMBER + 1)) - occupied)


PAYMENT_TYPES = {
    Transaction.Type.PAYMENT_CASH,
    Transaction.Type.PAYMENT_TRANSFER,
    Transaction.Type.PAYMENT_POS,
    Transaction.Type.PAYMENT_DEAL,
}


def _sum_amount(qs):
    return qs.aggregate(total=Coalesce(Sum('amount'), ZERO))['total']


def game_day_summary_data(game_day):
    """
    Everything GameDaySummary needs, computed fresh from Transaction — called once,
    at close, by gaming.services.close_game_day. Never called live/read-only; a
    closed game-day's summary is a frozen snapshot, not recomputed on each read.
    """
    txns = Transaction.objects.filter(game_day=game_day, is_voided=False)
    chips_out_total = _sum_amount(txns.filter(type=Transaction.Type.CHIPS_OUT))
    chips_in_total = _sum_amount(txns.filter(type=Transaction.Type.CHIPS_IN))
    rake_total = _sum_amount(txns.filter(type=Transaction.Type.RAKE))
    tips_total = _sum_amount(txns.filter(type=Transaction.Type.TIP))
    total_payments = _sum_amount(txns.filter(type__in=PAYMENT_TYPES))
    num_players = txns.filter(player__isnull=False).values('player').distinct().count()
    game_balance = _with_signed_amount(txns.exclude(type__in=EXCLUDED_FROM_GAME_DAY_LEDGER)).aggregate(
        total=Coalesce(Sum('signed_amount'), ZERO)
    )['total']
    return {
        'num_players': num_players,
        'chips_out_total': chips_out_total,
        'chips_in_total': chips_in_total,
        'rake_total': rake_total,
        'tips_total': tips_total,
        'chips_variance': chips_out_total - chips_in_total - rake_total - tips_total,
        'total_payments': total_payments,
        'game_balance': game_balance,
    }


def outstanding_chips_total():
    """
    Club-wide unreturned-chips liability — the live running sum of every closed
    game-day's variance (positive days add to it, negative/excess days pay it
    down). See CONCEPT.md's "Off-site chips."
    """
    return GameDaySummary.objects.aggregate(total=Coalesce(Sum('chips_variance'), ZERO))['total']


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
