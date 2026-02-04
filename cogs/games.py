"""
Interactive games and virtual economy system cog for Discord.

This module provides two main feature sets:

**Economy System:**
- Daily reward claims with configurable min/max amounts and cooldown.
- Balance checking for self and other members.
- Wealth leaderboard with pagination.
- Peer-to-peer currency transfers with validation.

**Games:**
- **Trivia**: Multiple-choice questions fetched from the Open Trivia Database
  (OpenTDB) API, with timed reaction-based answers and currency rewards.
- **Dice rolling**: Supports standard NdX notation (e.g., 2d6) with validation.
- **Coin flip**: Simple heads/tails random outcome.
- **Magic 8-Ball**: Random fortune-telling responses to user questions.
- **Rock-Paper-Scissors**: Play against the bot with win/lose/draw outcomes.
- **Slot machine**: Weighted symbol randomization with multiplier-based payouts.

All economy data (coins, daily claims, trivia scores) is persisted in the
SQLite database via the ``utils.database`` module.
"""
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import random
import asyncio
import html
import aiohttp
from typing import Optional

from config import (
    DAILY_REWARD_MIN, DAILY_REWARD_MAX, CURRENCY_NAME, CURRENCY_SYMBOL,
    TRIVIA_TIME_LIMIT, TRIVIA_REWARD, Colors, Emojis
)
from utils.database import db


class Games(commands.Cog):
    """Discord cog providing interactive games, trivia, and a virtual economy.

    The economy system allows users to earn, spend, and transfer virtual
    currency. Games provide entertainment and additional earning opportunities.

    Attributes:
        bot: The Discord bot instance.
        trivia_sessions: Tracks active trivia sessions per channel to prevent
            overlapping games. Maps ``{channel_id: True}`` for channels with
            an active trivia round.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.trivia_sessions = {}  # {channel_id: True} -- prevents concurrent trivia in same channel

    # =========================================================================
    # ECONOMY COMMANDS
    # =========================================================================

    @commands.hybrid_command(name="daily", aliases=["quotidien"])
    async def daily(self, ctx: commands.Context):
        """Claim your daily currency reward.

        Awards a random amount of coins between DAILY_REWARD_MIN and
        DAILY_REWARD_MAX. Can only be claimed once per day (resets at midnight).

        Args:
            ctx: The command invocation context.
        """
        user = await db.get_or_create_user(ctx.author.id, ctx.guild.id)

        if not await db.can_claim_daily(ctx.author.id, ctx.guild.id):
            embed = discord.Embed(
                title=f"{Emojis.ERROR} Récompense déjà réclamée",
                description="Revenez demain pour votre prochaine récompense!",
                color=Colors.ERROR
            )
            return await ctx.send(embed=embed)

        # Generate a random reward within the configured range
        amount = random.randint(DAILY_REWARD_MIN, DAILY_REWARD_MAX)
        await db.claim_daily(ctx.author.id, ctx.guild.id, amount)

        # Re-fetch user data to get the updated balance
        user = await db.get_user(ctx.author.id, ctx.guild.id)

        embed = discord.Embed(
            title=f"{Emojis.COIN} Récompense Quotidienne!",
            description=f"Vous avez reçu **{amount}** {CURRENCY_SYMBOL}{CURRENCY_NAME}!",
            color=Colors.ECONOMY
        )
        embed.add_field(name="Solde actuel", value=f"{CURRENCY_SYMBOL}{user['coins']:,} {CURRENCY_NAME}")
        embed.set_footer(text="Revenez demain pour une nouvelle récompense!")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="balance", aliases=["bal", "solde", "coins"])
    @app_commands.describe(membre="Le membre dont vous voulez voir le solde")
    async def balance(self, ctx: commands.Context, membre: Optional[discord.Member] = None):
        """Display your coin balance or another member's balance.

        Args:
            ctx: The command invocation context.
            membre: The member whose balance to check. Defaults to the command author.
        """
        member = membre or ctx.author
        user = await db.get_or_create_user(member.id, ctx.guild.id)

        embed = discord.Embed(
            title=f"{Emojis.COIN} Solde de {member.display_name}",
            description=f"**{CURRENCY_SYMBOL}{user['coins']:,}** {CURRENCY_NAME}",
            color=Colors.ECONOMY
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="richest", aliases=["baltop", "richesse"])
    @app_commands.describe(page="Numéro de page")
    async def richest(self, ctx: commands.Context, page: int = 1):
        """Display the wealthiest members leaderboard with pagination.

        Shows up to 100 members ranked by coin balance, 10 per page. The
        top 3 positions receive medal emojis (gold, silver, bronze).

        Args:
            ctx: The command invocation context.
            page: The page number to display (1-based). Defaults to 1.
        """
        users = await db.get_economy_leaderboard(ctx.guild.id, limit=100)
        per_page = 10
        # Ceiling division for total pages, minimum 1 page
        total_pages = max(1, (len(users) + per_page - 1) // per_page)

        if page < 1 or page > total_pages:
            return await ctx.send(f"{Emojis.ERROR} Page invalide.")

        start = (page - 1) * per_page
        end = start + per_page
        page_users = users[start:end]

        embed = discord.Embed(
            title=f"{Emojis.TROPHY} Les Plus Riches - {ctx.guild.name}",
            color=Colors.ECONOMY
        )

        medals = ["", "", ""]  # Gold, silver, bronze for top 3
        description_lines = []
        for i, user_data in enumerate(page_users, start=start + 1):
            member = ctx.guild.get_member(user_data['user_id'])
            name = member.display_name if member else f"Utilisateur #{user_data['user_id']}"
            medal = medals[i-1] if i <= 3 else f"**{i}.**"
            description_lines.append(f"{medal} {name} - {CURRENCY_SYMBOL}{user_data['coins']:,}")

        embed.description = "\n".join(description_lines) if description_lines else "Aucun utilisateur."
        embed.set_footer(text=f"Page {page}/{total_pages}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="give", aliases=["transfer", "donner"])
    @app_commands.describe(membre="Le membre à qui donner", montant="Le montant à donner")
    async def give(self, ctx: commands.Context, membre: discord.Member, montant: int):
        """Transfer coins to another member.

        Validates that the sender has sufficient balance and prevents transfers
        to bots, to self, and of non-positive amounts.

        Args:
            ctx: The command invocation context.
            membre: The member to send coins to.
            montant: The amount of coins to transfer (must be positive).
        """
        if membre.bot:
            return await ctx.send(f"{Emojis.ERROR} Vous ne pouvez pas donner à un bot.")
        if membre == ctx.author:
            return await ctx.send(f"{Emojis.ERROR} Vous ne pouvez pas vous donner à vous-même.")
        if montant <= 0:
            return await ctx.send(f"{Emojis.ERROR} Le montant doit être positif.")

        user = await db.get_or_create_user(ctx.author.id, ctx.guild.id)
        if user['coins'] < montant:
            return await ctx.send(f"{Emojis.ERROR} Vous n'avez pas assez de {CURRENCY_NAME}.")

        # Debit sender and credit recipient atomically
        await db.add_coins(ctx.author.id, ctx.guild.id, -montant)
        await db.add_coins(membre.id, ctx.guild.id, montant)

        embed = discord.Embed(
            title=f"{Emojis.SUCCESS} Transfert réussi!",
            description=f"Vous avez donné **{CURRENCY_SYMBOL}{montant:,}** {CURRENCY_NAME} à {membre.mention}",
            color=Colors.SUCCESS
        )
        await ctx.send(embed=embed)

    # =========================================================================
    # TRIVIA GAME
    # =========================================================================

    @commands.hybrid_command(name="trivia", aliases=["quiz"])
    @app_commands.describe(categorie="Catégorie (general, science, history, sports, entertainment)")
    async def trivia(self, ctx: commands.Context, categorie: str = "general"):
        """Start a timed trivia question with reaction-based answers.

        Fetches a multiple-choice question from the Open Trivia Database (OpenTDB)
        API, presents it with emoji reactions as answer options, and waits for
        users to react with the correct answer within the time limit.

        Only one trivia session can be active per channel at a time. Winners
        receive a currency reward and their trivia statistics are updated.

        Args:
            ctx: The command invocation context.
            categorie: The question category. Supported values: "general",
                "science", "history", "sports", "entertainment", "games",
                "geography", "animals". Defaults to "general".
        """
        # Prevent concurrent trivia sessions in the same channel
        if ctx.channel.id in self.trivia_sessions:
            return await ctx.send(f"{Emojis.ERROR} Une partie de trivia est déjà en cours!")

        self.trivia_sessions[ctx.channel.id] = True

        # Mapping of category names to OpenTDB category IDs
        categories = {
            "general": 9,
            "science": 17,
            "history": 23,
            "sports": 21,
            "entertainment": 11,
            "games": 15,
            "geography": 22,
            "animals": 27
        }

        # Default to "General Knowledge" (ID 9) for unrecognized categories
        cat_id = categories.get(categorie.lower(), 9)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"https://opentdb.com/api.php?amount=1&category={cat_id}&type=multiple"
                ) as resp:
                    if resp.status != 200:
                        del self.trivia_sessions[ctx.channel.id]
                        return await ctx.send(f"{Emojis.ERROR} Erreur lors de la récupération de la question.")

                    data = await resp.json()
                    if data['response_code'] != 0:
                        del self.trivia_sessions[ctx.channel.id]
                        return await ctx.send(f"{Emojis.ERROR} Aucune question disponible.")

                    question_data = data['results'][0]
        except Exception as e:
            del self.trivia_sessions[ctx.channel.id]
            return await ctx.send(f"{Emojis.ERROR} Erreur de connexion à l'API.")

        # Decode HTML entities in the API response (e.g., &amp; -> &)
        question = html.unescape(question_data['question'])
        correct = html.unescape(question_data['correct_answer'])
        incorrect = [html.unescape(a) for a in question_data['incorrect_answers']]
        difficulty = question_data['difficulty']

        # Shuffle answers so the correct answer is in a random position
        answers = incorrect + [correct]
        random.shuffle(answers)
        correct_index = answers.index(correct)

        # Map answer indices to letter emojis (A, B, C, D)
        emojis = ["", "", "", ""]
        answers_text = "\n".join(f"{emojis[i]} {answer}" for i, answer in enumerate(answers))

        embed = discord.Embed(
            title=f"{Emojis.GAME} Trivia - {categorie.capitalize()}",
            description=f"**{question}**\n\n{answers_text}",
            color=Colors.PRIMARY
        )
        embed.add_field(name="Difficulté", value=difficulty.capitalize(), inline=True)
        embed.add_field(name="Temps", value=f"{TRIVIA_TIME_LIMIT} secondes", inline=True)
        embed.add_field(name="Récompense", value=f"{CURRENCY_SYMBOL}{TRIVIA_REWARD}", inline=True)
        embed.set_footer(text="Réagissez avec la bonne réponse!")

        message = await ctx.send(embed=embed)
        # Add reaction options for users to click on
        for i in range(len(answers)):
            await message.add_reaction(emojis[i])

        def check(reaction, user):
            """Filter function: only accept reactions from non-bot users on this message."""
            return (
                user != self.bot.user and
                reaction.message.id == message.id and
                str(reaction.emoji) in emojis[:len(answers)]
            )

        winners = []
        start_time = datetime.now()

        # Collect reactions until the time limit expires
        while (datetime.now() - start_time).total_seconds() < TRIVIA_TIME_LIMIT:
            try:
                # Calculate remaining time for this wait_for call
                reaction, user = await self.bot.wait_for(
                    'reaction_add',
                    timeout=TRIVIA_TIME_LIMIT - (datetime.now() - start_time).total_seconds(),
                    check=check
                )
                # Record the user as a winner if they selected the correct answer
                if str(reaction.emoji) == emojis[correct_index] and user not in winners:
                    winners.append(user)
            except asyncio.TimeoutError:
                break

        # Clean up the trivia session lock for this channel
        del self.trivia_sessions[ctx.channel.id]

        # Build and send the results embed
        result_embed = discord.Embed(
            title=f"{Emojis.GAME} Résultats du Trivia",
            color=Colors.SUCCESS if winners else Colors.ERROR
        )
        result_embed.add_field(name="Question", value=question, inline=False)
        result_embed.add_field(name="Bonne réponse", value=f"{emojis[correct_index]} {correct}", inline=False)

        if winners:
            # Show up to 5 winner mentions to avoid overly long embeds
            winner_mentions = ", ".join(w.mention for w in winners[:5])
            result_embed.add_field(
                name=f"{Emojis.TROPHY} Gagnant(s)",
                value=winner_mentions,
                inline=False
            )
            # Award currency and update trivia stats for each winner
            for winner in winners:
                await db.add_coins(winner.id, ctx.guild.id, TRIVIA_REWARD)
                await db.update_trivia_score(winner.id, ctx.guild.id, True)
        else:
            result_embed.add_field(name="Résultat", value="Personne n'a trouvé la bonne réponse!", inline=False)

        await ctx.send(embed=result_embed)

    @commands.hybrid_command(name="triviastats", aliases=["quizstats"])
    async def triviastats(self, ctx: commands.Context):
        """Display the server's trivia leaderboard with accuracy statistics.

        Shows each player's correct answers, total questions attempted, and
        accuracy percentage. Top 3 positions receive medal emojis.

        Args:
            ctx: The command invocation context.
        """
        leaderboard = await db.get_trivia_leaderboard(ctx.guild.id)

        embed = discord.Embed(
            title=f"{Emojis.TROPHY} Classement Trivia",
            color=Colors.PRIMARY
        )

        if not leaderboard:
            embed.description = "Aucune statistique disponible."
        else:
            lines = []
            medals = ["", "", ""]  # Gold, silver, bronze for top 3
            for i, data in enumerate(leaderboard, 1):
                member = ctx.guild.get_member(data['user_id'])
                name = member.display_name if member else f"Utilisateur #{data['user_id']}"
                # Calculate accuracy percentage, avoiding division by zero
                accuracy = (data['correct_answers'] / data['total_questions'] * 100) if data['total_questions'] > 0 else 0
                medal = medals[i-1] if i <= 3 else f"**{i}.**"
                lines.append(f"{medal} {name} - {data['correct_answers']}/{data['total_questions']} ({accuracy:.0f}%)")
            embed.description = "\n".join(lines)

        await ctx.send(embed=embed)

    # =========================================================================
    # CASUAL GAMES (dice, coin flip, 8ball, RPS, slots)
    # =========================================================================

    @commands.hybrid_command(name="roll", aliases=["dice", "dé"])
    @app_commands.describe(des="Format: NdX (ex: 2d6 pour 2 dés à 6 faces)")
    async def roll(self, ctx: commands.Context, des: str = "1d6"):
        """Roll dice using standard NdX notation (e.g., 2d6 = two six-sided dice).

        Validates the input format and enforces limits: 1-100 dice with 2-1000
        faces each. Shows individual die results and the total sum.

        Args:
            ctx: The command invocation context.
            des: Dice notation string in NdX format. Defaults to "1d6".
        """
        try:
            # Parse NdX notation (e.g., "2d6" -> 2 dice, 6 sides each)
            if 'd' not in des.lower():
                raise ValueError()
            parts = des.lower().split('d')
            num_dice = int(parts[0]) if parts[0] else 1
            num_sides = int(parts[1])

            if num_dice < 1 or num_dice > 100:
                raise ValueError("Nombre de dés invalide")
            if num_sides < 2 or num_sides > 1000:
                raise ValueError("Nombre de faces invalide")
        except ValueError:
            return await ctx.send(f"{Emojis.ERROR} Format invalide. Utilisez NdX (ex: 2d6)")

        results = [random.randint(1, num_sides) for _ in range(num_dice)]
        total = sum(results)

        embed = discord.Embed(
            title=f"{Emojis.DICE} Lancer de dés",
            color=Colors.PRIMARY
        )
        embed.add_field(name="Dés", value=f"{num_dice}d{num_sides}", inline=True)
        embed.add_field(name="Résultats", value=", ".join(map(str, results)), inline=True)
        embed.add_field(name="Total", value=str(total), inline=True)
        embed.set_footer(text=f"Lancé par {ctx.author.display_name}")

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="coinflip", aliases=["flip", "pile"])
    async def coinflip(self, ctx: commands.Context):
        """Flip a coin and get heads or tails.

        Args:
            ctx: The command invocation context.
        """
        result = random.choice(["Pile", "Face"])
        emoji = "" if result == "Pile" else ""

        embed = discord.Embed(
            title=f"{Emojis.COIN} Lancer de pièce",
            description=f"{emoji} **{result}**!",
            color=Colors.PRIMARY
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="8ball", aliases=["8b", "boule"])
    @app_commands.describe(question="Votre question")
    async def eightball(self, ctx: commands.Context, *, question: str):
        """Ask the Magic 8-Ball a yes/no question.

        Returns a random response from a pool of 19 possible answers, ranging
        from affirmative to negative to non-committal, mimicking the classic
        Magic 8-Ball toy.

        Args:
            ctx: The command invocation context.
            question: The question to ask the Magic 8-Ball.
        """
        # Classic Magic 8-Ball response pool (French translations)
        # 9 affirmative, 5 non-committal, 5 negative responses
        responses = [
            "Oui, certainement.",
            "C'est décidément ainsi.",
            "Sans aucun doute.",
            "Oui, définitivement.",
            "Vous pouvez compter dessus.",
            "Très probablement.",
            "Les perspectives sont bonnes.",
            "Oui.",
            "Les signes indiquent que oui.",
            "Réponse floue, réessayez.",
            "Redemandez plus tard.",
            "Mieux vaut ne pas vous le dire maintenant.",
            "Je ne peux pas prédire maintenant.",
            "Concentrez-vous et redemandez.",
            "N'y comptez pas.",
            "Ma réponse est non.",
            "Mes sources disent non.",
            "Les perspectives ne sont pas bonnes.",
            "Très douteux."
        ]

        response = random.choice(responses)

        embed = discord.Embed(
            title="Boule Magique 8",
            color=Colors.PRIMARY
        )
        embed.add_field(name="Question", value=question, inline=False)
        embed.add_field(name="Réponse", value=f"*{response}*", inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="rps", aliases=["chifoumi", "pfc"])
    @app_commands.describe(choix="pierre, feuille ou ciseaux")
    async def rps(self, ctx: commands.Context, choix: str):
        """Play Rock-Paper-Scissors against the bot.

        Accepts both French (pierre/feuille/ciseaux) and English
        (rock/paper/scissors) input. The bot makes a random choice and the
        winner is determined by standard RPS rules.

        Args:
            ctx: The command invocation context.
            choix: The user's choice: "pierre"/"rock", "feuille"/"paper",
                or "ciseaux"/"scissors".
        """
        # Map of valid choices (French + English) to their display emojis
        choices = {
            "pierre": "",
            "feuille": "",
            "ciseaux": "",
            "rock": "",
            "paper": "",
            "scissors": ""
        }

        user_choice = choix.lower()
        if user_choice not in choices:
            return await ctx.send(f"{Emojis.ERROR} Choisissez: pierre, feuille, ou ciseaux")

        # Normalize English inputs to their French equivalents for consistent logic
        if user_choice in ["rock"]:
            user_choice = "pierre"
        elif user_choice in ["paper"]:
            user_choice = "feuille"
        elif user_choice in ["scissors"]:
            user_choice = "ciseaux"

        bot_choice = random.choice(["pierre", "feuille", "ciseaux"])

        # Win conditions: each choice beats exactly one other choice
        wins = {
            "pierre": "ciseaux",   # Rock beats scissors
            "feuille": "pierre",   # Paper beats rock
            "ciseaux": "feuille"   # Scissors beats paper
        }

        if user_choice == bot_choice:
            result = "Égalité!"
            color = Colors.WARNING
        elif wins[user_choice] == bot_choice:
            result = "Vous avez gagné!"
            color = Colors.SUCCESS
        else:
            result = "Vous avez perdu!"
            color = Colors.ERROR

        embed = discord.Embed(
            title=f"{Emojis.GAME} Pierre-Feuille-Ciseaux",
            color=color
        )
        embed.add_field(name="Votre choix", value=f"{choices[user_choice]} {user_choice.capitalize()}", inline=True)
        embed.add_field(name="Mon choix", value=f"{choices[bot_choice]} {bot_choice.capitalize()}", inline=True)
        embed.add_field(name="Résultat", value=result, inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="slot", aliases=["slots", "machine"])
    async def slot(self, ctx: commands.Context):
        """Play the slot machine for a chance to win multiplied rewards.

        Spins three reels with weighted symbol probabilities. Payout rules:
        - Three matching symbols: JACKPOT with multiplier based on symbol rarity
          (diamond=100x, seven=50x, bell=25x, others=10x).
        - Two adjacent matching symbols (first two or last two): 2x multiplier.
        - No matches: no reward.

        Args:
            ctx: The command invocation context.
        """
        symbols = ["", "", "", "", "", "", ""]
        # Weights control symbol frequency: common fruits appear most often,
        # rare symbols (bell, seven, diamond) appear least often
        weights = [30, 25, 20, 15, 5, 3, 2]

        reels = random.choices(symbols, weights=weights, k=3)

        # Calculate winnings based on symbol matches
        if reels[0] == reels[1] == reels[2]:
            # Triple match: JACKPOT with rarity-based multiplier
            if reels[0] == "":
                multiplier = 100
            elif reels[0] == "":
                multiplier = 50
            elif reels[0] == "":
                multiplier = 25
            else:
                multiplier = 10
            result = f"JACKPOT! x{multiplier}!"
            color = Colors.ECONOMY
        elif reels[0] == reels[1] or reels[1] == reels[2]:
            # Two adjacent matching symbols: small win
            multiplier = 2
            result = f"Deux identiques! x{multiplier}"
            color = Colors.SUCCESS
        else:
            # No matches: loss
            multiplier = 0
            result = "Pas de chance!"
            color = Colors.ERROR

        embed = discord.Embed(
            title="Machine à Sous",
            description=f"[ {reels[0]} | {reels[1]} | {reels[2]} ]",
            color=color
        )
        embed.add_field(name="Résultat", value=result)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    """Entry point for loading this cog into the bot.

    Called by ``bot.load_extension('cogs.games')``.

    Args:
        bot: The Discord bot instance to attach the cog to.
    """
    await bot.add_cog(Games(bot))
