from django.db import models

from accounts.models import Player


class PaystackAccount(models.Model):
    """
    Either the singleton Main account or one player's Gaming Account.

    Revised 2026-09-13: there is only ONE Paystack integration for the whole
    club (one secret/public key pair, in settings — see paystack_client.py),
    not a separate integration per player. A Gaming Account is a Paystack
    Customer (paystack_customer_code) plus a Dedicated Virtual Account,
    both under that single integration. The MAIN row carries no Paystack
    identity of its own — it exists as an anchor/label only. See SCHEMA.md.
    """

    class AccountType(models.TextChoices):
        MAIN = 'MAIN', 'Main account'
        GAMING = 'GAMING', 'Gaming account'

    account_type = models.CharField(max_length=10, choices=AccountType.choices)
    player = models.OneToOneField(
        Player, on_delete=models.PROTECT, null=True, blank=True, related_name='gaming_account',
    )  # required+unique for GAMING, null for MAIN
    paystack_customer_code = models.CharField(max_length=100, blank=True)  # blank for MAIN
    label = models.CharField(max_length=150)  # e.g. "LPC Main Account", or the player's name
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['account_type'], condition=models.Q(account_type='MAIN'), name='only_one_main_account',
            )
        ]

    def __str__(self):
        return self.label


class DedicatedVirtualAccount(models.Model):
    paystack_account = models.ForeignKey(PaystackAccount, on_delete=models.CASCADE, related_name='dvas')
    paystack_dva_id = models.CharField(max_length=50, blank=True)  # Paystack's own id, for future deactivation calls
    bank_name = models.CharField(max_length=150)
    bank_code = models.CharField(max_length=20)
    account_number = models.CharField(max_length=20)
    account_name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.account_number} — {self.bank_name}'
