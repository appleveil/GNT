from rest_framework import serializers

from .models import DedicatedVirtualAccount, PaystackAccount


class DedicatedVirtualAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = DedicatedVirtualAccount
        fields = ['id', 'bank_name', 'bank_code', 'account_number', 'account_name', 'is_active']
        read_only_fields = fields


class PaystackAccountSerializer(serializers.ModelSerializer):
    dvas = DedicatedVirtualAccountSerializer(many=True, read_only=True)

    class Meta:
        model = PaystackAccount
        fields = ['id', 'account_type', 'paystack_customer_code', 'label', 'dvas', 'created_at']
        read_only_fields = fields
