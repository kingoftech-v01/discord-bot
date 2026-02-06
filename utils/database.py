"""Async SQLite database layer for bot persistence.

Uses aiosqlite for non-blocking I/O. Each method opens its own connection
(short-lived connection model). Use the module-level `db` singleton.

Security: update_guild_config() and update_profanity_config() validate
column names against whitelists to prevent SQL injection.
"""

import sqlite3
import aiosqlite
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import json

# Path to the SQLite database file, relative to the bot's working directory.
DATABASE_PATH = "data/bot.db"


class Database:
    """Async database manager. Call init() once at startup."""

    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path

    async def init(self):
        """Create tables and seed default banned words. Safe to call multiple times."""
        async with aiosqlite.connect(self.db_path) as db:
            # ---- users: per-guild user profiles (XP, levelling, economy) ----
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    xp INTEGER DEFAULT 0,
                    level INTEGER DEFAULT 1,
                    total_xp INTEGER DEFAULT 0,
                    messages_count INTEGER DEFAULT 0,
                    coins INTEGER DEFAULT 0,
                    last_xp_gain TEXT,
                    last_daily TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, guild_id)
                )
            """)

            # ---- warnings: moderator-issued warnings per user/guild ----
            await db.execute("""
                CREATE TABLE IF NOT EXISTS warnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    moderator_id INTEGER NOT NULL,
                    reason TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # ---- infractions: auto-mod infractions (spam, banned words) ----
            await db.execute("""
                CREATE TABLE IF NOT EXISTS infractions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    details TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # ---- reaction_roles: emoji-to-role mappings for reaction-role messages ----
            await db.execute("""
                CREATE TABLE IF NOT EXISTS reaction_roles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    emoji TEXT NOT NULL,
                    role_id INTEGER NOT NULL,
                    UNIQUE(message_id, emoji)
                )
            """)

            # ---- guild_config: per-guild bot configuration and settings ----
            await db.execute("""
                CREATE TABLE IF NOT EXISTS guild_config (
                    guild_id INTEGER PRIMARY KEY,
                    welcome_channel_id INTEGER,
                    log_channel_id INTEGER,
                    level_up_channel_id INTEGER,
                    mute_role_id INTEGER,
                    auto_mod_enabled INTEGER DEFAULT 1,
                    leveling_enabled INTEGER DEFAULT 1,
                    welcome_message TEXT DEFAULT 'Bienvenue {user} sur {server}!',
                    goodbye_message TEXT DEFAULT '{user} a quitté le serveur.',
                    level_up_message TEXT DEFAULT 'Félicitations {user}! Tu es maintenant niveau {level}!',
                    prefix TEXT DEFAULT '!',
                    settings TEXT DEFAULT '{}'
                )
            """)

            # ---- tickets: support ticket tracking ----
            await db.execute("""
                CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    subject TEXT,
                    status TEXT DEFAULT 'open',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    closed_at TEXT
                )
            """)

            # ---- reminders: scheduled user reminders ----
            await db.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    message TEXT NOT NULL,
                    remind_at TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # ---- trivia_scores: per-user trivia game statistics ----
            await db.execute("""
                CREATE TABLE IF NOT EXISTS trivia_scores (
                    user_id INTEGER,
                    guild_id INTEGER,
                    correct_answers INTEGER DEFAULT 0,
                    total_questions INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, guild_id)
                )
            """)

            # ---- level_roles: roles automatically granted at specific levels ----
            await db.execute("""
                CREATE TABLE IF NOT EXISTS level_roles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    level INTEGER NOT NULL,
                    role_id INTEGER NOT NULL,
                    UNIQUE(guild_id, level)
                )
            """)

            # =============================================
            # BANNED-WORDS / PROFANITY FILTER TABLES
            # =============================================

            # ---- banned_words: multi-language word list (global + per-guild) ----
            await db.execute("""
                CREATE TABLE IF NOT EXISTS banned_words (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    word TEXT NOT NULL,
                    language TEXT DEFAULT 'all',
                    guild_id INTEGER DEFAULT 0,
                    severity INTEGER DEFAULT 1,
                    added_by INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(word, guild_id)
                )
            """)

            # ---- profanity_infractions: log of every profanity violation ----
            await db.execute("""
                CREATE TABLE IF NOT EXISTS profanity_infractions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    word_used TEXT NOT NULL,
                    message_content TEXT,
                    action_taken TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # ---- user_profanity_stats: aggregated stats for progressive punishment ----
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_profanity_stats (
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    total_infractions INTEGER DEFAULT 0,
                    warnings_count INTEGER DEFAULT 0,
                    mutes_count INTEGER DEFAULT 0,
                    kicks_count INTEGER DEFAULT 0,
                    is_banned INTEGER DEFAULT 0,
                    last_infraction TEXT,
                    PRIMARY KEY (user_id, guild_id)
                )
            """)

            # ---- profanity_config: per-guild punishment thresholds & toggles ----
            await db.execute("""
                CREATE TABLE IF NOT EXISTS profanity_config (
                    guild_id INTEGER PRIMARY KEY,
                    enabled INTEGER DEFAULT 1,
                    warn_threshold INTEGER DEFAULT 3,
                    mute_threshold INTEGER DEFAULT 5,
                    kick_threshold INTEGER DEFAULT 8,
                    ban_threshold INTEGER DEFAULT 10,
                    mute_duration INTEGER DEFAULT 3600,
                    delete_message INTEGER DEFAULT 1,
                    log_infractions INTEGER DEFAULT 1,
                    dm_user INTEGER DEFAULT 1
                )
            """)

            await db.commit()

        # Seed the banned-words table with the default word list
        await self._init_default_banned_words()

    # ===============================
    # USER PROFILES / XP / LEVELLING
    # ===============================

    async def get_user(self, user_id: int, guild_id: int) -> Optional[Dict]:
        """Return user profile dict or None if not found."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def create_user(self, user_id: int, guild_id: int) -> Dict:
        """Create user with defaults. Uses INSERT OR IGNORE (idempotent)."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO users (user_id, guild_id) VALUES (?, ?)",
                (user_id, guild_id)
            )
            await db.commit()
        return await self.get_user(user_id, guild_id)

    async def get_or_create_user(self, user_id: int, guild_id: int) -> Dict:
        """Get user profile, creating if needed. Always returns non-None."""
        user = await self.get_user(user_id, guild_id)
        if not user:
            user = await self.create_user(user_id, guild_id)
        return user

    async def add_xp(self, user_id: int, guild_id: int, xp: int) -> Dict:
        """Add XP and increment message count. Returns updated profile."""
        user = await self.get_or_create_user(user_id, guild_id)
        new_xp = user['xp'] + xp
        new_total_xp = user['total_xp'] + xp
        new_messages = user['messages_count'] + 1

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE users
                SET xp = ?, total_xp = ?, messages_count = ?, last_xp_gain = ?
                WHERE user_id = ? AND guild_id = ?
            """, (new_xp, new_total_xp, new_messages, datetime.now().isoformat(), user_id, guild_id))
            await db.commit()

        return await self.get_user(user_id, guild_id)

    async def set_level(self, user_id: int, guild_id: int, level: int, remaining_xp: int = 0):
        """Set a user's level and optionally reset their current-level XP.

        Typically called by the levelling cog after detecting that a user's
        XP exceeded the threshold for the next level.

        Args:
            user_id: The Discord user ID.
            guild_id: The Discord guild (server) ID.
            level: The new level value to set.
            remaining_xp: XP to carry over into the new level (default 0).
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE users SET level = ?, xp = ?
                WHERE user_id = ? AND guild_id = ?
            """, (level, remaining_xp, user_id, guild_id))
            await db.commit()

    async def get_leaderboard(self, guild_id: int, limit: int = 10) -> List[Dict]:
        """Retrieve the XP leaderboard for a guild.

        Users are sorted by ``total_xp`` in descending order.

        Args:
            guild_id: The Discord guild (server) ID.
            limit: Maximum number of entries to return (default 10).

        Returns:
            A list of user profile dicts, ordered from most to least XP.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM users
                WHERE guild_id = ?
                ORDER BY total_xp DESC
                LIMIT ?
            """, (guild_id, limit)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_rank(self, user_id: int, guild_id: int) -> int:
        """Calculate a user's rank (1-based position) on the XP leaderboard.

        The rank is computed by counting how many users in the same guild
        have strictly more ``total_xp`` than the target user, then adding 1.

        Args:
            user_id: The Discord user ID.
            guild_id: The Discord guild (server) ID.

        Returns:
            The user's 1-based rank, or ``0`` if the user has no record.
        """
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT COUNT(*) + 1 as rank FROM users
                WHERE guild_id = ? AND total_xp > (
                    SELECT total_xp FROM users WHERE user_id = ? AND guild_id = ?
                )
            """, (guild_id, user_id, guild_id)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    # ===============================
    # ECONOMY (COINS / DAILY REWARDS)
    # ===============================

    async def add_coins(self, user_id: int, guild_id: int, amount: int):
        """Add (or subtract) coins from a user's balance.

        The resulting balance is clamped to a minimum of ``0`` so that a
        negative ``amount`` can never push the user below zero coins.

        Args:
            user_id: The Discord user ID.
            guild_id: The Discord guild (server) ID.
            amount: Number of coins to add.  Use a negative value to deduct.
        """
        user = await self.get_or_create_user(user_id, guild_id)
        # Clamp to zero — a user's coin balance must never go negative.
        new_coins = max(0, user['coins'] + amount)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET coins = ? WHERE user_id = ? AND guild_id = ?",
                (new_coins, user_id, guild_id)
            )
            await db.commit()

    async def can_claim_daily(self, user_id: int, guild_id: int) -> bool:
        """Check whether a user is eligible to claim their daily reward.

        A daily reward may be claimed once every 24 hours.  If the user has
        never claimed (``last_daily`` is ``None``), they are always eligible.

        Args:
            user_id: The Discord user ID.
            guild_id: The Discord guild (server) ID.

        Returns:
            ``True`` if at least 24 hours have passed since the last claim
            (or if the user has never claimed), ``False`` otherwise.
        """
        user = await self.get_or_create_user(user_id, guild_id)
        if not user['last_daily']:
            return True
        last_daily = datetime.fromisoformat(user['last_daily'])
        return datetime.now() - last_daily > timedelta(hours=24)

    async def claim_daily(self, user_id: int, guild_id: int, amount: int):
        """Record a daily reward claim, adding coins and updating the timestamp.

        Note:
            The caller is responsible for checking ``can_claim_daily()``
            **before** calling this method.

        Args:
            user_id: The Discord user ID.
            guild_id: The Discord guild (server) ID.
            amount: Number of coins to award for the daily claim.
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE users
                SET coins = coins + ?, last_daily = ?
                WHERE user_id = ? AND guild_id = ?
            """, (amount, datetime.now().isoformat(), user_id, guild_id))
            await db.commit()

    async def get_economy_leaderboard(self, guild_id: int, limit: int = 10) -> List[Dict]:
        """Retrieve the coin leaderboard for a guild.

        Users are sorted by ``coins`` in descending order.

        Args:
            guild_id: The Discord guild (server) ID.
            limit: Maximum number of entries to return (default 10).

        Returns:
            A list of user profile dicts, ordered from richest to poorest.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM users
                WHERE guild_id = ?
                ORDER BY coins DESC
                LIMIT ?
            """, (guild_id, limit)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    # ===============================
    # MODERATION WARNINGS
    # ===============================

    async def add_warning(self, user_id: int, guild_id: int, moderator_id: int, reason: str = None) -> int:
        """Issue a warning to a user and return the updated warning count.

        Args:
            user_id: The Discord user ID receiving the warning.
            guild_id: The Discord guild (server) ID.
            moderator_id: The Discord user ID of the moderator issuing the
                warning.
            reason: Optional human-readable reason for the warning.

        Returns:
            The user's **total** warning count in this guild after the new
            warning has been inserted.
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO warnings (user_id, guild_id, moderator_id, reason)
                VALUES (?, ?, ?, ?)
            """, (user_id, guild_id, moderator_id, reason))
            await db.commit()
        return await self.get_warning_count(user_id, guild_id)

    async def get_warning_count(self, user_id: int, guild_id: int) -> int:
        """Return the total number of warnings for a user in a guild.

        Args:
            user_id: The Discord user ID.
            guild_id: The Discord guild (server) ID.

        Returns:
            An integer count (``0`` if the user has no warnings).
        """
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM warnings WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def get_warnings(self, user_id: int, guild_id: int) -> List[Dict]:
        """Retrieve all warning records for a user in a guild.

        Results are ordered by ``created_at`` descending (most recent first).

        Args:
            user_id: The Discord user ID.
            guild_id: The Discord guild (server) ID.

        Returns:
            A list of warning dicts, each containing ``id``, ``user_id``,
            ``guild_id``, ``moderator_id``, ``reason``, and ``created_at``.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM warnings WHERE user_id = ? AND guild_id = ? ORDER BY created_at DESC",
                (user_id, guild_id)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def clear_warnings(self, user_id: int, guild_id: int):
        """Delete **all** warnings for a user in a guild.

        This is a destructive operation and cannot be undone.

        Args:
            user_id: The Discord user ID whose warnings will be cleared.
            guild_id: The Discord guild (server) ID.
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM warnings WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id)
            )
            await db.commit()

    # ===============================
    # REACTION ROLES
    # ===============================

    async def add_reaction_role(self, guild_id: int, message_id: int, channel_id: int, emoji: str, role_id: int):
        """Register an emoji-to-role mapping for a specific message.

        If a mapping already exists for the same ``(message_id, emoji)``
        pair it will be replaced (``INSERT OR REPLACE``).

        Args:
            guild_id: The Discord guild (server) ID.
            message_id: The ID of the message users react to.
            channel_id: The channel containing the target message.
            emoji: The emoji string (Unicode character or custom emoji name).
            role_id: The Discord role ID to assign/remove on reaction.
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO reaction_roles (guild_id, message_id, channel_id, emoji, role_id)
                VALUES (?, ?, ?, ?, ?)
            """, (guild_id, message_id, channel_id, emoji, role_id))
            await db.commit()

    async def get_reaction_role(self, message_id: int, emoji: str) -> Optional[Dict]:
        """Look up the role mapping for a specific message + emoji pair.

        Args:
            message_id: The ID of the reaction-role message.
            emoji: The emoji string to look up.

        Returns:
            A dict with the mapping details, or ``None`` if no mapping
            exists for this combination.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM reaction_roles WHERE message_id = ? AND emoji = ?",
                (message_id, emoji)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_all_reaction_roles(self, guild_id: int) -> List[Dict]:
        """Retrieve every reaction-role mapping configured for a guild.

        Args:
            guild_id: The Discord guild (server) ID.

        Returns:
            A list of mapping dicts (may be empty).
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM reaction_roles WHERE guild_id = ?",
                (guild_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def remove_reaction_role(self, message_id: int, emoji: str):
        """Delete a reaction-role mapping.

        Args:
            message_id: The ID of the reaction-role message.
            emoji: The emoji string identifying the mapping to remove.
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM reaction_roles WHERE message_id = ? AND emoji = ?",
                (message_id, emoji)
            )
            await db.commit()

    # ===============================
    # GUILD CONFIGURATION
    # ===============================

    async def get_guild_config(self, guild_id: int) -> Dict:
        """Retrieve the configuration for a guild, creating defaults if needed.

        If no configuration row exists for the given guild, a new one is
        automatically inserted with default values and then returned.

        Args:
            guild_id: The Discord guild (server) ID.

        Returns:
            A dict containing all ``guild_config`` columns for this guild.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM guild_config WHERE guild_id = ?",
                (guild_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)

        # No row found — create the default config and recurse once.
        await self.create_guild_config(guild_id)
        return await self.get_guild_config(guild_id)

    async def create_guild_config(self, guild_id: int):
        """Insert a default configuration row for a guild.

        Uses ``INSERT OR IGNORE`` so it is safe to call even if the row
        already exists.

        Args:
            guild_id: The Discord guild (server) ID.
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO guild_config (guild_id) VALUES (?)",
                (guild_id,)
            )
            await db.commit()

    # Whitelist of allowed column names for guild_config to prevent SQL injection.
    # Because update_guild_config() builds its SET clause dynamically from
    # **kwargs keys, an attacker could theoretically inject arbitrary SQL via
    # a crafted key name.  This set acts as a strict allow-list: any key not
    # present here causes a ValueError *before* the query is constructed.
    GUILD_CONFIG_COLUMNS = {
        'welcome_channel_id', 'log_channel_id', 'level_up_channel_id',
        'mute_role_id', 'auto_mod_enabled', 'leveling_enabled',
        'welcome_message', 'goodbye_message', 'level_up_message',
        'prefix', 'settings', 'daily_channel_id', 'daily_message',
    }

    async def update_guild_config(self, guild_id: int, **kwargs):
        """Update one or more configuration fields for a guild.

        Column names provided as keyword arguments are validated against
        ``GUILD_CONFIG_COLUMNS`` to prevent SQL injection through dynamic
        column names.  Values are always passed as parameterised query
        arguments.

        Args:
            guild_id: The Discord guild (server) ID.
            **kwargs: Column-name / value pairs to update.  Every key
                **must** be present in ``GUILD_CONFIG_COLUMNS``.

        Raises:
            ValueError: If any key in ``kwargs`` is not in the allowed
                column whitelist.
        """
        if not kwargs:
            return

        # Security: validate column names against whitelist to prevent SQL injection
        invalid_keys = set(kwargs.keys()) - self.GUILD_CONFIG_COLUMNS
        if invalid_keys:
            raise ValueError(f"Invalid guild_config columns: {invalid_keys}")

        # Build a parameterised SET clause — column names come from the
        # validated whitelist; values are passed as query parameters (?).
        set_clause = ", ".join(f"{key} = ?" for key in kwargs.keys())
        values = list(kwargs.values()) + [guild_id]

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                f"UPDATE guild_config SET {set_clause} WHERE guild_id = ?",
                values
            )
            await db.commit()

    # ===============================
    # SUPPORT TICKETS
    # ===============================

    async def create_ticket(self, guild_id: int, channel_id: int, user_id: int, subject: str = None) -> int:
        """Create a new support ticket and return its database ID.

        Each ticket is associated with a dedicated Discord channel.  The
        ticket starts in ``'open'`` status.

        Args:
            guild_id: The Discord guild (server) ID.
            channel_id: The ID of the Discord channel created for this ticket.
            user_id: The Discord user ID who opened the ticket.
            subject: Optional short description of the issue.

        Returns:
            The auto-incremented primary key (``id``) of the new ticket row.
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO tickets (guild_id, channel_id, user_id, subject)
                VALUES (?, ?, ?, ?)
            """, (guild_id, channel_id, user_id, subject))
            await db.commit()
            return cursor.lastrowid

    async def close_ticket(self, ticket_id: int):
        """Mark a ticket as closed and record the closure timestamp.

        Args:
            ticket_id: The database primary key of the ticket to close.
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE tickets SET status = 'closed', closed_at = ?
                WHERE id = ?
            """, (datetime.now().isoformat(), ticket_id))
            await db.commit()

    async def get_ticket_by_channel(self, channel_id: int) -> Optional[Dict]:
        """Find the open ticket associated with a Discord channel.

        Only tickets with ``status = 'open'`` are returned; closed tickets
        in the same channel are ignored.

        Args:
            channel_id: The Discord channel ID to search for.

        Returns:
            The ticket dict if an open ticket exists in this channel,
            otherwise ``None``.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM tickets WHERE channel_id = ? AND status = 'open'",
                (channel_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    # ===============================
    # REMINDERS
    # ===============================

    async def add_reminder(self, user_id: int, channel_id: int, message: str, remind_at: datetime) -> int:
        """Schedule a new reminder.

        Args:
            user_id: The Discord user ID who set the reminder.
            channel_id: The channel where the reminder should be posted.
            message: The reminder text to display when the time comes.
            remind_at: The UTC datetime at which the reminder should fire.

        Returns:
            The auto-incremented primary key (``id``) of the new reminder.
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO reminders (user_id, channel_id, message, remind_at)
                VALUES (?, ?, ?, ?)
            """, (user_id, channel_id, message, remind_at.isoformat()))
            await db.commit()
            return cursor.lastrowid

    async def get_due_reminders(self) -> List[Dict]:
        """Retrieve all reminders whose scheduled time has passed.

        A background task should call this periodically, deliver each
        reminder to its channel, and then call ``delete_reminder()`` to
        clean it up.

        Returns:
            A list of reminder dicts whose ``remind_at`` is at or before
            the current time.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM reminders WHERE remind_at <= ?",
                (datetime.now().isoformat(),)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def delete_reminder(self, reminder_id: int):
        """Delete a reminder after it has been delivered.

        Args:
            reminder_id: The primary key of the reminder to delete.
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
            await db.commit()

    # ===============================
    # TRIVIA SCORES
    # ===============================

    async def update_trivia_score(self, user_id: int, guild_id: int, correct: bool):
        """Record the result of a single trivia question for a user.

        Uses an ``INSERT ... ON CONFLICT ... DO UPDATE`` (upsert) so that
        the row is created automatically on the user's first trivia answer.

        Args:
            user_id: The Discord user ID.
            guild_id: The Discord guild (server) ID.
            correct: ``True`` if the user answered correctly, ``False``
                otherwise.  ``total_questions`` is always incremented;
                ``correct_answers`` is only incremented when ``correct``
                is ``True``.
        """
        async with aiosqlite.connect(self.db_path) as db:
            # The ternary (1 if correct else 0) converts the bool to an
            # integer suitable for both the INSERT and the ON CONFLICT
            # UPDATE increment.
            await db.execute("""
                INSERT INTO trivia_scores (user_id, guild_id, correct_answers, total_questions)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(user_id, guild_id) DO UPDATE SET
                    correct_answers = correct_answers + ?,
                    total_questions = total_questions + 1
            """, (user_id, guild_id, 1 if correct else 0, 1 if correct else 0))
            await db.commit()

    async def get_trivia_leaderboard(self, guild_id: int, limit: int = 10) -> List[Dict]:
        """Retrieve the trivia leaderboard for a guild.

        Users are sorted by ``correct_answers`` in descending order.

        Args:
            guild_id: The Discord guild (server) ID.
            limit: Maximum number of entries to return (default 10).

        Returns:
            A list of trivia-score dicts, ordered from most to fewest
            correct answers.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM trivia_scores
                WHERE guild_id = ?
                ORDER BY correct_answers DESC
                LIMIT ?
            """, (guild_id, limit)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    # ===============================
    # LEVEL ROLES
    # ===============================

    async def add_level_role(self, guild_id: int, level: int, role_id: int):
        """Map a Discord role to a specific level for automatic assignment.

        When a user reaches the specified level, the bot can grant them
        this role automatically.  If a mapping already exists for the same
        ``(guild_id, level)`` pair, it is replaced.

        Args:
            guild_id: The Discord guild (server) ID.
            level: The level at which the role should be granted.
            role_id: The Discord role ID to assign.
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO level_roles (guild_id, level, role_id)
                VALUES (?, ?, ?)
            """, (guild_id, level, role_id))
            await db.commit()

    async def get_level_roles(self, guild_id: int) -> List[Dict]:
        """Retrieve all level-role mappings for a guild, sorted by level.

        Args:
            guild_id: The Discord guild (server) ID.

        Returns:
            A list of mapping dicts ordered by ``level`` ascending.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM level_roles WHERE guild_id = ? ORDER BY level ASC",
                (guild_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_role_for_level(self, guild_id: int, level: int) -> Optional[int]:
        """Return the role ID mapped to a specific level, if any.

        Args:
            guild_id: The Discord guild (server) ID.
            level: The level to look up.

        Returns:
            The ``role_id`` integer, or ``None`` if no role is mapped to
            this level.
        """
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT role_id FROM level_roles WHERE guild_id = ? AND level = ?",
                (guild_id, level)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def remove_level_role(self, guild_id: int, level: int):
        """Remove the level-role mapping for a specific level.

        Args:
            guild_id: The Discord guild (server) ID.
            level: The level whose role mapping should be deleted.
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM level_roles WHERE guild_id = ? AND level = ?",
                (guild_id, level)
            )
            await db.commit()


    # ===============================
    # BANNED WORDS MANAGEMENT
    # ===============================

    async def _init_default_banned_words(self):
        """Seed the ``banned_words`` table with a built-in multi-language word list.

        Words are inserted as **global** entries (``guild_id = 0``) so they
        apply to every guild by default.  ``INSERT OR IGNORE`` ensures that
        re-running this method (e.g. on every bot restart) never creates
        duplicates.

        The seed list covers English, French, Spanish, German, Italian,
        Portuguese, and transliterated Arabic profanity, each tagged with a
        language code and a severity level (1 = mild, 5 = extreme).
        """
        default_words = [
            # English
            ("fuck", "en", 3), ("fucking", "en", 3), ("fucker", "en", 3),
            ("shit", "en", 2), ("bullshit", "en", 2), ("shitty", "en", 2),
            ("bitch", "en", 2), ("asshole", "en", 3), ("bastard", "en", 2),
            ("dick", "en", 2), ("cock", "en", 2), ("pussy", "en", 2),
            ("slut", "en", 3), ("whore", "en", 3), ("cunt", "en", 3),
            ("retard", "en", 3), ("retarded", "en", 3),
            ("faggot", "en", 4), ("fag", "en", 4),
            ("nigger", "en", 5), ("nigga", "en", 4),
            ("kys", "en", 5), ("kill yourself", "en", 5),

            # French
            ("merde", "fr", 1), ("putain", "fr", 2), ("ptn", "fr", 2),
            ("salope", "fr", 3), ("connard", "fr", 2), ("connasse", "fr", 2),
            ("enculé", "fr", 3), ("encule", "fr", 3), ("nique", "fr", 3),
            ("niquer", "fr", 3), ("ntm", "fr", 4), ("nique ta mère", "fr", 4),
            ("fdp", "fr", 4), ("fils de pute", "fr", 4),
            ("pd", "fr", 3), ("pédé", "fr", 3), ("pédale", "fr", 3),
            ("tapette", "fr", 3), ("batard", "fr", 2), ("bâtard", "fr", 2),
            ("bite", "fr", 2), ("couilles", "fr", 1),
            ("ta gueule", "fr", 2), ("tg", "fr", 2), ("ferme ta gueule", "fr", 2),
            ("crétin", "fr", 1), ("abruti", "fr", 1), ("débile", "fr", 2),
            ("imbécile", "fr", 1), ("ordure", "fr", 2),
            ("pétasse", "fr", 3), ("pouffiasse", "fr", 3),
            ("salaud", "fr", 2), ("enfoiré", "fr", 2),
            ("bouffon", "fr", 1), ("gogol", "fr", 2),
            ("attardé", "fr", 3), ("mongol", "fr", 4), ("trisomique", "fr", 4),
            ("nègre", "fr", 5), ("bougnoule", "fr", 5),
            ("va te faire foutre", "fr", 3), ("vtff", "fr", 3),

            # Spanish
            ("puta", "es", 3), ("mierda", "es", 2), ("coño", "es", 2),
            ("joder", "es", 2), ("cabron", "es", 2), ("cabrón", "es", 2),
            ("pendejo", "es", 2), ("maricón", "es", 4), ("maricon", "es", 4),
            ("hijo de puta", "es", 4), ("polla", "es", 2), ("gilipollas", "es", 2),

            # German
            ("scheiße", "de", 2), ("scheisse", "de", 2), ("arschloch", "de", 3),
            ("hurensohn", "de", 4), ("fotze", "de", 3), ("wichser", "de", 3),
            ("schwuchtel", "de", 4), ("missgeburt", "de", 4),

            # Italian
            ("cazzo", "it", 2), ("merda", "it", 2), ("stronzo", "it", 2),
            ("puttana", "it", 3), ("vaffanculo", "it", 3), ("frocio", "it", 4),

            # Portuguese
            ("porra", "pt", 2), ("caralho", "pt", 2), ("filho da puta", "pt", 4),
            ("viado", "pt", 4), ("puta", "pt", 3), ("merda", "pt", 2),

            # Transliterated Arabic
            ("kelb", "ar", 2), ("kess", "ar", 3), ("sharmouta", "ar", 4),
            ("ibn el sharmouta", "ar", 5), ("zebi", "ar", 3), ("nik", "ar", 3),
        ]

        async with aiosqlite.connect(self.db_path) as db:
            for word, lang, severity in default_words:
                await db.execute("""
                    INSERT OR IGNORE INTO banned_words (word, language, guild_id, severity)
                    VALUES (?, ?, 0, ?)
                """, (word.lower(), lang, severity))
            await db.commit()

    async def add_banned_word(self, word: str, language: str = "all", guild_id: int = 0,
                             severity: int = 1, added_by: int = None) -> bool:
        """Add a new word to the banned-words list.

        The word is stored lower-cased to ensure case-insensitive matching.
        If the word already exists for the same ``guild_id`` (due to the
        ``UNIQUE(word, guild_id)`` constraint), the insert is silently
        skipped and ``False`` is returned.

        Args:
            word: The word or phrase to ban.
            language: ISO 639-1 language code (e.g. ``'en'``, ``'fr'``) or
                ``'all'`` to match regardless of language filtering.
            guild_id: The guild this word applies to.  Use ``0`` for a
                global entry that applies to every guild.
            severity: Severity level from 1 (mild) to 5 (extreme).
            added_by: The Discord user ID of the moderator who added the
                word (optional, for auditing).

        Returns:
            ``True`` if the word was inserted successfully, ``False`` if it
            already existed or another error occurred.
        """
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute("""
                    INSERT INTO banned_words (word, language, guild_id, severity, added_by)
                    VALUES (?, ?, ?, ?, ?)
                """, (word.lower(), language, guild_id, severity, added_by))
                await db.commit()
                return True
            except Exception:
                return False

    async def remove_banned_word(self, word: str, guild_id: int = 0) -> bool:
        """Remove a word from the banned-words list.

        Args:
            word: The word to remove (matched case-insensitively).
            guild_id: The guild scope to remove from (``0`` for global).

        Returns:
            ``True`` if a row was deleted, ``False`` if the word was not
            found for the given ``guild_id``.
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM banned_words WHERE word = ? AND guild_id = ?",
                (word.lower(), guild_id)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def get_banned_words(self, guild_id: int = 0, language: str = None) -> List[Dict]:
        """Retrieve all banned words applicable to a guild.

        This always includes **global** entries (``guild_id = 0``) in
        addition to any guild-specific entries.  Results are ordered by
        severity descending so that the most severe words appear first.

        Args:
            guild_id: The Discord guild ID.  Global words (``guild_id = 0``)
                are always included alongside guild-specific ones.
            language: If provided, only words tagged with this language code
                (or ``'all'``) are returned.  If ``None``, all languages
                are included.

        Returns:
            A list of banned-word dicts sorted by severity (highest first).
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if language:
                # Filter by language — include entries marked 'all' as well.
                async with db.execute("""
                    SELECT * FROM banned_words
                    WHERE (guild_id = 0 OR guild_id = ?)
                    AND (language = ? OR language = 'all')
                    ORDER BY severity DESC
                """, (guild_id, language)) as cursor:
                    rows = await cursor.fetchall()
            else:
                # No language filter — return every language.
                async with db.execute("""
                    SELECT * FROM banned_words
                    WHERE guild_id = 0 OR guild_id = ?
                    ORDER BY severity DESC
                """, (guild_id,)) as cursor:
                    rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_banned_words_list(self, guild_id: int = 0) -> List[str]:
        """Return a flat list of banned-word strings (convenience wrapper).

        This is a lightweight alternative to ``get_banned_words()`` when
        only the word strings are needed (e.g. for quick membership checks).

        Args:
            guild_id: The Discord guild ID (``0`` for global only).

        Returns:
            A list of lower-cased word strings.
        """
        words = await self.get_banned_words(guild_id)
        return [w['word'] for w in words]

    async def check_message_for_profanity(self, content: str, guild_id: int = 0) -> Optional[Dict]:
        """Scan a message for banned words and return the first match.

        The check uses two strategies for each banned word:

        1. **Word-boundary regex** (``\\b...\\b``) — preferred because it
           avoids false positives (e.g. "class" matching inside
           "classification").
        2. **Substring containment** — catches creative evasion attempts
           where word boundaries are absent (e.g. concatenated words).

        If a match is found the corresponding banned-word dict (including
        its severity) is returned immediately, so the caller can decide
        on the appropriate punishment.

        Args:
            content: The raw message text to check.
            guild_id: The guild context (so guild-specific words are
                included in the scan).

        Returns:
            The matched banned-word dict, or ``None`` if the message is
            clean.
        """
        content_lower = content.lower()
        words = await self.get_banned_words(guild_id)

        for word_data in words:
            word = word_data['word']
            # Strategy 1: word-boundary match to reduce false positives.
            import re
            pattern = r'\b' + re.escape(word) + r'\b'
            if re.search(pattern, content_lower):
                return word_data

            # Strategy 2: plain substring check for evasion variants
            # (e.g. words glued together without spaces/punctuation).
            if word in content_lower:
                return word_data

        return None

    # ===============================
    # PROFANITY INFRACTIONS
    # ===============================

    async def add_profanity_infraction(self, user_id: int, guild_id: int,
                                       word_used: str, message_content: str,
                                       action_taken: str) -> Dict:
        """Record a profanity infraction and update the user's aggregate stats.

        This method performs three operations in a single transaction:

        1. Insert a new row into ``profanity_infractions`` (the audit log).
        2. Upsert ``user_profanity_stats`` to increment
           ``total_infractions`` and update ``last_infraction``.
        3. Increment the action-specific counter (``warnings_count``,
           ``mutes_count``, ``kicks_count``, or set ``is_banned``).

        Args:
            user_id: The offending Discord user ID.
            guild_id: The Discord guild (server) ID.
            word_used: The banned word that was detected.
            message_content: The original message text (truncated to 500
                characters before storage to limit database bloat).
            action_taken: One of ``"warn"``, ``"mute"``, ``"kick"``, or
                ``"ban"`` — the punishment that was applied.

        Returns:
            The user's updated profanity stats dict (as returned by
            ``get_user_profanity_stats()``).
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Step 1: Log the infraction (message_content is capped at 500 chars).
            await db.execute("""
                INSERT INTO profanity_infractions
                (user_id, guild_id, word_used, message_content, action_taken)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, guild_id, word_used, message_content[:500], action_taken))

            # Step 2: Upsert aggregate stats — create row on first offence,
            # otherwise increment the running total.
            await db.execute("""
                INSERT INTO user_profanity_stats (user_id, guild_id, total_infractions, last_infraction)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(user_id, guild_id) DO UPDATE SET
                    total_infractions = total_infractions + 1,
                    last_infraction = ?
            """, (user_id, guild_id, datetime.now().isoformat(), datetime.now().isoformat()))

            # Step 3: Increment the counter specific to the punishment applied.
            if action_taken == "warn":
                await db.execute("""
                    UPDATE user_profanity_stats
                    SET warnings_count = warnings_count + 1
                    WHERE user_id = ? AND guild_id = ?
                """, (user_id, guild_id))
            elif action_taken == "mute":
                await db.execute("""
                    UPDATE user_profanity_stats
                    SET mutes_count = mutes_count + 1
                    WHERE user_id = ? AND guild_id = ?
                """, (user_id, guild_id))
            elif action_taken == "kick":
                await db.execute("""
                    UPDATE user_profanity_stats
                    SET kicks_count = kicks_count + 1
                    WHERE user_id = ? AND guild_id = ?
                """, (user_id, guild_id))
            elif action_taken == "ban":
                await db.execute("""
                    UPDATE user_profanity_stats
                    SET is_banned = 1
                    WHERE user_id = ? AND guild_id = ?
                """, (user_id, guild_id))

            await db.commit()

        return await self.get_user_profanity_stats(user_id, guild_id)

    async def get_user_profanity_stats(self, user_id: int, guild_id: int) -> Dict:
        """Retrieve a user's aggregated profanity infraction statistics.

        If the user has no record yet (i.e. zero infractions), a default
        dict with all counters set to zero is returned rather than ``None``,
        making it safe for callers to read any key without a null check.

        Args:
            user_id: The Discord user ID.
            guild_id: The Discord guild (server) ID.

        Returns:
            A dict with keys: ``user_id``, ``guild_id``,
            ``total_infractions``, ``warnings_count``, ``mutes_count``,
            ``kicks_count``, ``is_banned``, ``last_infraction``.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM user_profanity_stats
                WHERE user_id = ? AND guild_id = ?
            """, (user_id, guild_id)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)
                # Return a zeroed-out default so callers never deal with None.
                return {
                    'user_id': user_id,
                    'guild_id': guild_id,
                    'total_infractions': 0,
                    'warnings_count': 0,
                    'mutes_count': 0,
                    'kicks_count': 0,
                    'is_banned': 0,
                    'last_infraction': None
                }

    async def get_user_profanity_history(self, user_id: int, guild_id: int, limit: int = 10) -> List[Dict]:
        """Retrieve the detailed infraction history for a user.

        Results are ordered by ``created_at`` descending (most recent first).

        Args:
            user_id: The Discord user ID.
            guild_id: The Discord guild (server) ID.
            limit: Maximum number of records to return (default 10).

        Returns:
            A list of infraction dicts, each containing ``id``, ``user_id``,
            ``guild_id``, ``word_used``, ``message_content``,
            ``action_taken``, and ``created_at``.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM profanity_infractions
                WHERE user_id = ? AND guild_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (user_id, guild_id, limit)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def reset_user_profanity_stats(self, user_id: int, guild_id: int):
        """Reset all profanity counters for a user to zero.

        This zeroes out ``total_infractions``, ``warnings_count``,
        ``mutes_count``, ``kicks_count``, and ``is_banned`` but does
        **not** delete the detailed infraction history (those rows remain
        in ``profanity_infractions`` for auditing purposes).

        Args:
            user_id: The Discord user ID whose stats will be reset.
            guild_id: The Discord guild (server) ID.
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE user_profanity_stats
                SET total_infractions = 0, warnings_count = 0,
                    mutes_count = 0, kicks_count = 0, is_banned = 0
                WHERE user_id = ? AND guild_id = ?
            """, (user_id, guild_id))
            await db.commit()

    # ===============================
    # PROFANITY PUNISHMENT CONFIG
    # ===============================

    async def get_profanity_config(self, guild_id: int) -> Dict:
        """Retrieve the profanity punishment configuration for a guild.

        If no configuration row exists yet, a default one is created
        automatically (all thresholds at their table-level defaults) and
        then returned.

        Args:
            guild_id: The Discord guild (server) ID.

        Returns:
            A dict with keys: ``guild_id``, ``enabled``,
            ``warn_threshold``, ``mute_threshold``, ``kick_threshold``,
            ``ban_threshold``, ``mute_duration``, ``delete_message``,
            ``log_infractions``, ``dm_user``.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM profanity_config WHERE guild_id = ?",
                (guild_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)

            # No row found — insert default config and recurse once.
            await db.execute(
                "INSERT OR IGNORE INTO profanity_config (guild_id) VALUES (?)",
                (guild_id,)
            )
            await db.commit()

        return await self.get_profanity_config(guild_id)

    # Whitelist of allowed column names for profanity_config to prevent SQL
    # injection.  Same rationale as GUILD_CONFIG_COLUMNS — see the detailed
    # comment above that constant for the security explanation.
    PROFANITY_CONFIG_COLUMNS = {
        'enabled', 'warn_threshold', 'mute_threshold', 'kick_threshold',
        'ban_threshold', 'mute_duration', 'delete_message',
        'log_infractions', 'dm_user',
    }

    async def update_profanity_config(self, guild_id: int, **kwargs):
        """Update one or more profanity punishment settings for a guild.

        Column names provided as keyword arguments are validated against
        ``PROFANITY_CONFIG_COLUMNS`` to prevent SQL injection.  Values are
        always passed as parameterised query arguments.

        Args:
            guild_id: The Discord guild (server) ID.
            **kwargs: Column-name / value pairs to update.  Every key
                **must** be present in ``PROFANITY_CONFIG_COLUMNS``.

        Raises:
            ValueError: If any key in ``kwargs`` is not in the allowed
                column whitelist.
        """
        if not kwargs:
            return

        # Security: validate column names against whitelist to prevent SQL injection
        invalid_keys = set(kwargs.keys()) - self.PROFANITY_CONFIG_COLUMNS
        if invalid_keys:
            raise ValueError(f"Invalid profanity_config columns: {invalid_keys}")

        # Ensure a config row exists before attempting the UPDATE.
        await self.get_profanity_config(guild_id)

        # Build a parameterised SET clause — column names come from the
        # validated whitelist; values are passed as query parameters (?).
        set_clause = ", ".join(f"{key} = ?" for key in kwargs.keys())
        values = list(kwargs.values()) + [guild_id]

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                f"UPDATE profanity_config SET {set_clause} WHERE guild_id = ?",
                values
            )
            await db.commit()

    async def determine_punishment(self, user_id: int, guild_id: int) -> str:
        """Determine the appropriate punishment based on a user's infraction history.

        The decision follows a progressive escalation model.  Thresholds
        are read from the guild's ``profanity_config``; the user's current
        ``total_infractions`` count is compared against each threshold from
        most severe (ban) to least severe (warn).

        Escalation order (checked top-to-bottom):
            1. ``total_infractions >= ban_threshold``  -> ``"ban"``
            2. ``total_infractions >= kick_threshold`` -> ``"kick"``
            3. ``total_infractions >= mute_threshold`` -> ``"mute"``
            4. Otherwise                               -> ``"warn"``

        Args:
            user_id: The Discord user ID.
            guild_id: The Discord guild (server) ID.

        Returns:
            One of ``"ban"``, ``"kick"``, ``"mute"``, or ``"warn"``.
        """
        stats = await self.get_user_profanity_stats(user_id, guild_id)
        config = await self.get_profanity_config(guild_id)

        infractions = stats['total_infractions']

        # Check thresholds from most to least severe.
        if infractions >= config['ban_threshold']:
            return "ban"
        elif infractions >= config['kick_threshold']:
            return "kick"
        elif infractions >= config['mute_threshold']:
            return "mute"
        elif infractions >= config['warn_threshold']:
            return "warn"
        else:
            return "warn"  # Always at least issue a warning

    async def get_profanity_leaderboard(self, guild_id: int, limit: int = 10) -> List[Dict]:
        """Retrieve the profanity infraction leaderboard for a guild.

        Users are sorted by ``total_infractions`` in descending order
        (worst offenders first).  This is primarily intended for moderation
        dashboards and audit reports.

        Args:
            guild_id: The Discord guild (server) ID.
            limit: Maximum number of entries to return (default 10).

        Returns:
            A list of profanity-stats dicts, ordered from most to fewest
            infractions.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM user_profanity_stats
                WHERE guild_id = ?
                ORDER BY total_infractions DESC
                LIMIT ?
            """, (guild_id, limit)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Module-level singleton instance.
#
# All other modules should import and use this instance:
#
#     from utils.database import db
#     await db.init()           # once at startup
#     user = await db.get_user(...)
#
# Do NOT instantiate Database() elsewhere unless you need an isolated
# database (e.g. for testing with a separate in-memory SQLite).
# ---------------------------------------------------------------------------
db = Database()
