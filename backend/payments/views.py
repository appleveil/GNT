import logging

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from . import services

logger = logging.getLogger(__name__)


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
