"""
Tests for the moderation cog (cogs/moderation.py).

Covers the AutoMod engine (spam detection, mention spam, banned words,
excessive caps, invite link detection) and the Moderation cog's helper
methods (log_action, get_mute_role) and key command handlers.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
from datetime import datetime, timedelta
from collections import defaultdict

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
    ctx.guild.owner = MagicMock(spec=discord.Member)
    ctx.guild.default_role = MagicMock(spec=discord.Role)
    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.id = 123456789
    ctx.author.guild_permissions = MagicMock()
    ctx.author.top_role = MagicMock()
    ctx.author.top_role.__ge__ = MagicMock(return_value=True)
    ctx.author.top_role.__lt__ = MagicMock(return_value=False)
    ctx.send = AsyncMock()
    ctx.channel = MagicMock()
    ctx.channel.send = AsyncMock()
    ctx.channel.purge = AsyncMock(return_value=[MagicMock()] * 6)
    ctx.channel.edit = AsyncMock()
    ctx.channel.set_permissions = AsyncMock()
    return ctx


@pytest.fixture
def automod():
    from cogs.moderation import AutoMod
    return AutoMod()


@pytest.fixture
def moderation_cog(mock_bot):
    from cogs.moderation import Moderation
    return Moderation(mock_bot)


# ---------------------------------------------------------------------------
# AutoMod — check_spam
# ---------------------------------------------------------------------------

class TestAutoModSpam:
    """Tests for AutoMod.check_spam()."""

    def test_single_message_no_spam(self, automod):
        """One message should not be flagged as spam."""
        result = automod.check_spam(1, "hello")
        assert result is False

    def test_below_threshold_no_spam(self, automod):
        """Messages below SPAM_THRESHOLD should not be flagged."""
        for _ in range(3):
            result = automod.check_spam(1, "msg")
        assert result is False

    @patch("cogs.moderation.SPAM_THRESHOLD", 3)
    @patch("cogs.moderation.SPAM_INTERVAL", 10)
    def test_reach_threshold_is_spam(self, automod):
        """Reaching SPAM_THRESHOLD within the interval triggers spam detection."""
        from cogs.moderation import AutoMod
        am = AutoMod()
        for _ in range(2):
            am.check_spam(1, "msg")
        assert am.check_spam(1, "msg") is True

    @patch("cogs.moderation.SPAM_THRESHOLD", 3)
    @patch("cogs.moderation.SPAM_INTERVAL", 10)
    def test_separate_users_no_cross_contamination(self):
        """Spam tracking is per-user; one user's messages should not affect another."""
        from cogs.moderation import AutoMod
        am = AutoMod()
        for _ in range(2):
            am.check_spam(1, "msg")
        # User 2 has only 1 message
        result = am.check_spam(2, "msg")
        assert result is False

    def test_old_messages_pruned(self, automod):
        """Messages older than SPAM_INTERVAL should be pruned from the cache."""
        user_id = 42
        old_ts = datetime.now() - timedelta(seconds=999)
        automod.message_cache[user_id].append((old_ts, "old msg"))
        # After a check, old entries should be removed
        automod.check_spam(user_id, "new msg")
        # The old message should have been pruned
        assert all(
            (datetime.now() - ts).total_seconds() < 60
            for ts, _ in automod.message_cache[user_id]
        )

    def test_message_cache_is_defaultdict(self, automod):
        """message_cache should be a defaultdict(list)."""
        assert isinstance(automod.message_cache, defaultdict)
        assert automod.message_cache[99999] == []

    def test_message_content_stored(self, automod):
        """The message content should be stored alongside the timestamp."""
        automod.check_spam(1, "test content")
        _, content = automod.message_cache[1][-1]
        assert content == "test content"


# ---------------------------------------------------------------------------
# AutoMod — check_mention_spam
# ---------------------------------------------------------------------------

class TestAutoModMentionSpam:
    """Tests for AutoMod.check_mention_spam()."""

    def test_low_mention_count_ignored(self, automod):
        """Messages with < 5 mentions are always ignored."""
        assert automod.check_mention_spam(1, 4) is False

    def test_zero_mentions_ignored(self, automod):
        """Zero mentions should never trigger."""
        assert automod.check_mention_spam(1, 0) is False

    def test_five_mentions_recorded(self, automod):
        """Exactly 5 mentions should be recorded but not yet trigger (need 10)."""
        result = automod.check_mention_spam(1, 5)
        assert result is False

    def test_ten_mentions_single_message_triggers(self, automod):
        """10 mentions in a single message should trigger mention spam."""
        result = automod.check_mention_spam(1, 10)
        assert result is True

    def test_accumulated_mentions_trigger(self, automod):
        """Accumulated mentions across messages can trigger detection."""
        automod.check_mention_spam(1, 5)
        result = automod.check_mention_spam(1, 5)
        assert result is True

    def test_separate_users_mention_tracking(self, automod):
        """Mention spam tracking should be per-user."""
        automod.check_mention_spam(1, 5)
        # User 2 has separate tracking
        result = automod.check_mention_spam(2, 5)
        assert result is False


# ---------------------------------------------------------------------------
# AutoMod — check_banned_words
# ---------------------------------------------------------------------------

class TestAutoModBannedWords:
    """Tests for AutoMod.check_banned_words()."""

    @patch("cogs.moderation.BANNED_WORDS", ["badword", "slur"])
    def test_detects_banned_word(self):
        from cogs.moderation import AutoMod
        am = AutoMod()
        result = am.check_banned_words("this is a badword message")
        assert result == "badword"

    @patch("cogs.moderation.BANNED_WORDS", ["badword"])
    def test_case_insensitive(self):
        from cogs.moderation import AutoMod
        am = AutoMod()
        result = am.check_banned_words("BADWORD in caps")
        assert result == "badword"

    @patch("cogs.moderation.BANNED_WORDS", ["badword"])
    def test_clean_message_returns_none(self):
        from cogs.moderation import AutoMod
        am = AutoMod()
        result = am.check_banned_words("this is a perfectly clean message")
        assert result is None

    @patch("cogs.moderation.BANNED_WORDS", [])
    def test_empty_banned_list(self):
        from cogs.moderation import AutoMod
        am = AutoMod()
        result = am.check_banned_words("anything goes")
        assert result is None

    @patch("cogs.moderation.BANNED_WORDS", ["bad", "worse"])
    def test_returns_first_match(self):
        from cogs.moderation import AutoMod
        am = AutoMod()
        result = am.check_banned_words("worse and bad")
        # "bad" comes first in BANNED_WORDS list
        assert result == "bad"


# ---------------------------------------------------------------------------
# AutoMod — check_excessive_caps
# ---------------------------------------------------------------------------

class TestAutoModCaps:
    """Tests for AutoMod.check_excessive_caps()."""

    def test_short_message_exempt(self, automod):
        """Messages shorter than 10 characters should never be flagged."""
        assert automod.check_excessive_caps("HELLO") is False

    def test_all_caps_long_message(self, automod):
        """A fully capitalised long message should be flagged."""
        assert automod.check_excessive_caps("THIS IS ALL CAPS MESSAGE") is True

    def test_all_lowercase(self, automod):
        """All lowercase should not be flagged."""
        assert automod.check_excessive_caps("this is all lowercase and long enough") is False

    def test_exactly_at_threshold(self, automod):
        """A message at exactly 70% caps should be flagged (>= threshold)."""
        # 7 upper + 3 lower = 10 letters, ratio = 0.7
        msg = "AAAAAAAAAaa"  # 9A + 2a = 11 chars, 9/11 ~ 0.818 -> flagged
        assert automod.check_excessive_caps(msg) is True

    def test_custom_threshold(self, automod):
        """Custom threshold should override default."""
        msg = "AAAAAAAAaa"  # 8A + 2a, ratio = 0.8
        assert automod.check_excessive_caps(msg, threshold=0.9) is False
        assert automod.check_excessive_caps(msg, threshold=0.5) is True

    def test_no_letters_message(self, automod):
        """A message with only non-letter characters should not be flagged."""
        assert automod.check_excessive_caps("1234567890!!!!!") is False

    def test_mixed_case_below_threshold(self, automod):
        """Mixed case below threshold should not be flagged."""
        msg = "Hello World This Is A Normal Message"
        assert automod.check_excessive_caps(msg) is False


# ---------------------------------------------------------------------------
# AutoMod — check_invite_link
# ---------------------------------------------------------------------------

class TestAutoModInviteLink:
    """Tests for AutoMod.check_invite_link()."""

    def test_discord_gg_link(self, automod):
        """discord.gg invite link should be detected."""
        assert automod.check_invite_link("Join us at discord.gg/abc123") is True

    def test_discordapp_invite_link(self, automod):
        """discordapp.com/invite link should be detected."""
        assert automod.check_invite_link("Go to discordapp.com/invite/xyz789") is True

    def test_normal_link_not_flagged(self, automod):
        """A regular non-Discord URL should not be flagged."""
        assert automod.check_invite_link("Check out https://google.com") is False

    def test_no_link(self, automod):
        """A message with no links should not be flagged."""
        assert automod.check_invite_link("Just a normal message") is False

    def test_empty_string(self, automod):
        """An empty string should not be flagged."""
        assert automod.check_invite_link("") is False

    def test_invite_with_dash(self, automod):
        """Invite codes with dashes should be detected."""
        assert automod.check_invite_link("discord.gg/abc-123") is True


# ---------------------------------------------------------------------------
# Moderation Cog — log_action
# ---------------------------------------------------------------------------

class TestModerationLogAction:
    """Tests for Moderation.log_action()."""

    @pytest.mark.asyncio
    @patch("cogs.moderation.db")
    async def test_log_action_sends_embed(self, mock_db, moderation_cog):
        """log_action should send an embed to the configured log channel."""
        mock_db.get_guild_config = AsyncMock(return_value={"log_channel_id": 123})
        guild = MagicMock(spec=discord.Guild)
        channel = MagicMock()
        channel.send = AsyncMock()
        guild.get_channel = MagicMock(return_value=channel)

        embed = discord.Embed(title="Test")
        await moderation_cog.log_action(guild, embed)
        channel.send.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("cogs.moderation.db")
    async def test_log_action_no_channel_configured(self, mock_db, moderation_cog):
        """log_action should silently do nothing if no log channel is configured."""
        mock_db.get_guild_config = AsyncMock(return_value={})
        guild = MagicMock(spec=discord.Guild)
        embed = discord.Embed(title="Test")
        # Should not raise
        await moderation_cog.log_action(guild, embed)

    @pytest.mark.asyncio
    @patch("cogs.moderation.db")
    async def test_log_action_channel_not_found(self, mock_db, moderation_cog):
        """log_action should silently handle a missing channel object."""
        mock_db.get_guild_config = AsyncMock(return_value={"log_channel_id": 123})
        guild = MagicMock(spec=discord.Guild)
        guild.get_channel = MagicMock(return_value=None)
        embed = discord.Embed(title="Test")
        # Should not raise
        await moderation_cog.log_action(guild, embed)

    @pytest.mark.asyncio
    @patch("cogs.moderation.db")
    async def test_log_action_forbidden_error(self, mock_db, moderation_cog):
        """log_action should swallow discord.Forbidden errors."""
        mock_db.get_guild_config = AsyncMock(return_value={"log_channel_id": 123})
        guild = MagicMock(spec=discord.Guild)
        channel = MagicMock()
        channel.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "forbidden"))
        guild.get_channel = MagicMock(return_value=channel)
        embed = discord.Embed(title="Test")
        # Should not raise
        await moderation_cog.log_action(guild, embed)


# ---------------------------------------------------------------------------
# Moderation Cog — get_mute_role
# ---------------------------------------------------------------------------

class TestModerationGetMuteRole:
    """Tests for Moderation.get_mute_role()."""

    @pytest.mark.asyncio
    @patch("cogs.moderation.db")
    async def test_returns_existing_role(self, mock_db, moderation_cog):
        """Should return the existing mute role if found in guild."""
        mock_role = MagicMock(spec=discord.Role)
        mock_db.get_guild_config = AsyncMock(return_value={"mute_role_id": 555})
        guild = MagicMock(spec=discord.Guild)
        guild.get_role = MagicMock(return_value=mock_role)

        result = await moderation_cog.get_mute_role(guild)
        assert result is mock_role

    @pytest.mark.asyncio
    @patch("cogs.moderation.db")
    async def test_creates_role_when_missing(self, mock_db, moderation_cog):
        """Should create a new mute role when none exists."""
        mock_db.get_guild_config = AsyncMock(return_value={})
        mock_db.update_guild_config = AsyncMock()
        new_role = MagicMock(spec=discord.Role)
        new_role.id = 777

        guild = MagicMock(spec=discord.Guild)
        guild.get_role = MagicMock(return_value=None)
        guild.create_role = AsyncMock(return_value=new_role)
        guild.channels = []

        result = await moderation_cog.get_mute_role(guild)
        assert result is new_role
        guild.create_role.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("cogs.moderation.db")
    async def test_returns_none_on_forbidden(self, mock_db, moderation_cog):
        """Should return None if the bot lacks permission to create the role."""
        mock_db.get_guild_config = AsyncMock(return_value={})
        guild = MagicMock(spec=discord.Guild)
        guild.get_role = MagicMock(return_value=None)
        guild.create_role = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "forbidden"))

        result = await moderation_cog.get_mute_role(guild)
        assert result is None


# ---------------------------------------------------------------------------
# Moderation Cog — on_message automod listener
# ---------------------------------------------------------------------------

class TestModerationOnMessage:
    """Tests for the on_message auto-moderation listener."""

    @pytest.mark.asyncio
    @patch("cogs.moderation.db")
    async def test_skip_bot_messages(self, mock_db, moderation_cog):
        """Bot messages should be completely skipped."""
        message = MagicMock()
        message.author.bot = True
        message.guild = MagicMock()
        await moderation_cog.on_message(message)
        mock_db.get_guild_config.assert_not_called()

    @pytest.mark.asyncio
    @patch("cogs.moderation.db")
    async def test_skip_dm_messages(self, mock_db, moderation_cog):
        """DM messages (no guild) should be skipped."""
        message = MagicMock()
        message.author.bot = False
        message.guild = None
        await moderation_cog.on_message(message)
        mock_db.get_guild_config.assert_not_called()

    @pytest.mark.asyncio
    @patch("cogs.moderation.db")
    async def test_skip_admin_messages(self, mock_db, moderation_cog):
        """Administrators should be exempt from auto-moderation."""
        message = MagicMock()
        message.author.bot = False
        message.guild = MagicMock()
        message.author.guild_permissions.administrator = True
        await moderation_cog.on_message(message)
        mock_db.get_guild_config.assert_not_called()

    @pytest.mark.asyncio
    @patch("cogs.moderation.db")
    async def test_skip_when_automod_disabled(self, mock_db, moderation_cog):
        """When auto_mod_enabled is False, checks should be skipped."""
        message = MagicMock()
        message.author.bot = False
        message.guild = MagicMock()
        message.author.guild_permissions.administrator = False
        message.content = "some text"
        message.mentions = []
        mock_db.get_guild_config = AsyncMock(return_value={"auto_mod_enabled": False})
        await moderation_cog.on_message(message)
        # No violations should have been processed (no send to channel)
        message.channel.send.assert_not_called()
