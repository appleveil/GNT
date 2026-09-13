from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import FloorManager, Player, PlayerBankAccount, StaffUser
from gaming import services as gaming_services
from gaming.models import GameDay, Transaction
from payments.models import PaystackAccount

DEMO_PASSWORD = 'demo-pass-1'
DEMO_PIN = '1234'


class Command(BaseCommand):
    help = (
        'Seeds local dev data: one staff account per role, a Floor Manager, a Main '
        'PaystackAccount, a few players, and an open game-day with sample entries. '
        'Safe to re-run — existing records are reused, not duplicated.'
    )

    def handle(self, *args, **options):
        owner = self._get_or_create_staff('owner1', StaffUser.Role.OWNER, 'Olu', 'Owner')
        cashier = self._get_or_create_staff('cashier1', StaffUser.Role.CASHIER, 'Chidi', 'Cashier')
        self._get_or_create_staff('accountant1', StaffUser.Role.ACCOUNTANT, 'Ada', 'Accountant')

        fm, fm_created = FloorManager.objects.get_or_create(name='Femi Floor', defaults={'created_by': owner})
        if fm_created:
            fm.set_pin(DEMO_PIN)
            fm.save()

        PaystackAccount.objects.get_or_create(
            account_type=PaystackAccount.AccountType.MAIN,
            defaults={'paystack_integration_id': 'MAIN-DEV', 'integration_name': 'LPC Main Account'},
        )

        players = {}
        for code, name in [('WWI 7', 'Marco'), ('WWI 12', 'Moses'), ('WWI 6', 'Mary')]:
            player, _ = Player.objects.get_or_create(account_code=code, defaults={'display_name': name})
            players[code] = player

        PlayerBankAccount.objects.get_or_create(
            player=players['WWI 7'], bank_name='GTBank', bank_code='058', account_number='0123456789',
            defaults={'account_name': 'Marco', 'is_default': True},
        )

        game_day, game_day_created = self._get_or_open_game_day(owner)
        if game_day_created:
            # Goes through the real service layer (FM PIN and all) rather than the
            # ORM directly — doubles as a smoke test that the flow actually works.
            gaming_services.record_transaction(
                type=Transaction.Type.CHIPS_OUT, amount=Decimal(500000), recorded_by=cashier,
                game_day=game_day, player=players['WWI 7'], floor_manager_id=fm.pk, floor_manager_pin=DEMO_PIN,
            )
            gaming_services.record_transaction(
                type=Transaction.Type.PAYMENT_CASH, amount=Decimal(200000), recorded_by=cashier,
                game_day=game_day, player=players['WWI 7'], floor_manager_id=fm.pk, floor_manager_pin=DEMO_PIN,
            )

        self.stdout.write(self.style.SUCCESS('Seed complete.'))
        self.stdout.write(f'Staff logins (password for all): {DEMO_PASSWORD}')
        self.stdout.write('  owner1 (Owner) / cashier1 (Cashier) / accountant1 (Accountant)')
        self.stdout.write(f'Floor Manager: "Femi Floor", PIN {DEMO_PIN}')
        self.stdout.write(f'Game-day #{game_day.number} is {game_day.status.lower()}, {len(players)} players seeded.')

    def _get_or_create_staff(self, username, role, first_name, last_name):
        user, created = StaffUser.objects.get_or_create(
            username=username, defaults={'role': role, 'first_name': first_name, 'last_name': last_name},
        )
        if created:
            user.set_password(DEMO_PASSWORD)
            user.save()
        return user

    def _get_or_open_game_day(self, owner):
        existing = GameDay.objects.filter(status=GameDay.Status.OPEN).order_by('-number').first()
        if existing:
            return existing, False
        next_number = (GameDay.objects.order_by('-number').values_list('number', flat=True).first() or 0) + 1
        return gaming_services.open_game_day(next_number, timezone.now(), owner), True
