from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.utils import timezone
from rest_framework import status

from lpc_backend.testing import APITestCase, TestCase

from accounts.models import AccountCode, FloorManager, Player, PlayerBankAccount, StaffMember, StaffUser

from . import selectors, services
from .exceptions import AuthorizationError, InvalidStateError, TableFullError
from .models import ClubSettings, ConversionRate, Game, GameDay, GameDayPlayer, ProfitSplitArrangement, Table, Transaction


def _disable_payout_auto_approval():
    """
    A negative threshold `amount <= threshold` can never satisfy (even a
    ₦0 payout) — used by tests written before ClubSettings.
    payout_auto_approve_threshold existed (default ₦500,000), whose own
    intent is "stays PENDING_APPROVAL until an Owner acts," not the new
    threshold feature itself (see PayoutAutoApprovalThresholdTests for that).
    """
    obj = ClubSettings.load()
    obj.payout_auto_approve_threshold = Decimal('-1')
    obj.save(update_fields=['payout_auto_approve_threshold'])


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

    def test_voided_row_stays_in_the_ledger_but_not_the_running_balance(self):
        """
        Found live 2026-09-14: a voided row was silently dropped from every
        ledger listing, contradicting HiFiVoidEntry.dc.html's own text
        ("stays visible in the ledger... for audit — it isn't deleted") and
        HiFiGameDayLedger.dc.html's own mockup (a voided row shown inline,
        struck through). Fixed via _with_running_balance's `contribution`
        annotation — voided rows list, but contribute nothing to the sum.
        """
        self._txn(self.marco, Transaction.Type.CHIPS_OUT, 500000, Transaction.Channel.CASHIER)
        second = self._txn(self.marco, Transaction.Type.PAYMENT_CASH, 100000, Transaction.Channel.CASH)
        second.is_voided = True
        second.save(update_fields=['is_voided'])
        self._txn(self.marco, Transaction.Type.PAYMENT_CASH, 200000, Transaction.Channel.CASH)

        ledger = list(selectors.game_day_ledger(self.game_day))
        self.assertEqual(len(ledger), 3)  # the voided row is still a row

        voided_row = next(row for row in ledger if row.id == second.id)
        self.assertEqual(voided_row.signed_amount, Decimal(100000))  # true amount, for display
        self.assertEqual(voided_row.running_balance, Decimal(-500000))  # unchanged by the voided row

        last_row = ledger[-1]
        self.assertEqual(last_row.running_balance, Decimal(-300000))  # -500000 + 0 (voided) + 200000

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

    def test_chips_variance_is_positive_when_chips_are_unreturned(self):
        """More chips issued than accounted for by returns/rake/tips this
        game-day — a deficit, taken off-site or simply not yet cashed back in."""
        T, C = Transaction.Type, Transaction.Channel
        self._txn(self.marco, T.CHIPS_OUT, 500000, C.CASHIER)
        self._txn(self.marco, T.CHIPS_IN, 200000, C.CHIPS)
        Transaction.objects.create(
            game_day=self.game_day, player=None, type=T.RAKE, amount=Decimal(50000),
            channel=C.CASHIER, recorded_by=self.cashier,
        )
        data = selectors.game_day_summary_data(self.game_day)
        # 500,000 out - 200,000 in - 50,000 rake - 0 tips = 250,000 unreturned.
        self.assertEqual(data['chips_variance'], Decimal(250000))

    def test_chips_variance_is_negative_when_excess_chips_are_returned(self):
        """More chips returned than were issued this game-day — chips that
        went off-site on an earlier day coming back into play tonight."""
        T, C = Transaction.Type, Transaction.Channel
        self._txn(self.marco, T.CHIPS_OUT, 200000, C.CASHIER)
        self._txn(self.marco, T.CHIPS_IN, 500000, C.CHIPS)
        data = selectors.game_day_summary_data(self.game_day)
        # 200,000 out - 500,000 in = -300,000 — excess, not a deficit.
        self.assertEqual(data['chips_variance'], Decimal(-300000))


class AuthorizationTests(TestCase):
    def setUp(self):
        self.owner = StaffUser.objects.create_user(username='owner', password='x', role=StaffUser.Role.OWNER)
        self.cashier = StaffUser.objects.create_user(username='cashier', password='x', role=StaffUser.Role.CASHIER)
        self.cashier2 = StaffUser.objects.create_user(username='cashier2', password='x', role=StaffUser.Role.CASHIER)
        self.accountant = StaffUser.objects.create_user(username='acct', password='x', role=StaffUser.Role.ACCOUNTANT)
        self.fm = FloorManager(name='Floor Boss', created_by=self.owner)
        self.fm.set_pin('4321')
        self.fm.save()

    def _seat_and_leave(self, gd, player):
        """A payout now requires the player to have left the table (2026-09-17) —
        shared setup for every payout test below that isn't specifically testing
        that gate itself."""
        services.seat_player(gd, self.owner, player=player)
        services.leave_table(gd, player, operator=self.cashier)

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

    def test_cashier_alone_cannot_close_game_day(self):
        """Revised 2026-09-22: closing now always requires a Floor Manager
        PIN — the night's final physical reconciliation, witnessed
        independently, same as any other physical-count entry. No more
        Cashier/Owner-alone bypass."""
        gd = services.open_game_day(4, timezone.now(), self.owner)
        with self.assertRaises(AuthorizationError):
            services.close_game_day(gd, self.cashier)

    def test_owner_alone_cannot_close_game_day_either(self):
        """No Owner-login bypass, unlike open_game_day/set_conversion_rate —
        deliberately: an Owner closing solo defeats the point of an
        independent signature."""
        gd = services.open_game_day(41, timezone.now(), self.owner)
        with self.assertRaises(AuthorizationError):
            services.close_game_day(gd, self.owner)

    def test_floor_manager_pin_can_close_game_day(self):
        gd = services.open_game_day(42, timezone.now(), self.owner)
        closed = services.close_game_day(
            gd, self.cashier, floor_manager_id=self.fm.pk, floor_manager_pin='4321',
        )
        self.assertEqual(closed.status, GameDay.Status.CLOSED)
        self.assertEqual(closed.closed_by_floor_manager, self.fm)

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
        # A matching (raw, same as the CHIPS_OUT above) CHIPS_IN — this test
        # is about void authorization after close, not chip reconciliation,
        # so it needs the close-time gate satisfied, not exercised.
        Transaction.objects.create(
            game_day=gd, player=player, type=Transaction.Type.CHIPS_IN, amount=Decimal(1000),
            channel=Transaction.Channel.CASHIER, recorded_by=self.cashier,
        )
        services.close_game_day(gd, self.cashier, floor_manager_id=self.fm.pk, floor_manager_pin='4321')
        with self.assertRaises(AuthorizationError):
            services.void_transaction(txn, self.cashier, 'too late')
        services.void_transaction(txn, self.owner, 'owner override')  # should not raise

    # --- closed game-day guard (server-side, independent of any frontend) ---

    def test_cannot_record_transaction_against_closed_game_day(self):
        gd = services.open_game_day(9, timezone.now(), self.owner)
        services.close_game_day(gd, self.cashier, floor_manager_id=self.fm.pk, floor_manager_pin='4321')
        player = Player.objects.create(account_code='WWI 5', display_name='Test5')
        with self.assertRaises(InvalidStateError):
            services.record_transaction(
                type=Transaction.Type.CHIPS_OUT, amount=Decimal(1000), recorded_by=self.cashier,
                game_day=gd, player=player, floor_manager_id=self.fm.pk, floor_manager_pin='4321',
            )

    def test_cannot_initiate_payout_against_closed_game_day(self):
        gd = services.open_game_day(10, timezone.now(), self.owner)
        services.close_game_day(gd, self.cashier, floor_manager_id=self.fm.pk, floor_manager_pin='4321')
        player = Player.objects.create(account_code='WWI 6', display_name='Test6')
        with self.assertRaises(InvalidStateError):
            services.initiate_payout(player, Decimal(1000), self.cashier, game_day=gd)

    # --- payout approval ---

    @patch('payments.paystack_client.initiate_transfer', return_value={'transfer_code': 'TRF_test'})
    @patch('payments.paystack_client.create_transfer_recipient', return_value={'recipient_code': 'RCP_test'})
    def test_payout_requires_owner_approval(self, mock_create_recipient, mock_initiate_transfer):
        # Below the default auto-approval threshold — force it off (see
        # PayoutAutoApprovalThresholdTests for that feature's own tests) so
        # this keeps testing manual approval, undisturbed by it.
        _disable_payout_auto_approval()
        gd = services.open_game_day(20, timezone.now(), self.owner)
        player = Player.objects.create(account_code='WWI 4', display_name='Test4')
        PlayerBankAccount.objects.create(
            player=player, bank_name='GTBank', bank_code='058', account_number='0123456789',
            account_name='Test4', is_default=True,
        )
        self._seat_and_leave(gd, player)
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

    def test_payout_approval_blocked_by_insufficient_main_account_balance(self):
        """The club's own bank balance can't go negative on a payout — checked
        at approval time (Owner-only visibility), leaves the transaction fully
        untouched (still PENDING_APPROVAL, not TRANSFER_FAILED) so it can be
        retried once funds arrive."""
        _disable_payout_auto_approval()
        gd = services.open_game_day(30, timezone.now(), self.owner)
        player = Player.objects.create(account_code='WWI 16', display_name='Test16')
        PlayerBankAccount.objects.create(
            player=player, bank_name='GTBank', bank_code='058', account_number='0123456789',
            account_name='Test16', is_default=True,
        )
        self._seat_and_leave(gd, player)
        # The player has won 50,000 (satisfies the player-side cap), but
        # nothing has ever actually deposited into the Main Account — it's
        # still at 0, so a 50,000 payout can't be sent regardless of what
        # the player personally won tonight.
        Transaction.objects.create(
            game_day=gd, player=player, type=Transaction.Type.PAYMENT_DEAL, amount=Decimal(50000),
        )
        payout = services.initiate_payout(player, Decimal(50000), self.cashier, game_day=gd)
        with self.assertRaises(InvalidStateError):
            services.approve_payout(payout, self.owner)
        payout.refresh_from_db()
        self.assertEqual(payout.status, Transaction.Status.PENDING_APPROVAL)
        self.assertIsNone(payout.approved_by)

        # Once real funds land in the Main Account, the same payout approves normally.
        Transaction.objects.create(
            game_day=gd, player=player, type=Transaction.Type.PAYMENT_TRANSFER, amount=Decimal(50000),
            channel=Transaction.Channel.TRANSFER_DVA,
        )
        with patch('payments.paystack_client.create_transfer_recipient', return_value={'recipient_code': 'RCP_x'}), \
             patch('payments.paystack_client.initiate_transfer', return_value={'transfer_code': 'TRF_x'}):
            services.approve_payout(payout, self.owner)
        payout.refresh_from_db()
        self.assertEqual(payout.status, Transaction.Status.APPROVED)

    def test_payout_blocked_while_still_seated(self):
        """Revised 2026-09-17: a player can't cash out while still seated —
        leaving and paying out are independent, but a payout now requires it."""
        gd = services.open_game_day(21, timezone.now(), self.owner)
        player = Player.objects.create(account_code='WWI 8', display_name='Test8')
        PlayerBankAccount.objects.create(
            player=player, bank_name='GTBank', bank_code='058', account_number='0123456789',
            account_name='Test8', is_default=True,
        )
        services.seat_player(gd, self.owner, player=player)  # seated, but never left
        Transaction.objects.create(
            game_day=gd, player=player, type=Transaction.Type.PAYMENT_TRANSFER, amount=Decimal(50000),
            channel=Transaction.Channel.TRANSFER_DVA,
        )
        with self.assertRaises(InvalidStateError):
            services.initiate_payout(player, Decimal(50000), self.cashier, game_day=gd)

    def test_payout_request_blocked_without_bank_account(self):
        """Revised 2026-09-17: the bank-account gate is now enforced at
        REQUEST time, not just discovered later at approval as TRANSFER_FAILED."""
        gd = services.open_game_day(28, timezone.now(), self.owner)
        player = Player.objects.create(account_code='WWI 14', display_name='Test14')
        self._seat_and_leave(gd, player)  # left the table, but still no bank account on file
        Transaction.objects.create(
            game_day=gd, player=player, type=Transaction.Type.PAYMENT_TRANSFER, amount=Decimal(50000),
            channel=Transaction.Channel.TRANSFER_DVA,
        )
        with self.assertRaises(InvalidStateError):
            services.initiate_payout(player, Decimal(50000), self.cashier, game_day=gd)

    def test_payout_approval_fails_if_bank_account_removed_after_request(self):
        """The approval-time check stays too, as defense in depth — e.g. the
        bank account is removed between request and approval."""
        gd = services.open_game_day(29, timezone.now(), self.owner)
        player = Player.objects.create(account_code='WWI 15', display_name='Test15')
        bank = PlayerBankAccount.objects.create(
            player=player, bank_name='GTBank', bank_code='058', account_number='0123456789',
            account_name='Test15', is_default=True,
        )
        self._seat_and_leave(gd, player)
        Transaction.objects.create(
            game_day=gd, player=player, type=Transaction.Type.PAYMENT_TRANSFER, amount=Decimal(50000),
            channel=Transaction.Channel.TRANSFER_DVA,
        )
        payout = services.initiate_payout(player, Decimal(50000), self.cashier, game_day=gd)
        bank.delete()
        services.approve_payout(payout, self.owner)
        payout.refresh_from_db()
        self.assertEqual(payout.status, Transaction.Status.TRANSFER_FAILED)

    def test_payout_capped_at_game_day_winnings(self):
        """A payout can't exceed what the player has actually won this game-day."""
        gd = services.open_game_day(22, timezone.now(), self.owner)
        player = Player.objects.create(account_code='WWI 9', display_name='Test9')
        PlayerBankAccount.objects.create(
            player=player, bank_name='GTBank', bank_code='058', account_number='0123456789',
            account_name='Test9', is_default=True,
        )
        self._seat_and_leave(gd, player)
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

    # --- payout rejection ---

    def test_owner_can_reject_a_pending_payout(self):
        gd = services.open_game_day(24, timezone.now(), self.owner)
        player = Player.objects.create(account_code='WWI 11', display_name='Test11')
        PlayerBankAccount.objects.create(
            player=player, bank_name='GTBank', bank_code='058', account_number='0123456789',
            account_name='Test11', is_default=True,
        )
        self._seat_and_leave(gd, player)
        Transaction.objects.create(
            game_day=gd, player=player, type=Transaction.Type.PAYMENT_TRANSFER, amount=Decimal(50000),
            channel=Transaction.Channel.TRANSFER_DVA,
        )
        payout = services.initiate_payout(player, Decimal(50000), self.cashier, game_day=gd)
        # A pending payout already counts against the player's balance.
        self.assertEqual(selectors.player_game_day_balance(player, gd), Decimal(0))
        rejected = services.reject_payout(payout, self.owner, 'Player never actually requested this.')
        self.assertEqual(rejected.status, Transaction.Status.REJECTED)
        self.assertTrue(rejected.is_voided)
        self.assertEqual(rejected.void_reason, 'Player never actually requested this.')
        # Rejecting must drop it back out of the player's balance — it never happened.
        self.assertEqual(selectors.player_game_day_balance(player, gd), Decimal(50000))

    def test_cashier_cannot_reject_a_payout(self):
        gd = services.open_game_day(25, timezone.now(), self.owner)
        player = Player.objects.create(account_code='WWI 12', display_name='Test12')
        PlayerBankAccount.objects.create(
            player=player, bank_name='GTBank', bank_code='058', account_number='0123456789',
            account_name='Test12', is_default=True,
        )
        self._seat_and_leave(gd, player)
        payout = services.initiate_payout(player, Decimal(0), self.cashier, game_day=gd)
        with self.assertRaises(AuthorizationError):
            services.reject_payout(payout, self.cashier, 'No.')

    def test_cannot_reject_an_already_approved_payout(self):
        gd = services.open_game_day(26, timezone.now(), self.owner)
        player = Player.objects.create(account_code='WWI 13', display_name='Test13')
        PlayerBankAccount.objects.create(
            player=player, bank_name='GTBank', bank_code='058', account_number='0123456789',
            account_name='Test13', is_default=True,
        )
        self._seat_and_leave(gd, player)
        payout = services.initiate_payout(player, Decimal(0), self.cashier, game_day=gd)
        payout.status = Transaction.Status.APPROVED
        payout.save(update_fields=['status'])
        with self.assertRaises(InvalidStateError):
            services.reject_payout(payout, self.owner, 'Too late.')


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

    def test_owner_can_open_but_cashier_alone_cannot_close_via_api(self):
        """Revised 2026-09-22: closing always requires a Floor Manager PIN
        now — see services.close_game_day."""
        self.client.force_authenticate(self.owner)
        open_response = self.client.post('/api/game-days/open/', {'number': 2})
        self.assertEqual(open_response.status_code, status.HTTP_201_CREATED)
        game_day_id = open_response.data['id']

        self.client.force_authenticate(self.cashier)
        close_response = self.client.post(f'/api/game-days/{game_day_id}/close/', {})
        self.assertEqual(close_response.status_code, status.HTTP_403_FORBIDDEN)

        close_response = self.client.post(f'/api/game-days/{game_day_id}/close/', {
            'floor_manager_id': self.fm.pk, 'floor_manager_pin': '4321',
        })
        self.assertEqual(close_response.status_code, status.HTTP_200_OK)
        self.assertEqual(close_response.data['status'], GameDay.Status.CLOSED)

    def test_close_preview_does_not_close_and_matches_the_real_close(self):
        gd = services.open_game_day(41, timezone.now(), self.owner)
        Transaction.objects.create(
            game_day=gd, player=self.player, type=Transaction.Type.CHIPS_OUT, amount=Decimal(200000),
            channel=Transaction.Channel.CASHIER, recorded_by=self.cashier,
        )
        # Matching CHIPS_IN — this test is about the preview/close data
        # matching each other, not chip reconciliation; needs the close-time
        # gate satisfied rather than exercised. See close_blocked_reason.
        Transaction.objects.create(
            game_day=gd, player=self.player, type=Transaction.Type.CHIPS_IN, amount=Decimal(200000),
            channel=Transaction.Channel.CASHIER, recorded_by=self.cashier,
        )
        self.client.force_authenticate(self.cashier)

        preview = self.client.get(f'/api/game-days/{gd.id}/close-preview/')
        self.assertEqual(preview.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(str(preview.data['chips_out_total'])), Decimal(200000))
        self.assertIn('num_players_seated', preview.data)
        self.assertIn('outstanding_chips_after_close', preview.data)
        self.assertEqual(preview.data['active_players_count'], 0)
        self.assertIsNone(preview.data['close_blocked_reason'])

        gd.refresh_from_db()
        self.assertEqual(gd.status, GameDay.Status.OPEN)  # preview must not close it
        self.assertFalse(hasattr(gd, 'summary'))

        close_response = self.client.post(f'/api/game-days/{gd.id}/close/', {
            'floor_manager_id': self.fm.pk, 'floor_manager_pin': '4321',
        })
        self.assertEqual(close_response.data['summary']['chips_out_total'], preview.data['chips_out_total'])

    def test_cannot_close_while_a_player_is_still_active(self):
        gd = services.open_game_day(43, timezone.now(), self.owner)
        services.seat_player(gd, self.owner, player=self.player)
        self.assertIn('still at the table', services.close_blocked_reason(gd))
        with self.assertRaises(InvalidStateError):
            services.close_game_day(gd, self.cashier, floor_manager_id=self.fm.pk, floor_manager_pin='4321')

    def test_chips_shortfall_does_not_hard_block_but_requires_a_reason(self):
        """Revised 2026-09-22: a chip discrepancy doesn't block closing
        outright any more (a player may genuinely have walked off with
        chips) — it must be ACKNOWLEDGED instead. close_blocked_reason
        (the hard block) stays None; game_day_chip_discrepancy reports the
        gap; closing without a reason still raises."""
        gd = services.open_game_day(44, timezone.now(), self.owner)
        services.seat_player(gd, self.owner, player=self.player)
        services.record_transaction(
            type=Transaction.Type.CHIPS_OUT, amount=Decimal(500000), recorded_by=self.cashier,
            game_day=gd, player=self.player, floor_manager_id=self.fm.pk, floor_manager_pin='4321',
        )
        services.leave_table(gd, self.player, operator=self.cashier)  # left owing chips
        self.assertIsNone(services.close_blocked_reason(gd))  # not a hard block
        discrepancy = services.game_day_chip_discrepancy(gd)
        self.assertEqual(discrepancy['direction'], 'short')
        self.assertEqual(discrepancy['amount'], Decimal(500000))
        with self.assertRaises(InvalidStateError):
            services.close_game_day(
                gd, self.cashier, floor_manager_id=self.fm.pk, floor_manager_pin='4321',
            )  # no discrepancy_reason

    def test_chips_shortfall_closes_with_a_reason_and_fm_signoff(self):
        gd = services.open_game_day(47, timezone.now(), self.owner)
        services.seat_player(gd, self.owner, player=self.player)
        services.record_transaction(
            type=Transaction.Type.CHIPS_OUT, amount=Decimal(500000), recorded_by=self.cashier,
            game_day=gd, player=self.player, floor_manager_id=self.fm.pk, floor_manager_pin='4321',
        )
        services.leave_table(gd, self.player, operator=self.cashier)
        closed = services.close_game_day(
            gd, self.cashier, floor_manager_id=self.fm.pk, floor_manager_pin='4321',
            discrepancy_reason='Player left with chips, refused to return them.',
        )
        self.assertEqual(closed.status, GameDay.Status.CLOSED)
        self.assertEqual(
            closed.summary.chip_discrepancy_reason, 'Player left with chips, refused to return them.',
        )

    def test_chips_shortfall_closes_with_a_reason_and_owner_signoff_no_fm(self):
        """The sign-off is Owner-OR-Floor-Manager for a discrepancy
        specifically — wider than the Floor-Manager-only baseline."""
        gd = services.open_game_day(48, timezone.now(), self.owner)
        services.seat_player(gd, self.owner, player=self.player)
        services.record_transaction(
            type=Transaction.Type.CHIPS_OUT, amount=Decimal(500000), recorded_by=self.cashier,
            game_day=gd, player=self.player, floor_manager_id=self.fm.pk, floor_manager_pin='4321',
        )
        services.leave_table(gd, self.player, operator=self.cashier)
        closed = services.close_game_day(
            gd, self.owner, discrepancy_reason='Owner personally witnessed the count.',
        )
        self.assertEqual(closed.status, GameDay.Status.CLOSED)

    def test_chips_excess_also_requires_acknowledgement(self):
        """The other direction — more came back than makes sense once
        rake/tips are accounted for (see game_day_chip_discrepancy) — same
        acknowledge-and-sign-off path, not a separate mechanism."""
        gd = services.open_game_day(49, timezone.now(), self.owner)
        winner = Player.objects.create(account_code='WWI 64', display_name='Excess Winner')
        services.seat_player(gd, self.owner, player=winner)
        services.record_transaction(
            type=Transaction.Type.CHIPS_OUT, amount=Decimal(100000), recorded_by=self.cashier,
            game_day=gd, player=winner, floor_manager_id=self.fm.pk, floor_manager_pin='4321',
        )
        # A void of the CHIPS_OUT after a matching CHIPS_IN already posted —
        # one realistic way an excess shows up in practice (the earlier
        # per-transaction CHIPS_IN check in record_transaction blocks
        # over-returning at RECORD time, but can't see a later void).
        services.record_transaction(
            type=Transaction.Type.CHIPS_IN, amount=Decimal(100000), recorded_by=self.cashier,
            game_day=gd, player=winner, floor_manager_id=self.fm.pk, floor_manager_pin='4321',
        )
        chips_out_txn = Transaction.objects.get(game_day=gd, player=winner, type=Transaction.Type.CHIPS_OUT)
        services.void_transaction(chips_out_txn, self.owner, 'test-induced excess')
        services.leave_table(gd, winner, operator=self.cashier)

        discrepancy = services.game_day_chip_discrepancy(gd)
        self.assertEqual(discrepancy['direction'], 'excess')
        with self.assertRaises(InvalidStateError):
            services.close_game_day(gd, self.cashier, floor_manager_id=self.fm.pk, floor_manager_pin='4321')
        closed = services.close_game_day(
            gd, self.cashier, floor_manager_id=self.fm.pk, floor_manager_pin='4321',
            discrepancy_reason='Voided a chips-out after the return already posted.',
        )
        self.assertEqual(closed.status, GameDay.Status.CLOSED)

    def test_rake_and_tips_are_not_a_discrepancy(self):
        """Rake/tips are chips that legitimately never come back as a
        CHIPS_IN — game_day_chip_discrepancy must not flag a perfectly
        normal night just because rake was taken."""
        gd = services.open_game_day(51, timezone.now(), self.owner)
        services.seat_player(gd, self.owner, player=self.player)
        services.record_transaction(
            type=Transaction.Type.CHIPS_OUT, amount=Decimal(500000), recorded_by=self.cashier,
            game_day=gd, player=self.player, floor_manager_id=self.fm.pk, floor_manager_pin='4321',
        )
        services.record_transaction(
            type=Transaction.Type.CHIPS_IN, amount=Decimal(480000), recorded_by=self.cashier,
            game_day=gd, player=self.player, floor_manager_id=self.fm.pk, floor_manager_pin='4321',
        )
        services.record_transaction(
            type=Transaction.Type.RAKE, amount=Decimal(20000), recorded_by=self.cashier,
            game_day=gd, floor_manager_id=self.fm.pk, floor_manager_pin='4321',
        )
        services.leave_table(gd, self.player, operator=self.cashier)
        self.assertIsNone(services.game_day_chip_discrepancy(gd))  # 500,000 - 480,000 - 20,000 rake = 0
        closed = services.close_game_day(gd, self.cashier, floor_manager_id=self.fm.pk, floor_manager_pin='4321')
        self.assertEqual(closed.status, GameDay.Status.CLOSED)

    def test_can_close_once_everyone_has_left_and_chips_reconcile(self):
        gd = services.open_game_day(45, timezone.now(), self.owner)
        services.seat_player(gd, self.owner, player=self.player)
        services.record_transaction(
            type=Transaction.Type.CHIPS_OUT, amount=Decimal(500000), recorded_by=self.cashier,
            game_day=gd, player=self.player, floor_manager_id=self.fm.pk, floor_manager_pin='4321',
        )
        services.record_transaction(
            type=Transaction.Type.CHIPS_IN, amount=Decimal(500000), recorded_by=self.cashier,
            game_day=gd, player=self.player, floor_manager_id=self.fm.pk, floor_manager_pin='4321',
        )
        services.leave_table(gd, self.player, operator=self.cashier)
        self.assertIsNone(services.close_blocked_reason(gd))
        closed = services.close_game_day(gd, self.cashier, floor_manager_id=self.fm.pk, floor_manager_pin='4321')
        self.assertEqual(closed.status, GameDay.Status.CLOSED)

    def test_a_player_owing_money_but_having_returned_chips_does_not_block_close(self):
        """The gate is about the PHYSICAL chip count game-day-wide, not
        money owed by any one player — someone who lost chips at the table
        to another player returns everything they still HAVE (which is
        less than they took out) and still owes the club cash, carried to
        the Outstanding ledger; the club's total chip count still
        reconciles because the winner returns correspondingly more."""
        gd = services.open_game_day(46, timezone.now(), self.owner)
        winner = Player.objects.create(account_code='WWI 62', display_name='Winner')
        services.seat_player(gd, self.owner, player=self.player)
        services.seat_player(gd, self.owner, player=winner)
        services.record_transaction(
            type=Transaction.Type.CHIPS_OUT, amount=Decimal(500000), recorded_by=self.cashier,
            game_day=gd, player=self.player, floor_manager_id=self.fm.pk, floor_manager_pin='4321',
        )
        services.record_transaction(
            type=Transaction.Type.CHIPS_OUT, amount=Decimal(100000), recorded_by=self.cashier,
            game_day=gd, player=winner, floor_manager_id=self.fm.pk, floor_manager_pin='4321',
        )
        # self.player only has 300,000 left to hand back (lost 200,000 at
        # the table) — that's their FULL physical return, not a partial one.
        services.record_transaction(
            type=Transaction.Type.CHIPS_IN, amount=Decimal(300000), recorded_by=self.cashier,
            game_day=gd, player=self.player, floor_manager_id=self.fm.pk, floor_manager_pin='4321',
        )
        # winner cashes out with their winnings — the club's total still
        # reconciles (600,000 out, 600,000 in) even though self.player
        # personally still owes 200,000.
        services.record_transaction(
            type=Transaction.Type.CHIPS_IN, amount=Decimal(300000), recorded_by=self.cashier,
            game_day=gd, player=winner, floor_manager_id=self.fm.pk, floor_manager_pin='4321',
        )
        services.leave_table(gd, self.player, operator=self.cashier)
        services.leave_table(gd, winner, operator=self.cashier)
        self.assertEqual(selectors.player_game_day_balance(self.player, gd), Decimal(-200000))
        self.assertIsNone(services.close_blocked_reason(gd))

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
        services.close_game_day(game_day, self.cashier, floor_manager_id=self.fm.pk, floor_manager_pin='4321')
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
        Transaction.objects.create(
            player=self.player, type=Transaction.Type.CHIPS_OUT, amount=Decimal(150000),
            channel=Transaction.Channel.CASHIER, recorded_by=self.cashier,
        )
        self.client.force_authenticate(self.owner)
        response = self.client.post('/api/transactions/', {
            'player': self.player.id, 'type': Transaction.Type.WRITE_OFF, 'amount': '100000',
            'notes': 'Settled amicably',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_write_off_without_a_reason_is_rejected(self):
        Transaction.objects.create(
            player=self.player, type=Transaction.Type.CHIPS_OUT, amount=Decimal(150000),
            channel=Transaction.Channel.CASHIER, recorded_by=self.cashier,
        )
        self.client.force_authenticate(self.owner)
        response = self.client.post('/api/transactions/', {
            'player': self.player.id, 'type': Transaction.Type.WRITE_OFF, 'amount': '100000',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_write_off_cannot_exceed_outstanding_balance(self):
        Transaction.objects.create(
            player=self.player, type=Transaction.Type.CHIPS_OUT, amount=Decimal(50000),
            channel=Transaction.Channel.CASHIER, recorded_by=self.cashier,
        )
        self.client.force_authenticate(self.owner)
        response = self.client.post('/api/transactions/', {
            'player': self.player.id, 'type': Transaction.Type.WRITE_OFF, 'amount': '100000',
            'notes': 'Trying to over-forgive',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_write_off_cannot_push_a_debt_free_player_positive(self):
        # self.player has no transactions at all yet — balance is 0, not negative.
        self.client.force_authenticate(self.owner)
        response = self.client.post('/api/transactions/', {
            'player': self.player.id, 'type': Transaction.Type.WRITE_OFF, 'amount': '1',
            'notes': 'No debt to forgive',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_write_off_can_clear_the_full_outstanding_balance_exactly(self):
        Transaction.objects.create(
            player=self.player, type=Transaction.Type.CHIPS_OUT, amount=Decimal(75000),
            channel=Transaction.Channel.CASHIER, recorded_by=self.cashier,
        )
        self.client.force_authenticate(self.owner)
        response = self.client.post('/api/transactions/', {
            'player': self.player.id, 'type': Transaction.Type.WRITE_OFF, 'amount': '75000',
            'notes': 'Clearing it all',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(selectors.player_balance(self.player), Decimal('0'))

    @patch('payments.paystack_client.initiate_transfer', return_value={'transfer_code': 'TRF_test'})
    @patch('payments.paystack_client.create_transfer_recipient', return_value={'recipient_code': 'RCP_test'})
    def test_payout_flow_requires_owner_approval_via_api(self, mock_create_recipient, mock_initiate_transfer):
        _disable_payout_auto_approval()
        PlayerBankAccount.objects.create(
            player=self.player, bank_name='GTBank', bank_code='058', account_number='0123456789',
            account_name='Test Player', is_default=True,
        )
        gd = services.open_game_day(23, timezone.now(), self.owner)
        services.seat_player(gd, self.owner, player=self.player)
        services.leave_table(gd, self.player, operator=self.cashier)  # a payout now requires this
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

    def test_payout_reject_flow_via_api(self):
        gd = services.open_game_day(27, timezone.now(), self.owner)
        PlayerBankAccount.objects.create(
            player=self.player, bank_name='GTBank', bank_code='058', account_number='0123456789',
            account_name='Test Player', is_default=True,
        )
        services.seat_player(gd, self.owner, player=self.player)
        services.leave_table(gd, self.player, operator=self.cashier)  # a payout now requires this
        Transaction.objects.create(
            game_day=gd, player=self.player, type=Transaction.Type.PAYMENT_TRANSFER, amount=Decimal(50000),
            channel=Transaction.Channel.TRANSFER_DVA,
        )
        self.client.force_authenticate(self.cashier)
        response = self.client.post('/api/transactions/payout/', {'player': self.player.id, 'amount': '50000'})
        txn_id = response.data['id']

        reject_response = self.client.post(f'/api/transactions/{txn_id}/reject/', {'reason': 'Mistaken request.'})
        self.assertEqual(reject_response.status_code, status.HTTP_403_FORBIDDEN)  # Cashier can't reject

        self.client.force_authenticate(self.owner)
        reject_response = self.client.post(f'/api/transactions/{txn_id}/reject/', {})
        self.assertEqual(reject_response.status_code, status.HTTP_400_BAD_REQUEST)  # reason required

        reject_response = self.client.post(f'/api/transactions/{txn_id}/reject/', {'reason': 'Mistaken request.'})
        self.assertEqual(reject_response.status_code, status.HTTP_200_OK)
        self.assertEqual(reject_response.data['status'], Transaction.Status.REJECTED)
        self.assertTrue(reject_response.data['is_voided'])


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

    # total_rake_this_month replaced outstanding_chips on the Owner
    # Dashboard's stat grid (2026-09-23) — Accountant's own dashboard is
    # unaffected, still outstanding_chips only. See selectors.total_rake_this_month.
    def test_owner_dashboard_includes_total_rake_this_month_not_outstanding_chips(self):
        self.client.force_authenticate(self.owner)
        response = self.client.get('/api/dashboard/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('total_rake_this_month', response.data)
        self.assertNotIn('outstanding_chips', response.data)

    def test_accountant_dashboard_includes_outstanding_chips_not_total_rake(self):
        self.client.force_authenticate(self.accountant)
        response = self.client.get('/api/dashboard/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('outstanding_chips', response.data)
        self.assertNotIn('total_rake_this_month', response.data)

    # creditor_count (2026-09-23) — the "Owed to players" stat card's own
    # player count was hardcoded "7 players" in DashboardView.vue until now;
    # this checks the real number actually comes back and is correct.
    def test_dashboard_creditor_count_is_computed_not_hardcoded(self):
        debtor = Player.objects.create(account_code='WWI 90', display_name='Owes Money')
        creditor_a = Player.objects.create(account_code='WWI 91', display_name='Is Owed A')
        creditor_b = Player.objects.create(account_code='WWI 92', display_name='Is Owed B')
        Transaction.objects.create(
            player=debtor, type=Transaction.Type.CHIPS_OUT, amount=Decimal(50000),
            channel=Transaction.Channel.CHIPS, recorded_by=self.owner,
        )
        Transaction.objects.create(
            player=creditor_a, type=Transaction.Type.WRITE_OFF, amount=Decimal(20000),
            channel=Transaction.Channel.WRITE_OFF, recorded_by=self.owner,
        )
        Transaction.objects.create(
            player=creditor_b, type=Transaction.Type.WRITE_OFF, amount=Decimal(15000),
            channel=Transaction.Channel.WRITE_OFF, recorded_by=self.owner,
        )

        self.client.force_authenticate(self.owner)
        response = self.client.get('/api/dashboard/')
        self.assertEqual(response.data['debtor_count'], 1)
        self.assertEqual(response.data['creditor_count'], 2)

    def test_total_rake_this_month_only_counts_this_calendar_month(self):
        game_day = GameDay.objects.create(number=88, started_at=timezone.now(), opened_by=self.owner)
        now = timezone.localtime(timezone.now())
        this_month = now.replace(day=1, hour=12, minute=0, second=0, microsecond=0)
        last_month = (this_month - timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)

        in_month_txn = Transaction.objects.create(
            game_day=game_day, type=Transaction.Type.RAKE, amount=Decimal(5000),
            channel=Transaction.Channel.CHIPS, recorded_by=self.owner,
        )
        Transaction.objects.filter(pk=in_month_txn.pk).update(created_at=this_month)

        out_of_month_txn = Transaction.objects.create(
            game_day=game_day, type=Transaction.Type.RAKE, amount=Decimal(9000),
            channel=Transaction.Channel.CHIPS, recorded_by=self.owner,
        )
        Transaction.objects.filter(pk=out_of_month_txn.pk).update(created_at=last_month)

        self.client.force_authenticate(self.owner)
        response = self.client.get('/api/dashboard/')
        self.assertEqual(Decimal(response.data['total_rake_this_month']), Decimal(5000))

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
        self.fm = FloorManager(name='Floor Boss', created_by=self.owner)
        self.fm.set_pin('4321')
        self.fm.save()
        self.game_day = services.open_game_day(30, timezone.now(), self.owner)

    def _seat_and_leave(self, gd, player):
        """A payout requires the player to have left the table — same
        fixture as AuthorizationTests' own helper of the same name."""
        services.seat_player(gd, self.owner, player=player)
        services.leave_table(gd, player, operator=self.cashier)

    def test_seating_new_player_creates_and_seats(self):
        AccountCode.objects.create(code='WWI 30', account_number='9000000030', account_name='WWI 30 DVA')
        player = services.seat_player(
            self.game_day, self.owner, player_fields={'display_name': 'New Guy'},
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
        services.close_game_day(self.game_day, self.owner, floor_manager_id=self.fm.pk, floor_manager_pin='4321')
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
        winner = Player.objects.create(account_code='WWI 63', display_name='Old GD Winner')
        # A closed, older game-day debt that must NOT leak into today's figure.
        old_gd = services.open_game_day(31, timezone.now(), self.owner)
        Transaction.objects.create(
            game_day=old_gd, player=player, type=Transaction.Type.CHIPS_OUT, amount=Decimal(200000),
            channel=Transaction.Channel.CASHIER,
        )
        # `player` never returns anything (lost it all at the table) and
        # still owes 200,000 — the debt this test is actually about. `winner`
        # returning the matching amount is just what satisfies the
        # close-time chip-reconciliation gate (game-day-wide, not
        # per-player — see close_blocked_reason), not a plot point here.
        Transaction.objects.create(
            game_day=old_gd, player=winner, type=Transaction.Type.CHIPS_IN, amount=Decimal(200000),
            channel=Transaction.Channel.CASHIER,
        )
        services.close_game_day(old_gd, self.owner, floor_manager_id=self.fm.pk, floor_manager_pin='4321')
        self.assertEqual(selectors.player_game_day_balance(player, old_gd), Decimal(-200000))
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
        AccountCode.objects.create(code='WWI 38', account_number='9000000038', account_name='WWI 38 DVA')
        self.client.force_authenticate(self.cashier)
        response = self.client.post(
            f'/api/game-days/{self.game_day.id}/players/',
            {'display_name': 'Brand New'},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Player.objects.filter(account_code='WWI 38').exists())

    def test_seating_new_player_fails_without_an_available_account_code(self):
        self.client.force_authenticate(self.cashier)
        response = self.client.post(
            f'/api/game-days/{self.game_day.id}/players/', {'display_name': 'No Code Left'},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('No available account codes', response.data['detail'])

    def test_accountant_cannot_seat_a_player(self):
        accountant = StaffUser.objects.create_user(username='acct2', password='x', role=StaffUser.Role.ACCOUNTANT)
        self.client.force_authenticate(accountant)
        response = self.client.post(
            f'/api/game-days/{self.game_day.id}/players/', {'display_name': 'Blocked'},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_payout_failed_badge_surfaces_on_the_seated_players_endpoint(self):
        """A payout stuck at TRANSFER_FAILED shows up as payout_failed on the
        Cashier's own player panel — see selectors.player_has_failed_payout.
        Not otherwise visible to a Cashier (only the Owner's Payouts view
        showed TRANSFER_FAILED before this)."""
        player = Player.objects.create(account_code='WWI 42', display_name='Stuck Payout')
        bank = PlayerBankAccount.objects.create(
            player=player, bank_name='GTBank', bank_code='058', account_number='0123456789',
            account_name='Stuck Payout', is_default=True,
        )
        self._seat_and_leave(self.game_day, player)
        Transaction.objects.create(
            game_day=self.game_day, player=player, type=Transaction.Type.PAYMENT_TRANSFER, amount=Decimal(50000),
            channel=Transaction.Channel.TRANSFER_DVA,
        )
        payout = services.initiate_payout(player, Decimal(50000), self.cashier, game_day=self.game_day)
        bank.delete()
        services.approve_payout(payout, self.owner)
        payout.refresh_from_db()
        self.assertEqual(payout.status, Transaction.Status.TRANSFER_FAILED)
        self.assertTrue(selectors.player_has_failed_payout(player, self.game_day))

        self.client.force_authenticate(self.cashier)
        response = self.client.get(f'/api/game-days/{self.game_day.id}/players/{player.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['payout_failed'])

    def test_payout_failed_badge_clears_once_the_owner_retries_successfully(self):
        player = Player.objects.create(account_code='WWI 43', display_name='Retried Payout')
        bank = PlayerBankAccount.objects.create(
            player=player, bank_name='GTBank', bank_code='058', account_number='0123456789',
            account_name='Retried Payout', is_default=True,
        )
        self._seat_and_leave(self.game_day, player)
        Transaction.objects.create(
            game_day=self.game_day, player=player, type=Transaction.Type.PAYMENT_TRANSFER, amount=Decimal(50000),
            channel=Transaction.Channel.TRANSFER_DVA,
        )
        payout = services.initiate_payout(player, Decimal(50000), self.cashier, game_day=self.game_day)
        bank.delete()
        services.approve_payout(payout, self.owner)
        self.assertTrue(selectors.player_has_failed_payout(player, self.game_day))

        PlayerBankAccount.objects.create(
            player=player, bank_name='GTBank', bank_code='058', account_number='0123456789',
            account_name='Retried Payout', is_default=True,
        )
        with patch('payments.services.initiate_payout_transfer', return_value='TRF_ok'):
            services.approve_payout(payout, self.owner)
        self.assertFalse(selectors.player_has_failed_payout(player, self.game_day))

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

    def _fill_table(self, count):
        players = [Player.objects.create(account_code=f'WWI FULL{i}', display_name=f'Filler {i}') for i in range(count)]
        for p in players:
            services.seat_player(self.game_day, self.owner, player=p)
        return players

    def test_active_seat_cap_blocks_the_tenth_active_player(self):
        self._fill_table(services.MAX_ACTIVE_PLAYERS_PER_GAME_DAY)
        overflow = Player.objects.create(account_code='WWI OVER', display_name='Overflow')
        with self.assertRaises(TableFullError) as ctx:
            services.seat_player(self.game_day, self.owner, player=overflow)
        self.assertEqual(ctx.exception.player, overflow)
        self.assertFalse(GameDayPlayer.objects.filter(game_day=self.game_day, player=overflow).exists())

    def test_reseating_an_already_active_player_is_unaffected_by_the_cap(self):
        players = self._fill_table(services.MAX_ACTIVE_PLAYERS_PER_GAME_DAY)
        services.seat_player(self.game_day, self.owner, player=players[0])  # should not raise
        self.assertEqual(
            GameDayPlayer.objects.filter(game_day=self.game_day, player=players[0]).count(), 1,
        )

    def test_new_player_registration_succeeds_even_when_table_is_full(self):
        AccountCode.objects.create(code='WWI NEWFULL', account_number='9000000039', account_name='WWI NEWFULL DVA')
        self._fill_table(services.MAX_ACTIVE_PLAYERS_PER_GAME_DAY)
        with self.assertRaises(TableFullError):
            services.seat_player(
                self.game_day, self.owner, player_fields={'display_name': 'Hopeful'},
            )
        self.assertTrue(Player.objects.filter(account_code='WWI NEWFULL').exists())  # registered anyway
        self.assertFalse(
            GameDayPlayer.objects.filter(game_day=self.game_day, player__account_code='WWI NEWFULL').exists(),
        )

    def test_table_full_api_response_carries_registered_not_seated(self):
        AccountCode.objects.create(code='WWI APIFULL', account_number='9000000040', account_name='WWI APIFULL DVA')
        self._fill_table(services.MAX_ACTIVE_PLAYERS_PER_GAME_DAY)
        self.client.force_authenticate(self.cashier)
        response = self.client.post(
            f'/api/game-days/{self.game_day.id}/players/',
            {'display_name': 'Via API'},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(response.data['registered_not_seated'])
        self.assertTrue(Player.objects.filter(account_code='WWI APIFULL').exists())
        self.assertEqual(response.data['player_id'], Player.objects.get(account_code='WWI APIFULL').id)


class SeatNumberTests(APITestCase):
    """
    Numbered seats on top of GameDayPlayer's plain presence-tracking (added
    2026-09-17) — see gaming.services.seat_player/move_seat and
    selectors.free_seat_numbers.
    """

    def setUp(self):
        self.owner = StaffUser.objects.create_user(username='owner', password='x', role=StaffUser.Role.OWNER)
        self.cashier = StaffUser.objects.create_user(username='cashier', password='x', role=StaffUser.Role.CASHIER)
        self.game_day = services.open_game_day(31, timezone.now(), self.owner)
        self.a = Player.objects.create(account_code='WWI SEAT-A', display_name='Seat A')
        self.b = Player.objects.create(account_code='WWI SEAT-B', display_name='Seat B')

    def test_seat_number_out_of_range_rejected(self):
        with self.assertRaises(InvalidStateError):
            services.seat_player(self.game_day, self.owner, player=self.a, seat_number=10)
        with self.assertRaises(InvalidStateError):
            services.seat_player(self.game_day, self.owner, player=self.a, seat_number=0)

    def test_seat_number_already_taken_rejected(self):
        services.seat_player(self.game_day, self.owner, player=self.a, seat_number=3)
        with self.assertRaises(InvalidStateError):
            services.seat_player(self.game_day, self.owner, player=self.b, seat_number=3)

    def test_seat_number_is_optional(self):
        player = services.seat_player(self.game_day, self.owner, player=self.a)
        seat = GameDayPlayer.objects.get(game_day=self.game_day, player=player)
        self.assertIsNone(seat.seat_number)
        self.assertEqual(selectors.free_seat_numbers(self.game_day), list(range(1, 10)))

    def test_seat_number_freed_on_leave(self):
        services.seat_player(self.game_day, self.owner, player=self.a, seat_number=5)
        self.assertNotIn(5, selectors.free_seat_numbers(self.game_day))
        services.leave_table(self.game_day, self.a, operator=self.cashier)
        self.assertIn(5, selectors.free_seat_numbers(self.game_day))
        # And the freed number can immediately be taken by someone else.
        services.seat_player(self.game_day, self.owner, player=self.b, seat_number=5)
        self.assertEqual(
            GameDayPlayer.objects.get(game_day=self.game_day, player=self.b).seat_number, 5,
        )

    def test_move_seat_into_a_free_seat(self):
        services.seat_player(self.game_day, self.owner, player=self.a, seat_number=1)
        services.move_seat(self.game_day, self.a, 7, operator=self.cashier)
        seat = GameDayPlayer.objects.get(game_day=self.game_day, player=self.a)
        self.assertEqual(seat.seat_number, 7)
        self.assertIn(1, selectors.free_seat_numbers(self.game_day))

    def test_move_seat_swaps_two_occupied_seats(self):
        services.seat_player(self.game_day, self.owner, player=self.a, seat_number=1)
        services.seat_player(self.game_day, self.owner, player=self.b, seat_number=2)
        services.move_seat(self.game_day, self.a, 2, operator=self.cashier)
        self.assertEqual(GameDayPlayer.objects.get(game_day=self.game_day, player=self.a).seat_number, 2)
        self.assertEqual(GameDayPlayer.objects.get(game_day=self.game_day, player=self.b).seat_number, 1)

    def test_move_seat_requires_currently_seated(self):
        with self.assertRaises(InvalidStateError):
            services.move_seat(self.game_day, self.a, 4, operator=self.cashier)

    def test_move_seat_via_api(self):
        services.seat_player(self.game_day, self.owner, player=self.a, seat_number=1)
        self.client.force_authenticate(self.cashier)
        response = self.client.post(
            f'/api/game-days/{self.game_day.id}/players/{self.a.id}/move-seat/', {'seat_number': 9},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['seat_number'], 9)


class LeaveTableTests(APITestCase):
    """gaming.services.leave_table — see PLAN.md's "leave the table" entry."""

    def setUp(self):
        self.owner = StaffUser.objects.create_user(username='owner', password='x', role=StaffUser.Role.OWNER)
        self.cashier = StaffUser.objects.create_user(username='cashier', password='x', role=StaffUser.Role.CASHIER)
        self.accountant = StaffUser.objects.create_user(
            username='acct3', password='x', role=StaffUser.Role.ACCOUNTANT,
        )
        self.game_day = services.open_game_day(50, timezone.now(), self.owner)
        self.player = Player.objects.create(account_code='WWI 50', display_name='Leaver')
        services.seat_player(self.game_day, self.owner, player=self.player)
        self.fm = FloorManager(name='Floor Boss', created_by=self.owner)
        self.fm.set_pin('4321')
        self.fm.save()

    def test_leave_table_sets_left_at_without_touching_history(self):
        services.record_transaction(
            type=Transaction.Type.PAYMENT_TRANSFER, amount=Decimal(100000), recorded_by=self.cashier,
            game_day=self.game_day, player=self.player,
        )
        seat = services.leave_table(self.game_day, self.player, operator=self.cashier)
        self.assertIsNotNone(seat.left_at)
        self.assertEqual(selectors.player_game_day_balance(self.player, self.game_day), Decimal(100000))

    def test_leaving_someone_never_seated_raises(self):
        stranger = Player.objects.create(account_code='WWI 51', display_name='Stranger')
        with self.assertRaises(InvalidStateError):
            services.leave_table(self.game_day, stranger, operator=self.cashier)

    def test_reseating_a_departed_player_via_seat_player_now_raises(self):
        """Revised 2026-09-15: "Return to Table" is gone — seat_player can no
        longer revive anyone, only issuing chips can. A departed player_id
        gets a clear, specific error instead of a silent re-seat."""
        services.leave_table(self.game_day, self.player, operator=self.cashier)
        with self.assertRaises(InvalidStateError):
            services.seat_player(self.game_day, self.owner, player=self.player)
        seat = GameDayPlayer.objects.get(game_day=self.game_day, player=self.player)
        self.assertIsNotNone(seat.left_at)  # untouched — still departed

    def test_issuing_chips_to_a_departed_player_raises(self):
        """Revised 2026-09-22: Issue Chips no longer silently revives a
        departed player (it used to put them back on whatever seat_number
        they still carried from before, which could since have been taken
        by someone else) — it now raises, directing to rejoin_at_seat
        (explicit seat pick) instead. See _ensure_seated's block_departed."""
        services.leave_table(self.game_day, self.player, operator=self.cashier)
        with self.assertRaises(InvalidStateError):
            services.record_transaction(
                type=Transaction.Type.CHIPS_OUT, amount=Decimal(50000), recorded_by=self.cashier,
                game_day=self.game_day, player=self.player,
                floor_manager_id=self.fm.pk, floor_manager_pin='4321',
            )
        seat = GameDayPlayer.objects.get(game_day=self.game_day, player=self.player)
        self.assertIsNotNone(seat.left_at)  # still departed — untouched

    def test_any_other_transaction_type_does_not_revive_a_departed_player(self):
        """Return Chips (CHIPS_IN), a payment, etc. record normally against
        a departed player without seating them again — unaffected by the
        CHIPS_OUT block above, and this is exactly the "correct a mistake
        after the fact" path Return Chips is for."""
        services.leave_table(self.game_day, self.player, operator=self.cashier)
        services.record_transaction(
            type=Transaction.Type.PAYMENT_POS, amount=Decimal(5000), recorded_by=self.cashier,
            game_day=self.game_day, player=self.player,
        )
        seat = GameDayPlayer.objects.get(game_day=self.game_day, player=self.player)
        self.assertIsNotNone(seat.left_at)  # still departed
        self.assertEqual(selectors.player_game_day_balance(self.player, self.game_day), Decimal(5000))  # but recorded

    def test_rejoin_at_seat_happy_path(self):
        services.leave_table(self.game_day, self.player, operator=self.cashier)
        seat = services.rejoin_at_seat(self.game_day, self.player, 4, operator=self.cashier)
        self.assertIsNone(seat.left_at)
        self.assertEqual(seat.seat_number, 4)
        # Now active again — Issue Chips works exactly like any other player.
        services.record_transaction(
            type=Transaction.Type.CHIPS_OUT, amount=Decimal(50000), recorded_by=self.cashier,
            game_day=self.game_day, player=self.player,
            floor_manager_id=self.fm.pk, floor_manager_pin='4321',
        )

    def test_rejoin_at_seat_onto_a_taken_seat_raises(self):
        services.leave_table(self.game_day, self.player, operator=self.cashier)
        occupant = Player.objects.create(account_code='WWI 52', display_name='Occupant')
        services.seat_player(self.game_day, self.owner, player=occupant, seat_number=4)
        with self.assertRaises(InvalidStateError):
            services.rejoin_at_seat(self.game_day, self.player, 4, operator=self.cashier)

    def test_rejoin_at_seat_on_a_still_active_player_raises(self):
        with self.assertRaises(InvalidStateError):
            services.rejoin_at_seat(self.game_day, self.player, 4, operator=self.cashier)

    def test_rejoin_at_seat_is_subject_to_the_active_cap(self):
        services.leave_table(self.game_day, self.player, operator=self.cashier)
        fillers = [Player.objects.create(account_code=f'WWI RET{i}', display_name=f'Filler {i}')
                   for i in range(services.MAX_ACTIVE_PLAYERS_PER_GAME_DAY)]
        for i, p in enumerate(fillers):
            services.seat_player(self.game_day, self.owner, player=p, seat_number=i + 1)
        with self.assertRaises(TableFullError):
            services.rejoin_at_seat(self.game_day, self.player, services.MAX_ACTIVE_PLAYERS_PER_GAME_DAY, operator=self.cashier)

    def test_cashier_can_rejoin_a_player_via_api(self):
        services.leave_table(self.game_day, self.player, operator=self.cashier)
        self.client.force_authenticate(self.cashier)
        response = self.client.post(
            f'/api/game-days/{self.game_day.id}/players/{self.player.id}/rejoin/', {'seat_number': 3},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data['left_at'])
        self.assertEqual(response.data['seat_number'], 3)

    def test_a_brand_new_players_first_transaction_is_subject_to_the_active_cap(self):
        """Closes a gap found alongside the above: record_transaction seating
        someone never seated tonight at all (not just reviving a departed
        one) must be capped too, regardless of transaction type. self.player
        (from setUp) already occupies one active seat, so one fewer filler
        is needed to reach the cap of MAX_ACTIVE_PLAYERS_PER_GAME_DAY."""
        fillers = [Player.objects.create(account_code=f'WWI NEW{i}', display_name=f'Filler {i}')
                   for i in range(services.MAX_ACTIVE_PLAYERS_PER_GAME_DAY - 1)]
        for p in fillers:
            services.seat_player(self.game_day, self.owner, player=p)
        stranger = Player.objects.create(account_code='WWI STRANGER', display_name='Stranger')
        with self.assertRaises(TableFullError):
            services.record_transaction(
                type=Transaction.Type.PAYMENT_TRANSFER, amount=Decimal(1000), recorded_by=self.cashier,
                game_day=self.game_day, player=stranger,
            )

    def test_cashier_can_mark_a_player_as_left_via_api(self):
        self.client.force_authenticate(self.cashier)
        response = self.client.post(f'/api/game-days/{self.game_day.id}/players/{self.player.id}/leave/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data['left_at'])

    def test_accountant_cannot_mark_a_player_as_left(self):
        self.client.force_authenticate(self.accountant)
        response = self.client.post(f'/api/game-days/{self.game_day.id}/players/{self.player.id}/leave/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ChipsReturnedCannotExceedChipsOutTests(APITestCase):
    """
    gaming.services.record_transaction's CHIPS_IN branch — added 2026-09-22
    per an explicit request: chips returned on a game-day can never exceed
    what could still physically be on the table, checked before the entry
    posts (not just at close, where chips_variance would otherwise be the
    first place it surfaced). Deliberately game-day-wide, not per-player —
    see the check's own comment in services.py.

    Revised 2026-09-23: rake and tips are chips that legitimately never
    come back as a CHIPS_IN — netted out of the ceiling the same way
    chips_variance already nets them out at close, so this on-the-spot
    check can't be looser than that one.
    """

    def setUp(self):
        self.owner = StaffUser.objects.create_user(username='owner2', password='x', role=StaffUser.Role.OWNER)
        self.cashier = StaffUser.objects.create_user(username='cashier2', password='x', role=StaffUser.Role.CASHIER)
        self.game_day = services.open_game_day(60, timezone.now(), self.owner)
        self.fm = FloorManager(name='Floor Boss 2', created_by=self.owner)
        self.fm.set_pin('9999')
        self.fm.save()
        self.p1 = Player.objects.create(account_code='WWI 60', display_name='Player One')
        self.p2 = Player.objects.create(account_code='WWI 61', display_name='Player Two')
        services.seat_player(self.game_day, self.owner, player=self.p1)
        services.seat_player(self.game_day, self.owner, player=self.p2)

    def _chips_out(self, player, amount):
        return services.record_transaction(
            type=Transaction.Type.CHIPS_OUT, amount=Decimal(amount), recorded_by=self.cashier,
            game_day=self.game_day, player=player, floor_manager_id=self.fm.pk, floor_manager_pin='9999',
        )

    def _chips_in(self, player, amount):
        return services.record_transaction(
            type=Transaction.Type.CHIPS_IN, amount=Decimal(amount), recorded_by=self.cashier,
            game_day=self.game_day, player=player, floor_manager_id=self.fm.pk, floor_manager_pin='9999',
        )

    def _rake(self, amount):
        return services.record_transaction(
            type=Transaction.Type.RAKE, amount=Decimal(amount), recorded_by=self.cashier,
            game_day=self.game_day, floor_manager_id=self.fm.pk, floor_manager_pin='9999',
        )

    def _tip(self, amount):
        return services.record_transaction(
            type=Transaction.Type.TIP, amount=Decimal(amount), recorded_by=self.cashier,
            game_day=self.game_day, tip_category=Transaction.TipCategory.SERVICE_STAFF,
            floor_manager_id=self.fm.pk, floor_manager_pin='9999',
        )

    def test_return_up_to_exactly_chips_out_is_allowed(self):
        self._chips_out(self.p1, 500000)
        self._chips_in(self.p1, 500000)  # exact match — the boundary, not an error

    def test_return_exceeding_chips_out_raises(self):
        self._chips_out(self.p1, 500000)
        with self.assertRaises(InvalidStateError):
            self._chips_in(self.p1, 500001)

    def test_check_is_game_day_wide_not_per_player(self):
        """A discrepancy is still a discrepancy even if it nets out across
        different players — one player's excess return is still an excess
        against the night's total chips in play."""
        self._chips_out(self.p1, 500000)
        self._chips_in(self.p1, 200000)
        # p2 never had any chips out — this alone doesn't exceed the
        # game-day total (500,000 out vs 200,000+250,000=450,000 in), so it
        # should succeed even though it's a different player than the one
        # who was issued chips.
        self._chips_in(self.p2, 250000)
        with self.assertRaises(InvalidStateError):
            self._chips_in(self.p2, 50001)  # now 450,000 + 50,001 > 500,000

    def test_a_voided_chips_out_no_longer_counts_toward_the_cap(self):
        txn = self._chips_out(self.p1, 500000)
        services.void_transaction(txn, self.owner, 'test voided')
        with self.assertRaises(InvalidStateError):
            self._chips_in(self.p1, 1)  # nothing left to return against

    def test_error_message_reports_the_amounts(self):
        self._chips_out(self.p1, 500000)
        with self.assertRaises(InvalidStateError) as ctx:
            self._chips_in(self.p1, 600000)
        message = str(ctx.exception)
        self.assertIn('600,000', message)
        self.assertIn('500,000', message)

    def test_api_surfaces_the_discrepancy_as_a_400(self):
        self._chips_out(self.p1, 500000)
        self.client.force_authenticate(self.cashier)
        response = self.client.post('/api/transactions/', {
            'type': 'CHIPS_IN', 'amount': '600000', 'game_day': self.game_day.id, 'player': self.p1.id,
            'floor_manager_id': self.fm.pk, 'floor_manager_pin': '9999',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rake_lowers_the_returnable_ceiling(self):
        """500,000 out, 50,000 raked — only 450,000 can still come back as
        a CHIPS_IN, even though that's less than chips_out_total itself."""
        self._chips_out(self.p1, 500000)
        self._rake(50000)
        self._chips_in(self.p1, 450000)  # exact new ceiling — allowed
        with self.assertRaises(InvalidStateError):
            self._chips_in(self.p2, 1)  # one more than what's left on the table

    def test_tips_also_lower_the_returnable_ceiling(self):
        self._chips_out(self.p1, 500000)
        self._tip(20000)
        self._chips_in(self.p1, 480000)  # exact new ceiling — allowed
        with self.assertRaises(InvalidStateError):
            self._chips_in(self.p2, 1)

    def test_rake_and_tips_stack_against_the_ceiling(self):
        self._chips_out(self.p1, 500000)
        self._rake(50000)
        self._tip(20000)
        with self.assertRaises(InvalidStateError):
            self._chips_in(self.p1, 430001)  # one above 500,000 - 50,000 - 20,000
        self._chips_in(self.p1, 430000)  # exact ceiling — allowed

    def test_error_message_reports_the_rake_and_tip_adjusted_ceiling(self):
        self._chips_out(self.p1, 500000)
        self._rake(50000)
        with self.assertRaises(InvalidStateError) as ctx:
            self._chips_in(self.p1, 460000)
        message = str(ctx.exception)
        self.assertIn('460,000', message)
        self.assertIn('450,000', message)  # the rake-adjusted ceiling, not raw chips_out

    def test_chips_totals_endpoint_includes_rake_and_tips(self):
        """
        Added 2026-09-23 fixing a live bug: the Cashier's chips-caption used
        to derive rake/tips from `ledger`/`activity`, which exclude those
        types entirely (they're day-level, not player-scoped) — so the
        caption could never reflect them no matter how much chip was raked
        or tipped. This dedicated endpoint is the fix.
        """
        self._chips_out(self.p1, 500000)
        self._chips_in(self.p1, 100000)
        self._rake(50000)
        self._tip(20000)
        self.client.force_authenticate(self.cashier)
        response = self.client.get(f'/api/game-days/{self.game_day.id}/chips-totals/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(str(response.data['chips_out_total'])), Decimal(500000))
        self.assertEqual(Decimal(str(response.data['chips_in_total'])), Decimal(100000))
        self.assertEqual(Decimal(str(response.data['rake_total'])), Decimal(50000))
        self.assertEqual(Decimal(str(response.data['tips_total'])), Decimal(20000))


class DealOnClosedGameDayTests(APITestCase):
    """
    Corrected 2026-09-15: a Deal/write-off is not manually pointed at any
    game-day the Owner picks from history — it automatically lands wherever
    is open right now, and the ONLY closed game-day it may ever target is
    the single most-recently-closed one (RosterDetailView.vue's "just
    ended" checkbox). See services._require_open_game_day/DEAL_TYPES.
    """

    def setUp(self):
        self.owner = StaffUser.objects.create_user(username='owner4', password='x', role=StaffUser.Role.OWNER)
        self.cashier = StaffUser.objects.create_user(username='cashier4', password='x', role=StaffUser.Role.CASHIER)
        self.fm = FloorManager(name='Floor Boss 4', created_by=self.owner)
        self.fm.set_pin('4321')
        self.fm.save()
        self.player = Player.objects.create(account_code='WWI 60', display_name='Deal Target')

        self.old_gd = services.open_game_day(60, timezone.now(), self.owner)
        services.close_game_day(self.old_gd, self.cashier, floor_manager_id=self.fm.pk, floor_manager_pin='4321')
        self.last_closed_gd = services.open_game_day(61, timezone.now(), self.owner)
        services.close_game_day(
            self.last_closed_gd, self.cashier, floor_manager_id=self.fm.pk, floor_manager_pin='4321',
        )
        self.open_gd = services.open_game_day(62, timezone.now(), self.owner)

    def test_deal_on_the_just_closed_game_day_is_accepted_and_lands_there(self):
        txn = services.record_transaction(
            type=Transaction.Type.PAYMENT_DEAL, amount=Decimal(1000), recorded_by=self.owner,
            game_day=self.last_closed_gd, player=self.player, notes='retroactive',
        )
        self.assertEqual(selectors.player_game_day_balance(self.player, self.last_closed_gd), Decimal(1000))
        self.assertEqual(selectors.outstanding_ledger(player=self.player).count(), 0)
        # A ledger entry on a closed night shouldn't resurrect/seat anyone into it.
        self.assertFalse(GameDayPlayer.objects.filter(game_day=self.last_closed_gd, player=self.player).exists())
        self.assertIsNotNone(txn.game_day_id)

    def test_write_off_on_the_just_closed_game_day_is_also_accepted(self):
        Transaction.objects.create(
            player=self.player, type=Transaction.Type.CHIPS_OUT, amount=Decimal(200),
            channel=Transaction.Channel.CASHIER, recorded_by=self.cashier,
        )
        services.record_transaction(
            type=Transaction.Type.WRITE_OFF, amount=Decimal(200), recorded_by=self.owner,
            game_day=self.last_closed_gd, player=self.player, notes='retroactive write-off',
        )
        self.assertEqual(selectors.player_game_day_balance(self.player, self.last_closed_gd), Decimal(200))

    def test_deal_on_an_older_closed_game_day_is_rejected(self):
        with self.assertRaises(InvalidStateError):
            services.record_transaction(
                type=Transaction.Type.PAYMENT_DEAL, amount=Decimal(1000), recorded_by=self.owner,
                game_day=self.old_gd, player=self.player, notes='too old',
            )

    def test_non_deal_type_on_the_just_closed_game_day_is_still_rejected(self):
        with self.assertRaises(InvalidStateError):
            services.record_transaction(
                type=Transaction.Type.PAYMENT_TRANSFER, amount=Decimal(1000), recorded_by=self.owner,
                game_day=self.last_closed_gd, player=self.player,
            )

    def test_deal_with_no_game_day_still_lands_in_outstanding_as_before(self):
        txn = services.record_transaction(
            type=Transaction.Type.PAYMENT_DEAL, amount=Decimal(300), recorded_by=self.owner,
            game_day=None, player=self.player, notes='no game-day',
        )
        self.assertEqual(selectors.outstanding_ledger(player=self.player).count(), 1)
        self.assertIsNone(txn.game_day_id)

    def test_deal_on_the_currently_open_game_day_still_works_and_seats_normally(self):
        services.record_transaction(
            type=Transaction.Type.PAYMENT_DEAL, amount=Decimal(400), recorded_by=self.owner,
            game_day=self.open_gd, player=self.player,
        )
        self.assertEqual(selectors.player_game_day_balance(self.player, self.open_gd), Decimal(400))
        self.assertTrue(GameDayPlayer.objects.filter(game_day=self.open_gd, player=self.player).exists())

    def test_deal_via_api_on_the_just_closed_game_day(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post('/api/transactions/', {
            'type': 'PAYMENT_DEAL', 'amount': '750', 'player': self.player.id,
            'notes': 'via api', 'game_day': self.last_closed_gd.id,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(selectors.player_game_day_balance(self.player, self.last_closed_gd), Decimal(750))


class TipCategoryTests(APITestCase):
    """
    Service staff/Masseuse tip categorization (added 2026-09-17 as
    Dealer/Service, renamed 2026-09-23 — see Transaction.TipCategory's own
    comment) — Service staff stays anonymous/aggregate exactly as every Tip
    did before this; Masseuse requires a named, active Masseuse recipient.
    See PLAN.md's entry and gaming.services.record_transaction.
    """

    def setUp(self):
        self.owner = StaffUser.objects.create_user(username='owner5', password='x', role=StaffUser.Role.OWNER)
        self.cashier = StaffUser.objects.create_user(username='cashier5', password='x', role=StaffUser.Role.CASHIER)
        self.game_day = services.open_game_day(40, timezone.now(), self.owner)
        self.fm = FloorManager(name='Floor Boss 2', created_by=self.owner)
        self.fm.set_pin('4321')
        self.fm.save()
        self.person = StaffMember.objects.create(
            name='Blessing', role=StaffMember.Role.MASSEUSE, created_by=self.owner,
        )

    def _tip(self, **kwargs):
        return services.record_transaction(
            type=Transaction.Type.TIP, amount=Decimal(1000), recorded_by=self.cashier,
            game_day=self.game_day, floor_manager_id=self.fm.pk, floor_manager_pin='4321', **kwargs,
        )

    def test_service_staff_tip_needs_no_recipient(self):
        txn = self._tip(tip_category=Transaction.TipCategory.SERVICE_STAFF)
        self.assertIsNone(txn.masseuse)
        self.assertEqual(txn.tip_category, Transaction.TipCategory.SERVICE_STAFF)

    def test_service_staff_tip_rejects_a_recipient(self):
        with self.assertRaises(InvalidStateError):
            self._tip(tip_category=Transaction.TipCategory.SERVICE_STAFF, masseuse=self.person)

    def test_masseuse_tip_requires_a_recipient(self):
        with self.assertRaises(InvalidStateError):
            self._tip(tip_category=Transaction.TipCategory.MASSEUSE)

    def test_masseuse_tip_with_a_recipient_succeeds(self):
        txn = self._tip(tip_category=Transaction.TipCategory.MASSEUSE, masseuse=self.person)
        self.assertEqual(txn.masseuse, self.person)

    def test_masseuse_tip_requires_an_active_recipient(self):
        self.person.is_active = False
        self.person.save()
        with self.assertRaises(InvalidStateError):
            self._tip(tip_category=Transaction.TipCategory.MASSEUSE, masseuse=self.person)

    def test_masseuse_tip_rejects_a_dealer_or_service_staffmember(self):
        """A StaffMember's `masseuse` FK must actually be role=MASSEUSE — a
        Dealer/Service record (added 2026-09-23, same roster, different
        role) is never a valid tip recipient."""
        dealer = StaffMember.objects.create(name='Femi', role=StaffMember.Role.DEALER, created_by=self.owner)
        with self.assertRaises(InvalidStateError):
            self._tip(tip_category=Transaction.TipCategory.MASSEUSE, masseuse=dealer)

    def test_tip_without_a_category_is_rejected(self):
        with self.assertRaises(InvalidStateError):
            self._tip()

    def test_tip_category_rejected_on_a_non_tip_type(self):
        with self.assertRaises(InvalidStateError):
            services.record_transaction(
                type=Transaction.Type.PAYMENT_CASH, amount=Decimal(1000), recorded_by=self.cashier,
                game_day=self.game_day, tip_category=Transaction.TipCategory.SERVICE_STAFF,
                floor_manager_id=self.fm.pk, floor_manager_pin='4321',
            )

    def test_masseuse_tip_via_api(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post('/api/transactions/', {
            'type': 'TIP', 'amount': '2000', 'game_day': self.game_day.id,
            'tip_category': 'MASSEUSE', 'masseuse': self.person.id,
            'floor_manager_id': self.fm.pk, 'floor_manager_pin': '4321',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['masseuse'], self.person.id)

    def test_service_staff_tip_via_api_without_recipient(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post('/api/transactions/', {
            'type': 'TIP', 'amount': '2000', 'game_day': self.game_day.id,
            'tip_category': 'SERVICE_STAFF',
            'floor_manager_id': self.fm.pk, 'floor_manager_pin': '4321',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertIsNone(response.data['masseuse'])


class DealTransferTests(APITestCase):
    """
    "Deals" Transfer (added 2026-09-20) — settles one player's debt using
    another's excess. See gaming.services.record_deal_transfer and
    PLAN.md's entry.
    """

    def setUp(self):
        self.owner = StaffUser.objects.create_user(username='owner6', password='x', role=StaffUser.Role.OWNER)
        self.cashier = StaffUser.objects.create_user(username='cashier6', password='x', role=StaffUser.Role.CASHIER)
        self.source = Player.objects.create(account_code='WWI T1', display_name='Source Player')
        self.dest = Player.objects.create(account_code='WWI T2', display_name='Dest Player')

    def _give_source_credit(self, amount):
        # A positive lifetime balance — e.g. chips returned exceeding what was
        # issued, or a straightforward CHIPS_IN credit for test purposes.
        Transaction.objects.create(
            player=self.source, type=Transaction.Type.CHIPS_IN, amount=Decimal(amount),
            channel=Transaction.Channel.CHIPS, recorded_by=self.cashier,
        )

    def test_transfer_creates_a_linked_debit_and_credit_pair(self):
        self._give_source_credit(50000)
        out_txn, in_txn = services.record_deal_transfer(self.source, self.dest, Decimal(20000), 'settling up', self.owner)
        self.assertEqual(out_txn.type, Transaction.Type.DEAL_TRANSFER_OUT)
        self.assertEqual(in_txn.type, Transaction.Type.DEAL_TRANSFER_IN)
        self.assertEqual(out_txn.linked_transaction_id, in_txn.pk)
        self.assertEqual(in_txn.linked_transaction_id, out_txn.pk)
        self.assertEqual(selectors.player_balance(self.source), Decimal(30000))
        self.assertEqual(selectors.player_balance(self.dest), Decimal(20000))

    def test_transfer_cannot_exceed_sources_positive_balance(self):
        self._give_source_credit(10000)
        with self.assertRaises(InvalidStateError):
            services.record_deal_transfer(self.source, self.dest, Decimal(20000), 'too much', self.owner)

    def test_transfer_rejected_when_source_has_no_positive_balance(self):
        # source has no transactions at all — balance is 0, not positive.
        with self.assertRaises(InvalidStateError):
            services.record_deal_transfer(self.source, self.dest, Decimal(1), 'nothing to give', self.owner)

    def test_transfer_rejected_when_source_is_in_debt(self):
        Transaction.objects.create(
            player=self.source, type=Transaction.Type.CHIPS_OUT, amount=Decimal(30000),
            channel=Transaction.Channel.CASHIER, recorded_by=self.cashier,
        )
        with self.assertRaises(InvalidStateError):
            services.record_deal_transfer(self.source, self.dest, Decimal(1000), 'from a debtor', self.owner)

    def test_transfer_can_push_destination_positive(self):
        # No cap on the destination side beyond the source's own positive balance.
        self._give_source_credit(50000)
        services.record_deal_transfer(self.source, self.dest, Decimal(50000), 'full transfer', self.owner)
        self.assertEqual(selectors.player_balance(self.dest), Decimal(50000))

    def test_transfer_requires_a_reason(self):
        self._give_source_credit(10000)
        with self.assertRaises(InvalidStateError):
            services.record_deal_transfer(self.source, self.dest, Decimal(1000), '', self.owner)

    def test_transfer_to_self_is_rejected(self):
        self._give_source_credit(10000)
        with self.assertRaises(InvalidStateError):
            services.record_deal_transfer(self.source, self.source, Decimal(1000), 'to myself', self.owner)

    def test_cashier_cannot_record_a_transfer(self):
        self._give_source_credit(10000)
        with self.assertRaises(AuthorizationError):
            services.record_deal_transfer(self.source, self.dest, Decimal(1000), 'nice try', self.cashier)

    def test_voiding_one_leg_voids_the_linked_leg_too(self):
        self._give_source_credit(50000)
        out_txn, in_txn = services.record_deal_transfer(self.source, self.dest, Decimal(20000), 'settling up', self.owner)
        services.void_transaction(out_txn, self.owner, 'mistaken transfer')
        in_txn.refresh_from_db()
        self.assertTrue(in_txn.is_voided)
        self.assertEqual(in_txn.void_reason, 'mistaken transfer')
        self.assertEqual(selectors.player_balance(self.source), Decimal(50000))
        self.assertEqual(selectors.player_balance(self.dest), Decimal(0))

    def test_cashier_cannot_use_the_transfer_endpoint(self):
        self._give_source_credit(10000)
        self.client.force_authenticate(self.cashier)
        response = self.client.post('/api/deals/transfer/', {
            'source_player': self.source.id, 'destination_player': self.dest.id,
            'amount': '1000', 'reason': 'nice try',
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_can_transfer_via_api(self):
        self._give_source_credit(10000)
        self.client.force_authenticate(self.owner)
        response = self.client.post('/api/deals/transfer/', {
            'source_player': self.source.id, 'destination_player': self.dest.id,
            'amount': '4000', 'reason': 'via api',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['out']['type'], Transaction.Type.DEAL_TRANSFER_OUT)
        self.assertEqual(response.data['in']['type'], Transaction.Type.DEAL_TRANSFER_IN)
        self.assertEqual(selectors.player_balance(self.dest), Decimal(4000))


class ProfitSplitArrangementTests(APITestCase):
    """
    "Deals" Profit Split (added 2026-09-20) — only the stake side (buy-in
    funding) is actually enforced; the payout-split fields are configuration
    only for now. See ProfitSplitArrangement's docstring and PLAN.md's entry.
    """

    def setUp(self):
        self.owner = StaffUser.objects.create_user(username='owner7', password='x', role=StaffUser.Role.OWNER)
        self.cashier = StaffUser.objects.create_user(username='cashier7', password='x', role=StaffUser.Role.CASHIER)
        self.player = Player.objects.create(account_code='WWI PS1', display_name='Profit Split Player')
        self.game_day = services.open_game_day(70, timezone.now(), self.owner)
        self.fm = FloorManager(name='PS Floor Boss', created_by=self.owner)
        self.fm.set_pin('7777')
        self.fm.save()

    def _buy_in(self, amount):
        return services.record_transaction(
            type=Transaction.Type.CHIPS_OUT, amount=Decimal(amount), recorded_by=self.cashier,
            game_day=self.game_day, player=self.player,
            floor_manager_id=self.fm.pk, floor_manager_pin='7777',
        )

    # --- creation / validation ---

    def test_cashier_cannot_create_an_arrangement(self):
        with self.assertRaises(AuthorizationError):
            services.create_profit_split_arrangement(
                self.player, self.cashier, house_stake_pct=Decimal(50), cap_amount=Decimal(100000),
            )

    def test_house_stake_pct_out_of_range_is_rejected(self):
        with self.assertRaises(InvalidStateError):
            services.create_profit_split_arrangement(
                self.player, self.owner, house_stake_pct=Decimal(150), cap_amount=Decimal(100000),
            )

    def test_negative_cap_is_rejected(self):
        with self.assertRaises(InvalidStateError):
            services.create_profit_split_arrangement(
                self.player, self.owner, house_stake_pct=Decimal(50), cap_amount=Decimal(-1),
            )

    def test_one_off_with_an_end_date_is_rejected(self):
        with self.assertRaises(InvalidStateError):
            services.create_profit_split_arrangement(
                self.player, self.owner, house_stake_pct=Decimal(50), cap_amount=Decimal(100000),
                reset_cadence=ProfitSplitArrangement.ResetCadence.ONE_OFF, ends_at=timezone.now(),
            )

    def test_stake_ratio_payout_method_requires_a_positive_stake(self):
        with self.assertRaises(InvalidStateError):
            services.create_profit_split_arrangement(
                self.player, self.owner, house_stake_pct=Decimal(0), cap_amount=Decimal(0),
                payout_split_method=ProfitSplitArrangement.PayoutSplitMethod.STAKE_RATIO,
            )

    def test_custom_ratio_payout_method_requires_a_percentage(self):
        with self.assertRaises(InvalidStateError):
            services.create_profit_split_arrangement(
                self.player, self.owner, house_stake_pct=Decimal(50), cap_amount=Decimal(100000),
                payout_split_method=ProfitSplitArrangement.PayoutSplitMethod.CUSTOM_RATIO,
            )

    def test_fixed_payout_method_requires_an_amount(self):
        with self.assertRaises(InvalidStateError):
            services.create_profit_split_arrangement(
                self.player, self.owner, house_stake_pct=Decimal(50), cap_amount=Decimal(100000),
                payout_split_method=ProfitSplitArrangement.PayoutSplitMethod.FIXED,
            )

    def test_creating_a_new_arrangement_deactivates_the_previous_one(self):
        first = services.create_profit_split_arrangement(
            self.player, self.owner, house_stake_pct=Decimal(50), cap_amount=Decimal(100000),
        )
        second = services.create_profit_split_arrangement(
            self.player, self.owner, house_stake_pct=Decimal(30), cap_amount=Decimal(50000),
        )
        first.refresh_from_db()
        self.assertFalse(first.is_active)
        self.assertIsNotNone(first.deactivated_at)
        self.assertTrue(second.is_active)

    def test_owner_can_create_via_api(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post('/api/deals/profit-split/', {
            'player': self.player.id, 'house_stake_pct': '50', 'cap_amount': '100000',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_cashier_cannot_create_via_api(self):
        self.client.force_authenticate(self.cashier)
        response = self.client.post('/api/deals/profit-split/', {
            'player': self.player.id, 'house_stake_pct': '50', 'cap_amount': '100000',
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # --- buy-in stake application ---

    def test_buy_in_is_split_between_player_and_house(self):
        services.create_profit_split_arrangement(
            self.player, self.owner, house_stake_pct=Decimal(50), cap_amount=Decimal(1000000),
        )
        txn = self._buy_in(100000)
        self.assertEqual(txn.amount, Decimal(50000))
        stake_txn = Transaction.objects.get(type=Transaction.Type.PROFIT_SPLIT_STAKE, player=self.player)
        self.assertEqual(stake_txn.amount, Decimal(50000))
        self.assertEqual(selectors.player_game_day_balance(self.player, self.game_day), Decimal(-50000))

    def test_buy_in_split_is_capped(self):
        services.create_profit_split_arrangement(
            self.player, self.owner, house_stake_pct=Decimal(50), cap_amount=Decimal(20000),
        )
        txn = self._buy_in(100000)
        # 50% of 100000 = 50000, but capped at 20000.
        self.assertEqual(txn.amount, Decimal(80000))
        stake_txn = Transaction.objects.get(type=Transaction.Type.PROFIT_SPLIT_STAKE, player=self.player)
        self.assertEqual(stake_txn.amount, Decimal(20000))

    def test_no_arrangement_means_no_split(self):
        txn = self._buy_in(100000)
        self.assertEqual(txn.amount, Decimal(100000))
        self.assertFalse(Transaction.objects.filter(type=Transaction.Type.PROFIT_SPLIT_STAKE).exists())

    def test_deactivated_arrangement_means_no_split(self):
        arrangement = services.create_profit_split_arrangement(
            self.player, self.owner, house_stake_pct=Decimal(50), cap_amount=Decimal(1000000),
        )
        services.deactivate_profit_split_arrangement(arrangement, self.owner)
        txn = self._buy_in(100000)
        self.assertEqual(txn.amount, Decimal(100000))

    def test_profit_split_stake_never_touches_player_balance_directly(self):
        # It's excluded from both DEBIT_TYPES/CREDIT_TYPES by design — see
        # selectors.py. Confirmed here rather than just by construction.
        services.create_profit_split_arrangement(
            self.player, self.owner, house_stake_pct=Decimal(100), cap_amount=Decimal(1000000),
        )
        self._buy_in(50000)
        # Entirely house-covered — player's own debt is 0.
        self.assertEqual(selectors.player_game_day_balance(self.player, self.game_day), Decimal(0))

    def test_cumulative_cap_exhausts_the_arrangement(self):
        services.create_profit_split_arrangement(
            self.player, self.owner, house_stake_pct=Decimal(100), cap_amount=Decimal(1000000),
            reset_cadence=ProfitSplitArrangement.ResetCadence.DAILY, max_cumulative_value=Decimal(30000),
        )
        first = self._buy_in(20000)
        self.assertEqual(first.amount, Decimal(0))  # fully house-covered
        second = self._buy_in(20000)
        # Only 10000 left of the 30000 cumulative cap; the rest (10000) is on the player.
        self.assertEqual(second.amount, Decimal(10000))
        third = self._buy_in(20000)
        # Cumulative cap fully exhausted — entirely on the player now.
        self.assertEqual(third.amount, Decimal(20000))

    def test_daily_reset_gives_a_fresh_per_period_cap(self):
        arrangement = services.create_profit_split_arrangement(
            self.player, self.owner, house_stake_pct=Decimal(100), cap_amount=Decimal(20000),
            reset_cadence=ProfitSplitArrangement.ResetCadence.DAILY,
        )
        first = self._buy_in(20000)
        self.assertEqual(first.amount, Decimal(0))  # today's cap fully used

        # Backdate the arrangement by 2 days so "now" falls in a new period.
        ProfitSplitArrangement.objects.filter(pk=arrangement.pk).update(
            created_at=timezone.now() - timedelta(days=2),
        )
        second = self._buy_in(20000)
        self.assertEqual(second.amount, Decimal(0))  # fresh period, fresh cap

    def test_ended_arrangement_means_no_split(self):
        services.create_profit_split_arrangement(
            self.player, self.owner, house_stake_pct=Decimal(50), cap_amount=Decimal(1000000),
            reset_cadence=ProfitSplitArrangement.ResetCadence.DAILY, ends_at=timezone.now() - timedelta(days=1),
        )
        txn = self._buy_in(100000)
        self.assertEqual(txn.amount, Decimal(100000))

    # --- status endpoint ---

    def test_status_endpoint_returns_none_without_an_arrangement(self):
        self.client.force_authenticate(self.owner)
        response = self.client.get(f'/api/deals/profit-split/{self.player.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data)

    def test_status_endpoint_reflects_cumulative_covered(self):
        services.create_profit_split_arrangement(
            self.player, self.owner, house_stake_pct=Decimal(50), cap_amount=Decimal(1000000),
        )
        self._buy_in(100000)
        self.client.force_authenticate(self.owner)
        response = self.client.get(f'/api/deals/profit-split/{self.player.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(str(response.data['cumulative_covered'])), Decimal(50000))
        self.assertFalse(response.data['is_exhausted'])

    def test_deactivate_via_api(self):
        arrangement = services.create_profit_split_arrangement(
            self.player, self.owner, house_stake_pct=Decimal(50), cap_amount=Decimal(1000000),
        )
        self.client.force_authenticate(self.owner)
        response = self.client.post(f'/api/deals/profit-split/{arrangement.pk}/deactivate/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['is_active'])

    # --- bulk active-arrangements endpoint (2026-09-23, feeds the web
    # Deals player list's "active" badge without an N+1 per-player call) ---

    def test_active_arrangements_endpoint_lists_only_active_ones(self):
        other = Player.objects.create(account_code='WWI PS2', display_name='Other Player')
        active = services.create_profit_split_arrangement(
            self.player, self.owner, house_stake_pct=Decimal(50), cap_amount=Decimal(100000),
        )
        ended = services.create_profit_split_arrangement(
            other, self.owner, house_stake_pct=Decimal(30), cap_amount=Decimal(50000),
        )
        services.deactivate_profit_split_arrangement(ended, self.owner)

        self.client.force_authenticate(self.owner)
        response = self.client.get('/api/deals/profit-split/active/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [row['id'] for row in response.data]
        self.assertEqual(ids, [active.pk])

    def test_cashier_cannot_view_active_arrangements(self):
        self.client.force_authenticate(self.cashier)
        response = self.client.get('/api/deals/profit-split/active/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_accountant_can_view_active_arrangements(self):
        """Broadened 2026-09-25 — feeds the Players table's own 'Deal' icon column, a shared page."""
        accountant = StaffUser.objects.create_user(username='ps_acct', password='x', role=StaffUser.Role.ACCOUNTANT)
        self.client.force_authenticate(accountant)
        response = self.client.get('/api/deals/profit-split/active/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class StartGameDayFlowTests(APITestCase):
    """
    Game/Table/Buy-in selection at open (added 2026-09-21) — see
    PLAN.md's "Game/Table selection + two-step chip custody" entry.
    """

    def setUp(self):
        self.owner = StaffUser.objects.create_user(username='sgd_owner', password='x', role=StaffUser.Role.OWNER)
        # Distinct from the seeded "Texas Hold'em"/"Omaha" rows (see
        # gaming/migrations/0011_seed_games_and_tables.py) — Game.name is
        # globally unique, and those already exist in every test schema.
        self.game = Game.objects.create(name='Test Game — Start Flow')
        self.table = Table.objects.create(game=self.game, name='Main Table', default_buy_in=Decimal(500000))

    def test_game_day_can_still_be_opened_without_any_of_the_three(self):
        """Backward compatible — every game-day before this change had none of these."""
        game_day = services.open_game_day(100, timezone.now(), self.owner)
        self.assertIsNone(game_day.game)
        self.assertIsNone(game_day.table)
        self.assertIsNone(game_day.buy_in_amount)

    def test_buy_in_amount_defaults_from_the_table_when_omitted(self):
        game_day = services.open_game_day(101, timezone.now(), self.owner, game=self.game, table=self.table)
        self.assertEqual(game_day.buy_in_amount, Decimal(500000))

    def test_buy_in_amount_can_override_the_tables_default(self):
        """Independent choice each night, with a pre-filled default — confirmed, not a hard rule."""
        game_day = services.open_game_day(
            102, timezone.now(), self.owner, game=self.game, table=self.table, buy_in_amount=Decimal(100000),
        )
        self.assertEqual(game_day.buy_in_amount, Decimal(100000))

    def test_open_via_api_with_game_and_table(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(
            '/api/game-days/open/', {'number': 103, 'game_id': self.game.id, 'table_id': self.table.id},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['game'], self.game.id)
        self.assertEqual(response.data['table'], self.table.id)
        self.assertEqual(Decimal(str(response.data['buy_in_amount'])), Decimal(500000))

    def test_games_and_tables_are_listed_read_only(self):
        self.client.force_authenticate(self.owner)
        response = self.client.get('/api/games/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(self.game.name, [row['name'] for row in response.data])

        response = self.client.get(f'/api/tables/?game={self.game.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([row['id'] for row in response.data], [self.table.id])




class ClubSettingsModelTests(TestCase):
    """ClubSettings.load() — the pk=1 singleton convention. Added 2026-09-23
    alongside the "Settings" screen — see ClubSettings' own docstring."""

    def test_load_creates_the_row_with_documented_defaults(self):
        self.assertFalse(ClubSettings.objects.exists())
        obj = ClubSettings.load()
        self.assertEqual(obj.pk, 1)
        self.assertTrue(obj.require_approval_open_game_day)
        self.assertTrue(obj.require_approval_close_game_day)
        self.assertTrue(obj.require_approval_issue_chips)
        self.assertTrue(obj.require_approval_return_chips)
        self.assertTrue(obj.require_approval_add_tip)
        self.assertTrue(obj.require_approval_add_rake)
        self.assertEqual(obj.payout_auto_approve_threshold, Decimal('500000'))

    def test_load_is_a_true_singleton(self):
        first = ClubSettings.load()
        first.require_approval_open_game_day = False
        first.save()
        second = ClubSettings.load()
        self.assertEqual(second.pk, 1)
        self.assertFalse(second.require_approval_open_game_day)
        self.assertEqual(ClubSettings.objects.count(), 1)


class RequireApprovalTogglesTests(APITestCase):
    """
    ClubSettings.require_approval_* — each toggle governs whether its
    action needs an Owner-or-Floor-Manager (or Floor-Manager-only) PIN at
    all. Off doesn't touch anything else about the action — see
    gaming.services.open_game_day/close_game_day/record_transaction.
    """

    def setUp(self):
        self.owner = StaffUser.objects.create_user(username='rat_owner', password='x', role=StaffUser.Role.OWNER)
        self.cashier = StaffUser.objects.create_user(username='rat_cashier', password='x', role=StaffUser.Role.CASHIER)
        self.fm = FloorManager(name='RAT Floor Boss', created_by=self.owner)
        self.fm.set_pin('7777')
        self.fm.save()

    def test_open_game_day_requires_pin_by_default(self):
        with self.assertRaises(AuthorizationError):
            services.open_game_day(200, timezone.now(), self.cashier)

    def test_open_game_day_needs_no_pin_once_disabled(self):
        settings_obj = ClubSettings.load()
        settings_obj.require_approval_open_game_day = False
        settings_obj.save()
        gd = services.open_game_day(201, timezone.now(), self.cashier)
        self.assertIsNone(gd.opened_by)
        self.assertIsNone(gd.opened_by_floor_manager)

    def test_ordinary_close_needs_no_pin_once_disabled(self):
        settings_obj = ClubSettings.load()
        settings_obj.require_approval_close_game_day = False
        settings_obj.save()
        gd = services.open_game_day(202, timezone.now(), self.owner)
        closed = services.close_game_day(gd, self.cashier)  # no floor_manager_id/pin at all
        self.assertEqual(closed.status, GameDay.Status.CLOSED)
        self.assertIsNone(closed.closed_by_floor_manager)

    def test_discrepancy_close_still_requires_sign_off_even_when_disabled(self):
        """The toggle only streamlines the ROUTINE close — a chip
        discrepancy is a genuine anomaly and always needs sign-off."""
        settings_obj = ClubSettings.load()
        settings_obj.require_approval_close_game_day = False
        settings_obj.save()
        gd = services.open_game_day(203, timezone.now(), self.owner)
        player = Player.objects.create(account_code='WWI 200', display_name='Discrepancy Player')
        services.seat_player(gd, self.owner, player=player)
        services.record_transaction(
            type=Transaction.Type.CHIPS_OUT, amount=Decimal(500000), recorded_by=self.cashier,
            game_day=gd, player=player, floor_manager_id=self.fm.pk, floor_manager_pin='7777',
        )
        services.leave_table(gd, player, operator=self.cashier)  # left with chips still out — the discrepancy
        with self.assertRaises(AuthorizationError):
            services.close_game_day(gd, self.cashier, discrepancy_reason='Player walked with chips.')
        # Sign off with the FM PIN still works, exactly as before this toggle existed.
        closed = services.close_game_day(
            gd, self.cashier, floor_manager_id=self.fm.pk, floor_manager_pin='7777',
            discrepancy_reason='Player walked with chips.',
        )
        self.assertEqual(closed.status, GameDay.Status.CLOSED)

    def _open_and_seat(self, number):
        gd = services.open_game_day(number, timezone.now(), self.owner)
        player = Player.objects.create(account_code=f'WWI {number}', display_name=f'Player {number}')
        services.seat_player(gd, self.owner, player=player)
        return gd, player

    def test_payment_cash_always_requires_a_pin_regardless_of_toggles(self):
        """PAYMENT_CASH has no toggle at all — turning every other toggle
        (including issue chips) off must not affect it."""
        settings_obj = ClubSettings.load()
        settings_obj.require_approval_issue_chips = False
        settings_obj.require_approval_return_chips = False
        settings_obj.require_approval_add_tip = False
        settings_obj.require_approval_add_rake = False
        settings_obj.save()
        gd, player = self._open_and_seat(210)
        with self.assertRaises(AuthorizationError):
            services.record_transaction(
                type=Transaction.Type.PAYMENT_CASH, amount=Decimal(1000), recorded_by=self.cashier,
                game_day=gd, player=player,
            )

    def test_issue_chips_needs_no_pin_once_disabled(self):
        settings_obj = ClubSettings.load()
        settings_obj.require_approval_issue_chips = False
        settings_obj.save()
        gd, player = self._open_and_seat(214)
        txn = services.record_transaction(  # no PIN supplied at all
            type=Transaction.Type.CHIPS_OUT, amount=Decimal(50000), recorded_by=self.cashier,
            game_day=gd, player=player,
        )
        self.assertIsNotNone(txn.pk)

    def test_issue_chips_still_requires_a_pin_by_default(self):
        gd, player = self._open_and_seat(215)
        with self.assertRaises(AuthorizationError):
            services.record_transaction(
                type=Transaction.Type.CHIPS_OUT, amount=Decimal(50000), recorded_by=self.cashier,
                game_day=gd, player=player,
            )

    def test_return_chips_needs_no_pin_once_disabled(self):
        settings_obj = ClubSettings.load()
        settings_obj.require_approval_return_chips = False
        settings_obj.save()
        gd, player = self._open_and_seat(211)
        services.record_transaction(
            type=Transaction.Type.CHIPS_OUT, amount=Decimal(50000), recorded_by=self.cashier,
            game_day=gd, player=player, floor_manager_id=self.fm.pk, floor_manager_pin='7777',
        )
        txn = services.record_transaction(  # no PIN supplied at all
            type=Transaction.Type.CHIPS_IN, amount=Decimal(20000), recorded_by=self.cashier,
            game_day=gd, player=player,
        )
        self.assertIsNotNone(txn.pk)

    def test_add_tip_needs_no_pin_once_disabled(self):
        settings_obj = ClubSettings.load()
        settings_obj.require_approval_add_tip = False
        settings_obj.save()
        gd, player = self._open_and_seat(212)
        txn = services.record_transaction(
            type=Transaction.Type.TIP, amount=Decimal(5000), recorded_by=self.cashier,
            game_day=gd, tip_category=Transaction.TipCategory.SERVICE_STAFF,
        )
        self.assertIsNotNone(txn.pk)

    def test_add_rake_needs_no_pin_once_disabled(self):
        settings_obj = ClubSettings.load()
        settings_obj.require_approval_add_rake = False
        settings_obj.save()
        gd, player = self._open_and_seat(213)
        txn = services.record_transaction(
            type=Transaction.Type.RAKE, amount=Decimal(15000), recorded_by=self.cashier, game_day=gd,
        )
        self.assertIsNotNone(txn.pk)


class CashierCanInitiatePayoutToggleTests(APITestCase):
    """
    ClubSettings.cashier_can_initiate_payout (Owner-only, default True,
    added 2026-09-27) — off rejects a Cashier's call to initiate_payout
    outright, before any other check. Owner's own initiate_direct_payout
    is a separate flow, never affected.
    """

    def setUp(self):
        self.owner = StaffUser.objects.create_user(username='ccip_owner', password='x', role=StaffUser.Role.OWNER)
        self.cashier = StaffUser.objects.create_user(username='ccip_cashier', password='x', role=StaffUser.Role.CASHIER)
        self.player = Player.objects.create(account_code='CCIP 1', display_name='CCIP Player')
        PlayerBankAccount.objects.create(
            player=self.player, bank_name='GTBank', bank_code='058', account_number='0123456700',
            account_name='CCIP Player', is_default=True,
        )
        self.gd = services.open_game_day(260, timezone.now(), self.owner)
        services.seat_player(self.gd, self.owner, player=self.player)
        services.leave_table(self.gd, self.player, operator=self.cashier)
        Transaction.objects.create(
            game_day=self.gd, player=self.player, type=Transaction.Type.PAYMENT_TRANSFER, amount=Decimal(50000),
            channel=Transaction.Channel.TRANSFER_DVA,
        )

    def test_cashier_blocked_when_disabled(self):
        settings_obj = ClubSettings.load()
        settings_obj.cashier_can_initiate_payout = False
        settings_obj.save()
        with self.assertRaises(AuthorizationError):
            services.initiate_payout(self.player, Decimal(50000), self.cashier, game_day=self.gd)

    def test_cashier_allowed_by_default(self):
        _disable_payout_auto_approval()
        payout = services.initiate_payout(self.player, Decimal(50000), self.cashier, game_day=self.gd)
        self.assertIsNotNone(payout.pk)

    def test_toggle_off_does_not_affect_owner_direct_payout(self):
        settings_obj = ClubSettings.load()
        settings_obj.cashier_can_initiate_payout = False
        settings_obj.save()
        # A separate lifetime-balance credit, independent of tonight's game-day.
        Transaction.objects.create(
            game_day=None, player=self.player, type=Transaction.Type.PAYMENT_TRANSFER, amount=Decimal(10000),
            channel=Transaction.Channel.TRANSFER_DVA,
        )
        txn = services.initiate_direct_payout(self.player, Decimal(10000), self.owner)
        self.assertIsNotNone(txn.pk)


class MinimumPlayerTimeTests(APITestCase):
    """
    ClubSettings.observe_min_player_time / min_player_time_minutes (Owner-
    or-Floor-Manager-editable, off by default, added 2026-09-27) — a
    player can leave the table any time, but chips can't be RETURNED
    (CHIPS_IN) for them until min_player_time_minutes have passed since
    they were seated, unless a Floor Manager PIN overrides it.
    """

    def setUp(self):
        self.owner = StaffUser.objects.create_user(username='mpt_owner', password='x', role=StaffUser.Role.OWNER)
        self.cashier = StaffUser.objects.create_user(username='mpt_cashier', password='x', role=StaffUser.Role.CASHIER)
        self.fm = FloorManager(name='MPT Floor Boss', created_by=self.owner)
        self.fm.set_pin('9999')
        self.fm.save()
        self.gd = services.open_game_day(270, timezone.now(), self.owner)
        # Isolates the min-player-time gate from the separate, pre-existing
        # require_approval_return_chips toggle (default True — would
        # otherwise demand a PIN on every test here regardless of this
        # feature). test_one_pin_satisfies_both... turns it back on deliberately.
        settings_obj = ClubSettings.load()
        settings_obj.require_approval_return_chips = False
        settings_obj.save()

    def _seat(self, code, seated_minutes_ago):
        player = Player.objects.create(account_code=code, display_name=code)
        services.seat_player(self.gd, self.owner, player=player)
        seat = GameDayPlayer.objects.get(game_day=self.gd, player=player)
        seat.added_at = timezone.now() - timedelta(minutes=seated_minutes_ago)
        seat.save(update_fields=['added_at'])
        Transaction.objects.create(
            game_day=self.gd, player=player, type=Transaction.Type.CHIPS_OUT, amount=Decimal(100000),
            channel=Transaction.Channel.CASHIER, recorded_by=self.cashier,
        )
        return player

    def test_off_by_default_no_gate_at_all(self):
        player = self._seat('MPT 1', seated_minutes_ago=1)  # just sat down
        txn = services.record_transaction(  # no PIN supplied — off means off
            type=Transaction.Type.CHIPS_IN, amount=Decimal(50000), recorded_by=self.cashier,
            game_day=self.gd, player=player,
        )
        self.assertIsNotNone(txn.pk)

    def test_blocked_before_minimum_time_without_a_pin(self):
        settings_obj = ClubSettings.load()
        settings_obj.observe_min_player_time = True
        settings_obj.min_player_time_minutes = 240
        settings_obj.save()
        player = self._seat('MPT 2', seated_minutes_ago=30)  # well under 240
        with self.assertRaises(AuthorizationError):
            services.record_transaction(
                type=Transaction.Type.CHIPS_IN, amount=Decimal(50000), recorded_by=self.cashier,
                game_day=self.gd, player=player,
            )

    def test_floor_manager_pin_overrides_it(self):
        settings_obj = ClubSettings.load()
        settings_obj.observe_min_player_time = True
        settings_obj.min_player_time_minutes = 240
        settings_obj.save()
        player = self._seat('MPT 3', seated_minutes_ago=30)
        txn = services.record_transaction(
            type=Transaction.Type.CHIPS_IN, amount=Decimal(50000), recorded_by=self.cashier,
            game_day=self.gd, player=player, floor_manager_id=self.fm.pk, floor_manager_pin='9999',
        )
        self.assertIsNotNone(txn.pk)
        self.assertEqual(txn.floor_manager, self.fm)

    def test_allowed_once_minimum_time_has_elapsed(self):
        settings_obj = ClubSettings.load()
        settings_obj.observe_min_player_time = True
        settings_obj.min_player_time_minutes = 240
        settings_obj.save()
        player = self._seat('MPT 4', seated_minutes_ago=241)  # just over the line
        txn = services.record_transaction(  # no PIN supplied
            type=Transaction.Type.CHIPS_IN, amount=Decimal(50000), recorded_by=self.cashier,
            game_day=self.gd, player=player,
        )
        self.assertIsNotNone(txn.pk)

    def test_one_pin_satisfies_both_the_general_toggle_and_the_time_override(self):
        """When require_approval_return_chips is ALSO on, the same single PIN
        covers both requirements — no second prompt."""
        settings_obj = ClubSettings.load()
        settings_obj.observe_min_player_time = True
        settings_obj.min_player_time_minutes = 240
        settings_obj.require_approval_return_chips = True
        settings_obj.save()
        player = self._seat('MPT 5', seated_minutes_ago=30)
        txn = services.record_transaction(
            type=Transaction.Type.CHIPS_IN, amount=Decimal(50000), recorded_by=self.cashier,
            game_day=self.gd, player=player, floor_manager_id=self.fm.pk, floor_manager_pin='9999',
        )
        self.assertIsNotNone(txn.pk)

    def test_leaving_the_table_has_no_time_gate_at_all(self):
        settings_obj = ClubSettings.load()
        settings_obj.observe_min_player_time = True
        settings_obj.min_player_time_minutes = 240
        settings_obj.save()
        player = self._seat('MPT 6', seated_minutes_ago=1)
        seat = services.leave_table(self.gd, player, operator=self.cashier)  # should not raise
        self.assertIsNotNone(seat.left_at)

    def test_api_response_flags_requires_floor_manager_pin(self):
        """The frontend needs to tell this apart from any other 403 without
        string-matching the message — see TransactionEntryModal.vue's onSubmit."""
        settings_obj = ClubSettings.load()
        settings_obj.observe_min_player_time = True
        settings_obj.min_player_time_minutes = 240
        settings_obj.save()
        player = self._seat('MPT 7', seated_minutes_ago=5)
        self.client.force_authenticate(self.cashier)
        response = self.client.post('/api/transactions/', {
            'type': 'CHIPS_IN', 'amount': '10000', 'game_day': self.gd.id, 'player': player.id,
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(response.data['requires_floor_manager_pin'])


class MaxChipsIssuablePerTableTests(APITestCase):
    """
    Table.max_chips_issuable (added 2026-09-23, corrected same day) — a
    ceiling on any ONE issuance, not a running/cumulative total: a player
    can buy in at the cap as many times as they like over the night, and
    there's no limit at all on total chips outstanding at once. See
    record_transaction's CHIPS_OUT branch.
    """

    def setUp(self):
        self.owner = StaffUser.objects.create_user(username='mcit_owner', password='x', role=StaffUser.Role.OWNER)
        self.cashier = StaffUser.objects.create_user(username='mcit_cashier', password='x', role=StaffUser.Role.CASHIER)
        self.fm = FloorManager(name='MCIT Floor Boss', created_by=self.owner)
        self.fm.set_pin('3333')
        self.fm.save()
        self.game = Game.objects.create(name='Test Game — Max Chips')
        self.table = Table.objects.create(
            game=self.game, name='Capped Table', default_buy_in=Decimal(100000),
            max_chips_issuable=Decimal(300000),
        )
        # buy_in_amount=0 (falsy) — otherwise seat_player's own auto buy-in
        # (see its docstring) would issue the table's default_buy_in to
        # each seated player below, throwing off this test's own amounts.
        self.game_day = services.open_game_day(
            220, timezone.now(), self.owner, game=self.game, table=self.table, buy_in_amount=Decimal(0),
        )
        self.p1 = Player.objects.create(account_code='WWI 220', display_name='Capped Player One')
        self.p2 = Player.objects.create(account_code='WWI 221', display_name='Capped Player Two')
        services.seat_player(self.game_day, self.owner, player=self.p1)
        services.seat_player(self.game_day, self.owner, player=self.p2)

    def _chips_out(self, player, amount):
        return services.record_transaction(
            type=Transaction.Type.CHIPS_OUT, amount=Decimal(amount), recorded_by=self.cashier,
            game_day=self.game_day, player=player, floor_manager_id=self.fm.pk, floor_manager_pin='3333',
        )

    def test_issuing_up_to_the_cap_in_one_go_is_allowed(self):
        self._chips_out(self.p1, 300000)  # exact cap — allowed

    def test_issuing_beyond_the_cap_in_one_go_raises(self):
        with self.assertRaises(InvalidStateError):
            self._chips_out(self.p1, 300001)

    def test_multiple_buy_ins_at_the_cap_are_each_allowed_no_running_total(self):
        """There is no limit on total chips outstanding at once — only on
        the size of any single issuance."""
        self._chips_out(self.p1, 300000)
        self._chips_out(self.p1, 300000)  # a second buy-in at the same player, still fine
        self._chips_out(self.p2, 300000)  # and a different player, also fine

    def test_a_table_with_no_cap_set_is_unaffected(self):
        uncapped = Table.objects.create(
            game=self.game, name='Uncapped Table', default_buy_in=Decimal(100000),
        )
        gd = services.open_game_day(221, timezone.now(), self.owner, game=self.game, table=uncapped)
        player = Player.objects.create(account_code='WWI 222', display_name='Uncapped Player')
        services.seat_player(gd, self.owner, player=player)
        services.record_transaction(
            type=Transaction.Type.CHIPS_OUT, amount=Decimal(5000000), recorded_by=self.cashier,
            game_day=gd, player=player, floor_manager_id=self.fm.pk, floor_manager_pin='3333',
        )  # far beyond the OTHER table's cap — should not raise, this table has none

    def test_error_message_reports_the_requested_amount_and_the_cap(self):
        with self.assertRaises(InvalidStateError) as ctx:
            self._chips_out(self.p1, 300001)
        message = str(ctx.exception)
        self.assertIn('300,001', message)
        self.assertIn('300,000', message)


class TableMaxPlayersOverrideTests(TestCase):
    """selectors.max_active_players' table-first tier (added 2026-09-23)."""

    def setUp(self):
        self.owner = StaffUser.objects.create_user(username='tmp_owner', password='x', role=StaffUser.Role.OWNER)
        self.game = Game.objects.create(name='Test Game — Max Players', max_players=9)

    def test_table_override_wins_over_the_games_value(self):
        table = Table.objects.create(
            game=self.game, name='Small Table', default_buy_in=Decimal(100000), max_players=4,
        )
        gd = services.open_game_day(230, timezone.now(), self.owner, game=self.game, table=table)
        self.assertEqual(selectors.max_active_players(gd), 4)

    def test_null_table_override_falls_back_to_the_game(self):
        table = Table.objects.create(game=self.game, name='Default Table', default_buy_in=Decimal(100000))
        gd = services.open_game_day(231, timezone.now(), self.owner, game=self.game, table=table)
        self.assertEqual(selectors.max_active_players(gd), 9)


class PayoutAutoApprovalThresholdTests(APITestCase):
    """
    ClubSettings.payout_auto_approve_threshold (added 2026-09-23, default
    ₦500,000) — a payout at or under it skips PENDING_APPROVAL entirely.
    See gaming.services.initiate_payout/_execute_payout_transfer.
    """

    def setUp(self):
        self.owner = StaffUser.objects.create_user(username='paat_owner', password='x', role=StaffUser.Role.OWNER)
        self.cashier = StaffUser.objects.create_user(username='paat_cashier', password='x', role=StaffUser.Role.CASHIER)
        self.game_day = services.open_game_day(240, timezone.now(), self.owner)

    def _winning_player(self, code, winnings):
        player = Player.objects.create(account_code=code, display_name=code)
        PlayerBankAccount.objects.create(
            player=player, bank_name='GTBank', bank_code='058', account_number='0123456789',
            account_name=code, is_default=True,
        )
        services.seat_player(self.game_day, self.owner, player=player)
        services.leave_table(self.game_day, player, operator=self.cashier)
        # Funds the Main Account too (TRANSFER_DVA), so the funds guard inside
        # _execute_payout_transfer doesn't get in the way of this test.
        Transaction.objects.create(
            game_day=self.game_day, player=player, type=Transaction.Type.PAYMENT_TRANSFER, amount=Decimal(winnings),
            channel=Transaction.Channel.TRANSFER_DVA,
        )
        return player

    @patch('payments.paystack_client.initiate_transfer', return_value={'transfer_code': 'TRF_auto'})
    @patch('payments.paystack_client.create_transfer_recipient', return_value={'recipient_code': 'RCP_auto'})
    def test_at_or_under_threshold_auto_approves(self, mock_recipient, mock_transfer):
        player = self._winning_player('WWI 240', 500000)
        payout = services.initiate_payout(player, Decimal(500000), self.cashier, game_day=self.game_day)
        self.assertEqual(payout.status, Transaction.Status.APPROVED)
        self.assertIsNone(payout.approved_by)
        self.assertIsNotNone(payout.approved_at)
        self.assertEqual(payout.external_reference, 'TRF_auto')

    def test_over_threshold_stays_pending(self):
        player = self._winning_player('WWI 241', 500001)
        payout = services.initiate_payout(player, Decimal(500001), self.cashier, game_day=self.game_day)
        self.assertEqual(payout.status, Transaction.Status.PENDING_APPROVAL)
        self.assertIsNone(payout.approved_by)

    @patch('payments.paystack_client.initiate_transfer', return_value={'transfer_code': 'TRF_custom'})
    @patch('payments.paystack_client.create_transfer_recipient', return_value={'recipient_code': 'RCP_custom'})
    def test_owner_can_lower_the_threshold(self, mock_recipient, mock_transfer):
        settings_obj = ClubSettings.load()
        settings_obj.payout_auto_approve_threshold = Decimal('10000')
        settings_obj.save()
        player = self._winning_player('WWI 242', 10000)
        payout = services.initiate_payout(player, Decimal(10000), self.cashier, game_day=self.game_day)
        self.assertEqual(payout.status, Transaction.Status.APPROVED)

        other = self._winning_player('WWI 243', 10001)
        other_payout = services.initiate_payout(other, Decimal(10001), self.cashier, game_day=self.game_day)
        self.assertEqual(other_payout.status, Transaction.Status.PENDING_APPROVAL)


class PayoutNettingAgainstPriorDebtTests(APITestCase):
    """
    services.initiate_payout automatically netting against a player's prior
    outstanding (lifetime) balance — added 2026-09-27. See initiate_payout's
    own docstring for the full reasoning; this is the exact scenario that
    motivated it: a player owes the house from an earlier game-day, the
    Cashier only ever sees tonight's own winnings, and the actual bank
    transfer must not exceed what's left once the old debt is accounted for.
    """

    def setUp(self):
        self.owner = StaffUser.objects.create_user(username='pnd_owner', password='x', role=StaffUser.Role.OWNER)
        self.cashier = StaffUser.objects.create_user(username='pnd_cashier', password='x', role=StaffUser.Role.CASHIER)
        self.player = Player.objects.create(account_code='WWI 250', display_name='Netting Player')
        PlayerBankAccount.objects.create(
            player=self.player, bank_name='GTBank', bank_code='058', account_number='0123456789',
            account_name='Netting Player', is_default=True,
        )
        # A prior, already-closed game-day the player owes ₦600,000 from —
        # chips issued, never returned. Not closed via services.close_game_day
        # (irrelevant to this feature — player_balance doesn't care about
        # GameDay.status, only Transaction rows), so no FM sign-off needed here.
        old_gd = services.open_game_day(250, timezone.now() - timedelta(days=7), self.owner)
        services.seat_player(old_gd, self.owner, player=self.player)
        Transaction.objects.create(
            game_day=old_gd, player=self.player, type=Transaction.Type.CHIPS_OUT, amount=Decimal(600000),
            channel=Transaction.Channel.CASHIER, recorded_by=self.cashier,
        )
        self.assertEqual(selectors.player_balance(self.player), Decimal(-600000))

        # Tonight's game-day — the player wins ₦1,000,000, funding both their
        # own game-day balance AND the Main Account (TRANSFER_DVA) so the
        # payout's own funds guard never blocks these tests.
        self.game_day = services.open_game_day(251, timezone.now(), self.owner)
        services.seat_player(self.game_day, self.owner, player=self.player)
        services.leave_table(self.game_day, self.player, operator=self.cashier)
        Transaction.objects.create(
            game_day=self.game_day, player=self.player, type=Transaction.Type.PAYMENT_TRANSFER, amount=Decimal(1000000),
            channel=Transaction.Channel.TRANSFER_DVA,
        )

    @patch('payments.paystack_client.initiate_transfer', return_value={'transfer_code': 'TRF_net'})
    @patch('payments.paystack_client.create_transfer_recipient', return_value={'recipient_code': 'RCP_net'})
    def test_payout_nets_against_prior_debt_and_auto_approves_under_threshold(self, mock_recipient, mock_transfer):
        # Lifetime balance going in: -600,000 + 1,000,000 = 400,000 — under
        # the default ₦500,000 threshold, so despite the Cashier asking for
        # the full 1,000,000, this should auto-approve at the netted figure.
        payout = services.initiate_payout(self.player, Decimal(1000000), self.cashier, game_day=self.game_day)
        self.assertEqual(payout.amount, Decimal(400000))
        self.assertEqual(payout.requested_amount, Decimal(1000000))
        self.assertEqual(payout.status, Transaction.Status.APPROVED)
        self.assertIsNone(payout.approved_by)  # auto-approved, not manually signed off
        self.assertIn('600,000', payout.notes)
        self.assertIn('400,000', payout.notes)
        # The old debt is now fully cleared — lifetime balance nets to zero
        # once the actual (netted) payout amount is debited.
        self.assertEqual(selectors.player_balance(self.player), Decimal(0))

    def test_net_amount_over_threshold_requires_approval_for_the_net_only(self):
        # A smaller prior debt (₦200,000) leaves a ₦800,000 net — over the
        # default threshold, so this should land PENDING_APPROVAL, and
        # specifically at the netted 800,000, not the requested 1,000,000.
        player2 = Player.objects.create(account_code='WWI 252', display_name='Netting Player 2')
        PlayerBankAccount.objects.create(
            player=player2, bank_name='GTBank', bank_code='058', account_number='0123456780',
            account_name='Netting Player 2', is_default=True,
        )
        old_gd = services.open_game_day(253, timezone.now() - timedelta(days=7), self.owner)
        services.seat_player(old_gd, self.owner, player=player2)
        Transaction.objects.create(
            game_day=old_gd, player=player2, type=Transaction.Type.CHIPS_OUT, amount=Decimal(200000),
            channel=Transaction.Channel.CASHIER, recorded_by=self.cashier,
        )
        services.seat_player(self.game_day, self.owner, player=player2)
        services.leave_table(self.game_day, player2, operator=self.cashier)
        Transaction.objects.create(
            game_day=self.game_day, player=player2, type=Transaction.Type.PAYMENT_TRANSFER, amount=Decimal(1000000),
            channel=Transaction.Channel.TRANSFER_DVA,
        )

        payout = services.initiate_payout(player2, Decimal(1000000), self.cashier, game_day=self.game_day)
        self.assertEqual(payout.amount, Decimal(800000))
        self.assertEqual(payout.requested_amount, Decimal(1000000))
        self.assertEqual(payout.status, Transaction.Status.PENDING_APPROVAL)

    def test_debt_larger_than_winnings_records_a_zero_payout_capped_at_the_request(self):
        # Revised 2026-09-27 — a player whose prior debt is larger than what
        # they won tonight has nothing PAYABLE, but this is no longer a
        # silent no-op: a ₦0 payout is still recorded (settled immediately,
        # no real transfer attempted), with requested_amount preserved so
        # the "Payout BBF" ledger line has something to attach to. Per
        # explicit follow-up, the BBF/cleared figure is capped at what was
        # actually REQUESTED (₦1,000,000), never the full prior debt
        # (₦1,200,000) even though it's larger.
        player3 = Player.objects.create(account_code='WWI 254', display_name='Netting Player 3')
        PlayerBankAccount.objects.create(
            player=player3, bank_name='GTBank', bank_code='058', account_number='0123456781',
            account_name='Netting Player 3', is_default=True,
        )
        old_gd = services.open_game_day(255, timezone.now() - timedelta(days=7), self.owner)
        services.seat_player(old_gd, self.owner, player=player3)
        Transaction.objects.create(
            game_day=old_gd, player=player3, type=Transaction.Type.CHIPS_OUT, amount=Decimal(1200000),
            channel=Transaction.Channel.CASHIER, recorded_by=self.cashier,
        )
        services.seat_player(self.game_day, self.owner, player=player3)
        services.leave_table(self.game_day, player3, operator=self.cashier)
        Transaction.objects.create(
            game_day=self.game_day, player=player3, type=Transaction.Type.PAYMENT_TRANSFER, amount=Decimal(1000000),
            channel=Transaction.Channel.TRANSFER_DVA,
        )

        payout = services.initiate_payout(player3, Decimal(1000000), self.cashier, game_day=self.game_day)
        self.assertEqual(payout.amount, Decimal(0))
        self.assertEqual(payout.requested_amount, Decimal(1000000))  # capped at the request, not the 1,200,000 debt
        self.assertEqual(payout.status, Transaction.Status.APPROVED)
        self.assertIsNone(payout.approved_by)
        # The 1,200,000 debt isn't fully cleared by this — only 1,000,000 of
        # it (what was actually available) is accounted for; 200,000 stays
        # outstanding, same as it was before this payout was attempted.
        self.assertEqual(selectors.player_balance(player3), Decimal(-200000))

    def test_no_prior_debt_leaves_amount_and_requested_amount_unaffected(self):
        # Baseline regression: with no prior debt, requested_amount stays
        # unset and amount equals exactly what was requested — same as
        # before this feature existed.
        player4 = Player.objects.create(account_code='WWI 256', display_name='Netting Player 4')
        PlayerBankAccount.objects.create(
            player=player4, bank_name='GTBank', bank_code='058', account_number='0123456782',
            account_name='Netting Player 4', is_default=True,
        )
        # Kept above the auto-approval threshold so this stays PENDING_APPROVAL
        # without attempting (and failing) a real Paystack transfer — this
        # test only cares about the amount/requested_amount/notes fields, not
        # the transfer outcome, which is exercised elsewhere.
        services.seat_player(self.game_day, self.owner, player=player4)
        services.leave_table(self.game_day, player4, operator=self.cashier)
        Transaction.objects.create(
            game_day=self.game_day, player=player4, type=Transaction.Type.PAYMENT_TRANSFER, amount=Decimal(600000),
            channel=Transaction.Channel.TRANSFER_DVA,
        )
        payout = services.initiate_payout(player4, Decimal(600000), self.cashier, game_day=self.game_day)
        self.assertEqual(payout.amount, Decimal(600000))
        self.assertIsNone(payout.requested_amount)
        self.assertEqual(payout.notes, '')
        self.assertEqual(payout.status, Transaction.Status.PENDING_APPROVAL)


class DirectPayoutTests(APITestCase):
    """
    services.initiate_direct_payout + POST /api/transactions/direct-payout/
    (added 2026-09-24) — the Owner-initiated payout of a player's LIFETIME
    balance from the Players page, with no game-day involved at all. See
    PayoutAutoApprovalThresholdTests above for the game-day-scoped
    equivalent this deliberately does not touch.
    """

    def setUp(self):
        self.owner = StaffUser.objects.create_user(username='dp_owner', password='x', role=StaffUser.Role.OWNER)
        self.accountant = StaffUser.objects.create_user(username='dp_acct', password='x', role=StaffUser.Role.ACCOUNTANT)
        self.player = Player.objects.create(account_code='DP 1', display_name='Direct Payout Player')
        PlayerBankAccount.objects.create(
            player=self.player, bank_name='GTBank', bank_code='058', account_number='0123456789',
            account_name='Direct Payout Player', is_default=True,
        )
        # A credit with no game_day at all — an "owed outside any game-day"
        # balance, same shape as a Deal or a carried-over Outstanding figure.
        Transaction.objects.create(
            game_day=None, player=self.player, type=Transaction.Type.PAYMENT_TRANSFER, amount=Decimal(200000),
            channel=Transaction.Channel.TRANSFER_DVA,
        )

    def test_requires_no_game_day_at_all(self):
        # No game-day ever opened in this test — proves this path doesn't
        # need one, unlike initiate_payout.
        self.assertIsNone(GameDay.objects.filter(seated_players__player=self.player).first())
        txn = services.initiate_direct_payout(self.player, Decimal(50000), self.owner)
        self.assertIsNone(txn.game_day)
        self.assertEqual(txn.player, self.player)

    def test_capped_at_lifetime_balance_not_more(self):
        with self.assertRaises(InvalidStateError):
            services.initiate_direct_payout(self.player, Decimal(200001), self.owner)

    def test_owner_can_pay_out_less_than_the_full_balance(self):
        txn = services.initiate_direct_payout(self.player, Decimal(1000), self.owner)
        self.assertEqual(txn.amount, Decimal(1000))

    def test_blocked_without_a_bank_account(self):
        no_bank_player = Player.objects.create(account_code='DP 2', display_name='No Bank Player')
        Transaction.objects.create(
            game_day=None, player=no_bank_player, type=Transaction.Type.PAYMENT_TRANSFER, amount=Decimal(50000),
            channel=Transaction.Channel.TRANSFER_DVA,
        )
        with self.assertRaises(InvalidStateError):
            services.initiate_direct_payout(no_bank_player, Decimal(10000), self.owner)

    @patch('payments.paystack_client.initiate_transfer', return_value={'transfer_code': 'TRF_direct'})
    @patch('payments.paystack_client.create_transfer_recipient', return_value={'recipient_code': 'RCP_direct'})
    def test_at_or_under_threshold_auto_approves_via_api(self, mock_recipient, mock_transfer):
        self.client.force_authenticate(self.owner)
        response = self.client.post(
            '/api/transactions/direct-payout/', {'player': self.player.id, 'amount': '50000'},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['status'], 'APPROVED')

    def test_non_owner_cannot_initiate_a_direct_payout(self):
        self.client.force_authenticate(self.accountant)
        response = self.client.post(
            '/api/transactions/direct-payout/', {'player': self.player.id, 'amount': '1000'},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class GameDaysForPlayerFilterTests(APITestCase):
    """GET /api/game-days/?player=<id> (added 2026-09-24) — only game-days that player was actually seated in."""

    def setUp(self):
        self.owner = StaffUser.objects.create_user(username='gdfp_owner', password='x', role=StaffUser.Role.OWNER)
        self.player = Player.objects.create(account_code='GDFP 1', display_name='Seated Player')
        self.other_player = Player.objects.create(account_code='GDFP 2', display_name='Other Player')
        self.seated_gd = services.open_game_day(310, timezone.now(), self.owner)
        services.seat_player(self.seated_gd, self.owner, player=self.player)
        self.unrelated_gd = services.open_game_day(311, timezone.now(), self.owner)
        services.seat_player(self.unrelated_gd, self.owner, player=self.other_player)

    def test_filters_to_only_game_days_the_player_played_in(self):
        self.client.force_authenticate(self.owner)
        response = self.client.get(f'/api/game-days/?player={self.player.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {gd['id'] for gd in response.data}
        self.assertEqual(ids, {self.seated_gd.id})

    def test_unfiltered_without_the_param_returns_everything(self):
        self.client.force_authenticate(self.owner)
        response = self.client.get('/api/game-days/')
        ids = {gd['id'] for gd in response.data}
        self.assertIn(self.seated_gd.id, ids)
        self.assertIn(self.unrelated_gd.id, ids)

    def test_status_filter_finds_multiple_concurrently_open_game_days(self):
        """?status=OPEN (added 2026-09-26) for the Owner Dashboard's live-tables summary."""
        settings_obj = ClubSettings.load()
        settings_obj.require_approval_close_game_day = False
        settings_obj.save()
        closed_gd = services.open_game_day(312, timezone.now(), self.owner)
        services.close_game_day(closed_gd, self.owner)

        self.client.force_authenticate(self.owner)
        response = self.client.get('/api/game-days/?status=OPEN')
        ids = {gd['id'] for gd in response.data}
        # seated_gd and unrelated_gd are BOTH still open by construction —
        # nothing stops two tables running concurrently — closed_gd is not.
        self.assertEqual(ids, {self.seated_gd.id, self.unrelated_gd.id})
        self.assertNotIn(closed_gd.id, ids)


class ClubSettingsAndTablePermissionsAPITests(APITestCase):
    """
    ClubSettingsView (everyone reads; writes are Owner-only except the 4
    fields in FLOOR_MANAGER_EDITABLE_FIELDS, added 2026-09-27 — see that
    class) and TableViewSet's write half (Owner-or-Floor-Manager, added
    2026-09-23 for the "Settings" screen).
    """

    def setUp(self):
        self.owner = StaffUser.objects.create_user(username='csp_owner', password='x', role=StaffUser.Role.OWNER)
        self.fm_user = StaffUser.objects.create_user(username='csp_fm', password='x', role=StaffUser.Role.FLOOR_MANAGER)
        self.cashier = StaffUser.objects.create_user(username='csp_cashier', password='x', role=StaffUser.Role.CASHIER)
        self.game = Game.objects.create(name='Test Game — Settings Perms')
        self.table = Table.objects.create(game=self.game, name='Perms Table', default_buy_in=Decimal(100000))

    def test_any_authenticated_role_can_read_club_settings(self):
        self.client.force_authenticate(self.cashier)
        response = self.client.get('/api/club-settings/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('payout_auto_approve_threshold', response.data)

    def test_owner_dashboard_game_day_widget_defaults_off_and_owner_can_enable_it(self):
        self.client.force_authenticate(self.cashier)
        response = self.client.get('/api/club-settings/')
        self.assertFalse(response.data['owner_dashboard_game_day_enabled'])

        self.client.force_authenticate(self.owner)
        response = self.client.patch('/api/club-settings/', {'owner_dashboard_game_day_enabled': True})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(ClubSettings.load().owner_dashboard_game_day_enabled)

    def test_only_owner_can_write_club_settings(self):
        self.client.force_authenticate(self.fm_user)
        response = self.client.patch('/api/club-settings/', {'require_approval_open_game_day': False})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.owner)
        response = self.client.patch('/api/club-settings/', {'require_approval_open_game_day': False})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(ClubSettings.load().require_approval_open_game_day)

    def test_cashier_cannot_write_club_settings_at_all(self):
        self.client.force_authenticate(self.cashier)
        response = self.client.patch('/api/club-settings/', {'observe_min_player_time': True})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_floor_manager_can_write_min_player_time_and_track_away_fields(self):
        self.client.force_authenticate(self.fm_user)
        response = self.client.patch('/api/club-settings/', {
            'observe_min_player_time': True, 'min_player_time_minutes': 90,
            'track_away_from_table': True, 'away_max_minutes': 15,
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        obj = ClubSettings.load()
        self.assertTrue(obj.observe_min_player_time)
        self.assertEqual(obj.min_player_time_minutes, 90)
        self.assertTrue(obj.track_away_from_table)
        self.assertEqual(obj.away_max_minutes, 15)

    def test_floor_manager_cannot_write_owner_only_fields(self):
        self.client.force_authenticate(self.fm_user)
        response = self.client.patch('/api/club-settings/', {'cashier_can_initiate_payout': False})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(ClubSettings.load().cashier_can_initiate_payout)  # unchanged

    def test_floor_manager_cannot_mix_an_owner_only_field_into_an_otherwise_allowed_request(self):
        self.client.force_authenticate(self.fm_user)
        response = self.client.patch('/api/club-settings/', {
            'observe_min_player_time': True, 'require_approval_open_game_day': False,
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(ClubSettings.load().observe_min_player_time)  # neither field was written

    def test_owner_can_write_every_field_including_floor_manager_ones(self):
        self.client.force_authenticate(self.owner)
        response = self.client.patch('/api/club-settings/', {
            'cashier_can_initiate_payout': False, 'observe_min_player_time': True,
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        obj = ClubSettings.load()
        self.assertFalse(obj.cashier_can_initiate_payout)
        self.assertTrue(obj.observe_min_player_time)

    def test_min_player_time_minutes_rejects_sub_30_and_non_increments(self):
        self.client.force_authenticate(self.owner)
        for bad_value in (0, 15, 45, 100):
            response = self.client.patch('/api/club-settings/', {'min_player_time_minutes': bad_value})
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, bad_value)
        response = self.client.patch('/api/club-settings/', {'min_player_time_minutes': 90})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_floor_manager_and_owner_can_edit_a_table(self):
        for user in (self.fm_user, self.owner):
            self.client.force_authenticate(user)
            response = self.client.patch(f'/api/tables/{self.table.id}/', {'default_buy_in': '150000'})
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_cashier_cannot_edit_a_table(self):
        self.client.force_authenticate(self.cashier)
        response = self.client.patch(f'/api/tables/{self.table.id}/', {'default_buy_in': '150000'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_table_identity_fields_stay_locked(self):
        self.client.force_authenticate(self.owner)
        response = self.client.patch(f'/api/tables/{self.table.id}/', {'name': 'Renamed Table'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.table.refresh_from_db()
        self.assertEqual(self.table.name, 'Perms Table')  # read_only_fields silently ignores it, not rejects
