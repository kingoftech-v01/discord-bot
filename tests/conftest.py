"""
Pytest configuration and shared fixtures for all test suites.

This module provides:
    - Path setup so that bot modules (``config``, ``utils.database``, etc.) can be
      imported from any test file without manual ``sys.path`` manipulation.
    - Database fixtures (``temp_db_path``, ``initialized_db``) that create a
      temporary SQLite file with the full bot schema for each test.
    - Sample data fixtures (``sample_users``, ``sample_banned_words``) used by
      multiple test modules.
    - Mock Discord object fixtures (``mock_discord_user``, ``mock_discord_guild``,
      ``mock_discord_message``) that simulate Discord.py models so that cog logic
      can be tested without a live Discord connection.

All async fixtures use ``pytest-asyncio`` with ``asyncio_mode = auto`` (set in
``pytest.ini``), so the ``@pytest.mark.asyncio`` decorator is only required on
test *functions*, not on async fixtures.
"""
import os
import sys
import pytest
import tempfile
import aiosqlite

# Add the project root to ``sys.path`` so that ``import config`` and
# ``from utils.database import db`` work inside test files.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def temp_db_path():
    """Create a temporary database file path."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        yield f.name
    os.unlink(f.name)


@pytest.fixture
async def initialized_db(temp_db_path):
    """Create an initialized database with tables."""
    async with aiosqlite.connect(temp_db_path) as db:
        # Users table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER,
                guild_id INTEGER,
                username TEXT,
                level INTEGER DEFAULT 1,
                xp INTEGER DEFAULT 0,
                total_xp INTEGER DEFAULT 0,
                messages_count INTEGER DEFAULT 0,
                balance INTEGER DEFAULT 0,
                daily_streak INTEGER DEFAULT 0,
                last_daily TEXT,
                last_message TEXT,
                joined_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, guild_id)
            )
        ''')

        # Warnings table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                guild_id INTEGER,
                moderator_id INTEGER,
                reason TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Banned words table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS banned_words (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word TEXT NOT NULL,
                language TEXT DEFAULT 'all',
                severity INTEGER DEFAULT 2,
                guild_id INTEGER DEFAULT 0
            )
        ''')

        # Profanity config table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS profanity_config (
                guild_id INTEGER PRIMARY KEY,
                enabled INTEGER DEFAULT 1,
                warn_threshold INTEGER DEFAULT 3,
                mute_threshold INTEGER DEFAULT 5,
                kick_threshold INTEGER DEFAULT 8,
                ban_threshold INTEGER DEFAULT 10,
                mute_duration INTEGER DEFAULT 3600,
                delete_message INTEGER DEFAULT 1,
                dm_user INTEGER DEFAULT 1,
                log_channel INTEGER DEFAULT 0,
                exempt_roles TEXT DEFAULT ''
            )
        ''')

        # Profanity infractions table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS profanity_infractions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                guild_id INTEGER,
                word_detected TEXT,
                original_message TEXT,
                channel_id INTEGER,
                action_taken TEXT,
                infraction_count INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # User profanity stats table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS user_profanity_stats (
                user_id INTEGER,
                guild_id INTEGER,
                total_infractions INTEGER DEFAULT 0,
                warnings_count INTEGER DEFAULT 0,
                mutes_count INTEGER DEFAULT 0,
                kicks_count INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0,
                last_infraction TEXT,
                PRIMARY KEY (user_id, guild_id)
            )
        ''')

        # Level roles table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS level_roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                level INTEGER,
                role_id INTEGER,
                UNIQUE(guild_id, level)
            )
        ''')

        # Guild config table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS guild_config (
                guild_id INTEGER PRIMARY KEY,
                prefix TEXT DEFAULT '!',
                welcome_channel INTEGER DEFAULT 0,
                log_channel INTEGER DEFAULT 0,
                welcome_message TEXT DEFAULT '',
                goodbye_message TEXT DEFAULT '',
                level_up_message TEXT DEFAULT '',
                auto_mod_enabled INTEGER DEFAULT 1,
                leveling_enabled INTEGER DEFAULT 1
            )
        ''')

        await db.commit()

    yield temp_db_path


@pytest.fixture
def sample_users():
    """Sample user data for testing."""
    return [
        {
            'user_id': 123456789,
            'guild_id': 987654321,
            'username': 'TestUser1',
            'level': 5,
            'xp': 50,
            'total_xp': 500,
            'balance': 1000,
        },
        {
            'user_id': 234567890,
            'guild_id': 987654321,
            'username': 'TestUser2',
            'level': 10,
            'xp': 100,
            'total_xp': 2000,
            'balance': 2500,
        },
        {
            'user_id': 345678901,
            'guild_id': 987654321,
            'username': 'TestUser3',
            'level': 1,
            'xp': 0,
            'total_xp': 0,
            'balance': 0,
        },
    ]


@pytest.fixture
def sample_banned_words():
    """Sample banned words for testing."""
    return [
        {'word': 'badword', 'language': 'en', 'severity': 3},
        {'word': 'insult', 'language': 'en', 'severity': 2},
        {'word': 'grosmot', 'language': 'fr', 'severity': 3},
        {'word': 'merde', 'language': 'fr', 'severity': 2},
    ]


@pytest.fixture
def mock_discord_user():
    """Mock Discord user object."""
    from unittest.mock import MagicMock

    user = MagicMock()
    user.id = 123456789
    user.name = 'TestUser'
    user.discriminator = '1234'
    user.display_name = 'Test User'
    user.bot = False
    user.mention = '<@123456789>'

    return user


@pytest.fixture
def mock_discord_guild():
    """Mock Discord guild object."""
    from unittest.mock import MagicMock

    guild = MagicMock()
    guild.id = 987654321
    guild.name = 'Test Server'
    guild.member_count = 100

    return guild


@pytest.fixture
def mock_discord_message():
    """Mock Discord message object."""
    from unittest.mock import MagicMock, AsyncMock

    message = MagicMock()
    message.id = 111111111
    message.content = 'Test message content'
    message.author = MagicMock()
    message.author.id = 123456789
    message.author.name = 'TestUser'
    message.author.bot = False
    message.guild = MagicMock()
    message.guild.id = 987654321
    message.channel = MagicMock()
    message.channel.id = 555555555
    message.delete = AsyncMock()
    message.reply = AsyncMock()

    return message
