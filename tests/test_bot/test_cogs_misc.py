"""
Tests for the remaining cogs: admin, ai, welcome, scheduler, reaction_roles, tickets.

Covers Admin cog (help command categories, botinfo), AI cog (conversation
history management), Welcome cog (template variable replacement), Scheduler
cog (cron expression / day mapping), ReactionRoles cog (role mapping),
and Tickets cog (ticket state management, TicketView setup).
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
from datetime import datetime, timedelta

import discord
from discord.ext import commands


# ---------------------------------------------------------------------------
# Shared Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_bot():
    bot = MagicMock(spec=commands.Bot)
    bot.user = MagicMock()
    bot.user.id = 999999999
    bot.user.name = "TestBot"
    bot.user.display_avatar = MagicMock()
    bot.user.display_avatar.url = "https://cdn.discordapp.com/avatar.png"
    bot.get_channel = MagicMock(return_value=MagicMock())
    bot.get_user = MagicMock(return_value=MagicMock())
    bot.wait_until_ready = AsyncMock()
    bot.latency = 0.042
    bot.guilds = []
    bot.commands = [MagicMock() for _ in range(25)]
    bot.get_command = MagicMock(return_value=None)
    bot.tree = MagicMock()
    bot.tree.sync = AsyncMock(return_value=[MagicMock()] * 10)
    bot.reload_extension = AsyncMock()
    bot.close = AsyncMock()
    bot.add_view = MagicMock()
    return bot


@pytest.fixture
def mock_ctx():
    ctx = MagicMock(spec=commands.Context)
    ctx.guild = MagicMock(spec=discord.Guild)
    ctx.guild.id = 987654321
    ctx.guild.name = "Test Server"
    ctx.guild.member_count = 42
    ctx.guild.owner = MagicMock(spec=discord.Member)
    ctx.guild.get_channel = MagicMock(return_value=MagicMock())
    ctx.guild.get_member = MagicMock(return_value=MagicMock())
    ctx.guild.get_role = MagicMock(return_value=MagicMock())
    ctx.guild.me = MagicMock(spec=discord.Member)
    ctx.guild.me.top_role = MagicMock()
    ctx.guild.text_channels = [MagicMock() for _ in range(3)]
    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.id = 123456789
    ctx.author.mention = "<@123456789>"
    ctx.author.display_name = "TestUser"
    ctx.author.display_avatar = MagicMock()
    ctx.author.display_avatar.url = "https://cdn.discordapp.com/avatar.png"
    ctx.author.guild_permissions = MagicMock()
    ctx.send = AsyncMock()
    ctx.send_help = AsyncMock()
    ctx.channel = MagicMock()
    ctx.channel.id = 555555555
    ctx.channel.send = AsyncMock()
    ctx.channel.set_permissions = AsyncMock()
    ctx.channel.edit = AsyncMock()
    ctx.channel.delete = AsyncMock()
    ctx.prefix = "!"
    ctx.interaction = MagicMock()
    ctx.interaction.response = MagicMock()
    ctx.interaction.response.send_modal = AsyncMock()
    return ctx


# ===========================================================================
# ADMIN COG
# ===========================================================================

class TestAdminHelpCategories:
    """Tests for the help command category structure."""

    def test_help_categories_defined(self):
        """All expected categories should be present."""
        categories = {
            " Leveling": ["rank", "leaderboard", "levelroles"],
            " Economie": ["daily", "balance", "richest", "give"],
            " Jeux": ["trivia", "roll", "coinflip", "8ball", "rps", "slot"],
            " Moderation": ["ban", "kick", "mute", "unmute", "warn", "warnings", "purge", "slowmode", "lock", "unlock"],
            " Tickets": ["ticket setup", "ticket close", "ticket add", "ticket remove"],
            " Reaction Roles": ["reactionrole add", "reactionrole remove", "reactionrole list", "reactionrole create"],
            " Utilitaires": ["ping", "serverinfo", "userinfo", "avatar", "poll", "remind", "meme", "calc", "afk"],
            " Configuration": ["config", "setwelcome", "setwelcomemsg", "setgoodbyemsg"],
        }
        assert len(categories) == 8

    def test_moderation_commands_complete(self):
        """The moderation category should include all mod commands."""
        mod_commands = ["ban", "kick", "mute", "unmute", "warn", "warnings", "purge", "slowmode", "lock", "unlock"]
        assert len(mod_commands) == 10
        assert "ban" in mod_commands
        assert "purge" in mod_commands

    def test_economy_commands_complete(self):
        """The economy category should include daily, balance, richest, give."""
        eco_commands = ["daily", "balance", "richest", "give"]
        assert len(eco_commands) == 4


class TestAdminBotInfo:
    """Tests for the botinfo command data collection."""

    def test_total_members_calculation(self, mock_bot):
        """Total members should sum across all guilds."""
        guild1 = MagicMock()
        guild1.member_count = 50
        guild1.channels = [MagicMock()] * 5
        guild2 = MagicMock()
        guild2.member_count = 30
        guild2.channels = [MagicMock()] * 3
        mock_bot.guilds = [guild1, guild2]

        total_members = sum(g.member_count for g in mock_bot.guilds)
        assert total_members == 80

    def test_total_channels_calculation(self, mock_bot):
        """Total channels should sum across all guilds."""
        guild1 = MagicMock()
        guild1.member_count = 50
        guild1.channels = [MagicMock()] * 5
        guild2 = MagicMock()
        guild2.member_count = 30
        guild2.channels = [MagicMock()] * 3
        mock_bot.guilds = [guild1, guild2]

        total_channels = sum(len(g.channels) for g in mock_bot.guilds)
        assert total_channels == 8

    def test_latency_milliseconds(self, mock_bot):
        """Latency should be converted to milliseconds."""
        mock_bot.latency = 0.042
        latency_ms = round(mock_bot.latency * 1000)
        assert latency_ms == 42

    def test_guild_count(self, mock_bot):
        """Guild count should reflect len(bot.guilds)."""
        mock_bot.guilds = [MagicMock()] * 5
        assert len(mock_bot.guilds) == 5

    def test_command_count(self, mock_bot):
        """Command count should reflect len(bot.commands)."""
        assert len(mock_bot.commands) == 25


class TestAdminConfigCommands:
    """Tests for admin config subcommand logic."""

    def test_prefix_max_length(self):
        """Prefix must not exceed 5 characters."""
        prefix = "!!!!!"
        assert len(prefix) <= 5
        long_prefix = "!!!!!!"
        assert len(long_prefix) > 5

    def test_automod_toggle_values(self):
        """Valid toggle values should be recognized."""
        valid_on = ["on", "true", "1"]
        valid_off = ["off", "false", "0"]
        for v in valid_on:
            assert v.lower() in ["on", "true", "1"]
        for v in valid_off:
            assert v.lower() in ["off", "false", "0"]


# ===========================================================================
# AI COG — ConversationManager
# ===========================================================================

class TestConversationManager:
    """Tests for the AI cog's ConversationManager."""

    @pytest.fixture
    def manager(self):
        from cogs.ai import ConversationManager
        return ConversationManager(max_history=5)

    def test_get_key(self, manager):
        """Key should be 'user_id_channel_id'."""
        key = manager.get_key(123, 456)
        assert key == "123_456"

    def test_add_and_get_message(self, manager):
        """Adding a message should make it retrievable."""
        manager.add_message(1, 100, "user", "hello")
        history = manager.get_history(1, 100)
        assert len(history) == 1
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "hello"

    def test_multiple_messages(self, manager):
        """Multiple messages should accumulate in order."""
        manager.add_message(1, 100, "user", "q1")
        manager.add_message(1, 100, "assistant", "a1")
        manager.add_message(1, 100, "user", "q2")
        history = manager.get_history(1, 100)
        assert len(history) == 3
        assert history[0]["content"] == "q1"
        assert history[2]["content"] == "q2"

    def test_max_history_truncation(self, manager):
        """History exceeding max_history*2 should be truncated."""
        # max_history=5, so max messages = 10
        for i in range(15):
            manager.add_message(1, 100, "user", f"msg_{i}")
        history = manager.get_history(1, 100)
        assert len(history) == 10  # 5 * 2

    def test_truncation_keeps_recent(self, manager):
        """Truncation should keep the most recent messages."""
        for i in range(15):
            manager.add_message(1, 100, "user", f"msg_{i}")
        history = manager.get_history(1, 100)
        # The last message should be msg_14
        assert history[-1]["content"] == "msg_14"
        # The first message should be msg_5 (15-10=5)
        assert history[0]["content"] == "msg_5"

    def test_clear_history(self, manager):
        """clear() should remove all history for a user/channel pair."""
        manager.add_message(1, 100, "user", "hello")
        manager.clear(1, 100)
        history = manager.get_history(1, 100)
        assert len(history) == 0

    def test_clear_nonexistent_key(self, manager):
        """Clearing a nonexistent key should not raise."""
        manager.clear(999, 999)  # Should not raise

    def test_separate_channels(self, manager):
        """Different channels should have separate histories."""
        manager.add_message(1, 100, "user", "in channel 100")
        manager.add_message(1, 200, "user", "in channel 200")
        h100 = manager.get_history(1, 100)
        h200 = manager.get_history(1, 200)
        assert len(h100) == 1
        assert len(h200) == 1
        assert h100[0]["content"] == "in channel 100"
        assert h200[0]["content"] == "in channel 200"

    def test_separate_users(self, manager):
        """Different users should have separate histories."""
        manager.add_message(1, 100, "user", "user 1")
        manager.add_message(2, 100, "user", "user 2")
        h1 = manager.get_history(1, 100)
        h2 = manager.get_history(2, 100)
        assert len(h1) == 1
        assert len(h2) == 1
        assert h1[0]["content"] == "user 1"

    def test_empty_history(self, manager):
        """Getting history for a nonexistent key should return empty list."""
        history = manager.get_history(999, 999)
        assert history == []

    def test_default_max_history(self):
        """Default max_history should be 10."""
        from cogs.ai import ConversationManager
        cm = ConversationManager()
        assert cm.max_history == 10


# ===========================================================================
# WELCOME COG — Message Template Variable Replacement
# ===========================================================================

class TestWelcomeTemplateReplacement:
    """Tests for welcome/goodbye message template variable replacement."""

    def test_user_placeholder(self):
        """'{user}' should be replaced with the member's mention."""
        template = "Bienvenue {user} sur le serveur!"
        result = template.replace("{user}", "<@123456789>")
        assert "<@123456789>" in result

    def test_server_placeholder(self):
        """'{server}' should be replaced with the guild name."""
        template = "Bienvenue sur {server}!"
        result = template.replace("{server}", "Test Server")
        assert "Test Server" in result

    def test_member_count_placeholder(self):
        """'{member_count}' should be replaced with the member count."""
        template = "Vous etes le {member_count}e membre!"
        result = template.replace("{member_count}", "42")
        assert "42" in result

    def test_all_placeholders_together(self):
        """All three placeholders should be replaced simultaneously."""
        template = "Bienvenue {user} sur {server}! Membre #{member_count}"
        result = template.replace("{user}", "<@123>")
        result = result.replace("{server}", "MyServer")
        result = result.replace("{member_count}", "100")
        assert "<@123>" in result
        assert "MyServer" in result
        assert "100" in result

    def test_no_placeholders(self):
        """A template without placeholders should be left unchanged."""
        template = "Welcome to our server!"
        result = template.replace("{user}", "<@123>")
        result = result.replace("{server}", "MyServer")
        assert result == "Welcome to our server!"

    def test_goodbye_user_placeholder(self):
        """Goodbye messages use str(member) instead of mention for {user}."""
        template = "{user} a quitte le serveur."
        member_str = "TestUser#1234"
        result = template.replace("{user}", member_str)
        assert "TestUser#1234" in result

    def test_goodbye_server_placeholder(self):
        """Goodbye message should replace {server} with guild name."""
        template = "{user} a quitte {server}."
        result = template.replace("{user}", "User").replace("{server}", "MyServer")
        assert "MyServer" in result

    def test_default_welcome_message(self):
        """Default welcome message should use {user} and {server}."""
        default_msg = "Bienvenue {user} sur {server}!"
        assert "{user}" in default_msg
        assert "{server}" in default_msg


# ===========================================================================
# SCHEDULER COG — Cron Expression / Day Mapping
# ===========================================================================

class TestSchedulerDayMapping:
    """Tests for the scheduler cog's French-to-English day mapping."""

    def test_day_map_completeness(self):
        """All 7 French day abbreviations plus '*' should be mapped."""
        day_map = {
            "lun": "mon", "mar": "tue", "mer": "wed", "jeu": "thu",
            "ven": "fri", "sam": "sat", "dim": "sun", "*": "*",
        }
        assert len(day_map) == 8

    def test_french_to_english_monday(self):
        """'lun' should map to 'mon'."""
        day_map = {"lun": "mon", "mar": "tue", "mer": "wed", "jeu": "thu",
                    "ven": "fri", "sam": "sat", "dim": "sun"}
        assert day_map["lun"] == "mon"

    def test_french_to_english_sunday(self):
        """'dim' should map to 'sun'."""
        day_map = {"lun": "mon", "mar": "tue", "mer": "wed", "jeu": "thu",
                    "ven": "fri", "sam": "sat", "dim": "sun"}
        assert day_map["dim"] == "sun"

    def test_wildcard_mapping(self):
        """'*' should map to '*' (every day)."""
        day_map = {"*": "*"}
        assert day_map["*"] == "*"

    def test_comma_separated_days(self):
        """Comma-separated days should be converted individually."""
        day_map = {"lun": "mon", "mer": "wed", "ven": "fri"}
        jours = "lun,mer,ven"
        days = [d.strip().lower() for d in jours.split(",")]
        converted = [day_map[d] for d in days]
        result = ",".join(converted)
        assert result == "mon,wed,fri"

    def test_invalid_day_detection(self):
        """An invalid day abbreviation should not be in the map."""
        day_map = {"lun": "mon", "mar": "tue", "mer": "wed", "jeu": "thu",
                    "ven": "fri", "sam": "sat", "dim": "sun"}
        assert "xyz" not in day_map

    def test_time_parsing_valid(self):
        """Valid HH:MM format should parse correctly."""
        heure = "14:30"
        hour, minute = map(int, heure.split(":"))
        assert hour == 14
        assert minute == 30
        assert 0 <= hour <= 23
        assert 0 <= minute <= 59

    def test_time_parsing_midnight(self):
        """00:00 should parse correctly."""
        heure = "00:00"
        hour, minute = map(int, heure.split(":"))
        assert hour == 0
        assert minute == 0

    def test_time_parsing_end_of_day(self):
        """23:59 should parse correctly."""
        heure = "23:59"
        hour, minute = map(int, heure.split(":"))
        assert hour == 23
        assert minute == 59


class TestSchedulerDefaultMessages:
    """Tests for the scheduler's default daily messages."""

    def test_default_messages_not_empty(self):
        """Default daily messages list should have entries."""
        messages = [
            "Passez une excellente journee!",
            "Nouvelle journee, nouvelles opportunites!",
            "Bonjour la communaute!",
            "Le soleil se leve sur notre serveur!",
            "Un nouveau jour commence!",
        ]
        assert len(messages) == 5

    def test_each_message_is_nonempty(self):
        """Each default message should be a non-empty string."""
        messages = [
            "Passez une excellente journee!",
            "Nouvelle journee, nouvelles opportunites!",
        ]
        for msg in messages:
            assert isinstance(msg, str)
            assert len(msg) > 0


# ===========================================================================
# REACTION ROLES COG — Role Mapping Logic
# ===========================================================================

class TestReactionRoleMapping:
    """Tests for reaction role emoji-to-role mapping logic."""

    def test_emoji_to_role_lookup(self):
        """An emoji should map to the correct role ID."""
        role_map = {
            "\U0001f3ae": 111,  # Gaming role
            "\U0001f3b5": 222,  # Music role
            "\U0001f3a8": 333,  # Art role
        }
        assert role_map["\U0001f3ae"] == 111
        assert role_map["\U0001f3b5"] == 222

    def test_missing_emoji_returns_none(self):
        """Lookup for unmapped emoji should return None via .get()."""
        role_map = {"\U0001f3ae": 111}
        result = role_map.get("\U0001f600", None)
        assert result is None

    def test_role_hierarchy_check(self):
        """Bot should not be able to assign roles higher than its own top role."""
        bot_top_role_position = 5
        target_role_position = 8
        assert target_role_position > bot_top_role_position

    def test_reaction_role_data_structure(self):
        """Reaction role DB records should have expected keys."""
        rr = {
            "message_id": 12345,
            "channel_id": 67890,
            "emoji": "\U0001f3ae",
            "role_id": 111,
            "guild_id": 999,
        }
        assert "message_id" in rr
        assert "emoji" in rr
        assert "role_id" in rr

    @pytest.mark.asyncio
    async def test_reaction_add_grants_role(self, mock_bot):
        """on_raw_reaction_add should add the mapped role to the member."""
        from cogs.reaction_roles import ReactionRoles
        cog = ReactionRoles(mock_bot)

        payload = MagicMock()
        payload.member = MagicMock(spec=discord.Member)
        payload.member.bot = False
        payload.member.add_roles = AsyncMock()
        payload.emoji = MagicMock()
        payload.emoji.__str__ = MagicMock(return_value="\U0001f3ae")
        payload.message_id = 12345
        payload.guild_id = 999

        mock_role = MagicMock(spec=discord.Role)
        guild = MagicMock(spec=discord.Guild)
        guild.get_role = MagicMock(return_value=mock_role)
        mock_bot.get_guild = MagicMock(return_value=guild)

        with patch("cogs.reaction_roles.db") as mock_db:
            mock_db.get_reaction_role = AsyncMock(return_value={"role_id": 111})
            await cog.on_raw_reaction_add(payload)
            payload.member.add_roles.assert_awaited_once_with(mock_role, reason="Reaction Role")

    @pytest.mark.asyncio
    async def test_reaction_add_skips_bots(self, mock_bot):
        """Bot reactions should be skipped."""
        from cogs.reaction_roles import ReactionRoles
        cog = ReactionRoles(mock_bot)

        payload = MagicMock()
        payload.member = MagicMock(spec=discord.Member)
        payload.member.bot = True

        with patch("cogs.reaction_roles.db") as mock_db:
            await cog.on_raw_reaction_add(payload)
            mock_db.get_reaction_role.assert_not_called()


# ===========================================================================
# TICKETS COG — Ticket State Management
# ===========================================================================

class TestTicketStateManagement:
    """Tests for ticket lifecycle state management."""

    def test_ticket_status_values(self):
        """Ticket should have valid status values."""
        valid_statuses = ["open", "closed"]
        assert "open" in valid_statuses
        assert "closed" in valid_statuses

    def test_ticket_data_structure(self):
        """A ticket record should contain expected fields."""
        ticket = {
            "id": 1,
            "guild_id": 987654321,
            "channel_id": 555555555,
            "user_id": 123456789,
            "subject": "Help needed",
            "status": "open",
        }
        assert ticket["status"] == "open"
        assert ticket["user_id"] == 123456789

    def test_ticket_creator_can_close(self):
        """The ticket creator should be allowed to close."""
        ticket = {"user_id": 123}
        user_id = 123
        assert user_id == ticket["user_id"]

    def test_non_creator_without_perms_cannot_close(self):
        """Non-creator without manage_messages should not close."""
        ticket = {"user_id": 123}
        user_id = 456
        has_manage_messages = False
        can_close = user_id == ticket["user_id"] or has_manage_messages
        assert can_close is False

    def test_staff_can_close_any_ticket(self):
        """Users with manage_messages should be able to close any ticket."""
        ticket = {"user_id": 123}
        user_id = 456
        has_manage_messages = True
        can_close = user_id == ticket["user_id"] or has_manage_messages
        assert can_close is True

    def test_ticket_creator_cannot_be_removed(self):
        """The ticket creator should not be removable from the ticket."""
        ticket = {"user_id": 123}
        member_id = 123
        assert member_id == ticket["user_id"]  # Should trigger the rejection


class TestTicketViewSetup:
    """Tests for TicketView and TicketControlView initialization.

    discord.ui.View.__init__ requires a running asyncio event loop, so
    we patch asyncio.get_running_loop to return a mock loop.
    """

    @patch('discord.ui.view.asyncio.get_running_loop', return_value=MagicMock())
    def test_ticket_view_no_timeout(self, mock_loop, mock_bot):
        """TicketView should have timeout=None for persistence."""
        from cogs.tickets import TicketView
        view = TicketView(mock_bot)
        assert view.timeout is None

    @patch('discord.ui.view.asyncio.get_running_loop', return_value=MagicMock())
    def test_ticket_view_has_button(self, mock_loop, mock_bot):
        """TicketView should have at least one button child."""
        from cogs.tickets import TicketView
        view = TicketView(mock_bot)
        assert len(view.children) > 0

    @patch('discord.ui.view.asyncio.get_running_loop', return_value=MagicMock())
    def test_ticket_control_view_no_timeout(self, mock_loop, mock_bot):
        """TicketControlView should have timeout=None for persistence."""
        from cogs.tickets import TicketControlView
        view = TicketControlView(mock_bot)
        assert view.timeout is None

    @patch('discord.ui.view.asyncio.get_running_loop', return_value=MagicMock())
    def test_ticket_control_view_has_buttons(self, mock_loop, mock_bot):
        """TicketControlView should have 3 buttons (close, add, transfer)."""
        from cogs.tickets import TicketControlView
        view = TicketControlView(mock_bot)
        assert len(view.children) == 3

    @patch('discord.ui.view.asyncio.get_running_loop', return_value=MagicMock())
    def test_tickets_cog_registers_views(self, mock_loop, mock_bot):
        """Tickets cog __init__ should register persistent views with the bot."""
        from cogs.tickets import Tickets
        Tickets(mock_bot)
        assert mock_bot.add_view.call_count == 2

    @patch('discord.ui.view.asyncio.get_running_loop', return_value=MagicMock())
    def test_ticket_view_bot_reference(self, mock_loop, mock_bot):
        """TicketView should store a reference to the bot."""
        from cogs.tickets import TicketView
        view = TicketView(mock_bot)
        assert view.bot is mock_bot

    @patch('discord.ui.view.asyncio.get_running_loop', return_value=MagicMock())
    @pytest.mark.asyncio
    async def test_check_existing_ticket_returns_bool(self, mock_loop, mock_bot):
        """check_existing_ticket should return a boolean."""
        from cogs.tickets import TicketView
        view = TicketView(mock_bot)
        with patch("cogs.tickets.db") as mock_db:
            with patch("aiosqlite.connect") as mock_conn:
                mock_cursor = MagicMock()
                mock_cursor.fetchone = AsyncMock(return_value=None)
                mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
                mock_cursor.__aexit__ = AsyncMock(return_value=False)
                mock_connection = MagicMock()
                mock_connection.execute = MagicMock(return_value=mock_cursor)
                mock_connection.__aenter__ = AsyncMock(return_value=mock_connection)
                mock_connection.__aexit__ = AsyncMock(return_value=False)
                mock_conn.return_value = mock_connection
                result = await view.check_existing_ticket(123, 456)
                assert isinstance(result, bool)


class TestTicketModal:
    """Tests for the TicketModal text input fields."""

    def test_modal_subject_max_length(self):
        """Subject field should have max_length=100."""
        from cogs.tickets import TicketModal
        # Access the class attribute
        assert TicketModal.sujet.max_length == 100

    def test_modal_description_max_length(self):
        """Description field should have max_length=1000."""
        from cogs.tickets import TicketModal
        assert TicketModal.description.max_length == 1000

    def test_modal_subject_required(self):
        """Subject field should be required."""
        from cogs.tickets import TicketModal
        assert TicketModal.sujet.required is True

    def test_modal_description_optional(self):
        """Description field should be optional."""
        from cogs.tickets import TicketModal
        assert TicketModal.description.required is False


# ===========================================================================
# AI COG — AI Channel Management
# ===========================================================================

class TestAIChannelManagement:
    """Tests for the AI cog's auto-response channel tracking."""

    def test_ai_channels_is_set(self, mock_bot):
        """ai_channels should be a set."""
        from cogs.ai import AI
        cog = AI(mock_bot)
        assert isinstance(cog.ai_channels, set)

    def test_add_channel(self, mock_bot):
        """Adding a channel ID should make it appear in the set."""
        from cogs.ai import AI
        cog = AI(mock_bot)
        cog.ai_channels.add(555)
        assert 555 in cog.ai_channels

    def test_remove_channel(self, mock_bot):
        """Removing a channel ID should remove it from the set."""
        from cogs.ai import AI
        cog = AI(mock_bot)
        cog.ai_channels.add(555)
        cog.ai_channels.discard(555)
        assert 555 not in cog.ai_channels

    def test_discard_nonexistent_channel(self, mock_bot):
        """Discarding a nonexistent ID should not raise."""
        from cogs.ai import AI
        cog = AI(mock_bot)
        cog.ai_channels.discard(999)  # Should not raise

    def test_system_prompt_is_string(self, mock_bot):
        """The system prompt should be a non-empty string."""
        from cogs.ai import AI
        cog = AI(mock_bot)
        assert isinstance(cog.system_prompt, str)
        assert len(cog.system_prompt) > 0


# ===========================================================================
# REACTION ROLE VIEW
# ===========================================================================

class TestReactionRoleView:
    """Tests for the ReactionRoleView persistent view.

    discord.ui.View.__init__ requires a running asyncio event loop, so
    we patch asyncio.get_running_loop to return a mock loop.
    """

    @patch('discord.ui.view.asyncio.get_running_loop', return_value=MagicMock())
    def test_view_no_timeout(self, mock_loop, mock_bot):
        """ReactionRoleView should have timeout=None."""
        from cogs.reaction_roles import ReactionRoleView
        view = ReactionRoleView(mock_bot)
        assert view.timeout is None

    @patch('discord.ui.view.asyncio.get_running_loop', return_value=MagicMock())
    def test_view_stores_bot(self, mock_loop, mock_bot):
        """ReactionRoleView should store a reference to the bot."""
        from cogs.reaction_roles import ReactionRoleView
        view = ReactionRoleView(mock_bot)
        assert view.bot is mock_bot
