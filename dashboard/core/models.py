"""
Django ORM models that mirror the Discord bot's SQLite database tables.

These models provide a read/write interface for the Django dashboard and REST API
to access the same SQLite database that the Discord bot uses at runtime. Every model
in this module uses ``managed = False`` in its ``Meta`` class, which tells Django
**not** to create, alter, or delete these tables during migrations -- the bot's own
startup code is responsible for schema management.

Architecture notes:
    - The bot writes to ``data/bot.db`` (SQLite).  The Django ``DATABASES`` setting
      points to the same file so both processes share state.
    - Because SQLite does not have a native ``BOOLEAN`` type, boolean-like fields
      (e.g. ``auto_mod_enabled``, ``enabled``, ``is_banned``) are stored as
      ``IntegerField`` where ``1`` means *True* and ``0`` means *False*.
    - Timestamp fields are stored as ``TextField`` (ISO-8601 strings) rather than
      ``DateTimeField`` because the bot writes plain text timestamps from Python's
      ``datetime.isoformat()``.
    - Discord snowflake IDs are stored as ``BigIntegerField`` to accommodate the
      full 64-bit range of Discord snowflakes.

Models:
    GuildConfig          -- Per-server configuration (prefix, channels, toggles).
    BotUser              -- Per-user-per-guild data (XP, level, economy).
    Warning              -- Moderation warnings issued to users.
    BannedWord           -- Words banned by the profanity filter (global or per-guild).
    ProfanityInfraction  -- Log entries for detected profanity violations.
    UserProfanityStats   -- Aggregated profanity statistics per user per guild.
    ProfanityConfig      -- Per-guild profanity filter thresholds and toggles.
    LevelRole            -- Role rewards automatically assigned at certain levels.
    ReactionRole         -- Emoji-to-role mappings for reaction-role messages.
    Ticket               -- Support tickets opened by users.
"""
from django.db import models


class GuildConfig(models.Model):
    """Per-guild configuration for the Discord bot.

    Stores every server-level setting that guild administrators can customise
    through the dashboard or through bot commands.  A row is created the first
    time the bot joins a server (or the first time a dashboard user views it).

    Attributes:
        guild_id: Discord guild (server) snowflake ID.  Serves as the
            primary key so there is exactly one config row per guild.
        welcome_channel_id: Channel ID where welcome/goodbye messages are
            sent.  ``None`` means the feature is disabled.
        log_channel_id: Channel ID for audit / moderation log messages.
        level_up_channel_id: Channel ID for level-up announcements.
            ``None`` means announcements go to the channel where the user
            sent the message that triggered the level-up.
        mute_role_id: Role ID applied to muted users.
        auto_mod_enabled: ``1`` if the auto-moderation module (profanity
            filter, spam detection) is active; ``0`` otherwise.
        leveling_enabled: ``1`` if the XP / leveling system is active;
            ``0`` otherwise.
        welcome_message: Template string for welcome messages.  Supports
            ``{user}`` and ``{server}`` placeholders.
        goodbye_message: Template string for goodbye messages.
        level_up_message: Template string for level-up announcements.
            Supports ``{user}`` and ``{level}`` placeholders.
        prefix: The command prefix for text commands (e.g. ``!``).
        settings: JSON-encoded blob for additional/future settings that
            do not yet have dedicated columns.
    """

    guild_id = models.BigIntegerField(primary_key=True)
    welcome_channel_id = models.BigIntegerField(null=True, blank=True)
    log_channel_id = models.BigIntegerField(null=True, blank=True)
    level_up_channel_id = models.BigIntegerField(null=True, blank=True)
    mute_role_id = models.BigIntegerField(null=True, blank=True)
    # Boolean-like integer: 1 = enabled, 0 = disabled
    auto_mod_enabled = models.IntegerField(default=1)
    leveling_enabled = models.IntegerField(default=1)
    welcome_message = models.TextField(default='Bienvenue {user} sur {server}!')
    goodbye_message = models.TextField(default='{user} a quitté le serveur.')
    level_up_message = models.TextField(default='Félicitations {user}! Tu es maintenant niveau {level}!')
    prefix = models.CharField(max_length=10, default='!')
    # Free-form JSON for extensibility; parsed by the bot at runtime
    settings = models.TextField(default='{}')

    class Meta:
        db_table = 'guild_config'
        managed = False  # Schema managed by the bot, not Django migrations

    def __str__(self):
        """Return a human-readable representation including the guild ID."""
        return f"Guild {self.guild_id}"


class BotUser(models.Model):
    """Per-user-per-guild profile tracking XP, leveling, and economy data.

    Each row represents a single user within a single guild.  The same
    Discord user will have separate rows for each guild they belong to,
    allowing independent XP and economy balances per server.

    Attributes:
        user_id: Discord user snowflake ID.
        guild_id: Discord guild snowflake ID.
        xp: Current XP within the current level (resets on level-up).
        level: Current level (starts at 1).
        total_xp: Lifetime accumulated XP (never resets).
        messages_count: Total number of messages sent in this guild.
        coins: In-bot economy balance.
        last_xp_gain: ISO-8601 timestamp of the last XP award.  Used
            to enforce the XP cooldown (one gain per ``xp_cooldown``
            seconds).
        last_daily: ISO-8601 timestamp of the last ``!daily`` command
            claim.
        created_at: ISO-8601 timestamp when this user record was first
            created.
    """

    user_id = models.BigIntegerField()
    guild_id = models.BigIntegerField()
    xp = models.IntegerField(default=0)
    level = models.IntegerField(default=1)
    total_xp = models.IntegerField(default=0)
    messages_count = models.IntegerField(default=0)
    coins = models.IntegerField(default=0)
    last_xp_gain = models.TextField(null=True, blank=True)
    last_daily = models.TextField(null=True, blank=True)
    created_at = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'users'
        managed = False  # Schema managed by the bot, not Django migrations
        # A user can only appear once per guild
        unique_together = ('user_id', 'guild_id')

    def __str__(self):
        """Return a human-readable representation with user and guild IDs."""
        return f"User {self.user_id} in Guild {self.guild_id}"


class Warning(models.Model):
    """A moderation warning issued to a user by a moderator.

    Warnings are created via bot commands (e.g. ``!warn @user reason``) or
    through the dashboard / API.  They serve as an audit trail and can
    trigger automatic escalation (mute, kick, ban) when thresholds are
    reached.

    Attributes:
        id: Auto-incrementing primary key.
        user_id: Discord snowflake ID of the warned user.
        guild_id: Discord snowflake ID of the guild where the warning
            was issued.
        moderator_id: Discord snowflake ID of the moderator who issued
            the warning.
        reason: Free-text reason for the warning.  May be ``None`` if
            no reason was provided.
        created_at: ISO-8601 timestamp when the warning was created.
    """

    id = models.AutoField(primary_key=True)
    user_id = models.BigIntegerField()
    guild_id = models.BigIntegerField()
    moderator_id = models.BigIntegerField()
    reason = models.TextField(null=True, blank=True)
    created_at = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'warnings'
        managed = False  # Schema managed by the bot, not Django migrations


class BannedWord(models.Model):
    """A word or phrase banned by the profanity filter.

    Words can be either **global** (``guild_id=0``, applied to every server
    the bot is in) or **server-specific** (``guild_id=<snowflake>``).
    The profanity filter checks incoming messages against the combined set
    of global and server-specific words.

    Attributes:
        id: Auto-incrementing primary key.
        word: The banned word or phrase (stored lowercase).
        language: ISO language code (e.g. ``'en'``, ``'fr'``) or ``'all'``
            if the word applies regardless of language.
        guild_id: ``0`` for global words; otherwise the Discord guild
            snowflake ID for server-specific words.
        severity: Integer severity level from 1 (low) to 5 (high).
            Higher severity words may trigger harsher automatic punishments.
        added_by: Discord snowflake ID of the user who added this word.
            May be ``None`` for words seeded from the default list.
        created_at: ISO-8601 timestamp when the word was added.
    """

    id = models.AutoField(primary_key=True)
    word = models.TextField()
    language = models.CharField(max_length=10, default='all')
    # guild_id=0 means the word is global (applies to all guilds)
    guild_id = models.BigIntegerField(default=0)
    severity = models.IntegerField(default=1)
    added_by = models.BigIntegerField(null=True, blank=True)
    created_at = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'banned_words'
        managed = False  # Schema managed by the bot, not Django migrations
        # The same word cannot be banned twice within the same guild
        unique_together = ('word', 'guild_id')

    def __str__(self):
        """Return the banned word with its language tag."""
        return f"{self.word} ({self.language})"


class ProfanityInfraction(models.Model):
    """A log entry recording a single profanity filter violation.

    Created automatically by the bot whenever a message is caught by
    the profanity filter.  These records form the audit trail that
    moderators review in the dashboard's infractions list.

    Attributes:
        id: Auto-incrementing primary key.
        user_id: Discord snowflake ID of the user who triggered the
            infraction.
        guild_id: Discord snowflake ID of the guild where it occurred.
        word_used: The specific banned word or phrase that was detected.
        message_content: The full text of the offending message (may be
            ``None`` if message logging is disabled).
        action_taken: Description of the automated action (e.g.
            ``'warn'``, ``'mute'``, ``'kick'``, ``'ban'``).
        created_at: ISO-8601 timestamp when the infraction was recorded.
    """

    id = models.AutoField(primary_key=True)
    user_id = models.BigIntegerField()
    guild_id = models.BigIntegerField()
    word_used = models.TextField()
    message_content = models.TextField(null=True, blank=True)
    action_taken = models.TextField(null=True, blank=True)
    created_at = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'profanity_infractions'
        managed = False  # Schema managed by the bot, not Django migrations


class UserProfanityStats(models.Model):
    """Aggregated profanity statistics for a user within a guild.

    The bot updates these counters each time a user commits an infraction.
    The progressive punishment system uses the ``total_infractions`` count
    against the thresholds defined in :class:`ProfanityConfig` to decide
    whether to warn, mute, kick, or ban the user.

    Attributes:
        user_id: Discord snowflake ID of the user.
        guild_id: Discord snowflake ID of the guild.
        total_infractions: Cumulative number of profanity infractions.
        warnings_count: Number of times the user has been warned.
        mutes_count: Number of times the user has been muted.
        kicks_count: Number of times the user has been kicked.
        is_banned: ``1`` if the user has been banned by the profanity
            system; ``0`` otherwise.
        last_infraction: ISO-8601 timestamp of the most recent infraction.
    """

    user_id = models.BigIntegerField(primary_key=True)
    guild_id = models.BigIntegerField()
    total_infractions = models.IntegerField(default=0)
    warnings_count = models.IntegerField(default=0)
    mutes_count = models.IntegerField(default=0)
    kicks_count = models.IntegerField(default=0)
    # Boolean-like integer: 1 = banned, 0 = not banned
    is_banned = models.IntegerField(default=0)
    last_infraction = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'user_profanity_stats'
        managed = False  # Schema managed by the bot, not Django migrations
        # One stats row per user per guild
        unique_together = ('user_id', 'guild_id')


class ProfanityConfig(models.Model):
    """Per-guild configuration for the profanity filter and progressive punishments.

    Each threshold field defines the infraction count at which the
    corresponding punishment is automatically applied.  For example, if
    ``warn_threshold=3`` and ``mute_threshold=5``, the user will receive
    a warning at their 3rd infraction and a temporary mute at their 5th.

    Attributes:
        guild_id: Discord guild snowflake ID (primary key -- one config
            per guild).
        enabled: ``1`` if the profanity filter is active; ``0`` otherwise.
        warn_threshold: Number of infractions before an automatic warning.
        mute_threshold: Number of infractions before an automatic mute.
        kick_threshold: Number of infractions before an automatic kick.
        ban_threshold: Number of infractions before an automatic ban.
        mute_duration: Duration of automatic mutes **in seconds**
            (default 3600 = 1 hour).
        delete_message: ``1`` to automatically delete offending messages;
            ``0`` to leave them.
        log_infractions: ``1`` to write infraction records to
            :class:`ProfanityInfraction`; ``0`` to skip logging.
        dm_user: ``1`` to send the offending user a DM explaining the
            action; ``0`` to stay silent.
    """

    guild_id = models.BigIntegerField(primary_key=True)
    # Boolean-like integers: 1 = enabled/true, 0 = disabled/false
    enabled = models.IntegerField(default=1)
    warn_threshold = models.IntegerField(default=3)
    mute_threshold = models.IntegerField(default=5)
    kick_threshold = models.IntegerField(default=8)
    ban_threshold = models.IntegerField(default=10)
    mute_duration = models.IntegerField(default=3600)  # seconds
    delete_message = models.IntegerField(default=1)
    log_infractions = models.IntegerField(default=1)
    dm_user = models.IntegerField(default=1)

    class Meta:
        db_table = 'profanity_config'
        managed = False  # Schema managed by the bot, not Django migrations


class LevelRole(models.Model):
    """A role reward automatically granted when a user reaches a certain level.

    Guild administrators configure these via the dashboard or bot commands.
    When the bot detects a level-up, it checks this table for a matching
    ``(guild_id, level)`` pair and assigns the corresponding Discord role.

    Attributes:
        id: Auto-incrementing primary key.
        guild_id: Discord guild snowflake ID.
        level: The level at which this role is awarded.
        role_id: Discord role snowflake ID to assign.
    """

    id = models.AutoField(primary_key=True)
    guild_id = models.BigIntegerField()
    level = models.IntegerField()
    role_id = models.BigIntegerField()

    class Meta:
        db_table = 'level_roles'
        managed = False  # Schema managed by the bot, not Django migrations
        # Only one role reward per level per guild
        unique_together = ('guild_id', 'level')


class ReactionRole(models.Model):
    """Maps a reaction emoji on a specific message to a Discord role.

    When a user reacts with the configured emoji on the specified message,
    the bot assigns the mapped role.  Removing the reaction removes the
    role.

    Attributes:
        id: Auto-incrementing primary key.
        guild_id: Discord guild snowflake ID.
        message_id: Discord message snowflake ID that the bot watches
            for reactions.
        channel_id: Discord channel snowflake ID containing the watched
            message.
        emoji: The emoji string (Unicode emoji or custom emoji identifier)
            that triggers the role assignment.
        role_id: Discord role snowflake ID to assign/remove on
            react/unreact.
    """

    id = models.AutoField(primary_key=True)
    guild_id = models.BigIntegerField()
    message_id = models.BigIntegerField()
    channel_id = models.BigIntegerField()
    emoji = models.TextField()
    role_id = models.BigIntegerField()

    class Meta:
        db_table = 'reaction_roles'
        managed = False  # Schema managed by the bot, not Django migrations
        # Each emoji on a given message can only map to one role
        unique_together = ('message_id', 'emoji')


class Ticket(models.Model):
    """A support ticket opened by a guild member.

    Tickets are created via bot commands (e.g. ``!ticket open subject``)
    and each one corresponds to a private Discord channel where the user
    and support staff can communicate.

    Attributes:
        id: Auto-incrementing primary key.
        guild_id: Discord guild snowflake ID.
        channel_id: Discord channel snowflake ID of the private ticket
            channel created for this ticket.
        user_id: Discord snowflake ID of the user who opened the ticket.
        subject: Short description of the issue.  May be ``None`` if the
            user did not provide one.
        status: Current ticket state -- typically ``'open'``,
            ``'in_progress'``, or ``'closed'``.
        created_at: ISO-8601 timestamp when the ticket was opened.
        closed_at: ISO-8601 timestamp when the ticket was closed.
            ``None`` while the ticket is still open.
    """

    id = models.AutoField(primary_key=True)
    guild_id = models.BigIntegerField()
    channel_id = models.BigIntegerField()
    user_id = models.BigIntegerField()
    subject = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=20, default='open')
    created_at = models.TextField(null=True, blank=True)
    closed_at = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'tickets'
        managed = False  # Schema managed by the bot, not Django migrations
