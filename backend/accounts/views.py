import re

from django.db import transaction as db_transaction
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import ListAPIView
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from gaming import selectors
from gaming.activity import log_activity
from gaming.models import ActivityLog

from .models import AccountCode, FloorManager, Player, PlayerBankAccount, StaffMember, StaffUser
from .permissions import IsCashierOrOwner, IsFloorManagerOrOwner, IsOwner, IsOwnerOrAccountant

PIN_MIN_LENGTH = 4
PIN_MAX_LENGTH = 8
from .serializers import (
    AccountCodeSerializer,
    ActivityLogSerializer,
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

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            # Looked up post-hoc rather than threaded through the JWT
            # serializer — login is case-insensitive (accounts/backends.py),
            # so this mirrors that lookup exactly.
            user = StaffUser.objects.filter(username__iexact=request.data.get('username', '')).first()
            if user is not None:
                log_activity(user, ActivityLog.Action.LOGIN, f'{user.get_full_name() or user.username} logged in')
        return response


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
        log_activity(request.user, ActivityLog.Action.PIN_RESET, 'Set their own PIN')
        return Response(status=204)


class StaffUserViewSet(viewsets.ModelViewSet):
    """Owner-only: create/deactivate Cashier and Accountant accounts."""

    queryset = StaffUser.objects.all().order_by('username')
    permission_classes = [IsOwner]

    def get_serializer_class(self):
        return StaffUserCreateSerializer if self.action == 'create' else StaffUserSerializer

    def perform_create(self, serializer):
        user = serializer.save()
        log_activity(
            self.request.user, ActivityLog.Action.STAFF_CREATED,
            f'Created {user.get_role_display()} account for {user.get_full_name() or user.username}',
        )

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
        log_activity(
            request.user, ActivityLog.Action.PASSWORD_RESET,
            f"Reset {user.get_full_name() or user.username}'s password",
        )
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

    def perform_create(self, serializer):
        fm = serializer.save()
        log_activity(self.request.user, ActivityLog.Action.STAFF_CREATED, f'Added Floor Manager {fm.name}')

    def perform_update(self, serializer):
        # Only a PIN change is itself an "action" worth a log entry — a
        # plain name/is_active edit isn't one of the categories this log
        # covers.
        pin_changed = bool(self.request.data.get('pin'))
        fm = serializer.save()
        if pin_changed:
            log_activity(self.request.user, ActivityLog.Action.PIN_RESET, f"Reset Floor Manager {fm.name}'s PIN")


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

    def perform_create(self, serializer):
        member = serializer.save()
        log_activity(
            self.request.user, ActivityLog.Action.STAFF_CREATED,
            f'Added {member.get_role_display()} {member.name}',
        )


class PlayerViewSet(viewsets.ModelViewSet):
    """Read: any authenticated staff. Write: Cashier or Owner only."""

    queryset = Player.objects.all().prefetch_related('bank_accounts').select_related('gaming_account')
    serializer_class = PlayerSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy', 'provision_gaming_account'):
            return [IsCashierOrOwner()]
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        """
        Added 2026-10-02 for AddPlayerModal.vue's "+ New Player" button,
        which now registers a player here directly instead of going through
        seat_player (see that function's own "made OPT-IN" note) — it no
        longer seats them for any game-day at all, closing the old
        "Unassigned" list. Without an `account_code` in the payload, this
        mirrors seat_player's own path exactly: the next code is assigned
        from the AccountCode pool via gaming.services._assign_next_account_code
        (raises InvalidStateError, surfaced as 400 by the global exception
        handler, if the pool is empty). Passing an explicit `account_code`
        (not used by the frontend, but not removed) still goes through the
        normal serializer path unchanged.
        """
        if not request.data.get('account_code'):
            from gaming.services import _assign_next_account_code

            player = _assign_next_account_code(request.data.get('display_name', ''))
            log_activity(
                request.user, ActivityLog.Action.PLAYER_CREATED, f'Registered player {player.display_name}',
                player=player,
            )
            serializer = self.get_serializer(player)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        player = serializer.save()
        log_activity(
            self.request.user, ActivityLog.Action.PLAYER_CREATED, f'Registered player {player.display_name}',
            player=player,
        )

    def perform_update(self, serializer):
        # Credit limit is the one field on this viewset worth its own log
        # entry (Owner-only, per PlayerSerializer.validate_chips_limit) —
        # a display_name edit or similar isn't one of this log's categories.
        old_limit = serializer.instance.chips_limit
        player = serializer.save()
        if 'chips_limit' in serializer.validated_data and player.chips_limit != old_limit:
            log_activity(
                self.request.user, ActivityLog.Action.CREDIT_LIMIT_CHANGED,
                f"Changed {player.display_name}'s credit limit from "
                f'{old_limit if old_limit is not None else "none"} to '
                f'{player.chips_limit if player.chips_limit is not None else "none"}',
                player=player, details={'old': str(old_limit), 'new': str(player.chips_limit)},
            )

    def list(self, request, *args, **kwargs):
        """
        Bulk-computes balances for every player on the page in 1-2 aggregate
        queries total, instead of PlayerSerializer.get_balance/
        get_chips_used_today each running their own per-player query —
        found 2026-09-28 causing the Players page to load noticeably slowly
        even with only a handful of players (each row was 2-4 extra
        round-trips). See gaming.selectors.bulk_player_balances/
        bulk_player_game_day_balances.
        """
        from gaming.selectors import bulk_player_balances, bulk_player_game_day_balances, current_open_game_day

        players = list(self.filter_queryset(self.get_queryset()))
        player_ids = [p.id for p in players]
        game_day = current_open_game_day()
        context = self.get_serializer_context()
        context['lifetime_balances'] = bulk_player_balances(player_ids)
        context['game_day'] = game_day
        context['game_day_balances'] = bulk_player_game_day_balances(player_ids, game_day) if game_day else {}
        serializer = self.get_serializer(players, many=True, context=context)
        return Response(serializer.data)

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
            elif not re.fullmatch(r'\d{10}', account_number):
                errors.append(f'{label}: account number must be exactly 10 digits.')
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
        if created:
            log_activity(
                request.user, ActivityLog.Action.ACCOUNT_CODES_ADDED,
                f'Added {len(created)} account code(s)', details={'codes': [c.code for c in created]},
            )
        return Response(
            {'created': AccountCodeSerializer(created, many=True).data, 'errors': errors},
            status=status.HTTP_201_CREATED if created else status.HTTP_400_BAD_REQUEST,
        )

    @action(detail=False, methods=['get'], url_path='available-count', permission_classes=[IsAuthenticated])
    def available_count(self, request):
        return Response({'count': AccountCode.objects.filter(linked_player__isnull=True).count()})


class ActivityLogPagination(LimitOffsetPagination):
    default_limit = 50
    max_limit = 200


class ActivityLogView(ListAPIView):
    """
    GET /activity-log/ — see ActivityLog's own docstring and
    gaming.selectors.visible_activity for the role-scoping rule (every
    authenticated role can read this endpoint; what they see back differs).
    Optional filters: ?actor=<StaffUser id>, ?action=<ActivityLog.Action
    value>, ?date_from=<YYYY-MM-DD>, ?date_to=<YYYY-MM-DD> (inclusive).
    """

    serializer_class = ActivityLogSerializer
    pagination_class = ActivityLogPagination
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = selectors.visible_activity(self.request.user)
        params = self.request.query_params
        if params.get('actor'):
            qs = qs.filter(actor_id=params['actor'])
        if params.get('action'):
            qs = qs.filter(action=params['action'])
        if params.get('date_from'):
            qs = qs.filter(created_at__date__gte=params['date_from'])
        if params.get('date_to'):
            qs = qs.filter(created_at__date__lte=params['date_to'])
        return qs
