from rest_framework import status

from lpc_backend.testing import APITestCase

from .models import AccountCode, FloorManager, Player, PlayerBankAccount, StaffUser


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

    def test_login_is_case_insensitive(self):
        for attempt in ('OWNER', 'Owner', 'oWnEr'):
            response = self.client.post('/api/auth/login/', {'username': attempt, 'password': 'pass123'})
            self.assertEqual(response.status_code, status.HTTP_200_OK, attempt)

    def test_case_variant_username_rejected_on_create(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(
            '/api/staff-users/', {'username': 'Owner', 'password': 'x', 'role': StaffUser.Role.CASHIER},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


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

    def test_cashier_can_list_floor_managers(self):
        """Needed for the Open Game-Day 'who's authorizing' picker — relaxed 2026-09-14."""
        fm = FloorManager(name='Femi Floor', created_by=self.owner)
        fm.set_pin('1234')
        fm.save()
        inactive = FloorManager(name='Retired FM', created_by=self.owner, is_active=False)
        inactive.set_pin('1234')
        inactive.save()

        self.client.force_authenticate(self.cashier)
        response = self.client.get('/api/floor-managers/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [row['name'] for row in response.data]
        self.assertIn('Femi Floor', names)
        self.assertNotIn('Retired FM', names)  # inactive hidden from non-Owner

    def test_owner_sees_inactive_floor_managers_too(self):
        inactive = FloorManager(name='Retired FM', created_by=self.owner, is_active=False)
        inactive.set_pin('1234')
        inactive.save()
        self.client.force_authenticate(self.owner)
        response = self.client.get('/api/floor-managers/')
        self.assertIn('Retired FM', [row['name'] for row in response.data])

    def test_cashier_can_list_owners_only(self):
        """Added 2026-09-14: the Open Game-Day picker needs Owner names, not the full staff list."""
        self.client.force_authenticate(self.cashier)
        response = self.client.get('/api/staff-users/owners/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(all(row['role'] == StaffUser.Role.OWNER for row in response.data))
        self.assertIn('owner', [row['username'] for row in response.data])
        self.assertNotIn('cashier', [row['username'] for row in response.data])

    def test_cashier_cannot_list_all_staff_users(self):
        self.client.force_authenticate(self.cashier)
        response = self.client.get('/api/staff-users/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_can_reset_a_staff_users_password(self):
        """Phase C gap: StaffUserSerializer (used for update) has no password
        field at all — this dedicated action is the only way to change an
        existing user's password. Confirms the new password actually
        authenticates, not just that the call succeeds."""
        self.client.force_authenticate(self.owner)
        response = self.client.post(f'/api/staff-users/{self.cashier.id}/reset-password/', {'password': 'new-pass-123'})
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.cashier.refresh_from_db()
        self.assertTrue(self.cashier.check_password('new-pass-123'))

    def test_cashier_cannot_reset_a_staff_users_password(self):
        self.client.force_authenticate(self.cashier)
        response = self.client.post(f'/api/staff-users/{self.owner.id}/reset-password/', {'password': 'new-pass-123'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_reset_password_rejects_a_short_password(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(f'/api/staff-users/{self.cashier.id}/reset-password/', {'password': 'short'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class FloorManagerRoleAndStaffMemberTests(APITestCase):
    """
    Floor Manager as a real logged-in role, added 2026-09-17 alongside the
    named-staff roster it's meant to manage (named "Service Staff", then
    "Masseuse", then generalized to StaffMember on 2026-09-23 to also cover
    Dealer/Service — see StaffMember's own docstring and PLAN.md's entries).
    The existing PIN-witness FloorManager model/mechanic is unaffected;
    this covers only the login + StaffMember-roster pieces.
    """

    def setUp(self):
        self.owner = StaffUser.objects.create_user(username='owner2', password='x', role=StaffUser.Role.OWNER)
        self.cashier = StaffUser.objects.create_user(username='cashier2', password='x', role=StaffUser.Role.CASHIER)
        self.fm_login = StaffUser.objects.create_user(
            username='fm1', password='x', role=StaffUser.Role.FLOOR_MANAGER,
        )

    def test_floor_manager_can_log_in(self):
        response = self.client.post('/api/auth/login/', {'username': 'fm1', 'password': 'x'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)

    def test_floor_manager_pin_witness_record_can_link_to_the_login(self):
        """The two credentials — PIN-witness and login — are separate but
        linkable for the same real person; linking doesn't change how the
        PIN-witness mechanic itself works (_resolve_floor_manager)."""
        fm = FloorManager(name='Femi Floor', created_by=self.owner, staff_user=self.fm_login)
        fm.set_pin('1234')
        fm.save()
        self.assertEqual(fm.staff_user, self.fm_login)
        self.assertTrue(fm.check_pin('1234'))  # unaffected by the link

    def test_floor_manager_can_create_a_staff_member(self):
        self.client.force_authenticate(self.fm_login)
        response = self.client.post('/api/staff-members/', {'name': 'Tunde', 'role': 'MASSEUSE'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_owner_can_also_create_a_staff_member(self):
        """Added 2026-09-23 — Masseuse/Dealer/Service are addable from the
        Admin page's own section, none of them a real login (see
        StaffUser.Role's own comment for why that was reverted)."""
        self.client.force_authenticate(self.owner)
        for role in ('MASSEUSE', 'DEALER', 'SERVICE'):
            response = self.client.post('/api/staff-members/', {'name': f'Person {role}', 'role': role})
            self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
            self.assertEqual(response.data['role'], role)

    def test_cashier_cannot_create_a_staff_member(self):
        self.client.force_authenticate(self.cashier)
        response = self.client.post('/api/staff-members/', {'name': 'Blessing', 'role': 'MASSEUSE'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_any_staff_can_list_staff_members(self):
        """Needed for the Tip entry form's Masseuse picker."""
        from .models import StaffMember
        StaffMember.objects.create(name='Blessing', role='MASSEUSE', created_by=self.owner)
        self.client.force_authenticate(self.cashier)
        response = self.client.get('/api/staff-members/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('Blessing', [row['name'] for row in response.data])

    def test_inactive_staff_member_hidden_from_non_floor_manager_non_owner(self):
        from .models import StaffMember
        StaffMember.objects.create(name='Retired Server', role='SERVICE', created_by=self.owner, is_active=False)
        self.client.force_authenticate(self.cashier)
        response = self.client.get('/api/staff-members/')
        self.assertNotIn('Retired Server', [row['name'] for row in response.data])

    def test_role_query_param_filters_the_list(self):
        """Added 2026-09-23 — the Tip picker (and the Floor Manager's own
        "Masseuses" screen) only ever want role=MASSEUSE, not Dealer/Service
        too. Mirrors StaffUserViewSet.owners' own role-filtering pattern."""
        from .models import StaffMember
        StaffMember.objects.create(name='Blessing', role='MASSEUSE', created_by=self.owner)
        StaffMember.objects.create(name='Femi', role='DEALER', created_by=self.owner)
        self.client.force_authenticate(self.cashier)
        response = self.client.get('/api/staff-members/?role=MASSEUSE')
        names = [row['name'] for row in response.data]
        self.assertIn('Blessing', names)
        self.assertNotIn('Femi', names)


class PlayerBankAccountAPITests(APITestCase):
    """
    Found live 2026-09-14: setting a new default bank account crashed with an
    IntegrityError (one_default_bank_account_per_player) because nothing
    unset the old default first — the constraint was correct, the view was
    the bug.
    """

    def setUp(self):
        self.cashier = StaffUser.objects.create_user(username='cashier', password='x', role=StaffUser.Role.CASHIER)
        self.player = Player.objects.create(account_code='WWI 1', display_name='Test Player')
        self.client.force_authenticate(self.cashier)

    def test_setting_a_new_default_unsets_the_old_one(self):
        first = PlayerBankAccount.objects.create(
            player=self.player, bank_name='GTBank', bank_code='058', account_number='0123456789',
            account_name='Test Player', is_default=True,
        )
        second = PlayerBankAccount.objects.create(
            player=self.player, bank_name='Access Bank', bank_code='044', account_number='9998887776',
            account_name='Test Player', is_default=False,
        )
        response = self.client.patch(
            f'/api/players/{self.player.id}/bank-accounts/{second.id}/', {'is_default': True},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)

    def test_creating_a_new_default_unsets_the_old_one(self):
        PlayerBankAccount.objects.create(
            player=self.player, bank_name='GTBank', bank_code='058', account_number='0123456789',
            account_name='Test Player', is_default=True,
        )
        response = self.client.post(f'/api/players/{self.player.id}/bank-accounts/', {
            'bank_name': 'Access Bank', 'bank_code': '044', 'account_number': '9998887776',
            'account_name': 'Test Player', 'is_default': True,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            PlayerBankAccount.objects.filter(player=self.player, is_default=True).count(), 1,
        )


class AccountCodeAPITests(APITestCase):
    """The Account Code / DVA pool (Admin page, added 2026-09-25) — see AccountCode's own docstring."""

    def setUp(self):
        self.owner = StaffUser.objects.create_user(username='ac_owner', password='x', role=StaffUser.Role.OWNER)
        self.accountant = StaffUser.objects.create_user(
            username='ac_accountant', password='x', role=StaffUser.Role.ACCOUNTANT,
        )
        self.cashier = StaffUser.objects.create_user(username='ac_cashier', password='x', role=StaffUser.Role.CASHIER)

    def test_owner_can_bulk_add_codes(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post('/api/account-codes/', {'codes': ['WWI 100', 'WWI 101', 'WWI 100']}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data['created']), 2)  # in-batch duplicate collapsed, not double-created
        self.assertEqual(AccountCode.objects.filter(code__in=['WWI 100', 'WWI 101']).count(), 2)

    def test_adding_an_already_existing_code_is_reported_not_fatal(self):
        AccountCode.objects.create(code='WWI 102')
        self.client.force_authenticate(self.owner)
        response = self.client.post('/api/account-codes/', {'codes': ['WWI 102', 'WWI 103']}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data['created']), 1)
        self.assertEqual(len(response.data['errors']), 1)

    def test_accountant_can_manage_the_pool_cashier_cannot(self):
        self.client.force_authenticate(self.accountant)
        response = self.client.post('/api/account-codes/', {'codes': ['WWI 104']}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(self.cashier)
        response = self.client.get('/api/account-codes/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_available_count_is_open_to_every_role_but_excludes_linked(self):
        AccountCode.objects.create(code='WWI 105')
        linked_player = Player.objects.create(account_code='WWI 106', display_name='Linked')
        AccountCode.objects.create(code='WWI 106', linked_player=linked_player)

        self.client.force_authenticate(self.cashier)
        response = self.client.get('/api/account-codes/available-count/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
