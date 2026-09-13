from decimal import Decimal

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
    chips_used_today = serializers.SerializerMethodField()

    class Meta:
        model = Player
        fields = [
            'id', 'account_code', 'display_name', 'is_active', 'created_at',
            'bank_accounts', 'balance', 'chips_limit', 'chips_used_today',
        ]
        read_only_fields = ['id', 'created_at']

    def validate_chips_limit(self, value):
        # Owner-only, per CONCEPT.md's "Chips limit" — a Cashier can read it
        # (shown inline wherever chips are issued) but never set/change it.
        request = self.context.get('request')
        if request and getattr(request.user, 'role', None) != StaffUser.Role.OWNER:
            raise serializers.ValidationError("Only the Owner can set a player's chips limit.")
        return value

    def get_balance(self, obj):
        # Deferred imports: avoids a module-level accounts<->gaming cycle.
        from gaming.selectors import current_open_game_day, player_balance, player_game_day_balance

        lifetime = player_balance(obj)
        request = self.context.get('request')
        if not (request and getattr(request.user, 'role', None) == StaffUser.Role.CASHIER):
            return lifetime

        # Cashier visibility rule (see CONCEPT.md's "Cashier player-history
        # visibility"): positive is always shown, regardless of when it accrued —
        # it's what makes a payout possible. A negative lifetime figure is NEVER
        # shown as-is; only today's own game-day debt (if any) is surfaced, not
        # even a hint of how much is carried over from a previous day.
        if lifetime >= 0:
            return lifetime
        game_day = current_open_game_day()
        if game_day is None:
            return Decimal('0')
        today = player_game_day_balance(obj, game_day)
        return today if today < 0 else Decimal('0')

    def get_chips_used_today(self, obj):
        """How much of chips_limit is already used tonight, for the inline Cashier UI."""
        from gaming.selectors import current_open_game_day, player_game_day_balance

        if obj.chips_limit is None:
            return None
        game_day = current_open_game_day()
        if game_day is None:
            return Decimal('0')
        balance = player_game_day_balance(obj, game_day)
        return -balance if balance < 0 else Decimal('0')
