"""
Paystack integration: webhook handling (deposit capture + payout status),
Gaming Account provisioning, and payout transfers — all built on the
single-integration Customer+DVA model in paystack_client.py.
"""

import hashlib
import hmac
from decimal import Decimal

from django.conf import settings
from django.db import transaction as db_transaction

from accounts.models import Player
from gaming.models import Transaction
from gaming.selectors import current_open_game_day
from gaming.services import record_transaction

from . import paystack_client
from .models import DedicatedVirtualAccount, PaystackAccount
from .paystack_client import PaystackAPIError, PaystackNotConfiguredError  # re-exported for callers

__all__ = [
    'UnrecognizedAccountError', 'PaystackAPIError', 'PaystackNotConfiguredError',
    'verify_signature', 'handle_charge_success', 'handle_transfer_event',
    'provision_gaming_account', 'initiate_payout_transfer',
]


class UnrecognizedAccountError(Exception):
    """No Gaming Account matches the customer_code in the webhook payload."""


def verify_signature(raw_body: bytes, signature_header: str) -> bool:
    """
    Paystack signs every webhook with x-paystack-signature: a hex HMAC-SHA512 of
    the raw request body, keyed with the account's secret key. Must be computed
    over the exact raw bytes — never the re-serialized/parsed body.
    """
    if not signature_header or not settings.PAYSTACK_SECRET_KEY:
        return False
    computed = hmac.new(
        settings.PAYSTACK_SECRET_KEY.encode('utf-8'), raw_body, digestmod=hashlib.sha512,
    ).hexdigest()
    return hmac.compare_digest(computed, signature_header)


def handle_charge_success(data: dict):
    """
    Handles a `charge.success` event for a Dedicated Virtual Account deposit.
    Idempotent via Transaction.external_reference (unique): replaying the same
    Paystack reference is a no-op, not a duplicate credit.

    Returns the created Transaction, or None if there was nothing to do
    (not a DVA deposit, or already processed).

    Note: this used to also queue a "sweep to Main account" transfer — removed
    2026-09-13. Under the single-integration Customer+DVA model (see
    paystack_client.py) there is only one Paystack balance; the deposit is
    already in it the moment it clears. "Forwarding to the Main account" is
    this ledger entry itself (channel=TRANSFER_DVA), not a second Paystack
    money movement.
    """
    if data.get('channel') != 'dedicated_nuban':
        return None  # not a DVA deposit — e.g. a card charge; nothing for us to do here

    reference = data['reference']
    if Transaction.objects.filter(external_reference=reference).exists():
        return None  # already processed — Paystack retried a webhook we already handled

    customer_code = (data.get('customer') or {}).get('customer_code')
    try:
        paystack_account = PaystackAccount.objects.select_related('player').get(
            account_type=PaystackAccount.AccountType.GAMING, paystack_customer_code=customer_code,
        )
    except PaystackAccount.DoesNotExist:
        raise UnrecognizedAccountError(f'No Gaming Account found for customer {customer_code!r}.')

    amount_naira = Decimal(data['amount']) / Decimal('100')  # Paystack amounts are in kobo
    sender_name = (data.get('authorization') or {}).get('sender_name', 'unknown sender')

    txn = record_transaction(
        type=Transaction.Type.PAYMENT_TRANSFER, amount=amount_naira, recorded_by=None,
        game_day=current_open_game_day(), player=paystack_account.player,
        channel=Transaction.Channel.TRANSFER_DVA,
        notes=f'Webhook-captured deposit from {sender_name}',
    )
    # external_reference is set after creation since record_transaction doesn't
    # accept it directly — keeps that generic entry point free of Paystack specifics.
    Transaction.objects.filter(pk=txn.pk).update(external_reference=reference)
    txn.refresh_from_db()
    return txn


def handle_transfer_event(event: str, data: dict):
    """
    Handles transfer.success / transfer.failed / transfer.reversed for a
    payout previously sent via initiate_payout_transfer. Matched by
    external_reference (the transfer_code recorded there). Idempotent: safe
    to redeliver the same event.

    Returns the updated Transaction, or None if it doesn't match any payout
    we know about (e.g. a transfer initiated outside this app).
    """
    transfer_code = data.get('transfer_code')
    if not transfer_code:
        return None
    try:
        txn = Transaction.objects.get(external_reference=transfer_code, type=Transaction.Type.PAYOUT)
    except Transaction.DoesNotExist:
        return None

    if event == 'transfer.success':
        txn.status = Transaction.Status.POSTED
        txn.save(update_fields=['status'])
    elif event in ('transfer.failed', 'transfer.reversed'):
        reason = (data.get('reason') or event).strip()
        txn.status = Transaction.Status.TRANSFER_FAILED
        txn.notes = f'{txn.notes}\nTransfer {event}: {reason}'.strip()
        txn.save(update_fields=['status', 'notes'])
    return txn


def provision_gaming_account(player: Player) -> PaystackAccount:
    """
    Creates a player's Gaming Account: a Paystack Customer plus a Dedicated
    Virtual Account, both under the club's one Paystack integration. Safe to
    call more than once — an already-provisioned player's existing account is
    returned as-is.

    Raises PaystackNotConfiguredError (no key set) or PaystackAPIError
    (Paystack rejected the request — commonly: Dedicated NUBAN not yet
    enabled on the account) straight through to the caller; the frontend's
    "Gaming Account not yet available" state is exactly this case.
    """
    existing = PaystackAccount.objects.filter(
        account_type=PaystackAccount.AccountType.GAMING, player=player,
    ).first()
    if existing is not None:
        return existing

    first_name, _, last_name = player.display_name.partition(' ')
    last_name = last_name or player.account_code
    # Paystack customers are keyed by email; players don't have one, so a
    # stable, unique placeholder is synthesized from the account code.
    slug = player.account_code.lower().replace(' ', '-')
    email = f'{slug}@players.lpc.local'

    customer = paystack_client.create_customer(email=email, first_name=first_name, last_name=last_name)
    dva = paystack_client.create_dedicated_account(customer_code=customer['customer_code'])
    bank = dva.get('bank') or {}

    with db_transaction.atomic():
        paystack_account = PaystackAccount.objects.create(
            account_type=PaystackAccount.AccountType.GAMING, player=player,
            paystack_customer_code=customer['customer_code'], label=player.display_name,
        )
        DedicatedVirtualAccount.objects.create(
            paystack_account=paystack_account, paystack_dva_id=str(dva.get('id', '')),
            bank_name=bank.get('name', ''), bank_code=bank.get('slug', ''),
            account_number=dva.get('account_number', ''), account_name=dva.get('account_name', ''),
        )
    return paystack_account


def initiate_payout_transfer(transaction_obj: Transaction) -> str:
    """
    Calls Paystack's Transfer API to move payout funds to the player's bank
    account. Called by gaming.services.approve_payout right after Owner
    approval; a PaystackAPIError raised here is caught there and recorded as
    TRANSFER_FAILED rather than failing the approval itself.

    Returns the transfer_code for the caller to store as external_reference —
    doesn't save transaction_obj itself, so the caller controls exactly what
    gets persisted alongside it in one write. Actual completion (POSTED) is
    confirmed later by the transfer.success webhook, not by this call returning.
    """
    player = transaction_obj.player
    bank_account = player.bank_accounts.filter(is_default=True).first()
    if bank_account is None:
        raise PaystackAPIError('Player has no default bank account on file — add one before approving.')

    if not bank_account.paystack_recipient_code:
        recipient = paystack_client.create_transfer_recipient(
            name=bank_account.account_name, account_number=bank_account.account_number,
            bank_code=bank_account.bank_code,
        )
        bank_account.paystack_recipient_code = recipient['recipient_code']
        bank_account.save(update_fields=['paystack_recipient_code'])

    result = paystack_client.initiate_transfer(
        amount_naira=transaction_obj.amount, recipient_code=bank_account.paystack_recipient_code,
        reason=f'LPC payout — {player.display_name}',
    )
    transfer_code = result.get('transfer_code')
    if not transfer_code:
        raise PaystackAPIError('Paystack accepted the transfer but returned no transfer_code to track it by.')
    return transfer_code
