"""
Advanced moderation cog with automatic moderation (auto-mod) capabilities.

This module provides two main components:

1. **AutoMod**: An automatic moderation engine that detects rule violations in
   real-time, including spam detection, mention spam, banned words, excessive
   caps usage, and unauthorized Discord invite links.

2. **Moderation**: A Discord cog that integrates AutoMod with manual moderation
   commands (ban, kick, mute, warn, purge, slowmode, lock/unlock) and provides
   logging of all moderation actions to a configured log channel.

The auto-mod system processes every non-bot, non-admin message and checks it
against multiple violation rules. Detected violations trigger automatic message
deletion, user warnings, and log entries.
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
    """Automatic moderation engine that detects various message-based rule violations.

    This class maintains in-memory caches of recent messages and mentions per user
    to detect spam patterns. It also provides static checks for banned words,
    excessive capitalization, and Discord invite links.

    The caches are time-windowed: entries older than the configured interval
    are automatically pruned on each check call, so memory usage stays bounded.

    Attributes:
        message_cache: Per-user cache of recent messages as ``{user_id: [(timestamp, content), ...]}``.
            Used for spam detection within the configured SPAM_INTERVAL window.
        mention_cache: Per-user cache of recent mention timestamps as ``{user_id: [timestamps]}``.
            Used for mention-spam detection within a 10-second sliding window.
        caps_pattern: Compiled regex for matching uppercase letters.
        link_pattern: Compiled regex for matching HTTP/HTTPS URLs.
        invite_pattern: Compiled regex for matching Discord invite links
            (both discord.gg and discordapp.com/invite formats).
    """

    def __init__(self):
        self.message_cache = defaultdict(list)  # {user_id: [(timestamp, content), ...]}
        self.mention_cache = defaultdict(list)  # {user_id: [timestamps]}
        self.caps_pattern = re.compile(r'[A-Z]')
        self.link_pattern = re.compile(r'https?://\S+')
        self.invite_pattern = re.compile(r'discord(?:\.gg|app\.com/invite)/[\w-]+')

    def check_spam(self, user_id: int, content: str) -> bool:
        """Check whether a user is sending messages too rapidly (spamming).

        Maintains a sliding time window of recent messages per user. Messages
        older than SPAM_INTERVAL seconds are pruned, then the new message is
        appended. If the total count meets or exceeds SPAM_THRESHOLD, the user
        is considered to be spamming.

        Args:
            user_id: The Discord user ID to check.
            content: The message content (stored in cache for potential future use).

        Returns:
            True if the user's message count within the spam interval meets or
            exceeds the spam threshold, False otherwise.
        """
        now = datetime.now()
        # Prune messages that have aged out of the sliding time window
        self.message_cache[user_id] = [
            (ts, msg) for ts, msg in self.message_cache[user_id]
            if (now - ts).total_seconds() < SPAM_INTERVAL
        ]
        self.message_cache[user_id].append((now, content))
        return len(self.message_cache[user_id]) >= SPAM_THRESHOLD

    def check_mention_spam(self, user_id: int, mention_count: int) -> bool:
        """Check whether a user is spamming mentions (mass-pinging).

        Uses a 10-second sliding window. If a single message contains fewer
        than 5 mentions, it is ignored entirely. Otherwise, each mention is
        recorded as a separate timestamp entry. If the user accumulates 10 or
        more mention events within the 10-second window, it is flagged as
        mention spam.

        Args:
            user_id: The Discord user ID to check.
            mention_count: The number of user mentions in the current message.

        Returns:
            True if the user has 10 or more mentions within the last 10 seconds,
            False otherwise.
        """
        # Ignore messages with fewer than 5 mentions (not suspicious enough)
        if mention_count < 5:
            return False
        now = datetime.now()
        # Record one timestamp entry per mention in the message
        for _ in range(mention_count):
            self.mention_cache[user_id].append(now)
        # Prune entries older than the 10-second detection window
        self.mention_cache[user_id] = [
            ts for ts in self.mention_cache[user_id]
            if (now - ts).total_seconds() < 10
        ]
        return len(self.mention_cache[user_id]) >= 10

    def check_banned_words(self, content: str) -> Optional[str]:
        """Check whether the message contains any banned words.

        Performs a case-insensitive substring match against each word in the
        BANNED_WORDS list from the bot configuration.

        Args:
            content: The message content to scan.

        Returns:
            The first banned word found in the content, or None if no
            banned words are detected.
        """
        content_lower = content.lower()
        for word in BANNED_WORDS:
            if word.lower() in content_lower:
                return word
        return None

    def check_excessive_caps(self, content: str, threshold: float = 0.7) -> bool:
        """Check whether the message uses an excessive proportion of uppercase letters.

        Messages shorter than 10 characters are exempt from this check to avoid
        false positives on short messages like "OK" or "LOL".

        Args:
            content: The message content to analyze.
            threshold: The minimum ratio of uppercase letters to total letters
                that triggers a violation. Defaults to 0.7 (70%).

        Returns:
            True if the uppercase ratio meets or exceeds the threshold,
            False otherwise (including for short or non-alphabetic messages).
        """
        # Short messages are exempt to avoid false positives
        if len(content) < 10:
            return False
        letters = [c for c in content if c.isalpha()]
        if not letters:
            return False
        caps_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        return caps_ratio >= threshold

    def check_invite_link(self, content: str) -> bool:
        """Check whether the message contains a Discord invite link.

        Matches both ``discord.gg/xxx`` and ``discordapp.com/invite/xxx`` formats.

        Args:
            content: The message content to scan.

        Returns:
            True if a Discord invite link is found, False otherwise.
        """
        return bool(self.invite_pattern.search(content))


class Moderation(commands.Cog):
    """Discord cog providing moderation tools and automatic moderation.

    Combines the AutoMod engine for real-time message scanning with manual
    moderation commands available to server staff. All moderation actions
    (both automatic and manual) are logged to the guild's configured log channel.

    Available commands:
        - ban: Permanently ban a member from the server.
        - kick: Remove a member from the server (they can rejoin).
        - mute/timeout: Temporarily prevent a member from sending messages.
        - unmute: Remove a mute/timeout from a member.
        - warn: Issue a formal warning (auto-mutes at threshold).
        - warnings: View a member's warning history.
        - clearwarnings: Clear all warnings for a member (admin only).
        - purge: Bulk-delete messages from a channel.
        - slowmode: Set a channel's slowmode delay.
        - lock/unlock: Prevent or allow the @everyone role from sending messages.

    Attributes:
        bot: The Discord bot instance.
        automod: The AutoMod engine instance used for real-time message checks.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.automod = AutoMod()

    async def log_action(self, guild: discord.Guild, embed: discord.Embed):
        """Send a moderation log embed to the guild's configured log channel.

        Silently does nothing if no log channel is configured, if the channel
        no longer exists, or if the bot lacks permission to send messages there.

        Args:
            guild: The Discord guild where the action occurred.
            embed: The embed containing details of the moderation action.
        """
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
        """Retrieve the guild's mute role, creating one if it does not exist.

        First checks the database for a stored mute role ID. If the role exists
        in the guild, it is returned. Otherwise, a new "Muted" role is created
        with send_messages and speak permissions denied across all channels, and
        its ID is saved to the database for future use.

        Args:
            guild: The Discord guild to get or create the mute role for.

        Returns:
            The mute role if found or successfully created, or None if the bot
            lacks the necessary permissions to create a role.
        """
        config = await db.get_guild_config(guild.id)
        mute_role_id = config.get('mute_role_id')

        if mute_role_id:
            role = guild.get_role(mute_role_id)
            if role:
                return role

        # No existing mute role found; create a new one
        try:
            role = await guild.create_role(
                name="Muted",
                color=discord.Color.dark_gray(),
                reason="Auto-created mute role"
            )

            # Deny send_messages and speak in all existing channels
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
        """Automatically moderate incoming messages using the AutoMod engine.

        Runs every non-bot, non-DM message through a series of violation checks.
        Administrators are exempt from all checks. If auto-mod is disabled in the
        guild configuration, the listener returns early.

        Detected violations trigger message deletion (where applicable), a
        temporary warning embed sent to the channel (auto-deletes after 10s),
        and a detailed log entry to the guild's log channel.

        Args:
            message: The incoming Discord message to check.
        """
        # Skip bot messages and DMs (auto-mod only applies in guilds)
        if message.author.bot or not message.guild:
            return
        # Administrators are exempt from auto-moderation
        if message.author.guild_permissions.administrator:
            return

        config = await db.get_guild_config(message.guild.id)
        if not config.get('auto_mod_enabled', True):
            return

        violations = []

        # Check for banned/forbidden words
        banned_word = self.automod.check_banned_words(message.content)
        if banned_word:
            violations.append(f"Mot interdit détecté")
            try:
                await message.delete()
            except discord.Forbidden:
                pass

        # Check for rapid message spam
        if self.automod.check_spam(message.author.id, message.content):
            violations.append("Spam détecté")
            try:
                await message.delete()
            except discord.Forbidden:
                pass

        # Check for mass mention spam
        if self.automod.check_mention_spam(message.author.id, len(message.mentions)):
            violations.append("Spam de mentions")
            try:
                await message.delete()
            except discord.Forbidden:
                pass

        # Check for unauthorized Discord invite links
        if self.automod.check_invite_link(message.content):
            violations.append("Lien d'invitation non autorisé")
            try:
                await message.delete()
            except discord.Forbidden:
                pass

        # Check for excessive use of capital letters
        if self.automod.check_excessive_caps(message.content):
            violations.append("Usage excessif de majuscules")

        # Process any accumulated violations
        if violations:
            # Send a temporary warning embed to the channel (auto-deletes after 10s)
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

            # Send a detailed log entry to the moderation log channel
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
        """Ban a member from the server.

        Requires the ``ban_members`` permission. Enforces role hierarchy: you
        cannot ban a member whose highest role is equal to or above your own,
        unless you are the server owner.

        Args:
            ctx: The command invocation context.
            membre: The member to ban.
            raison: Optional reason for the ban (shown in audit log and embed).
        """
        # Role hierarchy check: prevent banning members with equal or higher roles
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

            # Log the ban action to the moderation log channel
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
        """Kick (remove) a member from the server.

        The member can rejoin using an invite link. Requires the ``kick_members``
        permission. Enforces role hierarchy the same way as the ban command.

        Args:
            ctx: The command invocation context.
            membre: The member to kick.
            raison: Optional reason for the kick (shown in audit log and embed).
        """
        # Role hierarchy check: prevent kicking members with equal or higher roles
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

            # Log the kick action to the moderation log channel
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
        """Mute a member using Discord's native timeout feature.

        Applies a timeout that prevents the member from sending messages,
        reacting, or joining voice channels for the specified duration.
        Requires the ``moderate_members`` permission. Discord limits timeouts
        to a maximum of 28 days (40,320 minutes).

        Args:
            ctx: The command invocation context.
            membre: The member to mute.
            duree: Duration of the mute in minutes. Defaults to 60.
                Must not exceed 40320 (28 days).
            raison: Optional reason for the mute (shown in audit log and embed).
        """
        # Role hierarchy check
        if membre.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send(f"{Emojis.ERROR} Vous ne pouvez pas mute ce membre.")

        # Discord timeout maximum is 28 days (40320 minutes)
        if duree > 40320:
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

            # Log the mute action to the moderation log channel
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
        """Remove a mute (timeout) from a member.

        Clears the member's Discord timeout, immediately restoring their ability
        to send messages, react, and join voice channels.

        Args:
            ctx: The command invocation context.
            membre: The member to unmute.
        """
        try:
            # Passing None removes the timeout entirely
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
        """Issue a formal warning to a member.

        Warnings are stored in the database and accumulate. When a member reaches
        the configured WARN_THRESHOLD, they are automatically muted for the
        MUTE_DURATION period. Requires the ``manage_messages`` permission.

        Args:
            ctx: The command invocation context.
            membre: The member to warn.
            raison: Optional reason for the warning.
        """
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

        # Auto-mute if the member has reached the warning threshold
        if warn_count >= WARN_THRESHOLD:
            try:
                until = datetime.now() + timedelta(seconds=MUTE_DURATION)
                await membre.timeout(until, reason=f"Atteint {WARN_THRESHOLD} avertissements")
                await ctx.send(
                    f"{Emojis.WARNING} {membre.mention} a atteint {WARN_THRESHOLD} avertissements et a été mute automatiquement."
                )
            except discord.Forbidden:
                pass

        # Log the warning to the moderation log channel
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
        """Display the warning history for a member.

        Shows up to 10 most recent warnings with dates, reasons, and the
        moderator who issued each one. If no member is specified, shows the
        invoking user's own warnings.

        Args:
            ctx: The command invocation context.
            membre: The member whose warnings to view. Defaults to the command author.
        """
        member = membre or ctx.author
        warnings = await db.get_warnings(member.id, ctx.guild.id)

        embed = discord.Embed(
            title=f"{Emojis.WARNING} Avertissements de {member.display_name}",
            color=Colors.WARNING
        )

        if not warnings:
            embed.description = "Aucun avertissement."
        else:
            # Display at most 10 warnings to avoid exceeding embed field limits
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
        """[Admin] Clear all warnings for a member.

        Permanently removes all warning records for the specified member in
        this guild. Requires the ``administrator`` permission.

        Args:
            ctx: The command invocation context.
            membre: The member whose warnings should be cleared.
        """
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
        """Bulk-delete messages from the current channel.

        Deletes up to 100 messages at once. The command's own invocation message
        is also deleted (hence ``limit=nombre + 1``). A confirmation message is
        shown briefly (auto-deletes after 5 seconds). Requires ``manage_messages``.

        Args:
            ctx: The command invocation context.
            nombre: Number of messages to delete (1-100).
        """
        if nombre < 1 or nombre > 100:
            return await ctx.send(f"{Emojis.ERROR} Le nombre doit être entre 1 et 100.")

        try:
            # +1 to also delete the command invocation message itself
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
        """Set or disable slowmode for the current channel.

        Slowmode restricts how often users can send messages by enforcing a
        delay between posts. Pass 0 to disable. Discord's maximum slowmode
        is 21600 seconds (6 hours). Requires ``manage_channels`` permission.

        Args:
            ctx: The command invocation context.
            secondes: Slowmode delay in seconds (0 to disable, max 21600).
        """
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
        """Lock the current channel, preventing @everyone from sending messages.

        Modifies the channel's permission overwrites for the guild's default
        role to deny ``send_messages``. Staff with explicit permission
        overwrites can still send messages. Requires ``manage_channels``.

        Args:
            ctx: The command invocation context.
        """
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
        """Unlock the current channel, allowing @everyone to send messages again.

        Restores the ``send_messages`` permission for the guild's default role.
        Requires ``manage_channels`` permission.

        Args:
            ctx: The command invocation context.
        """
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
    """Entry point for loading this cog into the bot.

    Called by ``bot.load_extension('cogs.moderation')``.

    Args:
        bot: The Discord bot instance to attach the cog to.
    """
    await bot.add_cog(Moderation(bot))
