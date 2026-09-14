"""
Global DRF exception handler. Keeps views free of try/except around every
service call — a service raises AuthorizationError, this turns it into a 403.
"""

from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from gaming.exceptions import AuthorizationError, InvalidStateError
from payments.paystack_client import PaystackAPIError


def exception_handler(exc, context):
    if isinstance(exc, AuthorizationError):
        return Response({'detail': str(exc)}, status=403)
    if isinstance(exc, InvalidStateError):
        return Response({'detail': str(exc)}, status=400)
    if isinstance(exc, PaystackAPIError):
        # Covers PaystackNotConfiguredError too (a subclass) — surfaced as an
        # upstream failure, not a client error. approve_payout catches this
        # itself (turns it into a TRANSFER_FAILED status instead), so this
        # branch is really only reached by provision_gaming_account.
        return Response({'detail': str(exc)}, status=502)
    return drf_exception_handler(exc, context)
