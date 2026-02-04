"""
Utility commands cog for the Discord bot.

Provides a collection of general-purpose commands available to all server
members, including server/user information display, avatar retrieval, timed
reminders, polls (simple and multi-option), random meme fetching from Reddit,
message echoing, custom embeds, an AFK status system, and a safe math
calculator.

The reminder system uses a background task loop that checks the database every
30 seconds for due reminders. The AFK system stores user status in-memory on
the bot instance and listens for messages to automatically clear or notify.
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
    """Utility commands cog providing general-purpose tools for server members.

    This cog bundles a variety of informational and interactive commands:
    - Server and user information lookups
    - Avatar display with download links
    - Timed reminders persisted in the database
    - Simple (yes/no) and multi-option polls
    - Random meme fetching from Reddit
    - Message echo and custom embed creation (mod-only)
    - AFK status tracking (in-memory, notifies on mention)
    - Safe mathematical expression evaluation via AST parsing

    Attributes:
        bot: The bot instance this cog is attached to.
    """

    def __init__(self, bot: commands.Bot):
        """Initialize the Utility cog and start the reminder background task.

        Args:
            bot: The bot instance to bind this cog to.
        """
        self.bot = bot
        self.reminder_check.start()

    def cog_unload(self):
        """Cancel the reminder background task when the cog is unloaded."""
        self.reminder_check.cancel()

    @tasks.loop(seconds=30)
    async def reminder_check(self):
        """Check for due reminders and send notification messages.

        Queries the database every 30 seconds for reminders whose scheduled
        time has passed. For each due reminder, sends an embed notification
        in the original channel mentioning the user who created it, then
        deletes the reminder from the database regardless of send success.
        """
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
            # Always delete the reminder after processing, even if sending failed
            await db.delete_reminder(reminder['id'])

    @reminder_check.before_loop
    async def before_reminder_check(self):
        """Wait until the bot is fully connected before checking reminders."""
        await self.bot.wait_until_ready()

    @commands.hybrid_command(name="ping")
    async def ping(self, ctx: commands.Context):
        """Display the bot's current latency (API and message round-trip).

        Measures two latencies:
        - **API latency**: The WebSocket heartbeat latency to Discord's gateway.
        - **Message latency**: The round-trip time to send and edit a message.

        The embed color is green if API latency is under 200ms, yellow otherwise.

        Args:
            ctx: The invocation context.
        """
        start = datetime.now()
        message = await ctx.send("Pinging...")
        end = datetime.now()

        # WebSocket heartbeat latency (gateway connection quality)
        api_latency = round(self.bot.latency * 1000)
        # Time it took to send the initial message and receive confirmation
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
        """Display detailed information about the current server.

        Shows an embed with the server's owner, creation date, ID, member
        breakdown (humans/bots/online), channel counts by type, role count,
        and Nitro boost status if applicable.

        Args:
            ctx: The invocation context.
        """
        guild = ctx.guild

        # Count channel types for the summary
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        categories = len(guild.categories)

        # Count member categories (requires members intent)
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

        # Only show boost info if the server has active boosts
        if guild.premium_subscription_count:
            embed.add_field(name="Boosts", value=f"{guild.premium_subscription_count} (Niveau {guild.premium_tier})", inline=True)

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="userinfo", aliases=["ui", "whois"])
    @app_commands.describe(membre="Le membre dont vous voulez les informations")
    async def userinfo(self, ctx: commands.Context, membre: Optional[discord.Member] = None):
        """Display detailed information about a server member.

        Shows the member's ID, nickname, bot status, account creation date,
        join date, roles (up to 10 displayed), and Nitro boost date if
        applicable. Defaults to the command invoker when no member is specified.

        Args:
            ctx: The invocation context.
            membre: The member to look up. Defaults to the command author.
        """
        member = membre or ctx.author

        # Exclude the implicit @everyone role (index 0)
        roles = [r.mention for r in member.roles[1:]]
        roles_str = ", ".join(roles[:10]) if roles else "Aucun"
        # Truncate display if the member has more than 10 roles
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
        """Display a member's avatar with download links in various formats.

        Shows the avatar as a large embed image and provides link buttons to
        download in PNG and JPG formats (1024px). If the avatar is animated,
        a GIF download button is also included.

        Args:
            ctx: The invocation context.
            membre: The member whose avatar to display. Defaults to the
                command author.
        """
        member = membre or ctx.author

        embed = discord.Embed(
            title=f"Avatar de {member.display_name}",
            color=Colors.PRIMARY
        )
        embed.set_image(url=member.display_avatar.url)

        # Download buttons for different image formats
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
        # Only offer GIF download if the avatar is actually animated
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
        """Create a timed reminder that notifies you in the current channel.

        The reminder is persisted in the database and delivered by the
        ``reminder_check`` background task. Supported time suffixes:
        ``s`` (seconds), ``m`` (minutes), ``h`` (hours), ``d`` (days).
        Maximum duration is 30 days.

        Args:
            ctx: The invocation context.
            temps: Duration string with a numeric value and unit suffix
                (e.g., ``10m``, ``1h``, ``2d``).
            message: The reminder text that will be shown when the timer fires.
        """
        # Parse the duration string: extract numeric value and time unit
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

        # Enforce a maximum reminder duration of 30 days (2,592,000 seconds)
        if seconds > 2592000:
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
        """Create a simple yes/no poll with thumbs-up and thumbs-down reactions.

        Args:
            ctx: The invocation context.
            question: The poll question to display in the embed.
        """
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
        """Create a multiple-choice poll with numbered emoji reactions.

        Options are separated by the pipe character (``|``). Supports 2 to 10
        options, each mapped to a numbered emoji (1-10).

        Args:
            ctx: The invocation context.
            question: The poll question.
            options: Pipe-separated list of answer options
                (e.g., ``"Option A | Option B | Option C"``).
        """
        opts = [o.strip() for o in options.split("|")]

        if len(opts) < 2:
            return await ctx.send(f"{Emojis.ERROR} Fournissez au moins 2 options séparées par |")
        if len(opts) > 10:
            return await ctx.send(f"{Emojis.ERROR} Maximum 10 options.")

        # Number emojis corresponding to each option index
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
        # Add one numbered reaction per option for users to vote
        for i in range(len(opts)):
            await message.add_reaction(emojis[i])

    @commands.hybrid_command(name="meme")
    async def meme(self, ctx: commands.Context):
        """Fetch and display a random meme from Reddit.

        Randomly selects a subreddit from a curated list, fetches the top 50
        hot posts, filters for SFW image posts (jpg/png/gif), and displays
        one at random. Includes the post title, image, upvote count, and
        subreddit name.

        Args:
            ctx: The invocation context.
        """
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
                    # Filter out NSFW posts and non-image URLs
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
        """Make the bot send a message on your behalf (requires Manage Messages).

        The invoking message is deleted if the bot has permission, so only
        the bot's echoed message remains visible in the channel.

        Args:
            ctx: The invocation context.
            message: The text content for the bot to send.
        """
        # Attempt to delete the original command invocation for a clean look
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass
        await ctx.send(message)

    @commands.hybrid_command(name="embed")
    @commands.has_permissions(manage_messages=True)
    @app_commands.describe(titre="Titre de l'embed", description="Description de l'embed")
    async def embed_cmd(self, ctx: commands.Context, titre: str, *, description: str):
        """Create and send a custom embed message (requires Manage Messages).

        Args:
            ctx: The invocation context.
            titre: The title text for the embed.
            description: The body/description text for the embed.
        """
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
        """Mark yourself as AFK with an optional reason.

        Your AFK status is stored in-memory on the bot instance (not persisted
        across restarts). When another user mentions you while you are AFK,
        the bot will notify them with your reason and duration. Your AFK status
        is automatically cleared when you send a message.

        Args:
            ctx: The invocation context.
            raison: The reason for going AFK. Defaults to ``"AFK"``.
        """
        # Store AFK data in-memory on the bot (could be moved to DB for persistence)
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
        """Handle the AFK system: clear returning users and notify on mentions.

        This listener runs on every guild message and performs two checks:
        1. If the message author was AFK, remove their AFK status and notify.
        2. If any mentioned user is AFK, send a temporary notification with
           their AFK reason and how long they have been away.

        Args:
            message: The incoming Discord message event.
        """
        if message.author.bot or not message.guild:
            return

        if not hasattr(self.bot, 'afk_users'):
            self.bot.afk_users = {}

        # Check if the message author was previously marked as AFK
        if message.author.id in self.bot.afk_users:
            del self.bot.afk_users[message.author.id]
            await message.channel.send(
                f"{Emojis.INFO} Bon retour {message.author.mention}! Votre statut AFK a été retiré.",
                delete_after=5
            )

        # Check if any mentioned users are currently AFK
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
        """Calcule une expression mathématique de manière sécurisée.

        Utilise un parseur AST au lieu de eval() pour empêcher l'exécution
        de code arbitraire. Supporte: +, -, *, /, parenthèses, nombres décimaux.

        Args:
            ctx: Le contexte de la commande Discord.
            expression: L'expression mathématique à évaluer (ex: '2 + 3 * 4').
        """
        try:
            result = self._safe_math_eval(expression)
            embed = discord.Embed(
                title="Calculatrice",
                color=Colors.PRIMARY
            )
            embed.add_field(name="Expression", value=f"`{expression}`", inline=False)
            embed.add_field(name="Résultat", value=f"`{result}`", inline=False)
            await ctx.send(embed=embed)
        except (ValueError, TypeError, ZeroDivisionError) as e:
            await ctx.send(f"{Emojis.ERROR} {str(e)}")
        except Exception:
            await ctx.send(f"{Emojis.ERROR} Impossible de calculer cette expression.")

    @staticmethod
    def _safe_math_eval(expression: str) -> float:
        """Évalue une expression mathématique de manière sécurisée via l'AST Python.

        Parcourt l'arbre syntaxique (AST) de l'expression et n'autorise que les
        opérations arithmétiques de base (+, -, *, /) et les nombres littéraux.
        Contrairement à eval(), cette méthode ne peut pas exécuter de code arbitraire.

        Args:
            expression: L'expression mathématique sous forme de chaîne.

        Returns:
            Le résultat numérique de l'expression.

        Raises:
            ValueError: Si l'expression contient des éléments non autorisés.
            ZeroDivisionError: Si l'expression contient une division par zéro.
        """
        import ast
        import operator

        # Mapping of allowed binary operators
        allowed_operators = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
        }

        # Mapping of allowed unary operators (for negative numbers like -5)
        allowed_unary = {
            ast.UAdd: operator.pos,
            ast.USub: operator.neg,
        }

        def _eval_node(node):
            """Recursively evaluate an AST node, only allowing safe operations."""
            if isinstance(node, ast.Expression):
                return _eval_node(node.body)
            elif isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                return node.value
            elif isinstance(node, ast.BinOp):
                op_type = type(node.op)
                if op_type not in allowed_operators:
                    raise ValueError(f"Opérateur non autorisé.")
                left = _eval_node(node.left)
                right = _eval_node(node.right)
                if op_type == ast.Div and right == 0:
                    raise ZeroDivisionError("Division par zéro.")
                return allowed_operators[op_type](left, right)
            elif isinstance(node, ast.UnaryOp):
                op_type = type(node.op)
                if op_type not in allowed_unary:
                    raise ValueError(f"Opérateur non autorisé.")
                return allowed_unary[op_type](_eval_node(node.operand))
            else:
                raise ValueError("Expression invalide. Seuls les nombres et +, -, *, / sont autorisés.")

        try:
            tree = ast.parse(expression, mode='eval')
        except SyntaxError:
            raise ValueError("Expression mathématique invalide.")

        return _eval_node(tree)


async def setup(bot: commands.Bot):
    """Load the Utility cog into the bot.

    Args:
        bot: The bot instance to register the cog with.
    """
    await bot.add_cog(Utility(bot))
