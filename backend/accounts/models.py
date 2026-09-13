from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractUser
from django.db import models


class StaffUser(AbstractUser):
    """Cashier, Accountant, or Owner — the three roles that get real logins."""

    class Role(models.TextChoices):
        CASHIER = 'CASHIER', 'Cashier'
        ACCOUNTANT = 'ACCOUNTANT', 'Accountant'
        OWNER = 'OWNER', 'Owner'

    role = models.CharField(max_length=20, choices=Role.choices)

    def __str__(self):
        return f'{self.get_full_name() or self.username} ({self.get_role_display()})'


class FloorManager(models.Model):
    """
    Not a login/role — a named individual's confirmation PIN, entered inline on a
    Cashier's device to co-sign physical-count entries, game-day open/close, and
    FX rate changes. See CONCEPT.md.
    """

    name = models.CharField(max_length=150)
    pin_hash = models.CharField(max_length=128)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        StaffUser, on_delete=models.PROTECT, related_name='floor_managers_added',
        limit_choices_to={'role': StaffUser.Role.OWNER},
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def set_pin(self, raw_pin: str) -> None:
        self.pin_hash = make_password(raw_pin)

    def check_pin(self, raw_pin: str) -> bool:
        return check_password(raw_pin, self.pin_hash)

    def __str__(self):
        return self.name


class Player(models.Model):
    account_code = models.CharField(max_length=20, unique=True)  # club-assigned short code, e.g. "WWI 7"
    display_name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.account_code} ({self.display_name})'


class PlayerBankAccount(models.Model):
    """A player's receiving account for cash-outs — managed by the Cashier, not the player."""

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='bank_accounts')
    bank_name = models.CharField(max_length=150)
    bank_code = models.CharField(max_length=20)
    account_number = models.CharField(max_length=20)
    account_name = models.CharField(max_length=150)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['player'], condition=models.Q(is_default=True), name='one_default_bank_account_per_player',
            )
        ]

    def __str__(self):
        return f'{self.account_name} — {self.bank_name} ({self.player.account_code})'
