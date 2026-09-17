from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractUser
from django.db import models


class StaffUser(AbstractUser):
    """Cashier, Accountant, Owner, or (added 2026-09-17) Floor Manager — the
    roles that get real logins."""

    class Role(models.TextChoices):
        CASHIER = 'CASHIER', 'Cashier'
        ACCOUNTANT = 'ACCOUNTANT', 'Accountant'
        OWNER = 'OWNER', 'Owner'
        # A Floor Manager's PIN-witness credential (see FloorManager below)
        # is unchanged and unrelated to this — this is a SEPARATE, real login
        # for the same real person, added so they can manage the Service
        # Staff roster themselves (gaming.models.ServiceStaff). See
        # FloorManager.staff_user for how the two records link.
        FLOOR_MANAGER = 'FLOOR_MANAGER', 'Floor Manager'

    role = models.CharField(max_length=20, choices=Role.choices)

    # In v1 only Owner-role rows set this — a quick in-person authorization PIN,
    # distinct from their login password, used for Open Game-Day / Set FX Rate.
    # Mirrors FloorManager.pin_hash. See CONCEPT.md's "Open Game-Day flow."
    pin_hash = models.CharField(max_length=128, blank=True)

    def set_pin(self, raw_pin: str) -> None:
        self.pin_hash = make_password(raw_pin)

    def check_pin(self, raw_pin: str) -> bool:
        return bool(self.pin_hash) and check_password(raw_pin, self.pin_hash)

    def __str__(self):
        return f'{self.get_full_name() or self.username} ({self.get_role_display()})'


class FloorManager(models.Model):
    """
    A named individual's confirmation PIN, entered inline on a Cashier's
    device to co-sign physical-count entries, game-day open/close, and FX
    rate changes. See CONCEPT.md.

    Revised 2026-09-17: a Floor Manager can now ALSO have a real login of
    their own (StaffUser.Role.FLOOR_MANAGER, for managing the Service Staff
    roster) — `staff_user` optionally links this PIN-witness record to that
    login for the same real person. The PIN-witness mechanic itself is
    completely unchanged: it's still looked up by this model directly
    (_resolve_floor_manager), never via the linked login, and a FloorManager
    row with no linked staff_user still works exactly as before.
    """

    name = models.CharField(max_length=150)
    pin_hash = models.CharField(max_length=128)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        StaffUser, on_delete=models.PROTECT, related_name='floor_managers_added',
        limit_choices_to={'role': StaffUser.Role.OWNER},
    )
    staff_user = models.OneToOneField(
        StaffUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='floor_manager_profile',
        limit_choices_to={'role': StaffUser.Role.FLOOR_MANAGER},
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def set_pin(self, raw_pin: str) -> None:
        self.pin_hash = make_password(raw_pin)

    def check_pin(self, raw_pin: str) -> bool:
        return check_password(raw_pin, self.pin_hash)

    def __str__(self):
        return self.name


class ServiceStaff(models.Model):
    """
    A named tipped-service person (not a Dealer — dealer tips stay
    anonymous/aggregate) — added 2026-09-17 alongside the Floor Manager
    login, since managing this roster is a Floor Manager function. Mirrors
    FloorManager's shape minus the PIN — this is a named recipient a tip
    gets attributed to, not a witness/authorizer, so no login/PIN of its
    own. See gaming.models.Transaction.service_staff/tip_category.
    """

    name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(StaffUser, on_delete=models.PROTECT, related_name='service_staff_added')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Player(models.Model):
    account_code = models.CharField(max_length=20, unique=True)  # club-assigned short code, e.g. "WWI 7"
    display_name = models.CharField(max_length=150)
    # Per-game-day credit ceiling, Owner-set-and-edited only; null = no cap. Checked
    # against the player's *current game-day* debt, not a lifetime total — see
    # CONCEPT.md's "Chips limit."
    chips_limit = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
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
    # Paystack transfer recipient for this account — created once on first payout
    # attempt (payments.services.initiate_payout_transfer) and reused after that.
    paystack_recipient_code = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['player'], condition=models.Q(is_default=True), name='one_default_bank_account_per_player',
            )
        ]

    def __str__(self):
        return f'{self.account_name} — {self.bank_name} ({self.player.account_code})'
