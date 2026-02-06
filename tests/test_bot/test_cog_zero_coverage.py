"""
Comprehensive tests for four Discord bot cogs with 0% coverage:
  - cogs/admin.py      (Admin)
  - cogs/leveling.py   (Leveling)
  - cogs/scheduler.py  (ScheduledMessages)
  - cogs/welcome.py    (Welcome)

Every test imports the real cog class, instantiates it with a mock bot,
and exercises real code paths.  Command methods are called via
``cog.command_name.callback(cog, ctx, ...)`` to bypass the discord.py
Command.__call__ dispatcher while still exercising the actual cog code.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
from datetime import datetime, timedelta

import discord
from discord.ext import commands


# ============================================================================
# Helpers
# ============================================================================

def _make_bot(**overrides):
    """Return a minimal mock Bot with sane defaults."""
    bot = MagicMock(spec=commands.Bot)
    bot.user = MagicMock()
    bot.user.id = 999
    bot.user.name = "TestBot"
    bot.user.display_avatar = MagicMock()
    bot.user.display_avatar.url = "https://cdn.discordapp.com/avatar.png"
    bot.latency = 0.042
    bot.guilds = []
    bot.commands = [MagicMock() for _ in range(25)]
    bot.get_command = MagicMock(return_value=None)
    bot.get_channel = MagicMock(return_value=None)
    bot.tree = MagicMock()
    bot.tree.sync = AsyncMock(return_value=[MagicMock()] * 10)
    bot.reload_extension = AsyncMock()
    bot.close = AsyncMock()
    for k, v in overrides.items():
        setattr(bot, k, v)
    return bot


def _make_ctx(**overrides):
    """Return a minimal mock Context with sane defaults."""
    ctx = MagicMock(spec=commands.Context)
    ctx.guild = MagicMock(spec=discord.Guild)
    ctx.guild.id = 123
    ctx.guild.name = "Test Server"
    ctx.guild.member_count = 42
    ctx.guild.get_channel = MagicMock(return_value=None)
    ctx.guild.get_member = MagicMock(return_value=None)
    ctx.guild.get_role = MagicMock(return_value=None)
    ctx.guild.text_channels = []
    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.id = 456
    ctx.author.mention = "<@456>"
    ctx.author.display_name = "Tester"
    ctx.author.display_avatar = MagicMock()
    ctx.author.display_avatar.url = "https://cdn.discordapp.com/avatar2.png"
    ctx.send = AsyncMock()
    ctx.send_help = AsyncMock()
    ctx.channel = MagicMock()
    ctx.channel.id = 789
    ctx.channel.send = AsyncMock()
    ctx.prefix = "!"
    ctx.invoked_subcommand = None
    ctx.command = MagicMock()
    for k, v in overrides.items():
        setattr(ctx, k, v)
    return ctx


# ============================================================================
# ADMIN COG
# ============================================================================

class TestAdminInit:
    @patch('cogs.admin.db')
    def test_init_stores_bot(self, mock_db):
        from cogs.admin import Admin
        bot = _make_bot()
        cog = Admin(bot)
        assert cog.bot is bot


class TestAdminConfig:
    @patch('cogs.admin.db')
    @pytest.mark.asyncio
    async def test_config_no_subcommand_calls_show_config(self, mock_db):
        from cogs.admin import Admin
        bot = _make_bot()
        cog = Admin(bot)
        ctx = _make_ctx()
        ctx.invoked_subcommand = None
        mock_db.get_guild_config = AsyncMock(return_value={
            'welcome_channel_id': 0, 'log_channel_id': 0,
            'level_up_channel_id': 0, 'auto_mod_enabled': True,
            'leveling_enabled': True, 'prefix': '!'
        })
        await cog.config.callback(cog, ctx)
        ctx.send.assert_called_once()

    @patch('cogs.admin.db')
    @pytest.mark.asyncio
    async def test_config_with_subcommand_does_not_call_show(self, mock_db):
        from cogs.admin import Admin
        bot = _make_bot()
        cog = Admin(bot)
        ctx = _make_ctx()
        ctx.invoked_subcommand = MagicMock()
        await cog.config.callback(cog, ctx)
        ctx.send.assert_not_called()


class TestAdminShowConfig:
    @patch('cogs.admin.db')
    @pytest.mark.asyncio
    async def test_show_config_all_channels(self, mock_db):
        from cogs.admin import Admin
        bot = _make_bot()
        cog = Admin(bot)
        ctx = _make_ctx()
        mock_db.get_guild_config = AsyncMock(return_value={
            'welcome_channel_id': 111, 'log_channel_id': 222,
            'level_up_channel_id': 333, 'auto_mod_enabled': True,
            'leveling_enabled': True, 'prefix': '!'
        })
        chan_mock = MagicMock()
        chan_mock.mention = "#chan"
        ctx.guild.get_channel = MagicMock(return_value=chan_mock)
        await cog.show_config(ctx)
        ctx.send.assert_called_once()
        embed = ctx.send.call_args[1]['embed']
        assert ctx.guild.name in embed.title

    @patch('cogs.admin.db')
    @pytest.mark.asyncio
    async def test_show_config_no_channels(self, mock_db):
        from cogs.admin import Admin
        bot = _make_bot()
        cog = Admin(bot)
        ctx = _make_ctx()
        mock_db.get_guild_config = AsyncMock(return_value={
            'welcome_channel_id': 0, 'log_channel_id': 0,
            'level_up_channel_id': 0, 'auto_mod_enabled': False,
            'leveling_enabled': False, 'prefix': '?'
        })
        ctx.guild.get_channel = MagicMock(return_value=None)
        await cog.show_config(ctx)
        ctx.send.assert_called_once()
        embed = ctx.send.call_args[1]['embed']
        field_val = embed.fields[0].value
        assert 'Non configuré' in field_val

    @patch('cogs.admin.db')
    @pytest.mark.asyncio
    async def test_show_config_automod_disabled_text(self, mock_db):
        from cogs.admin import Admin
        bot = _make_bot()
        cog = Admin(bot)
        ctx = _make_ctx()
        mock_db.get_guild_config = AsyncMock(return_value={
            'welcome_channel_id': 0, 'log_channel_id': 0,
            'level_up_channel_id': 0, 'auto_mod_enabled': False,
            'leveling_enabled': False, 'prefix': '!'
        })
        ctx.guild.get_channel = MagicMock(return_value=None)
        await cog.show_config(ctx)
        embed = ctx.send.call_args[1]['embed']
        assert 'Désactivé' in embed.fields[1].value


class TestAdminConfigPrefix:
    @patch('cogs.admin.db')
    @pytest.mark.asyncio
    async def test_prefix_valid(self, mock_db):
        from cogs.admin import Admin
        bot = _make_bot()
        cog = Admin(bot)
        ctx = _make_ctx()
        mock_db.update_guild_config = AsyncMock()
        await cog.config_prefix.callback(cog, ctx, "?")
        mock_db.update_guild_config.assert_awaited_once()
        embed = ctx.send.call_args[1]['embed']
        assert "?" in embed.description

    @patch('cogs.admin.db')
    @pytest.mark.asyncio
    async def test_prefix_too_long(self, mock_db):
        from cogs.admin import Admin
        bot = _make_bot()
        cog = Admin(bot)
        ctx = _make_ctx()
        await cog.config_prefix.callback(cog, ctx, "!!!!!!!")
        mock_db.update_guild_config.assert_not_called()
        ctx.send.assert_called_once()
        assert "5 caractères" in ctx.send.call_args[0][0]

    @patch('cogs.admin.db')
    @pytest.mark.asyncio
    async def test_prefix_exactly_five(self, mock_db):
        from cogs.admin import Admin
        bot = _make_bot()
        cog = Admin(bot)
        ctx = _make_ctx()
        mock_db.update_guild_config = AsyncMock()
        await cog.config_prefix.callback(cog, ctx, "!!!!!")
        mock_db.update_guild_config.assert_awaited_once()


class TestAdminConfigLogchannel:
    @patch('cogs.admin.db')
    @pytest.mark.asyncio
    async def test_logchannel(self, mock_db):
        from cogs.admin import Admin
        bot = _make_bot()
        cog = Admin(bot)
        ctx = _make_ctx()
        mock_db.update_guild_config = AsyncMock()
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 888
        channel.mention = "#logs"
        await cog.config_logchannel.callback(cog, ctx, channel)
        mock_db.update_guild_config.assert_awaited_once_with(123, log_channel_id=888)
        embed = ctx.send.call_args[1]['embed']
        assert "#logs" in embed.description


class TestAdminConfigLevelchannel:
    @patch('cogs.admin.db')
    @pytest.mark.asyncio
    async def test_levelchannel_with_channel(self, mock_db):
        from cogs.admin import Admin
        bot = _make_bot()
        cog = Admin(bot)
        ctx = _make_ctx()
        mock_db.update_guild_config = AsyncMock()
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 777
        channel.mention = "#levels"
        await cog.config_levelchannel.callback(cog, ctx, channel)
        mock_db.update_guild_config.assert_awaited_once_with(123, level_up_channel_id=777)
        embed = ctx.send.call_args[1]['embed']
        assert "#levels" in embed.description

    @patch('cogs.admin.db')
    @pytest.mark.asyncio
    async def test_levelchannel_none(self, mock_db):
        from cogs.admin import Admin
        bot = _make_bot()
        cog = Admin(bot)
        ctx = _make_ctx()
        mock_db.update_guild_config = AsyncMock()
        await cog.config_levelchannel.callback(cog, ctx, None)
        mock_db.update_guild_config.assert_awaited_once_with(123, level_up_channel_id=None)
        embed = ctx.send.call_args[1]['embed']
        assert "channel où l'utilisateur" in embed.description


class TestAdminConfigAutomod:
    @patch('cogs.admin.db')
    @pytest.mark.asyncio
    async def test_automod_on(self, mock_db):
        from cogs.admin import Admin
        bot = _make_bot()
        cog = Admin(bot)
        ctx = _make_ctx()
        mock_db.update_guild_config = AsyncMock()
        await cog.config_automod.callback(cog, ctx, "on")
        mock_db.update_guild_config.assert_awaited_once_with(123, auto_mod_enabled=1)
        assert 'activée' in ctx.send.call_args[1]['embed'].title

    @patch('cogs.admin.db')
    @pytest.mark.asyncio
    async def test_automod_off(self, mock_db):
        from cogs.admin import Admin
        bot = _make_bot()
        cog = Admin(bot)
        ctx = _make_ctx()
        mock_db.update_guild_config = AsyncMock()
        await cog.config_automod.callback(cog, ctx, "false")
        mock_db.update_guild_config.assert_awaited_once_with(123, auto_mod_enabled=0)
        assert 'désactivée' in ctx.send.call_args[1]['embed'].title

    @patch('cogs.admin.db')
    @pytest.mark.asyncio
    async def test_automod_true(self, mock_db):
        from cogs.admin import Admin
        bot = _make_bot()
        cog = Admin(bot)
        ctx = _make_ctx()
        mock_db.update_guild_config = AsyncMock()
        await cog.config_automod.callback(cog, ctx, "true")
        mock_db.update_guild_config.assert_awaited_once_with(123, auto_mod_enabled=1)

    @patch('cogs.admin.db')
    @pytest.mark.asyncio
    async def test_automod_invalid(self, mock_db):
        from cogs.admin import Admin
        bot = _make_bot()
        cog = Admin(bot)
        ctx = _make_ctx()
        await cog.config_automod.callback(cog, ctx, "maybe")
        mock_db.update_guild_config.assert_not_called()
        assert "on/off" in ctx.send.call_args[0][0]


class TestAdminConfigLeveling:
    @patch('cogs.admin.db')
    @pytest.mark.asyncio
    async def test_leveling_on(self, mock_db):
        from cogs.admin import Admin
        bot = _make_bot()
        cog = Admin(bot)
        ctx = _make_ctx()
        mock_db.update_guild_config = AsyncMock()
        await cog.config_leveling.callback(cog, ctx, "1")
        mock_db.update_guild_config.assert_awaited_once_with(123, leveling_enabled=1)
        assert 'activé' in ctx.send.call_args[1]['embed'].title

    @patch('cogs.admin.db')
    @pytest.mark.asyncio
    async def test_leveling_off(self, mock_db):
        from cogs.admin import Admin
        bot = _make_bot()
        cog = Admin(bot)
        ctx = _make_ctx()
        mock_db.update_guild_config = AsyncMock()
        await cog.config_leveling.callback(cog, ctx, "0")
        mock_db.update_guild_config.assert_awaited_once_with(123, leveling_enabled=0)
        assert 'désactivé' in ctx.send.call_args[1]['embed'].title

    @patch('cogs.admin.db')
    @pytest.mark.asyncio
    async def test_leveling_invalid(self, mock_db):
        from cogs.admin import Admin
        bot = _make_bot()
        cog = Admin(bot)
        ctx = _make_ctx()
        await cog.config_leveling.callback(cog, ctx, "nope")
        mock_db.update_guild_config.assert_not_called()


class TestAdminConfigLevelupmsg:
    @patch('cogs.admin.db')
    @pytest.mark.asyncio
    async def test_levelupmsg(self, mock_db):
        from cogs.admin import Admin
        bot = _make_bot()
        cog = Admin(bot)
        ctx = _make_ctx()
        mock_db.update_guild_config = AsyncMock()
        await cog.config_levelupmsg.callback(cog, ctx, message="GG {user} you hit {level}!")
        mock_db.update_guild_config.assert_awaited_once()
        embed = ctx.send.call_args[1]['embed']
        assert "<@456>" in embed.description
        assert "5" in embed.description


class TestAdminHelp:
    @patch('cogs.admin.db')
    @pytest.mark.asyncio
    async def test_help_specific_command_found(self, mock_db):
        from cogs.admin import Admin
        bot = _make_bot()
        cmd = MagicMock()
        cmd.name = "ping"
        cmd.help = "Check latency."
        cmd.aliases = ["p"]
        cmd.signature = ""
        bot.get_command = MagicMock(return_value=cmd)
        cog = Admin(bot)
        ctx = _make_ctx()
        await cog.help_command.callback(cog, ctx, commande="ping")
        embed = ctx.send.call_args[1]['embed']
        assert "ping" in embed.title

    @patch('cogs.admin.db')
    @pytest.mark.asyncio
    async def test_help_specific_command_not_found(self, mock_db):
        from cogs.admin import Admin
        bot = _make_bot()
        bot.get_command = MagicMock(return_value=None)
        cog = Admin(bot)
        ctx = _make_ctx()
        await cog.help_command.callback(cog, ctx, commande="nonexistent")
        assert "introuvable" in ctx.send.call_args[0][0]

    @patch('cogs.admin.db')
    @pytest.mark.asyncio
    async def test_help_command_no_aliases(self, mock_db):
        from cogs.admin import Admin
        bot = _make_bot()
        cmd = MagicMock()
        cmd.name = "test"
        cmd.help = "A test."
        cmd.aliases = []
        cmd.signature = "<arg>"
        bot.get_command = MagicMock(return_value=cmd)
        cog = Admin(bot)
        ctx = _make_ctx()
        await cog.help_command.callback(cog, ctx, commande="test")
        embed = ctx.send.call_args[1]['embed']
        alias_fields = [f for f in embed.fields if f.name == "Aliases"]
        assert len(alias_fields) == 0

    @patch('cogs.admin.db')
    @pytest.mark.asyncio
    async def test_help_command_no_description(self, mock_db):
        from cogs.admin import Admin
        bot = _make_bot()
        cmd = MagicMock()
        cmd.name = "test"
        cmd.help = None
        cmd.aliases = []
        cmd.signature = ""
        bot.get_command = MagicMock(return_value=cmd)
        cog = Admin(bot)
        ctx = _make_ctx()
        await cog.help_command.callback(cog, ctx, commande="test")
        embed = ctx.send.call_args[1]['embed']
        assert "Pas de description" in embed.description

    @patch('cogs.admin.db')
    @pytest.mark.asyncio
    async def test_help_full_list(self, mock_db):
        from cogs.admin import Admin
        bot = _make_bot()
        cog = Admin(bot)
        ctx = _make_ctx()
        await cog.help_command.callback(cog, ctx, commande=None)
        embed = ctx.send.call_args[1]['embed']
        assert len(embed.fields) == 8


class TestAdminBotinfo:
    @patch('cogs.admin.db')
    @pytest.mark.asyncio
    async def test_botinfo(self, mock_db):
        from cogs.admin import Admin
        bot = _make_bot()
        g1 = MagicMock()
        g1.member_count = 50
        g1.channels = [MagicMock()] * 5
        g2 = MagicMock()
        g2.member_count = 30
        g2.channels = [MagicMock()] * 3
        bot.guilds = [g1, g2]
        cog = Admin(bot)
        ctx = _make_ctx()
        await cog.botinfo.callback(cog, ctx)
        embed = ctx.send.call_args[1]['embed']
        assert "TestBot" in embed.title


class TestAdminInvite:
    @patch('cogs.admin.db')
    @pytest.mark.asyncio
    async def test_invite(self, mock_db):
        from cogs.admin import Admin
        bot = _make_bot()
        cog = Admin(bot)
        ctx = _make_ctx()
        await cog.invite.callback(cog, ctx)
        embed = ctx.send.call_args[1]['embed']
        assert "Inviter" in embed.title


class TestAdminSync:
    @patch('cogs.admin.db')
    @pytest.mark.asyncio
    async def test_sync_success(self, mock_db):
        from cogs.admin import Admin
        bot = _make_bot()
        cog = Admin(bot)
        ctx = _make_ctx()
        await cog.sync.callback(cog, ctx)
        assert ctx.send.call_count == 2
        last_msg = ctx.send.call_args[0][0]
        assert "10" in last_msg

    @patch('cogs.admin.db')
    @pytest.mark.asyncio
    async def test_sync_failure(self, mock_db):
        from cogs.admin import Admin
        bot = _make_bot()
        bot.tree.sync = AsyncMock(side_effect=Exception("sync fail"))
        cog = Admin(bot)
        ctx = _make_ctx()
        await cog.sync.callback(cog, ctx)
        assert ctx.send.call_count == 2
        last_msg = ctx.send.call_args[0][0]
        assert "Erreur" in last_msg


class TestAdminReloadCog:
    @patch('cogs.admin.db')
    @pytest.mark.asyncio
    async def test_reload_success(self, mock_db):
        from cogs.admin import Admin
        bot = _make_bot()
        cog = Admin(bot)
        ctx = _make_ctx()
        await cog.reload_cog.callback(cog, ctx, "utility")
        bot.reload_extension.assert_awaited_once_with("cogs.utility")
        assert "rechargé" in ctx.send.call_args[0][0]

    @patch('cogs.admin.db')
    @pytest.mark.asyncio
    async def test_reload_failure(self, mock_db):
        from cogs.admin import Admin
        bot = _make_bot()
        bot.reload_extension = AsyncMock(side_effect=Exception("not found"))
        cog = Admin(bot)
        ctx = _make_ctx()
        await cog.reload_cog.callback(cog, ctx, "bad")
        assert "Erreur" in ctx.send.call_args[0][0]


class TestAdminShutdown:
    @patch('cogs.admin.db')
    @pytest.mark.asyncio
    async def test_shutdown(self, mock_db):
        from cogs.admin import Admin
        bot = _make_bot()
        cog = Admin(bot)
        ctx = _make_ctx()
        await cog.shutdown.callback(cog, ctx)
        ctx.send.assert_called_once()
        bot.close.assert_awaited_once()


class TestAdminSetup:
    @patch('cogs.admin.db')
    @pytest.mark.asyncio
    async def test_setup(self, mock_db):
        from cogs.admin import setup
        bot = _make_bot()
        bot.add_cog = AsyncMock()
        await setup(bot)
        bot.add_cog.assert_awaited_once()


# ============================================================================
# LEVELING COG
# ============================================================================

class TestLevelingInit:
    @patch('cogs.leveling.db')
    def test_init(self, mock_db):
        from cogs.leveling import Leveling
        bot = _make_bot()
        cog = Leveling(bot)
        assert cog.bot is bot
        assert cog.xp_cooldowns == {}


class TestLevelingCalculateXp:
    @patch('cogs.leveling.db')
    def test_xp_for_level_1(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        assert cog.calculate_xp_for_level(1) == 100

    @patch('cogs.leveling.db')
    def test_xp_for_level_2(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        assert cog.calculate_xp_for_level(2) == 150

    @patch('cogs.leveling.db')
    def test_xp_for_level_5(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        assert cog.calculate_xp_for_level(5) == int(100 * (1.5 ** 4))


class TestLevelingCalculateLevelFromXp:
    @patch('cogs.leveling.db')
    def test_zero_xp(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        level, remaining = cog.calculate_level_from_xp(0)
        assert level == 1
        assert remaining == 0

    @patch('cogs.leveling.db')
    def test_exact_level_boundary(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        level, remaining = cog.calculate_level_from_xp(100)
        assert level == 2
        assert remaining == 0

    @patch('cogs.leveling.db')
    def test_mid_level(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        level, remaining = cog.calculate_level_from_xp(50)
        assert level == 1
        assert remaining == 50

    @patch('cogs.leveling.db')
    def test_high_xp(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        level, remaining = cog.calculate_level_from_xp(10000)
        assert level > 1


class TestLevelingCheckAndAssignRoles:
    @patch('cogs.leveling.db')
    @pytest.mark.asyncio
    async def test_adds_qualifying_role(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        role = MagicMock(spec=discord.Role)
        member = MagicMock(spec=discord.Member)
        member.guild = MagicMock(spec=discord.Guild)
        member.guild.id = 123
        member.guild.get_role = MagicMock(return_value=role)
        member.roles = []
        member.add_roles = AsyncMock()
        mock_db.get_level_roles = AsyncMock(return_value=[{'role_id': 10, 'level': 5}])
        await cog.check_and_assign_level_roles(member, 5)
        member.add_roles.assert_awaited_once_with(role)

    @patch('cogs.leveling.db')
    @pytest.mark.asyncio
    async def test_removes_unqualified_role(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        role = MagicMock(spec=discord.Role)
        member = MagicMock(spec=discord.Member)
        member.guild = MagicMock(spec=discord.Guild)
        member.guild.id = 123
        member.guild.get_role = MagicMock(return_value=role)
        member.roles = [role]
        member.remove_roles = AsyncMock()
        mock_db.get_level_roles = AsyncMock(return_value=[{'role_id': 10, 'level': 10}])
        await cog.check_and_assign_level_roles(member, 5)
        member.remove_roles.assert_awaited_once_with(role)

    @patch('cogs.leveling.db')
    @pytest.mark.asyncio
    async def test_forbidden_add_role(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        role = MagicMock(spec=discord.Role)
        member = MagicMock(spec=discord.Member)
        member.guild = MagicMock(spec=discord.Guild)
        member.guild.id = 123
        member.guild.get_role = MagicMock(return_value=role)
        member.roles = []
        member.add_roles = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "no perms"))
        mock_db.get_level_roles = AsyncMock(return_value=[{'role_id': 10, 'level': 5}])
        await cog.check_and_assign_level_roles(member, 5)

    @patch('cogs.leveling.db')
    @pytest.mark.asyncio
    async def test_forbidden_remove_role(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        role = MagicMock(spec=discord.Role)
        member = MagicMock(spec=discord.Member)
        member.guild = MagicMock(spec=discord.Guild)
        member.guild.id = 123
        member.guild.get_role = MagicMock(return_value=role)
        member.roles = [role]
        member.remove_roles = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "no perms"))
        mock_db.get_level_roles = AsyncMock(return_value=[{'role_id': 10, 'level': 10}])
        await cog.check_and_assign_level_roles(member, 5)

    @patch('cogs.leveling.db')
    @pytest.mark.asyncio
    async def test_role_not_found_in_guild(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        member = MagicMock(spec=discord.Member)
        member.guild = MagicMock(spec=discord.Guild)
        member.guild.id = 123
        member.guild.get_role = MagicMock(return_value=None)
        mock_db.get_level_roles = AsyncMock(return_value=[{'role_id': 10, 'level': 5}])
        await cog.check_and_assign_level_roles(member, 5)

    @patch('cogs.leveling.db')
    @pytest.mark.asyncio
    async def test_already_has_qualifying_role(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        role = MagicMock(spec=discord.Role)
        member = MagicMock(spec=discord.Member)
        member.guild = MagicMock(spec=discord.Guild)
        member.guild.id = 123
        member.guild.get_role = MagicMock(return_value=role)
        member.roles = [role]
        member.add_roles = AsyncMock()
        mock_db.get_level_roles = AsyncMock(return_value=[{'role_id': 10, 'level': 5}])
        await cog.check_and_assign_level_roles(member, 5)
        member.add_roles.assert_not_awaited()


class TestLevelingOnMessage:
    @patch('cogs.leveling.db')
    @pytest.mark.asyncio
    async def test_skips_bot_message(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        message = MagicMock()
        message.author.bot = True
        message.guild = MagicMock()
        await cog.on_message(message)
        mock_db.get_guild_config.assert_not_called()

    @patch('cogs.leveling.db')
    @pytest.mark.asyncio
    async def test_skips_dm_message(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        message = MagicMock()
        message.author.bot = False
        message.guild = None
        await cog.on_message(message)
        mock_db.get_guild_config.assert_not_called()

    @patch('cogs.leveling.db')
    @pytest.mark.asyncio
    async def test_skips_cooldown(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        message = MagicMock()
        message.author.bot = False
        message.author.id = 1
        message.guild = MagicMock()
        message.guild.id = 2
        cog.xp_cooldowns[(1, 2)] = datetime.now()
        await cog.on_message(message)
        mock_db.get_guild_config.assert_not_called()

    @patch('cogs.leveling.db')
    @pytest.mark.asyncio
    async def test_skips_leveling_disabled(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        message = MagicMock()
        message.author.bot = False
        message.author.id = 1
        message.guild = MagicMock()
        message.guild.id = 2
        mock_db.get_guild_config = AsyncMock(return_value={'leveling_enabled': False})
        await cog.on_message(message)
        mock_db.add_xp.assert_not_called()

    @patch('cogs.leveling.db')
    @pytest.mark.asyncio
    async def test_awards_xp_no_level_up(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        message = MagicMock()
        message.author.bot = False
        message.author.id = 1
        message.author.mention = "<@1>"
        message.guild = MagicMock()
        message.guild.id = 2
        mock_db.get_guild_config = AsyncMock(return_value={'leveling_enabled': True})
        mock_db.add_xp = AsyncMock(return_value={'total_xp': 50, 'level': 1})
        await cog.on_message(message)
        mock_db.add_xp.assert_awaited_once()
        mock_db.set_level.assert_not_called()

    @patch('cogs.leveling.db')
    @pytest.mark.asyncio
    async def test_level_up_default_channel(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        message = MagicMock()
        message.author.bot = False
        message.author.id = 1
        message.author.mention = "<@1>"
        message.author.display_avatar = MagicMock()
        message.author.display_avatar.url = "http://img"
        message.guild = MagicMock()
        message.guild.id = 2
        message.guild.get_channel = MagicMock(return_value=None)
        message.guild.get_role = MagicMock(return_value=None)
        message.channel = MagicMock()
        message.channel.send = AsyncMock()
        mock_db.get_guild_config = AsyncMock(return_value={
            'leveling_enabled': True, 'level_up_channel_id': None
        })
        mock_db.add_xp = AsyncMock(return_value={'total_xp': 100, 'level': 1})
        mock_db.set_level = AsyncMock()
        mock_db.get_level_roles = AsyncMock(return_value=[])
        mock_db.get_role_for_level = AsyncMock(return_value=None)
        await cog.on_message(message)
        mock_db.set_level.assert_awaited_once()
        message.channel.send.assert_awaited_once()

    @patch('cogs.leveling.db')
    @pytest.mark.asyncio
    async def test_level_up_dedicated_channel(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        message = MagicMock()
        message.author.bot = False
        message.author.id = 1
        message.author.mention = "<@1>"
        message.author.display_avatar = MagicMock()
        message.author.display_avatar.url = "http://img"
        message.guild = MagicMock()
        message.guild.id = 2
        level_ch = MagicMock()
        level_ch.send = AsyncMock()
        message.guild.get_channel = MagicMock(return_value=level_ch)
        message.guild.get_role = MagicMock(return_value=None)
        message.channel = MagicMock()
        message.channel.send = AsyncMock()
        mock_db.get_guild_config = AsyncMock(return_value={
            'leveling_enabled': True, 'level_up_channel_id': 999
        })
        mock_db.add_xp = AsyncMock(return_value={'total_xp': 100, 'level': 1})
        mock_db.set_level = AsyncMock()
        mock_db.get_level_roles = AsyncMock(return_value=[])
        mock_db.get_role_for_level = AsyncMock(return_value=None)
        await cog.on_message(message)
        level_ch.send.assert_awaited_once()
        message.channel.send.assert_not_awaited()

    @patch('cogs.leveling.db')
    @pytest.mark.asyncio
    async def test_level_up_with_role_reward(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        role = MagicMock(spec=discord.Role)
        role.mention = "@Level2"
        message = MagicMock()
        message.author.bot = False
        message.author.id = 1
        message.author.mention = "<@1>"
        message.author.display_avatar = MagicMock()
        message.author.display_avatar.url = "http://img"
        message.guild = MagicMock()
        message.guild.id = 2
        message.guild.get_channel = MagicMock(return_value=None)
        message.guild.get_role = MagicMock(return_value=role)
        message.channel = MagicMock()
        message.channel.send = AsyncMock()
        mock_db.get_guild_config = AsyncMock(return_value={
            'leveling_enabled': True, 'level_up_channel_id': None
        })
        mock_db.add_xp = AsyncMock(return_value={'total_xp': 100, 'level': 1})
        mock_db.set_level = AsyncMock()
        mock_db.get_level_roles = AsyncMock(return_value=[])
        mock_db.get_role_for_level = AsyncMock(return_value=42)
        await cog.on_message(message)
        embed = message.channel.send.call_args[1]['embed']
        assert len(embed.fields) > 0

    @patch('cogs.leveling.db')
    @pytest.mark.asyncio
    async def test_level_up_custom_message(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        message = MagicMock()
        message.author.bot = False
        message.author.id = 1
        message.author.mention = "<@1>"
        message.author.display_avatar = MagicMock()
        message.author.display_avatar.url = "http://img"
        message.guild = MagicMock()
        message.guild.id = 2
        message.guild.get_channel = MagicMock(return_value=None)
        message.guild.get_role = MagicMock(return_value=None)
        message.channel = MagicMock()
        message.channel.send = AsyncMock()
        mock_db.get_guild_config = AsyncMock(return_value={
            'leveling_enabled': True, 'level_up_channel_id': None,
            'level_up_message': 'Bravo {user}! Niveau {level}!'
        })
        mock_db.add_xp = AsyncMock(return_value={'total_xp': 100, 'level': 1})
        mock_db.set_level = AsyncMock()
        mock_db.get_level_roles = AsyncMock(return_value=[])
        mock_db.get_role_for_level = AsyncMock(return_value=None)
        await cog.on_message(message)
        embed = message.channel.send.call_args[1]['embed']
        assert "Bravo <@1>" in embed.description


class TestLevelingRank:
    @patch('cogs.leveling.db')
    @pytest.mark.asyncio
    async def test_rank_self(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        ctx = _make_ctx()
        ctx.author.bot = False
        ctx.author.display_name = "Tester"
        ctx.author.display_avatar = MagicMock()
        ctx.author.display_avatar.url = "http://img"
        mock_db.get_or_create_user = AsyncMock(return_value={
            'level': 3, 'xp': 50, 'total_xp': 400, 'messages_count': 100
        })
        mock_db.get_rank = AsyncMock(return_value=2)
        await cog.rank.callback(cog, ctx, membre=None)
        ctx.send.assert_called_once()
        embed = ctx.send.call_args[1]['embed']
        assert "Tester" in embed.title

    @patch('cogs.leveling.db')
    @pytest.mark.asyncio
    async def test_rank_other(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        ctx = _make_ctx()
        other = MagicMock(spec=discord.Member)
        other.bot = False
        other.display_name = "Other"
        other.display_avatar = MagicMock()
        other.display_avatar.url = "http://img"
        other.id = 999
        mock_db.get_or_create_user = AsyncMock(return_value={
            'level': 5, 'xp': 80, 'total_xp': 800, 'messages_count': 200
        })
        mock_db.get_rank = AsyncMock(return_value=1)
        await cog.rank.callback(cog, ctx, membre=other)
        embed = ctx.send.call_args[1]['embed']
        assert "Other" in embed.title

    @patch('cogs.leveling.db')
    @pytest.mark.asyncio
    async def test_rank_bot(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        ctx = _make_ctx()
        bot_member = MagicMock(spec=discord.Member)
        bot_member.bot = True
        await cog.rank.callback(cog, ctx, membre=bot_member)
        assert "bots" in ctx.send.call_args[0][0].lower()


class TestLevelingLeaderboard:
    @patch('cogs.leveling.db')
    @pytest.mark.asyncio
    async def test_leaderboard_page_1(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        ctx = _make_ctx()
        users = [{'user_id': i, 'level': 10 - i, 'total_xp': (10 - i) * 100} for i in range(15)]
        mock_db.get_leaderboard = AsyncMock(return_value=users)
        ctx.guild.get_member = MagicMock(return_value=MagicMock(display_name="User"))
        await cog.leaderboard.callback(cog, ctx, page=1)
        embed = ctx.send.call_args[1]['embed']
        assert "Page 1" in embed.footer.text

    @patch('cogs.leveling.db')
    @pytest.mark.asyncio
    async def test_leaderboard_empty(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        ctx = _make_ctx()
        mock_db.get_leaderboard = AsyncMock(return_value=[])
        await cog.leaderboard.callback(cog, ctx, page=1)
        embed = ctx.send.call_args[1]['embed']
        assert "Aucun" in embed.description

    @patch('cogs.leveling.db')
    @pytest.mark.asyncio
    async def test_leaderboard_invalid_page(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        ctx = _make_ctx()
        mock_db.get_leaderboard = AsyncMock(return_value=[{'user_id': 1, 'level': 1, 'total_xp': 10}])
        await cog.leaderboard.callback(cog, ctx, page=99)
        assert "invalide" in ctx.send.call_args[0][0].lower()

    @patch('cogs.leveling.db')
    @pytest.mark.asyncio
    async def test_leaderboard_page_0(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        ctx = _make_ctx()
        mock_db.get_leaderboard = AsyncMock(return_value=[{'user_id': 1, 'level': 1, 'total_xp': 10}])
        await cog.leaderboard.callback(cog, ctx, page=0)
        assert "invalide" in ctx.send.call_args[0][0].lower()

    @patch('cogs.leveling.db')
    @pytest.mark.asyncio
    async def test_leaderboard_member_not_found(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        ctx = _make_ctx()
        users = [{'user_id': 99999, 'level': 5, 'total_xp': 500}]
        mock_db.get_leaderboard = AsyncMock(return_value=users)
        ctx.guild.get_member = MagicMock(return_value=None)
        await cog.leaderboard.callback(cog, ctx, page=1)
        embed = ctx.send.call_args[1]['embed']
        assert "Utilisateur #99999" in embed.description


class TestLevelingSetXp:
    @patch('cogs.leveling.db')
    @pytest.mark.asyncio
    async def test_setxp_valid(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        ctx = _make_ctx()
        membre = MagicMock(spec=discord.Member)
        membre.id = 10
        membre.mention = "<@10>"
        membre.guild = MagicMock(spec=discord.Guild)
        membre.guild.id = 123
        mock_db.get_or_create_user = AsyncMock(return_value={'total_xp': 0, 'level': 1})
        mock_db.get_level_roles = AsyncMock(return_value=[])
        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)
        mock_db.aiosqlite.connect.return_value = mock_conn
        mock_db.db_path = 'test.db'
        await cog.setxp.callback(cog, ctx, membre, 500)
        mock_conn.execute.assert_awaited_once()
        mock_conn.commit.assert_awaited_once()
        embed = ctx.send.call_args[1]['embed']
        assert "500" in embed.description

    @patch('cogs.leveling.db')
    @pytest.mark.asyncio
    async def test_setxp_negative(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        ctx = _make_ctx()
        membre = MagicMock(spec=discord.Member)
        await cog.setxp.callback(cog, ctx, membre, -10)
        assert "négatif" in ctx.send.call_args[0][0]


class TestLevelingAddXp:
    @patch('cogs.leveling.db')
    @pytest.mark.asyncio
    async def test_addxp_positive(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        ctx = _make_ctx()
        membre = MagicMock(spec=discord.Member)
        membre.id = 10
        membre.mention = "<@10>"
        membre.guild = MagicMock(spec=discord.Guild)
        membre.guild.id = 123
        mock_db.get_or_create_user = AsyncMock(return_value={'total_xp': 100, 'level': 1})
        mock_db.get_level_roles = AsyncMock(return_value=[])
        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)
        mock_db.aiosqlite.connect.return_value = mock_conn
        mock_db.db_path = 'test.db'
        await cog.addxp.callback(cog, ctx, membre, 200)
        embed = ctx.send.call_args[1]['embed']
        assert "ajouté" in embed.description

    @patch('cogs.leveling.db')
    @pytest.mark.asyncio
    async def test_addxp_negative(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        ctx = _make_ctx()
        membre = MagicMock(spec=discord.Member)
        membre.id = 10
        membre.mention = "<@10>"
        membre.guild = MagicMock(spec=discord.Guild)
        membre.guild.id = 123
        mock_db.get_or_create_user = AsyncMock(return_value={'total_xp': 100, 'level': 1})
        mock_db.get_level_roles = AsyncMock(return_value=[])
        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)
        mock_db.aiosqlite.connect.return_value = mock_conn
        mock_db.db_path = 'test.db'
        await cog.addxp.callback(cog, ctx, membre, -50)
        embed = ctx.send.call_args[1]['embed']
        assert "retiré" in embed.description

    @patch('cogs.leveling.db')
    @pytest.mark.asyncio
    async def test_addxp_clamps_to_zero(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        ctx = _make_ctx()
        membre = MagicMock(spec=discord.Member)
        membre.id = 10
        membre.mention = "<@10>"
        membre.guild = MagicMock(spec=discord.Guild)
        membre.guild.id = 123
        mock_db.get_or_create_user = AsyncMock(return_value={'total_xp': 50, 'level': 1})
        mock_db.get_level_roles = AsyncMock(return_value=[])
        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)
        mock_db.aiosqlite.connect.return_value = mock_conn
        mock_db.db_path = 'test.db'
        await cog.addxp.callback(cog, ctx, membre, -9999)
        args = mock_conn.execute.call_args[0]
        assert args[1][1] == 0  # total_xp clamped to 0


class TestLevelingLevelRole:
    @patch('cogs.leveling.db')
    @pytest.mark.asyncio
    async def test_levelrole_valid(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        ctx = _make_ctx()
        role = MagicMock(spec=discord.Role)
        role.id = 55
        role.mention = "@LVL5"
        mock_db.add_level_role = AsyncMock()
        await cog.levelrole.callback(cog, ctx, 5, role)
        mock_db.add_level_role.assert_awaited_once_with(123, 5, 55)
        embed = ctx.send.call_args[1]['embed']
        assert "@LVL5" in embed.description

    @patch('cogs.leveling.db')
    @pytest.mark.asyncio
    async def test_levelrole_invalid_level(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        ctx = _make_ctx()
        role = MagicMock(spec=discord.Role)
        await cog.levelrole.callback(cog, ctx, 0, role)
        mock_db.add_level_role.assert_not_called()
        assert "supérieur" in ctx.send.call_args[0][0]


class TestLevelingLevelRoles:
    @patch('cogs.leveling.db')
    @pytest.mark.asyncio
    async def test_levelroles_with_roles(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        ctx = _make_ctx()
        role = MagicMock(spec=discord.Role)
        role.mention = "@Role"
        ctx.guild.get_role = MagicMock(return_value=role)
        mock_db.get_level_roles = AsyncMock(return_value=[{'role_id': 10, 'level': 5}])
        await cog.levelroles.callback(cog, ctx)
        embed = ctx.send.call_args[1]['embed']
        assert "@Role" in embed.description

    @patch('cogs.leveling.db')
    @pytest.mark.asyncio
    async def test_levelroles_empty(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        ctx = _make_ctx()
        mock_db.get_level_roles = AsyncMock(return_value=[])
        await cog.levelroles.callback(cog, ctx)
        assert "Aucun" in ctx.send.call_args[0][0]

    @patch('cogs.leveling.db')
    @pytest.mark.asyncio
    async def test_levelroles_deleted_role(self, mock_db):
        from cogs.leveling import Leveling
        cog = Leveling(_make_bot())
        ctx = _make_ctx()
        ctx.guild.get_role = MagicMock(return_value=None)
        mock_db.get_level_roles = AsyncMock(return_value=[{'role_id': 10, 'level': 5}])
        await cog.levelroles.callback(cog, ctx)
        embed = ctx.send.call_args[1]['embed']
        assert embed.description == "Aucun rôle configuré."


class TestLevelingSetup:
    @patch('cogs.leveling.db')
    @pytest.mark.asyncio
    async def test_setup(self, mock_db):
        from cogs.leveling import setup
        bot = _make_bot()
        bot.add_cog = AsyncMock()
        await setup(bot)
        bot.add_cog.assert_awaited_once()


# ============================================================================
# SCHEDULER COG
# ============================================================================

class TestSchedulerInit:
    @patch('cogs.scheduler.AsyncIOScheduler')
    @patch('cogs.scheduler.db')
    def test_init(self, mock_db, mock_sched_cls):
        from cogs.scheduler import ScheduledMessages
        mock_sched = MagicMock()
        mock_sched_cls.return_value = mock_sched
        bot = _make_bot()
        cog = ScheduledMessages(bot)
        assert cog.bot is bot
        assert cog.scheduler is mock_sched


class TestSchedulerCogLoad:
    @patch('cogs.scheduler.AsyncIOScheduler')
    @patch('cogs.scheduler.db')
    @pytest.mark.asyncio
    async def test_cog_load(self, mock_db, mock_sched_cls):
        from cogs.scheduler import ScheduledMessages
        mock_sched = MagicMock()
        mock_sched_cls.return_value = mock_sched
        bot = _make_bot()
        cog = ScheduledMessages(bot)
        await cog.cog_load()
        assert mock_sched.add_job.call_count == 2
        mock_sched.start.assert_called_once()


class TestSchedulerCogUnload:
    @patch('cogs.scheduler.AsyncIOScheduler')
    @patch('cogs.scheduler.db')
    @pytest.mark.asyncio
    async def test_cog_unload(self, mock_db, mock_sched_cls):
        from cogs.scheduler import ScheduledMessages
        mock_sched = MagicMock()
        mock_sched_cls.return_value = mock_sched
        bot = _make_bot()
        cog = ScheduledMessages(bot)
        await cog.cog_unload()
        mock_sched.shutdown.assert_called_once_with(wait=False)


class TestSchedulerSendDailyMessage:
    @patch('cogs.scheduler.AsyncIOScheduler')
    @patch('cogs.scheduler.db')
    @pytest.mark.asyncio
    async def test_daily_with_channel_id(self, mock_db, mock_sched_cls):
        from cogs.scheduler import ScheduledMessages
        mock_sched_cls.return_value = MagicMock()
        bot = _make_bot()
        channel = MagicMock()
        channel.send = AsyncMock()
        guild = MagicMock()
        guild.id = 1
        guild.name = "G"
        guild.get_channel = MagicMock(return_value=channel)
        guild.text_channels = []
        bot.guilds = [guild]
        mock_db.get_guild_config = AsyncMock(return_value={
            'daily_channel_id': 100, 'welcome_channel_id': None
        })
        cog = ScheduledMessages(bot)
        await cog.send_daily_message()
        channel.send.assert_awaited_once()

    @patch('cogs.scheduler.AsyncIOScheduler')
    @patch('cogs.scheduler.db')
    @pytest.mark.asyncio
    async def test_daily_fallback_general(self, mock_db, mock_sched_cls):
        from cogs.scheduler import ScheduledMessages
        mock_sched_cls.return_value = MagicMock()
        bot = _make_bot()
        gen_ch = MagicMock()
        gen_ch.name = 'general'
        gen_ch.send = AsyncMock()
        guild = MagicMock()
        guild.id = 1
        guild.name = "G"
        guild.get_channel = MagicMock(return_value=None)
        guild.text_channels = [gen_ch]
        bot.guilds = [guild]
        mock_db.get_guild_config = AsyncMock(return_value={
            'daily_channel_id': None, 'welcome_channel_id': None
        })
        with patch('discord.utils.get', side_effect=[None, gen_ch]):
            cog = ScheduledMessages(bot)
            await cog.send_daily_message()
            gen_ch.send.assert_awaited_once()

    @patch('cogs.scheduler.AsyncIOScheduler')
    @patch('cogs.scheduler.db')
    @pytest.mark.asyncio
    async def test_daily_fallback_first_channel(self, mock_db, mock_sched_cls):
        from cogs.scheduler import ScheduledMessages
        mock_sched_cls.return_value = MagicMock()
        bot = _make_bot()
        ch = MagicMock()
        ch.name = 'random'
        ch.send = AsyncMock()
        guild = MagicMock()
        guild.id = 1
        guild.name = "G"
        guild.get_channel = MagicMock(return_value=None)
        guild.text_channels = [ch]
        bot.guilds = [guild]
        mock_db.get_guild_config = AsyncMock(return_value={
            'daily_channel_id': None, 'welcome_channel_id': None
        })
        with patch('discord.utils.get', return_value=None):
            cog = ScheduledMessages(bot)
            await cog.send_daily_message()
            ch.send.assert_awaited_once()

    @patch('cogs.scheduler.AsyncIOScheduler')
    @patch('cogs.scheduler.db')
    @pytest.mark.asyncio
    async def test_daily_no_channels(self, mock_db, mock_sched_cls):
        from cogs.scheduler import ScheduledMessages
        mock_sched_cls.return_value = MagicMock()
        bot = _make_bot()
        guild = MagicMock()
        guild.id = 1
        guild.name = "G"
        guild.get_channel = MagicMock(return_value=None)
        guild.text_channels = []
        bot.guilds = [guild]
        mock_db.get_guild_config = AsyncMock(return_value={
            'daily_channel_id': None, 'welcome_channel_id': None
        })
        with patch('discord.utils.get', return_value=None):
            cog = ScheduledMessages(bot)
            await cog.send_daily_message()

    @patch('cogs.scheduler.AsyncIOScheduler')
    @patch('cogs.scheduler.db')
    @pytest.mark.asyncio
    async def test_daily_custom_message(self, mock_db, mock_sched_cls):
        from cogs.scheduler import ScheduledMessages
        mock_sched_cls.return_value = MagicMock()
        bot = _make_bot()
        channel = MagicMock()
        channel.send = AsyncMock()
        guild = MagicMock()
        guild.id = 1
        guild.name = "G"
        guild.get_channel = MagicMock(return_value=channel)
        bot.guilds = [guild]
        mock_db.get_guild_config = AsyncMock(return_value={
            'daily_channel_id': 100, 'daily_message': 'Custom daily!'
        })
        cog = ScheduledMessages(bot)
        await cog.send_daily_message()
        embed = channel.send.call_args[1]['embed']
        assert "Custom daily!" in embed.description

    @patch('cogs.scheduler.AsyncIOScheduler')
    @patch('cogs.scheduler.db')
    @pytest.mark.asyncio
    async def test_daily_exception_handled(self, mock_db, mock_sched_cls):
        from cogs.scheduler import ScheduledMessages
        mock_sched_cls.return_value = MagicMock()
        bot = _make_bot()
        guild = MagicMock()
        guild.id = 1
        guild.name = "G"
        bot.guilds = [guild]
        mock_db.get_guild_config = AsyncMock(side_effect=Exception("db error"))
        cog = ScheduledMessages(bot)
        await cog.send_daily_message()


class TestSchedulerGetDefaultMessage:
    @patch('cogs.scheduler.AsyncIOScheduler')
    @patch('cogs.scheduler.db')
    def test_returns_string(self, mock_db, mock_sched_cls):
        from cogs.scheduler import ScheduledMessages
        mock_sched_cls.return_value = MagicMock()
        cog = ScheduledMessages(_make_bot())
        msg = cog.get_default_daily_message()
        assert isinstance(msg, str)
        assert len(msg) > 0


class TestSchedulerCheckScheduledMessages:
    @patch('cogs.scheduler.AsyncIOScheduler')
    @patch('cogs.scheduler.db')
    @pytest.mark.asyncio
    async def test_noop(self, mock_db, mock_sched_cls):
        from cogs.scheduler import ScheduledMessages
        mock_sched_cls.return_value = MagicMock()
        cog = ScheduledMessages(_make_bot())
        result = await cog.check_scheduled_messages()
        assert result is None


class TestSchedulerScheduleGroup:
    @patch('cogs.scheduler.AsyncIOScheduler')
    @patch('cogs.scheduler.db')
    @pytest.mark.asyncio
    async def test_no_subcommand(self, mock_db, mock_sched_cls):
        from cogs.scheduler import ScheduledMessages
        mock_sched_cls.return_value = MagicMock()
        cog = ScheduledMessages(_make_bot())
        ctx = _make_ctx()
        ctx.invoked_subcommand = None
        await cog.schedule.callback(cog, ctx)
        ctx.send_help.assert_called_once()

    @patch('cogs.scheduler.AsyncIOScheduler')
    @patch('cogs.scheduler.db')
    @pytest.mark.asyncio
    async def test_with_subcommand(self, mock_db, mock_sched_cls):
        from cogs.scheduler import ScheduledMessages
        mock_sched_cls.return_value = MagicMock()
        cog = ScheduledMessages(_make_bot())
        ctx = _make_ctx()
        ctx.invoked_subcommand = MagicMock()
        await cog.schedule.callback(cog, ctx)
        ctx.send_help.assert_not_called()


class TestSchedulerDaily:
    @patch('cogs.scheduler.AsyncIOScheduler')
    @patch('cogs.scheduler.db')
    @pytest.mark.asyncio
    async def test_schedule_daily(self, mock_db, mock_sched_cls):
        from cogs.scheduler import ScheduledMessages
        mock_sched_cls.return_value = MagicMock()
        cog = ScheduledMessages(_make_bot())
        ctx = _make_ctx()
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 500
        channel.mention = "#daily"
        mock_db.update_guild_config = AsyncMock()
        await cog.schedule_daily.callback(cog, ctx, channel)
        mock_db.update_guild_config.assert_awaited_once_with(123, daily_channel_id=500)
        embed = ctx.send.call_args[1]['embed']
        assert "#daily" in embed.description


class TestSchedulerMessage:
    @patch('cogs.scheduler.AsyncIOScheduler')
    @patch('cogs.scheduler.db')
    @pytest.mark.asyncio
    async def test_schedule_message(self, mock_db, mock_sched_cls):
        from cogs.scheduler import ScheduledMessages
        mock_sched_cls.return_value = MagicMock()
        cog = ScheduledMessages(_make_bot())
        ctx = _make_ctx()
        mock_db.update_guild_config = AsyncMock()
        await cog.schedule_message.callback(cog, ctx, message="Hello everyone!")
        mock_db.update_guild_config.assert_awaited_once()
        embed = ctx.send.call_args[1]['embed']
        assert "Hello everyone!" in embed.description


class TestSchedulerTest:
    @patch('cogs.scheduler.AsyncIOScheduler')
    @patch('cogs.scheduler.db')
    @pytest.mark.asyncio
    async def test_schedule_test_default(self, mock_db, mock_sched_cls):
        from cogs.scheduler import ScheduledMessages
        mock_sched_cls.return_value = MagicMock()
        cog = ScheduledMessages(_make_bot())
        ctx = _make_ctx()
        mock_db.get_guild_config = AsyncMock(return_value={'daily_message': None})
        await cog.schedule_test.callback(cog, ctx)
        ctx.send.assert_called_once()

    @patch('cogs.scheduler.AsyncIOScheduler')
    @patch('cogs.scheduler.db')
    @pytest.mark.asyncio
    async def test_schedule_test_custom(self, mock_db, mock_sched_cls):
        from cogs.scheduler import ScheduledMessages
        mock_sched_cls.return_value = MagicMock()
        cog = ScheduledMessages(_make_bot())
        ctx = _make_ctx()
        mock_db.get_guild_config = AsyncMock(return_value={'daily_message': 'Custom!'})
        await cog.schedule_test.callback(cog, ctx)
        embed = ctx.send.call_args[1]['embed']
        assert "Custom!" in embed.description


class TestSchedulerAnnounce:
    @patch('cogs.scheduler.AsyncIOScheduler')
    @patch('cogs.scheduler.db')
    @pytest.mark.asyncio
    async def test_announce_valid(self, mock_db, mock_sched_cls):
        from cogs.scheduler import ScheduledMessages
        mock_sched = MagicMock()
        mock_sched_cls.return_value = mock_sched
        cog = ScheduledMessages(_make_bot())
        ctx = _make_ctx()
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 500
        channel.mention = "#ann"
        await cog.schedule_announce.callback(cog, ctx, channel, "23:59", message="Test announcement")
        mock_sched.add_job.assert_called_once()
        embed = ctx.send.call_args[1]['embed']
        assert "#ann" in embed.description

    @patch('cogs.scheduler.AsyncIOScheduler')
    @patch('cogs.scheduler.db')
    @pytest.mark.asyncio
    async def test_announce_invalid_format(self, mock_db, mock_sched_cls):
        from cogs.scheduler import ScheduledMessages
        mock_sched_cls.return_value = MagicMock()
        cog = ScheduledMessages(_make_bot())
        ctx = _make_ctx()
        channel = MagicMock(spec=discord.TextChannel)
        await cog.schedule_announce.callback(cog, ctx, channel, "abc", message="Test")
        assert "invalide" in ctx.send.call_args[0][0].lower()

    @patch('cogs.scheduler.AsyncIOScheduler')
    @patch('cogs.scheduler.db')
    @pytest.mark.asyncio
    async def test_announce_hour_out_of_range(self, mock_db, mock_sched_cls):
        from cogs.scheduler import ScheduledMessages
        mock_sched_cls.return_value = MagicMock()
        cog = ScheduledMessages(_make_bot())
        ctx = _make_ctx()
        channel = MagicMock(spec=discord.TextChannel)
        await cog.schedule_announce.callback(cog, ctx, channel, "25:00", message="Test")
        assert "invalide" in ctx.send.call_args[0][0].lower()

    @patch('cogs.scheduler.AsyncIOScheduler')
    @patch('cogs.scheduler.db')
    @pytest.mark.asyncio
    async def test_announce_long_message_truncated(self, mock_db, mock_sched_cls):
        from cogs.scheduler import ScheduledMessages
        mock_sched = MagicMock()
        mock_sched_cls.return_value = mock_sched
        cog = ScheduledMessages(_make_bot())
        ctx = _make_ctx()
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 500
        channel.mention = "#ann"
        long_msg = "A" * 300
        await cog.schedule_announce.callback(cog, ctx, channel, "12:00", message=long_msg)
        embed = ctx.send.call_args[1]['embed']
        msg_field = [f for f in embed.fields if f.name == "Message"][0]
        assert msg_field.value.endswith("...")


class TestSchedulerSendAnnouncement:
    @patch('cogs.scheduler.AsyncIOScheduler')
    @patch('cogs.scheduler.db')
    @pytest.mark.asyncio
    async def test_channel_exists(self, mock_db, mock_sched_cls):
        from cogs.scheduler import ScheduledMessages
        mock_sched_cls.return_value = MagicMock()
        bot = _make_bot()
        channel = MagicMock()
        channel.send = AsyncMock()
        bot.get_channel = MagicMock(return_value=channel)
        cog = ScheduledMessages(bot)
        await cog.send_scheduled_announcement(500, "Hello!")
        channel.send.assert_awaited_once()

    @patch('cogs.scheduler.AsyncIOScheduler')
    @patch('cogs.scheduler.db')
    @pytest.mark.asyncio
    async def test_channel_not_found(self, mock_db, mock_sched_cls):
        from cogs.scheduler import ScheduledMessages
        mock_sched_cls.return_value = MagicMock()
        bot = _make_bot()
        bot.get_channel = MagicMock(return_value=None)
        cog = ScheduledMessages(bot)
        await cog.send_scheduled_announcement(500, "Hello!")


class TestSchedulerRecurring:
    @patch('cogs.scheduler.AsyncIOScheduler')
    @patch('cogs.scheduler.db')
    @pytest.mark.asyncio
    async def test_recurring_valid(self, mock_db, mock_sched_cls):
        from cogs.scheduler import ScheduledMessages
        mock_sched = MagicMock()
        mock_sched_cls.return_value = mock_sched
        cog = ScheduledMessages(_make_bot())
        ctx = _make_ctx()
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 500
        channel.mention = "#ch"
        await cog.schedule_recurring.callback(cog, ctx, channel, "lun,mer,ven", "14:30", message="Recurring!")
        mock_sched.add_job.assert_called_once()
        embed = ctx.send.call_args[1]['embed']
        assert "#ch" in embed.description

    @patch('cogs.scheduler.AsyncIOScheduler')
    @patch('cogs.scheduler.db')
    @pytest.mark.asyncio
    async def test_recurring_wildcard(self, mock_db, mock_sched_cls):
        from cogs.scheduler import ScheduledMessages
        mock_sched = MagicMock()
        mock_sched_cls.return_value = mock_sched
        cog = ScheduledMessages(_make_bot())
        ctx = _make_ctx()
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 500
        channel.mention = "#ch"
        await cog.schedule_recurring.callback(cog, ctx, channel, "*", "08:00", message="Daily!")
        mock_sched.add_job.assert_called_once()

    @patch('cogs.scheduler.AsyncIOScheduler')
    @patch('cogs.scheduler.db')
    @pytest.mark.asyncio
    async def test_recurring_invalid_time(self, mock_db, mock_sched_cls):
        from cogs.scheduler import ScheduledMessages
        mock_sched_cls.return_value = MagicMock()
        cog = ScheduledMessages(_make_bot())
        ctx = _make_ctx()
        channel = MagicMock(spec=discord.TextChannel)
        await cog.schedule_recurring.callback(cog, ctx, channel, "lun", "bad", message="Test")
        assert "invalide" in ctx.send.call_args[0][0].lower()

    @patch('cogs.scheduler.AsyncIOScheduler')
    @patch('cogs.scheduler.db')
    @pytest.mark.asyncio
    async def test_recurring_invalid_day(self, mock_db, mock_sched_cls):
        from cogs.scheduler import ScheduledMessages
        mock_sched_cls.return_value = MagicMock()
        cog = ScheduledMessages(_make_bot())
        ctx = _make_ctx()
        channel = MagicMock(spec=discord.TextChannel)
        await cog.schedule_recurring.callback(cog, ctx, channel, "xyz", "12:00", message="Test")
        assert "invalide" in ctx.send.call_args[0][0].lower()

    @patch('cogs.scheduler.AsyncIOScheduler')
    @patch('cogs.scheduler.db')
    @pytest.mark.asyncio
    async def test_recurring_long_message_truncated(self, mock_db, mock_sched_cls):
        from cogs.scheduler import ScheduledMessages
        mock_sched = MagicMock()
        mock_sched_cls.return_value = mock_sched
        cog = ScheduledMessages(_make_bot())
        ctx = _make_ctx()
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 500
        channel.mention = "#ch"
        long_msg = "B" * 300
        await cog.schedule_recurring.callback(cog, ctx, channel, "lun", "10:00", message=long_msg)
        embed = ctx.send.call_args[1]['embed']
        msg_field = [f for f in embed.fields if f.name == "Message"][0]
        assert msg_field.value.endswith("...")


class TestSchedulerList:
    @patch('cogs.scheduler.AsyncIOScheduler')
    @patch('cogs.scheduler.db')
    @pytest.mark.asyncio
    async def test_list_with_jobs(self, mock_db, mock_sched_cls):
        from cogs.scheduler import ScheduledMessages
        mock_sched = MagicMock()
        mock_sched_cls.return_value = mock_sched
        job = MagicMock()
        job.id = "daily_morning_message"
        job.next_run_time = datetime(2026, 1, 1, 9, 0)
        mock_sched.get_jobs.return_value = [job]
        cog = ScheduledMessages(_make_bot())
        ctx = _make_ctx()
        await cog.schedule_list.callback(cog, ctx)
        embed = ctx.send.call_args[1]['embed']
        assert len(embed.fields) == 1

    @patch('cogs.scheduler.AsyncIOScheduler')
    @patch('cogs.scheduler.db')
    @pytest.mark.asyncio
    async def test_list_empty(self, mock_db, mock_sched_cls):
        from cogs.scheduler import ScheduledMessages
        mock_sched = MagicMock()
        mock_sched_cls.return_value = mock_sched
        mock_sched.get_jobs.return_value = []
        cog = ScheduledMessages(_make_bot())
        ctx = _make_ctx()
        await cog.schedule_list.callback(cog, ctx)
        embed = ctx.send.call_args[1]['embed']
        assert "Aucun" in embed.description

    @patch('cogs.scheduler.AsyncIOScheduler')
    @patch('cogs.scheduler.db')
    @pytest.mark.asyncio
    async def test_list_filters_by_guild(self, mock_db, mock_sched_cls):
        from cogs.scheduler import ScheduledMessages
        mock_sched = MagicMock()
        mock_sched_cls.return_value = mock_sched
        job1 = MagicMock()
        job1.id = "announce_123_1234"
        job1.next_run_time = datetime(2026, 1, 1, 12, 0)
        job2 = MagicMock()
        job2.id = "announce_999_5678"
        job2.next_run_time = datetime(2026, 1, 1, 12, 0)
        mock_sched.get_jobs.return_value = [job1, job2]
        cog = ScheduledMessages(_make_bot())
        ctx = _make_ctx()
        await cog.schedule_list.callback(cog, ctx)
        embed = ctx.send.call_args[1]['embed']
        assert len(embed.fields) == 1

    @patch('cogs.scheduler.AsyncIOScheduler')
    @patch('cogs.scheduler.db')
    @pytest.mark.asyncio
    async def test_list_job_no_next_run(self, mock_db, mock_sched_cls):
        from cogs.scheduler import ScheduledMessages
        mock_sched = MagicMock()
        mock_sched_cls.return_value = mock_sched
        job = MagicMock()
        job.id = "daily_morning_message"
        job.next_run_time = None
        mock_sched.get_jobs.return_value = [job]
        cog = ScheduledMessages(_make_bot())
        ctx = _make_ctx()
        await cog.schedule_list.callback(cog, ctx)
        embed = ctx.send.call_args[1]['embed']
        assert "N/A" in embed.fields[0].value


class TestSchedulerCancel:
    @patch('cogs.scheduler.AsyncIOScheduler')
    @patch('cogs.scheduler.db')
    @pytest.mark.asyncio
    async def test_cancel_success(self, mock_db, mock_sched_cls):
        from cogs.scheduler import ScheduledMessages
        mock_sched = MagicMock()
        mock_sched_cls.return_value = mock_sched
        cog = ScheduledMessages(_make_bot())
        ctx = _make_ctx()
        await cog.schedule_cancel.callback(cog, ctx, "some_job_id")
        mock_sched.remove_job.assert_called_once_with("some_job_id")
        embed = ctx.send.call_args[1]['embed']
        assert "annulé" in embed.description

    @patch('cogs.scheduler.AsyncIOScheduler')
    @patch('cogs.scheduler.db')
    @pytest.mark.asyncio
    async def test_cancel_not_found(self, mock_db, mock_sched_cls):
        from cogs.scheduler import ScheduledMessages
        mock_sched = MagicMock()
        mock_sched.remove_job.side_effect = Exception("not found")
        mock_sched_cls.return_value = mock_sched
        cog = ScheduledMessages(_make_bot())
        ctx = _make_ctx()
        await cog.schedule_cancel.callback(cog, ctx, "bad_id")
        embed = ctx.send.call_args[1]['embed']
        assert "Impossible" in embed.description


class TestSchedulerSetup:
    @patch('cogs.scheduler.AsyncIOScheduler')
    @patch('cogs.scheduler.db')
    @pytest.mark.asyncio
    async def test_setup(self, mock_db, mock_sched_cls):
        from cogs.scheduler import setup
        mock_sched_cls.return_value = MagicMock()
        bot = _make_bot()
        bot.add_cog = AsyncMock()
        await setup(bot)
        bot.add_cog.assert_awaited_once()


# ============================================================================
# WELCOME COG
# ============================================================================

class TestWelcomeInit:
    @patch('cogs.welcome.AsyncIOScheduler')
    @patch('cogs.welcome.db')
    def test_init(self, mock_db, mock_sched_cls):
        from cogs.welcome import Welcome
        mock_sched = MagicMock()
        mock_sched_cls.return_value = mock_sched
        bot = _make_bot()
        cog = Welcome(bot)
        assert cog.bot is bot
        assert cog.scheduler is mock_sched


class TestWelcomeCogLoad:
    @patch('cogs.welcome.AsyncIOScheduler')
    @patch('cogs.welcome.db')
    @pytest.mark.asyncio
    async def test_cog_load(self, mock_db, mock_sched_cls):
        from cogs.welcome import Welcome
        mock_sched = MagicMock()
        mock_sched_cls.return_value = mock_sched
        cog = Welcome(_make_bot())
        await cog.cog_load()
        mock_sched.add_job.assert_called_once()
        mock_sched.start.assert_called_once()


class TestWelcomeCogUnload:
    @patch('cogs.welcome.AsyncIOScheduler')
    @patch('cogs.welcome.db')
    @pytest.mark.asyncio
    async def test_cog_unload(self, mock_db, mock_sched_cls):
        from cogs.welcome import Welcome
        mock_sched = MagicMock()
        mock_sched_cls.return_value = mock_sched
        cog = Welcome(_make_bot())
        await cog.cog_unload()
        mock_sched.shutdown.assert_called_once()


class TestWelcomeSendDailyMessage:
    @patch('cogs.welcome.AsyncIOScheduler')
    @patch('cogs.welcome.db')
    @pytest.mark.asyncio
    async def test_daily_with_channel(self, mock_db, mock_sched_cls):
        from cogs.welcome import Welcome
        mock_sched_cls.return_value = MagicMock()
        bot = _make_bot()
        channel = MagicMock()
        channel.send = AsyncMock()
        guild = MagicMock()
        guild.id = 1
        guild.get_channel = MagicMock(return_value=channel)
        bot.guilds = [guild]
        mock_db.get_guild_config = AsyncMock(return_value={'welcome_channel_id': 100})
        cog = Welcome(bot)
        await cog.send_daily_message()
        channel.send.assert_awaited_once()

    @patch('cogs.welcome.AsyncIOScheduler')
    @patch('cogs.welcome.db')
    @pytest.mark.asyncio
    async def test_daily_no_channel(self, mock_db, mock_sched_cls):
        from cogs.welcome import Welcome
        mock_sched_cls.return_value = MagicMock()
        bot = _make_bot()
        guild = MagicMock()
        guild.id = 1
        guild.get_channel = MagicMock(return_value=None)
        bot.guilds = [guild]
        mock_db.get_guild_config = AsyncMock(return_value={'welcome_channel_id': 100})
        cog = Welcome(bot)
        await cog.send_daily_message()

    @patch('cogs.welcome.AsyncIOScheduler')
    @patch('cogs.welcome.db')
    @pytest.mark.asyncio
    async def test_daily_forbidden(self, mock_db, mock_sched_cls):
        from cogs.welcome import Welcome
        mock_sched_cls.return_value = MagicMock()
        bot = _make_bot()
        channel = MagicMock()
        channel.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "no perms"))
        guild = MagicMock()
        guild.id = 1
        guild.get_channel = MagicMock(return_value=channel)
        bot.guilds = [guild]
        mock_db.get_guild_config = AsyncMock(return_value={'welcome_channel_id': 100})
        cog = Welcome(bot)
        await cog.send_daily_message()

    @patch('cogs.welcome.AsyncIOScheduler')
    @patch('cogs.welcome.db')
    @pytest.mark.asyncio
    async def test_daily_fallback_default_channel(self, mock_db, mock_sched_cls):
        from cogs.welcome import Welcome
        mock_sched_cls.return_value = MagicMock()
        bot = _make_bot()
        channel = MagicMock()
        channel.send = AsyncMock()
        guild = MagicMock()
        guild.id = 1
        guild.get_channel = MagicMock(return_value=channel)
        bot.guilds = [guild]
        mock_db.get_guild_config = AsyncMock(return_value={'welcome_channel_id': None})
        cog = Welcome(bot)
        await cog.send_daily_message()
        channel.send.assert_awaited_once()


class TestWelcomeOnMemberJoin:
    @patch('cogs.welcome.AsyncIOScheduler')
    @patch('cogs.welcome.db')
    @pytest.mark.asyncio
    async def test_skips_bot(self, mock_db, mock_sched_cls):
        from cogs.welcome import Welcome
        mock_sched_cls.return_value = MagicMock()
        cog = Welcome(_make_bot())
        member = MagicMock(spec=discord.Member)
        member.bot = True
        await cog.on_member_join(member)
        mock_db.get_guild_config.assert_not_called()

    @patch('cogs.welcome.AsyncIOScheduler')
    @patch('cogs.welcome.db')
    @pytest.mark.asyncio
    async def test_no_welcome_channel(self, mock_db, mock_sched_cls):
        from cogs.welcome import Welcome
        mock_sched_cls.return_value = MagicMock()
        cog = Welcome(_make_bot())
        member = MagicMock(spec=discord.Member)
        member.bot = False
        member.guild = MagicMock(spec=discord.Guild)
        member.guild.id = 1
        mock_db.get_guild_config = AsyncMock(return_value={'welcome_channel_id': None})
        await cog.on_member_join(member)

    @patch('cogs.welcome.AsyncIOScheduler')
    @patch('cogs.welcome.db')
    @pytest.mark.asyncio
    async def test_channel_not_found(self, mock_db, mock_sched_cls):
        from cogs.welcome import Welcome
        mock_sched_cls.return_value = MagicMock()
        cog = Welcome(_make_bot())
        member = MagicMock(spec=discord.Member)
        member.bot = False
        member.guild = MagicMock(spec=discord.Guild)
        member.guild.id = 1
        member.guild.get_channel = MagicMock(return_value=None)
        mock_db.get_guild_config = AsyncMock(return_value={'welcome_channel_id': 100})
        await cog.on_member_join(member)

    @patch('cogs.welcome.AsyncIOScheduler')
    @patch('cogs.welcome.db')
    @pytest.mark.asyncio
    async def test_success(self, mock_db, mock_sched_cls):
        from cogs.welcome import Welcome
        mock_sched_cls.return_value = MagicMock()
        cog = Welcome(_make_bot())
        channel = MagicMock()
        channel.send = AsyncMock()
        member = MagicMock(spec=discord.Member)
        member.bot = False
        member.id = 10
        member.mention = "<@10>"
        member.display_avatar = MagicMock()
        member.display_avatar.url = "http://img"
        member.send = AsyncMock()
        member.guild = MagicMock(spec=discord.Guild)
        member.guild.id = 1
        member.guild.name = "G"
        member.guild.member_count = 50
        member.guild.get_channel = MagicMock(return_value=channel)
        member.guild.icon = MagicMock()
        member.guild.icon.url = "http://icon"
        mock_db.get_guild_config = AsyncMock(return_value={'welcome_channel_id': 100})
        await cog.on_member_join(member)
        channel.send.assert_awaited_once()
        member.send.assert_awaited_once()

    @patch('cogs.welcome.AsyncIOScheduler')
    @patch('cogs.welcome.db')
    @pytest.mark.asyncio
    async def test_dm_forbidden(self, mock_db, mock_sched_cls):
        from cogs.welcome import Welcome
        mock_sched_cls.return_value = MagicMock()
        cog = Welcome(_make_bot())
        channel = MagicMock()
        channel.send = AsyncMock()
        member = MagicMock(spec=discord.Member)
        member.bot = False
        member.id = 10
        member.mention = "<@10>"
        member.display_avatar = MagicMock()
        member.display_avatar.url = "http://img"
        member.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "dm disabled"))
        member.guild = MagicMock(spec=discord.Guild)
        member.guild.id = 1
        member.guild.name = "G"
        member.guild.member_count = 50
        member.guild.get_channel = MagicMock(return_value=channel)
        member.guild.icon = MagicMock()
        member.guild.icon.url = "http://icon"
        mock_db.get_guild_config = AsyncMock(return_value={'welcome_channel_id': 100})
        await cog.on_member_join(member)
        channel.send.assert_awaited_once()

    @patch('cogs.welcome.AsyncIOScheduler')
    @patch('cogs.welcome.db')
    @pytest.mark.asyncio
    async def test_channel_send_forbidden(self, mock_db, mock_sched_cls):
        from cogs.welcome import Welcome
        mock_sched_cls.return_value = MagicMock()
        cog = Welcome(_make_bot())
        channel = MagicMock()
        channel.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "no perms"))
        member = MagicMock(spec=discord.Member)
        member.bot = False
        member.id = 10
        member.mention = "<@10>"
        member.display_avatar = MagicMock()
        member.display_avatar.url = "http://img"
        member.send = AsyncMock()
        member.guild = MagicMock(spec=discord.Guild)
        member.guild.id = 1
        member.guild.name = "G"
        member.guild.member_count = 50
        member.guild.get_channel = MagicMock(return_value=channel)
        member.guild.icon = MagicMock()
        member.guild.icon.url = "http://icon"
        mock_db.get_guild_config = AsyncMock(return_value={'welcome_channel_id': 100})
        await cog.on_member_join(member)

    @patch('cogs.welcome.AsyncIOScheduler')
    @patch('cogs.welcome.db')
    @pytest.mark.asyncio
    async def test_custom_welcome_message(self, mock_db, mock_sched_cls):
        from cogs.welcome import Welcome
        mock_sched_cls.return_value = MagicMock()
        cog = Welcome(_make_bot())
        channel = MagicMock()
        channel.send = AsyncMock()
        member = MagicMock(spec=discord.Member)
        member.bot = False
        member.id = 10
        member.mention = "<@10>"
        member.display_avatar = MagicMock()
        member.display_avatar.url = "http://img"
        member.send = AsyncMock()
        member.guild = MagicMock(spec=discord.Guild)
        member.guild.id = 1
        member.guild.name = "TestGuild"
        member.guild.member_count = 50
        member.guild.get_channel = MagicMock(return_value=channel)
        member.guild.icon = MagicMock()
        member.guild.icon.url = "http://icon"
        mock_db.get_guild_config = AsyncMock(return_value={
            'welcome_channel_id': 100,
            'welcome_message': 'Hey {user}! Welcome to {server}! #{member_count}'
        })
        await cog.on_member_join(member)
        embed = channel.send.call_args[1]['embed']
        assert "<@10>" in embed.description
        assert "TestGuild" in embed.description
        assert "50" in embed.description

    @patch('cogs.welcome.AsyncIOScheduler')
    @patch('cogs.welcome.db')
    @pytest.mark.asyncio
    async def test_guild_no_icon(self, mock_db, mock_sched_cls):
        from cogs.welcome import Welcome
        mock_sched_cls.return_value = MagicMock()
        cog = Welcome(_make_bot())
        channel = MagicMock()
        channel.send = AsyncMock()
        member = MagicMock(spec=discord.Member)
        member.bot = False
        member.id = 10
        member.mention = "<@10>"
        member.display_avatar = MagicMock()
        member.display_avatar.url = "http://img"
        member.send = AsyncMock()
        member.guild = MagicMock(spec=discord.Guild)
        member.guild.id = 1
        member.guild.name = "G"
        member.guild.member_count = 50
        member.guild.get_channel = MagicMock(return_value=channel)
        member.guild.icon = None
        mock_db.get_guild_config = AsyncMock(return_value={'welcome_channel_id': 100})
        await cog.on_member_join(member)
        channel.send.assert_awaited_once()


class TestWelcomeOnMemberRemove:
    @patch('cogs.welcome.AsyncIOScheduler')
    @patch('cogs.welcome.db')
    @pytest.mark.asyncio
    async def test_skips_bot(self, mock_db, mock_sched_cls):
        from cogs.welcome import Welcome
        mock_sched_cls.return_value = MagicMock()
        cog = Welcome(_make_bot())
        member = MagicMock(spec=discord.Member)
        member.bot = True
        await cog.on_member_remove(member)
        mock_db.get_guild_config.assert_not_called()

    @patch('cogs.welcome.AsyncIOScheduler')
    @patch('cogs.welcome.db')
    @pytest.mark.asyncio
    async def test_no_welcome_channel(self, mock_db, mock_sched_cls):
        from cogs.welcome import Welcome
        mock_sched_cls.return_value = MagicMock()
        cog = Welcome(_make_bot())
        member = MagicMock(spec=discord.Member)
        member.bot = False
        member.guild = MagicMock(spec=discord.Guild)
        member.guild.id = 1
        mock_db.get_guild_config = AsyncMock(return_value={'welcome_channel_id': None})
        await cog.on_member_remove(member)

    @patch('cogs.welcome.AsyncIOScheduler')
    @patch('cogs.welcome.db')
    @pytest.mark.asyncio
    async def test_channel_not_found(self, mock_db, mock_sched_cls):
        from cogs.welcome import Welcome
        mock_sched_cls.return_value = MagicMock()
        cog = Welcome(_make_bot())
        member = MagicMock(spec=discord.Member)
        member.bot = False
        member.guild = MagicMock(spec=discord.Guild)
        member.guild.id = 1
        member.guild.get_channel = MagicMock(return_value=None)
        mock_db.get_guild_config = AsyncMock(return_value={'welcome_channel_id': 100})
        await cog.on_member_remove(member)

    @patch('cogs.welcome.AsyncIOScheduler')
    @patch('cogs.welcome.db')
    @pytest.mark.asyncio
    async def test_success(self, mock_db, mock_sched_cls):
        from cogs.welcome import Welcome
        mock_sched_cls.return_value = MagicMock()
        cog = Welcome(_make_bot())
        channel = MagicMock()
        channel.send = AsyncMock()
        member = MagicMock(spec=discord.Member)
        member.bot = False
        member.__str__ = MagicMock(return_value="Tester#1234")
        member.display_avatar = MagicMock()
        member.display_avatar.url = "http://img"
        member.guild = MagicMock(spec=discord.Guild)
        member.guild.id = 1
        member.guild.name = "G"
        member.guild.get_channel = MagicMock(return_value=channel)
        mock_db.get_guild_config = AsyncMock(return_value={'welcome_channel_id': 100})
        await cog.on_member_remove(member)
        channel.send.assert_awaited_once()

    @patch('cogs.welcome.AsyncIOScheduler')
    @patch('cogs.welcome.db')
    @pytest.mark.asyncio
    async def test_forbidden(self, mock_db, mock_sched_cls):
        from cogs.welcome import Welcome
        mock_sched_cls.return_value = MagicMock()
        cog = Welcome(_make_bot())
        channel = MagicMock()
        channel.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "no perms"))
        member = MagicMock(spec=discord.Member)
        member.bot = False
        member.__str__ = MagicMock(return_value="Tester#1234")
        member.display_avatar = MagicMock()
        member.display_avatar.url = "http://img"
        member.guild = MagicMock(spec=discord.Guild)
        member.guild.id = 1
        member.guild.name = "G"
        member.guild.get_channel = MagicMock(return_value=channel)
        mock_db.get_guild_config = AsyncMock(return_value={'welcome_channel_id': 100})
        await cog.on_member_remove(member)

    @patch('cogs.welcome.AsyncIOScheduler')
    @patch('cogs.welcome.db')
    @pytest.mark.asyncio
    async def test_custom_goodbye(self, mock_db, mock_sched_cls):
        from cogs.welcome import Welcome
        mock_sched_cls.return_value = MagicMock()
        cog = Welcome(_make_bot())
        channel = MagicMock()
        channel.send = AsyncMock()
        member = MagicMock(spec=discord.Member)
        member.bot = False
        member.__str__ = MagicMock(return_value="Tester#1234")
        member.display_avatar = MagicMock()
        member.display_avatar.url = "http://img"
        member.guild = MagicMock(spec=discord.Guild)
        member.guild.id = 1
        member.guild.name = "TestGuild"
        member.guild.get_channel = MagicMock(return_value=channel)
        mock_db.get_guild_config = AsyncMock(return_value={
            'welcome_channel_id': 100,
            'goodbye_message': 'Bye {user} from {server}!'
        })
        await cog.on_member_remove(member)
        embed = channel.send.call_args[1]['embed']
        assert "Tester#1234" in embed.description
        assert "TestGuild" in embed.description


class TestWelcomeSetWelcome:
    @patch('cogs.welcome.AsyncIOScheduler')
    @patch('cogs.welcome.db')
    @pytest.mark.asyncio
    async def test_setwelcome(self, mock_db, mock_sched_cls):
        from cogs.welcome import Welcome
        mock_sched_cls.return_value = MagicMock()
        cog = Welcome(_make_bot())
        ctx = _make_ctx()
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 600
        channel.mention = "#welcome"
        mock_db.update_guild_config = AsyncMock()
        await cog.setwelcome.callback(cog, ctx, channel)
        mock_db.update_guild_config.assert_awaited_once_with(123, welcome_channel_id=600)
        embed = ctx.send.call_args[1]['embed']
        assert "#welcome" in embed.description


class TestWelcomeSetWelcomeMsg:
    @patch('cogs.welcome.AsyncIOScheduler')
    @patch('cogs.welcome.db')
    @pytest.mark.asyncio
    async def test_setwelcomemsg(self, mock_db, mock_sched_cls):
        from cogs.welcome import Welcome
        mock_sched_cls.return_value = MagicMock()
        cog = Welcome(_make_bot())
        ctx = _make_ctx()
        mock_db.update_guild_config = AsyncMock()
        await cog.setwelcomemsg.callback(cog, ctx, message="Hi {user} on {server}! #{member_count}")
        mock_db.update_guild_config.assert_awaited_once()
        embed = ctx.send.call_args[1]['embed']
        assert "<@456>" in embed.description
        assert "Test Server" in embed.description
        assert "42" in embed.description


class TestWelcomeSetGoodbyeMsg:
    @patch('cogs.welcome.AsyncIOScheduler')
    @patch('cogs.welcome.db')
    @pytest.mark.asyncio
    async def test_setgoodbyemsg(self, mock_db, mock_sched_cls):
        from cogs.welcome import Welcome
        mock_sched_cls.return_value = MagicMock()
        cog = Welcome(_make_bot())
        ctx = _make_ctx()
        mock_db.update_guild_config = AsyncMock()
        await cog.setgoodbyemsg.callback(cog, ctx, message="Bye {user} from {server}")
        mock_db.update_guild_config.assert_awaited_once()
        embed = ctx.send.call_args[1]['embed']
        assert "Test Server" in embed.description


class TestWelcomeTestWelcome:
    @patch('cogs.welcome.AsyncIOScheduler')
    @patch('cogs.welcome.db')
    @pytest.mark.asyncio
    async def test_testwelcome_default(self, mock_db, mock_sched_cls):
        from cogs.welcome import Welcome
        mock_sched_cls.return_value = MagicMock()
        cog = Welcome(_make_bot())
        ctx = _make_ctx()
        mock_db.get_guild_config = AsyncMock(return_value={})
        await cog.testwelcome.callback(cog, ctx)
        embed = ctx.send.call_args[1]['embed']
        assert "[TEST]" in embed.title
        assert "<@456>" in embed.description

    @patch('cogs.welcome.AsyncIOScheduler')
    @patch('cogs.welcome.db')
    @pytest.mark.asyncio
    async def test_testwelcome_custom(self, mock_db, mock_sched_cls):
        from cogs.welcome import Welcome
        mock_sched_cls.return_value = MagicMock()
        cog = Welcome(_make_bot())
        ctx = _make_ctx()
        mock_db.get_guild_config = AsyncMock(return_value={
            'welcome_message': 'Yo {user} in {server}, member {member_count}!'
        })
        await cog.testwelcome.callback(cog, ctx)
        embed = ctx.send.call_args[1]['embed']
        assert "<@456>" in embed.description
        assert "Test Server" in embed.description
        assert "42" in embed.description


class TestWelcomeSetup:
    @patch('cogs.welcome.AsyncIOScheduler')
    @patch('cogs.welcome.db')
    @pytest.mark.asyncio
    async def test_setup(self, mock_db, mock_sched_cls):
        from cogs.welcome import setup
        mock_sched_cls.return_value = MagicMock()
        bot = _make_bot()
        bot.add_cog = AsyncMock()
        await setup(bot)
        bot.add_cog.assert_awaited_once()
