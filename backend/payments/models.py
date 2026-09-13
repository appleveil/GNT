from django.db import models

from accounts.models import Player


class PaystackAccount(models.Model):
    """
    Either the singleton Main account or one player's Gaming Account — merged into
    one table since both have identical shape (DVAs, keys, webhook, transfer endpoints).
    """

    class AccountType(models.TextChoices):
        MAIN = 'MAIN', 'Main account'
        GAMING = 'GAMING', 'Gaming account'

    account_type = models.CharField(max_length=10, choices=AccountType.choices)
    player = models.OneToOneField(
        Player, on_delete=models.PROTECT, null=True, blank=True, related_name='gaming_account',
    )  # required+unique for GAMING, null for MAIN
    paystack_integration_id = models.CharField(max_length=100)
    integration_name = models.CharField(max_length=150)
    public_key = models.CharField(max_length=255)
    secret_key = models.CharField(max_length=255)  # TODO: encrypt at rest before production
    webhook_secret = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['account_type'], condition=models.Q(account_type='MAIN'), name='only_one_main_account',
            )
        ]

    def __str__(self):
        return self.integration_name


class DedicatedVirtualAccount(models.Model):
    paystack_account = models.ForeignKey(PaystackAccount, on_delete=models.CASCADE, related_name='dvas')
    bank_name = models.CharField(max_length=150)
    bank_code = models.CharField(max_length=20)
    account_number = models.CharField(max_length=20)
    account_name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.account_number} — {self.bank_name}'
