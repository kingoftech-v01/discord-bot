"""
Cog de modération avancée avec auto-mod.
"""
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional
import re
import asyncio

from config import (
    BANNED_WORDS, WARN_THRESHOLD, MUTE_DURATION,
    SPAM_THRESHOLD, SPAM_INTERVAL, Colors, Emojis
)
from utils.database import db


class AutoMod:
    """Système d'auto-modération."""

    def __init__(self):
        self.message_cache = defaultdict(list)  # {user_id: [(timestamp, content), ...]}
        self.mention_cache = defaultdict(list)  # {user_id: [timestamps]}
        self.caps_pattern = re.compile(r'[A-Z]')
        self.link_pattern = re.compile(r'https?://\S+')
        self.invite_pattern = re.compile(r'discord(?:\.gg|app\.com/invite)/[\w-]+')

    def check_spam(self, user_id: int, content: str) -> bool:
        """Vérifie si un utilisateur spam."""
        now = datetime.now()
        # Nettoyer les anciens messages
        self.message_cache[user_id] = [
            (ts, msg) for ts, msg in self.message_cache[user_id]
            if (now - ts).total_seconds() < SPAM_INTERVAL
        ]
        self.message_cache[user_id].append((now, content))
        return len(self.message_cache[user_id]) >= SPAM_THRESHOLD

    def check_mention_spam(self, user_id: int, mention_count: int) -> bool:
        """Vérifie le spam de mentions."""
        if mention_count < 5:
            return False
        now = datetime.now()
        for _ in range(mention_count):
            self.mention_cache[user_id].append(now)
        self.mention_cache[user_id] = [
            ts for ts in self.mention_cache[user_id]
            if (now - ts).total_seconds() < 10
        ]
        return len(self.mention_cache[user_id]) >= 10

    def check_banned_words(self, content: str) -> Optional[str]:
        """Vérifie les mots interdits."""
        content_lower = content.lower()
        for word in BANNED_WORDS:
            if word.lower() in content_lower:
                return word
        return None

    def check_excessive_caps(self, content: str, threshold: float = 0.7) -> bool:
        """Vérifie l'usage excessif de majuscules."""
        if len(content) < 10:
            return False
        letters = [c for c in content if c.isalpha()]
        if not letters:
            return False
        caps_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        return caps_ratio >= threshold

    def check_invite_link(self, content: str) -> bool:
        """Vérifie les liens d'invitation Discord."""
        return bool(self.invite_pattern.search(content))


class Moderation(commands.Cog):
    """Outils de modération et auto-modération."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.automod = AutoMod()

    async def log_action(self, guild: discord.Guild, embed: discord.Embed):
        """Envoie un log dans le channel de logs."""
        config = await db.get_guild_config(guild.id)
        log_channel_id = config.get('log_channel_id')
        if log_channel_id:
            channel = guild.get_channel(log_channel_id)
            if channel:
                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    pass

    async def get_mute_role(self, guild: discord.Guild) -> Optional[discord.Role]:
        """Récupère ou crée le rôle mute."""
        config = await db.get_guild_config(guild.id)
        mute_role_id = config.get('mute_role_id')

        if mute_role_id:
            role = guild.get_role(mute_role_id)
            if role:
                return role

        # Créer le rôle mute
        try:
            role = await guild.create_role(
                name="Muted",
                color=discord.Color.dark_gray(),
                reason="Rôle de mute automatique"
            )

            # Configurer les permissions dans tous les channels
            for channel in guild.channels:
                try:
                    await channel.set_permissions(role, send_messages=False, speak=False)
                except discord.Forbidden:
                    pass

            await db.update_guild_config(guild.id, mute_role_id=role.id)
            return role
        except discord.Forbidden:
            return None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Auto-modération des messages."""
        if message.author.bot or not message.guild:
            return
        if message.author.guild_permissions.administrator:
            return

        config = await db.get_guild_config(message.guild.id)
        if not config.get('auto_mod_enabled', True):
            return

        violations = []

        # Vérifier les mots interdits
        banned_word = self.automod.check_banned_words(message.content)
        if banned_word:
            violations.append(f"Mot interdit détecté")
            try:
                await message.delete()
            except discord.Forbidden:
                pass

        # Vérifier le spam
        if self.automod.check_spam(message.author.id, message.content):
            violations.append("Spam détecté")
            try:
                await message.delete()
            except discord.Forbidden:
                pass

        # Vérifier le spam de mentions
        if self.automod.check_mention_spam(message.author.id, len(message.mentions)):
            violations.append("Spam de mentions")
            try:
                await message.delete()
            except discord.Forbidden:
                pass

        # Vérifier les liens d'invitation
        if self.automod.check_invite_link(message.content):
            violations.append("Lien d'invitation non autorisé")
            try:
                await message.delete()
            except discord.Forbidden:
                pass

        # Vérifier les majuscules excessives
        if self.automod.check_excessive_caps(message.content):
            violations.append("Usage excessif de majuscules")

        # Traiter les violations
        if violations:
            # Avertir l'utilisateur
            try:
                warning_embed = discord.Embed(
                    title=f"{Emojis.WARNING} Avertissement Auto-Mod",
                    description=f"Votre message a été signalé pour: {', '.join(violations)}",
                    color=Colors.WARNING
                )
                await message.channel.send(
                    f"{message.author.mention}",
                    embed=warning_embed,
                    delete_after=10
                )
            except discord.Forbidden:
                pass

            # Log
            log_embed = discord.Embed(
                title=f"{Emojis.WARNING} Auto-Modération",
                color=Colors.WARNING,
                timestamp=datetime.now()
            )
            log_embed.add_field(name="Utilisateur", value=f"{message.author.mention}", inline=True)
            log_embed.add_field(name="Channel", value=message.channel.mention, inline=True)
            log_embed.add_field(name="Violations", value="\n".join(violations), inline=False)
            log_embed.add_field(name="Message", value=message.content[:500] or "N/A", inline=False)
            await self.log_action(message.guild, log_embed)

    @commands.hybrid_command(name="ban")
    @commands.has_permissions(ban_members=True)
    @app_commands.describe(membre="Le membre à bannir", raison="Raison du ban")
    async def ban(self, ctx: commands.Context, membre: discord.Member, *, raison: str = None):
        """Bannit un membre du serveur."""
        if membre.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send(f"{Emojis.ERROR} Vous ne pouvez pas bannir ce membre.")

        try:
            await membre.ban(reason=raison)
            embed = discord.Embed(
                title=f"{Emojis.SUCCESS} Membre Banni",
                description=f"{membre.mention} a été banni du serveur.",
                color=Colors.ERROR
            )
            embed.add_field(name="Raison", value=raison or "Aucune raison spécifiée")
            embed.add_field(name="Modérateur", value=ctx.author.mention)
            await ctx.send(embed=embed)

            # Log
            log_embed = discord.Embed(
                title="Membre Banni",
                color=Colors.ERROR,
                timestamp=datetime.now()
            )
            log_embed.add_field(name="Membre", value=f"{membre} ({membre.id})")
            log_embed.add_field(name="Modérateur", value=ctx.author.mention)
            log_embed.add_field(name="Raison", value=raison or "Aucune")
            await self.log_action(ctx.guild, log_embed)
        except discord.Forbidden:
            await ctx.send(f"{Emojis.ERROR} Je n'ai pas la permission de bannir ce membre.")

    @commands.hybrid_command(name="kick")
    @commands.has_permissions(kick_members=True)
    @app_commands.describe(membre="Le membre à expulser", raison="Raison de l'expulsion")
    async def kick(self, ctx: commands.Context, membre: discord.Member, *, raison: str = None):
        """Expulse un membre du serveur."""
        if membre.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send(f"{Emojis.ERROR} Vous ne pouvez pas expulser ce membre.")

        try:
            await membre.kick(reason=raison)
            embed = discord.Embed(
                title=f"{Emojis.SUCCESS} Membre Expulsé",
                description=f"{membre.mention} a été expulsé du serveur.",
                color=Colors.WARNING
            )
            embed.add_field(name="Raison", value=raison or "Aucune raison spécifiée")
            embed.add_field(name="Modérateur", value=ctx.author.mention)
            await ctx.send(embed=embed)

            # Log
            log_embed = discord.Embed(
                title="Membre Expulsé",
                color=Colors.WARNING,
                timestamp=datetime.now()
            )
            log_embed.add_field(name="Membre", value=f"{membre} ({membre.id})")
            log_embed.add_field(name="Modérateur", value=ctx.author.mention)
            log_embed.add_field(name="Raison", value=raison or "Aucune")
            await self.log_action(ctx.guild, log_embed)
        except discord.Forbidden:
            await ctx.send(f"{Emojis.ERROR} Je n'ai pas la permission d'expulser ce membre.")

    @commands.hybrid_command(name="mute", aliases=["timeout"])
    @commands.has_permissions(moderate_members=True)
    @app_commands.describe(membre="Le membre à mute", duree="Durée en minutes", raison="Raison du mute")
    async def mute(self, ctx: commands.Context, membre: discord.Member, duree: int = 60, *, raison: str = None):
        """Mute un membre (timeout Discord)."""
        if membre.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send(f"{Emojis.ERROR} Vous ne pouvez pas mute ce membre.")

        if duree > 40320:  # Max 28 jours
            return await ctx.send(f"{Emojis.ERROR} La durée maximale est de 28 jours (40320 minutes).")

        try:
            until = datetime.now() + timedelta(minutes=duree)
            await membre.timeout(until, reason=raison)

            embed = discord.Embed(
                title=f"{Emojis.SUCCESS} Membre Mute",
                description=f"{membre.mention} a été mute pour **{duree}** minutes.",
                color=Colors.WARNING
            )
            embed.add_field(name="Raison", value=raison or "Aucune raison spécifiée")
            embed.add_field(name="Modérateur", value=ctx.author.mention)
            await ctx.send(embed=embed)

            # Log
            log_embed = discord.Embed(
                title="Membre Mute",
                color=Colors.WARNING,
                timestamp=datetime.now()
            )
            log_embed.add_field(name="Membre", value=f"{membre} ({membre.id})")
            log_embed.add_field(name="Durée", value=f"{duree} minutes")
            log_embed.add_field(name="Modérateur", value=ctx.author.mention)
            log_embed.add_field(name="Raison", value=raison or "Aucune")
            await self.log_action(ctx.guild, log_embed)
        except discord.Forbidden:
            await ctx.send(f"{Emojis.ERROR} Je n'ai pas la permission de mute ce membre.")

    @commands.hybrid_command(name="unmute", aliases=["untimeout"])
    @commands.has_permissions(moderate_members=True)
    @app_commands.describe(membre="Le membre à unmute")
    async def unmute(self, ctx: commands.Context, membre: discord.Member):
        """Retire le mute d'un membre."""
        try:
            await membre.timeout(None)
            embed = discord.Embed(
                title=f"{Emojis.SUCCESS} Membre Unmute",
                description=f"Le mute de {membre.mention} a été retiré.",
                color=Colors.SUCCESS
            )
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send(f"{Emojis.ERROR} Je n'ai pas la permission d'unmute ce membre.")

    @commands.hybrid_command(name="warn")
    @commands.has_permissions(manage_messages=True)
    @app_commands.describe(membre="Le membre à avertir", raison="Raison de l'avertissement")
    async def warn(self, ctx: commands.Context, membre: discord.Member, *, raison: str = None):
        """Donne un avertissement à un membre."""
        if membre.bot:
            return await ctx.send(f"{Emojis.ERROR} Vous ne pouvez pas avertir un bot.")

        warn_count = await db.add_warning(membre.id, ctx.guild.id, ctx.author.id, raison)

        embed = discord.Embed(
            title=f"{Emojis.WARNING} Avertissement",
            description=f"{membre.mention} a reçu un avertissement.",
            color=Colors.WARNING
        )
        embed.add_field(name="Raison", value=raison or "Aucune raison spécifiée")
        embed.add_field(name="Avertissements", value=f"{warn_count}/{WARN_THRESHOLD}")
        embed.add_field(name="Modérateur", value=ctx.author.mention)
        await ctx.send(embed=embed)

        # Vérifier le seuil d'avertissements
        if warn_count >= WARN_THRESHOLD:
            try:
                until = datetime.now() + timedelta(seconds=MUTE_DURATION)
                await membre.timeout(until, reason=f"Atteint {WARN_THRESHOLD} avertissements")
                await ctx.send(
                    f"{Emojis.WARNING} {membre.mention} a atteint {WARN_THRESHOLD} avertissements et a été mute automatiquement."
                )
            except discord.Forbidden:
                pass

        # Log
        log_embed = discord.Embed(
            title="Avertissement",
            color=Colors.WARNING,
            timestamp=datetime.now()
        )
        log_embed.add_field(name="Membre", value=f"{membre} ({membre.id})")
        log_embed.add_field(name="Total", value=f"{warn_count}/{WARN_THRESHOLD}")
        log_embed.add_field(name="Modérateur", value=ctx.author.mention)
        log_embed.add_field(name="Raison", value=raison or "Aucune")
        await self.log_action(ctx.guild, log_embed)

    @commands.hybrid_command(name="warnings", aliases=["warns"])
    @app_commands.describe(membre="Le membre dont vous voulez voir les avertissements")
    async def warnings(self, ctx: commands.Context, membre: Optional[discord.Member] = None):
        """Affiche les avertissements d'un membre."""
        member = membre or ctx.author
        warnings = await db.get_warnings(member.id, ctx.guild.id)

        embed = discord.Embed(
            title=f"{Emojis.WARNING} Avertissements de {member.display_name}",
            color=Colors.WARNING
        )

        if not warnings:
            embed.description = "Aucun avertissement."
        else:
            for i, warn in enumerate(warnings[:10], 1):
                mod = ctx.guild.get_member(warn['moderator_id'])
                mod_name = mod.display_name if mod else "Inconnu"
                date = datetime.fromisoformat(warn['created_at']).strftime("%d/%m/%Y")
                embed.add_field(
                    name=f"#{i} - {date}",
                    value=f"**Raison:** {warn['reason'] or 'Aucune'}\n**Par:** {mod_name}",
                    inline=False
                )

        embed.set_footer(text=f"Total: {len(warnings)} avertissement(s)")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="clearwarnings", aliases=["clearwarns"])
    @commands.has_permissions(administrator=True)
    @app_commands.describe(membre="Le membre dont vous voulez effacer les avertissements")
    async def clearwarnings(self, ctx: commands.Context, membre: discord.Member):
        """[Admin] Efface tous les avertissements d'un membre."""
        await db.clear_warnings(membre.id, ctx.guild.id)
        embed = discord.Embed(
            title=f"{Emojis.SUCCESS} Avertissements effacés",
            description=f"Tous les avertissements de {membre.mention} ont été effacés.",
            color=Colors.SUCCESS
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="purge", aliases=["clear", "clean"])
    @commands.has_permissions(manage_messages=True)
    @app_commands.describe(nombre="Nombre de messages à supprimer (max 100)")
    async def purge(self, ctx: commands.Context, nombre: int):
        """Supprime un nombre de messages."""
        if nombre < 1 or nombre > 100:
            return await ctx.send(f"{Emojis.ERROR} Le nombre doit être entre 1 et 100.")

        try:
            deleted = await ctx.channel.purge(limit=nombre + 1)
            msg = await ctx.send(
                f"{Emojis.SUCCESS} **{len(deleted) - 1}** messages supprimés.",
                delete_after=5
            )
        except discord.Forbidden:
            await ctx.send(f"{Emojis.ERROR} Je n'ai pas la permission de supprimer des messages.")

    @commands.hybrid_command(name="slowmode")
    @commands.has_permissions(manage_channels=True)
    @app_commands.describe(secondes="Délai en secondes (0 pour désactiver)")
    async def slowmode(self, ctx: commands.Context, secondes: int):
        """Configure le slowmode du channel."""
        if secondes < 0 or secondes > 21600:
            return await ctx.send(f"{Emojis.ERROR} Le délai doit être entre 0 et 21600 secondes.")

        await ctx.channel.edit(slowmode_delay=secondes)
        if secondes == 0:
            await ctx.send(f"{Emojis.SUCCESS} Slowmode désactivé.")
        else:
            await ctx.send(f"{Emojis.SUCCESS} Slowmode configuré à **{secondes}** secondes.")

    @commands.hybrid_command(name="lock")
    @commands.has_permissions(manage_channels=True)
    async def lock(self, ctx: commands.Context):
        """Verrouille le channel actuel."""
        await ctx.channel.set_permissions(
            ctx.guild.default_role,
            send_messages=False
        )
        embed = discord.Embed(
            title=f"{Emojis.SUCCESS} Channel Verrouillé",
            description="Ce channel a été verrouillé.",
            color=Colors.ERROR
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="unlock")
    @commands.has_permissions(manage_channels=True)
    async def unlock(self, ctx: commands.Context):
        """Déverrouille le channel actuel."""
        await ctx.channel.set_permissions(
            ctx.guild.default_role,
            send_messages=True
        )
        embed = discord.Embed(
            title=f"{Emojis.SUCCESS} Channel Déverrouillé",
            description="Ce channel a été déverrouillé.",
            color=Colors.SUCCESS
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
