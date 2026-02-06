"""
Comprehensive integration tests for ``utils.database.Database``.

Every test method exercises the **real** Database class against a temporary
SQLite file that is created fresh per test via the ``db`` fixture.  No
mocking is used -- these tests validate actual SQL execution, schema
correctness, and data-access logic end-to-end.
"""

import pytest
import tempfile
import os
from datetime import datetime, timedelta

from utils.database import Database


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def db():
    """Provide an initialised Database backed by a temporary file.

    The fixture creates a temp ``.db`` file, calls ``await database.init()``
    (which creates all tables and seeds banned words), yields the instance,
    and cleans up the file afterwards.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    database = Database(db_path)
    await database.init()
    yield database
    os.unlink(db_path)


# Shared test IDs for readability
USER_ID = 100000000000000001
USER_ID_2 = 100000000000000002
USER_ID_3 = 100000000000000003
GUILD_ID = 200000000000000001
GUILD_ID_2 = 200000000000000002
MOD_ID = 300000000000000001
CHANNEL_ID = 400000000000000001
CHANNEL_ID_2 = 400000000000000002
MESSAGE_ID = 500000000000000001
ROLE_ID = 600000000000000001
ROLE_ID_2 = 600000000000000002


# ===================================================================
# USER PROFILES / XP / LEVELLING
# ===================================================================

class TestUserMethods:
    """Tests for get_user, create_user, get_or_create_user, add_xp, set_level."""

    @pytest.mark.asyncio
    async def test_get_user_returns_none_for_missing(self, db):
        result = await db.get_user(USER_ID, GUILD_ID)
        assert result is None

    @pytest.mark.asyncio
    async def test_create_user_returns_dict(self, db):
        user = await db.create_user(USER_ID, GUILD_ID)
        assert isinstance(user, dict)
        assert user["user_id"] == USER_ID
        assert user["guild_id"] == GUILD_ID

    @pytest.mark.asyncio
    async def test_create_user_defaults(self, db):
        user = await db.create_user(USER_ID, GUILD_ID)
        assert user["xp"] == 0
        assert user["level"] == 1
        assert user["total_xp"] == 0
        assert user["messages_count"] == 0
        assert user["coins"] == 0

    @pytest.mark.asyncio
    async def test_create_user_is_idempotent(self, db):
        await db.create_user(USER_ID, GUILD_ID)
        user = await db.create_user(USER_ID, GUILD_ID)
        assert user is not None
        assert user["user_id"] == USER_ID

    @pytest.mark.asyncio
    async def test_get_user_after_create(self, db):
        await db.create_user(USER_ID, GUILD_ID)
        user = await db.get_user(USER_ID, GUILD_ID)
        assert user is not None
        assert user["user_id"] == USER_ID

    @pytest.mark.asyncio
    async def test_get_or_create_user_creates_when_missing(self, db):
        user = await db.get_or_create_user(USER_ID, GUILD_ID)
        assert user is not None
        assert user["user_id"] == USER_ID

    @pytest.mark.asyncio
    async def test_get_or_create_user_returns_existing(self, db):
        await db.create_user(USER_ID, GUILD_ID)
        user = await db.get_or_create_user(USER_ID, GUILD_ID)
        assert user["user_id"] == USER_ID

    @pytest.mark.asyncio
    async def test_add_xp_increases_values(self, db):
        await db.create_user(USER_ID, GUILD_ID)
        updated = await db.add_xp(USER_ID, GUILD_ID, 50)
        assert updated["xp"] == 50
        assert updated["total_xp"] == 50
        assert updated["messages_count"] == 1

    @pytest.mark.asyncio
    async def test_add_xp_accumulates(self, db):
        await db.create_user(USER_ID, GUILD_ID)
        await db.add_xp(USER_ID, GUILD_ID, 30)
        updated = await db.add_xp(USER_ID, GUILD_ID, 20)
        assert updated["xp"] == 50
        assert updated["total_xp"] == 50
        assert updated["messages_count"] == 2

    @pytest.mark.asyncio
    async def test_add_xp_creates_user_if_missing(self, db):
        updated = await db.add_xp(USER_ID, GUILD_ID, 10)
        assert updated is not None
        assert updated["xp"] == 10

    @pytest.mark.asyncio
    async def test_set_level(self, db):
        await db.create_user(USER_ID, GUILD_ID)
        await db.set_level(USER_ID, GUILD_ID, 5, remaining_xp=25)
        user = await db.get_user(USER_ID, GUILD_ID)
        assert user["level"] == 5
        assert user["xp"] == 25

    @pytest.mark.asyncio
    async def test_set_level_default_remaining_xp(self, db):
        await db.create_user(USER_ID, GUILD_ID)
        await db.set_level(USER_ID, GUILD_ID, 3)
        user = await db.get_user(USER_ID, GUILD_ID)
        assert user["level"] == 3
        assert user["xp"] == 0


# ===================================================================
# LEADERBOARD / RANK
# ===================================================================

class TestLeaderboard:
    """Tests for get_leaderboard and get_rank."""

    @pytest.mark.asyncio
    async def test_get_leaderboard_empty(self, db):
        lb = await db.get_leaderboard(GUILD_ID)
        assert lb == []

    @pytest.mark.asyncio
    async def test_get_leaderboard_ordering(self, db):
        await db.add_xp(USER_ID, GUILD_ID, 100)
        await db.add_xp(USER_ID_2, GUILD_ID, 200)
        await db.add_xp(USER_ID_3, GUILD_ID, 50)
        lb = await db.get_leaderboard(GUILD_ID)
        assert len(lb) == 3
        assert lb[0]["user_id"] == USER_ID_2
        assert lb[1]["user_id"] == USER_ID
        assert lb[2]["user_id"] == USER_ID_3

    @pytest.mark.asyncio
    async def test_get_leaderboard_respects_limit(self, db):
        await db.add_xp(USER_ID, GUILD_ID, 100)
        await db.add_xp(USER_ID_2, GUILD_ID, 200)
        await db.add_xp(USER_ID_3, GUILD_ID, 50)
        lb = await db.get_leaderboard(GUILD_ID, limit=2)
        assert len(lb) == 2

    @pytest.mark.asyncio
    async def test_get_leaderboard_isolates_guilds(self, db):
        await db.add_xp(USER_ID, GUILD_ID, 100)
        await db.add_xp(USER_ID_2, GUILD_ID_2, 200)
        lb = await db.get_leaderboard(GUILD_ID)
        assert len(lb) == 1

    @pytest.mark.asyncio
    async def test_get_rank(self, db):
        await db.add_xp(USER_ID, GUILD_ID, 100)
        await db.add_xp(USER_ID_2, GUILD_ID, 200)
        rank = await db.get_rank(USER_ID_2, GUILD_ID)
        assert rank == 1
        rank2 = await db.get_rank(USER_ID, GUILD_ID)
        assert rank2 == 2


# ===================================================================
# ECONOMY (COINS / BALANCE)
# ===================================================================

class TestEconomy:
    """Tests for add_coins, can_claim_daily, claim_daily, economy leaderboard."""

    @pytest.mark.asyncio
    async def test_add_coins_positive(self, db):
        await db.create_user(USER_ID, GUILD_ID)
        await db.add_coins(USER_ID, GUILD_ID, 500)
        user = await db.get_user(USER_ID, GUILD_ID)
        assert user["coins"] == 500

    @pytest.mark.asyncio
    async def test_add_coins_negative_clamped_to_zero(self, db):
        await db.create_user(USER_ID, GUILD_ID)
        await db.add_coins(USER_ID, GUILD_ID, 100)
        await db.add_coins(USER_ID, GUILD_ID, -999)
        user = await db.get_user(USER_ID, GUILD_ID)
        assert user["coins"] == 0

    @pytest.mark.asyncio
    async def test_can_claim_daily_first_time(self, db):
        await db.create_user(USER_ID, GUILD_ID)
        assert await db.can_claim_daily(USER_ID, GUILD_ID) is True

    @pytest.mark.asyncio
    async def test_can_claim_daily_after_recent_claim(self, db):
        await db.create_user(USER_ID, GUILD_ID)
        await db.claim_daily(USER_ID, GUILD_ID, 100)
        assert await db.can_claim_daily(USER_ID, GUILD_ID) is False

    @pytest.mark.asyncio
    async def test_get_economy_leaderboard(self, db):
        await db.create_user(USER_ID, GUILD_ID)
        await db.create_user(USER_ID_2, GUILD_ID)
        await db.add_coins(USER_ID, GUILD_ID, 100)
        await db.add_coins(USER_ID_2, GUILD_ID, 500)
        lb = await db.get_economy_leaderboard(GUILD_ID)
        assert lb[0]["user_id"] == USER_ID_2


# ===================================================================
# MODERATION WARNINGS
# ===================================================================

class TestWarnings:
    """Tests for add_warning, get_warnings, get_warning_count, clear_warnings."""

    @pytest.mark.asyncio
    async def test_add_warning_returns_count(self, db):
        count = await db.add_warning(USER_ID, GUILD_ID, MOD_ID, "test reason")
        assert count == 1

    @pytest.mark.asyncio
    async def test_add_multiple_warnings(self, db):
        await db.add_warning(USER_ID, GUILD_ID, MOD_ID, "reason 1")
        count = await db.add_warning(USER_ID, GUILD_ID, MOD_ID, "reason 2")
        assert count == 2

    @pytest.mark.asyncio
    async def test_get_warnings_returns_list(self, db):
        await db.add_warning(USER_ID, GUILD_ID, MOD_ID, "reason A")
        await db.add_warning(USER_ID, GUILD_ID, MOD_ID, "reason B")
        warnings = await db.get_warnings(USER_ID, GUILD_ID)
        assert len(warnings) == 2
        assert all(isinstance(w, dict) for w in warnings)

    @pytest.mark.asyncio
    async def test_get_warnings_returns_all(self, db):
        await db.add_warning(USER_ID, GUILD_ID, MOD_ID, "first")
        await db.add_warning(USER_ID, GUILD_ID, MOD_ID, "second")
        warnings = await db.get_warnings(USER_ID, GUILD_ID)
        assert len(warnings) == 2
        reasons = {w["reason"] for w in warnings}
        assert reasons == {"first", "second"}

    @pytest.mark.asyncio
    async def test_get_warning_count_zero(self, db):
        count = await db.get_warning_count(USER_ID, GUILD_ID)
        assert count == 0

    @pytest.mark.asyncio
    async def test_get_warning_count_after_add(self, db):
        await db.add_warning(USER_ID, GUILD_ID, MOD_ID, "warn")
        count = await db.get_warning_count(USER_ID, GUILD_ID)
        assert count == 1

    @pytest.mark.asyncio
    async def test_clear_warnings(self, db):
        await db.add_warning(USER_ID, GUILD_ID, MOD_ID, "w1")
        await db.add_warning(USER_ID, GUILD_ID, MOD_ID, "w2")
        await db.clear_warnings(USER_ID, GUILD_ID)
        count = await db.get_warning_count(USER_ID, GUILD_ID)
        assert count == 0

    @pytest.mark.asyncio
    async def test_clear_warnings_only_affects_target_user(self, db):
        await db.add_warning(USER_ID, GUILD_ID, MOD_ID, "u1 warn")
        await db.add_warning(USER_ID_2, GUILD_ID, MOD_ID, "u2 warn")
        await db.clear_warnings(USER_ID, GUILD_ID)
        assert await db.get_warning_count(USER_ID, GUILD_ID) == 0
        assert await db.get_warning_count(USER_ID_2, GUILD_ID) == 1

    @pytest.mark.asyncio
    async def test_add_warning_with_none_reason(self, db):
        count = await db.add_warning(USER_ID, GUILD_ID, MOD_ID, None)
        assert count == 1
        warnings = await db.get_warnings(USER_ID, GUILD_ID)
        assert warnings[0]["reason"] is None


# ===================================================================
# GUILD CONFIGURATION
# ===================================================================

class TestGuildConfig:
    """Tests for get_guild_config, create_guild_config, update_guild_config."""

    @pytest.mark.asyncio
    async def test_get_guild_config_auto_creates(self, db):
        config = await db.get_guild_config(GUILD_ID)
        assert isinstance(config, dict)
        assert config["guild_id"] == GUILD_ID

    @pytest.mark.asyncio
    async def test_get_guild_config_defaults(self, db):
        config = await db.get_guild_config(GUILD_ID)
        assert config["prefix"] == "!"
        assert config["auto_mod_enabled"] == 1
        assert config["leveling_enabled"] == 1

    @pytest.mark.asyncio
    async def test_create_guild_config_idempotent(self, db):
        await db.create_guild_config(GUILD_ID)
        await db.create_guild_config(GUILD_ID)
        config = await db.get_guild_config(GUILD_ID)
        assert config is not None

    @pytest.mark.asyncio
    async def test_update_guild_config_single_field(self, db):
        await db.get_guild_config(GUILD_ID)  # ensure row exists
        await db.update_guild_config(GUILD_ID, prefix="?")
        config = await db.get_guild_config(GUILD_ID)
        assert config["prefix"] == "?"

    @pytest.mark.asyncio
    async def test_update_guild_config_multiple_fields(self, db):
        await db.get_guild_config(GUILD_ID)
        await db.update_guild_config(
            GUILD_ID,
            prefix=">>",
            welcome_message="Hello {user}!",
            auto_mod_enabled=0,
        )
        config = await db.get_guild_config(GUILD_ID)
        assert config["prefix"] == ">>"
        assert config["welcome_message"] == "Hello {user}!"
        assert config["auto_mod_enabled"] == 0

    @pytest.mark.asyncio
    async def test_update_guild_config_invalid_key_raises(self, db):
        await db.get_guild_config(GUILD_ID)
        with pytest.raises(ValueError, match="Invalid guild_config columns"):
            await db.update_guild_config(GUILD_ID, nonexistent_column="bad")

    @pytest.mark.asyncio
    async def test_update_guild_config_no_kwargs_is_noop(self, db):
        await db.get_guild_config(GUILD_ID)
        await db.update_guild_config(GUILD_ID)  # should not raise

    @pytest.mark.asyncio
    async def test_update_guild_config_mixed_valid_invalid_raises(self, db):
        await db.get_guild_config(GUILD_ID)
        with pytest.raises(ValueError):
            await db.update_guild_config(GUILD_ID, prefix="!", evil_col="drop table")


# ===================================================================
# SUPPORT TICKETS
# ===================================================================

class TestTickets:
    """Tests for create_ticket, close_ticket, get_ticket_by_channel."""

    @pytest.mark.asyncio
    async def test_create_ticket_returns_id(self, db):
        ticket_id = await db.create_ticket(GUILD_ID, CHANNEL_ID, USER_ID, "Help me")
        assert isinstance(ticket_id, int)
        assert ticket_id > 0

    @pytest.mark.asyncio
    async def test_get_ticket_by_channel(self, db):
        await db.create_ticket(GUILD_ID, CHANNEL_ID, USER_ID, "Test subject")
        ticket = await db.get_ticket_by_channel(CHANNEL_ID)
        assert ticket is not None
        assert ticket["user_id"] == USER_ID
        assert ticket["subject"] == "Test subject"
        assert ticket["status"] == "open"

    @pytest.mark.asyncio
    async def test_get_ticket_by_channel_returns_none_for_missing(self, db):
        ticket = await db.get_ticket_by_channel(999999)
        assert ticket is None

    @pytest.mark.asyncio
    async def test_close_ticket(self, db):
        ticket_id = await db.create_ticket(GUILD_ID, CHANNEL_ID, USER_ID, "To close")
        await db.close_ticket(ticket_id)
        # After closing, get_ticket_by_channel should return None (it only finds open tickets)
        ticket = await db.get_ticket_by_channel(CHANNEL_ID)
        assert ticket is None

    @pytest.mark.asyncio
    async def test_create_ticket_without_subject(self, db):
        ticket_id = await db.create_ticket(GUILD_ID, CHANNEL_ID, USER_ID)
        ticket = await db.get_ticket_by_channel(CHANNEL_ID)
        assert ticket is not None
        assert ticket["subject"] is None

    @pytest.mark.asyncio
    async def test_multiple_tickets_different_channels(self, db):
        t1 = await db.create_ticket(GUILD_ID, CHANNEL_ID, USER_ID, "Ticket 1")
        t2 = await db.create_ticket(GUILD_ID, CHANNEL_ID_2, USER_ID_2, "Ticket 2")
        assert t1 != t2
        ticket1 = await db.get_ticket_by_channel(CHANNEL_ID)
        ticket2 = await db.get_ticket_by_channel(CHANNEL_ID_2)
        assert ticket1["subject"] == "Ticket 1"
        assert ticket2["subject"] == "Ticket 2"


# ===================================================================
# REMINDERS
# ===================================================================

class TestReminders:
    """Tests for add_reminder, get_due_reminders, delete_reminder."""

    @pytest.mark.asyncio
    async def test_add_reminder_returns_id(self, db):
        future = datetime.now() + timedelta(hours=1)
        rid = await db.add_reminder(USER_ID, CHANNEL_ID, "Remember this", future)
        assert isinstance(rid, int)
        assert rid > 0

    @pytest.mark.asyncio
    async def test_get_due_reminders_none_due(self, db):
        future = datetime.now() + timedelta(hours=1)
        await db.add_reminder(USER_ID, CHANNEL_ID, "Not yet", future)
        due = await db.get_due_reminders()
        assert len(due) == 0

    @pytest.mark.asyncio
    async def test_get_due_reminders_past(self, db):
        past = datetime.now() - timedelta(hours=1)
        await db.add_reminder(USER_ID, CHANNEL_ID, "Overdue", past)
        due = await db.get_due_reminders()
        assert len(due) == 1
        assert due[0]["message"] == "Overdue"

    @pytest.mark.asyncio
    async def test_delete_reminder(self, db):
        past = datetime.now() - timedelta(hours=1)
        rid = await db.add_reminder(USER_ID, CHANNEL_ID, "To delete", past)
        await db.delete_reminder(rid)
        due = await db.get_due_reminders()
        assert len(due) == 0

    @pytest.mark.asyncio
    async def test_multiple_due_reminders(self, db):
        past = datetime.now() - timedelta(minutes=5)
        await db.add_reminder(USER_ID, CHANNEL_ID, "Reminder A", past)
        await db.add_reminder(USER_ID_2, CHANNEL_ID_2, "Reminder B", past)
        due = await db.get_due_reminders()
        assert len(due) == 2


# ===================================================================
# REACTION ROLES
# ===================================================================

class TestReactionRoles:
    """Tests for add_reaction_role, get_reaction_role, get_all_reaction_roles, remove_reaction_role."""

    @pytest.mark.asyncio
    async def test_add_and_get_reaction_role(self, db):
        await db.add_reaction_role(GUILD_ID, MESSAGE_ID, CHANNEL_ID, "thumbsup", ROLE_ID)
        rr = await db.get_reaction_role(MESSAGE_ID, "thumbsup")
        assert rr is not None
        assert rr["role_id"] == ROLE_ID
        assert rr["guild_id"] == GUILD_ID

    @pytest.mark.asyncio
    async def test_get_reaction_role_missing(self, db):
        rr = await db.get_reaction_role(MESSAGE_ID, "nonexistent")
        assert rr is None

    @pytest.mark.asyncio
    async def test_get_all_reaction_roles(self, db):
        await db.add_reaction_role(GUILD_ID, MESSAGE_ID, CHANNEL_ID, "thumbsup", ROLE_ID)
        await db.add_reaction_role(GUILD_ID, MESSAGE_ID, CHANNEL_ID, "heart", ROLE_ID_2)
        roles = await db.get_all_reaction_roles(GUILD_ID)
        assert len(roles) == 2

    @pytest.mark.asyncio
    async def test_get_all_reaction_roles_empty(self, db):
        roles = await db.get_all_reaction_roles(GUILD_ID)
        assert roles == []

    @pytest.mark.asyncio
    async def test_remove_reaction_role(self, db):
        await db.add_reaction_role(GUILD_ID, MESSAGE_ID, CHANNEL_ID, "thumbsup", ROLE_ID)
        await db.remove_reaction_role(MESSAGE_ID, "thumbsup")
        rr = await db.get_reaction_role(MESSAGE_ID, "thumbsup")
        assert rr is None

    @pytest.mark.asyncio
    async def test_add_reaction_role_replace_on_conflict(self, db):
        await db.add_reaction_role(GUILD_ID, MESSAGE_ID, CHANNEL_ID, "star", ROLE_ID)
        await db.add_reaction_role(GUILD_ID, MESSAGE_ID, CHANNEL_ID, "star", ROLE_ID_2)
        rr = await db.get_reaction_role(MESSAGE_ID, "star")
        assert rr["role_id"] == ROLE_ID_2

    @pytest.mark.asyncio
    async def test_reaction_roles_isolate_by_guild(self, db):
        await db.add_reaction_role(GUILD_ID, MESSAGE_ID, CHANNEL_ID, "star", ROLE_ID)
        roles = await db.get_all_reaction_roles(GUILD_ID_2)
        assert roles == []


# ===================================================================
# LEVEL ROLES
# ===================================================================

class TestLevelRoles:
    """Tests for add_level_role, get_level_roles, get_role_for_level, remove_level_role."""

    @pytest.mark.asyncio
    async def test_add_and_get_level_roles(self, db):
        await db.add_level_role(GUILD_ID, 5, ROLE_ID)
        roles = await db.get_level_roles(GUILD_ID)
        assert len(roles) == 1
        assert roles[0]["level"] == 5
        assert roles[0]["role_id"] == ROLE_ID

    @pytest.mark.asyncio
    async def test_get_level_roles_ordered(self, db):
        await db.add_level_role(GUILD_ID, 10, ROLE_ID_2)
        await db.add_level_role(GUILD_ID, 5, ROLE_ID)
        roles = await db.get_level_roles(GUILD_ID)
        assert roles[0]["level"] == 5
        assert roles[1]["level"] == 10

    @pytest.mark.asyncio
    async def test_get_level_roles_empty(self, db):
        roles = await db.get_level_roles(GUILD_ID)
        assert roles == []

    @pytest.mark.asyncio
    async def test_get_role_for_level_found(self, db):
        await db.add_level_role(GUILD_ID, 5, ROLE_ID)
        rid = await db.get_role_for_level(GUILD_ID, 5)
        assert rid == ROLE_ID

    @pytest.mark.asyncio
    async def test_get_role_for_level_not_found(self, db):
        rid = await db.get_role_for_level(GUILD_ID, 99)
        assert rid is None

    @pytest.mark.asyncio
    async def test_remove_level_role(self, db):
        await db.add_level_role(GUILD_ID, 5, ROLE_ID)
        await db.remove_level_role(GUILD_ID, 5)
        roles = await db.get_level_roles(GUILD_ID)
        assert roles == []

    @pytest.mark.asyncio
    async def test_add_level_role_replace_on_conflict(self, db):
        await db.add_level_role(GUILD_ID, 5, ROLE_ID)
        await db.add_level_role(GUILD_ID, 5, ROLE_ID_2)
        rid = await db.get_role_for_level(GUILD_ID, 5)
        assert rid == ROLE_ID_2


# ===================================================================
# TRIVIA SCORES
# ===================================================================

class TestTrivia:
    """Tests for update_trivia_score, get_trivia_leaderboard."""

    @pytest.mark.asyncio
    async def test_update_trivia_score_correct(self, db):
        await db.update_trivia_score(USER_ID, GUILD_ID, correct=True)
        lb = await db.get_trivia_leaderboard(GUILD_ID)
        assert len(lb) == 1
        assert lb[0]["correct_answers"] == 1
        assert lb[0]["total_questions"] == 1

    @pytest.mark.asyncio
    async def test_update_trivia_score_incorrect(self, db):
        await db.update_trivia_score(USER_ID, GUILD_ID, correct=False)
        lb = await db.get_trivia_leaderboard(GUILD_ID)
        assert lb[0]["correct_answers"] == 0
        assert lb[0]["total_questions"] == 1

    @pytest.mark.asyncio
    async def test_update_trivia_score_accumulates(self, db):
        await db.update_trivia_score(USER_ID, GUILD_ID, correct=True)
        await db.update_trivia_score(USER_ID, GUILD_ID, correct=True)
        await db.update_trivia_score(USER_ID, GUILD_ID, correct=False)
        lb = await db.get_trivia_leaderboard(GUILD_ID)
        assert lb[0]["correct_answers"] == 2
        assert lb[0]["total_questions"] == 3

    @pytest.mark.asyncio
    async def test_trivia_leaderboard_ordering(self, db):
        await db.update_trivia_score(USER_ID, GUILD_ID, correct=True)
        await db.update_trivia_score(USER_ID_2, GUILD_ID, correct=True)
        await db.update_trivia_score(USER_ID_2, GUILD_ID, correct=True)
        lb = await db.get_trivia_leaderboard(GUILD_ID)
        assert lb[0]["user_id"] == USER_ID_2

    @pytest.mark.asyncio
    async def test_trivia_leaderboard_empty(self, db):
        lb = await db.get_trivia_leaderboard(GUILD_ID)
        assert lb == []

    @pytest.mark.asyncio
    async def test_trivia_leaderboard_limit(self, db):
        await db.update_trivia_score(USER_ID, GUILD_ID, correct=True)
        await db.update_trivia_score(USER_ID_2, GUILD_ID, correct=True)
        await db.update_trivia_score(USER_ID_3, GUILD_ID, correct=True)
        lb = await db.get_trivia_leaderboard(GUILD_ID, limit=2)
        assert len(lb) == 2


# ===================================================================
# BANNED WORDS
# ===================================================================

class TestBannedWords:
    """Tests for add_banned_word, get_banned_words, remove_banned_word,
    get_banned_words_list, check_message_for_profanity, and default seeding."""

    @pytest.mark.asyncio
    async def test_default_banned_words_seeded(self, db):
        """_init_default_banned_words should have populated the table on init()."""
        words = await db.get_banned_words(guild_id=0)
        assert len(words) > 0

    @pytest.mark.asyncio
    async def test_default_banned_words_include_english(self, db):
        word_strings = await db.get_banned_words_list(guild_id=0)
        assert "fuck" in word_strings

    @pytest.mark.asyncio
    async def test_default_banned_words_include_french(self, db):
        word_strings = await db.get_banned_words_list(guild_id=0)
        assert "merde" in word_strings

    @pytest.mark.asyncio
    async def test_add_banned_word_success(self, db):
        result = await db.add_banned_word("testword", language="en", guild_id=GUILD_ID, severity=2)
        assert result is True

    @pytest.mark.asyncio
    async def test_add_banned_word_duplicate_returns_false(self, db):
        await db.add_banned_word("duplicate", guild_id=GUILD_ID)
        result = await db.add_banned_word("duplicate", guild_id=GUILD_ID)
        assert result is False

    @pytest.mark.asyncio
    async def test_add_banned_word_stores_lowercase(self, db):
        await db.add_banned_word("UPPERCASE", guild_id=GUILD_ID)
        words = await db.get_banned_words(guild_id=GUILD_ID)
        guild_words = [w["word"] for w in words if w["guild_id"] == GUILD_ID]
        assert "uppercase" in guild_words

    @pytest.mark.asyncio
    async def test_remove_banned_word_success(self, db):
        await db.add_banned_word("removeme", guild_id=GUILD_ID)
        result = await db.remove_banned_word("removeme", guild_id=GUILD_ID)
        assert result is True

    @pytest.mark.asyncio
    async def test_remove_banned_word_not_found(self, db):
        result = await db.remove_banned_word("neveradded", guild_id=GUILD_ID)
        assert result is False

    @pytest.mark.asyncio
    async def test_get_banned_words_includes_global_and_guild(self, db):
        await db.add_banned_word("guildword", guild_id=GUILD_ID, severity=3)
        words = await db.get_banned_words(guild_id=GUILD_ID)
        guild_specific = [w for w in words if w["guild_id"] == GUILD_ID]
        global_words = [w for w in words if w["guild_id"] == 0]
        assert len(guild_specific) >= 1
        assert len(global_words) >= 1

    @pytest.mark.asyncio
    async def test_get_banned_words_language_filter(self, db):
        words_en = await db.get_banned_words(guild_id=0, language="en")
        words_fr = await db.get_banned_words(guild_id=0, language="fr")
        # English list should contain "fuck", French should contain "merde"
        en_strs = [w["word"] for w in words_en]
        fr_strs = [w["word"] for w in words_fr]
        assert "fuck" in en_strs
        assert "merde" in fr_strs

    @pytest.mark.asyncio
    async def test_get_banned_words_list_returns_strings(self, db):
        words = await db.get_banned_words_list(guild_id=0)
        assert isinstance(words, list)
        assert all(isinstance(w, str) for w in words)

    @pytest.mark.asyncio
    async def test_check_message_for_profanity_match(self, db):
        result = await db.check_message_for_profanity("this is fuck you", guild_id=0)
        assert result is not None
        assert result["word"] == "fuck"

    @pytest.mark.asyncio
    async def test_check_message_for_profanity_no_match(self, db):
        result = await db.check_message_for_profanity("this is a clean message", guild_id=0)
        assert result is None

    @pytest.mark.asyncio
    async def test_check_message_for_profanity_case_insensitive(self, db):
        result = await db.check_message_for_profanity("FUCK this", guild_id=0)
        assert result is not None


# ===================================================================
# PROFANITY INFRACTIONS & USER STATS
# ===================================================================

class TestProfanityInfractions:
    """Tests for add_profanity_infraction, get_user_profanity_stats,
    get_user_profanity_history, reset_user_profanity_stats."""

    @pytest.mark.asyncio
    async def test_get_user_profanity_stats_default(self, db):
        stats = await db.get_user_profanity_stats(USER_ID, GUILD_ID)
        assert stats["total_infractions"] == 0
        assert stats["warnings_count"] == 0
        assert stats["mutes_count"] == 0
        assert stats["kicks_count"] == 0
        assert stats["is_banned"] == 0
        assert stats["last_infraction"] is None

    @pytest.mark.asyncio
    async def test_add_profanity_infraction_warn(self, db):
        stats = await db.add_profanity_infraction(
            USER_ID, GUILD_ID, "badword", "you badword person", "warn"
        )
        assert stats["total_infractions"] == 1
        assert stats["warnings_count"] == 1

    @pytest.mark.asyncio
    async def test_add_profanity_infraction_mute(self, db):
        stats = await db.add_profanity_infraction(
            USER_ID, GUILD_ID, "badword", "msg", "mute"
        )
        assert stats["mutes_count"] == 1

    @pytest.mark.asyncio
    async def test_add_profanity_infraction_kick(self, db):
        stats = await db.add_profanity_infraction(
            USER_ID, GUILD_ID, "badword", "msg", "kick"
        )
        assert stats["kicks_count"] == 1

    @pytest.mark.asyncio
    async def test_add_profanity_infraction_ban(self, db):
        stats = await db.add_profanity_infraction(
            USER_ID, GUILD_ID, "badword", "msg", "ban"
        )
        assert stats["is_banned"] == 1

    @pytest.mark.asyncio
    async def test_add_profanity_infraction_accumulates(self, db):
        await db.add_profanity_infraction(USER_ID, GUILD_ID, "w1", "m1", "warn")
        stats = await db.add_profanity_infraction(USER_ID, GUILD_ID, "w2", "m2", "warn")
        assert stats["total_infractions"] == 2
        assert stats["warnings_count"] == 2

    @pytest.mark.asyncio
    async def test_add_profanity_infraction_truncates_message(self, db):
        long_msg = "x" * 1000
        stats = await db.add_profanity_infraction(USER_ID, GUILD_ID, "word", long_msg, "warn")
        # The infraction should still be recorded; the message is truncated internally
        assert stats["total_infractions"] == 1
        history = await db.get_user_profanity_history(USER_ID, GUILD_ID)
        assert len(history[0]["message_content"]) <= 500

    @pytest.mark.asyncio
    async def test_get_user_profanity_history(self, db):
        await db.add_profanity_infraction(USER_ID, GUILD_ID, "w1", "m1", "warn")
        await db.add_profanity_infraction(USER_ID, GUILD_ID, "w2", "m2", "mute")
        history = await db.get_user_profanity_history(USER_ID, GUILD_ID)
        assert len(history) == 2
        # Both action types should be present in the history
        actions = {h["action_taken"] for h in history}
        assert actions == {"warn", "mute"}

    @pytest.mark.asyncio
    async def test_get_user_profanity_history_limit(self, db):
        for i in range(5):
            await db.add_profanity_infraction(USER_ID, GUILD_ID, f"w{i}", f"m{i}", "warn")
        history = await db.get_user_profanity_history(USER_ID, GUILD_ID, limit=3)
        assert len(history) == 3

    @pytest.mark.asyncio
    async def test_reset_user_profanity_stats(self, db):
        await db.add_profanity_infraction(USER_ID, GUILD_ID, "w", "m", "warn")
        await db.add_profanity_infraction(USER_ID, GUILD_ID, "w", "m", "mute")
        await db.reset_user_profanity_stats(USER_ID, GUILD_ID)
        stats = await db.get_user_profanity_stats(USER_ID, GUILD_ID)
        assert stats["total_infractions"] == 0
        assert stats["warnings_count"] == 0
        assert stats["mutes_count"] == 0

    @pytest.mark.asyncio
    async def test_reset_profanity_stats_preserves_history(self, db):
        await db.add_profanity_infraction(USER_ID, GUILD_ID, "w", "m", "warn")
        await db.reset_user_profanity_stats(USER_ID, GUILD_ID)
        # History rows remain even after stats reset
        history = await db.get_user_profanity_history(USER_ID, GUILD_ID)
        assert len(history) == 1

    @pytest.mark.asyncio
    async def test_profanity_leaderboard(self, db):
        await db.add_profanity_infraction(USER_ID, GUILD_ID, "w", "m", "warn")
        await db.add_profanity_infraction(USER_ID_2, GUILD_ID, "w", "m", "warn")
        await db.add_profanity_infraction(USER_ID_2, GUILD_ID, "w", "m", "warn")
        lb = await db.get_profanity_leaderboard(GUILD_ID)
        assert len(lb) == 2
        assert lb[0]["user_id"] == USER_ID_2  # more infractions

    @pytest.mark.asyncio
    async def test_profanity_leaderboard_empty(self, db):
        lb = await db.get_profanity_leaderboard(GUILD_ID)
        assert lb == []


# ===================================================================
# PROFANITY CONFIG
# ===================================================================

class TestProfanityConfig:
    """Tests for get_profanity_config, update_profanity_config."""

    @pytest.mark.asyncio
    async def test_get_profanity_config_auto_creates(self, db):
        config = await db.get_profanity_config(GUILD_ID)
        assert isinstance(config, dict)
        assert config["guild_id"] == GUILD_ID

    @pytest.mark.asyncio
    async def test_get_profanity_config_defaults(self, db):
        config = await db.get_profanity_config(GUILD_ID)
        assert config["enabled"] == 1
        assert config["warn_threshold"] == 3
        assert config["mute_threshold"] == 5
        assert config["kick_threshold"] == 8
        assert config["ban_threshold"] == 10
        assert config["mute_duration"] == 3600
        assert config["delete_message"] == 1
        assert config["log_infractions"] == 1
        assert config["dm_user"] == 1

    @pytest.mark.asyncio
    async def test_update_profanity_config_single_field(self, db):
        await db.get_profanity_config(GUILD_ID)
        await db.update_profanity_config(GUILD_ID, warn_threshold=5)
        config = await db.get_profanity_config(GUILD_ID)
        assert config["warn_threshold"] == 5

    @pytest.mark.asyncio
    async def test_update_profanity_config_multiple_fields(self, db):
        await db.get_profanity_config(GUILD_ID)
        await db.update_profanity_config(
            GUILD_ID,
            enabled=0,
            mute_duration=7200,
            dm_user=0,
        )
        config = await db.get_profanity_config(GUILD_ID)
        assert config["enabled"] == 0
        assert config["mute_duration"] == 7200
        assert config["dm_user"] == 0

    @pytest.mark.asyncio
    async def test_update_profanity_config_invalid_key_raises(self, db):
        await db.get_profanity_config(GUILD_ID)
        with pytest.raises(ValueError, match="Invalid profanity_config columns"):
            await db.update_profanity_config(GUILD_ID, nonexistent="bad")

    @pytest.mark.asyncio
    async def test_update_profanity_config_no_kwargs_is_noop(self, db):
        await db.get_profanity_config(GUILD_ID)
        await db.update_profanity_config(GUILD_ID)  # should not raise

    @pytest.mark.asyncio
    async def test_update_profanity_config_all_valid_columns(self, db):
        """Verify every column in the whitelist can be updated."""
        await db.get_profanity_config(GUILD_ID)
        await db.update_profanity_config(
            GUILD_ID,
            enabled=0,
            warn_threshold=2,
            mute_threshold=4,
            kick_threshold=6,
            ban_threshold=8,
            mute_duration=1800,
            delete_message=0,
            log_infractions=0,
            dm_user=0,
        )
        config = await db.get_profanity_config(GUILD_ID)
        assert config["enabled"] == 0
        assert config["warn_threshold"] == 2
        assert config["mute_threshold"] == 4
        assert config["kick_threshold"] == 6
        assert config["ban_threshold"] == 8
        assert config["mute_duration"] == 1800
        assert config["delete_message"] == 0
        assert config["log_infractions"] == 0
        assert config["dm_user"] == 0


# ===================================================================
# DETERMINE PUNISHMENT (progressive escalation)
# ===================================================================

class TestDeterminePunishment:
    """Tests for the determine_punishment logic."""

    @pytest.mark.asyncio
    async def test_determine_punishment_warn_by_default(self, db):
        punishment = await db.determine_punishment(USER_ID, GUILD_ID)
        assert punishment == "warn"

    @pytest.mark.asyncio
    async def test_determine_punishment_warn_at_threshold(self, db):
        # Default warn_threshold is 3
        for _ in range(3):
            await db.add_profanity_infraction(USER_ID, GUILD_ID, "w", "m", "warn")
        punishment = await db.determine_punishment(USER_ID, GUILD_ID)
        assert punishment == "warn"

    @pytest.mark.asyncio
    async def test_determine_punishment_mute(self, db):
        # Default mute_threshold is 5
        for _ in range(5):
            await db.add_profanity_infraction(USER_ID, GUILD_ID, "w", "m", "warn")
        punishment = await db.determine_punishment(USER_ID, GUILD_ID)
        assert punishment == "mute"

    @pytest.mark.asyncio
    async def test_determine_punishment_kick(self, db):
        # Default kick_threshold is 8
        for _ in range(8):
            await db.add_profanity_infraction(USER_ID, GUILD_ID, "w", "m", "warn")
        punishment = await db.determine_punishment(USER_ID, GUILD_ID)
        assert punishment == "kick"

    @pytest.mark.asyncio
    async def test_determine_punishment_ban(self, db):
        # Default ban_threshold is 10
        for _ in range(10):
            await db.add_profanity_infraction(USER_ID, GUILD_ID, "w", "m", "warn")
        punishment = await db.determine_punishment(USER_ID, GUILD_ID)
        assert punishment == "ban"


# ===================================================================
# DATABASE INITIALISATION
# ===================================================================

class TestDatabaseInit:
    """Tests for Database construction and init()."""

    @pytest.mark.asyncio
    async def test_custom_db_path(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            database = Database(path)
            assert database.db_path == path
            await database.init()
            # After init, we should be able to perform basic operations
            user = await database.get_or_create_user(USER_ID, GUILD_ID)
            assert user is not None
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_init_is_idempotent(self, db):
        """Calling init() a second time should not break anything."""
        await db.init()
        user = await db.get_or_create_user(USER_ID, GUILD_ID)
        assert user is not None

    @pytest.mark.asyncio
    async def test_init_seeds_banned_words(self, db):
        """init() should call _init_default_banned_words and populate the table."""
        words = await db.get_banned_words_list(guild_id=0)
        assert len(words) > 50  # The seed list is extensive

    @pytest.mark.asyncio
    async def test_default_db_path(self):
        """The default Database() constructor uses DATABASE_PATH."""
        from utils.database import DATABASE_PATH
        database = Database()
        assert database.db_path == DATABASE_PATH
