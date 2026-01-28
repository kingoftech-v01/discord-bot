"""
Cog pour les commandes utilitaires.
"""
import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
import asyncio
import aiohttp
import random
from typing import Optional

from config import Colors, Emojis
from utils.database import db


class Utility(commands.Cog):
    """Commandes utilitaires diverses."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.reminder_check.start()

    def cog_unload(self):
        self.reminder_check.cancel()

    @tasks.loop(seconds=30)
    async def reminder_check(self):
        """Vérifie et envoie les rappels dus."""
        reminders = await db.get_due_reminders()
        for reminder in reminders:
            try:
                channel = self.bot.get_channel(reminder['channel_id'])
                if channel:
                    user = self.bot.get_user(reminder['user_id'])
                    if user:
                        embed = discord.Embed(
                            title=f"{Emojis.INFO} Rappel!",
                            description=reminder['message'],
                            color=Colors.INFO,
                            timestamp=datetime.now()
                        )
                        await channel.send(f"{user.mention}", embed=embed)
            except Exception:
                pass
            await db.delete_reminder(reminder['id'])

    @reminder_check.before_loop
    async def before_reminder_check(self):
        await self.bot.wait_until_ready()

    @commands.hybrid_command(name="ping")
    async def ping(self, ctx: commands.Context):
        """Affiche la latence du bot."""
        start = datetime.now()
        message = await ctx.send("Pinging...")
        end = datetime.now()

        api_latency = round(self.bot.latency * 1000)
        message_latency = round((end - start).total_seconds() * 1000)

        embed = discord.Embed(
            title="Pong!",
            color=Colors.SUCCESS if api_latency < 200 else Colors.WARNING
        )
        embed.add_field(name="API", value=f"`{api_latency}ms`", inline=True)
        embed.add_field(name="Message", value=f"`{message_latency}ms`", inline=True)
        await message.edit(content=None, embed=embed)

    @commands.hybrid_command(name="serverinfo", aliases=["si", "serveur"])
    async def serverinfo(self, ctx: commands.Context):
        """Affiche les informations du serveur."""
        guild = ctx.guild

        # Compter les types de channels
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        categories = len(guild.categories)

        # Compter les membres
        online = len([m for m in guild.members if m.status != discord.Status.offline])
        bots = len([m for m in guild.members if m.bot])
        humans = guild.member_count - bots

        embed = discord.Embed(
            title=guild.name,
            color=Colors.PRIMARY,
            timestamp=datetime.now()
        )

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(name="Propriétaire", value=guild.owner.mention if guild.owner else "N/A", inline=True)
        embed.add_field(name="Créé le", value=guild.created_at.strftime("%d/%m/%Y"), inline=True)
        embed.add_field(name="ID", value=f"`{guild.id}`", inline=True)

        embed.add_field(
            name=f"Membres ({guild.member_count})",
            value=f"Humains: {humans}\nBots: {bots}\nEn ligne: {online}",
            inline=True
        )
        embed.add_field(
            name=f"Channels ({text_channels + voice_channels})",
            value=f"Texte: {text_channels}\nVocal: {voice_channels}\nCatégories: {categories}",
            inline=True
        )
        embed.add_field(name="Rôles", value=str(len(guild.roles)), inline=True)

        if guild.premium_subscription_count:
            embed.add_field(name="Boosts", value=f"{guild.premium_subscription_count} (Niveau {guild.premium_tier})", inline=True)

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="userinfo", aliases=["ui", "whois"])
    @app_commands.describe(membre="Le membre dont vous voulez les informations")
    async def userinfo(self, ctx: commands.Context, membre: Optional[discord.Member] = None):
        """Affiche les informations d'un utilisateur."""
        member = membre or ctx.author

        roles = [r.mention for r in member.roles[1:]]  # Exclure @everyone
        roles_str = ", ".join(roles[:10]) if roles else "Aucun"
        if len(roles) > 10:
            roles_str += f" et {len(roles) - 10} autres..."

        embed = discord.Embed(
            title=str(member),
            color=member.color if member.color != discord.Color.default() else Colors.PRIMARY,
            timestamp=datetime.now()
        )

        embed.set_thumbnail(url=member.display_avatar.url)

        embed.add_field(name="ID", value=f"`{member.id}`", inline=True)
        embed.add_field(name="Surnom", value=member.nick or "Aucun", inline=True)
        embed.add_field(name="Bot", value="Oui" if member.bot else "Non", inline=True)

        embed.add_field(
            name="Compte créé",
            value=member.created_at.strftime("%d/%m/%Y à %H:%M"),
            inline=True
        )
        embed.add_field(
            name="A rejoint le",
            value=member.joined_at.strftime("%d/%m/%Y à %H:%M") if member.joined_at else "N/A",
            inline=True
        )

        embed.add_field(name=f"Rôles ({len(roles)})", value=roles_str, inline=False)

        if member.premium_since:
            embed.add_field(
                name="Boost",
                value=f"Depuis {member.premium_since.strftime('%d/%m/%Y')}",
                inline=True
            )

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="avatar", aliases=["av", "pp"])
    @app_commands.describe(membre="Le membre dont vous voulez l'avatar")
    async def avatar(self, ctx: commands.Context, membre: Optional[discord.Member] = None):
        """Affiche l'avatar d'un utilisateur."""
        member = membre or ctx.author

        embed = discord.Embed(
            title=f"Avatar de {member.display_name}",
            color=Colors.PRIMARY
        )
        embed.set_image(url=member.display_avatar.url)

        # Boutons de téléchargement
        view = discord.ui.View()
        view.add_item(discord.ui.Button(
            label="PNG",
            url=str(member.display_avatar.replace(format="png", size=1024)),
            style=discord.ButtonStyle.link
        ))
        view.add_item(discord.ui.Button(
            label="JPG",
            url=str(member.display_avatar.replace(format="jpg", size=1024)),
            style=discord.ButtonStyle.link
        ))
        if member.display_avatar.is_animated():
            view.add_item(discord.ui.Button(
                label="GIF",
                url=str(member.display_avatar.replace(format="gif", size=1024)),
                style=discord.ButtonStyle.link
            ))

        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="remind", aliases=["rappel", "remindme"])
    @app_commands.describe(temps="Durée (ex: 10m, 1h, 2d)", message="Le message du rappel")
    async def remind(self, ctx: commands.Context, temps: str, *, message: str):
        """Crée un rappel."""
        # Parser le temps
        time_units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        try:
            unit = temps[-1].lower()
            if unit not in time_units:
                raise ValueError()
            amount = int(temps[:-1])
            if amount <= 0:
                raise ValueError()
            seconds = amount * time_units[unit]
        except (ValueError, IndexError):
            return await ctx.send(f"{Emojis.ERROR} Format invalide. Utilisez: 10s, 5m, 2h, 1d")

        if seconds > 2592000:  # Max 30 jours
            return await ctx.send(f"{Emojis.ERROR} Le rappel ne peut pas dépasser 30 jours.")

        remind_at = datetime.now() + timedelta(seconds=seconds)
        await db.add_reminder(ctx.author.id, ctx.channel.id, message, remind_at)

        embed = discord.Embed(
            title=f"{Emojis.SUCCESS} Rappel créé!",
            description=f"Je vous rappellerai dans **{temps}**",
            color=Colors.SUCCESS
        )
        embed.add_field(name="Message", value=message)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="poll", aliases=["sondage"])
    @app_commands.describe(question="La question du sondage")
    async def poll(self, ctx: commands.Context, *, question: str):
        """Crée un sondage simple (oui/non)."""
        embed = discord.Embed(
            title="Sondage",
            description=question,
            color=Colors.PRIMARY,
            timestamp=datetime.now()
        )
        embed.set_footer(text=f"Sondage créé par {ctx.author.display_name}")

        message = await ctx.send(embed=embed)
        await message.add_reaction("")
        await message.add_reaction("")

    @commands.hybrid_command(name="multipoll", aliases=["sondagemulti"])
    @app_commands.describe(question="La question", options="Options séparées par | (ex: Option1 | Option2 | Option3)")
    async def multipoll(self, ctx: commands.Context, question: str, *, options: str):
        """Crée un sondage à choix multiples."""
        opts = [o.strip() for o in options.split("|")]

        if len(opts) < 2:
            return await ctx.send(f"{Emojis.ERROR} Fournissez au moins 2 options séparées par |")
        if len(opts) > 10:
            return await ctx.send(f"{Emojis.ERROR} Maximum 10 options.")

        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", ""]
        description = "\n".join(f"{emojis[i]} {opt}" for i, opt in enumerate(opts))

        embed = discord.Embed(
            title="Sondage",
            description=f"**{question}**\n\n{description}",
            color=Colors.PRIMARY,
            timestamp=datetime.now()
        )
        embed.set_footer(text=f"Sondage créé par {ctx.author.display_name}")

        message = await ctx.send(embed=embed)
        for i in range(len(opts)):
            await message.add_reaction(emojis[i])

    @commands.hybrid_command(name="meme")
    async def meme(self, ctx: commands.Context):
        """Affiche un meme aléatoire."""
        subreddits = ["memes", "dankmemes", "wholesomememes", "me_irl"]

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    f"https://www.reddit.com/r/{random.choice(subreddits)}/hot.json?limit=50",
                    headers={"User-Agent": "DiscordBot/1.0"}
                ) as resp:
                    if resp.status != 200:
                        return await ctx.send(f"{Emojis.ERROR} Impossible de récupérer un meme.")

                    data = await resp.json()
                    posts = [
                        p['data'] for p in data['data']['children']
                        if not p['data']['over_18'] and p['data'].get('url_overridden_by_dest', '').endswith(('.jpg', '.png', '.gif'))
                    ]

                    if not posts:
                        return await ctx.send(f"{Emojis.ERROR} Aucun meme trouvé.")

                    post = random.choice(posts)
            except Exception:
                return await ctx.send(f"{Emojis.ERROR} Erreur lors de la récupération du meme.")

        embed = discord.Embed(
            title=post['title'][:256],
            color=Colors.PRIMARY,
            url=f"https://reddit.com{post['permalink']}"
        )
        embed.set_image(url=post['url_overridden_by_dest'])
        embed.set_footer(text=f" {post['ups']} | r/{post['subreddit']}")

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="say", aliases=["echo"])
    @commands.has_permissions(manage_messages=True)
    @app_commands.describe(message="Le message à envoyer")
    async def say(self, ctx: commands.Context, *, message: str):
        """Fait parler le bot."""
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass
        await ctx.send(message)

    @commands.hybrid_command(name="embed")
    @commands.has_permissions(manage_messages=True)
    @app_commands.describe(titre="Titre de l'embed", description="Description de l'embed")
    async def embed_cmd(self, ctx: commands.Context, titre: str, *, description: str):
        """Crée un embed personnalisé."""
        embed = discord.Embed(
            title=titre,
            description=description,
            color=Colors.PRIMARY
        )
        embed.set_footer(text=f"Créé par {ctx.author.display_name}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="afk")
    @app_commands.describe(raison="Raison de votre absence")
    async def afk(self, ctx: commands.Context, *, raison: str = "AFK"):
        """Marque vous comme AFK."""
        # Stocker en mémoire (pourrait être en DB pour persistance)
        if not hasattr(self.bot, 'afk_users'):
            self.bot.afk_users = {}

        self.bot.afk_users[ctx.author.id] = {
            'reason': raison,
            'time': datetime.now()
        }

        embed = discord.Embed(
            title=f"{Emojis.INFO} AFK",
            description=f"{ctx.author.mention} est maintenant AFK: {raison}",
            color=Colors.INFO
        )
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Gère le système AFK."""
        if message.author.bot or not message.guild:
            return

        if not hasattr(self.bot, 'afk_users'):
            self.bot.afk_users = {}

        # Vérifier si l'auteur était AFK
        if message.author.id in self.bot.afk_users:
            del self.bot.afk_users[message.author.id]
            await message.channel.send(
                f"{Emojis.INFO} Bon retour {message.author.mention}! Votre statut AFK a été retiré.",
                delete_after=5
            )

        # Vérifier si quelqu'un mentionne un utilisateur AFK
        for mentioned in message.mentions:
            if mentioned.id in self.bot.afk_users:
                afk_data = self.bot.afk_users[mentioned.id]
                time_ago = datetime.now() - afk_data['time']
                minutes = int(time_ago.total_seconds() // 60)
                await message.channel.send(
                    f"{Emojis.INFO} {mentioned.display_name} est AFK: {afk_data['reason']} (depuis {minutes} min)",
                    delete_after=10
                )

    @commands.hybrid_command(name="calc", aliases=["calculer", "math"])
    @app_commands.describe(expression="L'expression mathématique")
    async def calc(self, ctx: commands.Context, *, expression: str):
        """Calcule une expression mathématique."""
        # Sécuriser l'expression
        allowed_chars = set("0123456789+-*/.() ")
        if not all(c in allowed_chars for c in expression):
            return await ctx.send(f"{Emojis.ERROR} Expression invalide.")

        try:
            result = eval(expression)
            embed = discord.Embed(
                title="Calculatrice",
                color=Colors.PRIMARY
            )
            embed.add_field(name="Expression", value=f"`{expression}`", inline=False)
            embed.add_field(name="Résultat", value=f"`{result}`", inline=False)
            await ctx.send(embed=embed)
        except Exception:
            await ctx.send(f"{Emojis.ERROR} Impossible de calculer cette expression.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Utility(bot))
