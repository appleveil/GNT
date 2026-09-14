"""
Authorization rules and state-changing actions, kept out of views.py so each
rule is independently callable/testable. See CONCEPT.md's "Scope decisions"
and "Floor Manager" sections for the rules encoded here.
"""

from decimal import Decimal

from django.utils import timezone

from accounts.models import FloorManager, Player, StaffUser

from . import selectors
from .exceptions import AuthorizationError, InvalidStateError, TableFullError
from .models import ConversionRate, GameDay, GameDayPlayer, GameDaySummary, Transaction

# A real table only has so many seats. Enforced in seat_player (the explicit
# "add a player" action) only — _ensure_seated stays permissive, since any
# real transaction recorded for a departed player should just revive them,
# not get silently blocked by a cap meant for the explicit add flow. See
# PLAN.md's "leave the table" entry.
MAX_ACTIVE_PLAYERS_PER_GAME_DAY = 9


def _require_open_game_day(game_day):
    """
    Enforced server-side, not left to whichever frontend is calling in: a client
    can go stale (another device closed this game-day moments ago) or simply not
    be the sanctioned UI at all, so this can't be a client-side-only rule.
    """
    if game_day is not None and game_day.status != GameDay.Status.OPEN:
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


def _ensure_seated(game_day, player, operator=None):
    """
    Idempotently records that `player` is part of `game_day` — see
    GameDayPlayer. A no-op for the between-game-day case (game_day is None)
    or rake/tip (player is None); called from both record_transaction and
    initiate_payout so a player can never have real activity tonight without
    also showing up in the Cashier's seated-players list.

    Also revives a departed player (clears left_at) — deliberately permissive
    here, unlike seat_player's cap check: any real transaction recorded
    against someone who'd left just means they're evidently back at the
    table, not something to silently block. See PLAN.md's "leave the table" entry.
    """
    if game_day is None or player is None:
        return
    seat, _ = GameDayPlayer.objects.get_or_create(game_day=game_day, player=player, defaults={'added_by': operator})
    if seat.left_at is not None:
        seat.left_at = None
        seat.save(update_fields=['left_at'])


def seat_player(game_day, operator, player=None, player_fields=None):
    """
    The explicit "add a player for tonight" action — see CONCEPT.md's Buy-in
    flow. Either pass an existing `player`, or `player_fields` to create a new
    club-wide Player record and seat it in one call. Idempotent: seating an
    already-active player is a no-op, not an error.

    Registering a brand-new player (player_fields) always succeeds, even if
    the table is full — only seating them for tonight is capped at
    MAX_ACTIVE_PLAYERS_PER_GAME_DAY active players (this includes reviving a
    departed player via "Return to Table", which is exactly this same call
    with an existing player_id). Raises TableFullError, carrying the player,
    so the caller can report "registered but not seated" rather than a bare
    failure — the Player row this call already created is NOT rolled back.
    """
    _require_open_game_day(game_day)
    if player is None:
        if not player_fields:
            raise ValueError('Either player or player_fields is required.')
        player = Player.objects.create(**player_fields)

    already_active = GameDayPlayer.objects.filter(game_day=game_day, player=player, left_at__isnull=True).exists()
    if not already_active and selectors.active_game_day_players_count(game_day) >= MAX_ACTIVE_PLAYERS_PER_GAME_DAY:
        raise TableFullError(
            f'The table is full ({MAX_ACTIVE_PLAYERS_PER_GAME_DAY} active players right now) — '
            f"{player.display_name} wasn't seated. Try again once someone leaves the table.",
            player=player,
        )
    _ensure_seated(game_day, player, operator)
    return player


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

    transaction_obj.is_voided = True
    transaction_obj.voided_by = actor
    transaction_obj.voided_at = timezone.now()
    transaction_obj.void_reason = reason
    transaction_obj.save(update_fields=['is_voided', 'voided_by', 'voided_at', 'void_reason'])
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
}


def record_transaction(
    *, type, amount, recorded_by, game_day=None, player=None, notes='', currency='NGN',
    conversion_rate=None, channel=None, floor_manager_id=None, floor_manager_pin=None,
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
    """
    _require_open_game_day(game_day)
    if type == Transaction.Type.CHIPS_OUT and player is not None and player.chips_limit is not None:
        current_balance = selectors.player_game_day_balance(player, game_day) if game_day else Decimal('0')
        debt_after = max(Decimal('0'), amount - current_balance)
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
    _ensure_seated(game_day, player, recorded_by)
    return Transaction.objects.create(
        game_day=game_day, player=player, type=type, amount=amount,
        currency=currency, conversion_rate=conversion_rate,
        channel=channel or DEFAULT_CHANNEL_BY_TYPE[type], notes=notes,
        recorded_by=recorded_by, floor_manager=fm,
        confirmed_at=timezone.now() if fm else None,
    )


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
    """
    game_day = game_day or selectors.current_open_game_day()
    if game_day is None:
        raise InvalidStateError('A game-day must be open to initiate a payout.')
    _require_open_game_day(game_day)

    available = max(selectors.player_game_day_balance(player, game_day), Decimal('0'))
    if amount > available:
        raise InvalidStateError(
            f"This exceeds what {player.display_name} has won this game-day "
            f'(available: ₦{available:,}).'
        )

    _ensure_seated(game_day, player, operator)
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
    """
    if operator.role != StaffUser.Role.OWNER:
        raise AuthorizationError('Only the Owner can approve a payout.')
    if transaction_obj.type != Transaction.Type.PAYOUT:
        raise ValueError('Not a payout transaction.')
    if transaction_obj.status not in (Transaction.Status.PENDING_APPROVAL, Transaction.Status.TRANSFER_FAILED):
        raise InvalidStateError('Only a pending or previously failed payout can be approved.')

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
