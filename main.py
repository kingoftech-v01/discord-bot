"""
Bot Discord Professionnel
Un bot complet avec leveling, économie, modération, tickets et plus encore.

Auteur: Discord Bot Pro
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

# Configuration du logging
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
    """Classe principale du bot Discord."""

    def __init__(self):
        # Configuration des intents
        intents = discord.Intents.default()
        intents.messages = True
        intents.message_content = True
        intents.members = True
        intents.reactions = True
        intents.guilds = True

        super().__init__(
            command_prefix=self.get_prefix,
            intents=intents,
            help_command=None,  # On utilise notre propre commande help
            case_insensitive=True
        )

        self.start_time = datetime.now()

    async def get_prefix(self, bot, message: discord.Message):
        """Récupère le préfixe personnalisé du serveur."""
        if not message.guild:
            return PREFIX

        config = await db.get_guild_config(message.guild.id)
        return config.get('prefix', PREFIX)

    async def setup_hook(self):
        """Configuration initiale du bot."""
        # Initialiser la base de données
        logger.info("Initialisation de la base de données...")
        await db.init()

        # Charger les cogs
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
                logger.info(f"Cog chargé: {cog}")
            except Exception as e:
                logger.error(f"Erreur lors du chargement de {cog}: {e}")

    async def on_ready(self):
        """Événement déclenché quand le bot est prêt."""
        logger.info(f"Bot connecté en tant que {self.user} (ID: {self.user.id})")
        logger.info(f"Connecté à {len(self.guilds)} serveur(s)")
        logger.info(f"Latence: {round(self.latency * 1000)}ms")
        logger.info("-" * 50)

        # Définir le statut du bot
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(self.guilds)} serveurs | !help"
        )
        await self.change_presence(activity=activity)

        # Synchroniser les slash commands (une seule fois en production)
        try:
            synced = await self.tree.sync()
            logger.info(f"{len(synced)} slash commands synchronisées")
        except Exception as e:
            logger.error(f"Erreur de synchronisation: {e}")

    async def on_guild_join(self, guild: discord.Guild):
        """Événement quand le bot rejoint un serveur."""
        logger.info(f"Bot ajouté au serveur: {guild.name} (ID: {guild.id})")

        # Créer la config par défaut
        await db.create_guild_config(guild.id)

        # Mettre à jour le statut
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(self.guilds)} serveurs | !help"
        )
        await self.change_presence(activity=activity)

        # Envoyer un message de bienvenue au owner
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
                pass

    async def on_guild_remove(self, guild: discord.Guild):
        """Événement quand le bot quitte un serveur."""
        logger.info(f"Bot retiré du serveur: {guild.name} (ID: {guild.id})")

        # Mettre à jour le statut
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(self.guilds)} serveurs | !help"
        )
        await self.change_presence(activity=activity)

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        """Gestion globale des erreurs de commandes."""
        if isinstance(error, commands.CommandNotFound):
            return  # Ignorer les commandes inexistantes

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

        # Erreur non gérée
        logger.error(f"Erreur non gérée: {error}", exc_info=error)
        embed = discord.Embed(
            title="Erreur",
            description="Une erreur inattendue s'est produite.",
            color=Colors.ERROR
        )
        await ctx.send(embed=embed, delete_after=10)


async def main():
    """Point d'entrée principal."""
    # Créer le dossier data si nécessaire
    os.makedirs('data', exist_ok=True)

    bot = DiscordBot()

    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot arrêté par l'utilisateur")
    except Exception as e:
        logger.error(f"Erreur fatale: {e}")
