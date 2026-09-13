from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import FloorManager, Player, PlayerBankAccount, StaffUser


class StaffLoginSerializer(TokenObtainPairSerializer):
    """Adds role/name to the token claims so a frontend doesn't need a second call."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['role'] = user.role
        token['full_name'] = user.get_full_name() or user.username
        return token


class StaffUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffUser
        fields = ['id', 'username', 'first_name', 'last_name', 'role', 'is_active']
        read_only_fields = ['id']


class StaffUserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = StaffUser
        fields = ['id', 'username', 'first_name', 'last_name', 'role', 'password']

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = StaffUser(**validated_data)
        user.set_password(password)
        user.save()
        return user


class FloorManagerSerializer(serializers.ModelSerializer):
    pin = serializers.CharField(write_only=True, required=False, min_length=4, max_length=8)

    class Meta:
        model = FloorManager
        fields = ['id', 'name', 'is_active', 'created_by', 'created_at', 'pin']
        read_only_fields = ['id', 'created_by', 'created_at']

    def create(self, validated_data):
        pin = validated_data.pop('pin', None)
        if not pin:
            raise serializers.ValidationError({'pin': 'A PIN is required.'})
        fm = FloorManager(**validated_data, created_by=self.context['request'].user)
        fm.set_pin(pin)
        fm.save()
        return fm

    def update(self, instance, validated_data):
        pin = validated_data.pop('pin', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if pin:
            instance.set_pin(pin)
        instance.save()
        return instance


class PlayerBankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlayerBankAccount
        fields = ['id', 'bank_name', 'bank_code', 'account_number', 'account_name', 'is_default']
        read_only_fields = ['id']


class PlayerSerializer(serializers.ModelSerializer):
    bank_accounts = PlayerBankAccountSerializer(many=True, read_only=True)
    balance = serializers.SerializerMethodField()

    class Meta:
        model = Player
        fields = ['id', 'account_code', 'display_name', 'is_active', 'created_at', 'bank_accounts', 'balance']
        read_only_fields = ['id', 'created_at']

    def get_balance(self, obj):
        from gaming.selectors import player_balance  # deferred: avoids a module-level accounts<->gaming cycle
        return player_balance(obj)
