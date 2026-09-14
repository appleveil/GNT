from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import FloorManager, Player, PlayerBankAccount, StaffUser

from . import selectors, services
from .exceptions import AuthorizationError, InvalidStateError
from .models import ConversionRate, GameDay, GameDayPlayer, Transaction


class LedgerMathTests(TestCase):
    """Replays the worked example from CONCEPT.md's Game-day ledger table and
    checks the computed running balance matches it line for line."""

    def setUp(self):
        self.owner = StaffUser.objects.create_user(username='owner', password='x', role=StaffUser.Role.OWNER)
        self.cashier = StaffUser.objects.create_user(username='cashier', password='x', role=StaffUser.Role.CASHIER)
        self.game_day = GameDay.objects.create(number=12, started_at=timezone.now(), opened_by=self.owner)
        self.marco = Player.objects.create(account_code='WWI 7', display_name='Marco')
        self.moses = Player.objects.create(account_code='WWI 12', display_name='Moses')
        self.mary = Player.objects.create(account_code='WWI 6', display_name='Mary')
        self.martin = Player.objects.create(account_code='WWI 9', display_name='Martin')
        self.mama = Player.objects.create(account_code='WWI 27', display_name='Mama')
        self.musa = Player.objects.create(account_code='WWI 2', display_name='Musa')
        self.mike = Player.objects.create(account_code='WWI 5', display_name='Mike')
        self._seq = 0
        self._base = timezone.now()

    def _txn(self, player, type_, amount, channel):
        # Force strictly increasing created_at so ordering is deterministic in the test,
        # independent of real wall-clock resolution.
        self._seq += 1
        txn = Transaction.objects.create(
            game_day=self.game_day, player=player, type=type_, amount=Decimal(amount),
            channel=channel, recorded_by=self.cashier,
        )
        Transaction.objects.filter(pk=txn.pk).update(created_at=self._base + timedelta(seconds=self._seq))
        return txn

    def test_game_day_ledger_matches_worked_example(self):
        T, C = Transaction.Type, Transaction.Channel
        self._txn(self.marco, T.CHIPS_OUT, 500000, C.CASHIER)
        self._txn(self.moses, T.CHIPS_OUT, 1000000, C.CASHIER)
        self._txn(self.mary, T.CHIPS_OUT, 500000, C.CASHIER)
        self._txn(self.martin, T.CHIPS_OUT, 500000, C.CASHIER)
        self._txn(self.mama, T.CHIPS_OUT, 500000, C.CASHIER)
        self._txn(self.musa, T.CHIPS_OUT, 1500000, C.CASHIER)
        self._txn(self.marco, T.PAYMENT_TRANSFER, 700000, C.TRANSFER_DVA)
        self._txn(self.marco, T.CHIPS_OUT, 2000000, C.CASHIER)
        self._txn(self.marco, T.CHIPS_IN, 500000, C.CHIPS)
        self._txn(self.marco, T.PAYMENT_CASH, 100000, C.CASH)
        self._txn(self.musa, T.PAYMENT_CASH, 1000000, C.CASH)
        self._txn(self.mike, T.CHIPS_OUT, 1500000, C.CASHIER)
        self._txn(self.mike, T.PAYMENT_TRANSFER, 1500000, C.TRANSFER_DVA)
        self._txn(self.mary, T.CHIPS_IN, 700000, C.CHIPS)
        self._txn(self.martin, T.PAYMENT_TRANSFER, 500000, C.TRANSFER_DVA)
        self._txn(self.marco, T.PAYMENT_DEAL, 1000000, C.DEAL)

        # Note: the source table in CONCEPT.md has a typo on its last row (-2,900,000
        # where -3,000,000 + 1,000,000 = -2,000,000). Corrected here; see CONCEPT.md.
        expected_balances = [
            -500000, -1500000, -2000000, -2500000, -3000000, -4500000,
            -3800000, -5800000, -5300000, -5200000, -4200000, -5700000,
            -4200000, -3500000, -3000000, -2000000,
        ]
        ledger = list(selectors.game_day_ledger(self.game_day))
        self.assertEqual(len(ledger), len(expected_balances))
        for row, expected in zip(ledger, expected_balances):
            self.assertEqual(row.running_balance, Decimal(expected))

    def test_rake_and_tips_excluded_from_game_day_ledger(self):
        self._txn(self.marco, Transaction.Type.CHIPS_OUT, 500000, Transaction.Channel.CASHIER)
        Transaction.objects.create(
            game_day=self.game_day, player=None, type=Transaction.Type.RAKE, amount=Decimal(1000),
            channel=Transaction.Channel.CASHIER, recorded_by=self.cashier,
        )
        ledger = list(selectors.game_day_ledger(self.game_day))
        self.assertEqual(len(ledger), 1)

    def test_player_balance_is_lifetime_across_game_days(self):
        self._txn(self.marco, Transaction.Type.CHIPS_OUT, 500000, Transaction.Channel.CASHIER)
        Transaction.objects.create(
            game_day=None, player=self.marco, type=Transaction.Type.PAYMENT_CASH, amount=Decimal(200000),
            channel=Transaction.Channel.CASH, recorded_by=self.cashier,
        )
        self.assertEqual(selectors.player_balance(self.marco), Decimal(-300000))

    def test_outstanding_ledger_partitions_by_player(self):
        Transaction.objects.create(
            game_day=None, player=self.moses, type=Transaction.Type.PAYMENT_TRANSFER, amount=Decimal(500000),
            channel=Transaction.Channel.TRANSFER_DVA, recorded_by=self.cashier,
        )
        Transaction.objects.create(
            game_day=None, player=self.mary, type=Transaction.Type.PAYMENT_DEAL, amount=Decimal(200000),
            channel=Transaction.Channel.DEAL, recorded_by=self.owner,
        )
        moses_rows = list(selectors.outstanding_ledger(player=self.moses))
        self.assertEqual(len(moses_rows), 1)
        self.assertEqual(moses_rows[0].running_balance, Decimal(500000))

    def test_activity_feed_partitions_running_balance_by_player_unlike_ledger(self):
        """
        Found live 2026-09-14: the Cashier's 'today's activity' feed showed
        game_day_ledger's CLUB-WIDE running_balance next to an individual
        player's name — reading as their own balance when it wasn't (two
        players' interleaved transactions bleed into each other's total).
        game_day_activity_feed fixes this by partitioning the same window
        function per player, same rows game_day_ledger would return.
        """
        T, C = Transaction.Type, Transaction.Channel
        self._txn(self.marco, T.CHIPS_OUT, 400000, C.CASHIER)
        self._txn(self.moses, T.CHIPS_OUT, 100000, C.CASHIER)
        self._txn(self.marco, T.PAYMENT_CASH, 100000, C.CASH)

        ledger_balances = [row.running_balance for row in selectors.game_day_ledger(self.game_day)]
        # Club-wide cumulative: Moses's chips-out bleeds into what looks like Marco's total.
        self.assertEqual(ledger_balances, [Decimal(-400000), Decimal(-500000), Decimal(-400000)])

        activity = list(selectors.game_day_activity_feed(self.game_day))
        by_player = {(row.player_id, row.type): row.running_balance for row in activity}
        self.assertEqual(by_player[(self.marco.id, T.CHIPS_OUT)], Decimal(-400000))
        self.assertEqual(by_player[(self.moses.id, T.CHIPS_OUT)], Decimal(-100000))  # unaffected by Marco's rows
        self.assertEqual(by_player[(self.marco.id, T.PAYMENT_CASH)], Decimal(-300000))  # Marco's own balance only


class AuthorizationTests(TestCase):
    def setUp(self):
        self.owner = StaffUser.objects.create_user(username='owner', password='x', role=StaffUser.Role.OWNER)
        self.cashier = StaffUser.objects.create_user(username='cashier', password='x', role=StaffUser.Role.CASHIER)
        self.cashier2 = StaffUser.objects.create_user(username='cashier2', password='x', role=StaffUser.Role.CASHIER)
        self.accountant = StaffUser.objects.create_user(username='acct', password='x', role=StaffUser.Role.ACCOUNTANT)
        self.fm = FloorManager(name='Floor Boss', created_by=self.owner)
        self.fm.set_pin('4321')
        self.fm.save()

    # --- game-day open/close ---

    def test_cashier_cannot_open_game_day_alone(self):
        with self.assertRaises(AuthorizationError):
            services.open_game_day(1, timezone.now(), self.cashier)

    def test_owner_can_open_game_day(self):
        gd = services.open_game_day(1, timezone.now(), self.owner)
        self.assertIsNone(gd.opened_by_floor_manager)

    def test_floor_manager_pin_can_open_game_day(self):
        gd = services.open_game_day(
            2, timezone.now(), self.cashier, floor_manager_id=self.fm.pk, floor_manager_pin='4321',
        )
        self.assertEqual(gd.opened_by_floor_manager, self.fm)

    def test_wrong_pin_rejected(self):
        with self.assertRaises(AuthorizationError):
            services.open_game_day(
                3, timezone.now(), self.cashier, floor_manager_id=self.fm.pk, floor_manager_pin='0000',
            )

    def test_cashier_can_close_game_day_alone(self):
        gd = services.open_game_day(4, timezone.now(), self.owner)
        closed = services.close_game_day(gd, self.cashier)
        self.assertEqual(closed.status, GameDay.Status.CLOSED)

    def test_accountant_cannot_close_game_day(self):
        gd = services.open_game_day(5, timezone.now(), self.owner)
        with self.assertRaises(AuthorizationError):
            services.close_game_day(gd, self.accountant)

    # --- FX rate ---

    def test_accountant_cannot_set_fx_rate(self):
        with self.assertRaises(AuthorizationError):
            services.set_conversion_rate(ConversionRate.Currency.USD, Decimal('1500'), self.accountant)

    def test_floor_manager_can_set_fx_rate(self):
        rate = services.set_conversion_rate(
            ConversionRate.Currency.USD, Decimal('1500'), self.cashier,
            floor_manager_id=self.fm.pk, floor_manager_pin='4321',
        )
        self.assertEqual(rate.set_by_floor_manager, self.fm)

    # --- void/correction rules ---

    def test_cashier_can_void_own_open_game_day_entry(self):
        gd = services.open_game_day(6, timezone.now(), self.owner)
        player = Player.objects.create(account_code='WWI 1', display_name='Test')
        txn = Transaction.objects.create(
            game_day=gd, player=player, type=Transaction.Type.CHIPS_OUT, amount=Decimal(1000),
            channel=Transaction.Channel.CASHIER, recorded_by=self.cashier,
        )
        services.void_transaction(txn, self.cashier, 'miscount')
        txn.refresh_from_db()
        self.assertTrue(txn.is_voided)

    def test_other_cashier_cannot_void_someone_elses_entry(self):
        gd = services.open_game_day(7, timezone.now(), self.owner)
        player = Player.objects.create(account_code='WWI 2', display_name='Test2')
        txn = Transaction.objects.create(
            game_day=gd, player=player, type=Transaction.Type.CHIPS_OUT, amount=Decimal(1000),
            channel=Transaction.Channel.CASHIER, recorded_by=self.cashier,
        )
        with self.assertRaises(AuthorizationError):
            services.void_transaction(txn, self.cashier2, 'not mine')

    def test_only_owner_can_void_after_close(self):
        gd = services.open_game_day(8, timezone.now(), self.owner)
        player = Player.objects.create(account_code='WWI 3', display_name='Test3')
        txn = Transaction.objects.create(
            game_day=gd, player=player, type=Transaction.Type.CHIPS_OUT, amount=Decimal(1000),
            channel=Transaction.Channel.CASHIER, recorded_by=self.cashier,
        )
        services.close_game_day(gd, self.cashier)
        with self.assertRaises(AuthorizationError):
            services.void_transaction(txn, self.cashier, 'too late')
        services.void_transaction(txn, self.owner, 'owner override')  # should not raise

    # --- closed game-day guard (server-side, independent of any frontend) ---

    def test_cannot_record_transaction_against_closed_game_day(self):
        gd = services.open_game_day(9, timezone.now(), self.owner)
        services.close_game_day(gd, self.cashier)
        player = Player.objects.create(account_code='WWI 5', display_name='Test5')
        with self.assertRaises(InvalidStateError):
            services.record_transaction(
                type=Transaction.Type.CHIPS_OUT, amount=Decimal(1000), recorded_by=self.cashier,
                game_day=gd, player=player, floor_manager_id=self.fm.pk, floor_manager_pin='4321',
            )

    def test_cannot_initiate_payout_against_closed_game_day(self):
        gd = services.open_game_day(10, timezone.now(), self.owner)
        services.close_game_day(gd, self.cashier)
        player = Player.objects.create(account_code='WWI 6', display_name='Test6')
        with self.assertRaises(InvalidStateError):
            services.initiate_payout(player, Decimal(1000), self.cashier, game_day=gd)

    # --- payout approval ---

    @patch('payments.paystack_client.initiate_transfer', return_value={'transfer_code': 'TRF_test'})
    @patch('payments.paystack_client.create_transfer_recipient', return_value={'recipient_code': 'RCP_test'})
    def test_payout_requires_owner_approval(self, mock_create_recipient, mock_initiate_transfer):
        gd = services.open_game_day(20, timezone.now(), self.owner)
        player = Player.objects.create(account_code='WWI 4', display_name='Test4')
        PlayerBankAccount.objects.create(
            player=player, bank_name='GTBank', bank_code='058', account_number='0123456789',
            account_name='Test4', is_default=True,
        )
        # Gives the player 50,000 in winnings this game-day — a payout is now
        # capped at what's actually been won tonight, not unlimited.
        Transaction.objects.create(
            game_day=gd, player=player, type=Transaction.Type.PAYMENT_TRANSFER, amount=Decimal(50000),
            channel=Transaction.Channel.TRANSFER_DVA,
        )
        payout = services.initiate_payout(player, Decimal(50000), self.cashier, game_day=gd)
        self.assertEqual(payout.status, Transaction.Status.PENDING_APPROVAL)
        with self.assertRaises(AuthorizationError):
            services.approve_payout(payout, self.cashier)
        services.approve_payout(payout, self.owner)
        payout.refresh_from_db()
        self.assertEqual(payout.status, Transaction.Status.APPROVED)
        self.assertEqual(payout.external_reference, 'TRF_test')

    def test_payout_approval_fails_without_bank_account(self):
        """No bank account on file — Paystack transfer can't proceed, lands TRANSFER_FAILED, not silently APPROVED."""
        gd = services.open_game_day(21, timezone.now(), self.owner)
        player = Player.objects.create(account_code='WWI 8', display_name='Test8')
        Transaction.objects.create(
            game_day=gd, player=player, type=Transaction.Type.PAYMENT_TRANSFER, amount=Decimal(50000),
            channel=Transaction.Channel.TRANSFER_DVA,
        )
        payout = services.initiate_payout(player, Decimal(50000), self.cashier, game_day=gd)
        services.approve_payout(payout, self.owner)
        payout.refresh_from_db()
        self.assertEqual(payout.status, Transaction.Status.TRANSFER_FAILED)

    def test_payout_capped_at_game_day_winnings(self):
        """A payout can't exceed what the player has actually won this game-day."""
        gd = services.open_game_day(22, timezone.now(), self.owner)
        player = Player.objects.create(account_code='WWI 9', display_name='Test9')
        Transaction.objects.create(
            game_day=gd, player=player, type=Transaction.Type.PAYMENT_TRANSFER, amount=Decimal(10000),
            channel=Transaction.Channel.TRANSFER_DVA,
        )
        with self.assertRaises(InvalidStateError):
            services.initiate_payout(player, Decimal(10001), self.cashier, game_day=gd)

    def test_payout_requires_an_open_game_day(self):
        player = Player.objects.create(account_code='WWI 10', display_name='Test10')
        with self.assertRaises(InvalidStateError):
            services.initiate_payout(player, Decimal(1000), self.cashier)


class GameDayAndTransactionAPITests(APITestCase):
    def setUp(self):
        self.owner = StaffUser.objects.create_user(username='owner', password='x', role=StaffUser.Role.OWNER)
        self.cashier = StaffUser.objects.create_user(username='cashier', password='x', role=StaffUser.Role.CASHIER)
        self.accountant = StaffUser.objects.create_user(
            username='accountant', password='x', role=StaffUser.Role.ACCOUNTANT,
        )
        self.fm = FloorManager(name='Floor Boss', created_by=self.owner)
        self.fm.set_pin('4321')
        self.fm.save()
        self.player = Player.objects.create(account_code='WWI 1', display_name='Test Player')

    def test_cashier_cannot_open_game_day_via_api(self):
        self.client.force_authenticate(self.cashier)
        response = self.client.post('/api/game-days/open/', {'number': 1})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_can_open_and_cashier_can_close_via_api(self):
        self.client.force_authenticate(self.owner)
        open_response = self.client.post('/api/game-days/open/', {'number': 2})
        self.assertEqual(open_response.status_code, status.HTTP_201_CREATED)
        game_day_id = open_response.data['id']

        self.client.force_authenticate(self.cashier)
        close_response = self.client.post(f'/api/game-days/{game_day_id}/close/', {})
        self.assertEqual(close_response.status_code, status.HTTP_200_OK)
        self.assertEqual(close_response.data['status'], GameDay.Status.CLOSED)

    def test_close_preview_does_not_close_and_matches_the_real_close(self):
        gd = services.open_game_day(41, timezone.now(), self.owner)
        Transaction.objects.create(
            game_day=gd, player=self.player, type=Transaction.Type.CHIPS_OUT, amount=Decimal(200000),
            channel=Transaction.Channel.CASHIER, recorded_by=self.cashier,
        )
        self.client.force_authenticate(self.cashier)

        preview = self.client.get(f'/api/game-days/{gd.id}/close-preview/')
        self.assertEqual(preview.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(str(preview.data['chips_out_total'])), Decimal(200000))
        self.assertIn('num_players_seated', preview.data)
        self.assertIn('outstanding_chips_after_close', preview.data)

        gd.refresh_from_db()
        self.assertEqual(gd.status, GameDay.Status.OPEN)  # preview must not close it
        self.assertFalse(hasattr(gd, 'summary'))

        close_response = self.client.post(f'/api/game-days/{gd.id}/close/', {})
        self.assertEqual(close_response.data['summary']['chips_out_total'], preview.data['chips_out_total'])

    def test_current_game_day_endpoint(self):
        self.client.force_authenticate(self.cashier)
        self.assertIsNone(self.client.get('/api/game-days/current/').data)

        self.client.force_authenticate(self.owner)
        opened = self.client.post('/api/game-days/open/', {'number': 40}).data

        self.client.force_authenticate(self.cashier)
        current = self.client.get('/api/game-days/current/').data
        self.assertEqual(current['id'], opened['id'])

    def test_activity_endpoint_returns_per_player_running_balance(self):
        """GET /activity/ (not /ledger/) is what the Cashier's live feed uses —
        see the 2026-09-14 fix in gaming.selectors.game_day_activity_feed."""
        game_day = services.open_game_day(50, timezone.now(), self.owner)
        other_player = Player.objects.create(account_code='WWI 2', display_name='Other Player')
        self.client.force_authenticate(self.cashier)
        self.client.post('/api/transactions/', {
            'game_day': game_day.id, 'player': self.player.id, 'type': Transaction.Type.CHIPS_OUT,
            'amount': '400000', 'floor_manager_id': self.fm.pk, 'floor_manager_pin': '4321',
        })
        self.client.post('/api/transactions/', {
            'game_day': game_day.id, 'player': other_player.id, 'type': Transaction.Type.CHIPS_OUT,
            'amount': '100000', 'floor_manager_id': self.fm.pk, 'floor_manager_pin': '4321',
        })
        self.client.post('/api/transactions/', {
            'game_day': game_day.id, 'player': self.player.id, 'type': Transaction.Type.PAYMENT_CASH,
            'amount': '100000', 'floor_manager_id': self.fm.pk, 'floor_manager_pin': '4321',
        })

        response = self.client.get(f'/api/game-days/{game_day.id}/activity/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows_by_type = {(row['player'], row['type']): row for row in response.data}
        self.assertEqual(
            Decimal(rows_by_type[(other_player.id, 'CHIPS_OUT')]['running_balance']), Decimal(-100000),
        )
        self.assertEqual(
            Decimal(rows_by_type[(self.player.id, 'PAYMENT_CASH')]['running_balance']), Decimal(-300000),
        )

    def test_recording_chips_out_requires_floor_manager_pin(self):
        game_day = services.open_game_day(3, timezone.now(), self.owner)
        self.client.force_authenticate(self.cashier)
        response = self.client.post('/api/transactions/', {
            'game_day': game_day.id, 'player': self.player.id, 'type': Transaction.Type.CHIPS_OUT,
            'amount': '500000',
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.post('/api/transactions/', {
            'game_day': game_day.id, 'player': self.player.id, 'type': Transaction.Type.CHIPS_OUT,
            'amount': '500000', 'floor_manager_id': self.fm.pk, 'floor_manager_pin': '4321',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['channel'], Transaction.Channel.CASHIER)

    def test_recording_against_closed_game_day_returns_400(self):
        game_day = services.open_game_day(4, timezone.now(), self.owner)
        services.close_game_day(game_day, self.cashier)
        self.client.force_authenticate(self.cashier)
        response = self.client.post('/api/transactions/', {
            'game_day': game_day.id, 'player': self.player.id, 'type': Transaction.Type.CHIPS_OUT,
            'amount': '500000', 'floor_manager_id': self.fm.pk, 'floor_manager_pin': '4321',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cashier_cannot_record_write_off(self):
        self.client.force_authenticate(self.cashier)
        response = self.client.post('/api/transactions/', {
            'player': self.player.id, 'type': Transaction.Type.WRITE_OFF, 'amount': '100000',
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_can_record_write_off(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post('/api/transactions/', {
            'player': self.player.id, 'type': Transaction.Type.WRITE_OFF, 'amount': '100000',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    @patch('payments.paystack_client.initiate_transfer', return_value={'transfer_code': 'TRF_test'})
    @patch('payments.paystack_client.create_transfer_recipient', return_value={'recipient_code': 'RCP_test'})
    def test_payout_flow_requires_owner_approval_via_api(self, mock_create_recipient, mock_initiate_transfer):
        PlayerBankAccount.objects.create(
            player=self.player, bank_name='GTBank', bank_code='058', account_number='0123456789',
            account_name='Test Player', is_default=True,
        )
        gd = services.open_game_day(23, timezone.now(), self.owner)
        Transaction.objects.create(
            game_day=gd, player=self.player, type=Transaction.Type.PAYMENT_TRANSFER, amount=Decimal(50000),
            channel=Transaction.Channel.TRANSFER_DVA,
        )
        self.client.force_authenticate(self.cashier)
        # game_day omitted deliberately — initiate_payout defaults to whichever is currently open.
        response = self.client.post('/api/transactions/payout/', {'player': self.player.id, 'amount': '50000'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], Transaction.Status.PENDING_APPROVAL)
        txn_id = response.data['id']

        approve_response = self.client.post(f'/api/transactions/{txn_id}/approve/')
        self.assertEqual(approve_response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.owner)
        approve_response = self.client.post(f'/api/transactions/{txn_id}/approve/')
        self.assertEqual(approve_response.status_code, status.HTTP_200_OK)
        self.assertEqual(approve_response.data['status'], Transaction.Status.APPROVED)


class DashboardAndMainAccountAPITests(APITestCase):
    def setUp(self):
        self.owner = StaffUser.objects.create_user(username='owner', password='x', role=StaffUser.Role.OWNER)
        self.cashier = StaffUser.objects.create_user(username='cashier', password='x', role=StaffUser.Role.CASHIER)
        self.accountant = StaffUser.objects.create_user(
            username='accountant', password='x', role=StaffUser.Role.ACCOUNTANT,
        )

    def test_cashier_cannot_view_dashboard(self):
        self.client.force_authenticate(self.cashier)
        response = self.client.get('/api/dashboard/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_accountant_dashboard_excludes_main_account_balance(self):
        self.client.force_authenticate(self.accountant)
        response = self.client.get('/api/dashboard/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn('main_account_balance', response.data)

    def test_owner_dashboard_includes_main_account_balance(self):
        self.client.force_authenticate(self.owner)
        response = self.client.get('/api/dashboard/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('main_account_balance', response.data)

    def test_accountant_cannot_view_main_account_ledger(self):
        self.client.force_authenticate(self.accountant)
        response = self.client.get('/api/main-account/ledger/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_can_view_main_account_ledger(self):
        self.client.force_authenticate(self.owner)
        response = self.client.get('/api/main-account/ledger/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class GameDaySeatingTests(APITestCase):
    """
    GameDayPlayer — "seated at tonight's table," independent of any
    Transaction. See gaming.services.seat_player/_ensure_seated and
    CONCEPT.md's Buy-in flow.
    """

    def setUp(self):
        self.owner = StaffUser.objects.create_user(username='owner', password='x', role=StaffUser.Role.OWNER)
        self.cashier = StaffUser.objects.create_user(username='cashier', password='x', role=StaffUser.Role.CASHIER)
        self.game_day = services.open_game_day(30, timezone.now(), self.owner)

    def test_seating_new_player_creates_and_seats(self):
        player = services.seat_player(
            self.game_day, self.owner, player_fields={'account_code': 'WWI 30', 'display_name': 'New Guy'},
        )
        self.assertEqual(Player.objects.filter(account_code='WWI 30').count(), 1)
        self.assertTrue(GameDayPlayer.objects.filter(game_day=self.game_day, player=player).exists())

    def test_seating_is_idempotent(self):
        player = Player.objects.create(account_code='WWI 31', display_name='Existing')
        services.seat_player(self.game_day, self.owner, player=player)
        services.seat_player(self.game_day, self.owner, player=player)  # should not raise / duplicate
        self.assertEqual(GameDayPlayer.objects.filter(game_day=self.game_day, player=player).count(), 1)

    def test_recording_a_transaction_auto_seats(self):
        """A player with real activity tonight shows up seated even without the explicit add-player step."""
        player = Player.objects.create(account_code='WWI 32', display_name='Auto Seated')
        self.assertFalse(GameDayPlayer.objects.filter(game_day=self.game_day, player=player).exists())
        services.record_transaction(
            type=Transaction.Type.PAYMENT_TRANSFER, amount=Decimal(1000), recorded_by=self.cashier,
            game_day=self.game_day, player=player,
        )
        self.assertTrue(GameDayPlayer.objects.filter(game_day=self.game_day, player=player).exists())

    def test_cannot_seat_a_player_against_a_closed_game_day(self):
        services.close_game_day(self.game_day, self.owner)
        player = Player.objects.create(account_code='WWI 33', display_name='Too Late')
        with self.assertRaises(InvalidStateError):
            services.seat_player(self.game_day, self.owner, player=player)

    def test_seated_players_endpoint_scopes_to_that_game_day(self):
        seated = Player.objects.create(account_code='WWI 34', display_name='Seated')
        not_seated = Player.objects.create(account_code='WWI 35', display_name='Not Seated')
        services.seat_player(self.game_day, self.owner, player=seated)

        self.client.force_authenticate(self.cashier)
        response = self.client.get(f'/api/game-days/{self.game_day.id}/players/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        codes = [row['account_code'] for row in response.data]
        self.assertIn('WWI 34', codes)
        self.assertNotIn('WWI 35', codes)

    def test_balance_on_seated_endpoint_is_game_day_scoped_not_lifetime(self):
        player = Player.objects.create(account_code='WWI 36', display_name='Scoped Balance')
        # A closed, older game-day debt that must NOT leak into today's figure.
        old_gd = services.open_game_day(31, timezone.now(), self.owner)
        Transaction.objects.create(
            game_day=old_gd, player=player, type=Transaction.Type.CHIPS_OUT, amount=Decimal(200000),
            channel=Transaction.Channel.CASHIER,
        )
        services.close_game_day(old_gd, self.owner)
        services.seat_player(self.game_day, self.owner, player=player)

        self.client.force_authenticate(self.cashier)
        response = self.client.get(f'/api/game-days/{self.game_day.id}/players/')
        row = next(r for r in response.data if r['account_code'] == 'WWI 36')
        self.assertEqual(Decimal(str(row['balance'])), Decimal('0'))  # nothing tonight, old debt hidden

    def test_cashier_can_seat_existing_player_via_api(self):
        player = Player.objects.create(account_code='WWI 37', display_name='Seat Me')
        self.client.force_authenticate(self.cashier)
        response = self.client.post(f'/api/game-days/{self.game_day.id}/players/', {'player_id': player.id})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['account_code'], 'WWI 37')

    def test_cashier_can_seat_new_player_via_api(self):
        self.client.force_authenticate(self.cashier)
        response = self.client.post(
            f'/api/game-days/{self.game_day.id}/players/',
            {'account_code': 'WWI 38', 'display_name': 'Brand New'},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Player.objects.filter(account_code='WWI 38').exists())

    def test_accountant_cannot_seat_a_player(self):
        accountant = StaffUser.objects.create_user(username='acct2', password='x', role=StaffUser.Role.ACCOUNTANT)
        self.client.force_authenticate(accountant)
        response = self.client.post(
            f'/api/game-days/{self.game_day.id}/players/', {'account_code': 'WWI 39', 'display_name': 'Blocked'},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_single_seated_player_detail_endpoint(self):
        player = Player.objects.create(account_code='WWI 40', display_name='Detail Test')
        services.seat_player(self.game_day, self.owner, player=player)
        self.client.force_authenticate(self.cashier)
        response = self.client.get(f'/api/game-days/{self.game_day.id}/players/{player.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['account_code'], 'WWI 40')
        self.assertIsNone(response.data['gaming_account'])  # not provisioned

    def test_player_detail_404_when_not_seated(self):
        player = Player.objects.create(account_code='WWI 41', display_name='Not Seated')
        self.client.force_authenticate(self.cashier)
        response = self.client.get(f'/api/game-days/{self.game_day.id}/players/{player.id}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
