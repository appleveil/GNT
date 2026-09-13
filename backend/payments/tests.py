import hashlib
import hmac
import json

from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Player
from gaming.models import Transaction

from . import services
from .models import PaystackAccount

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
            paystack_integration_id='CUS_test123', integration_name='Amina GA',
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
            paystack_integration_id='CUS_test456', integration_name='Moses GA',
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
