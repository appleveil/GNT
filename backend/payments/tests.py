import hashlib
import hmac
import json
from unittest.mock import patch

from django.test import override_settings
from rest_framework import status

from lpc_backend.testing import APITestCase, TestCase

from accounts.models import Player, StaffUser
from gaming.models import Transaction

from . import paystack_client, services
from .models import DedicatedVirtualAccount, PaystackAccount
from .paystack_client import PaystackAPIError, PaystackNotConfiguredError

TEST_SECRET = 'test-paystack-secret'


def _signed_payload(body: dict):
    raw = json.dumps(body).encode('utf-8')
    signature = hmac.new(TEST_SECRET.encode('utf-8'), raw, digestmod=hashlib.sha512).hexdigest()
    return raw, signature


def _dva_deposit_payload(reference='DVA_ref_abc123', customer_code='CUS_test123', amount=100000):
    return {
        'event': 'charge.success',
        'data': {
            'id': 98765432,
            'reference': reference,
            'amount': amount,  # kobo
            'currency': 'NGN',
            'channel': 'dedicated_nuban',
            'customer': {'email': 'amina@example.com', 'customer_code': customer_code},
            'authorization': {
                'sender_name': 'JOHN DOE', 'sender_bank': 'First Bank', 'sender_bank_account_number': '0123456789',
            },
        },
    }


@override_settings(PAYSTACK_SECRET_KEY=TEST_SECRET)
class SignatureVerificationTests(TestCase):
    def test_valid_signature_accepted(self):
        raw, signature = _signed_payload({'event': 'charge.success'})
        self.assertTrue(services.verify_signature(raw, signature))

    def test_wrong_signature_rejected(self):
        raw, _ = _signed_payload({'event': 'charge.success'})
        self.assertFalse(services.verify_signature(raw, 'not-the-real-signature'))

    def test_missing_signature_rejected(self):
        raw, _ = _signed_payload({'event': 'charge.success'})
        self.assertFalse(services.verify_signature(raw, ''))


@override_settings(PAYSTACK_SECRET_KEY=TEST_SECRET)
class HandleChargeSuccessTests(TestCase):
    def setUp(self):
        self.player = Player.objects.create(account_code='WWI 1', display_name='Amina')
        self.paystack_account = PaystackAccount.objects.create(
            account_type=PaystackAccount.AccountType.GAMING, player=self.player,
            paystack_customer_code='CUS_test123', label='Amina GA',
        )

    def test_creates_payment_transfer_transaction(self):
        payload = _dva_deposit_payload(amount=150000)
        txn = services.handle_charge_success(payload['data'])
        self.assertIsNotNone(txn)
        self.assertEqual(txn.type, Transaction.Type.PAYMENT_TRANSFER)
        self.assertEqual(txn.player, self.player)
        self.assertEqual(txn.amount, 1500)  # 150000 kobo -> 1500 naira
        self.assertEqual(txn.external_reference, 'DVA_ref_abc123')
        self.assertIsNone(txn.recorded_by)  # webhook-captured, not staff-entered

    def test_replaying_same_reference_is_a_noop(self):
        payload = _dva_deposit_payload()
        services.handle_charge_success(payload['data'])
        result = services.handle_charge_success(payload['data'])
        self.assertIsNone(result)
        self.assertEqual(Transaction.objects.filter(external_reference='DVA_ref_abc123').count(), 1)

    def test_non_dva_channel_ignored(self):
        payload = _dva_deposit_payload()
        payload['data']['channel'] = 'card'
        result = services.handle_charge_success(payload['data'])
        self.assertIsNone(result)
        self.assertEqual(Transaction.objects.count(), 0)

    def test_unrecognized_customer_raises(self):
        payload = _dva_deposit_payload(customer_code='CUS_unknown')
        with self.assertRaises(services.UnrecognizedAccountError):
            services.handle_charge_success(payload['data'])


@override_settings(PAYSTACK_SECRET_KEY=TEST_SECRET)
class PaystackWebhookViewTests(APITestCase):
    def setUp(self):
        self.player = Player.objects.create(account_code='WWI 2', display_name='Moses')
        PaystackAccount.objects.create(
            account_type=PaystackAccount.AccountType.GAMING, player=self.player,
            paystack_customer_code='CUS_test456', label='Moses GA',
        )

    def test_valid_webhook_creates_transaction(self):
        payload = _dva_deposit_payload(reference='ref_1', customer_code='CUS_test456')
        raw, signature = _signed_payload(payload)
        response = self.client.post(
            '/api/webhooks/paystack/', data=raw, content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE=signature,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Transaction.objects.filter(external_reference='ref_1').exists())

    def test_invalid_signature_rejected(self):
        payload = _dva_deposit_payload(reference='ref_2', customer_code='CUS_test456')
        raw, _ = _signed_payload(payload)
        response = self.client.post(
            '/api/webhooks/paystack/', data=raw, content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE='bogus',
        )
        self.assertEqual(response.status_code, 401)
        self.assertFalse(Transaction.objects.filter(external_reference='ref_2').exists())

    def test_replayed_webhook_does_not_duplicate(self):
        payload = _dva_deposit_payload(reference='ref_3', customer_code='CUS_test456')
        raw, signature = _signed_payload(payload)
        for _ in range(2):
            response = self.client.post(
                '/api/webhooks/paystack/', data=raw, content_type='application/json',
                HTTP_X_PAYSTACK_SIGNATURE=signature,
            )
            self.assertEqual(response.status_code, 200)
        self.assertEqual(Transaction.objects.filter(external_reference='ref_3').count(), 1)

    def test_unrecognized_account_still_returns_200(self):
        payload = _dva_deposit_payload(reference='ref_4', customer_code='CUS_does_not_exist')
        raw, signature = _signed_payload(payload)
        response = self.client.post(
            '/api/webhooks/paystack/', data=raw, content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE=signature,
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class PaystackClientTests(TestCase):
    """paystack_client._request, exercised via its public wrapper functions."""

    def test_raises_when_not_configured(self):
        with override_settings(PAYSTACK_SECRET_KEY=''):
            with self.assertRaises(PaystackNotConfiguredError):
                paystack_client.create_customer('a@example.com', 'A', 'B')

    @override_settings(PAYSTACK_SECRET_KEY=TEST_SECRET)
    @patch('requests.request')
    def test_raises_on_paystack_error_response(self, mock_request):
        mock_request.return_value.ok = False
        mock_request.return_value.status_code = 400
        mock_request.return_value.json.return_value = {'status': False, 'message': 'Invalid email'}
        with self.assertRaises(PaystackAPIError) as ctx:
            paystack_client.create_customer('bad', 'A', 'B')
        self.assertIn('Invalid email', str(ctx.exception))

    @override_settings(PAYSTACK_SECRET_KEY=TEST_SECRET)
    @patch('requests.request')
    def test_returns_data_on_success(self, mock_request):
        mock_request.return_value.ok = True
        mock_request.return_value.status_code = 200
        mock_request.return_value.json.return_value = {'status': True, 'data': {'customer_code': 'CUS_1'}}
        result = paystack_client.create_customer('a@example.com', 'A', 'B')
        self.assertEqual(result, {'customer_code': 'CUS_1'})


@override_settings(PAYSTACK_SECRET_KEY=TEST_SECRET)
class ProvisionGamingAccountTests(TestCase):
    def setUp(self):
        self.player = Player.objects.create(account_code='WWI 20', display_name='Tunde Test')

    @patch('payments.paystack_client.create_dedicated_account')
    @patch('payments.paystack_client.create_customer')
    def test_provisions_customer_and_dva(self, mock_create_customer, mock_create_dva):
        mock_create_customer.return_value = {'customer_code': 'CUS_new'}
        mock_create_dva.return_value = {
            'id': 555, 'account_number': '9990001111', 'account_name': 'Tunde Test',
            'bank': {'name': 'Wema Bank', 'slug': 'wema-bank'},
        }
        account = services.provision_gaming_account(self.player)
        self.assertEqual(account.account_type, PaystackAccount.AccountType.GAMING)
        self.assertEqual(account.paystack_customer_code, 'CUS_new')
        dva = DedicatedVirtualAccount.objects.get(paystack_account=account)
        self.assertEqual(dva.account_number, '9990001111')
        self.assertEqual(dva.paystack_dva_id, '555')
        mock_create_customer.assert_called_once()
        mock_create_dva.assert_called_once_with(customer_code='CUS_new')

    @patch('payments.paystack_client.create_dedicated_account')
    @patch('payments.paystack_client.create_customer')
    def test_is_idempotent(self, mock_create_customer, mock_create_dva):
        mock_create_customer.return_value = {'customer_code': 'CUS_new'}
        mock_create_dva.return_value = {'id': 1, 'account_number': '1', 'account_name': 'x', 'bank': {}}
        first = services.provision_gaming_account(self.player)
        second = services.provision_gaming_account(self.player)
        self.assertEqual(first.pk, second.pk)
        mock_create_customer.assert_called_once()  # not called again on the second call

    def test_paystack_error_propagates(self):
        # No PAYSTACK_SECRET_KEY override here would hit real settings; instead
        # force the underlying call to fail as Paystack itself would (e.g.
        # Dedicated NUBAN not enabled yet).
        with patch('payments.paystack_client.create_customer', side_effect=PaystackAPIError('boom')):
            with self.assertRaises(PaystackAPIError):
                services.provision_gaming_account(self.player)


class HandleTransferEventTests(TestCase):
    def setUp(self):
        self.owner = StaffUser.objects.create_user(username='owner2', password='x', role=StaffUser.Role.OWNER)
        self.player = Player.objects.create(account_code='WWI 21', display_name='Payout Test')
        self.txn = Transaction.objects.create(
            player=self.player, type=Transaction.Type.PAYOUT, amount=50000,
            channel=Transaction.Channel.CASHIER, status=Transaction.Status.APPROVED,
            approved_by=self.owner, external_reference='TRF_abc',
        )

    def test_transfer_success_marks_posted(self):
        services.handle_transfer_event('transfer.success', {'transfer_code': 'TRF_abc'})
        self.txn.refresh_from_db()
        self.assertEqual(self.txn.status, Transaction.Status.POSTED)

    def test_transfer_failed_marks_transfer_failed(self):
        services.handle_transfer_event('transfer.failed', {'transfer_code': 'TRF_abc', 'reason': 'Insufficient funds'})
        self.txn.refresh_from_db()
        self.assertEqual(self.txn.status, Transaction.Status.TRANSFER_FAILED)
        self.assertIn('Insufficient funds', self.txn.notes)

    def test_unmatched_transfer_code_is_a_noop(self):
        result = services.handle_transfer_event('transfer.success', {'transfer_code': 'TRF_unknown'})
        self.assertIsNone(result)
        self.txn.refresh_from_db()
        self.assertEqual(self.txn.status, Transaction.Status.APPROVED)


class ProvisionGamingAccountAPITests(APITestCase):
    def setUp(self):
        self.cashier = StaffUser.objects.create_user(username='cashier3', password='x', role=StaffUser.Role.CASHIER)
        self.player = Player.objects.create(account_code='WWI 22', display_name='API Test')

    @patch('payments.paystack_client.create_dedicated_account')
    @patch('payments.paystack_client.create_customer')
    def test_cashier_can_provision(self, mock_create_customer, mock_create_dva):
        mock_create_customer.return_value = {'customer_code': 'CUS_api'}
        mock_create_dva.return_value = {'id': 1, 'account_number': '1', 'account_name': 'x', 'bank': {}}
        self.client.force_authenticate(self.cashier)
        response = self.client.post(f'/api/players/{self.player.id}/provision-gaming-account/')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNotNone(response.data['gaming_account'])
        self.assertEqual(response.data['gaming_account']['paystack_customer_code'], 'CUS_api')

    def test_not_configured_surfaces_as_502(self):
        self.client.force_authenticate(self.cashier)
        with override_settings(PAYSTACK_SECRET_KEY=''):
            response = self.client.post(f'/api/players/{self.player.id}/provision-gaming-account/')
        self.assertEqual(response.status_code, 502)


class BankListAndResolveAccountAPITests(APITestCase):
    """
    Backs the "Add bank account" form's bank picker + account-number lookup,
    added 2026-09-14: the cashier picks a bank by name (bank_code travels
    invisibly) and gets the resolved account name back to confirm with the
    player before saving.
    """

    def setUp(self):
        from django.core.cache import cache

        cache.delete('paystack_banks_ng')  # the view's process-wide cache would otherwise leak between tests
        self.cashier = StaffUser.objects.create_user(username='cashier4', password='x', role=StaffUser.Role.CASHIER)
        self.accountant = StaffUser.objects.create_user(
            username='accountant4', password='x', role=StaffUser.Role.ACCOUNTANT,
        )

    @patch('payments.paystack_client.list_banks')
    def test_cashier_can_list_banks(self, mock_list_banks):
        mock_list_banks.return_value = [{'name': 'GTBank', 'code': '058'}]
        self.client.force_authenticate(self.cashier)
        response = self.client.get('/api/payments/banks/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [{'name': 'GTBank', 'code': '058'}])

    @patch('payments.paystack_client.list_banks')
    def test_bank_list_is_cached_across_requests(self, mock_list_banks):
        mock_list_banks.return_value = [{'name': 'GTBank', 'code': '058'}]
        self.client.force_authenticate(self.cashier)
        self.client.get('/api/payments/banks/')
        self.client.get('/api/payments/banks/')
        mock_list_banks.assert_called_once()

    def test_accountant_cannot_list_banks(self):
        self.client.force_authenticate(self.accountant)
        response = self.client.get('/api/payments/banks/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch('payments.paystack_client.resolve_account_number')
    def test_cashier_can_resolve_account(self, mock_resolve):
        mock_resolve.return_value = {'account_number': '0123456789', 'account_name': 'MARCO PLAYER'}
        self.client.force_authenticate(self.cashier)
        response = self.client.get(
            '/api/payments/resolve-account/', {'account_number': '0123456789', 'bank_code': '058'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['account_name'], 'MARCO PLAYER')
        mock_resolve.assert_called_once_with('0123456789', '058')

    def test_resolve_rejects_non_ten_digit_number(self):
        self.client.force_authenticate(self.cashier)
        response = self.client.get(
            '/api/payments/resolve-account/', {'account_number': '123', 'bank_code': '058'},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('payments.paystack_client.resolve_account_number')
    def test_unresolvable_account_surfaces_as_502(self, mock_resolve):
        mock_resolve.side_effect = PaystackAPIError('Could not resolve account name.')
        self.client.force_authenticate(self.cashier)
        response = self.client.get(
            '/api/payments/resolve-account/', {'account_number': '0123456789', 'bank_code': '058'},
        )
        self.assertEqual(response.status_code, 502)
