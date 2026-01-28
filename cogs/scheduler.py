"""
Cog pour les messages programmés et les annonces automatiques.
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
    """Gestion des messages programmés et annonces automatiques."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.scheduler = AsyncIOScheduler()
        self.scheduled_jobs = {}  # {guild_id: {job_name: job}}

    async def cog_load(self):
        """Démarrer le scheduler au chargement du cog."""
        # Message quotidien par défaut
        self.scheduler.add_job(
            self.send_daily_message,
            CronTrigger(hour=SEND_HOUR, minute=0),
            id="daily_morning_message",
            replace_existing=True
        )

        # Vérifier les messages programmés en base toutes les minutes
        self.scheduler.add_job(
            self.check_scheduled_messages,
            CronTrigger(minute="*"),
            id="check_scheduled",
            replace_existing=True
        )

        self.scheduler.start()

    async def cog_unload(self):
        """Arrêter le scheduler au déchargement."""
        self.scheduler.shutdown(wait=False)

    async def send_daily_message(self):
        """Envoie le message quotidien à tous les serveurs configurés."""
        for guild in self.bot.guilds:
            try:
                config = await db.get_guild_config(guild.id)
                channel_id = config.get('daily_channel_id') or config.get('welcome_channel_id')

                if not channel_id:
                    # Essayer de trouver un channel général
                    channel = discord.utils.get(guild.text_channels, name='général')
                    if not channel:
                        channel = discord.utils.get(guild.text_channels, name='general')
                    if not channel and guild.text_channels:
                        channel = guild.text_channels[0]
                else:
                    channel = guild.get_channel(channel_id)

                if channel:
                    # Message du matin personnalisé
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
        """Retourne un message quotidien par défaut."""
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
        """Vérifie et envoie les messages programmés."""
        # Cette fonction peut être étendue pour gérer des messages
        # programmés personnalisés stockés en base de données
        pass

    @commands.hybrid_group(name="schedule", aliases=["programme", "planifier"])
    @commands.has_permissions(administrator=True)
    async def schedule(self, ctx: commands.Context):
        """Commandes de gestion des messages programmés."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @schedule.command(name="daily")
    @app_commands.describe(channel="Le channel pour les messages quotidiens")
    async def schedule_daily(self, ctx: commands.Context, channel: discord.TextChannel):
        """Configure le channel pour les messages quotidiens."""
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
        """Configure le message quotidien personnalisé."""
        await db.update_guild_config(ctx.guild.id, daily_message=message)

        embed = discord.Embed(
            title=f"{Emojis.SUCCESS} Message quotidien configuré",
            description=f"**Nouveau message:**\n{message}",
            color=Colors.SUCCESS
        )
        await ctx.send(embed=embed)

    @schedule.command(name="test")
    async def schedule_test(self, ctx: commands.Context):
        """Envoie un message de test."""
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
        """Programme une annonce unique."""
        try:
            hour, minute = map(int, heure.split(":"))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError()
        except ValueError:
            return await ctx.send(f"{Emojis.ERROR} Format d'heure invalide. Utilisez HH:MM")

        now = datetime.now()
        scheduled_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        if scheduled_time <= now:
            # Si l'heure est passée, programmer pour demain
            from datetime import timedelta
            scheduled_time += timedelta(days=1)

        # Programmer l'annonce
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
        """Envoie une annonce programmée."""
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
        """Programme un message récurrent."""
        try:
            hour, minute = map(int, heure.split(":"))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError()
        except ValueError:
            return await ctx.send(f"{Emojis.ERROR} Format d'heure invalide. Utilisez HH:MM")

        # Convertir les jours
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
        """Affiche les messages programmés."""
        jobs = self.scheduler.get_jobs()
        guild_jobs = [j for j in jobs if str(ctx.guild.id) in j.id or j.id in ["daily_morning_message"]]

        embed = discord.Embed(
            title="Messages programmés",
            color=Colors.PRIMARY
        )

        if not guild_jobs:
            embed.description = "Aucun message programmé."
        else:
            for job in guild_jobs[:10]:
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
        """Annule un message programmé."""
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
    await bot.add_cog(ScheduledMessages(bot))
