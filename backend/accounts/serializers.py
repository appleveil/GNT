from decimal import Decimal

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from gaming.models import ActivityLog

from .models import AccountCode, FloorManager, Player, PlayerBankAccount, StaffMember, StaffUser


class ActivityLogSerializer(serializers.ModelSerializer):
    """Read-only — see ActivityLog's own docstring and views.ActivityLogView."""

    actor_name = serializers.SerializerMethodField()
    action_display = serializers.CharField(source='get_action_display', read_only=True)
    player_name = serializers.CharField(source='player.display_name', read_only=True, default=None)
    game_day_number = serializers.IntegerField(source='game_day.number', read_only=True, default=None)

    class Meta:
        model = ActivityLog
        fields = [
            'id', 'actor', 'actor_name', 'actor_role', 'action', 'action_display', 'summary',
            'player', 'player_name', 'game_day', 'game_day_number', 'transaction', 'details', 'created_at',
        ]

    def get_actor_name(self, obj):
        # Falls back to "System" for a webhook/automated entry (actor=None)
        # or one whose actor account was since deleted (SET_NULL) — never
        # a blank cell.
        if obj.actor_id is None:
            return 'System'
        return obj.actor.get_full_name() or obj.actor.username


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

    def validate_username(self, value):
        # Login itself is case-insensitive (accounts/backends.py) — reject a
        # case-variant duplicate here so there's never more than one account
        # a case-insensitive lookup could ambiguously match.
        if StaffUser.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError('A user with that username already exists.')
        return value

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = StaffUser(**validated_data)
        user.set_password(password)
        user.save()
        return user


class StaffPasswordResetSerializer(serializers.Serializer):
    """
    Owner-privileged reset of an EXISTING staff user's login password — a real
    gap StaffUserSerializer (used for update/partial_update) never covered,
    since it has no password field at all; password was only ever settable at
    create time before this. See StaffUserViewSet.reset_password. Not a
    ModelSerializer since it doesn't map 1:1 onto the model (write-only,
    no other field touched).
    """

    password = serializers.CharField(write_only=True, min_length=8)


class FloorManagerSerializer(serializers.ModelSerializer):
    pin = serializers.CharField(write_only=True, required=False, min_length=4, max_length=8)
    # Links this PIN-witness record to that same person's real login
    # (StaffUser.Role.FLOOR_MANAGER) — optional, added 2026-09-17. AdminView.vue's
    # combined create-form sets this to the StaffUser it just created in the
    # same submit, via two sequential calls.
    staff_user = serializers.PrimaryKeyRelatedField(
        queryset=StaffUser.objects.filter(role=StaffUser.Role.FLOOR_MANAGER), required=False, allow_null=True,
    )

    class Meta:
        model = FloorManager
        fields = ['id', 'name', 'is_active', 'created_by', 'created_at', 'pin', 'staff_user']
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


class StaffMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffMember
        fields = ['id', 'name', 'role', 'is_active', 'created_by', 'created_at']
        read_only_fields = ['id', 'created_by', 'created_at']

    def create(self, validated_data):
        return StaffMember.objects.create(**validated_data, created_by=self.context['request'].user)


class AccountCodeSerializer(serializers.ModelSerializer):
    """The Account Code / DVA pool (Admin page, added 2026-09-25) — see AccountCode's own docstring."""

    is_linked = serializers.SerializerMethodField()
    linked_player_name = serializers.SerializerMethodField()

    class Meta:
        model = AccountCode
        fields = [
            'id', 'code', 'account_number', 'account_name', 'is_linked', 'linked_player',
            'linked_player_name', 'created_by', 'created_at',
        ]
        read_only_fields = ['id', 'linked_player', 'created_by', 'created_at']

    def get_is_linked(self, obj):
        return obj.linked_player_id is not None

    def get_linked_player_name(self, obj):
        return obj.linked_player.display_name if obj.linked_player_id else None

    def create(self, validated_data):
        return AccountCode.objects.create(**validated_data, created_by=self.context['request'].user)


class PlayerBankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlayerBankAccount
        fields = ['id', 'bank_name', 'bank_code', 'account_number', 'account_name', 'is_default']
        read_only_fields = ['id']


class PlayerSerializer(serializers.ModelSerializer):
    bank_accounts = PlayerBankAccountSerializer(many=True, read_only=True)
    balance = serializers.SerializerMethodField()
    chips_used_today = serializers.SerializerMethodField()
    gaming_account = serializers.SerializerMethodField()

    class Meta:
        model = Player
        fields = [
            'id', 'account_code', 'display_name', 'is_active', 'created_at',
            'bank_accounts', 'balance', 'chips_limit', 'chips_used_today', 'gaming_account',
        ]
        read_only_fields = ['id', 'created_at']

    def validate_chips_limit(self, value):
        # Owner-only, per CONCEPT.md's "Chips limit" — a Cashier can read it
        # (shown inline wherever chips are issued) but never set/change it.
        request = self.context.get('request')
        if request and getattr(request.user, 'role', None) != StaffUser.Role.OWNER:
            raise serializers.ValidationError("Only the Owner can set a player's chips limit.")
        return value

    def _lifetime_balance(self, obj):
        # `lifetime_balances`/`game_day`/`game_day_balances`, when present in
        # context, come from PlayerViewSet.list's bulk selectors (added
        # 2026-09-28) — one query for every player on the page instead of
        # player_balance(player)/player_game_day_balance(player, game_day)
        # each running their own aggregate query per row, which was the
        # actual cause of the Players page being slow even with a handful of
        # players. A single-object serialization (retrieve, create, the
        # provision-gaming-account action) has no such context and falls
        # back to the original per-object selector calls, where the N+1
        # concern doesn't apply.
        if 'lifetime_balances' in self.context:
            return self.context['lifetime_balances'].get(obj.id, Decimal('0'))
        from gaming.selectors import player_balance
        return player_balance(obj)

    def _game_day_balance(self, obj):
        if 'game_day_balances' in self.context:
            if self.context.get('game_day') is None:
                return Decimal('0')
            return self.context['game_day_balances'].get(obj.id, Decimal('0'))
        from gaming.selectors import current_open_game_day, player_game_day_balance
        game_day = current_open_game_day()
        if game_day is None:
            return Decimal('0')
        return player_game_day_balance(obj, game_day)

    def _cashier_visible_balance(self, obj):
        """
        gaming.selectors.cashier_visible_balance, reimplemented against this
        serializer's own (possibly bulk-context-backed) helpers rather than
        called directly, so PlayerViewSet.list's N+1 fix still applies here.
        See CONCEPT.md's "Cashier player-history visibility": a DEBT carried
        over from before today stays hidden — only today's own game-day
        debt (if any) is surfaced. A CREDIT carried over (the house owes
        this player) is shown instead, drawn down by today's own activity;
        once it's exhausted the figure can legitimately go negative — that
        portion is today's own net activity, not old debt resurfacing.
        """
        lifetime = self._lifetime_balance(obj)
        today = self._game_day_balance(obj)
        prior = lifetime - today
        if prior >= 0:
            return lifetime
        return today if today < 0 else Decimal('0')

    def get_balance(self, obj):
        request = self.context.get('request')
        if not (request and getattr(request.user, 'role', None) == StaffUser.Role.CASHIER):
            return self._lifetime_balance(obj)
        return self._cashier_visible_balance(obj)

    def get_chips_used_today(self, obj):
        """How much of chips_limit is already used tonight, for the inline Cashier UI."""
        if obj.chips_limit is None:
            return None
        balance = self._cashier_visible_balance(obj)
        return -balance if balance < 0 else Decimal('0')

    def get_gaming_account(self, obj):
        """
        None until provisioned (see PlayerViewSet.provision_gaming_account) —
        the frontend's "Gaming Account not yet available" state is exactly this.
        """
        from payments.models import PaystackAccount
        from payments.serializers import PaystackAccountSerializer

        try:
            account = obj.gaming_account
        except PaystackAccount.DoesNotExist:
            return None
        return PaystackAccountSerializer(account).data
