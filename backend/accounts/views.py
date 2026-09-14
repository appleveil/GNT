from django.db import transaction as db_transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import FloorManager, Player, PlayerBankAccount, StaffUser
from .permissions import IsCashierOrOwner, IsOwner

PIN_MIN_LENGTH = 4
PIN_MAX_LENGTH = 8
from .serializers import (
    FloorManagerSerializer,
    PlayerBankAccountSerializer,
    PlayerSerializer,
    StaffLoginSerializer,
    StaffUserCreateSerializer,
    StaffUserSerializer,
)


class StaffLoginView(TokenObtainPairView):
    serializer_class = StaffLoginSerializer
    permission_classes = [AllowAny]


class LogoutView(APIView):
    """Blacklists the refresh token so it can no longer be used to mint new access tokens."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            RefreshToken(request.data['refresh']).blacklist()
        except (KeyError, TokenError):
            pass
        return Response(status=204)


class SetOwnPinView(APIView):
    """
    Owner sets/resets their own in-person authorization PIN — distinct from
    their login password, used for Open Game-Day / Set FX Rate. See
    CONCEPT.md's "Open Game-Day flow." Owner-only: a Cashier/Accountant has no
    such PIN in v1.
    """

    permission_classes = [IsOwner]

    def post(self, request):
        pin = request.data.get('pin', '')
        if not (PIN_MIN_LENGTH <= len(pin) <= PIN_MAX_LENGTH):
            return Response(
                {'pin': f'A PIN must be {PIN_MIN_LENGTH}-{PIN_MAX_LENGTH} characters.'}, status=400,
            )
        request.user.set_pin(pin)
        request.user.save(update_fields=['pin_hash'])
        return Response(status=204)


class StaffUserViewSet(viewsets.ModelViewSet):
    """Owner-only: create/deactivate Cashier and Accountant accounts."""

    queryset = StaffUser.objects.all().order_by('username')
    permission_classes = [IsOwner]

    def get_serializer_class(self):
        return StaffUserCreateSerializer if self.action == 'create' else StaffUserSerializer

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def owners(self, request):
        """
        Active Owners only — not the full staff list. Added 2026-09-14: the
        Open Game-Day flow needs a Cashier to pick "who's authorizing" from
        Owner-or-Floor-Manager, without exposing every Cashier/Accountant
        username to a Cashier session.
        """
        owners = StaffUser.objects.filter(role=StaffUser.Role.OWNER, is_active=True).order_by('username')
        return Response(StaffUserSerializer(owners, many=True).data)


class FloorManagerViewSet(viewsets.ModelViewSet):
    """
    Read (list/retrieve): any authenticated staff — needed to pick "who's
    authorizing" on the Open Game-Day flow (relaxed 2026-09-14; was Owner-only).
    Write (create/update/delete): Owner-only, unchanged.
    """

    serializer_class = FloorManagerSerializer

    def get_queryset(self):
        qs = FloorManager.objects.all().order_by('name')
        # Non-Owners only see active FMs — an inactive one can't authorize
        # anything anyway, so listing them would just be a confusing dead end.
        if getattr(self.request.user, 'role', None) != StaffUser.Role.OWNER:
            qs = qs.filter(is_active=True)
        return qs

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsAuthenticated()]
        return [IsOwner()]


class PlayerViewSet(viewsets.ModelViewSet):
    """Read: any authenticated staff. Write: Cashier or Owner only."""

    queryset = Player.objects.all().prefetch_related('bank_accounts')
    serializer_class = PlayerSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy', 'provision_gaming_account'):
            return [IsCashierOrOwner()]
        return super().get_permissions()

    @action(detail=True, methods=['post'], url_path='provision-gaming-account')
    def provision_gaming_account(self, request, pk=None):
        """
        Creates the player's Gaming Account (Paystack Customer + Dedicated
        Virtual Account) if it doesn't already exist. A PaystackAPIError here
        (e.g. Dedicated NUBAN not yet enabled) surfaces as 502 via the global
        exception handler — see lpc_backend/exception_handling.py.
        """
        from payments.services import provision_gaming_account

        player = self.get_object()
        provision_gaming_account(player)
        player.refresh_from_db()
        return Response(PlayerSerializer(player, context={'request': request}).data, status=status.HTTP_201_CREATED)


class PlayerBankAccountViewSet(viewsets.ModelViewSet):
    """Nested under a player — Cashier/Owner manage a player's receiving accounts."""

    serializer_class = PlayerBankAccountSerializer
    permission_classes = [IsCashierOrOwner]

    def get_queryset(self):
        return PlayerBankAccount.objects.filter(player_id=self.kwargs['player_pk'])

    def perform_create(self, serializer):
        # Setting is_default=True here without first clearing any existing
        # default violates one_default_bank_account_per_player (a real
        # IntegrityError, found live 2026-09-14) — the DB constraint is
        # correct, this view just never unset the old one for it.
        with db_transaction.atomic():
            if serializer.validated_data.get('is_default'):
                self.get_queryset().update(is_default=False)
            serializer.save(player_id=self.kwargs['player_pk'])

    def perform_update(self, serializer):
        with db_transaction.atomic():
            if serializer.validated_data.get('is_default'):
                self.get_queryset().exclude(pk=serializer.instance.pk).update(is_default=False)
            serializer.save()
