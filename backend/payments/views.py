import logging

from django.core.cache import cache
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.permissions import IsCashierOrOwner

from . import paystack_client, services

logger = logging.getLogger(__name__)

BANKS_CACHE_KEY = 'paystack_banks_ng'
BANKS_CACHE_TIMEOUT_SECONDS = 60 * 60 * 24  # bank list barely ever changes


class PaystackWebhookView(APIView):
    """
    Receives Paystack's webhook events. Always returns 200 once the signature
    checks out — including for events we don't act on or already processed —
    so Paystack doesn't endlessly retry; failures we need to know about are
    logged instead of surfaced as an error status.
    """

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'webhook'

    def post(self, request):
        # Read raw body before request.data touches the stream — Django can't
        # re-read the body once the parser has consumed it.
        raw_body = request.body
        signature = request.headers.get('x-paystack-signature', '')
        if not services.verify_signature(raw_body, signature):
            return Response(status=401)

        event = request.data.get('event')
        data = request.data.get('data') or {}

        if event == 'charge.success':
            try:
                services.handle_charge_success(data)
            except services.UnrecognizedAccountError as exc:
                logger.warning('Paystack webhook: %s', exc)
        elif event in ('transfer.success', 'transfer.failed', 'transfer.reversed'):
            services.handle_transfer_event(event, data)

        return Response(status=200)


class BankListView(APIView):
    """
    Nigerian banks (name + Paystack bank code) for the "Add bank account"
    picker — added 2026-09-14 so the cashier selects a bank by name and the
    bank code travels along invisibly, never typed. Cached process-wide for a
    day since the list is effectively static and this is called on every
    "Add bank account" form open.
    """

    permission_classes = [IsCashierOrOwner]

    def get(self, request):
        banks = cache.get(BANKS_CACHE_KEY)
        if banks is None:
            banks = paystack_client.list_banks()
            cache.set(BANKS_CACHE_KEY, banks, timeout=BANKS_CACHE_TIMEOUT_SECONDS)
        return Response(banks)


class ResolveAccountView(APIView):
    """
    Confirms the account name for an account number + bank code before it's
    saved as a player's bank account — lets the cashier show the player "is
    this you?" instead of finding out about a typo only when a payout later
    fails. Added 2026-09-14. A PaystackAPIError (can't resolve — bad number,
    wrong bank, ...) surfaces as 502 via the global exception handler, same
    convention as provision_gaming_account.
    """

    permission_classes = [IsCashierOrOwner]

    def get(self, request):
        account_number = request.query_params.get('account_number', '')
        bank_code = request.query_params.get('bank_code', '')
        if len(account_number) != 10 or not account_number.isdigit() or not bank_code:
            return Response(
                {'detail': 'account_number (10 digits) and bank_code are required.'}, status=400,
            )
        data = paystack_client.resolve_account_number(account_number, bank_code)
        return Response(data)
