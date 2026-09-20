"""
Authorization rules and state-changing actions, kept out of views.py so each
rule is independently callable/testable. See CONCEPT.md's "Scope decisions"
and "Floor Manager" sections for the rules encoded here.
"""

from decimal import Decimal

from django.db import transaction as db_transaction
from django.utils import timezone

from accounts.models import FloorManager, Player, StaffUser

from . import selectors
from .exceptions import AuthorizationError, InvalidStateError, TableFullError
from .models import ConversionRate, GameDay, GameDayPlayer, GameDaySummary, ProfitSplitArrangement, Transaction

# A real table only has so many seats. Revised 2026-09-15: a departed player
# returns ONLY by being issued chips (CHIPS_OUT) — never a bare re-add — and
# that revival is capped exactly like creating a brand-new seat is. See
# _ensure_seated's `revive` param and PLAN.md's "leave the table" entry.
MAX_ACTIVE_PLAYERS_PER_GAME_DAY = 9

# The one exception to "a closed game-day accepts no new entries" — see
# _require_open_game_day. A Deal/write-off made right after a game-day closes
# (it really happened during it, entered a few minutes late) can still be
# attributed to that specific night, never an older one.
DEAL_TYPES = {Transaction.Type.PAYMENT_DEAL, Transaction.Type.WRITE_OFF}


def _require_open_game_day(game_day, type=None):
    """
    Enforced server-side, not left to whichever frontend is calling in: a client
    can go stale (another device closed this game-day moments ago) or simply not
    be the sanctioned UI at all, so this can't be a client-side-only rule.

    One narrow exception (2026-09-15): a Deal/write-off (`type` in DEAL_TYPES)
    may target the game-day that JUST closed — the single most-recently-closed
    one, never any older one, and no other transaction type — matching the
    choice RosterDetailView.vue's Deal form actually offers the Owner.
    """
    if game_day is None or game_day.status == GameDay.Status.OPEN:
        return
    if type in DEAL_TYPES:
        last_closed = GameDay.objects.filter(status=GameDay.Status.CLOSED).order_by('-number').first()
        if last_closed is not None and last_closed.pk == game_day.pk:
            return
    raise InvalidStateError(f'Game-day {game_day.number} is closed — it cannot accept new entries.')


def _resolve_floor_manager(floor_manager_id, pin):
    """Returns the authorizing FloorManager, or None if no PIN was offered at all."""
    if not floor_manager_id or not pin:
        return None
    try:
        fm = FloorManager.objects.get(pk=floor_manager_id, is_active=True)
    except FloorManager.DoesNotExist:
        raise AuthorizationError('Unknown or inactive Floor Manager.')
    if not fm.check_pin(pin):
        raise AuthorizationError('Incorrect Floor Manager PIN.')
    return fm


def _resolve_owner_pin(owner_id, pin):
    """
    Returns the authorizing Owner (validated by their own PIN, not the operator's
    session), or None if no PIN was offered at all. Mirrors _resolve_floor_manager.
    """
    if not owner_id or not pin:
        return None
    try:
        owner = StaffUser.objects.get(pk=owner_id, role=StaffUser.Role.OWNER, is_active=True)
    except StaffUser.DoesNotExist:
        raise AuthorizationError('Unknown or inactive Owner.')
    if not owner.check_pin(pin):
        raise AuthorizationError('Incorrect Owner PIN.')
    return owner


def _resolve_owner_or_floor_manager(
    operator, floor_manager_id=None, floor_manager_pin=None, owner_id=None, owner_pin=None, action='This',
):
    """
    Shared by open_game_day and set_conversion_rate — both are Owner-or-Floor-
    Manager-gated. A Cashier is never the authorizer, even as the session that
    submits someone else's PIN: attribution comes from whichever PIN/login
    resolves here, never from `operator` beyond the operator.role == OWNER
    shortcut (a real Owner login needs no PIN). Returns (owner_or_None, fm_or_None).
    """
    fm = _resolve_floor_manager(floor_manager_id, floor_manager_pin)
    if operator.role == StaffUser.Role.OWNER:
        return operator, fm if fm else None
    owner = _resolve_owner_pin(owner_id, owner_pin) if fm is None else None
    if owner is None and fm is None:
        raise AuthorizationError(f'{action} requires the Owner (login or PIN) or a Floor Manager PIN.')
    return owner, fm


def open_game_day(
    number, started_at, operator, floor_manager_id=None, floor_manager_pin=None,
    owner_id=None, owner_pin=None,
):
    """
    Owner (own login, or PIN) or a Floor Manager PIN authorizes this — a Cashier
    is never the authorizer, under any circumstance. See CONCEPT.md's "Open
    Game-Day flow."
    """
    owner, fm = _resolve_owner_or_floor_manager(
        operator, floor_manager_id, floor_manager_pin, owner_id, owner_pin, action='Opening a game-day',
    )
    return GameDay.objects.create(
        number=number, started_at=started_at, status=GameDay.Status.OPEN,
        opened_by=owner, opened_by_floor_manager=fm,
    )


def close_game_day(game_day, operator, floor_manager_id=None, floor_manager_pin=None):
    """
    Cashier, Owner, or a Floor Manager PIN can each close a game-day alone.
    Writes the GameDaySummary snapshot (incl. the chips variance) once, here —
    it's never recomputed after this.
    """
    fm = _resolve_floor_manager(floor_manager_id, floor_manager_pin)
    allowed_roles = {StaffUser.Role.CASHIER, StaffUser.Role.OWNER}
    if operator.role not in allowed_roles and fm is None:
        raise AuthorizationError('Closing a game-day requires the Cashier, Owner, or a Floor Manager PIN.')
    game_day.status = GameDay.Status.CLOSED
    game_day.ended_at = timezone.now()
    game_day.closed_by = operator
    game_day.closed_by_floor_manager = fm
    game_day.save(update_fields=['status', 'ended_at', 'closed_by', 'closed_by_floor_manager'])
    GameDaySummary.objects.update_or_create(
        game_day=game_day, defaults=selectors.game_day_summary_data(game_day),
    )
    return game_day


def set_conversion_rate(
    currency, rate_to_naira, operator, game_day=None, floor_manager_id=None, floor_manager_pin=None,
    owner_id=None, owner_pin=None,
):
    """Owner (own login, or PIN) or a Floor Manager PIN. Cashier/Accountant cannot."""
    owner, fm = _resolve_owner_or_floor_manager(
        operator, floor_manager_id, floor_manager_pin, owner_id, owner_pin, action='Setting the FX rate',
    )
    return ConversionRate.objects.create(
        currency=currency, rate_to_naira=rate_to_naira, game_day=game_day,
        set_by=owner, set_by_floor_manager=fm,
    )


def _ensure_seated(game_day, player, operator=None, revive=False):
    """
    Idempotently ensures `player` has a GameDayPlayer row for `game_day` — a
    no-op for the between-game-day case (game_day is None) or rake/tip
    (player is None); called from both record_transaction and
    initiate_payout so a player can never have real activity tonight without
    also showing up in the Cashier's seated-players list.

    `revive` (added 2026-09-15, default False) is the ONLY thing that clears
    a departed player's left_at — pass True only for a CHIPS_OUT
    (record_transaction). Every other transaction type, and initiate_payout,
    record normally against a departed player without bringing them back to
    the table (e.g. settling a Return-Chips owed from before they left).
    "Return to Table" as a bare re-add is gone — seat_player no longer calls
    this for an already-seated-but-departed player at all (see below).

    Creating a brand-new seat (never seated tonight, regardless of who's
    calling) is always capped, same as a revival — closes a gap where
    record_transaction/initiate_payout could otherwise seat a 10th active
    player without ever going through seat_player's check.
    """
    if game_day is None or player is None:
        return
    seat = GameDayPlayer.objects.filter(game_day=game_day, player=player).first()
    if seat is None:
        if selectors.active_game_day_players_count(game_day) >= MAX_ACTIVE_PLAYERS_PER_GAME_DAY:
            raise TableFullError(
                f'The table is full ({MAX_ACTIVE_PLAYERS_PER_GAME_DAY} active players right now) — '
                f"{player.display_name} wasn't seated. Try again once someone leaves the table.",
                player=player,
            )
        GameDayPlayer.objects.create(game_day=game_day, player=player, added_by=operator)
    elif revive and seat.left_at is not None:
        if selectors.active_game_day_players_count(game_day) >= MAX_ACTIVE_PLAYERS_PER_GAME_DAY:
            raise TableFullError(
                f'The table is full ({MAX_ACTIVE_PLAYERS_PER_GAME_DAY} active players right now) — '
                f"{player.display_name} wasn't seated. Try again once someone leaves the table.",
                player=player,
            )
        seat.left_at = None
        seat.save(update_fields=['left_at'])


def _validate_seat_number(game_day, seat_number, exclude_player=None):
    """
    Raises a clean InvalidStateError for an out-of-range or already-taken
    seat, rather than letting the DB's partial-unique constraint (see
    GameDayPlayer.Meta) surface as a raw IntegrityError. `exclude_player`
    lets a player "take" the seat they're already sitting in (a no-op move).
    """
    if not (1 <= seat_number <= MAX_ACTIVE_PLAYERS_PER_GAME_DAY):
        raise InvalidStateError(f'Seat number must be between 1 and {MAX_ACTIVE_PLAYERS_PER_GAME_DAY}.')
    occupied = GameDayPlayer.objects.filter(game_day=game_day, seat_number=seat_number, left_at__isnull=True)
    if exclude_player is not None:
        occupied = occupied.exclude(player=exclude_player)
    if occupied.exists():
        raise InvalidStateError(f'Seat {seat_number} is already taken.')


def seat_player(game_day, operator, player=None, player_fields=None, seat_number=None):
    """
    The explicit "add a player for tonight" action — see CONCEPT.md's Buy-in
    flow. Either pass an existing `player`, or `player_fields` to create a new
    club-wide Player record and seat it in one call. Idempotent: seating an
    already-active player is a no-op, not an error.

    Registering a brand-new player (player_fields) always succeeds, even if
    the table is full — only seating them for tonight is capped (via
    _ensure_seated). Revised 2026-09-15: this can no longer revive a departed
    player at all — that's issue-chips-only now — so a departed player_id
    raises a clear InvalidStateError instead of silently re-seating them.

    `seat_number` (added 2026-09-17, optional) assigns a specific numbered
    seat at the same time — used when the Cashier taps an empty seat
    directly. Left null (e.g. the bulk "+ Add Player" flow), the player is
    seated "unassigned" and can be placed into a seat later via move_seat.
    """
    _require_open_game_day(game_day)
    if player is None:
        if not player_fields:
            raise ValueError('Either player or player_fields is required.')
        player = Player.objects.create(**player_fields)

    existing_seat = GameDayPlayer.objects.filter(game_day=game_day, player=player).first()
    if existing_seat is not None and existing_seat.left_at is not None:
        raise InvalidStateError(
            f'{player.display_name} left the table tonight — issue them chips to bring them back, not re-seat.'
        )
    if seat_number is not None:
        _validate_seat_number(game_day, seat_number, exclude_player=player)
    _ensure_seated(game_day, player, operator)  # raises TableFullError for a brand-new seat at cap
    if seat_number is not None:
        GameDayPlayer.objects.filter(game_day=game_day, player=player).update(seat_number=seat_number)
    return player


def move_seat(game_day, player, seat_number, operator=None):
    """
    Relocates an already-seated, still-active player into `seat_number` —
    the Cashier just picks a destination; this figures out whether that's a
    plain move (seat is free) or a SWAP (occupied by someone else) and
    handles both identically from the caller's point of view. Added
    2026-09-17.

    Swapping nulls both rows' seat_number first, inside one atomic block,
    before setting final values — sidesteps the partial-unique constraint
    (GameDayPlayer.Meta) without needing a DB-specific deferrable
    constraint, so it works the same on every backend.
    """
    _require_open_game_day(game_day)
    if not (1 <= seat_number <= MAX_ACTIVE_PLAYERS_PER_GAME_DAY):
        raise InvalidStateError(f'Seat number must be between 1 and {MAX_ACTIVE_PLAYERS_PER_GAME_DAY}.')
    seat = GameDayPlayer.objects.filter(game_day=game_day, player=player, left_at__isnull=True).first()
    if seat is None:
        raise InvalidStateError(f"{player.display_name} isn't currently seated at tonight's table.")

    with db_transaction.atomic():
        occupant = GameDayPlayer.objects.filter(
            game_day=game_day, seat_number=seat_number, left_at__isnull=True,
        ).exclude(pk=seat.pk).first()
        previous_seat_number = seat.seat_number
        seat.seat_number = None
        seat.save(update_fields=['seat_number'])
        if occupant is not None:
            occupant.seat_number = None
            occupant.save(update_fields=['seat_number'])
            occupant.seat_number = previous_seat_number
            occupant.save(update_fields=['seat_number'])
        seat.seat_number = seat_number
        seat.save(update_fields=['seat_number'])
    return seat


def leave_table(game_day, player, operator=None):
    """
    Marks a seated player as having left tonight's table — frees their
    active "slot" (see MAX_ACTIVE_PLAYERS_PER_GAME_DAY) without deleting
    their GameDayPlayer row or touching any transaction history. Idempotent:
    calling this again on an already-departed player just refreshes the
    timestamp. Re-seating them (seat_player / _ensure_seated) clears left_at.
    """
    _require_open_game_day(game_day)
    seat = GameDayPlayer.objects.filter(game_day=game_day, player=player).first()
    if seat is None:
        raise InvalidStateError(f"{player.display_name} isn't seated for tonight's game-day.")
    seat.left_at = timezone.now()
    seat.save(update_fields=['left_at'])
    return seat


def confirm_transaction(transaction_obj, floor_manager_id, floor_manager_pin):
    """A Floor Manager co-signs a physical-count entry they independently witnessed."""
    fm = _resolve_floor_manager(floor_manager_id, floor_manager_pin)
    if fm is None:
        raise AuthorizationError('A valid Floor Manager PIN is required to confirm this entry.')
    transaction_obj.floor_manager = fm
    transaction_obj.confirmed_at = timezone.now()
    transaction_obj.save(update_fields=['floor_manager', 'confirmed_at'])
    return transaction_obj


def void_transaction(transaction_obj, actor, reason):
    """
    Cashier can void their own entry only while its game-day is still open.
    Once closed (or for a between-game-day entry that's otherwise settled),
    only the Owner can amend/void it.

    A Deals Transfer's two legs (DEAL_TRANSFER_OUT/IN, see
    record_deal_transfer) are voided together, atomically — voiding only
    one half would leave one player's debit undone without undoing the
    other's matching credit, an inconsistent ledger. The linked leg is
    voided with the same actor/reason, no separate authorization check
    (voiding a transfer at all is already Owner-only in practice, since
    Transfer creation itself is).
    """
    game_day = transaction_obj.game_day
    is_open = game_day is None or game_day.status == GameDay.Status.OPEN

    if actor.role == StaffUser.Role.OWNER:
        pass  # Owner can always void
    elif is_open and actor.role == StaffUser.Role.CASHIER and transaction_obj.recorded_by_id == actor.id:
        pass  # Cashier voiding their own same-day entry
    else:
        raise AuthorizationError(
            'Only the recording Cashier (while the game-day is open) or the Owner can void this entry.'
        )

    with db_transaction.atomic():
        transaction_obj.is_voided = True
        transaction_obj.voided_by = actor
        transaction_obj.voided_at = timezone.now()
        transaction_obj.void_reason = reason
        transaction_obj.save(update_fields=['is_voided', 'voided_by', 'voided_at', 'void_reason'])

        linked = transaction_obj.linked_transaction
        if linked is not None and not linked.is_voided:
            linked.is_voided = True
            linked.voided_by = actor
            linked.voided_at = timezone.now()
            linked.void_reason = reason
            linked.save(update_fields=['is_voided', 'voided_by', 'voided_at', 'void_reason'])
    return transaction_obj


# Physical-count types: a Floor Manager independently witnessed the same count, so
# these can't save without their PIN — see CONCEPT.md's Floor Manager section.
PHYSICAL_COUNT_TYPES = {
    Transaction.Type.CHIPS_OUT,
    Transaction.Type.CHIPS_IN,
    Transaction.Type.PAYMENT_CASH,
    Transaction.Type.RAKE,
    Transaction.Type.TIP,
}

DEFAULT_CHANNEL_BY_TYPE = {
    Transaction.Type.CHIPS_OUT: Transaction.Channel.CASHIER,
    Transaction.Type.CHIPS_IN: Transaction.Channel.CHIPS,
    Transaction.Type.PAYMENT_CASH: Transaction.Channel.CASH,
    Transaction.Type.PAYMENT_TRANSFER: Transaction.Channel.TRANSFER_DVA,
    Transaction.Type.PAYMENT_POS: Transaction.Channel.POS,
    Transaction.Type.PAYMENT_DEAL: Transaction.Channel.DEAL,
    Transaction.Type.WRITE_OFF: Transaction.Channel.WRITE_OFF,
    Transaction.Type.PAYOUT: Transaction.Channel.CASHIER,
    Transaction.Type.RAKE: Transaction.Channel.CASHIER,
    Transaction.Type.TIP: Transaction.Channel.CASHIER,
    Transaction.Type.DEAL_TRANSFER_OUT: Transaction.Channel.DEAL,
    Transaction.Type.DEAL_TRANSFER_IN: Transaction.Channel.DEAL,
}


def _apply_profit_split_stake(player, amount):
    """
    Returns (player_portion, house_portion, arrangement_or_None) for a
    CHIPS_OUT of `amount` — see ProfitSplitArrangement's docstring and
    record_transaction's CHIPS_OUT branch. No active arrangement, a zero
    stake %, or an already-exhausted arrangement (end date / max resets /
    max cumulative value reached) all fall through to "house covers
    nothing," so this is a no-op for every player without one, by
    construction.
    """
    arrangement = (
        ProfitSplitArrangement.objects.filter(player=player, is_active=True).order_by('-created_at').first()
    )
    if arrangement is None or arrangement.house_stake_pct <= 0:
        return amount, Decimal('0'), arrangement
    status = selectors.profit_split_status(arrangement)
    if status['is_exhausted']:
        return amount, Decimal('0'), arrangement
    uncapped_house_share = amount * arrangement.house_stake_pct / Decimal('100')
    house_portion = min(uncapped_house_share, status['available_stake_this_period'], amount)
    house_portion = house_portion.quantize(Decimal('0.01'))
    return amount - house_portion, house_portion, arrangement


def record_transaction(
    *, type, amount, recorded_by, game_day=None, player=None, notes='', currency='NGN',
    conversion_rate=None, channel=None, floor_manager_id=None, floor_manager_pin=None,
    tip_category=None, service_staff=None,
):
    """
    The general entry point for recording a ledger-affecting event (chips, cash,
    POS, transfer, deal, write-off, rake, tip — everything except PAYOUT, which
    goes through initiate_payout/approve_payout instead).

    Physical-count types require a valid Floor Manager PIN inline — the entry
    cannot be created without one.

    A CHIPS_OUT that would push the player's current-game-day debt past their
    chips_limit is rejected before the Floor Manager PIN step ever runs — see
    CONCEPT.md's "Chips limit."

    A Deal/write-off may target a CLOSED game-day, but only the one that just
    ended — see _require_open_game_day and DEAL_TYPES. When that happens,
    seating (_ensure_seated) is skipped entirely: that night's roster is
    already final, and a retroactive ledger entry shouldn't reopen its
    active-player cap or resurrect anyone into its seated list.

    A TIP requires `tip_category` (added 2026-09-17): DEALER stays anonymous/
    aggregate exactly as every Tip did before this (no recipient, tips_total
    arithmetic unaffected — this is attribution layered on top, not a new
    ledger figure); SERVICE requires an active `service_staff` recipient.
    Neither field applies to any other type.

    A WRITE_OFF (added 2026-09-20, part of "Deals" — see CONCEPT.md's Deals
    section) always requires a `notes` reason — it's the one Transaction
    type presented to the Owner with an on-screen "this can't be reversed"
    warning, so the audit trail can't be left blank — and can't exceed the
    player's current outstanding (lifetime) balance: a Deal can only ever
    relieve debt, never push a player into or further into one. Capped
    against player_balance (lifetime), not player_game_day_balance, since a
    write-off is a general debt-relief tool, not scoped to one night's play.
    """
    _require_open_game_day(game_day, type)
    if type == Transaction.Type.WRITE_OFF:
        if player is None:
            raise InvalidStateError('A write-off requires a player.')
        if not notes.strip():
            raise InvalidStateError('A reason is required for a write-off.')
        outstanding = max(-selectors.player_balance(player), Decimal('0'))
        if amount > outstanding:
            raise InvalidStateError(
                f"This exceeds {player.display_name}'s outstanding balance "
                f'(outstanding: ₦{outstanding:,}).'
            )
    if type == Transaction.Type.TIP:
        if tip_category not in (Transaction.TipCategory.DEALER, Transaction.TipCategory.SERVICE):
            raise InvalidStateError('A Tip must specify a category: Dealer or Service.')
        if tip_category == Transaction.TipCategory.SERVICE:
            if service_staff is None or not service_staff.is_active:
                raise InvalidStateError('A Service tip requires an active Service Staff recipient.')
        elif service_staff is not None:
            raise InvalidStateError('A Dealer tip cannot have a Service Staff recipient.')
    elif tip_category is not None or service_staff is not None:
        raise InvalidStateError('tip_category/service_staff only apply to a Tip.')

    # "Deals" Profit Split stake (added 2026-09-20): if this player has an
    # active arrangement, part of this buy-in is house-covered rather than
    # owed by the player — see _apply_profit_split_stake. Computed BEFORE
    # the chips_limit check below, since chips_limit caps the player's own
    # debt, not the total chips handed to them at the table.
    player_portion, house_portion, arrangement = amount, Decimal('0'), None
    if type == Transaction.Type.CHIPS_OUT and player is not None:
        player_portion, house_portion, arrangement = _apply_profit_split_stake(player, amount)

    if type == Transaction.Type.CHIPS_OUT and player is not None and player.chips_limit is not None:
        current_balance = selectors.player_game_day_balance(player, game_day) if game_day else Decimal('0')
        debt_after = max(Decimal('0'), player_portion - current_balance)
        if debt_after > player.chips_limit:
            raise InvalidStateError(
                f"This would exceed {player.display_name}'s chips limit for tonight "
                f'(limit ₦{player.chips_limit:,}, debt after this issuance would be ₦{debt_after:,}).'
            )
    fm = None
    if type in PHYSICAL_COUNT_TYPES:
        fm = _resolve_floor_manager(floor_manager_id, floor_manager_pin)
        if fm is None:
            raise AuthorizationError('A Floor Manager PIN is required to record this entry.')
    if game_day is not None and game_day.status == GameDay.Status.OPEN:
        _ensure_seated(game_day, player, recorded_by, revive=(type == Transaction.Type.CHIPS_OUT))

    with db_transaction.atomic():
        txn = Transaction.objects.create(
            game_day=game_day, player=player, type=type,
            amount=player_portion if type == Transaction.Type.CHIPS_OUT else amount,
            currency=currency, conversion_rate=conversion_rate,
            channel=channel or DEFAULT_CHANNEL_BY_TYPE[type], notes=notes,
            recorded_by=recorded_by, floor_manager=fm,
            confirmed_at=timezone.now() if fm else None,
            tip_category=tip_category, service_staff=service_staff,
            profit_split_arrangement=arrangement if house_portion > 0 else None,
        )
        if house_portion > 0:
            Transaction.objects.create(
                game_day=game_day, player=player, type=Transaction.Type.PROFIT_SPLIT_STAKE,
                amount=house_portion, channel=Transaction.Channel.DEAL,
                notes=f'House stake ({arrangement.house_stake_pct}%) toward this buy-in',
                recorded_by=recorded_by, profit_split_arrangement=arrangement,
            )
    return txn


def record_deal_transfer(source_player, destination_player, amount, reason, operator):
    """
    "Deals" Transfer (added 2026-09-20) — settles one player's debt (or tops
    up their credit) using another player's excess, as a linked pair of
    Transaction rows: DEAL_TRANSFER_OUT (debit, source) and DEAL_TRANSFER_IN
    (credit, destination), both game_day=None (an Outstanding-ledger entry,
    not tied to one night — the source's excess and the destination's debt
    are both lifetime figures). Owner-only, checked here explicitly (not
    just at the view layer) since this is a standalone single-purpose
    action with no other legitimate caller — same pattern as
    approve_payout/reject_payout.

    Can only ever relieve debt, never create or worsen it: the source must
    currently have a positive lifetime balance, and the amount can't exceed
    it — mirrors initiate_payout's `available = max(balance, 0)` capping
    pattern, but against lifetime player_balance rather than one game-day.
    """
    if operator.role != StaffUser.Role.OWNER:
        raise AuthorizationError('Only the Owner can record a Deals transfer.')
    if source_player.pk == destination_player.pk:
        raise InvalidStateError('Cannot transfer a player\'s balance to themselves.')
    if amount <= 0:
        raise InvalidStateError('Transfer amount must be greater than zero.')
    if not reason.strip():
        raise InvalidStateError('A reason is required for a transfer.')

    available = max(selectors.player_balance(source_player), Decimal('0'))
    if amount > available:
        raise InvalidStateError(
            f"This exceeds {source_player.display_name}'s available balance "
            f'(available: ₦{available:,}).'
        )

    with db_transaction.atomic():
        out_txn = Transaction.objects.create(
            player=source_player, type=Transaction.Type.DEAL_TRANSFER_OUT, amount=amount,
            channel=Transaction.Channel.DEAL, notes=reason, recorded_by=operator,
        )
        in_txn = Transaction.objects.create(
            player=destination_player, type=Transaction.Type.DEAL_TRANSFER_IN, amount=amount,
            channel=Transaction.Channel.DEAL, notes=reason, recorded_by=operator,
        )
        out_txn.linked_transaction = in_txn
        out_txn.save(update_fields=['linked_transaction'])
        in_txn.linked_transaction = out_txn
        in_txn.save(update_fields=['linked_transaction'])
    return out_txn, in_txn


def _validate_profit_split_arrangement(
    house_stake_pct, cap_amount, reset_cadence, ends_at, max_resets, max_cumulative_value,
    payout_split_method, custom_ratio_pct, fixed_amount,
):
    if not (Decimal('0') <= house_stake_pct <= Decimal('100')):
        raise InvalidStateError('House stake % must be between 0 and 100.')
    if cap_amount < 0:
        raise InvalidStateError('Cap amount cannot be negative.')
    if reset_cadence == ProfitSplitArrangement.ResetCadence.ONE_OFF:
        if ends_at or max_resets or max_cumulative_value:
            raise InvalidStateError(
                'End date / number of times / max value only apply to a recurring reset.'
            )
    if max_resets is not None and max_resets <= 0:
        raise InvalidStateError('Number of times must be a positive number.')
    if max_cumulative_value is not None and max_cumulative_value < 0:
        raise InvalidStateError('Max value cannot be negative.')
    if payout_split_method == ProfitSplitArrangement.PayoutSplitMethod.STAKE_RATIO and house_stake_pct <= 0:
        raise InvalidStateError('Ratio-according-to-stake requires a stake percentage greater than zero.')
    if payout_split_method == ProfitSplitArrangement.PayoutSplitMethod.CUSTOM_RATIO:
        if custom_ratio_pct is None or not (Decimal('0') <= custom_ratio_pct <= Decimal('100')):
            raise InvalidStateError('A custom house percentage (0-100) is required for this payout split method.')
    if payout_split_method == ProfitSplitArrangement.PayoutSplitMethod.FIXED:
        if fixed_amount is None or fixed_amount < 0:
            raise InvalidStateError('A fixed amount is required for this payout split method.')


def create_profit_split_arrangement(
    player, operator, house_stake_pct, cap_amount, reset_cadence=ProfitSplitArrangement.ResetCadence.ONE_OFF,
    ends_at=None, max_resets=None, max_cumulative_value=None,
    payout_basis=ProfitSplitArrangement.PayoutBasis.AFTER_BUYIN,
    payout_split_method=ProfitSplitArrangement.PayoutSplitMethod.STAKE_RATIO,
    custom_ratio_pct=None, fixed_amount=None, fixed_offset=None,
):
    """
    "Deals" Profit Split (added 2026-09-20) — Owner-only, checked here
    explicitly (not just at the view layer), same pattern as
    record_deal_transfer/approve_payout: a standalone single-purpose action
    with no other legitimate caller. Creating a new arrangement for a
    player automatically deactivates any previous active one for them —
    see ProfitSplitArrangement's docstring on why only one is meant to
    apply at a time. Only the stake side is actually enforced automatically
    (record_transaction's CHIPS_OUT branch); the payout-split fields are
    captured as configuration only for now.
    """
    if operator.role != StaffUser.Role.OWNER:
        raise AuthorizationError('Only the Owner can set up a Profit Split arrangement.')
    _validate_profit_split_arrangement(
        house_stake_pct, cap_amount, reset_cadence, ends_at, max_resets, max_cumulative_value,
        payout_split_method, custom_ratio_pct, fixed_amount,
    )
    with db_transaction.atomic():
        ProfitSplitArrangement.objects.filter(player=player, is_active=True).update(
            is_active=False, deactivated_at=timezone.now(),
        )
        return ProfitSplitArrangement.objects.create(
            player=player, house_stake_pct=house_stake_pct, cap_amount=cap_amount,
            reset_cadence=reset_cadence, ends_at=ends_at, max_resets=max_resets,
            max_cumulative_value=max_cumulative_value, payout_basis=payout_basis,
            payout_split_method=payout_split_method, custom_ratio_pct=custom_ratio_pct,
            fixed_amount=fixed_amount, fixed_offset=fixed_offset, created_by=operator,
        )


def deactivate_profit_split_arrangement(arrangement, operator):
    """Owner-only, ends an arrangement early — the per-period cap simply stops applying to future buy-ins."""
    if operator.role != StaffUser.Role.OWNER:
        raise AuthorizationError('Only the Owner can end a Profit Split arrangement.')
    arrangement.is_active = False
    arrangement.deactivated_at = timezone.now()
    arrangement.save(update_fields=['is_active', 'deactivated_at'])
    return arrangement


def initiate_payout(player, amount, operator, game_day=None):
    """
    Cashier initiates a cash-out transfer; it always lands PENDING_APPROVAL.

    Revised 2026-09-13: a payout is now always scoped to a game-day — it
    defaults to whichever one is currently open when the caller doesn't pass
    one — and is hard-capped at what the player has actually won *this*
    game-day (their positive player_game_day_balance), mirroring how
    chips_limit hard-blocks CHIPS_OUT rather than relying on Owner approval
    as the only guard. A pending payout already reduces this figure for any
    payout requested after it (balance selectors don't filter by status), so
    two payouts can't double-spend the same winnings.

    Revised 2026-09-17, two more upfront gates: a player can't cash out while
    still seated (leaving doesn't itself trigger a payout — the two stay
    independent — but a payout now requires it); and a payout can't even be
    requested without a default bank account on file, not just discovered
    later as TRANSFER_FAILED at approval time (that approval-time check in
    payments.services.initiate_payout_transfer stays too, as defense in
    depth — e.g. the account being removed between request and approval).
    """
    game_day = game_day or selectors.current_open_game_day()
    if game_day is None:
        raise InvalidStateError('A game-day must be open to initiate a payout.')
    _require_open_game_day(game_day)

    seat = GameDayPlayer.objects.filter(game_day=game_day, player=player).first()
    if seat is None or seat.left_at is None:
        raise InvalidStateError(
            f'{player.display_name} must leave the table before a payout can be requested.'
        )
    if not player.bank_accounts.filter(is_default=True).exists():
        raise InvalidStateError(
            f'{player.display_name} has no bank account on file — add one before requesting a payout.'
        )

    available = max(selectors.player_game_day_balance(player, game_day), Decimal('0'))
    if amount > available:
        raise InvalidStateError(
            f"This exceeds what {player.display_name} has won this game-day "
            f'(available: ₦{available:,}).'
        )

    _ensure_seated(game_day, player, operator, revive=False)  # a payout never revives a departed player
    return Transaction.objects.create(
        game_day=game_day, player=player, type=Transaction.Type.PAYOUT, amount=amount,
        channel=Transaction.Channel.CASHIER, recorded_by=operator,
        status=Transaction.Status.PENDING_APPROVAL,
    )


def approve_payout(transaction_obj, operator):
    """
    Every payout requires Owner approval before funds move — no threshold
    exemption. Approval and the real Paystack transfer happen together: if
    the transfer can't be sent (no bank account on file, Paystack rejects
    it, ...), the payout lands TRANSFER_FAILED instead of APPROVED so it's
    visibly stuck rather than silently "approved" with nothing moving.
    TRANSFER_FAILED can be retried by calling this again once the underlying
    issue is fixed (e.g. a bank account is added).

    Revised 2026-09-17: also guards against the club's Main Account balance
    itself going negative — checked first, before approved_by/approved_at
    are ever touched, so an insufficient-funds rejection leaves the
    transaction completely untouched and retryable once funds arrive
    (distinct from TRANSFER_FAILED, which means a transfer was actually
    attempted and failed). Placed here rather than at initiate_payout
    because the Main Account balance is Owner-only visibility (CONCEPT.md) —
    a Cashier requesting a payout shouldn't learn anything about club-wide
    funds. The whole function now runs inside one atomic, row-locked block:
    previously two concurrent approvals of the SAME transaction (double-
    click, two tabs) had a bare TOCTOU race on the status check alone;
    select_for_update() serializes that plus this new funds check.
    """
    if operator.role != StaffUser.Role.OWNER:
        raise AuthorizationError('Only the Owner can approve a payout.')
    if transaction_obj.type != Transaction.Type.PAYOUT:
        raise ValueError('Not a payout transaction.')

    with db_transaction.atomic():
        transaction_obj = Transaction.objects.select_for_update().get(pk=transaction_obj.pk)
        if transaction_obj.status not in (Transaction.Status.PENDING_APPROVAL, Transaction.Status.TRANSFER_FAILED):
            raise InvalidStateError('Only a pending or previously failed payout can be approved.')
        # main_account_balance() already has THIS payout's own debit baked in
        # (it's status-agnostic, same as the player-side balance check — a
        # pending payout already reserves its amount) — so the right test is
        # "would honoring every currently-reserved obligation, including this
        # one, push the account negative," not amount-vs-balance directly.
        if selectors.main_account_balance() < 0:
            raise InvalidStateError('Insufficient Main Account balance to complete this payout.')

        # Deferred import: payments.services imports gaming.services (record_transaction)
        # at module level, so importing it back at module level here would be circular.
        from payments.services import PaystackAPIError, initiate_payout_transfer

        transaction_obj.approved_by = operator
        transaction_obj.approved_at = timezone.now()
        try:
            transfer_code = initiate_payout_transfer(transaction_obj)
        except PaystackAPIError as exc:
            transaction_obj.status = Transaction.Status.TRANSFER_FAILED
            transaction_obj.notes = f'{transaction_obj.notes}\nTransfer failed: {exc}'.strip()
            transaction_obj.save(update_fields=['status', 'notes', 'approved_by', 'approved_at'])
            return transaction_obj

        transaction_obj.status = Transaction.Status.APPROVED
        transaction_obj.external_reference = transfer_code
        transaction_obj.save(update_fields=['status', 'approved_by', 'approved_at', 'external_reference'])
        return transaction_obj


def reject_payout(transaction_obj, operator, reason):
    """
    Owner declines a pending (or previously failed) payout — added
    2026-09-15. Reuses void_transaction's own fields (is_voided, voided_by,
    voided_at, void_reason) rather than a parallel set of "rejected_*"
    fields: a rejected payout must drop out of every balance sum exactly the
    way a voided one already does (every balance/aggregate selector filters
    only is_voided=False, never by status — so without this, a "rejected"
    payout would keep silently debiting the player forever, since it was
    already counted the moment it went PENDING_APPROVAL). status=REJECTED is
    kept as the more specific, user-facing state on top of that.
    """
    if operator.role != StaffUser.Role.OWNER:
        raise AuthorizationError('Only the Owner can reject a payout.')
    if transaction_obj.type != Transaction.Type.PAYOUT:
        raise ValueError('Not a payout transaction.')
    if transaction_obj.status not in (Transaction.Status.PENDING_APPROVAL, Transaction.Status.TRANSFER_FAILED):
        raise InvalidStateError('Only a pending or previously failed payout can be rejected.')

    transaction_obj.status = Transaction.Status.REJECTED
    transaction_obj.is_voided = True
    transaction_obj.voided_by = operator
    transaction_obj.voided_at = timezone.now()
    transaction_obj.void_reason = reason
    transaction_obj.save(update_fields=['status', 'is_voided', 'voided_by', 'voided_at', 'void_reason'])
    return transaction_obj
