"""
Paystack webhook handling — signature verification and the DVA-deposit flow
described in CONCEPT.md's "Platform rules > Deposits" section.
"""

import hashlib
import hmac
from decimal import Decimal

from django.conf import settings

from gaming.models import Transaction
from gaming.selectors import current_open_game_day
from gaming.services import record_transaction

from .models import PaystackAccount


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
    """
    if data.get('channel') != 'dedicated_nuban':
        return None  # not a DVA deposit — e.g. a card charge; nothing for us to do here

    reference = data['reference']
    if Transaction.objects.filter(external_reference=reference).exists():
        return None  # already processed — Paystack retried a webhook we already handled

    customer_code = (data.get('customer') or {}).get('customer_code')
    try:
        paystack_account = PaystackAccount.objects.select_related('player').get(
            account_type=PaystackAccount.AccountType.GAMING, paystack_integration_id=customer_code,
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

    from .tasks import sweep_to_main_account
    sweep_to_main_account.delay(txn.id)

    return txn
