"""
Cog de gestion du système de leveling et d'XP.
"""
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta
from typing import Optional
import math
import io

from config import (
    XP_PER_MESSAGE, XP_COOLDOWN, LEVEL_UP_BASE, LEVEL_UP_FACTOR,
    Colors, Emojis
)
from utils.database import db


class Leveling(commands.Cog):
    """Système de leveling avec XP, niveaux et récompenses."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.xp_cooldowns = {}  # {(user_id, guild_id): last_xp_time}

    def calculate_xp_for_level(self, level: int) -> int:
        """Calcule l'XP nécessaire pour atteindre un niveau."""
        return int(LEVEL_UP_BASE * (LEVEL_UP_FACTOR ** (level - 1)))

    def calculate_level_from_xp(self, total_xp: int) -> tuple[int, int]:
        """Calcule le niveau et l'XP restant à partir de l'XP total."""
        level = 1
        xp_remaining = total_xp
        while True:
            xp_needed = self.calculate_xp_for_level(level)
            if xp_remaining < xp_needed:
                break
            xp_remaining -= xp_needed
            level += 1
        return level, xp_remaining

    async def check_and_assign_level_roles(self, member: discord.Member, new_level: int):
        """Vérifie et attribue les rôles de niveau."""
        level_roles = await db.get_level_roles(member.guild.id)
        for lr in level_roles:
            role = member.guild.get_role(lr['role_id'])
            if role:
                if lr['level'] <= new_level:
                    if role not in member.roles:
                        try:
                            await member.add_roles(role)
                        except discord.Forbidden:
                            pass
                else:
                    if role in member.roles:
                        try:
                            await member.remove_roles(role)
                        except discord.Forbidden:
                            pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Gère l'attribution d'XP sur les messages."""
        if message.author.bot or not message.guild:
            return

        # Vérifier le cooldown
        key = (message.author.id, message.guild.id)
        now = datetime.now()
        if key in self.xp_cooldowns:
            if (now - self.xp_cooldowns[key]).total_seconds() < XP_COOLDOWN:
                return

        self.xp_cooldowns[key] = now

        # Vérifier si le leveling est activé
        config = await db.get_guild_config(message.guild.id)
        if not config.get('leveling_enabled', True):
            return

        # Ajouter l'XP
        user_data = await db.add_xp(message.author.id, message.guild.id, XP_PER_MESSAGE)

        # Calculer le nouveau niveau
        new_level, remaining_xp = self.calculate_level_from_xp(user_data['total_xp'])

        # Vérifier si level up
        if new_level > user_data['level']:
            await db.set_level(message.author.id, message.guild.id, new_level, remaining_xp)

            # Attribuer les rôles de niveau
            await self.check_and_assign_level_roles(message.author, new_level)

            # Envoyer le message de level up
            level_up_channel_id = config.get('level_up_channel_id')
            channel = message.guild.get_channel(level_up_channel_id) if level_up_channel_id else message.channel

            level_up_msg = config.get('level_up_message', 'Félicitations {user}! Tu es maintenant niveau {level}!')
            level_up_msg = level_up_msg.replace('{user}', message.author.mention)
            level_up_msg = level_up_msg.replace('{level}', str(new_level))

            embed = discord.Embed(
                title=f"{Emojis.LEVEL} Level Up!",
                description=level_up_msg,
                color=Colors.LEVEL_UP
            )
            embed.set_thumbnail(url=message.author.display_avatar.url)

            # Vérifier les récompenses de niveau
            role_id = await db.get_role_for_level(message.guild.id, new_level)
            if role_id:
                role = message.guild.get_role(role_id)
                if role:
                    embed.add_field(
                        name=f"{Emojis.TROPHY} Récompense débloquée!",
                        value=f"Tu as obtenu le rôle {role.mention}!"
                    )

            await channel.send(embed=embed)

    @commands.hybrid_command(name="rank", aliases=["niveau", "level"])
    @app_commands.describe(membre="Le membre dont vous voulez voir le rang")
    async def rank(self, ctx: commands.Context, membre: Optional[discord.Member] = None):
        """Affiche votre rang ou celui d'un autre membre."""
        member = membre or ctx.author
        if member.bot:
            return await ctx.send(f"{Emojis.ERROR} Les bots n'ont pas de niveau!")

        user_data = await db.get_or_create_user(member.id, ctx.guild.id)
        rank = await db.get_rank(member.id, ctx.guild.id)

        current_level = user_data['level']
        current_xp = user_data['xp']
        xp_needed = self.calculate_xp_for_level(current_level)

        # Barre de progression
        progress = current_xp / xp_needed
        bar_length = 20
        filled = int(bar_length * progress)
        bar = "" * filled + "" * (bar_length - filled)

        embed = discord.Embed(
            title=f"{Emojis.STAR} Profil de {member.display_name}",
            color=Colors.PRIMARY
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name=f"{Emojis.TROPHY} Rang", value=f"#{rank}", inline=True)
        embed.add_field(name=f"{Emojis.LEVEL} Niveau", value=str(current_level), inline=True)
        embed.add_field(name=f"{Emojis.XP} XP Total", value=f"{user_data['total_xp']:,}", inline=True)
        embed.add_field(
            name="Progression",
            value=f"`{bar}` {current_xp}/{xp_needed} XP",
            inline=False
        )
        embed.add_field(name="Messages", value=f"{user_data['messages_count']:,}", inline=True)

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="leaderboard", aliases=["top", "classement", "lb"])
    @app_commands.describe(page="Numéro de page")
    async def leaderboard(self, ctx: commands.Context, page: int = 1):
        """Affiche le classement XP du serveur."""
        per_page = 10
        offset = (page - 1) * per_page

        # Récupérer le classement complet pour calculer le nombre de pages
        all_users = await db.get_leaderboard(ctx.guild.id, limit=100)
        total_pages = max(1, math.ceil(len(all_users) / per_page))

        if page < 1 or page > total_pages:
            return await ctx.send(f"{Emojis.ERROR} Page invalide. Pages disponibles: 1-{total_pages}")

        users = all_users[offset:offset + per_page]

        embed = discord.Embed(
            title=f"{Emojis.TROPHY} Classement XP - {ctx.guild.name}",
            color=Colors.PRIMARY
        )

        if not users:
            embed.description = "Aucun utilisateur dans le classement."
        else:
            description_lines = []
            medals = ["", "", ""]
            for i, user_data in enumerate(users, start=offset + 1):
                member = ctx.guild.get_member(user_data['user_id'])
                name = member.display_name if member else f"Utilisateur #{user_data['user_id']}"

                medal = medals[i-1] if i <= 3 else f"**{i}.**"
                description_lines.append(
                    f"{medal} {name} - Niveau {user_data['level']} ({user_data['total_xp']:,} XP)"
                )

            embed.description = "\n".join(description_lines)

        embed.set_footer(text=f"Page {page}/{total_pages} | Utilisez !leaderboard [page]")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="setxp")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(membre="Le membre", xp="Quantité d'XP")
    async def setxp(self, ctx: commands.Context, membre: discord.Member, xp: int):
        """[Admin] Définit l'XP d'un membre."""
        if xp < 0:
            return await ctx.send(f"{Emojis.ERROR} L'XP ne peut pas être négatif.")

        user_data = await db.get_or_create_user(membre.id, ctx.guild.id)
        new_level, remaining_xp = self.calculate_level_from_xp(xp)

        async with db.aiosqlite.connect(db.db_path) as conn:
            await conn.execute("""
                UPDATE users SET xp = ?, total_xp = ?, level = ?
                WHERE user_id = ? AND guild_id = ?
            """, (remaining_xp, xp, new_level, membre.id, ctx.guild.id))
            await conn.commit()

        await self.check_and_assign_level_roles(membre, new_level)

        embed = discord.Embed(
            title=f"{Emojis.SUCCESS} XP Modifié",
            description=f"L'XP de {membre.mention} a été défini à **{xp:,}** (Niveau {new_level})",
            color=Colors.SUCCESS
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="addxp")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(membre="Le membre", xp="Quantité d'XP à ajouter")
    async def addxp(self, ctx: commands.Context, membre: discord.Member, xp: int):
        """[Admin] Ajoute de l'XP à un membre."""
        user_data = await db.get_or_create_user(membre.id, ctx.guild.id)
        new_total = max(0, user_data['total_xp'] + xp)
        new_level, remaining_xp = self.calculate_level_from_xp(new_total)

        async with db.aiosqlite.connect(db.db_path) as conn:
            await conn.execute("""
                UPDATE users SET xp = ?, total_xp = ?, level = ?
                WHERE user_id = ? AND guild_id = ?
            """, (remaining_xp, new_total, new_level, membre.id, ctx.guild.id))
            await conn.commit()

        await self.check_and_assign_level_roles(membre, new_level)

        action = "ajouté à" if xp >= 0 else "retiré de"
        embed = discord.Embed(
            title=f"{Emojis.SUCCESS} XP Modifié",
            description=f"**{abs(xp):,}** XP {action} {membre.mention}\nNouveau total: **{new_total:,}** XP (Niveau {new_level})",
            color=Colors.SUCCESS
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="levelrole")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(niveau="Le niveau requis", role="Le rôle à attribuer")
    async def levelrole(self, ctx: commands.Context, niveau: int, role: discord.Role):
        """[Admin] Configure un rôle de récompense pour un niveau."""
        if niveau < 1:
            return await ctx.send(f"{Emojis.ERROR} Le niveau doit être supérieur à 0.")

        await db.add_level_role(ctx.guild.id, niveau, role.id)

        embed = discord.Embed(
            title=f"{Emojis.SUCCESS} Rôle de niveau configuré",
            description=f"Le rôle {role.mention} sera attribué au niveau **{niveau}**",
            color=Colors.SUCCESS
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="levelroles")
    async def levelroles(self, ctx: commands.Context):
        """Affiche les rôles de niveau configurés."""
        roles = await db.get_level_roles(ctx.guild.id)

        if not roles:
            return await ctx.send(f"{Emojis.INFO} Aucun rôle de niveau configuré.")

        embed = discord.Embed(
            title=f"{Emojis.TROPHY} Rôles de Niveau",
            color=Colors.PRIMARY
        )

        description_lines = []
        for lr in roles:
            role = ctx.guild.get_role(lr['role_id'])
            if role:
                description_lines.append(f"Niveau **{lr['level']}** - {role.mention}")

        embed.description = "\n".join(description_lines) if description_lines else "Aucun rôle configuré."
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Leveling(bot))
