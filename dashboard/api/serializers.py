"""
Django REST Framework serializers for the Discord Bot Dashboard API.

Serializers define the translation layer between Django ORM model instances
(or plain dictionaries) and JSON representations consumed by API clients.
Each model typically has:

    - A **read serializer** (``ModelSerializer``) that exposes most fields
      with selected fields marked ``read_only``.
    - A **create / update serializer** that accepts only the fields the
      client is allowed to set, omitting auto-generated or server-assigned
      fields (e.g. ``id``, ``guild_id``, ``created_at``).

Non-model serializers (``Serializer`` subclasses) are used for derived data
structures that do not map 1:1 to a database table, such as leaderboard
entries and aggregated guild statistics.

Serializer hierarchy:
    GuildConfigSerializer            -- Read/update for GuildConfig.
    BotUserSerializer                -- Read for BotUser.
    BotUserUpdateSerializer          -- Partial update for BotUser (XP, level, balance).
    WarningSerializer                -- Read for Warning.
    WarningCreateSerializer          -- Create for Warning (user_id + reason only).
    BannedWordSerializer             -- Read for BannedWord (includes ``is_global``).
    BannedWordCreateSerializer       -- Create for BannedWord.
    ProfanityConfigSerializer        -- Read/update for ProfanityConfig.
    ProfanityInfractionSerializer    -- Read for ProfanityInfraction.
    UserProfanityStatsSerializer     -- Read for UserProfanityStats.
    LevelRoleSerializer              -- Read for LevelRole.
    LevelRoleCreateSerializer        -- Create for LevelRole.
    LeaderboardEntrySerializer       -- Non-model: ranked user entry.
    GuildStatsSerializer             -- Non-model: aggregated guild statistics.
    GuildDetailSerializer            -- Non-model: guild info + config + stats.
    GuildListSerializer              -- Non-model: compact guild summary for lists.
"""
from rest_framework import serializers
from core.models import (
    GuildConfig, BotUser, Warning, BannedWord,
    ProfanityConfig, ProfanityInfraction, UserProfanityStats, LevelRole
)


class GuildConfigSerializer(serializers.ModelSerializer):
    """Serializer for reading and updating guild configuration.

    Exposes the most commonly-managed settings from
    :class:`~core.models.GuildConfig`.  The ``guild_id`` is read-only
    because it is the primary key and must not be changed after creation.
    """

    class Meta:
        model = GuildConfig
        fields = [
            'guild_id', 'prefix', 'welcome_channel', 'log_channel',
            'welcome_message', 'goodbye_message', 'level_up_message',
            'auto_mod_enabled', 'leveling_enabled'
        ]
        read_only_fields = ['guild_id']


class BotUserSerializer(serializers.ModelSerializer):
    """Read-only serializer for a user's profile within a guild.

    Contains identity fields (``user_id``, ``guild_id``), leveling data,
    economy data, and timestamps.  Used by list and detail endpoints.
    """

    class Meta:
        model = BotUser
        fields = [
            'user_id', 'guild_id', 'username', 'level', 'xp',
            'total_xp', 'messages_count', 'balance', 'daily_streak',
            'last_daily', 'last_message', 'joined_at'
        ]
        read_only_fields = ['user_id', 'guild_id', 'joined_at']


class BotUserUpdateSerializer(serializers.ModelSerializer):
    """Serializer for admin-initiated updates to a user's profile.

    Only the fields that a guild administrator should be able to modify
    directly are included (level, XP, balance).  All other fields are
    managed exclusively by the bot.
    """

    class Meta:
        model = BotUser
        fields = ['level', 'xp', 'total_xp', 'balance']


class WarningSerializer(serializers.ModelSerializer):
    """Read serializer for moderation warnings.

    Includes all fields needed to display a warning in the dashboard:
    who was warned, who issued it, why, and when.  The ``guild_id`` and
    ``created_at`` are read-only because they are set automatically when
    the warning is created.
    """

    class Meta:
        model = Warning
        fields = [
            'id', 'user_id', 'guild_id', 'moderator_id',
            'reason', 'created_at'
        ]
        read_only_fields = ['id', 'guild_id', 'created_at']


class WarningCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a new warning via the API.

    Accepts only the user being warned and an optional reason.  The
    ``guild_id`` and ``moderator_id`` are injected by the viewset's
    ``perform_create`` method from the URL and the authenticated user.
    """

    class Meta:
        model = Warning
        fields = ['user_id', 'reason']


class BannedWordSerializer(serializers.ModelSerializer):
    """Read serializer for banned words with a computed ``is_global`` flag.

    The ``is_global`` field is a :class:`~rest_framework.fields.SerializerMethodField`
    that returns ``True`` when the word's ``guild_id`` is ``0`` (meaning
    the word applies to all guilds).
    """

    # Computed field -- not stored in the database
    is_global = serializers.SerializerMethodField()

    class Meta:
        model = BannedWord
        fields = ['id', 'word', 'language', 'severity', 'guild_id', 'is_global']
        read_only_fields = ['id']

    def get_is_global(self, obj):
        """Return ``True`` if the banned word is global (applies to every guild).

        Args:
            obj (BannedWord): The banned-word instance being serialized.

        Returns:
            bool: ``True`` when ``guild_id == 0``, ``False`` otherwise.
        """
        return obj.guild_id == 0


class BannedWordCreateSerializer(serializers.Serializer):
    """Serializer for creating a new banned word via the API.

    Does not extend ``ModelSerializer`` because the viewset manually
    handles creation with ``get_or_create`` to prevent duplicates.

    Attributes:
        word: The word or phrase to ban (max 100 characters).
        language: ISO language code or ``'all'`` (default).
        severity: Integer severity 1-5 (default 2).
    """

    word = serializers.CharField(max_length=100)
    language = serializers.CharField(max_length=10, default='all')
    severity = serializers.IntegerField(min_value=1, max_value=5, default=2)


class ProfanityConfigSerializer(serializers.ModelSerializer):
    """Serializer for reading and updating profanity filter configuration.

    Maps to :class:`~core.models.ProfanityConfig`.  The ``guild_id`` is
    read-only since it is the primary key.  All threshold and toggle fields
    are writable via PATCH requests.
    """

    class Meta:
        model = ProfanityConfig
        fields = [
            'guild_id', 'enabled', 'warn_threshold', 'mute_threshold',
            'kick_threshold', 'ban_threshold', 'mute_duration',
            'delete_message', 'dm_user', 'log_channel', 'exempt_roles'
        ]
        read_only_fields = ['guild_id']


class ProfanityInfractionSerializer(serializers.ModelSerializer):
    """Read serializer for profanity infraction log entries.

    Used by the ``InfractionViewSet`` (read-only) to present infraction
    records to guild administrators.  Server-assigned fields (``id``,
    ``guild_id``, ``created_at``) are read-only.
    """

    class Meta:
        model = ProfanityInfraction
        fields = [
            'id', 'user_id', 'guild_id', 'word_detected', 'original_message',
            'channel_id', 'action_taken', 'infraction_count', 'created_at'
        ]
        read_only_fields = ['id', 'guild_id', 'created_at']


class UserProfanityStatsSerializer(serializers.ModelSerializer):
    """Read-only serializer for aggregated per-user profanity statistics.

    All fields are exposed as-is from :class:`~core.models.UserProfanityStats`.
    This serializer is used when displaying top-offender data in the API.
    """

    class Meta:
        model = UserProfanityStats
        fields = [
            'user_id', 'guild_id', 'total_infractions', 'warnings_count',
            'mutes_count', 'kicks_count', 'is_banned', 'last_infraction'
        ]


class LevelRoleSerializer(serializers.ModelSerializer):
    """Read serializer for level-role reward mappings.

    The ``id`` and ``guild_id`` are read-only because they are set by the
    server.  Only ``level`` and ``role_id`` are writable (via create).
    """

    class Meta:
        model = LevelRole
        fields = ['id', 'guild_id', 'level', 'role_id']
        read_only_fields = ['id', 'guild_id']


class LevelRoleCreateSerializer(serializers.Serializer):
    """Serializer for creating a level-role mapping via the API.

    The ``guild_id`` is extracted from the URL by the viewset, so only the
    ``level`` and ``role_id`` need to be provided by the client.

    Attributes:
        level: The level at which the role is awarded (minimum 1).
        role_id: Discord snowflake ID of the role to assign.
    """

    level = serializers.IntegerField(min_value=1)
    role_id = serializers.IntegerField()


# ---------------------------------------------------------------------------
# Non-model serializers (for derived / aggregated data)
# ---------------------------------------------------------------------------


class LeaderboardEntrySerializer(serializers.Serializer):
    """Serializer for a single entry in the guild XP leaderboard.

    This is a non-model serializer because leaderboard entries are
    constructed in the view by enumerating ranked users, not read
    directly from a database table.

    Attributes:
        rank: 1-based position on the leaderboard.
        user_id: Discord user snowflake ID.
        username: Display name (falls back to ``'User <id>'``).
        level: Current user level.
        total_xp: Lifetime accumulated XP.
    """

    rank = serializers.IntegerField()
    user_id = serializers.IntegerField()
    username = serializers.CharField()
    level = serializers.IntegerField()
    total_xp = serializers.IntegerField()


class GuildStatsSerializer(serializers.Serializer):
    """Serializer for aggregated guild-wide statistics.

    Each field is a dictionary containing related metrics:

    - ``users``: total, active_today, new_this_week.
    - ``messages``: total, today.
    - ``moderation``: warnings, infractions, bans.
    - ``leveling``: total_xp, average_level, max_level.
    """

    users = serializers.DictField()
    messages = serializers.DictField()
    moderation = serializers.DictField()
    leveling = serializers.DictField()


class GuildDetailSerializer(serializers.Serializer):
    """Serializer for the detailed guild view (retrieve endpoint).

    Combines Discord guild metadata (``id``, ``name``, ``icon``) with
    the bot's :class:`GuildConfigSerializer` and
    :class:`GuildStatsSerializer` in a single response.
    """

    id = serializers.CharField()
    name = serializers.CharField()
    icon = serializers.CharField(allow_null=True)
    config = GuildConfigSerializer()
    stats = GuildStatsSerializer()


class GuildListSerializer(serializers.Serializer):
    """Serializer for the compact guild list (list endpoint).

    Returns just enough information to render a guild-selection card:
    name, icon, member count, and whether the bot is present.
    """

    id = serializers.CharField()
    name = serializers.CharField()
    icon = serializers.CharField(allow_null=True)
    member_count = serializers.IntegerField()
    bot_present = serializers.BooleanField()
