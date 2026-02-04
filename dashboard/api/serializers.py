"""
API Serializers for Discord Bot Dashboard.
"""
from rest_framework import serializers
from core.models import (
    GuildConfig, BotUser, Warning, BannedWord,
    ProfanityConfig, ProfanityInfraction, UserProfanityStats, LevelRole
)


class GuildConfigSerializer(serializers.ModelSerializer):
    """Serializer for guild configuration."""

    class Meta:
        model = GuildConfig
        fields = [
            'guild_id', 'prefix', 'welcome_channel', 'log_channel',
            'welcome_message', 'goodbye_message', 'level_up_message',
            'auto_mod_enabled', 'leveling_enabled'
        ]
        read_only_fields = ['guild_id']


class BotUserSerializer(serializers.ModelSerializer):
    """Serializer for bot users."""

    class Meta:
        model = BotUser
        fields = [
            'user_id', 'guild_id', 'username', 'level', 'xp',
            'total_xp', 'messages_count', 'balance', 'daily_streak',
            'last_daily', 'last_message', 'joined_at'
        ]
        read_only_fields = ['user_id', 'guild_id', 'joined_at']


class BotUserUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating bot users."""

    class Meta:
        model = BotUser
        fields = ['level', 'xp', 'total_xp', 'balance']


class WarningSerializer(serializers.ModelSerializer):
    """Serializer for warnings."""

    class Meta:
        model = Warning
        fields = [
            'id', 'user_id', 'guild_id', 'moderator_id',
            'reason', 'created_at'
        ]
        read_only_fields = ['id', 'guild_id', 'created_at']


class WarningCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating warnings."""

    class Meta:
        model = Warning
        fields = ['user_id', 'reason']


class BannedWordSerializer(serializers.ModelSerializer):
    """Serializer for banned words."""
    is_global = serializers.SerializerMethodField()

    class Meta:
        model = BannedWord
        fields = ['id', 'word', 'language', 'severity', 'guild_id', 'is_global']
        read_only_fields = ['id']

    def get_is_global(self, obj):
        return obj.guild_id == 0


class BannedWordCreateSerializer(serializers.Serializer):
    """Serializer for creating banned words."""
    word = serializers.CharField(max_length=100)
    language = serializers.CharField(max_length=10, default='all')
    severity = serializers.IntegerField(min_value=1, max_value=5, default=2)


class ProfanityConfigSerializer(serializers.ModelSerializer):
    """Serializer for profanity filter configuration."""

    class Meta:
        model = ProfanityConfig
        fields = [
            'guild_id', 'enabled', 'warn_threshold', 'mute_threshold',
            'kick_threshold', 'ban_threshold', 'mute_duration',
            'delete_message', 'dm_user', 'log_channel', 'exempt_roles'
        ]
        read_only_fields = ['guild_id']


class ProfanityInfractionSerializer(serializers.ModelSerializer):
    """Serializer for profanity infractions."""

    class Meta:
        model = ProfanityInfraction
        fields = [
            'id', 'user_id', 'guild_id', 'word_detected', 'original_message',
            'channel_id', 'action_taken', 'infraction_count', 'created_at'
        ]
        read_only_fields = ['id', 'guild_id', 'created_at']


class UserProfanityStatsSerializer(serializers.ModelSerializer):
    """Serializer for user profanity statistics."""

    class Meta:
        model = UserProfanityStats
        fields = [
            'user_id', 'guild_id', 'total_infractions', 'warnings_count',
            'mutes_count', 'kicks_count', 'is_banned', 'last_infraction'
        ]


class LevelRoleSerializer(serializers.ModelSerializer):
    """Serializer for level roles."""

    class Meta:
        model = LevelRole
        fields = ['id', 'guild_id', 'level', 'role_id']
        read_only_fields = ['id', 'guild_id']


class LevelRoleCreateSerializer(serializers.Serializer):
    """Serializer for creating level roles."""
    level = serializers.IntegerField(min_value=1)
    role_id = serializers.IntegerField()


class LeaderboardEntrySerializer(serializers.Serializer):
    """Serializer for leaderboard entries."""
    rank = serializers.IntegerField()
    user_id = serializers.IntegerField()
    username = serializers.CharField()
    level = serializers.IntegerField()
    total_xp = serializers.IntegerField()


class GuildStatsSerializer(serializers.Serializer):
    """Serializer for guild statistics."""
    users = serializers.DictField()
    messages = serializers.DictField()
    moderation = serializers.DictField()
    leveling = serializers.DictField()


class GuildDetailSerializer(serializers.Serializer):
    """Serializer for detailed guild information."""
    id = serializers.CharField()
    name = serializers.CharField()
    icon = serializers.CharField(allow_null=True)
    config = GuildConfigSerializer()
    stats = GuildStatsSerializer()


class GuildListSerializer(serializers.Serializer):
    """Serializer for guild list."""
    id = serializers.CharField()
    name = serializers.CharField()
    icon = serializers.CharField(allow_null=True)
    member_count = serializers.IntegerField()
    bot_present = serializers.BooleanField()
