from rest_framework import status
from rest_framework.test import APITestCase

from .models import FloorManager, Player, StaffUser


class AuthTests(APITestCase):
    def setUp(self):
        self.owner = StaffUser.objects.create_user(username='owner', password='pass123', role=StaffUser.Role.OWNER)

    def test_login_returns_role_claim(self):
        response = self.client.post('/api/auth/login/', {'username': 'owner', 'password': 'pass123'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_wrong_password_rejected(self):
        response = self.client.post('/api/auth/login/', {'username': 'owner', 'password': 'wrong'})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class PlayerAPITests(APITestCase):
    def setUp(self):
        self.owner = StaffUser.objects.create_user(username='owner', password='x', role=StaffUser.Role.OWNER)
        self.cashier = StaffUser.objects.create_user(username='cashier', password='x', role=StaffUser.Role.CASHIER)
        self.accountant = StaffUser.objects.create_user(
            username='accountant', password='x', role=StaffUser.Role.ACCOUNTANT,
        )

    def test_cashier_can_create_player(self):
        self.client.force_authenticate(self.cashier)
        response = self.client.post('/api/players/', {'account_code': 'WWI 1', 'display_name': 'Test Player'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_accountant_cannot_create_player(self):
        self.client.force_authenticate(self.accountant)
        response = self.client.post('/api/players/', {'account_code': 'WWI 2', 'display_name': 'Test Player 2'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_accountant_can_list_players(self):
        Player.objects.create(account_code='WWI 3', display_name='Existing')
        self.client.force_authenticate(self.accountant)
        response = self.client.get('/api/players/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_anonymous_request_rejected(self):
        response = self.client.get('/api/players/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class StaffAndFloorManagerAPITests(APITestCase):
    def setUp(self):
        self.owner = StaffUser.objects.create_user(username='owner', password='x', role=StaffUser.Role.OWNER)
        self.cashier = StaffUser.objects.create_user(username='cashier', password='x', role=StaffUser.Role.CASHIER)

    def test_owner_can_create_staff_user(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(
            '/api/staff-users/',
            {'username': 'newcashier', 'password': 'temp-pass-1', 'role': StaffUser.Role.CASHIER},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_cashier_cannot_create_staff_user(self):
        self.client.force_authenticate(self.cashier)
        response = self.client.post(
            '/api/staff-users/',
            {'username': 'x', 'password': 'temp-pass-1', 'role': StaffUser.Role.CASHIER},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_can_create_floor_manager(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post('/api/floor-managers/', {'name': 'Floor Boss', 'pin': '4321'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        fm = FloorManager.objects.get(pk=response.data['id'])
        self.assertTrue(fm.check_pin('4321'))
        self.assertNotIn('pin', response.data)  # write-only, never echoed back

    def test_cashier_cannot_create_floor_manager(self):
        self.client.force_authenticate(self.cashier)
        response = self.client.post('/api/floor-managers/', {'name': 'Floor Boss', 'pin': '4321'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
