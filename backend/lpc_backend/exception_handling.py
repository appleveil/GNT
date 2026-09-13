"""
Global DRF exception handler. Keeps views free of try/except around every
service call — a service raises AuthorizationError, this turns it into a 403.
"""

from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from gaming.exceptions import AuthorizationError


def exception_handler(exc, context):
    if isinstance(exc, AuthorizationError):
        return Response({'detail': str(exc)}, status=403)
    return drf_exception_handler(exc, context)
