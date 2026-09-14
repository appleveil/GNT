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


class FloorManagerViewSet(viewsets.ModelViewSet):
    """Owner-only: manage Floor Manager staff records (name + PIN, no login of their own)."""

    queryset = FloorManager.objects.all().order_by('name')
    serializer_class = FloorManagerSerializer
    permission_classes = [IsOwner]


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
        serializer.save(player_id=self.kwargs['player_pk'])
