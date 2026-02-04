"""
Administration and configuration cog for the Discord bot.

Provides server administrators with commands to customize bot behavior on a
per-guild basis: setting the command prefix, configuring logging and level-up
channels, toggling auto-moderation and leveling systems, and customizing the
level-up notification message.

Also includes a comprehensive ``help`` command that lists all available
commands by category, a ``botinfo`` command showing global bot statistics,
an ``invite`` command generating an OAuth2 invitation link, and several
owner-only maintenance commands (``sync``, ``reload``, ``shutdown``).
"""
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from typing import Optional
import json

from config import Colors, Emojis, PREFIX
from utils.database import db


class Admin(commands.Cog):
    """Administration and configuration cog for per-guild bot settings.

    Groups server-configuration subcommands under the ``config`` hybrid
    command group and provides informational commands (``help``, ``botinfo``,
    ``invite``) as well as owner-only maintenance utilities.

    Attributes:
        bot: The bot instance this cog is attached to.
    """

    def __init__(self, bot: commands.Bot):
        """Initialize the Admin cog.

        Args:
            bot: The bot instance to bind this cog to.
        """
        self.bot = bot

    @commands.hybrid_group(name="config", aliases=["settings", "parametres"])
    @commands.has_permissions(administrator=True)
    async def config(self, ctx: commands.Context):
        """Server configuration command group (admin only).

        When invoked without a subcommand, displays the current guild
        configuration overview. Otherwise delegates to the specified
        subcommand.

        Args:
            ctx: The invocation context.
        """
        if ctx.invoked_subcommand is None:
            await self.show_config(ctx)

    async def show_config(self, ctx: commands.Context):
        """Display the current guild configuration as an embed.

        Shows configured channels (welcome, logs, level-up), feature
        toggles (auto-mod, leveling), and the current command prefix.

        Args:
            ctx: The invocation context.
        """
        config = await db.get_guild_config(ctx.guild.id)

        embed = discord.Embed(
            title=f"Configuration de {ctx.guild.name}",
            color=Colors.PRIMARY,
            timestamp=datetime.now()
        )

        # Resolve channel objects from stored IDs (defaulting to 0 for safe lookup)
        welcome_ch = ctx.guild.get_channel(config.get('welcome_channel_id') or 0)
        log_ch = ctx.guild.get_channel(config.get('log_channel_id') or 0)
        level_ch = ctx.guild.get_channel(config.get('level_up_channel_id') or 0)

        embed.add_field(
            name="Channels",
            value=f" Bienvenue: {welcome_ch.mention if welcome_ch else 'Non configuré'}\n"
                  f" Logs: {log_ch.mention if log_ch else 'Non configuré'}\n"
                  f" Level Up: {level_ch.mention if level_ch else 'Channel actuel'}",
            inline=False
        )

        # Feature toggle statuses
        embed.add_field(
            name="Fonctionnalités",
            value=f" Auto-Mod: {'Activé' if config.get('auto_mod_enabled', True) else 'Désactivé'}\n"
                  f" Leveling: {'Activé' if config.get('leveling_enabled', True) else 'Désactivé'}",
            inline=True
        )

        # Current command prefix
        embed.add_field(
            name="Préfixe",
            value=f"`{config.get('prefix', PREFIX)}`",
            inline=True
        )

        embed.set_footer(text="Utilisez !config <option> pour modifier")
        await ctx.send(embed=embed)

    @config.command(name="prefix")
    @app_commands.describe(prefix="Le nouveau préfixe")
    async def config_prefix(self, ctx: commands.Context, prefix: str):
        """Change the bot's command prefix for this server.

        The prefix is limited to a maximum of 5 characters to prevent abuse.

        Args:
            ctx: The invocation context.
            prefix: The new command prefix string (max 5 characters).
        """
        if len(prefix) > 5:
            return await ctx.send(f"{Emojis.ERROR} Le préfixe ne peut pas dépasser 5 caractères.")

        await db.update_guild_config(ctx.guild.id, prefix=prefix)

        embed = discord.Embed(
            title=f"{Emojis.SUCCESS} Préfixe modifié",
            description=f"Le nouveau préfixe est `{prefix}`",
            color=Colors.SUCCESS
        )
        await ctx.send(embed=embed)

    @config.command(name="logchannel")
    @app_commands.describe(channel="Le channel de logs")
    async def config_logchannel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set the channel where moderation and event logs are sent.

        Args:
            ctx: The invocation context.
            channel: The text channel to use for logging.
        """
        await db.update_guild_config(ctx.guild.id, log_channel_id=channel.id)

        embed = discord.Embed(
            title=f"{Emojis.SUCCESS} Channel de logs configuré",
            description=f"Les logs seront envoyés dans {channel.mention}",
            color=Colors.SUCCESS
        )
        await ctx.send(embed=embed)

    @config.command(name="levelchannel")
    @app_commands.describe(channel="Le channel pour les level up (laissez vide pour le channel actuel)")
    async def config_levelchannel(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Set the channel for level-up notifications.

        If no channel is provided, level-up messages will be sent in the
        same channel where the user earned the level (default behavior).

        Args:
            ctx: The invocation context.
            channel: The dedicated level-up notification channel, or ``None``
                to use the channel where the XP was earned.
        """
        channel_id = channel.id if channel else None
        await db.update_guild_config(ctx.guild.id, level_up_channel_id=channel_id)

        if channel:
            msg = f"Les notifications de level up seront envoyées dans {channel.mention}"
        else:
            msg = "Les notifications de level up seront envoyées dans le channel où l'utilisateur a gagné le niveau"

        embed = discord.Embed(
            title=f"{Emojis.SUCCESS} Channel de level up configuré",
            description=msg,
            color=Colors.SUCCESS
        )
        await ctx.send(embed=embed)

    @config.command(name="automod")
    @app_commands.describe(etat="Activer ou désactiver (on/off)")
    async def config_automod(self, ctx: commands.Context, etat: str):
        """Toggle the auto-moderation system on or off for this server.

        Accepts ``on``, ``off``, ``true``, ``false``, ``1``, or ``0`` as
        valid input values.

        Args:
            ctx: The invocation context.
            etat: The desired state (on/off/true/false/1/0).
        """
        if etat.lower() not in ['on', 'off', 'true', 'false', '1', '0']:
            return await ctx.send(f"{Emojis.ERROR} Utilisez: on/off")

        enabled = etat.lower() in ['on', 'true', '1']
        await db.update_guild_config(ctx.guild.id, auto_mod_enabled=1 if enabled else 0)

        embed = discord.Embed(
            title=f"{Emojis.SUCCESS} Auto-modération {'activée' if enabled else 'désactivée'}",
            color=Colors.SUCCESS
        )
        await ctx.send(embed=embed)

    @config.command(name="leveling")
    @app_commands.describe(etat="Activer ou désactiver (on/off)")
    async def config_leveling(self, ctx: commands.Context, etat: str):
        """Toggle the XP leveling system on or off for this server.

        Accepts ``on``, ``off``, ``true``, ``false``, ``1``, or ``0`` as
        valid input values.

        Args:
            ctx: The invocation context.
            etat: The desired state (on/off/true/false/1/0).
        """
        if etat.lower() not in ['on', 'off', 'true', 'false', '1', '0']:
            return await ctx.send(f"{Emojis.ERROR} Utilisez: on/off")

        enabled = etat.lower() in ['on', 'true', '1']
        await db.update_guild_config(ctx.guild.id, leveling_enabled=1 if enabled else 0)

        embed = discord.Embed(
            title=f"{Emojis.SUCCESS} Leveling {'activé' if enabled else 'désactivé'}",
            color=Colors.SUCCESS
        )
        await ctx.send(embed=embed)

    @config.command(name="levelupmsg")
    @app_commands.describe(message="Le message de level up ({user}, {level})")
    async def config_levelupmsg(self, ctx: commands.Context, *, message: str):
        """Set a custom level-up notification message template.

        Supports ``{user}`` (member mention) and ``{level}`` (new level
        number) placeholders. A preview is shown after saving, using level
        5 as an example.

        Args:
            ctx: The invocation context.
            message: The level-up message template string.
        """
        await db.update_guild_config(ctx.guild.id, level_up_message=message)

        # Generate a preview with placeholder substitution (level 5 as example)
        preview = message.replace('{user}', ctx.author.mention)
        preview = preview.replace('{level}', '5')

        embed = discord.Embed(
            title=f"{Emojis.SUCCESS} Message de level up configuré",
            description=f"**Aperçu:**\n{preview}",
            color=Colors.SUCCESS
        )
        embed.set_footer(text="Variables: {user}, {level}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="help", aliases=["aide", "commands"])
    @app_commands.describe(commande="La commande pour laquelle obtenir de l'aide")
    async def help_command(self, ctx: commands.Context, commande: Optional[str] = None):
        """Display bot help -- either a command overview or details for a specific command.

        When called without arguments, lists all commands grouped by category.
        When a command name is provided, shows that command's description,
        aliases, and usage signature.

        Args:
            ctx: The invocation context.
            commande: The name of a specific command to get help for.
                If ``None``, the full command list is displayed.
        """
        if commande:
            # Show detailed help for a specific command
            cmd = self.bot.get_command(commande)
            if not cmd:
                return await ctx.send(f"{Emojis.ERROR} Commande `{commande}` introuvable.")

            embed = discord.Embed(
                title=f"Aide: {cmd.name}",
                description=cmd.help or "Pas de description.",
                color=Colors.PRIMARY
            )

            if cmd.aliases:
                embed.add_field(name="Aliases", value=", ".join(f"`{a}`" for a in cmd.aliases))

            # Build the usage string from the command's parameter signature
            usage = f"{ctx.prefix}{cmd.name}"
            if cmd.signature:
                usage += f" {cmd.signature}"
            embed.add_field(name="Utilisation", value=f"`{usage}`", inline=False)

            await ctx.send(embed=embed)
            return

        # Show the full categorized command overview
        embed = discord.Embed(
            title=f"Aide - {self.bot.user.name}",
            description=f"Préfixe: `{ctx.prefix}` | Utilisez `{ctx.prefix}help <commande>` pour plus d'infos",
            color=Colors.PRIMARY
        )

        # Command categories with their associated command names
        categories = {
            " Leveling": ["rank", "leaderboard", "levelroles"],
            " Économie": ["daily", "balance", "richest", "give"],
            " Jeux": ["trivia", "roll", "coinflip", "8ball", "rps", "slot"],
            "️ Modération": ["ban", "kick", "mute", "unmute", "warn", "warnings", "purge", "slowmode", "lock", "unlock"],
            " Tickets": ["ticket setup", "ticket close", "ticket add", "ticket remove"],
            " Reaction Roles": ["reactionrole add", "reactionrole remove", "reactionrole list", "reactionrole create"],
            " Utilitaires": ["ping", "serverinfo", "userinfo", "avatar", "poll", "remind", "meme", "calc", "afk"],
            "️ Configuration": ["config", "setwelcome", "setwelcomemsg", "setgoodbyemsg"]
        }

        for category, cmds in categories.items():
            embed.add_field(
                name=category,
                value=", ".join(f"`{c}`" for c in cmds),
                inline=False
            )

        embed.set_footer(text=f"Bot créé avec discord.py | {len(self.bot.commands)} commandes")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="botinfo", aliases=["about", "info"])
    async def botinfo(self, ctx: commands.Context):
        """Display global bot statistics and feature list.

        Shows the number of guilds, total users, total channels, registered
        commands, current API latency, bot version, and a summary of the
        bot's main feature areas.

        Args:
            ctx: The invocation context.
        """
        embed = discord.Embed(
            title=f"À propos de {self.bot.user.name}",
            color=Colors.PRIMARY,
            timestamp=datetime.now()
        )

        embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        # Aggregate statistics across all guilds
        total_members = sum(g.member_count for g in self.bot.guilds)
        total_channels = sum(len(g.channels) for g in self.bot.guilds)

        embed.add_field(name="Serveurs", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="Utilisateurs", value=f"{total_members:,}", inline=True)
        embed.add_field(name="Channels", value=f"{total_channels:,}", inline=True)

        embed.add_field(name="Commandes", value=str(len(self.bot.commands)), inline=True)
        embed.add_field(name="Latence", value=f"{round(self.bot.latency * 1000)}ms", inline=True)
        embed.add_field(name="Version", value="2.0.0", inline=True)

        embed.add_field(
            name="Fonctionnalités",
            value=" Leveling & XP\n"
                  " Économie & Jeux\n"
                  "️ Modération avancée\n"
                  " Reaction Roles\n"
                  " Système de Tickets\n"
                  " Configuration personnalisable",
            inline=False
        )

        embed.set_footer(text="Développé avec discord.py")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="invite")
    async def invite(self, ctx: commands.Context):
        """Generate and display the bot's OAuth2 invitation link.

        Creates an invite URL with administrator permissions and both ``bot``
        and ``applications.commands`` OAuth2 scopes so slash commands are
        registered on the target guild.

        Args:
            ctx: The invocation context.
        """
        permissions = discord.Permissions(
            administrator=True  # Requests admin; could be narrowed to specific permissions
        )
        invite_url = discord.utils.oauth_url(
            self.bot.user.id,
            permissions=permissions,
            scopes=["bot", "applications.commands"]
        )

        embed = discord.Embed(
            title="Inviter le bot",
            description=f"[Cliquez ici pour m'inviter sur votre serveur!]({invite_url})",
            color=Colors.PRIMARY
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="sync")
    @commands.is_owner()
    async def sync(self, ctx: commands.Context):
        """[Owner only] Synchronize slash commands with the Discord API.

        Pushes the current application command tree to Discord so that new
        or updated slash commands become visible to users.

        Args:
            ctx: The invocation context.
        """
        await ctx.send(f"{Emojis.LOADING} Synchronisation en cours...")
        try:
            synced = await self.bot.tree.sync()
            await ctx.send(f"{Emojis.SUCCESS} {len(synced)} commandes synchronisées!")
        except Exception as e:
            await ctx.send(f"{Emojis.ERROR} Erreur: {e}")

    @commands.command(name="reload")
    @commands.is_owner()
    async def reload_cog(self, ctx: commands.Context, cog: str):
        """[Owner only] Hot-reload a cog extension without restarting the bot.

        Useful during development to apply code changes to a specific cog
        on the fly.

        Args:
            ctx: The invocation context.
            cog: The cog module name (e.g., ``"utility"``, ``"admin"``).
        """
        try:
            await self.bot.reload_extension(f"cogs.{cog}")
            await ctx.send(f"{Emojis.SUCCESS} Cog `{cog}` rechargé!")
        except Exception as e:
            await ctx.send(f"{Emojis.ERROR} Erreur: {e}")

    @commands.command(name="shutdown")
    @commands.is_owner()
    async def shutdown(self, ctx: commands.Context):
        """[Owner only] Gracefully shut down the bot.

        Sends a confirmation message and then closes the bot's connection
        to Discord, which terminates the process.

        Args:
            ctx: The invocation context.
        """
        await ctx.send(f"{Emojis.INFO} Arrêt du bot...")
        await self.bot.close()


async def setup(bot: commands.Bot):
    """Load the Admin cog into the bot.

    Args:
        bot: The bot instance to register the cog with.
    """
    await bot.add_cog(Admin(bot))
