from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Player, StaffUser
from accounts.permissions import IsCashierOrOwner, IsOwner, IsOwnerOrAccountant

from . import selectors, services
from .exceptions import TableFullError
from .models import ConversionRate, GameDay, Transaction
from .serializers import (
    CloseGameDaySerializer,
    ConversionRateSerializer,
    GameDaySeatedPlayerSerializer,
    GameDaySerializer,
    GameDaySummaryPreviewSerializer,
    InitiatePayoutSerializer,
    LedgerEntrySerializer,
    OpenGameDaySerializer,
    RecordTransactionSerializer,
    SeatPlayerSerializer,
    SetConversionRateSerializer,
    TransactionSerializer,
    VoidTransactionSerializer,
)

# Only the Owner can create these — a Deal/write-off is the Owner's own decision.
OWNER_ONLY_TRANSACTION_TYPES = {Transaction.Type.PAYMENT_DEAL, Transaction.Type.WRITE_OFF}


class GameDayViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = GameDay.objects.all().order_by('-number')
    serializer_class = GameDaySerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def current(self, request):
        """The currently open game-day, or null — added 2026-09-14 so the frontend
        doesn't have to fetch the whole history just to find today's."""
        game_day = selectors.current_open_game_day()
        return Response(GameDaySerializer(game_day).data if game_day else None)

    @action(detail=False, methods=['post'])
    def open(self, request):
        """Owner or a Floor Manager PIN required — see gaming.services.open_game_day."""
        serializer = OpenGameDaySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        game_day = services.open_game_day(
            number=data['number'],
            started_at=data.get('started_at') or timezone.now(),
            operator=request.user,
            floor_manager_id=data.get('floor_manager_id'),
            floor_manager_pin=data.get('floor_manager_pin'),
            owner_id=data.get('owner_id'),
            owner_pin=data.get('owner_pin'),
        )
        return Response(GameDaySerializer(game_day).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='close-preview')
    def close_preview(self, request, pk=None):
        """
        What close() would write to GameDaySummary, computed live (read-only —
        game_day_summary_data has no side effects) so the Cashier's close
        confirmation can show real numbers before committing. Added 2026-09-14.
        """
        game_day = self.get_object()
        data = selectors.game_day_summary_data(game_day)
        data['num_players_seated'] = selectors.game_day_players(game_day).count()
        data['outstanding_chips_after_close'] = selectors.outstanding_chips_total() + data['chips_variance']
        return Response(GameDaySummaryPreviewSerializer(data).data)

    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        """Cashier, Owner, or a Floor Manager PIN — any one alone."""
        game_day = self.get_object()
        serializer = CloseGameDaySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        game_day = services.close_game_day(
            game_day, operator=request.user,
            floor_manager_id=data.get('floor_manager_id'),
            floor_manager_pin=data.get('floor_manager_pin'),
        )
        return Response(GameDaySerializer(game_day).data)

    @action(detail=True, methods=['get'])
    def ledger(self, request, pk=None):
        """The club-wide Game-Day Ledger (CONCEPT.md's spec'd worked example) —
        one cumulative running_balance across every player's interleaved
        transactions. NOT any individual player's balance — see `activity`."""
        game_day = self.get_object()
        rows = selectors.game_day_ledger(game_day)
        return Response(LedgerEntrySerializer(rows, many=True).data)

    @action(detail=True, methods=['get'])
    def activity(self, request, pk=None):
        """
        The Cashier's live 'today's activity' feed on the Active Game-Day
        working screen — same rows as `ledger`, but running_balance is scoped
        per-player (see gaming.selectors.game_day_activity_feed). Added
        2026-09-14 after `ledger`'s club-wide total was found displayed next
        to individual players' names, reading as their own balance when it
        wasn't.
        """
        game_day = self.get_object()
        rows = selectors.game_day_activity_feed(game_day)
        return Response(LedgerEntrySerializer(rows, many=True).data)

    @action(detail=True, methods=['get'], url_path=r'players/(?P<player_pk>\d+)/ledger')
    def player_ledger(self, request, pk=None, player_pk=None):
        game_day = self.get_object()
        player = get_object_or_404(Player, pk=player_pk)
        rows = selectors.player_game_day_ledger(game_day, player)
        return Response(LedgerEntrySerializer(rows, many=True).data)

    @action(detail=True, methods=['get', 'post'], url_path='players')
    def players(self, request, pk=None):
        """
        GET: players seated at this game-day (see GameDayPlayer) — the
        Cashier-facing Players list, scoped to the current game-day only.
        POST: seat a player for this game-day — either an existing player
        (player_id) or a brand-new one (account_code + display_name), per
        CONCEPT.md's Buy-in flow. Cashier or Owner only, same as PlayerViewSet.
        """
        game_day = self.get_object()
        if request.method == 'GET':
            rows = selectors.game_day_players(game_day)
            return Response(GameDaySeatedPlayerSerializer(rows, many=True).data)

        if not IsCashierOrOwner().has_permission(request, self):
            return Response({'detail': 'Only a Cashier or the Owner can add a player.'}, status=403)
        serializer = SeatPlayerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            player = services.seat_player(
                game_day, request.user, player=data.get('player'),
                player_fields=(
                    {'account_code': data['account_code'], 'display_name': data['display_name']}
                    if 'player' not in data else None
                ),
                seat_number=data.get('seat_number'),
            )
        except TableFullError as exc:
            # Caught here (not left to the global handler) so the response can
            # carry registered_not_seated/player_id — the frontend needs to
            # tell "seat capacity full" apart from any other 400 without
            # string-matching the message. The Player row (if newly created)
            # is NOT rolled back — see seat_player's own docstring.
            return Response(
                {'detail': str(exc), 'registered_not_seated': True, 'player_id': exc.player.id}, status=400,
            )
        seat = selectors.game_day_players(game_day).get(player=player)
        return Response(GameDaySeatedPlayerSerializer(seat).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path=r'players/(?P<player_pk>\d+)')
    def player_detail(self, request, pk=None, player_pk=None):
        """
        One seated player, game-day-scoped — backs PlayerDetailView. 404 if
        that player isn't seated at this game-day (they're never auto-added
        just by looking them up).
        """
        game_day = self.get_object()
        seat = get_object_or_404(selectors.game_day_players(game_day), player_id=player_pk)
        return Response(GameDaySeatedPlayerSerializer(seat).data)

    @action(detail=True, methods=['post'], url_path=r'players/(?P<player_pk>\d+)/leave')
    def player_leave(self, request, pk=None, player_pk=None):
        """
        Marks a seated player as having left tonight's table — see
        gaming.services.leave_table. Cashier or Owner only, same as seating
        them; no PIN (leaving isn't a physical count or a financial action —
        see PLAN.md's "leave the table" entry).
        """
        if not IsCashierOrOwner().has_permission(request, self):
            return Response({'detail': 'Only a Cashier or the Owner can do this.'}, status=403)
        game_day = self.get_object()
        player = get_object_or_404(Player, pk=player_pk)
        seat = services.leave_table(game_day, player, operator=request.user)
        return Response(GameDaySeatedPlayerSerializer(seat).data)

    @action(detail=True, methods=['post'], url_path=r'players/(?P<player_pk>\d+)/move-seat')
    def player_move_seat(self, request, pk=None, player_pk=None):
        """
        Relocates a still-seated player to a different numbered seat —
        either into a free one, or swapping with whoever's currently there
        (gaming.services.move_seat handles both). Cashier or Owner only,
        same as seating/leaving — not a physical count or financial action.
        Added 2026-09-17.
        """
        if not IsCashierOrOwner().has_permission(request, self):
            return Response({'detail': 'Only a Cashier or the Owner can do this.'}, status=403)
        game_day = self.get_object()
        player = get_object_or_404(Player, pk=player_pk)
        try:
            seat_number = int(request.data.get('seat_number'))
        except (TypeError, ValueError):
            return Response({'detail': 'seat_number is required.'}, status=400)
        seat = services.move_seat(game_day, player, seat_number, operator=request.user)
        return Response(GameDaySeatedPlayerSerializer(seat).data)


class ConversionRateViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ConversionRate.objects.all().order_by('-created_at')
    serializer_class = ConversionRateSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'])
    def set_rate(self, request):
        """Owner or a Floor Manager PIN — Cashier/Accountant cannot set this alone."""
        serializer = SetConversionRateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        rate = services.set_conversion_rate(
            currency=data['currency'], rate_to_naira=data['rate_to_naira'], operator=request.user,
            game_day=data.get('game_day'), floor_manager_id=data.get('floor_manager_id'),
            floor_manager_pin=data.get('floor_manager_pin'),
            owner_id=data.get('owner_id'), owner_pin=data.get('owner_pin'),
        )
        return Response(ConversionRateSerializer(rate).data, status=status.HTTP_201_CREATED)


class TransactionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    Transactions are never edited directly — only recorded, voided, or (for a
    payout) approved. See gaming.services for the authorization rules each
    action below delegates to.
    """

    queryset = Transaction.objects.all().order_by('-created_at')
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = RecordTransactionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        txn_type = data['type']

        if txn_type == Transaction.Type.PAYOUT:
            return Response(
                {'detail': 'Use the payout action to initiate a payout.'}, status=status.HTTP_400_BAD_REQUEST,
            )
        if txn_type in OWNER_ONLY_TRANSACTION_TYPES and request.user.role != StaffUser.Role.OWNER:
            return Response(
                {'detail': 'Only the Owner can record this transaction type.'}, status=status.HTTP_403_FORBIDDEN,
            )

        txn = services.record_transaction(
            type=txn_type, amount=data['amount'], recorded_by=request.user,
            game_day=data.get('game_day'), player=data.get('player'), notes=data.get('notes', ''),
            currency=data.get('currency', 'NGN'), conversion_rate=data.get('conversion_rate'),
            floor_manager_id=data.get('floor_manager_id'), floor_manager_pin=data.get('floor_manager_pin'),
            tip_category=data.get('tip_category'), service_staff=data.get('service_staff'),
        )
        return Response(TransactionSerializer(txn).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def void(self, request, pk=None):
        """Cashier can void their own same-day entry; Owner can void anything."""
        txn = self.get_object()
        serializer = VoidTransactionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        txn = services.void_transaction(txn, request.user, serializer.validated_data['reason'])
        return Response(TransactionSerializer(txn).data)

    @action(detail=False, methods=['post'])
    def payout(self, request):
        """Cashier initiates — always lands PENDING_APPROVAL until the Owner approves it."""
        serializer = InitiatePayoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        txn = services.initiate_payout(
            data['player'], data['amount'], request.user, game_day=data.get('game_day'),
        )
        return Response(TransactionSerializer(txn).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Every payout requires Owner approval, no threshold exemption."""
        txn = self.get_object()
        txn = services.approve_payout(txn, request.user)
        return Response(TransactionSerializer(txn).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Owner declines a pending/failed payout — see services.reject_payout."""
        txn = self.get_object()
        serializer = VoidTransactionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        txn = services.reject_payout(txn, request.user, serializer.validated_data['reason'])
        return Response(TransactionSerializer(txn).data)


class OutstandingLedgerView(APIView):
    """
    Owner/Accountant only (as of 2026-09-13) — spans past game-days, and a
    Cashier sees no cross-game-day history at all. See CONCEPT.md's "Cashier
    player-history visibility."
    """

    permission_classes = [IsOwnerOrAccountant]

    def get(self, request):
        player_id = request.query_params.get('player')
        player = get_object_or_404(Player, pk=player_id) if player_id else None
        rows = selectors.outstanding_ledger(player=player)
        return Response(LedgerEntrySerializer(rows, many=True).data)


class MainAccountLedgerView(APIView):
    """Owner-only — Accountant does not get Main account visibility (see CONCEPT.md)."""

    permission_classes = [IsOwner]

    def get(self, request):
        rows = selectors.main_account_ledger()
        return Response(LedgerEntrySerializer(rows, many=True).data)


class DashboardView(APIView):
    """Accountant and Owner only. Main account balance is Owner-only within it."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in {StaffUser.Role.ACCOUNTANT, StaffUser.Role.OWNER}:
            return Response({'detail': 'Not permitted.'}, status=status.HTTP_403_FORBIDDEN)
        total_debt, total_credit, debtor_count = selectors.dashboard_totals()
        data = {
            'total_outstanding_from_players': total_debt,
            'total_outstanding_to_players': total_credit,
            'debtor_count': debtor_count,
            'outstanding_chips': selectors.outstanding_chips_total(),
        }
        if request.user.role == StaffUser.Role.OWNER:
            data['main_account_balance'] = selectors.main_account_balance()
        return Response(data)
