"""
XP and leveling system cog for Discord.

This module implements a complete experience point (XP) and leveling system that:

- **Awards XP per message**: Each message earns the user a configurable amount of
  XP, subject to a per-user cooldown to prevent farming.
- **Tracks levels**: XP thresholds increase exponentially per level using a
  configurable base and growth factor (``LEVEL_UP_BASE * LEVEL_UP_FACTOR ^ (level - 1)``).
- **Level-up notifications**: Sends a celebratory embed when a user reaches a new
  level, optionally in a dedicated level-up channel.
- **Level role rewards**: Automatically assigns and removes Discord roles based on
  the user's current level, allowing for milestone-based perks.
- **Leaderboard**: Paginated server-wide XP rankings.
- **Admin tools**: Commands to manually set, add, or remove XP, and configure
  level-role mappings.

All user data (XP, levels, message counts) is persisted in the SQLite database
via the ``utils.database`` module.
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
    """Discord cog implementing an XP-based leveling system with role rewards.

    Users earn XP for each message they send (subject to a cooldown), and
    level up when they accumulate enough XP. Level-up events trigger
    notifications and optional role assignments.

    The XP curve is exponential: each level requires more XP than the last,
    calculated as ``LEVEL_UP_BASE * (LEVEL_UP_FACTOR ** (level - 1))``.

    Attributes:
        bot: The Discord bot instance.
        xp_cooldowns: In-memory cooldown tracker mapping ``(user_id, guild_id)``
            tuples to the datetime of their last XP award. Prevents XP farming
            by enforcing a minimum interval between awards.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.xp_cooldowns = {}  # {(user_id, guild_id): last_xp_time}

    def calculate_xp_for_level(self, level: int) -> int:
        """Calculate the XP required to advance from the given level to the next.

        Uses an exponential curve: ``LEVEL_UP_BASE * (LEVEL_UP_FACTOR ** (level - 1))``.
        This means higher levels require progressively more XP.

        Args:
            level: The current level (1-based).

        Returns:
            The amount of XP needed to progress from this level to the next.
        """
        return int(LEVEL_UP_BASE * (LEVEL_UP_FACTOR ** (level - 1)))

    def calculate_level_from_xp(self, total_xp: int) -> tuple[int, int]:
        """Determine the level and remaining XP from a total XP amount.

        Iteratively subtracts the XP cost of each level until the remaining
        XP is insufficient to reach the next level.

        Args:
            total_xp: The cumulative XP earned by the user.

        Returns:
            A tuple of ``(level, remaining_xp)`` where ``level`` is the
            user's current level (1-based) and ``remaining_xp`` is the XP
            accumulated toward the next level.
        """
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
        """Synchronize a member's level-based roles with their current level.

        Fetches all configured level-role mappings for the guild, then:
        - Adds roles that the member has qualified for (level requirement <= new_level).
        - Removes roles that the member no longer qualifies for (level requirement > new_level).

        Silently skips any role operations that fail due to insufficient permissions.

        Args:
            member: The guild member whose roles should be updated.
            new_level: The member's current level after the most recent XP change.
        """
        level_roles = await db.get_level_roles(member.guild.id)
        for lr in level_roles:
            role = member.guild.get_role(lr['role_id'])
            if role:
                if lr['level'] <= new_level:
                    # Member qualifies for this role; add if not already assigned
                    if role not in member.roles:
                        try:
                            await member.add_roles(role)
                        except discord.Forbidden:
                            pass
                else:
                    # Member no longer qualifies; remove if currently assigned
                    if role in member.roles:
                        try:
                            await member.remove_roles(role)
                        except discord.Forbidden:
                            pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Award XP for each eligible message and handle level-up events.

        This listener runs on every message. It skips bot messages, DMs, and
        messages from users still on cooldown. When a user levels up, it:
        1. Updates their level in the database.
        2. Assigns/removes any applicable level roles.
        3. Sends a level-up notification embed (to a configured channel or the
           current channel).
        4. Includes information about any newly unlocked role reward.

        Args:
            message: The incoming Discord message.
        """
        # Skip bot messages and DMs (XP is only awarded in guilds)
        if message.author.bot or not message.guild:
            return

        # Enforce per-user XP cooldown to prevent farming
        key = (message.author.id, message.guild.id)
        now = datetime.now()
        if key in self.xp_cooldowns:
            if (now - self.xp_cooldowns[key]).total_seconds() < XP_COOLDOWN:
                return

        self.xp_cooldowns[key] = now

        # Check if the leveling system is enabled for this guild
        config = await db.get_guild_config(message.guild.id)
        if not config.get('leveling_enabled', True):
            return

        # Award XP and get updated user data
        user_data = await db.add_xp(message.author.id, message.guild.id, XP_PER_MESSAGE)

        # Recalculate level from the new total XP
        new_level, remaining_xp = self.calculate_level_from_xp(user_data['total_xp'])

        # Detect level-up by comparing new level with stored level
        if new_level > user_data['level']:
            await db.set_level(message.author.id, message.guild.id, new_level, remaining_xp)

            # Synchronize level-based roles with the new level
            await self.check_and_assign_level_roles(message.author, new_level)

            # Determine which channel to send the level-up notification to
            level_up_channel_id = config.get('level_up_channel_id')
            channel = message.guild.get_channel(level_up_channel_id) if level_up_channel_id else message.channel

            # Build the level-up message using the configurable template
            level_up_msg = config.get('level_up_message', 'Félicitations {user}! Tu es maintenant niveau {level}!')
            level_up_msg = level_up_msg.replace('{user}', message.author.mention)
            level_up_msg = level_up_msg.replace('{level}', str(new_level))

            embed = discord.Embed(
                title=f"{Emojis.LEVEL} Level Up!",
                description=level_up_msg,
                color=Colors.LEVEL_UP
            )
            embed.set_thumbnail(url=message.author.display_avatar.url)

            # Check if the new level unlocks a specific role reward
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
        """Display a member's rank card showing level, XP, and progress.

        Shows the member's server rank, current level, total XP, a visual
        progress bar toward the next level, and total message count. If no
        member is specified, shows the invoking user's rank.

        Args:
            ctx: The command invocation context.
            membre: The member whose rank to display. Defaults to the command author.
        """
        member = membre or ctx.author
        if member.bot:
            return await ctx.send(f"{Emojis.ERROR} Les bots n'ont pas de niveau!")

        user_data = await db.get_or_create_user(member.id, ctx.guild.id)
        rank = await db.get_rank(member.id, ctx.guild.id)

        current_level = user_data['level']
        current_xp = user_data['xp']
        xp_needed = self.calculate_xp_for_level(current_level)

        # Build a visual text-based progress bar (20 characters wide)
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
        """Display the server's XP leaderboard with pagination.

        Shows a paginated ranking of the top 100 users by total XP, with
        10 entries per page. The top 3 entries receive medal emojis (gold,
        silver, bronze).

        Args:
            ctx: The command invocation context.
            page: The page number to display (1-based). Defaults to 1.
        """
        per_page = 10
        offset = (page - 1) * per_page

        # Fetch top 100 users to calculate total page count
        all_users = await db.get_leaderboard(ctx.guild.id, limit=100)
        total_pages = max(1, math.ceil(len(all_users) / per_page))

        if page < 1 or page > total_pages:
            return await ctx.send(f"{Emojis.ERROR} Page invalide. Pages disponibles: 1-{total_pages}")

        # Slice the list to get only the current page's entries
        users = all_users[offset:offset + per_page]

        embed = discord.Embed(
            title=f"{Emojis.TROPHY} Classement XP - {ctx.guild.name}",
            color=Colors.PRIMARY
        )

        if not users:
            embed.description = "Aucun utilisateur dans le classement."
        else:
            description_lines = []
            medals = ["", "", ""]  # Gold, silver, bronze for top 3
            for i, user_data in enumerate(users, start=offset + 1):
                member = ctx.guild.get_member(user_data['user_id'])
                name = member.display_name if member else f"Utilisateur #{user_data['user_id']}"

                # Use medal emoji for top 3, numbered bold text for others
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
        """[Admin] Set a member's total XP to an exact value.

        Recalculates the member's level from the new XP total, updates the
        database, and synchronizes their level roles accordingly. Requires
        the ``administrator`` permission.

        Args:
            ctx: The command invocation context.
            membre: The member whose XP to set.
            xp: The new total XP value (must be >= 0).
        """
        if xp < 0:
            return await ctx.send(f"{Emojis.ERROR} L'XP ne peut pas être négatif.")

        user_data = await db.get_or_create_user(membre.id, ctx.guild.id)
        new_level, remaining_xp = self.calculate_level_from_xp(xp)

        # Directly update the database with the new XP, total_xp, and level
        async with db.aiosqlite.connect(db.db_path) as conn:
            await conn.execute("""
                UPDATE users SET xp = ?, total_xp = ?, level = ?
                WHERE user_id = ? AND guild_id = ?
            """, (remaining_xp, xp, new_level, membre.id, ctx.guild.id))
            await conn.commit()

        # Synchronize level roles with the new level
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
        """[Admin] Add (or subtract) XP from a member's total.

        Accepts negative values to remove XP. The total XP is clamped to a
        minimum of 0 to prevent negative totals. Recalculates level and
        synchronizes level roles after the change.

        Args:
            ctx: The command invocation context.
            membre: The member whose XP to modify.
            xp: The amount of XP to add (positive) or remove (negative).
        """
        user_data = await db.get_or_create_user(membre.id, ctx.guild.id)
        # Clamp to 0 to prevent negative total XP
        new_total = max(0, user_data['total_xp'] + xp)
        new_level, remaining_xp = self.calculate_level_from_xp(new_total)

        # Update the database with recalculated values
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
        """[Admin] Configure a role reward for reaching a specific level.

        When a member reaches the specified level, they will automatically
        receive the given role. This mapping is stored in the database and
        applied by the ``check_and_assign_level_roles`` method.

        Args:
            ctx: The command invocation context.
            niveau: The level at which the role should be awarded (must be >= 1).
            role: The Discord role to assign as a reward.
        """
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
        """Display all configured level-role reward mappings for this server.

        Lists each level threshold and its associated Discord role. Roles
        that have been deleted from the server are silently omitted.

        Args:
            ctx: The command invocation context.
        """
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
    """Entry point for loading this cog into the bot.

    Called by ``bot.load_extension('cogs.leveling')``.

    Args:
        bot: The Discord bot instance to attach the cog to.
    """
    await bot.add_cog(Leveling(bot))
