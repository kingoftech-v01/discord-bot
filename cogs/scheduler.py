"""
Scheduled messages cog for the Discord bot.

Uses APScheduler to manage automated messaging tasks including daily morning
greetings, one-time scheduled announcements, and recurring messages on
specific days and times. Administrators can configure the daily channel,
customize the daily message, schedule one-off or recurring announcements,
list all active jobs, and cancel them by ID.

The scheduler runs two default jobs on cog load:
1. A daily morning message sent at the hour defined by ``SEND_HOUR``.
2. A per-minute check for database-stored scheduled messages (extensible
   hook for future persistence of custom scheduled messages).
"""
import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, time
from typing import Optional
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import Colors, Emojis, SEND_HOUR, DEFAULT_CHANNEL_ID
from utils.database import db


class ScheduledMessages(commands.Cog):
    """Cog for managing scheduled and recurring automated messages.

    Wraps APScheduler's ``AsyncIOScheduler`` to provide Discord-friendly
    scheduling of daily greetings, one-time announcements at a specified
    time, and recurring messages on specific days of the week.

    Attributes:
        bot: The bot instance this cog is attached to.
        scheduler: The APScheduler ``AsyncIOScheduler`` instance managing
            all scheduled jobs.
        scheduled_jobs: Reserved dictionary for future per-guild job
            tracking (currently unused).
    """

    def __init__(self, bot: commands.Bot):
        """Initialize the ScheduledMessages cog.

        Args:
            bot: The bot instance to bind this cog to.
        """
        self.bot = bot
        self.scheduler = AsyncIOScheduler()
        self.scheduled_jobs = {}  # {guild_id: {job_name: job}} -- reserved for future use

    async def cog_load(self):
        """Start the APScheduler and register default jobs when the cog loads.

        Registers two default jobs:
        - ``daily_morning_message``: Fires at ``SEND_HOUR:00`` to send daily
          greetings to all configured guilds.
        - ``check_scheduled``: Fires every minute to check for database-stored
          scheduled messages (extensibility hook).
        """
        # Default daily morning greeting job
        self.scheduler.add_job(
            self.send_daily_message,
            CronTrigger(hour=SEND_HOUR, minute=0),
            id="daily_morning_message",
            replace_existing=True
        )

        # Per-minute check for database-stored scheduled messages
        self.scheduler.add_job(
            self.check_scheduled_messages,
            CronTrigger(minute="*"),
            id="check_scheduled",
            replace_existing=True
        )

        self.scheduler.start()

    async def cog_unload(self):
        """Shut down the APScheduler immediately when the cog is unloaded."""
        self.scheduler.shutdown(wait=False)

    async def send_daily_message(self):
        """Send the daily morning greeting to all configured guilds.

        For each guild the bot is in, attempts to find the best channel in
        this order of priority:
        1. The guild's configured ``daily_channel_id``.
        2. The guild's configured ``welcome_channel_id``.
        3. A text channel named "general" (French or English).
        4. The first available text channel as a last resort.

        Uses the guild's custom daily message if set, otherwise picks a
        random default greeting from ``get_default_daily_message()``.
        """
        for guild in self.bot.guilds:
            try:
                config = await db.get_guild_config(guild.id)
                channel_id = config.get('daily_channel_id') or config.get('welcome_channel_id')

                if not channel_id:
                    # Fallback: try to find a "general" channel by name
                    channel = discord.utils.get(guild.text_channels, name='général')
                    if not channel:
                        channel = discord.utils.get(guild.text_channels, name='general')
                    # Last resort: use the first text channel available
                    if not channel and guild.text_channels:
                        channel = guild.text_channels[0]
                else:
                    channel = guild.get_channel(channel_id)

                if channel:
                    # Use the custom daily message or a random default
                    daily_msg = config.get('daily_message') or self.get_default_daily_message()

                    embed = discord.Embed(
                        title="Bonjour à tous!",
                        description=daily_msg,
                        color=Colors.PRIMARY,
                        timestamp=datetime.now()
                    )
                    embed.set_footer(text=f"Message automatique • {guild.name}")

                    await channel.send(embed=embed)
            except Exception as e:
                print(f"Erreur message quotidien pour {guild.name}: {e}")

    def get_default_daily_message(self) -> str:
        """Return a randomly selected default daily greeting message.

        Returns:
            A motivational French greeting string chosen at random from
            a predefined list of five messages.
        """
        messages = [
            "Passez une excellente journée! N'oubliez pas de rester positif et de vous entraider.",
            "Nouvelle journée, nouvelles opportunités! Qu'allez-vous accomplir aujourd'hui?",
            "Bonjour la communauté! Prêts pour une journée productive?",
            "Le soleil se lève sur notre serveur! Bonne journée à tous les membres!",
            "Un nouveau jour commence! N'hésitez pas à discuter et à partager vos idées!"
        ]
        from random import choice
        return choice(messages)

    async def check_scheduled_messages(self):
        """Check for and send database-stored scheduled messages.

        This is an extensibility hook that runs every minute. Currently a
        no-op placeholder; can be extended to query the database for
        custom scheduled messages and dispatch them.
        """
        # Extensibility hook: query db for custom scheduled messages here
        pass

    @commands.hybrid_group(name="schedule", aliases=["programme", "planifier"])
    @commands.has_permissions(administrator=True)
    async def schedule(self, ctx: commands.Context):
        """Command group for managing scheduled messages (admin only).

        When invoked without a subcommand, displays the group's help page
        listing all available scheduling subcommands.

        Args:
            ctx: The invocation context.
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @schedule.command(name="daily")
    @app_commands.describe(channel="Le channel pour les messages quotidiens")
    async def schedule_daily(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set the channel for daily morning greeting messages.

        The daily message will be sent at the hour defined by ``SEND_HOUR``
        in the bot configuration.

        Args:
            ctx: The invocation context.
            channel: The text channel to receive daily messages.
        """
        await db.update_guild_config(ctx.guild.id, daily_channel_id=channel.id)

        embed = discord.Embed(
            title=f"{Emojis.SUCCESS} Channel quotidien configuré",
            description=f"Les messages quotidiens seront envoyés dans {channel.mention} à {SEND_HOUR}h00.",
            color=Colors.SUCCESS
        )
        await ctx.send(embed=embed)

    @schedule.command(name="message")
    @app_commands.describe(message="Le message quotidien personnalisé")
    async def schedule_message(self, ctx: commands.Context, *, message: str):
        """Set a custom daily morning greeting message for this server.

        Replaces the default random greeting with a fixed custom message.

        Args:
            ctx: The invocation context.
            message: The custom daily message text.
        """
        await db.update_guild_config(ctx.guild.id, daily_message=message)

        embed = discord.Embed(
            title=f"{Emojis.SUCCESS} Message quotidien configuré",
            description=f"**Nouveau message:**\n{message}",
            color=Colors.SUCCESS
        )
        await ctx.send(embed=embed)

    @schedule.command(name="test")
    async def schedule_test(self, ctx: commands.Context):
        """Send a test daily message to the current channel for preview.

        Uses the guild's custom daily message if configured, otherwise
        picks a random default greeting.

        Args:
            ctx: The invocation context.
        """
        config = await db.get_guild_config(ctx.guild.id)
        daily_msg = config.get('daily_message') or self.get_default_daily_message()

        embed = discord.Embed(
            title="Bonjour à tous!",
            description=daily_msg,
            color=Colors.PRIMARY,
            timestamp=datetime.now()
        )
        embed.set_footer(text=f"Message automatique • {ctx.guild.name}")

        await ctx.send(embed=embed)

    @schedule.command(name="announce")
    @app_commands.describe(
        channel="Le channel où envoyer",
        heure="Heure (format HH:MM)",
        message="Le message à envoyer"
    )
    async def schedule_announce(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel,
        heure: str,
        *,
        message: str
    ):
        """Schedule a one-time announcement at a specific time today or tomorrow.

        If the specified time has already passed today, the announcement is
        automatically scheduled for the same time tomorrow. The job ID is
        derived from the guild ID and the target timestamp.

        Args:
            ctx: The invocation context.
            channel: The text channel where the announcement will be posted.
            heure: The target time in ``HH:MM`` (24-hour) format.
            message: The announcement message text.
        """
        try:
            hour, minute = map(int, heure.split(":"))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError()
        except ValueError:
            return await ctx.send(f"{Emojis.ERROR} Format d'heure invalide. Utilisez HH:MM")

        now = datetime.now()
        scheduled_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        # If the specified time has already passed today, schedule for tomorrow
        if scheduled_time <= now:
            from datetime import timedelta
            scheduled_time += timedelta(days=1)

        # Create a unique job ID from guild ID and target timestamp
        job_id = f"announce_{ctx.guild.id}_{scheduled_time.timestamp()}"

        self.scheduler.add_job(
            self.send_scheduled_announcement,
            'date',
            run_date=scheduled_time,
            args=[channel.id, message],
            id=job_id,
            replace_existing=True
        )

        embed = discord.Embed(
            title=f"{Emojis.SUCCESS} Annonce programmée",
            description=f"L'annonce sera envoyée dans {channel.mention}",
            color=Colors.SUCCESS
        )
        embed.add_field(name="Heure", value=scheduled_time.strftime("%d/%m/%Y à %H:%M"))
        embed.add_field(name="Message", value=message[:200] + "..." if len(message) > 200 else message)
        await ctx.send(embed=embed)

    async def send_scheduled_announcement(self, channel_id: int, message: str):
        """Callback to send a scheduled announcement embed to a channel.

        Called by APScheduler when a one-time or recurring announcement job
        fires. Silently does nothing if the channel no longer exists.

        Args:
            channel_id: The snowflake ID of the target text channel.
            message: The announcement message text.
        """
        channel = self.bot.get_channel(channel_id)
        if channel:
            embed = discord.Embed(
                title="Annonce",
                description=message,
                color=Colors.PRIMARY,
                timestamp=datetime.now()
            )
            await channel.send(embed=embed)

    @schedule.command(name="recurring")
    @app_commands.describe(
        channel="Le channel où envoyer",
        jours="Jours (lun,mar,mer,jeu,ven,sam,dim ou *)",
        heure="Heure (format HH:MM)",
        message="Le message à envoyer"
    )
    async def schedule_recurring(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel,
        jours: str,
        heure: str,
        *,
        message: str
    ):
        """Schedule a recurring message on specific days of the week.

        Days are specified using French abbreviations (``lun``, ``mar``,
        ``mer``, ``jeu``, ``ven``, ``sam``, ``dim``) separated by commas,
        or ``*`` for every day. They are converted to English abbreviations
        for the APScheduler ``CronTrigger``.

        Args:
            ctx: The invocation context.
            channel: The text channel where the message will be posted.
            jours: Comma-separated French day abbreviations or ``"*"``
                for every day.
            heure: The target time in ``HH:MM`` (24-hour) format.
            message: The message text to send on each occurrence.
        """
        try:
            hour, minute = map(int, heure.split(":"))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError()
        except ValueError:
            return await ctx.send(f"{Emojis.ERROR} Format d'heure invalide. Utilisez HH:MM")

        # Map French day abbreviations to English for APScheduler's CronTrigger
        day_map = {
            "lun": "mon", "mar": "tue", "mer": "wed", "jeu": "thu",
            "ven": "fri", "sam": "sat", "dim": "sun", "*": "*"
        }

        if jours == "*":
            day_of_week = "*"
        else:
            days = [d.strip().lower() for d in jours.split(",")]
            converted = []
            for d in days:
                if d not in day_map:
                    return await ctx.send(f"{Emojis.ERROR} Jour invalide: {d}")
                converted.append(day_map[d])
            day_of_week = ",".join(converted)

        # Build a deterministic job ID from guild, channel, and time
        job_id = f"recurring_{ctx.guild.id}_{channel.id}_{hour}_{minute}"

        self.scheduler.add_job(
            self.send_scheduled_announcement,
            CronTrigger(day_of_week=day_of_week, hour=hour, minute=minute),
            args=[channel.id, message],
            id=job_id,
            replace_existing=True
        )

        embed = discord.Embed(
            title=f"{Emojis.SUCCESS} Message récurrent programmé",
            description=f"Le message sera envoyé dans {channel.mention}",
            color=Colors.SUCCESS
        )
        embed.add_field(name="Jours", value=jours)
        embed.add_field(name="Heure", value=heure)
        embed.add_field(name="Message", value=message[:200] + "..." if len(message) > 200 else message, inline=False)
        await ctx.send(embed=embed)

    @schedule.command(name="list")
    async def schedule_list(self, ctx: commands.Context):
        """List all active scheduled jobs relevant to this server.

        Filters the scheduler's job list to show only jobs whose ID contains
        the current guild's ID or the global ``daily_morning_message`` job.
        Displays up to 10 jobs with their next scheduled run time.

        Args:
            ctx: The invocation context.
        """
        jobs = self.scheduler.get_jobs()
        # Filter to jobs belonging to this guild plus the global daily job
        guild_jobs = [j for j in jobs if str(ctx.guild.id) in j.id or j.id in ["daily_morning_message"]]

        embed = discord.Embed(
            title="Messages programmés",
            color=Colors.PRIMARY
        )

        if not guild_jobs:
            embed.description = "Aucun message programmé."
        else:
            for job in guild_jobs[:10]:  # Limit to 10 to avoid embed overflow
                next_run = job.next_run_time.strftime("%d/%m/%Y %H:%M") if job.next_run_time else "N/A"
                embed.add_field(
                    name=job.id[:50],
                    value=f"Prochaine exécution: {next_run}",
                    inline=False
                )

        await ctx.send(embed=embed)

    @schedule.command(name="cancel")
    @app_commands.describe(job_id="L'ID du job à annuler")
    async def schedule_cancel(self, ctx: commands.Context, job_id: str):
        """Cancel a scheduled job by its ID.

        The job ID can be found via the ``schedule list`` command. If the
        ID does not match any active job, an error message is shown.

        Args:
            ctx: The invocation context.
            job_id: The APScheduler job ID string to remove.
        """
        try:
            self.scheduler.remove_job(job_id)
            embed = discord.Embed(
                title=f"{Emojis.SUCCESS} Message annulé",
                description=f"Le message programmé `{job_id}` a été annulé.",
                color=Colors.SUCCESS
            )
        except Exception:
            embed = discord.Embed(
                title=f"{Emojis.ERROR} Erreur",
                description=f"Impossible de trouver le message programmé `{job_id}`.",
                color=Colors.ERROR
            )

        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    """Load the ScheduledMessages cog into the bot.

    Args:
        bot: The bot instance to register the cog with.
    """
    await bot.add_cog(ScheduledMessages(bot))
