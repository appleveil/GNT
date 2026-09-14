"""
Thin wrapper over the Paystack REST API.

There is exactly ONE Paystack integration for the whole club — one secret/public
key pair (settings.PAYSTACK_SECRET_KEY/PUBLIC_KEY), one webhook. A player's
"Gaming Account" is NOT a separate Paystack integration (Paystack has no such
concept) — it's a Paystack Customer plus a Dedicated Virtual Account (DVA)
assigned to that customer, both created under this one integration. See
CONCEPT.md's "Gaming account" section and SCHEMA.md's PaystackAccount notes
for the correction from the original per-player-integration idea.

Every function here raises PaystackAPIError (or the more specific
PaystackNotConfiguredError) rather than returning falsy/partial data, so
callers never need to check a status field themselves.
"""

import requests
from django.conf import settings

BASE_URL = 'https://api.paystack.co'
TIMEOUT_SECONDS = 15


class PaystackAPIError(Exception):
    """Paystack rejected the request, or the request itself failed (network, timeout, ...)."""


class PaystackNotConfiguredError(PaystackAPIError):
    """No PAYSTACK_SECRET_KEY is set — nothing safe to call yet (e.g. local dev)."""


def _request(method: str, path: str, json: dict | None = None) -> dict | list:
    if not settings.PAYSTACK_SECRET_KEY:
        raise PaystackNotConfiguredError('PAYSTACK_SECRET_KEY is not configured.')

    headers = {
        'Authorization': f'Bearer {settings.PAYSTACK_SECRET_KEY}',
        'Content-Type': 'application/json',
    }
    try:
        response = requests.request(
            method, f'{BASE_URL}{path}', headers=headers, json=json, timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise PaystackAPIError(f'Could not reach Paystack: {exc}') from exc

    try:
        body = response.json()
    except ValueError:
        raise PaystackAPIError(f'Paystack returned a non-JSON response (status {response.status_code}).')

    if not response.ok or not body.get('status', False):
        message = body.get('message', f'Paystack request failed with status {response.status_code}.')
        raise PaystackAPIError(message)

    return body.get('data') or {}


def list_banks(country: str = 'nigeria') -> list[dict]:
    """
    GET /bank — every bank Paystack knows for `country`, each carrying the
    `code` used by transferrecipient/dedicated_account/bank_resolve. Backs the
    bank picker on the "Add bank account" form — the cashier picks a bank by
    name, never types a code. The caller (payments.views) caches this; it
    barely ever changes and is otherwise one extra Paystack round-trip per
    form open.
    """
    return _request('GET', f'/bank?country={country}&currency=NGN')


def resolve_account_number(account_number: str, bank_code: str) -> dict:
    """
    GET /bank/resolve — confirms the account name for an account number +
    bank code before it's saved, so the cashier can show the player "is this
    you?" instead of finding out a typo'd digit or wrong bank only when a
    payout later fails to resolve. Raises PaystackAPIError if Paystack can't
    resolve it (bad number, wrong bank, account doesn't exist, ...).
    """
    return _request('GET', f'/bank/resolve?account_number={account_number}&bank_code={bank_code}')


def create_customer(email: str, first_name: str, last_name: str, phone: str = '') -> dict:
    """POST /customer — one per player. Paystack dedupes by email, so calling
    this again for an existing email returns the existing customer, not an error."""
    return _request('POST', '/customer', json={
        'email': email, 'first_name': first_name, 'last_name': last_name, 'phone': phone,
    })


def create_dedicated_account(customer_code: str, preferred_bank: str = 'wema-bank') -> dict:
    """
    POST /dedicated_account — assigns a Dedicated Virtual Account to an
    existing customer. Requires the Dedicated NUBAN product to be enabled on
    the Paystack account (business KYC with a bank partner); until then this
    raises PaystackAPIError with Paystack's own message explaining why.
    """
    return _request('POST', '/dedicated_account', json={
        'customer': customer_code, 'preferred_bank': preferred_bank,
    })


def create_transfer_recipient(name: str, account_number: str, bank_code: str) -> dict:
    """POST /transferrecipient — a payout destination. Cached on
    PlayerBankAccount.paystack_recipient_code so it's only created once per bank account."""
    return _request('POST', '/transferrecipient', json={
        'type': 'nuban', 'name': name, 'account_number': account_number, 'bank_code': bank_code, 'currency': 'NGN',
    })


def initiate_transfer(amount_naira, recipient_code: str, reason: str) -> dict:
    """POST /transfer — moves money out of the club's one Paystack balance to
    a transfer recipient. amount_naira is converted to kobo (Paystack's unit)."""
    amount_kobo = int(round(amount_naira * 100))
    return _request('POST', '/transfer', json={
        'source': 'balance', 'amount': amount_kobo, 'recipient': recipient_code, 'reason': reason,
    })
