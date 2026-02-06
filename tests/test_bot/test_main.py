"""
Tests for the main bot module (main.py).

Tests cover the DiscordBot class lifecycle methods, prefix resolution,
error handling, and guild join/leave events using mocked Discord objects.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
import discord
from discord.ext import commands


class TestDiscordBotInit:
    """Test DiscordBot initialization."""

    @patch('main.db')
    def test_bot_creation(self, mock_db):
        """Test that DiscordBot can be instantiated."""
        from main import DiscordBot
        bot = DiscordBot()
        assert bot is not None
        assert bot.start_time is not None
        assert bot.help_command is None  # Custom help disabled
        assert bot.case_insensitive is True

    @patch('main.db')
    def test_bot_has_start_time(self, mock_db):
        """Test that bot records a start time on creation."""
        from datetime import datetime
        from main import DiscordBot
        before = datetime.now()
        bot = DiscordBot()
        after = datetime.now()
        assert before <= bot.start_time <= after

    @patch('main.db')
    def test_bot_intents_configured(self, mock_db):
        """Test that required intents are enabled."""
        from main import DiscordBot
        bot = DiscordBot()
        assert bot.intents.messages is True
        assert bot.intents.message_content is True
        assert bot.intents.members is True
        assert bot.intents.reactions is True
        assert bot.intents.guilds is True


class TestGetPrefix:
    """Test dynamic prefix resolution."""

    @patch('main.db')
    @pytest.mark.asyncio
    async def test_dm_returns_default_prefix(self, mock_db):
        """Test that DMs use the global default prefix."""
        from main import DiscordBot, PREFIX
        bot = DiscordBot()
        message = MagicMock(spec=discord.Message)
        message.guild = None  # DM has no guild
        prefix = await bot.get_prefix(bot, message)
        assert prefix == PREFIX

    @patch('main.db')
    @pytest.mark.asyncio
    async def test_guild_returns_custom_prefix(self, mock_db):
        """Test that guild messages use the guild's custom prefix."""
        from main import DiscordBot
        mock_db.get_guild_config = AsyncMock(return_value={'prefix': '?'})
        bot = DiscordBot()
        message = MagicMock(spec=discord.Message)
        message.guild = MagicMock(spec=discord.Guild)
        message.guild.id = 123456789
        prefix = await bot.get_prefix(bot, message)
        assert prefix == '?'
        mock_db.get_guild_config.assert_called_once_with(123456789)

    @patch('main.db')
    @pytest.mark.asyncio
    async def test_guild_with_no_custom_prefix_returns_default(self, mock_db):
        """Test fallback to default prefix when guild has no custom one."""
        from main import DiscordBot, PREFIX
        mock_db.get_guild_config = AsyncMock(return_value={})
        bot = DiscordBot()
        message = MagicMock(spec=discord.Message)
        message.guild = MagicMock(spec=discord.Guild)
        message.guild.id = 123456789
        prefix = await bot.get_prefix(bot, message)
        assert prefix == PREFIX


class TestSetupHook:
    """Test the setup_hook method."""

    @patch('main.db')
    @pytest.mark.asyncio
    async def test_setup_hook_initialises_db(self, mock_db):
        """Test that setup_hook calls db.init()."""
        from main import DiscordBot
        mock_db.init = AsyncMock()
        bot = DiscordBot()
        bot.load_extension = AsyncMock()
        await bot.setup_hook()
        mock_db.init.assert_called_once()

    @patch('main.db')
    @pytest.mark.asyncio
    async def test_setup_hook_loads_cogs(self, mock_db):
        """Test that setup_hook attempts to load all registered cogs."""
        from main import DiscordBot
        mock_db.init = AsyncMock()
        bot = DiscordBot()
        bot.load_extension = AsyncMock()
        await bot.setup_hook()
        # Should attempt to load 11 cogs
        assert bot.load_extension.call_count == 11
        # Verify some specific cogs were loaded
        loaded_cogs = [call.args[0] for call in bot.load_extension.call_args_list]
        assert 'cogs.leveling' in loaded_cogs
        assert 'cogs.moderation' in loaded_cogs
        assert 'cogs.ai' in loaded_cogs

    @patch('main.db')
    @pytest.mark.asyncio
    async def test_setup_hook_handles_cog_load_failure(self, mock_db):
        """Test that a failing cog doesn't prevent others from loading."""
        from main import DiscordBot
        mock_db.init = AsyncMock()
        bot = DiscordBot()

        call_count = 0
        async def load_ext_side_effect(name):
            nonlocal call_count
            call_count += 1
            if name == 'cogs.ai':
                raise ImportError("Test error")

        bot.load_extension = AsyncMock(side_effect=load_ext_side_effect)
        # Should NOT raise even though cogs.ai fails
        await bot.setup_hook()
        # All 11 cogs should be attempted
        assert call_count == 11


class TestOnReady:
    """Test the on_ready event handler."""

    @patch('main.db')
    @pytest.mark.asyncio
    async def test_on_ready_sets_presence(self, mock_db):
        """Test that on_ready sets the bot's presence."""
        from main import DiscordBot
        bot = DiscordBot()
        mock_user = MagicMock()
        mock_user.id = 999999999
        mock_user.__str__ = MagicMock(return_value='TestBot#1234')
        type(bot).user = PropertyMock(return_value=mock_user)
        type(bot).guilds = PropertyMock(return_value=[MagicMock(), MagicMock()])
        type(bot).latency = PropertyMock(return_value=0.05)
        bot.change_presence = AsyncMock()
        mock_tree = MagicMock()
        mock_tree.sync = AsyncMock(return_value=[])
        type(bot).tree = PropertyMock(return_value=mock_tree)
        await bot.on_ready()
        bot.change_presence.assert_called_once()

    @patch('main.db')
    @pytest.mark.asyncio
    async def test_on_ready_syncs_commands(self, mock_db):
        """Test that on_ready syncs slash commands."""
        from main import DiscordBot
        bot = DiscordBot()
        mock_user = MagicMock()
        mock_user.id = 999
        mock_user.__str__ = MagicMock(return_value='Bot')
        type(bot).user = PropertyMock(return_value=mock_user)
        type(bot).guilds = PropertyMock(return_value=[])
        type(bot).latency = PropertyMock(return_value=0.05)
        bot.change_presence = AsyncMock()
        mock_tree = MagicMock()
        mock_tree.sync = AsyncMock(return_value=['cmd1', 'cmd2'])
        type(bot).tree = PropertyMock(return_value=mock_tree)
        await bot.on_ready()
        mock_tree.sync.assert_called_once()

    @patch('main.db')
    @pytest.mark.asyncio
    async def test_on_ready_handles_sync_failure(self, mock_db):
        """Test that on_ready handles slash command sync failure gracefully."""
        from main import DiscordBot
        bot = DiscordBot()
        mock_user = MagicMock()
        mock_user.id = 999
        mock_user.__str__ = MagicMock(return_value='Bot')
        type(bot).user = PropertyMock(return_value=mock_user)
        type(bot).guilds = PropertyMock(return_value=[])
        type(bot).latency = PropertyMock(return_value=0.05)
        bot.change_presence = AsyncMock()
        mock_tree = MagicMock()
        mock_tree.sync = AsyncMock(side_effect=Exception("Sync failed"))
        type(bot).tree = PropertyMock(return_value=mock_tree)
        # Should NOT raise
        await bot.on_ready()


class TestGuildEvents:
    """Test guild join/leave event handlers."""

    @patch('main.db')
    @pytest.mark.asyncio
    async def test_on_guild_join_creates_config(self, mock_db):
        """Test that joining a guild creates a config entry."""
        from main import DiscordBot
        mock_db.create_guild_config = AsyncMock()
        bot = DiscordBot()
        type(bot).guilds = PropertyMock(return_value=[MagicMock()])
        bot.change_presence = AsyncMock()
        guild = MagicMock(spec=discord.Guild)
        guild.id = 123456789
        guild.name = 'Test Server'
        guild.owner = None  # No owner DM
        await bot.on_guild_join(guild)
        mock_db.create_guild_config.assert_called_once_with(123456789)

    @patch('main.db')
    @pytest.mark.asyncio
    async def test_on_guild_join_dms_owner(self, mock_db):
        """Test that joining a guild sends a DM to the owner."""
        from main import DiscordBot
        mock_db.create_guild_config = AsyncMock()
        bot = DiscordBot()
        type(bot).guilds = PropertyMock(return_value=[MagicMock()])
        bot.change_presence = AsyncMock()
        guild = MagicMock(spec=discord.Guild)
        guild.id = 123
        guild.name = 'Test'
        guild.owner = MagicMock()
        guild.owner.send = AsyncMock()
        await bot.on_guild_join(guild)
        guild.owner.send.assert_called_once()

    @patch('main.db')
    @pytest.mark.asyncio
    async def test_on_guild_join_handles_dm_forbidden(self, mock_db):
        """Test graceful handling when owner has DMs disabled."""
        from main import DiscordBot
        mock_db.create_guild_config = AsyncMock()
        bot = DiscordBot()
        type(bot).guilds = PropertyMock(return_value=[MagicMock()])
        bot.change_presence = AsyncMock()
        guild = MagicMock(spec=discord.Guild)
        guild.id = 123
        guild.name = 'Test'
        guild.owner = MagicMock()
        guild.owner.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), 'Forbidden'))
        # Should NOT raise
        await bot.on_guild_join(guild)

    @patch('main.db')
    @pytest.mark.asyncio
    async def test_on_guild_remove_updates_presence(self, mock_db):
        """Test that leaving a guild updates the presence."""
        from main import DiscordBot
        bot = DiscordBot()
        type(bot).guilds = PropertyMock(return_value=[])
        bot.change_presence = AsyncMock()
        guild = MagicMock(spec=discord.Guild)
        guild.name = 'Removed'
        guild.id = 111
        await bot.on_guild_remove(guild)
        bot.change_presence.assert_called_once()


class TestOnCommandError:
    """Test the global command error handler."""

    @patch('main.db')
    @pytest.mark.asyncio
    async def test_command_not_found_is_ignored(self, mock_db):
        """Test that CommandNotFound errors are silently ignored."""
        from main import DiscordBot
        bot = DiscordBot()
        ctx = MagicMock(spec=commands.Context)
        ctx.send = AsyncMock()
        error = commands.CommandNotFound()
        await bot.on_command_error(ctx, error)
        ctx.send.assert_not_called()

    @patch('main.db')
    @pytest.mark.asyncio
    async def test_missing_permissions_sends_embed(self, mock_db):
        """Test that MissingPermissions sends an error embed."""
        from main import DiscordBot
        bot = DiscordBot()
        ctx = MagicMock(spec=commands.Context)
        ctx.send = AsyncMock()
        error = commands.MissingPermissions(['ban_members'])
        await bot.on_command_error(ctx, error)
        ctx.send.assert_called_once()
        call_kwargs = ctx.send.call_args
        assert call_kwargs.kwargs.get('delete_after') == 10

    @patch('main.db')
    @pytest.mark.asyncio
    async def test_bot_missing_permissions_sends_embed(self, mock_db):
        """Test that BotMissingPermissions sends an error embed."""
        from main import DiscordBot
        bot = DiscordBot()
        ctx = MagicMock(spec=commands.Context)
        ctx.send = AsyncMock()
        error = commands.BotMissingPermissions(['manage_messages'])
        await bot.on_command_error(ctx, error)
        ctx.send.assert_called_once()

    @patch('main.db')
    @pytest.mark.asyncio
    async def test_missing_required_argument_shows_usage(self, mock_db):
        """Test that MissingRequiredArgument shows the command usage."""
        from main import DiscordBot
        bot = DiscordBot()
        ctx = MagicMock(spec=commands.Context)
        ctx.send = AsyncMock()
        ctx.prefix = '!'
        ctx.command = MagicMock()
        ctx.command.name = 'ban'
        ctx.command.signature = '<member> [reason]'
        param = MagicMock()
        param.name = 'member'
        error = commands.MissingRequiredArgument(param)
        await bot.on_command_error(ctx, error)
        ctx.send.assert_called_once()

    @patch('main.db')
    @pytest.mark.asyncio
    async def test_bad_argument_sends_embed(self, mock_db):
        """Test that BadArgument sends an error embed."""
        from main import DiscordBot
        bot = DiscordBot()
        ctx = MagicMock(spec=commands.Context)
        ctx.send = AsyncMock()
        error = commands.BadArgument('Invalid member')
        await bot.on_command_error(ctx, error)
        ctx.send.assert_called_once()

    @patch('main.db')
    @pytest.mark.asyncio
    async def test_command_on_cooldown_shows_retry_time(self, mock_db):
        """Test that CommandOnCooldown shows the retry time."""
        from main import DiscordBot
        bot = DiscordBot()
        ctx = MagicMock(spec=commands.Context)
        ctx.send = AsyncMock()
        cooldown = MagicMock()
        cooldown.per = 5.0
        cooldown.rate = 1
        cooldown.type = commands.BucketType.user
        error = commands.CommandOnCooldown(cooldown, 3.5, commands.BucketType.user)
        await bot.on_command_error(ctx, error)
        ctx.send.assert_called_once()
        call_kwargs = ctx.send.call_args
        assert call_kwargs.kwargs.get('delete_after') == 5

    @patch('main.db')
    @pytest.mark.asyncio
    async def test_not_owner_sends_embed(self, mock_db):
        """Test that NotOwner sends an access denied embed."""
        from main import DiscordBot
        bot = DiscordBot()
        ctx = MagicMock(spec=commands.Context)
        ctx.send = AsyncMock()
        error = commands.NotOwner()
        await bot.on_command_error(ctx, error)
        ctx.send.assert_called_once()

    @patch('main.db')
    @pytest.mark.asyncio
    async def test_unhandled_error_sends_generic_message(self, mock_db):
        """Test that unhandled errors send a generic error message."""
        from main import DiscordBot
        bot = DiscordBot()
        ctx = MagicMock(spec=commands.Context)
        ctx.send = AsyncMock()
        error = commands.CommandError('Something unexpected')
        await bot.on_command_error(ctx, error)
        ctx.send.assert_called_once()


class TestMainFunction:
    """Test the main() entry point function."""

    @patch('main.db')
    @patch('main.DiscordBot')
    @patch('main.os.makedirs')
    @pytest.mark.asyncio
    async def test_main_creates_data_dir(self, mock_makedirs, mock_bot_cls, mock_db):
        """Test that main() creates the data directory."""
        from main import main
        mock_bot = MagicMock()
        mock_bot.__aenter__ = AsyncMock(return_value=mock_bot)
        mock_bot.__aexit__ = AsyncMock(return_value=False)
        mock_bot.start = AsyncMock()
        mock_bot_cls.return_value = mock_bot
        await main()
        mock_makedirs.assert_called_once_with('data', exist_ok=True)

    @patch('main.db')
    @patch('main.DiscordBot')
    @patch('main.os.makedirs')
    @pytest.mark.asyncio
    async def test_main_starts_bot(self, mock_makedirs, mock_bot_cls, mock_db):
        """Test that main() starts the bot with the token."""
        from main import main, TOKEN
        mock_bot = MagicMock()
        mock_bot.__aenter__ = AsyncMock(return_value=mock_bot)
        mock_bot.__aexit__ = AsyncMock(return_value=False)
        mock_bot.start = AsyncMock()
        mock_bot_cls.return_value = mock_bot
        await main()
        mock_bot.start.assert_called_once_with(TOKEN)
