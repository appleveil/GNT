"""
Authorization rules and state-changing actions, kept out of views.py so each
rule is independently callable/testable. See CONCEPT.md's "Scope decisions"
and "Floor Manager" sections for the rules encoded here.
"""

from datetime import timedelta
from decimal import Decimal

from django.db import transaction as db_transaction
from django.utils import timezone

from accounts.models import AccountCode, FloorManager, Player, StaffMember, StaffUser

from . import selectors
from .exceptions import AuthorizationError, InvalidStateError, MinimumPlayerTimeNotMetError, TableFullError
from .models import ClubSettings, ConversionRate, GameDay, GameDayPlayer, GameDaySummary, ProfitSplitArrangement, Transaction

# A real table only has so many seats. Revised 2026-09-15: a departed player
# returns ONLY by being issued chips (CHIPS_OUT) — never a bare re-add — and
# that revival is capped exactly like creating a brand-new seat is. See
# _ensure_seated's `revive` param and PLAN.md's "leave the table" entry.
#
# The cap itself is now per-game (Texas Hold'em 9, Omaha 8 — see
# Game.max_players and selectors.max_active_players, added 2026-09-21); this
# constant survives ONLY as selectors.max_active_players' fallback for a
# legacy game-day with no `game` set. Every usage below resolves through
# that function now, not this constant directly.
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
    owner_id=None, owner_pin=None, game=None, table=None, buy_in_amount=None,
):
    """
    Owner (own login, or PIN) or a Floor Manager PIN authorizes this — a Cashier
    is never the authorizer, under any circumstance. See CONCEPT.md's "Open
    Game-Day flow."

    Added 2026-09-21: optionally records which Game/Table this game-day is
    running and the Buy-in amount for it — the "Start game-day" flow's
    three steps (see PLAN.md's "Game/Table selection + two-step chip
    custody" entry). `buy_in_amount` defaults to `table.default_buy_in`
    when a table is given but no amount is specified — an independent
    choice each night, but with a pre-filled default (confirmed). All
    three stay optional so a game-day can still be opened without them,
    same as every game-day before this change.

    Revised 2026-09-23: sign-off itself is now optional, per
    ClubSettings.require_approval_open_game_day — off, and this skips
    straight to creating the game-day with no owner/fm at all (the
    frontend still shows a plain, PIN-less confirm step first; see
    usePlainConfirm.js).
    """
    if ClubSettings.load().require_approval_open_game_day:
        owner, fm = _resolve_owner_or_floor_manager(
            operator, floor_manager_id, floor_manager_pin, owner_id, owner_pin, action='Opening a game-day',
        )
    else:
        owner, fm = None, None
    if buy_in_amount is None and table is not None:
        buy_in_amount = table.default_buy_in
    return GameDay.objects.create(
        number=number, started_at=started_at, status=GameDay.Status.OPEN,
        opened_by=owner, opened_by_floor_manager=fm,
        game=game, table=table, buy_in_amount=buy_in_amount,
    )


def close_blocked_reason(game_day):
    """
    Why close_game_day would refuse outright right now, or None if it
    wouldn't — added 2026-09-22, shared with GameDayViewSet.close_preview
    so the Cashier sees this up front rather than only after entering a
    PIN. HARD block only, never overridable: every seated player must have
    left the table first — an active seat means someone's still mid-play,
    nothing to reconcile against yet. A chip discrepancy is a SEPARATE,
    acknowledgeable condition — see game_day_chip_discrepancy — not a hard
    block at all.
    """
    active_count = selectors.active_game_day_players_count(game_day)
    if active_count > 0:
        noun = 'player' if active_count == 1 else 'players'
        return f'{active_count} {noun} still at the table — everyone must leave before closing.'
    return None


def game_day_chip_discrepancy(game_day):
    """
    None once chips fully reconcile for the night; otherwise a dict
    describing the gap, used by close_game_day's acknowledge-and-sign-off
    path (see its own docstring) and surfaced on GameDayViewSet.close_preview
    so the Cashier sees it before attempting to close.

    Deliberately built on the SAME chips_variance formula GameDaySummary
    already freezes at close (chips_out − chips_in − rake − tips), not a
    bare chips_out-vs-chips_in comparison — rake and tips are chips that
    legitimately never come back as a CHIPS_IN (skimmed from play, or
    handed to staff as a tip), so they're not a discrepancy; only whatever
    is still unaccounted for after those is. Added 2026-09-22.
    """
    data = selectors.game_day_summary_data(game_day)
    variance = data['chips_variance']
    if variance == 0:
        return None
    return {
        'chips_out_total': data['chips_out_total'],
        'chips_in_total': data['chips_in_total'],
        'rake_total': data['rake_total'],
        'tips_total': data['tips_total'],
        'amount': abs(variance),
        'direction': 'short' if variance > 0 else 'excess',
    }


def close_game_day(
    game_day, operator, floor_manager_id=None, floor_manager_pin=None,
    owner_id=None, owner_pin=None, discrepancy_reason='',
):
    """
    Closing is the night's final physical reconciliation, witnessed
    independently just like any other physical-count entry (CHIPS_OUT/IN,
    cash, rake, tip — see PHYSICAL_COUNT_TYPES): an ordinary close (chips
    fully reconciled) requires a Floor Manager PIN, full stop — no
    Owner-login bypass, unlike open_game_day/set_conversion_rate,
    deliberately: the whole point of a signature here is independent
    verification, which an Owner closing solo wouldn't provide.

    A chip discrepancy (see game_day_chip_discrepancy) does NOT block
    closing outright — a player may genuinely have walked off with chips,
    which isn't something anyone can fix on the spot — but it must be
    ACKNOWLEDGED: `discrepancy_reason` is required (raises otherwise), and
    authorization widens to Owner (own login or PIN) OR Floor Manager PIN
    for that close specifically — either may sign off on a deficit or an
    excess. The reason is frozen onto GameDaySummary.chip_discrepancy_reason
    for the audit trail. Revised 2026-09-22 — see PLAN.md's dated entry for
    the full history (was Cashier/Owner/FM, any one alone, no PIN, no gate
    of any kind, before this).

    Still hard-blocks on close_blocked_reason (players still seated) —
    nothing to sign off on there, it's just not ready yet. Writes the
    GameDaySummary snapshot once, here — it's never recomputed after.

    Revised 2026-09-23: the ORDINARY (no-discrepancy) path's PIN is now
    optional, per ClubSettings.require_approval_close_game_day — off, and
    `fm` just stays None. A chip discrepancy always still requires
    Owner-or-FM sign-off regardless of this flag: it's a genuine anomaly
    (chips didn't reconcile), not the routine close this flag streamlines.
    """
    reason = close_blocked_reason(game_day)
    if reason is not None:
        raise InvalidStateError(reason)

    discrepancy = game_day_chip_discrepancy(game_day)
    if discrepancy is not None:
        if not discrepancy_reason.strip():
            raise InvalidStateError(
                f"Chips don't reconcile (₦{discrepancy['amount']:,} {discrepancy['direction']}) — "
                f'a reason is required to close anyway.'
            )
        owner, fm = _resolve_owner_or_floor_manager(
            operator, floor_manager_id, floor_manager_pin, owner_id, owner_pin,
            action='Closing with a chip discrepancy',
        )
    elif ClubSettings.load().require_approval_close_game_day:
        fm = _resolve_floor_manager(floor_manager_id, floor_manager_pin)
        if fm is None:
            raise AuthorizationError('Closing a game-day requires a Floor Manager PIN.')
    else:
        fm = None

    game_day.status = GameDay.Status.CLOSED
    game_day.ended_at = timezone.now()
    game_day.closed_by = operator
    game_day.closed_by_floor_manager = fm
    game_day.save(update_fields=['status', 'ended_at', 'closed_by', 'closed_by_floor_manager'])
    summary_data = selectors.game_day_summary_data(game_day)
    summary_data['chip_discrepancy_reason'] = discrepancy_reason.strip() if discrepancy is not None else ''
    GameDaySummary.objects.update_or_create(game_day=game_day, defaults=summary_data)
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


def _ensure_seated(game_day, player, operator=None, block_departed=False):
    """
    Idempotently ensures `player` has a GameDayPlayer row for `game_day` — a
    no-op for the between-game-day case (game_day is None) or rake/tip
    (player is None); called from both record_transaction and
    initiate_payout so a player can never have real activity tonight without
    also showing up in the Cashier's seated-players list.

    `block_departed` (renamed from `revive` 2026-09-22, default False) —
    pass True only for a CHIPS_OUT (record_transaction). Until 2026-09-22
    this silently cleared a departed player's left_at, reviving them onto
    whatever seat_number they still carried from before — but leave_table
    never clears seat_number, so that seat could since have been taken by
    someone else, and the Cashier had no chance to pick a (possibly
    different) seat first. Now it raises instead, directing the caller to
    gaming.services.rejoin_at_seat — an explicit seat pick, THEN chips.
    Every other transaction type, and initiate_payout, still record
    normally against a departed player without touching left_at at all
    (e.g. a Return-Chips correction after the fact — see PLAN.md).

    Creating a brand-new seat (never seated tonight, regardless of who's
    calling) is always capped — closes a gap where record_transaction/
    initiate_payout could otherwise seat a 10th active player without ever
    going through seat_player's check.
    """
    if game_day is None or player is None:
        return
    seat = GameDayPlayer.objects.filter(game_day=game_day, player=player).first()
    max_players = selectors.max_active_players(game_day)
    if seat is None:
        if selectors.active_game_day_players_count(game_day) >= max_players:
            raise TableFullError(
                f'The table is full ({max_players} active players right now) — '
                f"{player.display_name} wasn't seated. Try again once someone leaves the table.",
                player=player,
            )
        GameDayPlayer.objects.create(game_day=game_day, player=player, added_by=operator)
    elif block_departed and seat.left_at is not None:
        raise InvalidStateError(
            f'{player.display_name} left the table tonight — pick a seat to bring them back '
            f'(Rejoin) before issuing chips.'
        )


def _validate_seat_number(game_day, seat_number, exclude_player=None):
    """
    Raises a clean InvalidStateError for an out-of-range or already-taken
    seat, rather than letting the DB's partial-unique constraint (see
    GameDayPlayer.Meta) surface as a raw IntegrityError. `exclude_player`
    lets a player "take" the seat they're already sitting in (a no-op move).
    """
    max_players = selectors.max_active_players(game_day)
    if not (1 <= seat_number <= max_players):
        raise InvalidStateError(f'Seat number must be between 1 and {max_players}.')
    occupied = GameDayPlayer.objects.filter(game_day=game_day, seat_number=seat_number, left_at__isnull=True)
    if exclude_player is not None:
        occupied = occupied.exclude(player=exclude_player)
    if occupied.exists():
        raise InvalidStateError(f'Seat {seat_number} is already taken.')


def _assign_next_account_code(display_name):
    """
    Creates a new Player, consuming the oldest available AccountCode row —
    added 2026-09-25, see AccountCode's own docstring. select_for_update
    inside its own atomic block so two Cashiers registering a new player at
    the same instant can never be handed the same code.
    """
    with db_transaction.atomic():
        code_row = AccountCode.objects.select_for_update().filter(linked_player__isnull=True).first()
        if code_row is None:
            raise InvalidStateError(
                'No available account codes — add more from the Admin page before registering a new player.'
            )
        player = Player.objects.create(account_code=code_row.code, display_name=display_name)
        code_row.linked_player = player
        code_row.save(update_fields=['linked_player'])
        return player


def seat_player(game_day, operator, player=None, player_fields=None, seat_number=None):
    """
    The explicit "add a player for tonight" action — see CONCEPT.md's Buy-in
    flow. Either pass an existing `player`, or `player_fields` to create a new
    club-wide Player record and seat it in one call. Idempotent: seating an
    already-active player is a no-op, not an error.

    Registering a brand-new player (player_fields) always succeeds, even if
    the table is full — only seating them for tonight is capped (via
    _ensure_seated). Revised 2026-09-15: this can no longer revive a departed
    player at all — a departed player_id raises a clear InvalidStateError
    instead of silently re-seating them. Revised again 2026-09-22: bringing
    a departed player back is now rejoin_at_seat (explicit seat pick), not
    issuing them chips — see _ensure_seated's block_departed docstring.

    `seat_number` (added 2026-09-17, optional) assigns a specific numbered
    seat at the same time — used when the Cashier taps an empty seat
    directly. Left null (e.g. the bulk "+ Add Player" flow), the player is
    seated "unassigned" and can be placed into a seat later via move_seat.

    Added 2026-09-21: if this game-day has a Table and a Buy-in amount set
    (see GameDay.table/buy_in_amount and the "Start game-day" flow), and
    this player has no CHIPS_OUT yet tonight, seating them ALSO
    automatically issues that default buy-in — house to the player — with
    NO Floor Manager PIN at all. This is the one deliberate automation
    confirmed for this specific case (see record_transaction's
    `_skip_pin_check`); a manual top-up beyond this default still requires
    the PIN, exactly as before. Wrapped in one atomic block with the
    seating itself: a rejection here (e.g. the default exceeds this
    player's chips_limit) rolls the seat back too, rather than leaving
    them seated but unchipped.

    Revised 2026-09-25: `player_fields` no longer carries `account_code` —
    a brand-new player is assigned the next available one from the
    AccountCode pool (see _assign_next_account_code) instead of a Cashier
    typing one in free-hand. Raises InvalidStateError if the pool is empty;
    the Add Player form is expected to check GET
    /account-codes/available-count/ first and disable itself, but this is
    the real, authoritative gate.
    """
    _require_open_game_day(game_day)
    if player is None:
        if not player_fields:
            raise ValueError('Either player or player_fields is required.')
        player = _assign_next_account_code(player_fields['display_name'])

    existing_seat = GameDayPlayer.objects.filter(game_day=game_day, player=player).first()
    if existing_seat is not None and existing_seat.left_at is not None:
        raise InvalidStateError(
            f'{player.display_name} left the table tonight — rejoin them at a seat instead of re-seating.'
        )
    if seat_number is not None:
        _validate_seat_number(game_day, seat_number, exclude_player=player)

    with db_transaction.atomic():
        _ensure_seated(game_day, player, operator)  # raises TableFullError for a brand-new seat at cap
        if seat_number is not None:
            GameDayPlayer.objects.filter(game_day=game_day, player=player).update(seat_number=seat_number)

        if (
            game_day.table_id and game_day.buy_in_amount and
            not Transaction.objects.filter(
                game_day=game_day, player=player, type=Transaction.Type.CHIPS_OUT,
            ).exists()
        ):
            record_transaction(
                type=Transaction.Type.CHIPS_OUT, amount=game_day.buy_in_amount, recorded_by=operator,
                game_day=game_day, player=player, channel=Transaction.Channel.CASHIER,
                notes='Default buy-in on seating', _skip_pin_check=True,
            )
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
    max_players = selectors.max_active_players(game_day)
    if not (1 <= seat_number <= max_players):
        raise InvalidStateError(f'Seat number must be between 1 and {max_players}.')
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


def rejoin_at_seat(game_day, player, seat_number, operator=None):
    """
    Brings a departed player back to the table at a specific seat, in one
    atomic step — added 2026-09-22 so bringing someone back always goes
    through an explicit seat pick FIRST, rather than the old "Issue Chips
    silently revives them onto whatever seat_number they still carried from
    before they left" behavior (leave_table never clears seat_number, so
    that seat could since have been taken by someone else — a real, if
    quiet, correctness gap this closes). Once rejoined here, the player is
    active again and Issue Chips works on them exactly like anyone else —
    see _ensure_seated's block_departed, which now refuses to do this
    implicitly.
    """
    _require_open_game_day(game_day)
    seat = GameDayPlayer.objects.filter(game_day=game_day, player=player).first()
    if seat is None or seat.left_at is None:
        raise InvalidStateError(f"{player.display_name} hasn't left tonight's table.")
    max_players = selectors.max_active_players(game_day)
    if selectors.active_game_day_players_count(game_day) >= max_players:
        raise TableFullError(
            f'The table is full ({max_players} active players right now) — '
            f"{player.display_name} wasn't seated. Try again once someone leaves the table.",
            player=player,
        )
    _validate_seat_number(game_day, seat_number, exclude_player=player)
    with db_transaction.atomic():
        seat.left_at = None
        seat.seat_number = seat_number
        seat.save(update_fields=['left_at', 'seat_number'])
    return seat


def leave_table(game_day, player, operator=None):
    """
    Marks a seated player as having left tonight's table — frees their
    active "slot" (see MAX_ACTIVE_PLAYERS_PER_GAME_DAY) without deleting
    their GameDayPlayer row or touching any transaction history. Idempotent:
    calling this again on an already-departed player just refreshes the
    timestamp. Re-seating them (seat_player / _ensure_seated) clears left_at.

    Not a physical count or financial action on its own — returning chips
    is its own separate CHIPS_IN entry (PIN-witnessed, same as any other
    physical count), recorded before this is called, same as it always was.

    Briefly (2026-09-21) became a 3-way disposition (LeaveDisposition:
    NO_RETURN/HOLD/CASH_OUT) as part of a two-step chip-custody model
    (TABLE_BUY_IN/TABLE_CASH_OUT) — reverted the same day: HOLD/CASH_OUT
    were never reachable from the frontend (it always called this with no
    body), and the custody model itself read as confusing/redundant in the
    ledger. See PLAN.md's dated revert entry.
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

# Which of PHYSICAL_COUNT_TYPES has an Owner-configurable "require
# approval" toggle (see ClubSettings) — PAYMENT_CASH isn't here, so it
# keeps requiring the Floor Manager PIN unconditionally. Added 2026-09-23;
# CHIPS_OUT added the same day. Doesn't touch seat_player's own automatic
# default buy-in (_skip_pin_check=True) — that bypass runs before this
# lookup is ever consulted (see the `if not _skip_pin_check` guard below),
# same as before this toggle existed.
_APPROVAL_SETTING_BY_TYPE = {
    Transaction.Type.CHIPS_OUT: 'require_approval_issue_chips',
    Transaction.Type.CHIPS_IN: 'require_approval_return_chips',
    Transaction.Type.TIP: 'require_approval_add_tip',
    Transaction.Type.RAKE: 'require_approval_add_rake',
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
    house_portion = house_portion.quantize(Decimal('1'))  # whole Naira only — no kobo
    return amount - house_portion, house_portion, arrangement


def record_transaction(
    *, type, amount, recorded_by, game_day=None, player=None, notes='', currency='NGN',
    conversion_rate=None, channel=None, floor_manager_id=None, floor_manager_pin=None,
    tip_category=None, masseuse=None, _skip_pin_check=False,
):
    """
    The general entry point for recording a ledger-affecting event (chips, cash,
    POS, transfer, deal, write-off, rake, tip — everything except PAYOUT, which
    goes through initiate_payout/approve_payout instead).

    Physical-count types require a valid Floor Manager PIN inline — the entry
    cannot be created without one.

    `_skip_pin_check` (added 2026-09-21, private — never exposed through
    RecordTransactionSerializer or any view) is set ONLY by seat_player's
    automatic default buy-in: the one deliberate, explicitly-requested
    exception where a CHIPS_OUT needs no Floor Manager PIN at all, because
    it's a known, system-computed default amount, not a manual physical
    count. Every other CHIPS_OUT — including a manual rebuy through the
    normal endpoint — keeps requiring the PIN exactly as before.

    A CHIPS_OUT that would push the player's current-game-day debt past their
    chips_limit is rejected before the Floor Manager PIN step ever runs — see
    CONCEPT.md's "Chips limit."

    A Deal/write-off may target a CLOSED game-day, but only the one that just
    ended — see _require_open_game_day and DEAL_TYPES. When that happens,
    seating (_ensure_seated) is skipped entirely: that night's roster is
    already final, and a retroactive ledger entry shouldn't reopen its
    active-player cap or resurrect anyone into its seated list.

    A TIP requires `tip_category` (added 2026-09-17, values renamed
    2026-09-23): SERVICE_STAFF stays anonymous/aggregate exactly as every Tip
    did before this (no recipient, tips_total arithmetic unaffected — this is
    attribution layered on top, not a new ledger figure); MASSEUSE requires
    an active `masseuse` recipient. Neither field applies to any other type.

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
        if tip_category not in (Transaction.TipCategory.SERVICE_STAFF, Transaction.TipCategory.MASSEUSE):
            raise InvalidStateError('A Tip must specify a category: Service staff or Masseuse.')
        if tip_category == Transaction.TipCategory.MASSEUSE:
            if masseuse is None or not masseuse.is_active or masseuse.role != StaffMember.Role.MASSEUSE:
                raise InvalidStateError('A Masseuse tip requires an active Masseuse recipient.')
        elif masseuse is not None:
            raise InvalidStateError('A Service staff tip cannot have a Masseuse recipient.')
    elif tip_category is not None or masseuse is not None:
        raise InvalidStateError('tip_category/masseuse only apply to a Tip.')

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

    # Per-issuance cap (added 2026-09-23, Owner/Floor-Manager-editable via
    # Table.max_chips_issuable — see the Settings screen): how much can be
    # issued to a player IN ONE GO. Corrected same day — this is NOT a
    # running/cumulative total (a player can buy in at the cap multiple
    # times over the night; there's no limit on total chips outstanding at
    # once) — just a ceiling on any single CHIPS_OUT amount. Distinct from
    # player.chips_limit above, which caps one player's own overall debt
    # tonight, not the size of any one issuance. null = no cap.
    if (
        type == Transaction.Type.CHIPS_OUT and game_day is not None
        and game_day.table_id and game_day.table.max_chips_issuable is not None
        and amount > game_day.table.max_chips_issuable
    ):
        raise InvalidStateError(
            f'This exceeds the most that can be issued in one go on this table '
            f"(₦{amount:,} requested, cap ₦{game_day.table.max_chips_issuable:,})."
        )

    # Chips returned can never exceed what could still physically be on the
    # table for the game-day, full stop — added 2026-09-22 after a request
    # to catch this on the spot (a miscount, or forgetting someone already
    # cashed out) rather than only at close. Deliberately game-day-wide, not
    # per-player: an excess return is still a discrepancy in the physical
    # chip count even if it nets out across different players' CHIPS_OUT/
    # CHIPS_IN rows. Blocks the entry outright — no override — until the
    # amount (or a missing CHIPS_OUT elsewhere) is corrected.
    #
    # Revised 2026-09-23: rake and tips are chips that legitimately never
    # come back as a CHIPS_IN (skimmed from play / handed to staff) — same
    # reasoning close-time's chips_variance already used (see
    # game_day_chip_discrepancy). Netting them out of the ceiling here
    # means this on-the-spot check now agrees with that close-time one,
    # instead of being looser than it (it would otherwise let a return
    # through that close would immediately flag as an excess).
    if type == Transaction.Type.CHIPS_IN and game_day is not None:
        totals = selectors.game_day_chips_totals(game_day)
        max_returnable = totals['chips_out_total'] - totals['rake_total'] - totals['tips_total']
        chips_in_after = totals['chips_in_total'] + amount
        if chips_in_after > max_returnable:
            over_by = chips_in_after - max_returnable
            raise InvalidStateError(
                f'This would put total chips returned tonight (₦{chips_in_after:,}) above what could still be '
                f'on the table (₦{max_returnable:,} — chips issued minus rake/tips already taken out) '
                f'by ₦{over_by:,} — recount before returning.'
            )
    fm = None
    if not _skip_pin_check and type in PHYSICAL_COUNT_TYPES:
        # CHIPS_OUT/CHIPS_IN/TIP/RAKE's sign-off is Owner-configurable
        # (added 2026-09-23, ClubSettings.require_approval_*) —
        # PAYMENT_CASH has no entry here, so it keeps requiring the PIN
        # unconditionally, same as before this change.
        setting_name = _APPROVAL_SETTING_BY_TYPE.get(type)
        requires_pin = getattr(ClubSettings.load(), setting_name) if setting_name else True
        if requires_pin:
            fm = _resolve_floor_manager(floor_manager_id, floor_manager_pin)
            if fm is None:
                raise AuthorizationError('A Floor Manager PIN is required to record this entry.')

    # Minimum player time (added 2026-09-27, ClubSettings.observe_min_player_time)
    # — a player can LEAVE the table any time (leave_table has no time gate
    # at all) but chips can't be RETURNED for them until they've been
    # seated at least min_player_time_minutes, unless a Floor Manager PIN
    # overrides it. Independent of require_approval_return_chips above —
    # even when that toggle is off (no PIN normally needed to return
    # chips), a too-early return still forces one; if `fm` was already
    # resolved by the block above, that same PIN satisfies both, no second
    # prompt. GameDayPlayer.added_at is the anchor — a player who leaves and
    # rejoins doesn't get their clock reset (Track Away From Table, when
    # it's actually built, is the mechanism for adjusting this, not a
    # reset). Player-facing debt/time figures stay visible here (unlike the
    # Cashier's lifetime-balance blind spot) — this isn't about hiding
    # history, just gating an early cash-out.
    if type == Transaction.Type.CHIPS_IN and game_day is not None and player is not None:
        settings_obj = ClubSettings.load()
        if settings_obj.observe_min_player_time:
            seat = GameDayPlayer.objects.filter(game_day=game_day, player=player).first()
            if seat is not None:
                minimum = timedelta(minutes=settings_obj.min_player_time_minutes)
                elapsed = timezone.now() - seat.added_at
                if elapsed < minimum:
                    if fm is None:
                        fm = _resolve_floor_manager(floor_manager_id, floor_manager_pin)
                    if fm is None:
                        elapsed_minutes = int(elapsed.total_seconds() // 60)
                        raise MinimumPlayerTimeNotMetError(
                            f'{player.display_name} must be seated at least {settings_obj.min_player_time_minutes} '
                            f'minutes before chips can be returned (seated {elapsed_minutes} minute(s) so far) — '
                            f'a Floor Manager PIN is required to override this.'
                        )

    if game_day is not None and game_day.status == GameDay.Status.OPEN:
        _ensure_seated(game_day, player, recorded_by, block_departed=(type == Transaction.Type.CHIPS_OUT))

    with db_transaction.atomic():
        txn = Transaction.objects.create(
            game_day=game_day, player=player, type=type,
            amount=player_portion if type == Transaction.Type.CHIPS_OUT else amount,
            currency=currency, conversion_rate=conversion_rate,
            channel=channel or DEFAULT_CHANNEL_BY_TYPE[type], notes=notes,
            recorded_by=recorded_by, floor_manager=fm,
            confirmed_at=timezone.now() if fm else None,
            tip_category=tip_category, masseuse=masseuse,
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
    Cashier initiates a cash-out transfer; it lands PENDING_APPROVAL unless
    it clears the auto-approval threshold (see the bottom of this function).

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

    Revised 2026-09-23: a payout at or below
    ClubSettings.payout_auto_approve_threshold (Owner-editable, default
    ₦500,000) skips PENDING_APPROVAL entirely and runs the same funds-check
    + real transfer approve_payout does — see _execute_payout_transfer,
    shared by both. `approved_by=None` on the resulting transaction is the
    marker for "auto-approved, nobody manually signed off" (vs a real
    Owner's id for a manual approval).

    Revised 2026-09-27 — automatic netting against a prior outstanding
    balance. The Cashier's own request is still validated against ONLY
    today's game-day winnings (`available` below) — they never see, and
    never get shown, a player's lifetime figure (CONCEPT.md's "Cashier
    player-history visibility"). But a player who ALSO owes the house from
    an earlier game-day (a debt the Cashier has no way to know about) could
    otherwise have their full requested amount transferred out in cash while
    that older debt just sits there uncollected — the ledger nets it
    mathematically (player_balance is one cumulative sum), but the real bank
    transfer wouldn't. So the amount that actually leaves the bank — what
    gets created here, what the auto-approval threshold is measured
    against — is capped a second time, at the player's LIFETIME balance
    (selectors.player_balance, which already reflects tonight's win netted
    against every prior game-day). If that's less than what was requested,
    the difference already went to closing out the old debt the instant
    tonight's win was recorded — nothing further needs to happen for that
    half; only the remainder becomes this Transaction, with the original
    ask preserved on requested_amount and spelled out in notes so it's
    visible on the ledger rather than silently substituted. If the netted
    amount is zero (this game-day's win doesn't even cover the old debt),
    a ₦0 payout is still recorded (revised 2026-09-27 — see the net_amount
    <= 0 branch below), settled immediately since there's nothing to
    actually transfer; the Cashier still isn't told the debt figure itself.

    Revised 2026-09-27 — ClubSettings.cashier_can_initiate_payout (Owner-
    only, default True): off rejects a Cashier's call to this outright,
    before any of the checks below run. Mirrored in the frontend (the
    Payout button hides/disables on ActiveGameDayView.vue), but enforced
    here too since this is reachable directly via the API regardless of
    what the UI shows. Doesn't affect initiate_direct_payout (the Owner's
    own, separate Players-page flow) at all.
    """
    if operator.role == StaffUser.Role.CASHIER and not ClubSettings.load().cashier_can_initiate_payout:
        raise AuthorizationError('A Cashier is not currently permitted to initiate a payout — ask the Owner.')

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

    # Second, independent cap — see the netting note above. Computed AFTER
    # the game-day-scoped check above (never instead of it): that check is
    # what the Cashier's own request is validated and error-messaged
    # against; this one only ever silently reduces what actually pays out.
    # Guarded on `amount > 0` — a genuinely ₦0 request (a couple of existing
    # tests use one just to get a Transaction to act on) nets to 0 too, but
    # that's not "the old debt ate this payout," there was never anything
    # requested in the first place; only an actually-positive ask that nets
    # down to nothing is the special case this guard exists for.
    net_amount = min(amount, max(selectors.player_balance(player), Decimal('0')))

    _ensure_seated(game_day, player, operator)  # a payout never brings back a departed player

    # Revised 2026-09-27 — a prior debt LARGER than the request (net_amount
    # would be 0) used to raise here with NOTHING recorded at all: no
    # Transaction, no ledger line, nothing for the "Payout BBF" line (see
    # LedgerTable.vue) to attach to. Now it's still recorded — a ₦0 payout,
    # settled immediately (there is nothing to actually transfer, so this
    # never reaches a real Paystack call), with requested_amount preserved
    # exactly as normal. cleared (= amount - net_amount, used by the BBF
    # line's own display) is CAPPED at the requested amount here by the
    # exact same arithmetic as every other case — net_amount=0 makes
    # cleared == amount — never the full prior debt if that debt happens to
    # be larger than what was actually requested; only up to what was asked
    # for is ever shown as "brought forward," per explicit follow-up.
    if amount > 0 and net_amount <= 0:
        notes = (
            f'Cashier requested ₦{amount:,}. All of it applied to an outstanding balance '
            f'from a previous game-day; net ₦0 payable.'
        )
        return Transaction.objects.create(
            game_day=game_day, player=player, type=Transaction.Type.PAYOUT, amount=Decimal('0'),
            requested_amount=amount, channel=Transaction.Channel.CASHIER, recorded_by=operator,
            notes=notes, status=Transaction.Status.APPROVED, approved_by=None, approved_at=timezone.now(),
        )

    notes = ''
    if net_amount < amount:
        cleared = amount - net_amount
        # "Net" spelled out explicitly (not just "payable") — a first live
        # read of the old wording ("₦X applied...; ₦Y payable") was
        # misread as Y being a sub-amount rather than the actual net figure
        # the auto-approval threshold is compared against. Fixed 2026-09-27.
        notes = (
            f'Cashier requested ₦{amount:,}. ₦{cleared:,} applied to an outstanding balance '
            f'from a previous game-day; net ₦{net_amount:,} payable.'
        )
    transaction_obj = Transaction.objects.create(
        game_day=game_day, player=player, type=Transaction.Type.PAYOUT, amount=net_amount,
        requested_amount=amount if net_amount < amount else None,
        channel=Transaction.Channel.CASHIER, recorded_by=operator, notes=notes,
        status=Transaction.Status.PENDING_APPROVAL,
    )
    if net_amount <= ClubSettings.load().payout_auto_approve_threshold:
        return _execute_payout_transfer(transaction_obj, approved_by=None)
    return transaction_obj


def initiate_direct_payout(player, amount, operator):
    """
    Owner-initiated payout from the Players page (2026-09-24) — pays out up
    to a player's LIFETIME outstanding balance (selectors.player_balance),
    with no game-day involved at all: game_day=None on the resulting
    Transaction, same "between-game-day" convention as any other Outstanding
    entry (it shows up there, not on any game-day's ledger).

    Distinct from initiate_payout, which is always Cashier-side, always
    scoped to a currently-open game-day, and capped at that game-day's own
    winnings — this is the back-office equivalent for a player who's owed
    money independent of tonight's table (e.g. from a Deal, or a balance
    carried over from a previous game-day). No "must have left the table"
    gate either — there's no table this is scoped to.
    """
    available = max(selectors.player_balance(player), Decimal('0'))
    if amount <= 0:
        raise InvalidStateError('Enter an amount greater than zero.')
    if amount > available:
        raise InvalidStateError(
            f'This exceeds what {player.display_name} is owed (available: ₦{available:,}).'
        )
    if not player.bank_accounts.filter(is_default=True).exists():
        raise InvalidStateError(
            f'{player.display_name} has no bank account on file — add one before requesting a payout.'
        )

    transaction_obj = Transaction.objects.create(
        game_day=None, player=player, type=Transaction.Type.PAYOUT, amount=amount,
        channel=Transaction.Channel.CASHIER, recorded_by=operator,
        status=Transaction.Status.PENDING_APPROVAL,
    )
    if amount <= ClubSettings.load().payout_auto_approve_threshold:
        return _execute_payout_transfer(transaction_obj, approved_by=None)
    return transaction_obj


def _execute_payout_transfer(transaction_obj, approved_by):
    """
    Shared by approve_payout (Owner manually approves) and
    initiate_payout's auto-approval path (amount at/under
    ClubSettings.payout_auto_approve_threshold, approved_by=None) — the
    funds-guard, the real Paystack transfer, and the resulting status are
    identical either way; only who (if anyone) approved it differs.

    Guards against the club's Main Account balance itself going negative —
    checked first, before approved_by/approved_at are ever touched, so an
    insufficient-funds rejection leaves the transaction completely
    untouched and retryable once funds arrive (distinct from
    TRANSFER_FAILED, which means a transfer was actually attempted and
    failed). Runs inside one atomic, row-locked block: two concurrent
    approvals of the SAME transaction (double-click, two tabs) would
    otherwise have a bare TOCTOU race on the status check alone;
    select_for_update() serializes that plus the funds check. If the
    transfer can't be sent (no bank account on file, Paystack rejects
    it, ...), the payout lands TRANSFER_FAILED instead of APPROVED so it's
    visibly stuck rather than silently "approved" with nothing moving —
    retryable by calling approve_payout again once the underlying issue is
    fixed.
    """
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

        transaction_obj.approved_by = approved_by
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


def approve_payout(transaction_obj, operator):
    """
    Owner manually approves a still-pending (or previously TRANSFER_FAILED)
    payout — the auto-approval path (see initiate_payout) handles anything
    at or under the club's threshold on its own; this is for the rest.
    See _execute_payout_transfer for what approval actually does.
    """
    if operator.role != StaffUser.Role.OWNER:
        raise AuthorizationError('Only the Owner can approve a payout.')
    if transaction_obj.type != Transaction.Type.PAYOUT:
        raise ValueError('Not a payout transaction.')
    return _execute_payout_transfer(transaction_obj, approved_by=operator)


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
