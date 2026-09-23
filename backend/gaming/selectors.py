"""
Read-only ledger views over Transaction — see SCHEMA.md's "four ledgers, as
queries over Transaction" table. Nothing here is stored; every balance is
computed at query time.
"""

from decimal import Decimal

from django.db.models import Case, DecimalField, F, Q, Sum, Value, When, Window
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import GameDay, GameDayPlayer, GameDaySummary, ProfitSplitArrangement, Transaction

ZERO = Value(0, output_field=DecimalField(max_digits=14, decimal_places=2))

# Debits reduce a player's balance (chips issued, money paid out to them).
DEBIT_TYPES = {
    Transaction.Type.CHIPS_OUT,
    Transaction.Type.PAYOUT,
    Transaction.Type.DEAL_TRANSFER_OUT,
}
# Credits increase a player's balance (chips returned, any form of payment, write-offs).
CREDIT_TYPES = {
    Transaction.Type.CHIPS_IN,
    Transaction.Type.PAYMENT_CASH,
    Transaction.Type.PAYMENT_TRANSFER,
    Transaction.Type.PAYMENT_POS,
    Transaction.Type.PAYMENT_DEAL,
    Transaction.Type.WRITE_OFF,
    Transaction.Type.DEAL_TRANSFER_IN,
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
    # `id` as a tiebreaker — two rows created in the same request (e.g.
    # seating auto-issuing a CHIPS_OUT) can share a created_at down to the
    # microsecond; `id` guarantees a stable, insertion-order sort instead of
    # leaving ties to the database's whim.
    queryset = _with_signed_amount(queryset).order_by('created_at', 'id')
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
            order_by=[F('created_at').asc(), F('id').asc()],
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


def player_has_failed_payout(player, game_day):
    """
    Whether this player currently has a payout stuck at TRANSFER_FAILED
    tonight — Owner approved it but the real transfer didn't go through
    (see gaming.services.approve_payout). A Cashier who initiated the
    payout otherwise has no way to learn this short of asking the Owner,
    so it's surfaced as a status badge on the Cashier's player panel
    (see GameDaySeatedPlayerSerializer.get_payout_failed). Clears itself
    once the Owner retries approve_payout successfully (APPROVED) or
    rejects it (REJECTED + is_voided) — both move the same Transaction
    row off TRANSFER_FAILED, so no separate "acknowledge" step is needed.
    Added 2026-09-23.
    """
    return Transaction.objects.filter(
        game_day=game_day, player=player, type=Transaction.Type.PAYOUT,
        status=Transaction.Status.TRANSFER_FAILED, is_voided=False,
    ).exists()


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
    max_active_players caps. Added 2026-09-14."""
    return GameDayPlayer.objects.filter(game_day=game_day, left_at__isnull=True).count()


# Fallback ONLY for a game-day with no `game` set at all — pre-2026-09-21
# historical rows, from before Game.max_players existed. Every game-day
# opened through the "Start game-day" flow has a `game`, so this is never
# hit going forward; kept for the same reason GameDay.game/table are
# nullable in the first place. Was a single hard-coded 9 shared by every
# game (gaming.services.MAX_ACTIVE_PLAYERS_PER_GAME_DAY, and a duplicate
# _MAX_SEAT_NUMBER here) — see Game.max_players' docstring.
_DEFAULT_MAX_PLAYERS = 9


def max_active_players(game_day):
    """
    The active-seat cap for THIS game-day — Table.max_players (Owner/Floor-
    Manager-editable, added 2026-09-23) when the table has its own override,
    else Game.max_players for the game actually being played tonight (Texas
    Hold'em 9, Omaha 8, ...), else _DEFAULT_MAX_PLAYERS for a legacy
    game-day with no `game` set. The one place both gaming.services
    (seating/moving a player) and free_seat_numbers below resolve the cap
    through, so the two can never drift apart the way the old duplicated
    constants could. Added 2026-09-21.
    """
    if game_day.table_id and game_day.table.max_players:
        return game_day.table.max_players
    if game_day.game_id:
        return game_day.game.max_players
    return _DEFAULT_MAX_PLAYERS


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
    return sorted(set(range(1, max_active_players(game_day) + 1)) - occupied)


PAYMENT_TYPES = {
    Transaction.Type.PAYMENT_CASH,
    Transaction.Type.PAYMENT_TRANSFER,
    Transaction.Type.PAYMENT_POS,
    Transaction.Type.PAYMENT_DEAL,
}


def _sum_amount(qs):
    return qs.aggregate(total=Coalesce(Sum('amount'), ZERO))['total']


def game_day_chips_totals(game_day):
    """
    Live chips out/in/rake/tip totals for one game-day (not the frozen
    close-time summary — see game_day_summary_data for that). Added
    2026-09-22 so record_transaction can enforce "chips returned can never
    exceed chips issued" before a new CHIPS_IN posts, catching a miscount on
    the spot rather than only at close (where chips_variance would
    otherwise be the first place it surfaced).

    rake_total/tips_total added 2026-09-23: rake and tips are chips that
    legitimately never come back as a CHIPS_IN (skimmed from play / handed
    to staff — same reasoning as game_day_summary_data's chips_variance,
    which this now mirrors) — a game-day-wide cap that didn't net these out
    would let more chips be "returned" than could physically still be on
    the table.
    """
    txns = Transaction.objects.filter(game_day=game_day, is_voided=False)
    return {
        'chips_out_total': _sum_amount(txns.filter(type=Transaction.Type.CHIPS_OUT)),
        'chips_in_total': _sum_amount(txns.filter(type=Transaction.Type.CHIPS_IN)),
        'rake_total': _sum_amount(txns.filter(type=Transaction.Type.RAKE)),
        'tips_total': _sum_amount(txns.filter(type=Transaction.Type.TIP)),
    }


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


def total_rake_this_month():
    """
    Club-wide RAKE total since the start of the current calendar month
    (Africa/Lagos — settings.TIME_ZONE), across every game-day, open or
    closed alike (unlike outstanding_chips_total, which only ever sees
    closed game-days via GameDaySummary — rake posts live as RAKE
    transactions the moment it's recorded, no close needed to count here).
    Feeds the Owner Dashboard's "Total rake this month" stat card, which
    replaced "Unreturned chips" there on 2026-09-23 — Accountant's own
    dashboard still gets outstanding_chips_total, unchanged.
    """
    start_of_month = timezone.localtime(timezone.now()).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0,
    )
    return _sum_amount(
        Transaction.objects.filter(type=Transaction.Type.RAKE, is_voided=False, created_at__gte=start_of_month)
    )


def dashboard_totals():
    """
    (total owed BY players, total owed TO players, debtor count, creditor
    count) across every player, in a single grouped query — feeds the
    Accountant/Owner dashboard. creditor_count added 2026-09-23 — the
    "Owed to players" stat card was reading debtor_count's own sibling
    number off a hardcoded "7 players" in DashboardView.vue until then; it
    now comes from here like everything else on that card.
    """
    per_player = (
        _with_signed_amount(Transaction.objects.filter(is_voided=False, player__isnull=False))
        .values('player')
        .annotate(balance=Sum('signed_amount'))
    )
    total_debt = sum((-row['balance'] for row in per_player if row['balance'] < 0), Decimal('0'))
    total_credit = sum((row['balance'] for row in per_player if row['balance'] > 0), Decimal('0'))
    debtor_count = sum(1 for row in per_player if row['balance'] < 0)
    creditor_count = sum(1 for row in per_player if row['balance'] > 0)
    return total_debt, total_credit, debtor_count, creditor_count


def _profit_split_periods_elapsed(arrangement, now):
    """
    How many complete reset-periods have passed since an arrangement was
    created, and when the CURRENT one started — computed live from
    created_at + cadence, never stored (see ProfitSplitArrangement's
    docstring). A ONE_OFF arrangement has exactly one period spanning its
    whole lifetime. Months are real calendar months (via dateutil), not a
    fixed 30-day chunk — weeks/days are fixed-length, which is unambiguous
    for them.
    """
    Cadence = ProfitSplitArrangement.ResetCadence
    start = arrangement.created_at
    if arrangement.reset_cadence == Cadence.ONE_OFF:
        return 0, start
    if arrangement.reset_cadence == Cadence.DAILY:
        from datetime import timedelta
        step = timedelta(days=1)
    elif arrangement.reset_cadence == Cadence.WEEKLY:
        from datetime import timedelta
        step = timedelta(weeks=1)
    elif arrangement.reset_cadence == Cadence.MONTHLY:
        from dateutil.relativedelta import relativedelta
        periods, period_start = 0, start
        while period_start + relativedelta(months=1) <= now:
            period_start += relativedelta(months=1)
            periods += 1
        return periods, period_start
    else:
        raise ValueError(f'Unknown reset cadence: {arrangement.reset_cadence}')
    periods = max(0, (now - start) // step)
    return periods, start + periods * step


def profit_split_status(arrangement, now=None):
    """
    Everything needed to enforce/display a Profit Split arrangement,
    computed live — never stored, matching this file's "balances are
    computed, not stored" philosophy (SCHEMA.md). "How much the house has
    covered" is a live SUM over PROFIT_SPLIT_STAKE rows FK'd to this
    arrangement, never a mutable counter.
    """
    now = now or timezone.now()
    periods_elapsed, period_start = _profit_split_periods_elapsed(arrangement, now)

    stake_qs = Transaction.objects.filter(
        profit_split_arrangement=arrangement, type=Transaction.Type.PROFIT_SPLIT_STAKE, is_voided=False,
    )
    covered_this_period = stake_qs.filter(created_at__gte=period_start).aggregate(
        total=Coalesce(Sum('amount'), ZERO),
    )['total']
    cumulative_covered = stake_qs.aggregate(total=Coalesce(Sum('amount'), ZERO))['total']

    exhausted_reason = None
    if arrangement.ends_at and now >= arrangement.ends_at:
        exhausted_reason = 'end date reached'
    elif arrangement.max_resets is not None and periods_elapsed >= arrangement.max_resets:
        exhausted_reason = 'max resets reached'
    elif arrangement.max_cumulative_value is not None and cumulative_covered >= arrangement.max_cumulative_value:
        exhausted_reason = 'max cumulative value reached'

    if exhausted_reason is not None:
        available_this_period = Decimal('0')
    else:
        available_this_period = max(arrangement.cap_amount - covered_this_period, Decimal('0'))
        if arrangement.max_cumulative_value is not None:
            cumulative_remaining = max(arrangement.max_cumulative_value - cumulative_covered, Decimal('0'))
            available_this_period = min(available_this_period, cumulative_remaining)

    return {
        'period_start': period_start,
        'periods_elapsed': periods_elapsed,
        'covered_this_period': covered_this_period,
        'cumulative_covered': cumulative_covered,
        'is_exhausted': exhausted_reason is not None,
        'exhausted_reason': exhausted_reason,
        'available_stake_this_period': available_this_period,
    }
