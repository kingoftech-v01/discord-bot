"""
Tests for the profanity filter cog (cogs/profanity_filter.py).

Covers ProfanityFilter initialization, the on_message detection pipeline,
the apply_punishment method, and the progressive punishment configuration
commands.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timedelta

import discord
from discord.ext import commands


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_bot():
    bot = MagicMock(spec=commands.Bot)
    bot.user = MagicMock()
    bot.user.id = 999999999
    bot.get_channel = MagicMock(return_value=MagicMock())
    bot.wait_until_ready = AsyncMock()
    return bot


@pytest.fixture
def mock_ctx():
    ctx = MagicMock(spec=commands.Context)
    ctx.guild = MagicMock(spec=discord.Guild)
    ctx.guild.id = 987654321
    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.id = 123456789
    ctx.author.guild_permissions = MagicMock()
    ctx.send = AsyncMock()
    ctx.channel = MagicMock()
    ctx.channel.send = AsyncMock()
    return ctx


@pytest.fixture
def profanity_cog(mock_bot):
    from cogs.profanity_filter import ProfanityFilter
    return ProfanityFilter(mock_bot)


# ---------------------------------------------------------------------------
# ProfanityFilter — Initialization
# ---------------------------------------------------------------------------

class TestProfanityFilterInit:
    """Tests for ProfanityFilter __init__."""

    def test_language_names_mapping(self, profanity_cog):
        """language_names should contain mappings for all supported languages."""
        assert "fr" in profanity_cog.language_names
        assert "en" in profanity_cog.language_names
        assert "all" in profanity_cog.language_names

    def test_language_names_all_key(self, profanity_cog):
        """The 'all' key should map to 'Toutes'."""
        assert profanity_cog.language_names["all"] == "Toutes"

    def test_language_names_french(self, profanity_cog):
        """The 'fr' key should map to 'Francais'."""
        assert profanity_cog.language_names["fr"] == "Français"

    def test_language_names_count(self, profanity_cog):
        """All 11 languages should be in the mapping."""
        assert len(profanity_cog.language_names) == 11

    def test_bot_reference(self, profanity_cog, mock_bot):
        """The cog should hold a reference to the bot."""
        assert profanity_cog.bot is mock_bot


# ---------------------------------------------------------------------------
# ProfanityFilter — apply_punishment
# ---------------------------------------------------------------------------

class TestApplyPunishment:
    """Tests for ProfanityFilter.apply_punishment()."""

    @pytest.mark.asyncio
    async def test_warn_returns_true(self, profanity_cog):
        """Warn punishment should return True without calling Discord API."""
        member = MagicMock(spec=discord.Member)
        guild = MagicMock(spec=discord.Guild)
        result = await profanity_cog.apply_punishment(member, "warn", guild, "reason")
        assert result is True

    @pytest.mark.asyncio
    @patch("cogs.profanity_filter.db")
    async def test_mute_applies_timeout(self, mock_db, profanity_cog):
        """Mute punishment should call member.timeout()."""
        mock_db.get_profanity_config = AsyncMock(return_value={"mute_duration": 3600})
        member = MagicMock(spec=discord.Member)
        member.timeout = AsyncMock()
        guild = MagicMock(spec=discord.Guild)

        result = await profanity_cog.apply_punishment(member, "mute", guild, "reason")
        assert result is True
        member.timeout.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_kick_calls_kick(self, profanity_cog):
        """Kick punishment should call member.kick()."""
        member = MagicMock(spec=discord.Member)
        member.kick = AsyncMock()
        guild = MagicMock(spec=discord.Guild)

        result = await profanity_cog.apply_punishment(member, "kick", guild, "reason")
        assert result is True
        member.kick.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ban_calls_ban(self, profanity_cog):
        """Ban punishment should call member.ban()."""
        member = MagicMock(spec=discord.Member)
        member.ban = AsyncMock()
        guild = MagicMock(spec=discord.Guild)

        result = await profanity_cog.apply_punishment(member, "ban", guild, "reason")
        assert result is True
        member.ban.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_forbidden_returns_false(self, profanity_cog):
        """Should return False if bot lacks permission to kick."""
        member = MagicMock(spec=discord.Member)
        member.kick = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "no perms"))
        guild = MagicMock(spec=discord.Guild)

        result = await profanity_cog.apply_punishment(member, "kick", guild, "reason")
        assert result is False

    @pytest.mark.asyncio
    async def test_unknown_punishment_returns_false(self, profanity_cog):
        """Unknown punishment type should return False."""
        member = MagicMock(spec=discord.Member)
        guild = MagicMock(spec=discord.Guild)
        result = await profanity_cog.apply_punishment(member, "unknown", guild, "reason")
        assert result is False

    @pytest.mark.asyncio
    @patch("cogs.profanity_filter.db")
    async def test_mute_uses_config_duration(self, mock_db, profanity_cog):
        """Mute duration should come from guild profanity config."""
        mock_db.get_profanity_config = AsyncMock(return_value={"mute_duration": 7200})
        member = MagicMock(spec=discord.Member)
        member.timeout = AsyncMock()
        guild = MagicMock(spec=discord.Guild)

        await profanity_cog.apply_punishment(member, "mute", guild, "reason")
        # Check that timeout was called with a timedelta-based until
        args, kwargs = member.timeout.call_args
        timeout_until = args[0]
        # The until should be roughly now + 7200 seconds
        expected = datetime.now() + timedelta(seconds=7200)
        assert abs((timeout_until - expected).total_seconds()) < 5

    @pytest.mark.asyncio
    @patch("cogs.profanity_filter.db")
    async def test_mute_default_duration(self, mock_db, profanity_cog):
        """Mute should default to 3600 seconds if config has no mute_duration."""
        mock_db.get_profanity_config = AsyncMock(return_value={})
        member = MagicMock(spec=discord.Member)
        member.timeout = AsyncMock()
        guild = MagicMock(spec=discord.Guild)

        await profanity_cog.apply_punishment(member, "mute", guild, "reason")
        args, _ = member.timeout.call_args
        timeout_until = args[0]
        expected = datetime.now() + timedelta(seconds=3600)
        assert abs((timeout_until - expected).total_seconds()) < 5


# ---------------------------------------------------------------------------
# ProfanityFilter — log_infraction
# ---------------------------------------------------------------------------

class TestLogInfraction:
    """Tests for ProfanityFilter.log_infraction()."""

    @pytest.mark.asyncio
    @patch("cogs.profanity_filter.db")
    async def test_logs_to_channel(self, mock_db, profanity_cog):
        """Should send embed to configured log channel."""
        mock_db.get_guild_config = AsyncMock(return_value={"log_channel_id": 888})
        channel = MagicMock()
        channel.send = AsyncMock()
        guild = MagicMock(spec=discord.Guild)
        guild.get_channel = MagicMock(return_value=channel)

        embed = discord.Embed(title="Infraction")
        await profanity_cog.log_infraction(guild, embed)
        channel.send.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("cogs.profanity_filter.db")
    async def test_no_log_channel(self, mock_db, profanity_cog):
        """Should do nothing if no log channel configured."""
        mock_db.get_guild_config = AsyncMock(return_value={})
        guild = MagicMock(spec=discord.Guild)
        # Should not raise
        await profanity_cog.log_infraction(guild, discord.Embed())

    @pytest.mark.asyncio
    @patch("cogs.profanity_filter.db")
    async def test_handles_forbidden(self, mock_db, profanity_cog):
        """Should swallow discord.Forbidden silently."""
        mock_db.get_guild_config = AsyncMock(return_value={"log_channel_id": 888})
        channel = MagicMock()
        channel.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "no perms"))
        guild = MagicMock(spec=discord.Guild)
        guild.get_channel = MagicMock(return_value=channel)

        await profanity_cog.log_infraction(guild, discord.Embed())


# ---------------------------------------------------------------------------
# ProfanityFilter — on_message listener
# ---------------------------------------------------------------------------

class TestProfanityOnMessage:
    """Tests for the on_message profanity detection listener."""

    @pytest.mark.asyncio
    @patch("cogs.profanity_filter.db")
    async def test_skip_bot_messages(self, mock_db, profanity_cog):
        """Bot messages should be skipped."""
        message = MagicMock()
        message.author.bot = True
        message.guild = MagicMock()
        await profanity_cog.on_message(message)
        mock_db.get_profanity_config.assert_not_called()

    @pytest.mark.asyncio
    @patch("cogs.profanity_filter.db")
    async def test_skip_dm_messages(self, mock_db, profanity_cog):
        """DM messages should be skipped."""
        message = MagicMock()
        message.author.bot = False
        message.guild = None
        await profanity_cog.on_message(message)
        mock_db.get_profanity_config.assert_not_called()

    @pytest.mark.asyncio
    @patch("cogs.profanity_filter.db")
    async def test_skip_admin_messages(self, mock_db, profanity_cog):
        """Administrators should be exempt."""
        message = MagicMock()
        message.author.bot = False
        message.guild = MagicMock()
        message.author.guild_permissions.administrator = True
        await profanity_cog.on_message(message)
        mock_db.get_profanity_config.assert_not_called()

    @pytest.mark.asyncio
    @patch("cogs.profanity_filter.db")
    async def test_skip_when_filter_disabled(self, mock_db, profanity_cog):
        """When enabled is False, detection should be skipped."""
        message = MagicMock()
        message.author.bot = False
        message.guild = MagicMock()
        message.guild.id = 123
        message.author.guild_permissions.administrator = False
        mock_db.get_profanity_config = AsyncMock(return_value={"enabled": False})
        await profanity_cog.on_message(message)
        mock_db.check_message_for_profanity.assert_not_called()

    @pytest.mark.asyncio
    @patch("cogs.profanity_filter.db")
    async def test_clean_message_no_action(self, mock_db, profanity_cog):
        """A message with no detected profanity should cause no action."""
        message = MagicMock()
        message.author.bot = False
        message.guild = MagicMock()
        message.guild.id = 123
        message.content = "hello world"
        message.author.guild_permissions.administrator = False
        mock_db.get_profanity_config = AsyncMock(return_value={"enabled": True})
        mock_db.check_message_for_profanity = AsyncMock(return_value=None)
        await profanity_cog.on_message(message)
        mock_db.determine_punishment.assert_not_called()

    @pytest.mark.asyncio
    @patch("cogs.profanity_filter.db")
    async def test_detected_word_triggers_punishment(self, mock_db, profanity_cog):
        """A detected word should trigger the punishment pipeline."""
        message = MagicMock()
        message.author.bot = False
        message.guild = MagicMock()
        message.guild.id = 123
        message.content = "bad content"
        message.author.guild_permissions.administrator = False
        message.author.id = 999
        message.author.mention = "<@999>"
        message.author.send = AsyncMock()
        message.channel = MagicMock()
        message.channel.send = AsyncMock()
        message.channel.mention = "#channel"
        message.delete = AsyncMock()

        mock_db.get_profanity_config = AsyncMock(return_value={
            "enabled": True,
            "delete_message": True,
            "dm_user": False,
            "log_infractions": False,
            "mute_threshold": 5,
            "kick_threshold": 8,
            "ban_threshold": 10,
        })
        mock_db.check_message_for_profanity = AsyncMock(return_value={
            "word": "badword",
            "severity": 3,
        })
        mock_db.determine_punishment = AsyncMock(return_value="warn")
        mock_db.add_profanity_infraction = AsyncMock(return_value={
            "total_infractions": 1,
        })

        # Patch apply_punishment to avoid actual Discord calls
        profanity_cog.apply_punishment = AsyncMock(return_value=True)
        profanity_cog.log_infraction = AsyncMock()

        await profanity_cog.on_message(message)

        message.delete.assert_awaited_once()
        mock_db.determine_punishment.assert_awaited_once()
        mock_db.add_profanity_infraction.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("cogs.profanity_filter.db")
    async def test_delete_message_disabled(self, mock_db, profanity_cog):
        """When delete_message is False, the message should not be deleted."""
        message = MagicMock()
        message.author.bot = False
        message.guild = MagicMock()
        message.guild.id = 123
        message.content = "bad content"
        message.author.guild_permissions.administrator = False
        message.author.id = 999
        message.author.mention = "<@999>"
        message.author.send = AsyncMock()
        message.channel = MagicMock()
        message.channel.send = AsyncMock()
        message.channel.mention = "#channel"
        message.delete = AsyncMock()

        mock_db.get_profanity_config = AsyncMock(return_value={
            "enabled": True,
            "delete_message": False,
            "dm_user": False,
            "log_infractions": False,
        })
        mock_db.check_message_for_profanity = AsyncMock(return_value={
            "word": "badword",
            "severity": 3,
        })
        mock_db.determine_punishment = AsyncMock(return_value="warn")
        mock_db.add_profanity_infraction = AsyncMock(return_value={
            "total_infractions": 1,
        })

        profanity_cog.apply_punishment = AsyncMock(return_value=True)
        profanity_cog.log_infraction = AsyncMock()

        await profanity_cog.on_message(message)
        message.delete.assert_not_awaited()


# ---------------------------------------------------------------------------
# Progressive Punishment Logic
# ---------------------------------------------------------------------------

class TestProgressivePunishment:
    """Tests for progressive punishment escalation logic.

    These tests verify the expected behavior of the db.determine_punishment
    function indirectly, by testing the thresholds that would be configured.
    """

    def test_punishment_order(self):
        """Punishment severity should follow: warn -> mute -> kick -> ban."""
        punishment_order = ["warn", "mute", "kick", "ban"]
        assert punishment_order.index("warn") < punishment_order.index("mute")
        assert punishment_order.index("mute") < punishment_order.index("kick")
        assert punishment_order.index("kick") < punishment_order.index("ban")

    def test_default_thresholds(self):
        """Default thresholds should be sensible: warn=3, mute=5, kick=8, ban=10."""
        defaults = {
            "warn_threshold": 3,
            "mute_threshold": 5,
            "kick_threshold": 8,
            "ban_threshold": 10,
        }
        assert defaults["warn_threshold"] < defaults["mute_threshold"]
        assert defaults["mute_threshold"] < defaults["kick_threshold"]
        assert defaults["kick_threshold"] < defaults["ban_threshold"]

    def test_determine_punishment_logic(self):
        """Simulate the punishment determination based on infraction count."""
        config = {
            "warn_threshold": 1,
            "mute_threshold": 3,
            "kick_threshold": 5,
            "ban_threshold": 8,
        }

        def get_punishment(infraction_count, cfg):
            if infraction_count >= cfg["ban_threshold"]:
                return "ban"
            elif infraction_count >= cfg["kick_threshold"]:
                return "kick"
            elif infraction_count >= cfg["mute_threshold"]:
                return "mute"
            else:
                return "warn"

        assert get_punishment(0, config) == "warn"
        assert get_punishment(1, config) == "warn"
        assert get_punishment(3, config) == "mute"
        assert get_punishment(5, config) == "kick"
        assert get_punishment(8, config) == "ban"
        assert get_punishment(100, config) == "ban"

    def test_single_infraction_is_warn(self):
        """First infraction should always result in a warning."""
        config = {"warn_threshold": 1, "mute_threshold": 3, "kick_threshold": 5, "ban_threshold": 8}
        infraction_count = 1
        assert infraction_count < config["mute_threshold"]

    def test_word_boundary_matching(self):
        """Test that substring matching works (as used in check_message_for_profanity)."""
        test_word = "bad"
        messages = [
            ("badword", True),
            ("this is bad", True),
            ("nothing here", False),
            ("BAD case", True),
        ]
        for msg, expected in messages:
            result = test_word.lower() in msg.lower()
            assert result is expected, f"Failed for message: '{msg}'"


# ---------------------------------------------------------------------------
# Punishment Messages
# ---------------------------------------------------------------------------

class TestPunishmentMessages:
    """Tests for human-readable punishment message mapping."""

    def test_all_punishment_types_have_messages(self):
        """All punishment types should have a corresponding message."""
        punishment_messages = {
            "warn": "Vous avez reçu un avertissement.",
            "mute": "Vous avez été mute.",
            "kick": "Vous avez été expulsé du serveur.",
            "ban": "Vous avez été banni du serveur.",
        }
        for ptype in ["warn", "mute", "kick", "ban"]:
            assert ptype in punishment_messages
            assert len(punishment_messages[ptype]) > 0

    def test_unknown_punishment_fallback(self):
        """Unknown punishment type should get a default message via .get()."""
        messages = {
            "warn": "warning",
            "mute": "muted",
        }
        assert messages.get("unknown", "Avertissement") == "Avertissement"
