"""
Welcome and goodbye messages cog for the Discord bot.

Handles automatic greeting and farewell messages when members join or leave
the server. Also manages a daily scheduled greeting message sent at the
configured hour. Server administrators can customize the welcome/goodbye
channel, welcome message template (with placeholder variables), and goodbye
message template through dedicated commands.

Key features:
- Customizable welcome messages with ``{user}``, ``{server}``, and
  ``{member_count}`` placeholders.
- Customizable goodbye messages with ``{user}`` and ``{server}`` placeholders.
- Optional DM sent to new members upon joining.
- Daily scheduled greeting message via APScheduler.
- Test command to preview the welcome message without a real join event.
"""
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from typing import Optional

from config import Colors, Emojis, DEFAULT_CHANNEL_ID, SEND_HOUR
from utils.database import db


class Welcome(commands.Cog):
    """Cog for welcome/goodbye messages and daily scheduled greetings.

    Listens for member join and leave events to send customizable
    notification embeds to a configured channel. Also runs a daily
    scheduled job that posts a morning greeting at the configured hour.

    Attributes:
        bot: The bot instance this cog is attached to.
        scheduler: APScheduler instance managing the daily message cron job.
    """

    def __init__(self, bot: commands.Bot):
        """Initialize the Welcome cog with the APScheduler instance.

        Args:
            bot: The bot instance to bind this cog to.
        """
        self.bot = bot
        self.scheduler = AsyncIOScheduler()

    async def cog_load(self):
        """Start the APScheduler when the cog is loaded.

        Registers a cron job that fires ``send_daily_message`` at the hour
        defined by the ``SEND_HOUR`` configuration constant.
        """
        self.scheduler.add_job(self.send_daily_message, 'cron', hour=SEND_HOUR)
        self.scheduler.start()

    async def cog_unload(self):
        """Shut down the APScheduler when the cog is unloaded."""
        self.scheduler.shutdown()

    async def send_daily_message(self):
        """Send a daily greeting message to every guild's configured channel.

        Iterates over all guilds the bot is in, looks up the welcome channel
        (falling back to ``DEFAULT_CHANNEL_ID``), and posts a simple
        "good morning" embed. Silently skips guilds where the channel is
        missing or the bot lacks send permissions.
        """
        for guild in self.bot.guilds:
            config = await db.get_guild_config(guild.id)
            channel_id = config.get('welcome_channel_id') or DEFAULT_CHANNEL_ID
            channel = guild.get_channel(channel_id)
            if channel:
                try:
                    embed = discord.Embed(
                        title="Bonjour!",
                        description="Passez une excellente journée!",
                        color=Colors.PRIMARY,
                        timestamp=datetime.now()
                    )
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Send a welcome message when a new (non-bot) member joins the server.

        Looks up the guild's welcome channel and message template from the
        database, replaces placeholder variables, and posts a welcome embed.
        Also attempts to send a private DM welcome to the new member.

        Placeholder variables supported in the welcome message template:
        - ``{user}`` -- replaced with the member's mention
        - ``{server}`` -- replaced with the guild name
        - ``{member_count}`` -- replaced with the current member count

        Args:
            member: The member who just joined the guild.
        """
        if member.bot:
            return

        config = await db.get_guild_config(member.guild.id)
        channel_id = config.get('welcome_channel_id')

        if not channel_id:
            return

        channel = member.guild.get_channel(channel_id)
        if not channel:
            return

        # Build the welcome message by replacing template placeholders
        welcome_msg = config.get('welcome_message', 'Bienvenue {user} sur {server}!')
        welcome_msg = welcome_msg.replace('{user}', member.mention)
        welcome_msg = welcome_msg.replace('{server}', member.guild.name)
        welcome_msg = welcome_msg.replace('{member_count}', str(member.guild.member_count))

        embed = discord.Embed(
            title=f"Bienvenue sur {member.guild.name}!",
            description=welcome_msg,
            color=Colors.SUCCESS,
            timestamp=datetime.now()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Membre #", value=str(member.guild.member_count), inline=True)
        embed.set_footer(text=f"ID: {member.id}")

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass

        # Attempt to send a private DM welcome (optional; silently fails if DMs are disabled)
        try:
            dm_embed = discord.Embed(
                title=f"Bienvenue sur {member.guild.name}!",
                description=f"Nous sommes ravis de t'accueillir parmi nous!\n\n"
                            f"N'hésite pas à consulter les règles et à te présenter.",
                color=Colors.PRIMARY
            )
            dm_embed.set_thumbnail(url=member.guild.icon.url if member.guild.icon else None)
            await member.send(embed=dm_embed)
        except discord.Forbidden:
            pass  # The user has DMs disabled -- nothing we can do

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Send a goodbye message when a (non-bot) member leaves the server.

        Uses the guild's configured goodbye message template with placeholder
        variables and posts it to the welcome channel.

        Placeholder variables supported in the goodbye message template:
        - ``{user}`` -- replaced with the member's username string
        - ``{server}`` -- replaced with the guild name

        Args:
            member: The member who just left or was removed from the guild.
        """
        if member.bot:
            return

        config = await db.get_guild_config(member.guild.id)
        channel_id = config.get('welcome_channel_id')

        if not channel_id:
            return

        channel = member.guild.get_channel(channel_id)
        if not channel:
            return

        goodbye_msg = config.get('goodbye_message', '{user} a quitté le serveur.')
        goodbye_msg = goodbye_msg.replace('{user}', str(member))
        goodbye_msg = goodbye_msg.replace('{server}', member.guild.name)

        embed = discord.Embed(
            title="Au revoir!",
            description=goodbye_msg,
            color=Colors.ERROR,
            timestamp=datetime.now()
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass

    @commands.hybrid_command(name="setwelcome")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(channel="Le channel pour les messages de bienvenue")
    async def setwelcome(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set the channel where welcome and goodbye messages are sent (admin only).

        Args:
            ctx: The invocation context.
            channel: The text channel to designate as the welcome channel.
        """
        await db.update_guild_config(ctx.guild.id, welcome_channel_id=channel.id)

        embed = discord.Embed(
            title=f"{Emojis.SUCCESS} Channel de bienvenue configuré",
            description=f"Les messages de bienvenue seront envoyés dans {channel.mention}",
            color=Colors.SUCCESS
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="setwelcomemsg")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(message="Le message de bienvenue ({user}, {server}, {member_count})")
    async def setwelcomemsg(self, ctx: commands.Context, *, message: str):
        """Set a custom welcome message template (admin only).

        The message may contain placeholder variables that are replaced at
        send time: ``{user}`` (member mention), ``{server}`` (guild name),
        ``{member_count}`` (current member count). A preview with the
        placeholders filled in is shown after saving.

        Args:
            ctx: The invocation context.
            message: The welcome message template string.
        """
        await db.update_guild_config(ctx.guild.id, welcome_message=message)

        # Generate a preview by filling in the template with current context
        preview = message.replace('{user}', ctx.author.mention)
        preview = preview.replace('{server}', ctx.guild.name)
        preview = preview.replace('{member_count}', str(ctx.guild.member_count))

        embed = discord.Embed(
            title=f"{Emojis.SUCCESS} Message de bienvenue configuré",
            description=f"**Aperçu:**\n{preview}",
            color=Colors.SUCCESS
        )
        embed.set_footer(text="Variables: {user}, {server}, {member_count}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="setgoodbyemsg")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(message="Le message de départ ({user}, {server})")
    async def setgoodbyemsg(self, ctx: commands.Context, *, message: str):
        """Set a custom goodbye message template (admin only).

        Supports ``{user}`` (member username) and ``{server}`` (guild name)
        placeholders. A preview is shown after saving.

        Args:
            ctx: The invocation context.
            message: The goodbye message template string.
        """
        await db.update_guild_config(ctx.guild.id, goodbye_message=message)

        # Generate a preview by filling in the template with current context
        preview = message.replace('{user}', str(ctx.author))
        preview = preview.replace('{server}', ctx.guild.name)

        embed = discord.Embed(
            title=f"{Emojis.SUCCESS} Message de départ configuré",
            description=f"**Aperçu:**\n{preview}",
            color=Colors.SUCCESS
        )
        embed.set_footer(text="Variables: {user}, {server}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="testwelcome")
    @commands.has_permissions(administrator=True)
    async def testwelcome(self, ctx: commands.Context):
        """Preview the welcome message without a real member join (admin only).

        Simulates a member joining by using the command author's information
        to fill in the welcome message template placeholders. The embed title
        is prefixed with ``[TEST]`` to distinguish it from real welcome messages.

        Args:
            ctx: The invocation context.
        """
        # Simulate a join event using the invoking user's data
        config = await db.get_guild_config(ctx.guild.id)

        welcome_msg = config.get('welcome_message', 'Bienvenue {user} sur {server}!')
        welcome_msg = welcome_msg.replace('{user}', ctx.author.mention)
        welcome_msg = welcome_msg.replace('{server}', ctx.guild.name)
        welcome_msg = welcome_msg.replace('{member_count}', str(ctx.guild.member_count))

        embed = discord.Embed(
            title=f"[TEST] Bienvenue sur {ctx.guild.name}!",
            description=welcome_msg,
            color=Colors.SUCCESS,
            timestamp=datetime.now()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.add_field(name="Membre #", value=str(ctx.guild.member_count), inline=True)
        embed.set_footer(text=f"ID: {ctx.author.id}")

        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    """Load the Welcome cog into the bot.

    Args:
        bot: The bot instance to register the cog with.
    """
    await bot.add_cog(Welcome(bot))
