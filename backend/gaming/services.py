"""
Authorization rules and state-changing actions, kept out of views.py so each
rule is independently callable/testable. See CONCEPT.md's "Scope decisions"
and "Floor Manager" sections for the rules encoded here.
"""

from django.utils import timezone

from accounts.models import FloorManager, StaffUser

from .exceptions import AuthorizationError
from .models import ConversionRate, GameDay, Transaction


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


def open_game_day(number, started_at, operator, floor_manager_id=None, floor_manager_pin=None):
    """Owner, or a Floor Manager PIN, can open a game-day. Cashier cannot do this alone."""
    fm = _resolve_floor_manager(floor_manager_id, floor_manager_pin)
    if operator.role != StaffUser.Role.OWNER and fm is None:
        raise AuthorizationError('Opening a game-day requires the Owner or a Floor Manager PIN.')
    return GameDay.objects.create(
        number=number, started_at=started_at, status=GameDay.Status.OPEN,
        opened_by=operator, opened_by_floor_manager=fm,
    )


def close_game_day(game_day, operator, floor_manager_id=None, floor_manager_pin=None):
    """Cashier, Owner, or a Floor Manager PIN can each close a game-day alone."""
    fm = _resolve_floor_manager(floor_manager_id, floor_manager_pin)
    allowed_roles = {StaffUser.Role.CASHIER, StaffUser.Role.OWNER}
    if operator.role not in allowed_roles and fm is None:
        raise AuthorizationError('Closing a game-day requires the Cashier, Owner, or a Floor Manager PIN.')
    game_day.status = GameDay.Status.CLOSED
    game_day.ended_at = timezone.now()
    game_day.closed_by = operator
    game_day.closed_by_floor_manager = fm
    game_day.save(update_fields=['status', 'ended_at', 'closed_by', 'closed_by_floor_manager'])
    return game_day


def set_conversion_rate(
    currency, rate_to_naira, operator, game_day=None, floor_manager_id=None, floor_manager_pin=None,
):
    """Owner, or a Floor Manager PIN, can set/update an FX rate. Cashier/Accountant cannot."""
    fm = _resolve_floor_manager(floor_manager_id, floor_manager_pin)
    if operator.role != StaffUser.Role.OWNER and fm is None:
        raise AuthorizationError('Setting the FX rate requires the Owner or a Floor Manager PIN.')
    return ConversionRate.objects.create(
        currency=currency, rate_to_naira=rate_to_naira, game_day=game_day,
        set_by=operator, set_by_floor_manager=fm,
    )


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


def initiate_payout(player, amount, operator, game_day=None):
    """Cashier initiates a cash-out transfer; it always lands PENDING_APPROVAL."""
    return Transaction.objects.create(
        game_day=game_day, player=player, type=Transaction.Type.PAYOUT, amount=amount,
        channel=Transaction.Channel.CASHIER, recorded_by=operator,
        status=Transaction.Status.PENDING_APPROVAL,
    )


def approve_payout(transaction_obj, operator):
    """Every payout requires Owner approval before funds move — no threshold exemption."""
    if operator.role != StaffUser.Role.OWNER:
        raise AuthorizationError('Only the Owner can approve a payout.')
    if transaction_obj.type != Transaction.Type.PAYOUT:
        raise ValueError('Not a payout transaction.')
    transaction_obj.status = Transaction.Status.APPROVED
    transaction_obj.approved_by = operator
    transaction_obj.approved_at = timezone.now()
    transaction_obj.save(update_fields=['status', 'approved_by', 'approved_at'])
    return transaction_obj
