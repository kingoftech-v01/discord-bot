"""Discord Bot - Main Entry Point.

Startup: main() -> DiscordBot.setup_hook() -> on_ready()
"""

import discord
from discord.ext import commands
import asyncio
import os
import logging
from datetime import datetime

from config import TOKEN, PREFIX, Colors
from utils.database import db

# UTF-8 required for non-ASCII guild names in logs
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
    """Main bot class with per-guild prefix support and cog loading."""

    def __init__(self):
        # message_content is privileged and must be enabled in Discord Developer Portal
        intents = discord.Intents.default()
        intents.messages = True
        intents.message_content = True
        intents.members = True  # Privileged: required for welcome/leveling
        intents.reactions = True
        intents.guilds = True

        super().__init__(
            command_prefix=self.get_prefix,
            intents=intents,
            help_command=None,  # Custom help in admin cog
            case_insensitive=True
        )

        self.start_time = datetime.now()  # For uptime command

    async def get_prefix(self, bot, message: discord.Message):
        """Return guild-specific prefix or default for DMs."""
        if not message.guild:
            return PREFIX

        config = await db.get_guild_config(message.guild.id)
        return config.get('prefix', PREFIX)

    async def setup_hook(self):
        """Initialize database and load cogs before connecting."""
        logger.info("Initialising the database...")
        await db.init()

        cogs = [
            'cogs.leveling',
            'cogs.moderation',
            'cogs.profanity_filter',
            'cogs.reaction_roles',
            'cogs.games',
            'cogs.utility',
            'cogs.tickets',
            'cogs.welcome',
            'cogs.admin',
            'cogs.scheduler',
            'cogs.ai'
        ]

        for cog in cogs:
            try:
                await self.load_extension(cog)
                logger.info(f"Cog loaded: {cog}")
            except Exception as e:
                # Don't crash the bot if one cog fails
                logger.error(f"Failed to load cog {cog}: {e}")

    async def on_ready(self):
        """Log connection info and sync slash commands."""
        logger.info(f"Bot connected as {self.user} (ID: {self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} guild(s)")
        logger.info(f"Latency: {round(self.latency * 1000)}ms")
        logger.info("-" * 50)

        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(self.guilds)} serveurs | !help"
        )
        await self.change_presence(activity=activity)

        # FIXME: Global sync has daily rate limit; consider guild-specific sync for dev
        try:
            synced = await self.tree.sync()
            logger.info(f"{len(synced)} slash command(s) synchronised")
        except Exception as e:
            logger.error(f"Slash command sync failed: {e}")

    async def on_guild_join(self, guild: discord.Guild):
        """Create default config and welcome the guild owner."""
        logger.info(f"Bot added to guild: {guild.name} (ID: {guild.id})")

        await db.create_guild_config(guild.id)

        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(self.guilds)} serveurs | !help"
        )
        await self.change_presence(activity=activity)

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
                pass  # Owner has DMs disabled

    async def on_guild_remove(self, guild: discord.Guild):
        """Update presence. Data is kept for potential re-add."""
        logger.info(f"Bot removed from guild: {guild.name} (ID: {guild.id})")

        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(self.guilds)} serveurs | !help"
        )
        await self.change_presence(activity=activity)

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        """Handle common command errors with user-friendly messages."""
        # Ignore unknown commands to avoid spam when users mistype
        if isinstance(error, commands.CommandNotFound):
            return

        if isinstance(error, commands.MissingPermissions):
            embed = discord.Embed(
                title="Permission refusée",
                description="Vous n'avez pas les permissions nécessaires pour cette commande.",
                color=Colors.ERROR
            )
            await ctx.send(embed=embed, delete_after=10)
            return

        if isinstance(error, commands.BotMissingPermissions):
            embed = discord.Embed(
                title="Permission manquante",
                description="Je n'ai pas les permissions nécessaires pour effectuer cette action.",
                color=Colors.ERROR
            )
            await ctx.send(embed=embed, delete_after=10)
            return

        if isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(
                title="Argument manquant",
                description=f"Utilisation: `{ctx.prefix}{ctx.command.name} {ctx.command.signature}`",
                color=Colors.WARNING
            )
            await ctx.send(embed=embed, delete_after=10)
            return

        if isinstance(error, commands.BadArgument):
            embed = discord.Embed(
                title="Argument invalide",
                description=str(error),
                color=Colors.WARNING
            )
            await ctx.send(embed=embed, delete_after=10)
            return

        if isinstance(error, commands.CommandOnCooldown):
            embed = discord.Embed(
                title="Cooldown",
                description=f"Réessayez dans {error.retry_after:.1f} secondes.",
                color=Colors.WARNING
            )
            await ctx.send(embed=embed, delete_after=5)
            return

        if isinstance(error, commands.NotOwner):
            embed = discord.Embed(
                title="Accès refusé",
                description="Cette commande est réservée au propriétaire du bot.",
                color=Colors.ERROR
            )
            await ctx.send(embed=embed, delete_after=10)
            return

        # Log unexpected errors for debugging
        logger.error(f"Unhandled command error: {error}", exc_info=error)
        embed = discord.Embed(
            title="Erreur",
            description="Une erreur inattendue s'est produite.",
            color=Colors.ERROR
        )
        await ctx.send(embed=embed, delete_after=10)


async def main():
    """Entry point: create data dir, start bot."""
    os.makedirs('data', exist_ok=True)

    bot = DiscordBot()

    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (KeyboardInterrupt)")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
