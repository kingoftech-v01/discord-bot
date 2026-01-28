"""
Cog pour l'administration et la configuration du bot.
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
    """Configuration et administration du bot."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_group(name="config", aliases=["settings", "parametres"])
    @commands.has_permissions(administrator=True)
    async def config(self, ctx: commands.Context):
        """Commandes de configuration du bot."""
        if ctx.invoked_subcommand is None:
            await self.show_config(ctx)

    async def show_config(self, ctx: commands.Context):
        """Affiche la configuration actuelle."""
        config = await db.get_guild_config(ctx.guild.id)

        embed = discord.Embed(
            title=f"Configuration de {ctx.guild.name}",
            color=Colors.PRIMARY,
            timestamp=datetime.now()
        )

        # Channels
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

        # Fonctionnalités
        embed.add_field(
            name="Fonctionnalités",
            value=f" Auto-Mod: {'Activé' if config.get('auto_mod_enabled', True) else 'Désactivé'}\n"
                  f" Leveling: {'Activé' if config.get('leveling_enabled', True) else 'Désactivé'}",
            inline=True
        )

        # Préfixe
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
        """Change le préfixe du bot."""
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
        """Configure le channel de logs."""
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
        """Configure le channel pour les notifications de level up."""
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
        """Active ou désactive l'auto-modération."""
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
        """Active ou désactive le système de leveling."""
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
        """Configure le message de level up."""
        await db.update_guild_config(ctx.guild.id, level_up_message=message)

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
        """Affiche l'aide du bot."""
        if commande:
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

            usage = f"{ctx.prefix}{cmd.name}"
            if cmd.signature:
                usage += f" {cmd.signature}"
            embed.add_field(name="Utilisation", value=f"`{usage}`", inline=False)

            await ctx.send(embed=embed)
            return

        embed = discord.Embed(
            title=f"Aide - {self.bot.user.name}",
            description=f"Préfixe: `{ctx.prefix}` | Utilisez `{ctx.prefix}help <commande>` pour plus d'infos",
            color=Colors.PRIMARY
        )

        # Catégories de commandes
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
        """Affiche les informations du bot."""
        embed = discord.Embed(
            title=f"À propos de {self.bot.user.name}",
            color=Colors.PRIMARY,
            timestamp=datetime.now()
        )

        embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        # Stats
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
        """Obtenir le lien d'invitation du bot."""
        permissions = discord.Permissions(
            administrator=True  # Ou définir des permissions spécifiques
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
        """[Owner] Synchronise les slash commands."""
        await ctx.send(f"{Emojis.LOADING} Synchronisation en cours...")
        try:
            synced = await self.bot.tree.sync()
            await ctx.send(f"{Emojis.SUCCESS} {len(synced)} commandes synchronisées!")
        except Exception as e:
            await ctx.send(f"{Emojis.ERROR} Erreur: {e}")

    @commands.command(name="reload")
    @commands.is_owner()
    async def reload_cog(self, ctx: commands.Context, cog: str):
        """[Owner] Recharge un cog."""
        try:
            await self.bot.reload_extension(f"cogs.{cog}")
            await ctx.send(f"{Emojis.SUCCESS} Cog `{cog}` rechargé!")
        except Exception as e:
            await ctx.send(f"{Emojis.ERROR} Erreur: {e}")

    @commands.command(name="shutdown")
    @commands.is_owner()
    async def shutdown(self, ctx: commands.Context):
        """[Owner] Arrête le bot."""
        await ctx.send(f"{Emojis.INFO} Arrêt du bot...")
        await self.bot.close()


async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
