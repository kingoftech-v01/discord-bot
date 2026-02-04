"""
Tests for the database module.
"""
import pytest
import aiosqlite
import tempfile
import os
from pathlib import Path


class TestDatabase:
    """Test database operations."""

    @pytest.fixture
    async def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        async with aiosqlite.connect(db_path) as db:
            # Create tables
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
                    joined_at TEXT,
                    PRIMARY KEY (user_id, guild_id)
                )
            ''')
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
            await db.execute('''
                CREATE TABLE IF NOT EXISTS banned_words (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    word TEXT NOT NULL,
                    language TEXT DEFAULT 'all',
                    severity INTEGER DEFAULT 2,
                    guild_id INTEGER DEFAULT 0
                )
            ''')
            await db.commit()

        yield db_path

        # Cleanup
        os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_create_user(self, temp_db):
        """Test creating a new user."""
        async with aiosqlite.connect(temp_db) as db:
            await db.execute(
                'INSERT INTO users (user_id, guild_id, username) VALUES (?, ?, ?)',
                (123456789, 987654321, 'TestUser')
            )
            await db.commit()

            cursor = await db.execute(
                'SELECT * FROM users WHERE user_id = ? AND guild_id = ?',
                (123456789, 987654321)
            )
            user = await cursor.fetchone()

            assert user is not None
            assert user[2] == 'TestUser'
            assert user[3] == 1  # level
            assert user[4] == 0  # xp

    @pytest.mark.asyncio
    async def test_update_user_xp(self, temp_db):
        """Test updating user XP."""
        async with aiosqlite.connect(temp_db) as db:
            # Create user
            await db.execute(
                'INSERT INTO users (user_id, guild_id, username, xp, total_xp) VALUES (?, ?, ?, ?, ?)',
                (123456789, 987654321, 'TestUser', 0, 0)
            )
            await db.commit()

            # Add XP
            await db.execute(
                'UPDATE users SET xp = xp + ?, total_xp = total_xp + ? WHERE user_id = ? AND guild_id = ?',
                (50, 50, 123456789, 987654321)
            )
            await db.commit()

            cursor = await db.execute(
                'SELECT xp, total_xp FROM users WHERE user_id = ? AND guild_id = ?',
                (123456789, 987654321)
            )
            result = await cursor.fetchone()

            assert result[0] == 50  # xp
            assert result[1] == 50  # total_xp

    @pytest.mark.asyncio
    async def test_level_up_calculation(self, temp_db):
        """Test level up calculation."""
        # Level formula: base_xp * (factor ^ (level - 1))
        base_xp = 100
        factor = 1.5

        def xp_for_level(level):
            return int(base_xp * (factor ** (level - 1)))

        assert xp_for_level(1) == 100
        assert xp_for_level(2) == 150
        assert xp_for_level(3) == 225
        assert xp_for_level(5) == int(100 * (1.5 ** 4))

    @pytest.mark.asyncio
    async def test_add_warning(self, temp_db):
        """Test adding a warning."""
        async with aiosqlite.connect(temp_db) as db:
            await db.execute(
                'INSERT INTO warnings (user_id, guild_id, moderator_id, reason) VALUES (?, ?, ?, ?)',
                (123456789, 987654321, 111111111, 'Test warning')
            )
            await db.commit()

            cursor = await db.execute(
                'SELECT COUNT(*) FROM warnings WHERE user_id = ? AND guild_id = ?',
                (123456789, 987654321)
            )
            count = await cursor.fetchone()

            assert count[0] == 1

    @pytest.mark.asyncio
    async def test_warning_count(self, temp_db):
        """Test counting user warnings."""
        async with aiosqlite.connect(temp_db) as db:
            # Add multiple warnings
            for i in range(3):
                await db.execute(
                    'INSERT INTO warnings (user_id, guild_id, moderator_id, reason) VALUES (?, ?, ?, ?)',
                    (123456789, 987654321, 111111111, f'Warning {i+1}')
                )
            await db.commit()

            cursor = await db.execute(
                'SELECT COUNT(*) FROM warnings WHERE user_id = ? AND guild_id = ?',
                (123456789, 987654321)
            )
            count = await cursor.fetchone()

            assert count[0] == 3

    @pytest.mark.asyncio
    async def test_banned_word_check(self, temp_db):
        """Test banned word detection."""
        async with aiosqlite.connect(temp_db) as db:
            # Add banned words
            await db.execute(
                'INSERT INTO banned_words (word, language, severity) VALUES (?, ?, ?)',
                ('badword', 'en', 3)
            )
            await db.execute(
                'INSERT INTO banned_words (word, language, severity) VALUES (?, ?, ?)',
                ('grosmot', 'fr', 2)
            )
            await db.commit()

            # Check for banned words
            cursor = await db.execute('SELECT word FROM banned_words')
            words = [row[0] for row in await cursor.fetchall()]

            message = "This contains a badword in it"
            detected = [w for w in words if w in message.lower()]

            assert len(detected) == 1
            assert detected[0] == 'badword'

    @pytest.mark.asyncio
    async def test_leaderboard_query(self, temp_db):
        """Test leaderboard query."""
        async with aiosqlite.connect(temp_db) as db:
            # Create multiple users
            users_data = [
                (1, 100, 'User1', 5, 500),
                (2, 100, 'User2', 10, 2000),
                (3, 100, 'User3', 3, 150),
                (4, 100, 'User4', 8, 1200),
            ]

            for user_id, guild_id, username, level, total_xp in users_data:
                await db.execute(
                    'INSERT INTO users (user_id, guild_id, username, level, total_xp) VALUES (?, ?, ?, ?, ?)',
                    (user_id, guild_id, username, level, total_xp)
                )
            await db.commit()

            # Get leaderboard
            cursor = await db.execute(
                '''SELECT user_id, username, level, total_xp
                   FROM users WHERE guild_id = ?
                   ORDER BY total_xp DESC LIMIT 10''',
                (100,)
            )
            leaderboard = await cursor.fetchall()

            assert len(leaderboard) == 4
            assert leaderboard[0][1] == 'User2'  # Highest XP
            assert leaderboard[0][3] == 2000

    @pytest.mark.asyncio
    async def test_user_balance_operations(self, temp_db):
        """Test balance operations."""
        async with aiosqlite.connect(temp_db) as db:
            # Create user with balance
            await db.execute(
                'INSERT INTO users (user_id, guild_id, username, balance) VALUES (?, ?, ?, ?)',
                (123456789, 987654321, 'TestUser', 1000)
            )
            await db.commit()

            # Add balance
            await db.execute(
                'UPDATE users SET balance = balance + ? WHERE user_id = ? AND guild_id = ?',
                (500, 123456789, 987654321)
            )
            await db.commit()

            cursor = await db.execute(
                'SELECT balance FROM users WHERE user_id = ? AND guild_id = ?',
                (123456789, 987654321)
            )
            balance = (await cursor.fetchone())[0]
            assert balance == 1500

            # Subtract balance
            await db.execute(
                'UPDATE users SET balance = balance - ? WHERE user_id = ? AND guild_id = ?',
                (200, 123456789, 987654321)
            )
            await db.commit()

            cursor = await db.execute(
                'SELECT balance FROM users WHERE user_id = ? AND guild_id = ?',
                (123456789, 987654321)
            )
            balance = (await cursor.fetchone())[0]
            assert balance == 1300


class TestProfanityFilter:
    """Test profanity filter functionality."""

    def test_word_detection_simple(self):
        """Test simple word detection."""
        banned_words = ['badword', 'insult', 'curse']
        message = "This is a badword test"

        detected = [w for w in banned_words if w in message.lower()]
        assert 'badword' in detected

    def test_word_detection_case_insensitive(self):
        """Test case-insensitive detection."""
        banned_words = ['badword']
        message = "This is a BADWORD test"

        detected = [w for w in banned_words if w in message.lower()]
        assert 'badword' in detected

    def test_word_detection_partial(self):
        """Test partial word detection (avoid false positives)."""
        banned_words = ['ass']
        message = "This is a classic example"

        # Simple substring check would give false positive
        detected = [w for w in banned_words if w in message.lower()]

        # This tests the limitation - should use word boundaries in production
        assert 'ass' in detected  # Shows the false positive issue

    def test_word_detection_with_boundaries(self):
        """Test word detection with boundaries."""
        import re

        banned_words = ['ass']
        message = "This is a classic example"

        # Better detection with word boundaries
        detected = [w for w in banned_words if re.search(rf'\b{re.escape(w)}\b', message.lower())]
        assert 'ass' not in detected  # No false positive

        # But detect actual bad word
        message2 = "This is ass in sentence"
        detected2 = [w for w in banned_words if re.search(rf'\b{re.escape(w)}\b', message2.lower())]
        assert 'ass' in detected2

    def test_progressive_punishment_thresholds(self):
        """Test progressive punishment system."""
        config = {
            'warn_threshold': 3,
            'mute_threshold': 5,
            'kick_threshold': 8,
            'ban_threshold': 10,
        }

        def get_punishment(infraction_count):
            if infraction_count >= config['ban_threshold']:
                return 'ban'
            elif infraction_count >= config['kick_threshold']:
                return 'kick'
            elif infraction_count >= config['mute_threshold']:
                return 'mute'
            elif infraction_count >= config['warn_threshold']:
                return 'warn'
            return 'delete'

        assert get_punishment(1) == 'delete'
        assert get_punishment(3) == 'warn'
        assert get_punishment(5) == 'mute'
        assert get_punishment(8) == 'kick'
        assert get_punishment(10) == 'ban'
        assert get_punishment(15) == 'ban'
