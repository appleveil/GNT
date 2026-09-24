from django.db import transaction as db_transaction
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import AccountCode, FloorManager, Player, PlayerBankAccount, StaffMember, StaffUser
from .permissions import IsCashierOrOwner, IsFloorManagerOrOwner, IsOwner, IsOwnerOrAccountant

PIN_MIN_LENGTH = 4
PIN_MAX_LENGTH = 8
from .serializers import (
    AccountCodeSerializer,
    FloorManagerSerializer,
    PlayerBankAccountSerializer,
    PlayerSerializer,
    StaffLoginSerializer,
    StaffMemberSerializer,
    StaffPasswordResetSerializer,
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

    @action(detail=True, methods=['post'], url_path='reset-password')
    def reset_password(self, request, pk=None):
        """
        Owner-privileged reset of another staff user's login password — see
        StaffPasswordResetSerializer. Permission inherited from the viewset's
        class-level IsOwner; no extra check needed here.
        """
        user = self.get_object()
        serializer = StaffPasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user.set_password(serializer.validated_data['password'])
        user.save(update_fields=['password'])
        return Response(status=204)


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


class StaffMemberViewSet(viewsets.ModelViewSet):
    """
    Named, non-login staff (added 2026-09-17 as "Service Staff", generalized
    2026-09-23 — see StaffMember's own docstring, and its Role's MASSEUSE/
    DEALER/SERVICE) — read: any authenticated staff (needed for the Tip
    entry form's Masseuse picker, and the Admin page's own listing); write
    (create/deactivate): Floor Manager or Owner, matching CONCEPT.md's
    framing of "adding these service people" as a Floor Manager function,
    with the Owner able to do it too as usual.

    `?role=MASSEUSE` (added 2026-09-23) scopes the list to one role —
    used by the Tip entry form (only a Masseuse can be a named tip
    recipient) and by the Floor Manager's own "Masseuses" screen, which
    only ever shows/creates that one role. Mirrors StaffUserViewSet.owners'
    own role-filtering pattern.
    """

    serializer_class = StaffMemberSerializer

    def get_queryset(self):
        qs = StaffMember.objects.all().order_by('name')
        role = self.request.query_params.get('role')
        if role:
            qs = qs.filter(role=role)
        if getattr(self.request.user, 'role', None) not in (StaffUser.Role.FLOOR_MANAGER, StaffUser.Role.OWNER):
            qs = qs.filter(is_active=True)
        return qs

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsAuthenticated()]
        return [IsFloorManagerOrOwner()]


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


class AccountCodeViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """
    The Account Code / DVA pool (Admin page, added 2026-09-25) — Owner or
    Accountant stage codes ahead of time; gaming.services._assign_next_account_code
    auto-consumes the oldest available one when a new player registers, so
    a Cashier never types one in by hand any more (see AddPlayerModal.vue).

    List/create (managing the pool) are Owner-or-Accountant only.
    `available-count` is open to every authenticated role instead — the
    Cashier's Add Player form needs it to disable itself / show a notice
    when the pool is empty, without exposing the full pool listing (which
    names every linked player) to that role.
    """

    queryset = AccountCode.objects.all().order_by('-created_at')
    serializer_class = AccountCodeSerializer
    permission_classes = [IsOwnerOrAccountant]

    def create(self, request, *args, **kwargs):
        # A single {"code": ..., "account_number": ..., "account_name": ...}
        # still works via the default ModelSerializer path below;
        # {"codes": [{...}, ...]} is the bulk path the Admin page actually
        # uses — one row per staged DVA, built there from a manual "+ Add"
        # row or a parsed CSV/XLS/XLSX upload (parsing happens client-side;
        # this endpoint only ever sees plain rows). Duplicates (already in
        # the pool, or repeated within the same batch) are reported, not
        # fatal — every other row in the batch still gets added.
        rows = request.data.get('codes')
        if rows is None:
            return super().create(request, *args, **kwargs)

        errors = []
        seen_codes, seen_numbers = set(), set()
        cleaned = []
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                errors.append(f'Row {i + 1}: malformed.')
                continue
            code = str(row.get('code', '')).strip()
            account_number = str(row.get('account_number', '')).strip()
            account_name = str(row.get('account_name', '')).strip()
            label = code or account_number or f'Row {i + 1}'
            if not (code and account_number and account_name):
                errors.append(f'{label}: code, account number, and account name are all required.')
            elif code in seen_codes or account_number in seen_numbers:
                errors.append(f'{label}: duplicated within this batch.')
            else:
                seen_codes.add(code)
                seen_numbers.add(account_number)
                cleaned.append({'code': code, 'account_number': account_number, 'account_name': account_name})

        if cleaned:
            existing_codes = set(
                AccountCode.objects.filter(code__in=[r['code'] for r in cleaned]).values_list('code', flat=True),
            )
            existing_numbers = set(
                AccountCode.objects.filter(
                    account_number__in=[r['account_number'] for r in cleaned],
                ).values_list('account_number', flat=True),
            )
            to_create = []
            for r in cleaned:
                if r['code'] in existing_codes:
                    errors.append(f"{r['code']}: this code already exists.")
                elif r['account_number'] in existing_numbers:
                    errors.append(f"{r['account_number']}: this account number already exists.")
                else:
                    to_create.append(AccountCode(**r, created_by=request.user))
        else:
            to_create = []

        created = AccountCode.objects.bulk_create(to_create)
        return Response(
            {'created': AccountCodeSerializer(created, many=True).data, 'errors': errors},
            status=status.HTTP_201_CREATED if created else status.HTTP_400_BAD_REQUEST,
        )

    @action(detail=False, methods=['get'], url_path='available-count', permission_classes=[IsAuthenticated])
    def available_count(self, request):
        return Response({'count': AccountCode.objects.filter(linked_player__isnull=True).count()})
