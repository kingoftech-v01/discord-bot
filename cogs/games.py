"""
Cog pour les jeux interactifs et l'économie.
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
    """Jeux interactifs, trivia, et système d'économie."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.trivia_sessions = {}  # {channel_id: True}

    # ===============================
    # ECONOMIE
    # ===============================

    @commands.hybrid_command(name="daily", aliases=["quotidien"])
    async def daily(self, ctx: commands.Context):
        """Réclamez votre récompense quotidienne."""
        user = await db.get_or_create_user(ctx.author.id, ctx.guild.id)

        if not await db.can_claim_daily(ctx.author.id, ctx.guild.id):
            embed = discord.Embed(
                title=f"{Emojis.ERROR} Récompense déjà réclamée",
                description="Revenez demain pour votre prochaine récompense!",
                color=Colors.ERROR
            )
            return await ctx.send(embed=embed)

        amount = random.randint(DAILY_REWARD_MIN, DAILY_REWARD_MAX)
        await db.claim_daily(ctx.author.id, ctx.guild.id, amount)

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
        """Affiche votre solde ou celui d'un autre membre."""
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
        """Affiche le classement des plus riches."""
        users = await db.get_economy_leaderboard(ctx.guild.id, limit=100)
        per_page = 10
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

        medals = ["", "", ""]
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
        """Donne des coins à un autre membre."""
        if membre.bot:
            return await ctx.send(f"{Emojis.ERROR} Vous ne pouvez pas donner à un bot.")
        if membre == ctx.author:
            return await ctx.send(f"{Emojis.ERROR} Vous ne pouvez pas vous donner à vous-même.")
        if montant <= 0:
            return await ctx.send(f"{Emojis.ERROR} Le montant doit être positif.")

        user = await db.get_or_create_user(ctx.author.id, ctx.guild.id)
        if user['coins'] < montant:
            return await ctx.send(f"{Emojis.ERROR} Vous n'avez pas assez de {CURRENCY_NAME}.")

        await db.add_coins(ctx.author.id, ctx.guild.id, -montant)
        await db.add_coins(membre.id, ctx.guild.id, montant)

        embed = discord.Embed(
            title=f"{Emojis.SUCCESS} Transfert réussi!",
            description=f"Vous avez donné **{CURRENCY_SYMBOL}{montant:,}** {CURRENCY_NAME} à {membre.mention}",
            color=Colors.SUCCESS
        )
        await ctx.send(embed=embed)

    # ===============================
    # TRIVIA
    # ===============================

    @commands.hybrid_command(name="trivia", aliases=["quiz"])
    @app_commands.describe(categorie="Catégorie (general, science, history, sports, entertainment)")
    async def trivia(self, ctx: commands.Context, categorie: str = "general"):
        """Lance une question de trivia."""
        if ctx.channel.id in self.trivia_sessions:
            return await ctx.send(f"{Emojis.ERROR} Une partie de trivia est déjà en cours!")

        self.trivia_sessions[ctx.channel.id] = True

        # Catégories OpenTDB
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

        question = html.unescape(question_data['question'])
        correct = html.unescape(question_data['correct_answer'])
        incorrect = [html.unescape(a) for a in question_data['incorrect_answers']]
        difficulty = question_data['difficulty']

        # Mélanger les réponses
        answers = incorrect + [correct]
        random.shuffle(answers)
        correct_index = answers.index(correct)

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
        for i in range(len(answers)):
            await message.add_reaction(emojis[i])

        def check(reaction, user):
            return (
                user != self.bot.user and
                reaction.message.id == message.id and
                str(reaction.emoji) in emojis[:len(answers)]
            )

        winners = []
        start_time = datetime.now()

        while (datetime.now() - start_time).total_seconds() < TRIVIA_TIME_LIMIT:
            try:
                reaction, user = await self.bot.wait_for(
                    'reaction_add',
                    timeout=TRIVIA_TIME_LIMIT - (datetime.now() - start_time).total_seconds(),
                    check=check
                )
                if str(reaction.emoji) == emojis[correct_index] and user not in winners:
                    winners.append(user)
            except asyncio.TimeoutError:
                break

        del self.trivia_sessions[ctx.channel.id]

        # Résultats
        result_embed = discord.Embed(
            title=f"{Emojis.GAME} Résultats du Trivia",
            color=Colors.SUCCESS if winners else Colors.ERROR
        )
        result_embed.add_field(name="Question", value=question, inline=False)
        result_embed.add_field(name="Bonne réponse", value=f"{emojis[correct_index]} {correct}", inline=False)

        if winners:
            winner_mentions = ", ".join(w.mention for w in winners[:5])
            result_embed.add_field(
                name=f"{Emojis.TROPHY} Gagnant(s)",
                value=winner_mentions,
                inline=False
            )
            # Donner les récompenses
            for winner in winners:
                await db.add_coins(winner.id, ctx.guild.id, TRIVIA_REWARD)
                await db.update_trivia_score(winner.id, ctx.guild.id, True)
        else:
            result_embed.add_field(name="Résultat", value="Personne n'a trouvé la bonne réponse!", inline=False)

        await ctx.send(embed=result_embed)

    @commands.hybrid_command(name="triviastats", aliases=["quizstats"])
    async def triviastats(self, ctx: commands.Context):
        """Affiche le classement trivia."""
        leaderboard = await db.get_trivia_leaderboard(ctx.guild.id)

        embed = discord.Embed(
            title=f"{Emojis.TROPHY} Classement Trivia",
            color=Colors.PRIMARY
        )

        if not leaderboard:
            embed.description = "Aucune statistique disponible."
        else:
            lines = []
            medals = ["", "", ""]
            for i, data in enumerate(leaderboard, 1):
                member = ctx.guild.get_member(data['user_id'])
                name = member.display_name if member else f"Utilisateur #{data['user_id']}"
                accuracy = (data['correct_answers'] / data['total_questions'] * 100) if data['total_questions'] > 0 else 0
                medal = medals[i-1] if i <= 3 else f"**{i}.**"
                lines.append(f"{medal} {name} - {data['correct_answers']}/{data['total_questions']} ({accuracy:.0f}%)")
            embed.description = "\n".join(lines)

        await ctx.send(embed=embed)

    # ===============================
    # JEUX DE DES
    # ===============================

    @commands.hybrid_command(name="roll", aliases=["dice", "dé"])
    @app_commands.describe(des="Format: NdX (ex: 2d6 pour 2 dés à 6 faces)")
    async def roll(self, ctx: commands.Context, des: str = "1d6"):
        """Lance des dés."""
        try:
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
        """Lance une pièce (pile ou face)."""
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
        """Pose une question à la boule magique."""
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
        """Jouez à pierre-feuille-ciseaux."""
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

        # Normaliser le choix
        if user_choice in ["rock"]:
            user_choice = "pierre"
        elif user_choice in ["paper"]:
            user_choice = "feuille"
        elif user_choice in ["scissors"]:
            user_choice = "ciseaux"

        bot_choice = random.choice(["pierre", "feuille", "ciseaux"])

        # Déterminer le gagnant
        wins = {
            "pierre": "ciseaux",
            "feuille": "pierre",
            "ciseaux": "feuille"
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
        """Jouez à la machine à sous."""
        symbols = ["", "", "", "", "", "", ""]
        weights = [30, 25, 20, 15, 5, 3, 2]  # Probabilités

        reels = random.choices(symbols, weights=weights, k=3)

        # Calculer les gains
        if reels[0] == reels[1] == reels[2]:
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
            multiplier = 2
            result = f"Deux identiques! x{multiplier}"
            color = Colors.SUCCESS
        else:
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
    await bot.add_cog(Games(bot))
