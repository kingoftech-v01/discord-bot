"""
Cog pour les messages de bienvenue et les événements du serveur.
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
    """Gestion des messages de bienvenue, départ et événements programmés."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.scheduler = AsyncIOScheduler()

    async def cog_load(self):
        """Démarrage du scheduler."""
        self.scheduler.add_job(self.send_daily_message, 'cron', hour=SEND_HOUR)
        self.scheduler.start()

    async def cog_unload(self):
        """Arrêt du scheduler."""
        self.scheduler.shutdown()

    async def send_daily_message(self):
        """Envoie un message quotidien."""
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
        """Envoie un message de bienvenue."""
        if member.bot:
            return

        config = await db.get_guild_config(member.guild.id)
        channel_id = config.get('welcome_channel_id')

        if not channel_id:
            return

        channel = member.guild.get_channel(channel_id)
        if not channel:
            return

        # Préparer le message
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

        # Envoyer un DM de bienvenue (optionnel)
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
            pass  # L'utilisateur n'accepte pas les DMs

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Envoie un message de départ."""
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
        """Configure le channel de bienvenue."""
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
        """Configure le message de bienvenue personnalisé."""
        await db.update_guild_config(ctx.guild.id, welcome_message=message)

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
        """Configure le message de départ personnalisé."""
        await db.update_guild_config(ctx.guild.id, goodbye_message=message)

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
        """Teste le message de bienvenue."""
        # Simuler un membre qui rejoint
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
    await bot.add_cog(Welcome(bot))
