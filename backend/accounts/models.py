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
        # for the same real person, added so they can manage the StaffMember
        # roster themselves (gaming.models.Transaction.masseuse points at
        # accounts.StaffMember). See FloorManager.staff_user for how the two
        # records link.
        #
        # MASSEUSE/DEALER/SERVICE were added here 2026-09-23, then reverted
        # the same day once it was clarified they never actually log in —
        # see StaffMember below, which is where they live instead: named,
        # non-login staff records the Owner adds from the Admin page.
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


class StaffMember(models.Model):
    """
    A named, NON-LOGIN staff record — added 2026-09-17 as "ServiceStaff"
    (a named tipped person only), renamed to "Masseuse" 2026-09-23 when
    Transaction.TipCategory's two values were relabeled, then generalized
    to StaffMember the same day once it was clarified that Masseuse/Dealer/
    Service should never log in at all: they were briefly added as
    StaffUser.Role choices (a real login) before that correction — see
    StaffUser.Role's own comment. This is where they actually belong:
    Owner-addable from the Admin page, no username/password, no dashboard.

    `role` is one of three: MASSEUSE (named tip recipient — see
    gaming.models.Transaction.masseuse/tip_category; the ONLY role this
    FK ever points at, validated in gaming.services.record_transaction),
    DEALER, or SERVICE — the latter two are pure record-keeping today (an
    employee directory), not wired into anything else yet. Mirrors
    FloorManager's shape minus the PIN — a name, not a witness/authorizer.
    """

    class Role(models.TextChoices):
        MASSEUSE = 'MASSEUSE', 'Masseuse'
        DEALER = 'DEALER', 'Dealer'
        SERVICE = 'SERVICE', 'Service'

    name = models.CharField(max_length=150)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MASSEUSE)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(StaffUser, on_delete=models.PROTECT, related_name='staff_members_added')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Player(models.Model):
    account_code = models.CharField(max_length=20, unique=True)  # club-assigned short code, e.g. "WWI 7"
    display_name = models.CharField(max_length=150)
    # Per-game-day credit ceiling, Owner-set-and-edited only; null = no cap. Checked
    # against the player's *current game-day* debt, not a lifetime total — see
    # CONCEPT.md's "Chips limit." Labeled "Credit limit" in the UI as of
    # 2026-09-25 (this field name is unchanged — a display-only rename, to
    # stop it being confused with a table's own max_chips_issuable, a
    # different, per-buy-in cap set in Settings): this is the max a player
    # can owe in unpaid chips before settling up, not the max issuable at once.
    chips_limit = models.DecimalField(max_digits=14, decimal_places=0, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.account_code} ({self.display_name})'


class AccountCode(models.Model):
    """
    A pre-provisioned real bank-issued dedicated account ("DVA"), staged
    ahead of time by the Owner or Accountant from the Admin page (added
    2026-09-25, extended 2026-09-26 with real bank details). Stands in for
    Paystack's own Dedicated NUBAN provisioning while that's still pending
    approval — the next available row here is auto-assigned to a new
    Player instead of a Cashier typing a bare code in free-hand at
    registration (AddPlayerModal.vue's old "Account code" field); see
    gaming.services.seat_player.

    `code` is the club's own short reference (e.g. "WWI 15", becomes the
    Player's account_code); `account_number`/`account_name` are the real
    bank account details that code refers to — one-at-a-time via the Admin
    form, or bulk via a CSV/XLS/XLSX upload (parsed client-side, posted as
    plain rows — see AdminView.vue).

    `linked_player` is null while available; set exactly once, the moment
    it's consumed by a new player, and never freed again — same
    never-un-record convention as everything else in this schema (a
    linked code doesn't go back in the pool even if that player is later
    deactivated).
    """

    code = models.CharField(max_length=20, unique=True)
    account_number = models.CharField(max_length=20, unique=True)
    account_name = models.CharField(max_length=150)
    linked_player = models.OneToOneField(
        Player, on_delete=models.PROTECT, null=True, blank=True, related_name='account_code_entry',
    )
    created_by = models.ForeignKey(
        StaffUser, on_delete=models.PROTECT, null=True, blank=True, related_name='account_codes_added',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.code} ({"linked" if self.linked_player_id else "available"})'


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
