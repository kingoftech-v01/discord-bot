"""
Professional Discord Bot - Main Entry Point.

This module serves as the primary entry point for the Discord bot application.
It defines the ``DiscordBot`` class (a subclass of ``commands.Bot``) which
orchestrates every aspect of the bot lifecycle: intent configuration, dynamic
command-prefix resolution, extension (cog) loading, event handling, and
centralised error management.

Architecture overview:
    main.py (this file)
        -> config.py          Central configuration loaded from .env
        -> utils/database.py  Async database helper (guild configs, user data)
        -> cogs/*             Feature modules (leveling, moderation, economy, ...)

Startup flow:
    1. ``main()`` ensures the ``data/`` directory exists, then creates a
       ``DiscordBot`` instance and calls ``bot.start(TOKEN)``.
    2. ``setup_hook()`` initialises the database and loads every cog listed in
       its internal registry.
    3. ``on_ready()`` logs connection details, sets the bot's presence, and
       synchronises slash commands with the Discord API.

Author: Discord Bot Pro
Version: 2.0.0
"""

import discord
from discord.ext import commands
import asyncio
import os
import logging
from datetime import datetime

from config import TOKEN, PREFIX, Colors
from utils.database import db

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
# Logs are written both to a file (bot.log) and to the console (stderr).
# UTF-8 encoding is used for the file handler so that non-ASCII characters
# (e.g. guild names with special characters) are handled correctly.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('discord_bot')


class DiscordBot(commands.Bot):
    """Main bot class that extends ``commands.Bot``.

    This class is responsible for:
        - Configuring Discord gateway intents so the bot receives the events
          it needs (messages, members, reactions, guilds).
        - Providing a per-guild dynamic command prefix via ``get_prefix``.
        - Loading all feature cogs during ``setup_hook``.
        - Handling lifecycle events (``on_ready``, ``on_guild_join``,
          ``on_guild_remove``).
        - Providing centralised command-error handling in
          ``on_command_error``.

    Attributes:
        start_time (datetime): The UTC-naive timestamp recorded when the bot
            instance is created.  Used elsewhere (e.g. the ``!uptime``
            command) to calculate how long the bot has been running.
    """

    def __init__(self):
        """Initialise the bot with required intents and settings.

        Intents enabled:
            - ``messages`` / ``message_content``: Read and process user
              messages for prefix commands and auto-moderation.
            - ``members``: Track join/leave events for welcome messages and
              leveling.
            - ``reactions``: Power the reaction-role system.
            - ``guilds``: Receive guild-level events (join, remove, channel
              updates).

        The built-in help command is disabled (``help_command=None``) because
        the bot ships its own custom help implementation via a cog.
        Commands are matched case-insensitively for a friendlier UX.
        """

        # Configure gateway intents -- each intent corresponds to a category
        # of events the bot will receive from Discord.
        intents = discord.Intents.default()
        intents.messages = True          # Receive message create / update / delete
        intents.message_content = True   # Access the text content of messages (privileged)
        intents.members = True           # Receive member join / leave / update (privileged)
        intents.reactions = True         # Receive reaction add / remove
        intents.guilds = True            # Receive guild-level metadata changes

        super().__init__(
            command_prefix=self.get_prefix,
            intents=intents,
            help_command=None,  # Disabled: we use our own custom help command
            case_insensitive=True
        )

        # Record the creation time so other parts of the bot can compute uptime
        self.start_time = datetime.now()

    async def get_prefix(self, bot, message: discord.Message):
        """Resolve the command prefix for the current context.

        If the message originates from a DM (no guild), the global default
        prefix from ``config.py`` is used.  Otherwise the guild-specific
        prefix is looked up in the database, falling back to the global
        default when no custom prefix has been configured.

        Args:
            bot (commands.Bot): The bot instance (unused but required by the
                ``command_prefix`` callable signature).
            message (discord.Message): The message that triggered prefix
                resolution.

        Returns:
            str: The command prefix string to use for this message.
        """

        # DMs have no guild context -- always use the global default prefix
        if not message.guild:
            return PREFIX

        # Look up the guild's stored configuration; fall back to the global
        # default prefix when the guild has not customised it.
        config = await db.get_guild_config(message.guild.id)
        return config.get('prefix', PREFIX)

    async def setup_hook(self):
        """Perform one-time async setup before the bot connects to Discord.

        This method is called automatically by ``discord.py`` after
        ``__init__`` but before the bot logs in.  It is the correct place for
        any setup that requires ``await`` (database init, loading extensions).

        Steps:
            1. Initialise the database connection / schema via ``db.init()``.
            2. Iterate over the cog registry and attempt to load each
               extension.  Failures are logged but do **not** prevent the bot
               from starting -- this allows partial operation even if a single
               cog has an import error or bug.

        Raises:
            No exceptions are raised to the caller; individual cog-loading
            failures are caught and logged at ERROR level.
        """

        # Initialise the database (creates tables / opens connection pool)
        logger.info("Initialising the database...")
        await db.init()

        # Registry of cog module paths to load.
        # Each entry corresponds to a Python module inside the ``cogs/``
        # package that exposes a ``setup(bot)`` function.
        cogs = [
            'cogs.leveling',          # XP / level-up system
            'cogs.moderation',        # Ban, kick, mute, warn commands
            'cogs.profanity_filter',  # Automatic bad-word detection
            'cogs.reaction_roles',    # Role assignment via reactions
            'cogs.games',             # Mini-games (trivia, dice, etc.)
            'cogs.utility',           # General-purpose utilities
            'cogs.tickets',           # Support ticket system
            'cogs.welcome',           # Welcome / goodbye messages
            'cogs.admin',             # Bot-owner / admin commands
            'cogs.scheduler',         # Scheduled / recurring messages
            'cogs.ai'                 # AI-powered chatbot integration
        ]

        for cog in cogs:
            try:
                await self.load_extension(cog)
                logger.info(f"Cog loaded: {cog}")
            except Exception as e:
                # Log but do not re-raise -- allow the bot to start without
                # this cog so that the remaining features stay available.
                logger.error(f"Failed to load cog {cog}: {e}")

    async def on_ready(self):
        """Called when the bot has successfully connected to Discord.

        This event may fire multiple times during the bot's lifetime (e.g.
        after a reconnect), so expensive one-time work should be guarded or
        placed in ``setup_hook`` instead.

        Actions performed:
            1. Log connection diagnostics (username, guild count, latency).
            2. Set the bot's Rich Presence status to show the current guild
               count.
            3. Synchronise the application command tree (slash commands) with
               Discord.  In production you may want to gate this behind a
               flag to avoid rate-limit issues.
        """

        logger.info(f"Bot connected as {self.user} (ID: {self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} guild(s)")
        logger.info(f"Latency: {round(self.latency * 1000)}ms")
        logger.info("-" * 50)

        # Set the bot's "Watching" status to display the guild count
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(self.guilds)} serveurs | !help"
        )
        await self.change_presence(activity=activity)

        # Synchronise slash commands with Discord (global sync).
        # NOTE: In large bots, consider syncing only on explicit command to
        # avoid hitting the daily global-sync rate limit.
        try:
            synced = await self.tree.sync()
            logger.info(f"{len(synced)} slash command(s) synchronised")
        except Exception as e:
            logger.error(f"Slash command sync failed: {e}")

    async def on_guild_join(self, guild: discord.Guild):
        """Handle the bot being added to a new guild.

        When the bot joins a guild the following steps are performed:
            1. Log the event.
            2. Create a default configuration row in the database for the
               guild so that all config look-ups have a baseline.
            3. Update the bot's presence to reflect the new guild count.
            4. Attempt to DM the guild owner with a welcome / quick-start
               embed.  If the owner has DMs disabled (``Forbidden``), the
               error is silently ignored.

        Args:
            guild (discord.Guild): The guild the bot was added to.
        """

        logger.info(f"Bot added to guild: {guild.name} (ID: {guild.id})")

        # Persist default settings for this guild in the database
        await db.create_guild_config(guild.id)

        # Refresh the presence to include the updated guild count
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(self.guilds)} serveurs | !help"
        )
        await self.change_presence(activity=activity)

        # Send a quick-start DM to the guild owner
        if guild.owner:
            try:
                embed = discord.Embed(
                    title=f"Merci de m'avoir ajouté à {guild.name}!",
                    description="Voici quelques commandes pour commencer:\n\n"
                                "**Configuration:**\n"
                                "`!config` - Voir la configuration\n"
                                "`!setwelcome #channel` - Channel de bienvenue\n"
                                "`!config logchannel #channel` - Channel de logs\n\n"
                                "**Fonctionnalités:**\n"
                                "`!help` - Liste des commandes\n"
                                "`!ticket setup` - Système de tickets\n"
                                "`!reactionrole create` - Menus de rôles\n\n"
                                "Besoin d'aide? Rejoignez notre serveur support!",
                    color=Colors.PRIMARY
                )
                await guild.owner.send(embed=embed)
            except discord.Forbidden:
                # The guild owner has DMs disabled -- nothing we can do
                pass

    async def on_guild_remove(self, guild: discord.Guild):
        """Handle the bot being removed from a guild.

        Updates the bot's Rich Presence to reflect the decreased guild count.
        Guild data is intentionally **not** deleted from the database so that
        it can be restored if the bot is re-added later.

        Args:
            guild (discord.Guild): The guild the bot was removed from.
        """

        logger.info(f"Bot removed from guild: {guild.name} (ID: {guild.id})")

        # Refresh the presence to reflect the updated guild count
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(self.guilds)} serveurs | !help"
        )
        await self.change_presence(activity=activity)

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        """Global command-error handler.

        This method acts as a catch-all for any command error that is not
        handled locally by an individual cog or command.  Each recognised
        error type produces a user-friendly embed that auto-deletes after a
        short delay to keep channels tidy.

        Handled error types:
            - ``CommandNotFound``: Silently ignored (no feedback to the user).
            - ``MissingPermissions``: The invoking user lacks a required
              Discord permission.
            - ``BotMissingPermissions``: The bot itself lacks a permission
              needed to execute the action.
            - ``MissingRequiredArgument``: A required command argument was
              not supplied; the correct usage signature is shown.
            - ``BadArgument``: An argument could not be converted to the
              expected type.
            - ``CommandOnCooldown``: The command is rate-limited; the
              remaining cooldown time is displayed.
            - ``NotOwner``: A bot-owner-only command was invoked by someone
              who is not listed in the owner IDs.

        Any error type not listed above is logged at ERROR level with a full
        traceback and a generic error message is sent to the user.

        Args:
            ctx (commands.Context): The invocation context of the failed
                command.
            error (commands.CommandError): The exception raised during
                command processing.
        """

        # ---- CommandNotFound ----
        # Silently ignore unknown commands so users are not spammed with
        # error messages when they mistype or use another bot's prefix.
        if isinstance(error, commands.CommandNotFound):
            return

        # ---- MissingPermissions (user) ----
        if isinstance(error, commands.MissingPermissions):
            embed = discord.Embed(
                title="Permission refusée",
                description="Vous n'avez pas les permissions nécessaires pour cette commande.",
                color=Colors.ERROR
            )
            await ctx.send(embed=embed, delete_after=10)
            return

        # ---- BotMissingPermissions ----
        if isinstance(error, commands.BotMissingPermissions):
            embed = discord.Embed(
                title="Permission manquante",
                description="Je n'ai pas les permissions nécessaires pour effectuer cette action.",
                color=Colors.ERROR
            )
            await ctx.send(embed=embed, delete_after=10)
            return

        # ---- MissingRequiredArgument ----
        if isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(
                title="Argument manquant",
                description=f"Utilisation: `{ctx.prefix}{ctx.command.name} {ctx.command.signature}`",
                color=Colors.WARNING
            )
            await ctx.send(embed=embed, delete_after=10)
            return

        # ---- BadArgument ----
        if isinstance(error, commands.BadArgument):
            embed = discord.Embed(
                title="Argument invalide",
                description=str(error),
                color=Colors.WARNING
            )
            await ctx.send(embed=embed, delete_after=10)
            return

        # ---- CommandOnCooldown ----
        if isinstance(error, commands.CommandOnCooldown):
            embed = discord.Embed(
                title="Cooldown",
                description=f"Réessayez dans {error.retry_after:.1f} secondes.",
                color=Colors.WARNING
            )
            await ctx.send(embed=embed, delete_after=5)
            return

        # ---- NotOwner ----
        if isinstance(error, commands.NotOwner):
            embed = discord.Embed(
                title="Accès refusé",
                description="Cette commande est réservée au propriétaire du bot.",
                color=Colors.ERROR
            )
            await ctx.send(embed=embed, delete_after=10)
            return

        # ---- Unhandled / unexpected error ----
        # Log the full traceback for debugging, then show a generic message
        # to the end user.
        logger.error(f"Unhandled command error: {error}", exc_info=error)
        embed = discord.Embed(
            title="Erreur",
            description="Une erreur inattendue s'est produite.",
            color=Colors.ERROR
        )
        await ctx.send(embed=embed, delete_after=10)


async def main():
    """Asynchronous entry point for the bot.

    Creates the ``data/`` directory (used by the database and other
    file-based storage) if it does not already exist, then instantiates
    ``DiscordBot`` and connects to the Discord gateway using the token
    loaded from the environment.

    The ``async with bot:`` context manager ensures that the bot's internal
    aiohttp session and other resources are properly closed on shutdown.
    """

    # Ensure the data directory exists for SQLite / JSON file storage
    os.makedirs('data', exist_ok=True)

    bot = DiscordBot()

    async with bot:
        await bot.start(TOKEN)


# ---------------------------------------------------------------------------
# Script entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Graceful shutdown when the operator presses Ctrl+C
        logger.info("Bot stopped by user (KeyboardInterrupt)")
    except Exception as e:
        # Catch-all for fatal errors that escape the event loop
        logger.error(f"Fatal error: {e}")
