"""
Integration tests for cog command methods.

These tests directly exercise the cog command methods to achieve higher coverage
on moderation, profanity_filter, tickets, and reaction_roles cogs.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
from datetime import datetime, timedelta
import discord
from discord.ext import commands


# =============================================================================
# Moderation Cog Command Tests
# =============================================================================

class TestModerationCommands:
    """Tests for Moderation cog command methods."""

    @pytest.fixture
    def mock_bot(self):
        bot = MagicMock(spec=commands.Bot)
        bot.user = MagicMock()
        bot.user.id = 999999999
        return bot

    @pytest.fixture
    def mock_ctx(self, mock_bot):
        ctx = MagicMock(spec=commands.Context)
        ctx.bot = mock_bot
        ctx.guild = MagicMock(spec=discord.Guild)
        ctx.guild.id = 123456789
        ctx.guild.owner = MagicMock()
        ctx.guild.default_role = MagicMock()
        ctx.author = MagicMock(spec=discord.Member)
        ctx.author.top_role = MagicMock()
        ctx.author.top_role.position = 10
        ctx.channel = MagicMock(spec=discord.TextChannel)
        ctx.channel.send = AsyncMock()
        ctx.channel.purge = AsyncMock(return_value=[MagicMock() for _ in range(5)])
        ctx.channel.edit = AsyncMock()
        ctx.channel.set_permissions = AsyncMock()
        ctx.send = AsyncMock()
        ctx.prefix = "!"
        return ctx

    @pytest.mark.asyncio
    @patch('cogs.moderation.db')
    async def test_ban_command_success(self, mock_db, mock_bot, mock_ctx):
        """Test successful ban command."""
        from cogs.moderation import Moderation

        mock_db.get_guild_config = AsyncMock(return_value={'log_channel_id': None})

        cog = Moderation(mock_bot)

        member = MagicMock(spec=discord.Member)
        member.top_role = MagicMock()
        member.top_role.position = 5  # Lower than author
        member.top_role.__ge__ = MagicMock(return_value=False)
        member.mention = "<@12345>"
        member.ban = AsyncMock()

        mock_ctx.author.top_role.__le__ = MagicMock(return_value=False)

        await cog.ban.callback(cog, mock_ctx, member, raison="Test ban")

        member.ban.assert_called_once()
        mock_ctx.send.assert_called()

    @pytest.mark.asyncio
    @patch('cogs.moderation.db')
    async def test_ban_command_hierarchy_check(self, mock_db, mock_bot, mock_ctx):
        """Test ban fails when target has higher role."""
        from cogs.moderation import Moderation

        cog = Moderation(mock_bot)

        member = MagicMock(spec=discord.Member)
        member.top_role = MagicMock()
        member.top_role.position = 15  # Higher than author
        member.top_role.__ge__ = MagicMock(return_value=True)

        mock_ctx.author.top_role.__le__ = MagicMock(return_value=True)
        mock_ctx.author.__ne__ = MagicMock(return_value=True)
        mock_ctx.guild.owner.__eq__ = MagicMock(return_value=False)

        # The hierarchy check compares top_role >= ctx.author.top_role
        await cog.ban.callback(cog, mock_ctx, member, raison="Test")

        # Should send error message about not being able to ban
        mock_ctx.send.assert_called()

    @pytest.mark.asyncio
    @patch('cogs.moderation.db')
    async def test_kick_command_success(self, mock_db, mock_bot, mock_ctx):
        """Test successful kick command."""
        from cogs.moderation import Moderation

        mock_db.get_guild_config = AsyncMock(return_value={'log_channel_id': None})

        cog = Moderation(mock_bot)

        member = MagicMock(spec=discord.Member)
        member.top_role = MagicMock()
        member.top_role.position = 5
        member.top_role.__ge__ = MagicMock(return_value=False)
        member.mention = "<@12345>"
        member.kick = AsyncMock()

        await cog.kick.callback(cog, mock_ctx, member, raison="Test kick")

        member.kick.assert_called_once()

    @pytest.mark.asyncio
    @patch('cogs.moderation.db')
    async def test_mute_command_success(self, mock_db, mock_bot, mock_ctx):
        """Test successful mute command."""
        from cogs.moderation import Moderation

        mock_db.get_guild_config = AsyncMock(return_value={'log_channel_id': None})

        cog = Moderation(mock_bot)

        member = MagicMock(spec=discord.Member)
        member.top_role = MagicMock()
        member.top_role.position = 5
        member.top_role.__ge__ = MagicMock(return_value=False)
        member.mention = "<@12345>"
        member.timeout = AsyncMock()

        await cog.mute.callback(cog, mock_ctx, member, duree=60, raison="Test mute")

        member.timeout.assert_called_once()

    @pytest.mark.asyncio
    @patch('cogs.moderation.db')
    async def test_mute_command_exceeds_max_duration(self, mock_db, mock_bot, mock_ctx):
        """Test mute fails when duration exceeds 28 days."""
        from cogs.moderation import Moderation

        cog = Moderation(mock_bot)

        member = MagicMock(spec=discord.Member)
        member.top_role = MagicMock()
        member.top_role.position = 5
        member.top_role.__ge__ = MagicMock(return_value=False)

        # 50000 minutes > 40320 (28 days max)
        await cog.mute.callback(cog, mock_ctx, member, duree=50000, raison="Test")

        mock_ctx.send.assert_called()

    @pytest.mark.asyncio
    @patch('cogs.moderation.db')
    async def test_unmute_command_success(self, mock_db, mock_bot, mock_ctx):
        """Test successful unmute command."""
        from cogs.moderation import Moderation

        cog = Moderation(mock_bot)

        member = MagicMock(spec=discord.Member)
        member.mention = "<@12345>"
        member.timeout = AsyncMock()

        await cog.unmute.callback(cog, mock_ctx, member)

        # timeout(None) removes the timeout
        member.timeout.assert_called_once_with(None)

    @pytest.mark.asyncio
    @patch('cogs.moderation.db')
    async def test_warn_command_success(self, mock_db, mock_bot, mock_ctx):
        """Test successful warn command."""
        from cogs.moderation import Moderation

        mock_db.add_warning = AsyncMock(return_value=1)  # Returns warning count
        mock_db.get_guild_config = AsyncMock(return_value={'log_channel_id': None})

        cog = Moderation(mock_bot)

        member = MagicMock(spec=discord.Member)
        member.bot = False
        member.mention = "<@12345>"
        member.id = 12345

        await cog.warn.callback(cog, mock_ctx, member, raison="Test warning")

        mock_db.add_warning.assert_called_once()
        mock_ctx.send.assert_called()

    @pytest.mark.asyncio
    @patch('cogs.moderation.db')
    async def test_warn_command_cannot_warn_bot(self, mock_db, mock_bot, mock_ctx):
        """Test warn fails for bot users."""
        from cogs.moderation import Moderation

        cog = Moderation(mock_bot)

        member = MagicMock(spec=discord.Member)
        member.bot = True

        await cog.warn.callback(cog, mock_ctx, member, raison="Test")

        mock_ctx.send.assert_called()
        mock_db.add_warning.assert_not_called()

    @pytest.mark.asyncio
    @patch('cogs.moderation.db')
    async def test_warn_auto_mute_at_threshold(self, mock_db, mock_bot, mock_ctx):
        """Test automatic mute when warning threshold reached."""
        from cogs.moderation import Moderation

        # Return warning count >= threshold (3)
        mock_db.add_warning = AsyncMock(return_value=3)
        mock_db.get_guild_config = AsyncMock(return_value={'log_channel_id': None})

        cog = Moderation(mock_bot)

        member = MagicMock(spec=discord.Member)
        member.bot = False
        member.mention = "<@12345>"
        member.id = 12345
        member.timeout = AsyncMock()

        await cog.warn.callback(cog, mock_ctx, member, raison="Test warning")

        # Should trigger auto-mute
        member.timeout.assert_called()

    @pytest.mark.asyncio
    @patch('cogs.moderation.db')
    async def test_warnings_command_with_warnings(self, mock_db, mock_bot, mock_ctx):
        """Test warnings command displays warning history."""
        from cogs.moderation import Moderation

        mock_db.get_warnings = AsyncMock(return_value=[
            {
                'moderator_id': 999,
                'reason': 'Test warning',
                'created_at': '2024-01-01T12:00:00'
            }
        ])

        cog = Moderation(mock_bot)

        member = MagicMock(spec=discord.Member)
        member.id = 12345
        member.display_name = "TestUser"

        mock_ctx.guild.get_member = MagicMock(return_value=None)

        await cog.warnings.callback(cog, mock_ctx, member)

        mock_db.get_warnings.assert_called_once()
        mock_ctx.send.assert_called()

    @pytest.mark.asyncio
    @patch('cogs.moderation.db')
    async def test_warnings_command_no_member(self, mock_db, mock_bot, mock_ctx):
        """Test warnings command defaults to author when no member specified."""
        from cogs.moderation import Moderation

        mock_db.get_warnings = AsyncMock(return_value=[])

        cog = Moderation(mock_bot)
        mock_ctx.author.id = 99999
        mock_ctx.author.display_name = "Author"

        await cog.warnings.callback(cog, mock_ctx, membre=None)

        mock_db.get_warnings.assert_called_with(99999, mock_ctx.guild.id)

    @pytest.mark.asyncio
    @patch('cogs.moderation.db')
    async def test_clearwarnings_command(self, mock_db, mock_bot, mock_ctx):
        """Test clearwarnings command clears all warnings."""
        from cogs.moderation import Moderation

        mock_db.clear_warnings = AsyncMock()

        cog = Moderation(mock_bot)

        member = MagicMock(spec=discord.Member)
        member.id = 12345
        member.mention = "<@12345>"

        await cog.clearwarnings.callback(cog, mock_ctx, member)

        mock_db.clear_warnings.assert_called_once()
        mock_ctx.send.assert_called()

    @pytest.mark.asyncio
    async def test_purge_command_success(self, mock_bot, mock_ctx):
        """Test purge command deletes messages."""
        from cogs.moderation import Moderation

        cog = Moderation(mock_bot)

        await cog.purge.callback(cog, mock_ctx, nombre=10)

        mock_ctx.channel.purge.assert_called_once_with(limit=11)  # +1 for command message

    @pytest.mark.asyncio
    async def test_purge_command_invalid_count(self, mock_bot, mock_ctx):
        """Test purge command with invalid count."""
        from cogs.moderation import Moderation

        cog = Moderation(mock_bot)

        # Test below minimum
        await cog.purge.callback(cog, mock_ctx, nombre=0)
        mock_ctx.send.assert_called()

        # Test above maximum
        mock_ctx.send.reset_mock()
        await cog.purge.callback(cog, mock_ctx, nombre=101)
        mock_ctx.send.assert_called()

    @pytest.mark.asyncio
    async def test_slowmode_command_enable(self, mock_bot, mock_ctx):
        """Test slowmode command enables slowmode."""
        from cogs.moderation import Moderation

        cog = Moderation(mock_bot)

        await cog.slowmode.callback(cog, mock_ctx, secondes=30)

        mock_ctx.channel.edit.assert_called_once_with(slowmode_delay=30)

    @pytest.mark.asyncio
    async def test_slowmode_command_disable(self, mock_bot, mock_ctx):
        """Test slowmode command with 0 disables slowmode."""
        from cogs.moderation import Moderation

        cog = Moderation(mock_bot)

        await cog.slowmode.callback(cog, mock_ctx, secondes=0)

        mock_ctx.channel.edit.assert_called_once_with(slowmode_delay=0)

    @pytest.mark.asyncio
    async def test_slowmode_command_invalid(self, mock_bot, mock_ctx):
        """Test slowmode command with invalid value."""
        from cogs.moderation import Moderation

        cog = Moderation(mock_bot)

        await cog.slowmode.callback(cog, mock_ctx, secondes=-1)
        mock_ctx.send.assert_called()

        mock_ctx.send.reset_mock()
        await cog.slowmode.callback(cog, mock_ctx, secondes=22000)
        mock_ctx.send.assert_called()

    @pytest.mark.asyncio
    async def test_lock_command(self, mock_bot, mock_ctx):
        """Test lock command prevents sending messages."""
        from cogs.moderation import Moderation

        cog = Moderation(mock_bot)

        await cog.lock.callback(cog, mock_ctx)

        mock_ctx.channel.set_permissions.assert_called_once_with(
            mock_ctx.guild.default_role,
            send_messages=False
        )

    @pytest.mark.asyncio
    async def test_unlock_command(self, mock_bot, mock_ctx):
        """Test unlock command allows sending messages."""
        from cogs.moderation import Moderation

        cog = Moderation(mock_bot)

        await cog.unlock.callback(cog, mock_ctx)

        mock_ctx.channel.set_permissions.assert_called_once_with(
            mock_ctx.guild.default_role,
            send_messages=True
        )


# =============================================================================
# Reaction Roles Cog Tests
# =============================================================================

class TestReactionRolesCommands:
    """Tests for ReactionRoles cog command methods."""

    @pytest.fixture
    def mock_bot(self):
        bot = MagicMock(spec=commands.Bot)
        bot.user = MagicMock()
        bot.user.id = 999999999
        bot.get_channel = MagicMock()
        return bot

    @pytest.fixture
    def mock_ctx(self, mock_bot):
        ctx = MagicMock(spec=commands.Context)
        ctx.bot = mock_bot
        ctx.guild = MagicMock(spec=discord.Guild)
        ctx.guild.id = 123456789
        ctx.author = MagicMock(spec=discord.Member)
        ctx.channel = MagicMock(spec=discord.TextChannel)
        ctx.send = AsyncMock()
        return ctx

    @pytest.mark.asyncio
    @patch('discord.ui.view.asyncio.get_running_loop', return_value=MagicMock())
    @patch('cogs.reaction_roles.db')
    async def test_on_raw_reaction_add_grants_role(self, mock_db, mock_loop, mock_bot):
        """Test reaction add grants the configured role."""
        from cogs.reaction_roles import ReactionRoles

        mock_db.get_reaction_role = AsyncMock(return_value={
            'role_id': 111222333
        })

        # Create cog
        cog = ReactionRoles(mock_bot)

        # Create mock payload
        payload = MagicMock()
        payload.guild_id = 123456789
        payload.message_id = 987654321
        payload.user_id = 111111111
        payload.emoji = MagicMock()
        payload.emoji.__str__ = MagicMock(return_value='👍')

        # Create mock member
        member = MagicMock(spec=discord.Member)
        member.bot = False
        member.add_roles = AsyncMock()
        payload.member = member

        # Create mock guild and role
        guild = MagicMock(spec=discord.Guild)
        role = MagicMock(spec=discord.Role)
        guild.get_role = MagicMock(return_value=role)
        mock_bot.get_guild = MagicMock(return_value=guild)

        await cog.on_raw_reaction_add(payload)

        mock_db.get_reaction_role.assert_called_once()
        member.add_roles.assert_called_once_with(role, reason='Reaction Role')

    @pytest.mark.asyncio
    @patch('discord.ui.view.asyncio.get_running_loop', return_value=MagicMock())
    @patch('cogs.reaction_roles.db')
    async def test_on_raw_reaction_add_ignores_bots(self, mock_db, mock_loop, mock_bot):
        """Test reaction add ignores bot reactions."""
        from cogs.reaction_roles import ReactionRoles

        cog = ReactionRoles(mock_bot)

        payload = MagicMock()
        payload.member = MagicMock()
        payload.member.bot = True

        await cog.on_raw_reaction_add(payload)

        mock_db.get_reaction_role.assert_not_called()

    @pytest.mark.asyncio
    @patch('discord.ui.view.asyncio.get_running_loop', return_value=MagicMock())
    @patch('cogs.reaction_roles.db')
    async def test_on_raw_reaction_remove_removes_role(self, mock_db, mock_loop, mock_bot):
        """Test reaction remove removes the configured role."""
        from cogs.reaction_roles import ReactionRoles

        mock_db.get_reaction_role = AsyncMock(return_value={
            'role_id': 111222333
        })

        cog = ReactionRoles(mock_bot)

        # Create mock payload (no member on remove events)
        payload = MagicMock()
        payload.guild_id = 123456789
        payload.message_id = 987654321
        payload.user_id = 111111111
        payload.emoji = MagicMock()
        payload.emoji.__str__ = MagicMock(return_value='👍')

        # Create mock guild, member, and role
        member = MagicMock(spec=discord.Member)
        member.bot = False
        member.remove_roles = AsyncMock()

        guild = MagicMock(spec=discord.Guild)
        guild.get_member = MagicMock(return_value=member)
        role = MagicMock(spec=discord.Role)
        guild.get_role = MagicMock(return_value=role)
        mock_bot.get_guild = MagicMock(return_value=guild)

        await cog.on_raw_reaction_remove(payload)

        member.remove_roles.assert_called_once_with(role, reason='Reaction Role')

    @pytest.mark.asyncio
    @patch('discord.ui.view.asyncio.get_running_loop', return_value=MagicMock())
    @patch('cogs.reaction_roles.db')
    async def test_rr_add_command(self, mock_db, mock_loop, mock_bot, mock_ctx):
        """Test adding a reaction role."""
        from cogs.reaction_roles import ReactionRoles

        mock_db.add_reaction_role = AsyncMock()

        cog = ReactionRoles(mock_bot)

        # Mock text_channels to find the message
        message = MagicMock()
        message.add_reaction = AsyncMock()
        message.channel = MagicMock()
        message.channel.id = 555666777

        channel = MagicMock(spec=discord.TextChannel)
        channel.fetch_message = AsyncMock(return_value=message)
        mock_ctx.guild.text_channels = [channel]

        # The bot's top role must be above the role being assigned
        mock_bot.user = MagicMock()
        mock_bot_member = MagicMock()
        mock_bot_member.top_role = MagicMock()
        mock_bot_member.top_role.position = 100
        mock_ctx.guild.me = mock_bot_member

        role = MagicMock(spec=discord.Role)
        role.id = 111222333
        role.position = 50
        role.__ge__ = MagicMock(return_value=False)  # Role is below bot's top role

        await cog.rr_add.callback(cog, mock_ctx, message_id="987654321", emoji='👍', role=role)

        mock_db.add_reaction_role.assert_called_once()
        message.add_reaction.assert_called_once_with('👍')

    @pytest.mark.asyncio
    @patch('discord.ui.view.asyncio.get_running_loop', return_value=MagicMock())
    @patch('cogs.reaction_roles.db')
    async def test_rr_remove_command(self, mock_db, mock_loop, mock_bot, mock_ctx):
        """Test removing a reaction role."""
        from cogs.reaction_roles import ReactionRoles

        mock_db.remove_reaction_role = AsyncMock()

        cog = ReactionRoles(mock_bot)

        await cog.rr_remove.callback(cog, mock_ctx, message_id=987654321, emoji='👍')

        mock_db.remove_reaction_role.assert_called_once()
        mock_ctx.send.assert_called()

    @pytest.mark.asyncio
    @patch('discord.ui.view.asyncio.get_running_loop', return_value=MagicMock())
    @patch('cogs.reaction_roles.db')
    async def test_rr_list_command(self, mock_db, mock_loop, mock_bot, mock_ctx):
        """Test listing reaction roles."""
        from cogs.reaction_roles import ReactionRoles

        mock_db.get_all_reaction_roles = AsyncMock(return_value=[
            {'message_id': 123, 'emoji': '👍', 'role_id': 456, 'channel_id': 789}
        ])

        cog = ReactionRoles(mock_bot)

        # Mock role lookup
        role = MagicMock()
        role.mention = "@Role"
        mock_ctx.guild.get_role = MagicMock(return_value=role)

        await cog.rr_list.callback(cog, mock_ctx)

        mock_db.get_all_reaction_roles.assert_called_once()
        mock_ctx.send.assert_called()

    @pytest.mark.asyncio
    @patch('discord.ui.view.asyncio.get_running_loop', return_value=MagicMock())
    @patch('cogs.reaction_roles.db')
    async def test_rr_list_empty(self, mock_db, mock_loop, mock_bot, mock_ctx):
        """Test listing reaction roles when none exist."""
        from cogs.reaction_roles import ReactionRoles

        mock_db.get_all_reaction_roles = AsyncMock(return_value=[])

        cog = ReactionRoles(mock_bot)

        await cog.rr_list.callback(cog, mock_ctx)

        mock_ctx.send.assert_called()

    @pytest.mark.asyncio
    @patch('discord.ui.view.asyncio.get_running_loop', return_value=MagicMock())
    @patch('cogs.reaction_roles.db')
    async def test_rr_create_command(self, mock_db, mock_loop, mock_bot, mock_ctx):
        """Test creating a reaction role message."""
        from cogs.reaction_roles import ReactionRoles

        cog = ReactionRoles(mock_bot)

        await cog.rr_create.callback(cog, mock_ctx, titre="Role Menu", description="Pick a role!")

        mock_ctx.send.assert_called()


# =============================================================================
# Tickets Cog Tests
# =============================================================================

class TestTicketsCommands:
    """Tests for Tickets cog command methods."""

    @pytest.fixture
    def mock_bot(self):
        bot = MagicMock(spec=commands.Bot)
        bot.user = MagicMock()
        bot.user.id = 999999999
        return bot

    @pytest.fixture
    def mock_ctx(self, mock_bot):
        ctx = MagicMock(spec=commands.Context)
        ctx.bot = mock_bot
        ctx.guild = MagicMock(spec=discord.Guild)
        ctx.guild.id = 123456789
        ctx.author = MagicMock(spec=discord.Member)
        ctx.author.id = 111111111
        ctx.channel = MagicMock(spec=discord.TextChannel)
        ctx.channel.id = 555666777
        ctx.channel.name = "ticket-test"
        ctx.send = AsyncMock()
        return ctx

    @pytest.mark.asyncio
    @patch('discord.ui.view.asyncio.get_running_loop', return_value=MagicMock())
    @patch('cogs.tickets.db')
    async def test_ticket_setup_command(self, mock_db, mock_loop, mock_bot, mock_ctx):
        """Test setting up ticket panel."""
        from cogs.tickets import Tickets

        cog = Tickets(mock_bot)

        channel = MagicMock(spec=discord.TextChannel)
        channel.send = AsyncMock()

        await cog.ticket_setup.callback(cog, mock_ctx, channel=channel)

        channel.send.assert_called()
        mock_ctx.send.assert_called()

    @pytest.mark.asyncio
    @patch('discord.ui.view.asyncio.get_running_loop', return_value=MagicMock())
    @patch('cogs.tickets.db')
    async def test_ticket_close_command_not_in_ticket(self, mock_db, mock_loop, mock_bot, mock_ctx):
        """Test closing ticket when not in a ticket channel."""
        from cogs.tickets import Tickets

        mock_db.get_ticket_by_channel = AsyncMock(return_value=None)

        cog = Tickets(mock_bot)

        await cog.ticket_close.callback(cog, mock_ctx)

        mock_ctx.send.assert_called()

    @pytest.mark.asyncio
    @patch('discord.ui.view.asyncio.get_running_loop', return_value=MagicMock())
    @patch('cogs.tickets.db')
    async def test_ticket_add_command_not_in_ticket(self, mock_db, mock_loop, mock_bot, mock_ctx):
        """Test adding member when not in a ticket channel."""
        from cogs.tickets import Tickets

        mock_db.get_ticket_by_channel = AsyncMock(return_value=None)

        cog = Tickets(mock_bot)

        member = MagicMock(spec=discord.Member)

        await cog.ticket_add.callback(cog, mock_ctx, membre=member)

        mock_ctx.send.assert_called()

    @pytest.mark.asyncio
    @patch('discord.ui.view.asyncio.get_running_loop', return_value=MagicMock())
    @patch('cogs.tickets.db')
    async def test_ticket_add_command_in_ticket(self, mock_db, mock_loop, mock_bot, mock_ctx):
        """Test adding member to ticket channel."""
        from cogs.tickets import Tickets

        mock_db.get_ticket_by_channel = AsyncMock(return_value={
            'user_id': 111111111,
            'status': 'open'
        })

        cog = Tickets(mock_bot)

        member = MagicMock(spec=discord.Member)
        member.mention = "<@222222222>"
        mock_ctx.channel.set_permissions = AsyncMock()

        await cog.ticket_add.callback(cog, mock_ctx, membre=member)

        mock_ctx.channel.set_permissions.assert_called_once()

    @pytest.mark.asyncio
    @patch('discord.ui.view.asyncio.get_running_loop', return_value=MagicMock())
    @patch('cogs.tickets.db')
    async def test_ticket_remove_command_cannot_remove_creator(self, mock_db, mock_loop, mock_bot, mock_ctx):
        """Test cannot remove ticket creator."""
        from cogs.tickets import Tickets

        mock_db.get_ticket_by_channel = AsyncMock(return_value={
            'user_id': 111111111,  # Same as member to remove
            'status': 'open'
        })

        cog = Tickets(mock_bot)

        member = MagicMock(spec=discord.Member)
        member.id = 111111111  # Same as ticket creator

        await cog.ticket_remove.callback(cog, mock_ctx, membre=member)

        mock_ctx.send.assert_called()

    @pytest.mark.asyncio
    @patch('discord.ui.view.asyncio.get_running_loop', return_value=MagicMock())
    @patch('cogs.tickets.db')
    async def test_ticket_remove_command_success(self, mock_db, mock_loop, mock_bot, mock_ctx):
        """Test removing member from ticket."""
        from cogs.tickets import Tickets

        mock_db.get_ticket_by_channel = AsyncMock(return_value={
            'user_id': 111111111,
            'status': 'open'
        })

        cog = Tickets(mock_bot)

        member = MagicMock(spec=discord.Member)
        member.id = 222222222  # Different from creator
        member.mention = "<@222222222>"
        mock_ctx.channel.set_permissions = AsyncMock()

        await cog.ticket_remove.callback(cog, mock_ctx, membre=member)

        mock_ctx.channel.set_permissions.assert_called_once()

    @pytest.mark.asyncio
    @patch('discord.ui.view.asyncio.get_running_loop', return_value=MagicMock())
    @patch('cogs.tickets.db')
    async def test_ticket_rename_command(self, mock_db, mock_loop, mock_bot, mock_ctx):
        """Test renaming ticket channel."""
        from cogs.tickets import Tickets

        mock_db.get_ticket_by_channel = AsyncMock(return_value={
            'user_id': 111111111,
            'status': 'open'
        })

        cog = Tickets(mock_bot)

        mock_ctx.channel.edit = AsyncMock()

        await cog.ticket_rename.callback(cog, mock_ctx, nom="new-name")

        mock_ctx.channel.edit.assert_called_once_with(name="ticket-new-name")


# =============================================================================
# Profanity Filter Cog Tests
# =============================================================================

class TestProfanityFilterCommands:
    """Tests for ProfanityFilter cog command methods."""

    @pytest.fixture
    def mock_bot(self):
        bot = MagicMock(spec=commands.Bot)
        bot.user = MagicMock()
        bot.user.id = 999999999
        return bot

    @pytest.fixture
    def mock_ctx(self, mock_bot):
        ctx = MagicMock(spec=commands.Context)
        ctx.bot = mock_bot
        ctx.guild = MagicMock(spec=discord.Guild)
        ctx.guild.id = 123456789
        ctx.author = MagicMock(spec=discord.Member)
        ctx.channel = MagicMock(spec=discord.TextChannel)
        ctx.send = AsyncMock()
        return ctx

    @pytest.mark.asyncio
    @patch('cogs.profanity_filter.db')
    async def test_badword_add_command(self, mock_db, mock_bot, mock_ctx):
        """Test adding a banned word."""
        from cogs.profanity_filter import ProfanityFilter

        mock_db.add_banned_word = AsyncMock()

        cog = ProfanityFilter(mock_bot)

        await cog.badword_add.callback(cog, mock_ctx, mot="badword", langue="all", severite=3)

        mock_db.add_banned_word.assert_called_once()
        mock_ctx.send.assert_called()

    @pytest.mark.asyncio
    @patch('cogs.profanity_filter.db')
    async def test_badword_remove_command(self, mock_db, mock_bot, mock_ctx):
        """Test removing a banned word."""
        from cogs.profanity_filter import ProfanityFilter

        mock_db.remove_banned_word = AsyncMock()

        cog = ProfanityFilter(mock_bot)

        await cog.badword_remove.callback(cog, mock_ctx, mot="badword")

        mock_db.remove_banned_word.assert_called_once()
        mock_ctx.send.assert_called()

    @pytest.mark.asyncio
    @patch('cogs.profanity_filter.db')
    async def test_badword_list_command(self, mock_db, mock_bot, mock_ctx):
        """Test listing banned words."""
        from cogs.profanity_filter import ProfanityFilter

        mock_db.get_banned_words = AsyncMock(return_value=[
            {'word': 'test', 'language': 'all', 'severity': 2}
        ])

        cog = ProfanityFilter(mock_bot)

        await cog.badword_list.callback(cog, mock_ctx, langue=None)

        mock_db.get_banned_words.assert_called_once()
        mock_ctx.send.assert_called()

    @pytest.mark.asyncio
    @patch('cogs.profanity_filter.db')
    async def test_badword_import_command(self, mock_db, mock_bot, mock_ctx):
        """Test bulk importing banned words."""
        from cogs.profanity_filter import ProfanityFilter

        mock_db.add_banned_word = AsyncMock()

        cog = ProfanityFilter(mock_bot)

        await cog.badword_import.callback(cog, mock_ctx, mots="word1, word2, word3")

        assert mock_db.add_banned_word.call_count == 3
        mock_ctx.send.assert_called()

    @pytest.mark.asyncio
    @patch('cogs.profanity_filter.db')
    async def test_infractions_command(self, mock_db, mock_bot, mock_ctx):
        """Test viewing user infractions."""
        from cogs.profanity_filter import ProfanityFilter

        mock_db.get_user_profanity_stats = AsyncMock(return_value={
            'total_infractions': 5,
            'warnings_count': 3,
            'mutes_count': 1,
            'kicks_count': 0,
            'is_banned': 0,
            'last_infraction': '2024-01-01T12:00:00'
        })
        mock_db.get_user_profanity_history = AsyncMock(return_value=[
            {'word_used': 'badword', 'created_at': '2024-01-01T12:00:00', 'action_taken': 'warn'}
        ])

        cog = ProfanityFilter(mock_bot)

        member = MagicMock(spec=discord.Member)
        member.id = 12345
        member.display_name = "TestUser"
        member.display_avatar = MagicMock()
        member.display_avatar.url = "https://example.com/avatar.png"

        await cog.infractions.callback(cog, mock_ctx, membre=member)

        mock_ctx.send.assert_called()

    @pytest.mark.asyncio
    @patch('cogs.profanity_filter.db')
    async def test_infractions_leaderboard_command(self, mock_db, mock_bot, mock_ctx):
        """Test infraction leaderboard."""
        from cogs.profanity_filter import ProfanityFilter

        mock_db.get_profanity_leaderboard = AsyncMock(return_value=[
            {'user_id': 123, 'total_infractions': 10},
            {'user_id': 456, 'total_infractions': 5}
        ])

        cog = ProfanityFilter(mock_bot)

        mock_ctx.guild.get_member = MagicMock(return_value=None)

        await cog.infractions_leaderboard.callback(cog, mock_ctx)

        mock_ctx.send.assert_called()

    @pytest.mark.asyncio
    @patch('cogs.profanity_filter.db')
    async def test_reset_infractions_command(self, mock_db, mock_bot, mock_ctx):
        """Test resetting user infractions."""
        from cogs.profanity_filter import ProfanityFilter

        mock_db.reset_user_profanity_stats = AsyncMock()

        cog = ProfanityFilter(mock_bot)

        member = MagicMock(spec=discord.Member)
        member.id = 12345
        member.mention = "<@12345>"

        await cog.reset_infractions.callback(cog, mock_ctx, membre=member)

        mock_db.reset_user_profanity_stats.assert_called_once()
        mock_ctx.send.assert_called()

    @pytest.mark.asyncio
    @patch('cogs.profanity_filter.db')
    async def test_pconfig_enable_command(self, mock_db, mock_bot, mock_ctx):
        """Test enabling/disabling profanity filter."""
        from cogs.profanity_filter import ProfanityFilter

        mock_db.update_profanity_config = AsyncMock()

        cog = ProfanityFilter(mock_bot)

        await cog.pconfig_enable.callback(cog, mock_ctx, etat="on")

        mock_db.update_profanity_config.assert_called()
        mock_ctx.send.assert_called()

    @pytest.mark.asyncio
    @patch('cogs.profanity_filter.db')
    async def test_pconfig_threshold_command(self, mock_db, mock_bot, mock_ctx):
        """Test setting punishment thresholds."""
        from cogs.profanity_filter import ProfanityFilter

        mock_db.update_profanity_config = AsyncMock()

        cog = ProfanityFilter(mock_bot)

        await cog.pconfig_threshold.callback(cog, mock_ctx, type="warn", nombre=5)

        mock_db.update_profanity_config.assert_called()
        mock_ctx.send.assert_called()

    @pytest.mark.asyncio
    @patch('cogs.profanity_filter.db')
    async def test_pconfig_muteduration_command(self, mock_db, mock_bot, mock_ctx):
        """Test setting mute duration."""
        from cogs.profanity_filter import ProfanityFilter

        mock_db.update_profanity_config = AsyncMock()

        cog = ProfanityFilter(mock_bot)

        await cog.pconfig_muteduration.callback(cog, mock_ctx, minutes=30)

        mock_db.update_profanity_config.assert_called()
        mock_ctx.send.assert_called()

    @pytest.mark.asyncio
    @patch('cogs.profanity_filter.db')
    async def test_pconfig_dm_command(self, mock_db, mock_bot, mock_ctx):
        """Test enabling/disabling DM notifications."""
        from cogs.profanity_filter import ProfanityFilter

        mock_db.update_profanity_config = AsyncMock()

        cog = ProfanityFilter(mock_bot)

        await cog.pconfig_dm.callback(cog, mock_ctx, etat="on")

        mock_db.update_profanity_config.assert_called()
        mock_ctx.send.assert_called()


# =============================================================================
# Setup Function Tests
# =============================================================================

class TestCogSetupFunctions:
    """Tests for cog setup functions."""

    @pytest.mark.asyncio
    async def test_moderation_setup(self):
        """Test moderation cog setup function."""
        from cogs.moderation import setup

        bot = MagicMock(spec=commands.Bot)
        bot.add_cog = AsyncMock()

        await setup(bot)

        bot.add_cog.assert_called_once()

    @pytest.mark.asyncio
    @patch('discord.ui.view.asyncio.get_running_loop', return_value=MagicMock())
    async def test_reaction_roles_setup(self, mock_loop):
        """Test reaction roles cog setup function."""
        from cogs.reaction_roles import setup

        bot = MagicMock(spec=commands.Bot)
        bot.add_cog = AsyncMock()

        await setup(bot)

        bot.add_cog.assert_called_once()

    @pytest.mark.asyncio
    @patch('discord.ui.view.asyncio.get_running_loop', return_value=MagicMock())
    async def test_tickets_setup(self, mock_loop):
        """Test tickets cog setup function."""
        from cogs.tickets import setup

        bot = MagicMock(spec=commands.Bot)
        bot.add_cog = AsyncMock()

        await setup(bot)

        bot.add_cog.assert_called_once()

    @pytest.mark.asyncio
    async def test_profanity_filter_setup(self):
        """Test profanity filter cog setup function."""
        from cogs.profanity_filter import setup

        bot = MagicMock(spec=commands.Bot)
        bot.add_cog = AsyncMock()

        await setup(bot)

        bot.add_cog.assert_called_once()
