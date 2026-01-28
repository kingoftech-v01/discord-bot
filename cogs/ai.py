"""
Cog pour l'intégration AI (chatbot intelligent).
Supporte OpenAI et des alternatives gratuites.
"""
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from typing import Optional, Dict, List
import aiohttp
import json
import asyncio

from config import Colors, Emojis, OPENAI_API_KEY, AI_MODEL, AI_ENABLED
from utils.database import db


class ConversationManager:
    """Gère les conversations AI par utilisateur/channel."""

    def __init__(self, max_history: int = 10):
        self.conversations: Dict[str, List[Dict]] = {}
        self.max_history = max_history

    def get_key(self, user_id: int, channel_id: int) -> str:
        return f"{user_id}_{channel_id}"

    def add_message(self, user_id: int, channel_id: int, role: str, content: str):
        key = self.get_key(user_id, channel_id)
        if key not in self.conversations:
            self.conversations[key] = []

        self.conversations[key].append({"role": role, "content": content})

        # Garder seulement les derniers messages
        if len(self.conversations[key]) > self.max_history * 2:
            self.conversations[key] = self.conversations[key][-self.max_history * 2:]

    def get_history(self, user_id: int, channel_id: int) -> List[Dict]:
        key = self.get_key(user_id, channel_id)
        return self.conversations.get(key, [])

    def clear(self, user_id: int, channel_id: int):
        key = self.get_key(user_id, channel_id)
        if key in self.conversations:
            del self.conversations[key]


class AI(commands.Cog):
    """Chatbot AI intelligent avec mémoire de conversation."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.conversations = ConversationManager()
        self.ai_channels = set()  # Channels où l'AI répond automatiquement
        self.system_prompt = """Tu es un assistant Discord amical et serviable.
Tu réponds de manière concise et utile en français.
Tu peux aider avec des questions générales, la programmation, et divertir les utilisateurs.
Tu es poli, respectueux et tu évites tout contenu inapproprié.
Garde tes réponses courtes (max 2000 caractères pour Discord)."""

    async def get_ai_response(self, messages: List[Dict], user_name: str) -> Optional[str]:
        """Obtient une réponse de l'API AI."""
        if not OPENAI_API_KEY or OPENAI_API_KEY == "YOUR_OPENAI_API_KEY":
            return None

        # Préparer les messages avec le system prompt
        full_messages = [
            {"role": "system", "content": self.system_prompt},
            *messages
        ]

        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }

        # Support pour OpenAI ou compatible (OpenRouter, Together, etc.)
        api_url = "https://api.openai.com/v1/chat/completions"

        payload = {
            "model": AI_MODEL,
            "messages": full_messages,
            "max_tokens": 500,
            "temperature": 0.7
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, headers=headers, json=payload, timeout=30) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data["choices"][0]["message"]["content"]
                    else:
                        error = await resp.text()
                        print(f"Erreur API AI: {resp.status} - {error}")
                        return None
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            print(f"Erreur AI: {e}")
            return None

    async def get_free_ai_response(self, prompt: str) -> Optional[str]:
        """Utilise une API AI gratuite comme fallback."""
        # Utilisation de l'API gratuite de Hugging Face ou similaire
        api_url = "https://api-inference.huggingface.co/models/microsoft/DialoGPT-medium"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url,
                    json={"inputs": prompt},
                    timeout=15
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if isinstance(data, list) and len(data) > 0:
                            return data[0].get("generated_text", "")
                    return None
        except Exception:
            return None

    @commands.hybrid_command(name="ask", aliases=["ai", "chat", "gpt"])
    @app_commands.describe(question="Votre question pour l'AI")
    async def ask(self, ctx: commands.Context, *, question: str):
        """Pose une question à l'assistant AI."""
        if not AI_ENABLED:
            return await ctx.send(f"{Emojis.ERROR} L'AI n'est pas activée sur ce bot.")

        async with ctx.typing():
            # Ajouter le message de l'utilisateur
            self.conversations.add_message(
                ctx.author.id, ctx.channel.id, "user", question
            )

            # Obtenir l'historique
            history = self.conversations.get_history(ctx.author.id, ctx.channel.id)

            # Essayer l'API principale
            response = await self.get_ai_response(history, ctx.author.display_name)

            # Fallback vers API gratuite si nécessaire
            if not response:
                response = await self.get_free_ai_response(question)

            if not response:
                return await ctx.send(
                    f"{Emojis.ERROR} Impossible d'obtenir une réponse. L'API AI est peut-être indisponible."
                )

            # Limiter la réponse à 2000 caractères (limite Discord)
            if len(response) > 1900:
                response = response[:1900] + "..."

            # Sauvegarder la réponse dans l'historique
            self.conversations.add_message(
                ctx.author.id, ctx.channel.id, "assistant", response
            )

            embed = discord.Embed(
                description=response,
                color=Colors.PRIMARY,
                timestamp=datetime.now()
            )
            embed.set_author(
                name=f"Réponse à {ctx.author.display_name}",
                icon_url=ctx.author.display_avatar.url
            )
            embed.set_footer(text="Powered by AI")

            await ctx.send(embed=embed)

    @commands.hybrid_command(name="imagine", aliases=["draw", "image"])
    @app_commands.describe(prompt="Description de l'image à générer")
    async def imagine(self, ctx: commands.Context, *, prompt: str):
        """Génère une image avec l'AI (nécessite DALL-E ou similaire)."""
        if not AI_ENABLED or not OPENAI_API_KEY or OPENAI_API_KEY == "YOUR_OPENAI_API_KEY":
            return await ctx.send(f"{Emojis.ERROR} La génération d'images n'est pas configurée.")

        await ctx.send(f"{Emojis.LOADING} Génération de l'image en cours...")

        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "dall-e-3",
            "prompt": prompt,
            "n": 1,
            "size": "1024x1024"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.openai.com/v1/images/generations",
                    headers=headers,
                    json=payload,
                    timeout=60
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        image_url = data["data"][0]["url"]

                        embed = discord.Embed(
                            title="Image générée",
                            description=f"**Prompt:** {prompt[:200]}",
                            color=Colors.PRIMARY
                        )
                        embed.set_image(url=image_url)
                        embed.set_footer(text=f"Demandé par {ctx.author.display_name}")

                        await ctx.send(embed=embed)
                    else:
                        error = await resp.json()
                        await ctx.send(f"{Emojis.ERROR} Erreur: {error.get('error', {}).get('message', 'Inconnue')}")
        except asyncio.TimeoutError:
            await ctx.send(f"{Emojis.ERROR} La génération a pris trop de temps.")
        except Exception as e:
            await ctx.send(f"{Emojis.ERROR} Erreur lors de la génération: {str(e)[:100]}")

    @commands.hybrid_command(name="translate", aliases=["trad", "traduire"])
    @app_commands.describe(
        langue="Langue cible (fr, en, es, de, etc.)",
        texte="Le texte à traduire"
    )
    async def translate(self, ctx: commands.Context, langue: str, *, texte: str):
        """Traduit un texte dans une autre langue."""
        if not AI_ENABLED:
            return await ctx.send(f"{Emojis.ERROR} L'AI n'est pas activée.")

        prompt = f"Traduis ce texte en {langue} (réponds uniquement avec la traduction): {texte}"

        async with ctx.typing():
            messages = [{"role": "user", "content": prompt}]
            response = await self.get_ai_response(messages, ctx.author.display_name)

            if not response:
                return await ctx.send(f"{Emojis.ERROR} Impossible de traduire.")

            embed = discord.Embed(
                title=f"Traduction → {langue.upper()}",
                color=Colors.PRIMARY
            )
            embed.add_field(name="Original", value=texte[:500], inline=False)
            embed.add_field(name="Traduction", value=response[:500], inline=False)

            await ctx.send(embed=embed)

    @commands.hybrid_command(name="summarize", aliases=["resume", "résume"])
    @app_commands.describe(texte="Le texte à résumer")
    async def summarize(self, ctx: commands.Context, *, texte: str):
        """Résume un texte long."""
        if not AI_ENABLED:
            return await ctx.send(f"{Emojis.ERROR} L'AI n'est pas activée.")

        prompt = f"Résume ce texte en quelques points clés (en français): {texte}"

        async with ctx.typing():
            messages = [{"role": "user", "content": prompt}]
            response = await self.get_ai_response(messages, ctx.author.display_name)

            if not response:
                return await ctx.send(f"{Emojis.ERROR} Impossible de résumer.")

            embed = discord.Embed(
                title="Résumé",
                description=response,
                color=Colors.PRIMARY
            )

            await ctx.send(embed=embed)

    @commands.hybrid_command(name="explain", aliases=["explique"])
    @app_commands.describe(sujet="Le sujet à expliquer")
    async def explain(self, ctx: commands.Context, *, sujet: str):
        """Explique un concept de manière simple."""
        if not AI_ENABLED:
            return await ctx.send(f"{Emojis.ERROR} L'AI n'est pas activée.")

        prompt = f"Explique simplement ce concept à quelqu'un qui n'y connaît rien (en français): {sujet}"

        async with ctx.typing():
            messages = [{"role": "user", "content": prompt}]
            response = await self.get_ai_response(messages, ctx.author.display_name)

            if not response:
                return await ctx.send(f"{Emojis.ERROR} Impossible d'expliquer.")

            embed = discord.Embed(
                title=f"Explication: {sujet[:100]}",
                description=response,
                color=Colors.PRIMARY
            )

            await ctx.send(embed=embed)

    @commands.hybrid_command(name="code", aliases=["coder"])
    @app_commands.describe(
        langage="Le langage de programmation",
        description="Ce que le code doit faire"
    )
    async def code(self, ctx: commands.Context, langage: str, *, description: str):
        """Génère du code selon votre description."""
        if not AI_ENABLED:
            return await ctx.send(f"{Emojis.ERROR} L'AI n'est pas activée.")

        prompt = f"Écris du code {langage} qui fait: {description}. Donne uniquement le code avec des commentaires explicatifs."

        async with ctx.typing():
            messages = [{"role": "user", "content": prompt}]
            response = await self.get_ai_response(messages, ctx.author.display_name)

            if not response:
                return await ctx.send(f"{Emojis.ERROR} Impossible de générer le code.")

            # Si la réponse est trop longue, la couper
            if len(response) > 1900:
                response = response[:1900] + "\n... (code tronqué)"

            await ctx.send(f"```{langage}\n{response}\n```")

    @commands.hybrid_command(name="clearai", aliases=["resetai"])
    async def clearai(self, ctx: commands.Context):
        """Efface l'historique de conversation AI."""
        self.conversations.clear(ctx.author.id, ctx.channel.id)
        await ctx.send(f"{Emojis.SUCCESS} Historique de conversation effacé.")

    @commands.hybrid_command(name="aichannel")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(action="add/remove", channel="Le channel")
    async def aichannel(self, ctx: commands.Context, action: str, channel: Optional[discord.TextChannel] = None):
        """Configure les channels où l'AI répond automatiquement."""
        ch = channel or ctx.channel

        if action.lower() == "add":
            self.ai_channels.add(ch.id)
            await ctx.send(f"{Emojis.SUCCESS} L'AI répondra automatiquement dans {ch.mention}")
        elif action.lower() == "remove":
            self.ai_channels.discard(ch.id)
            await ctx.send(f"{Emojis.SUCCESS} L'AI ne répondra plus automatiquement dans {ch.mention}")
        else:
            await ctx.send(f"{Emojis.ERROR} Utilisez: add ou remove")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Répond automatiquement dans les channels AI configurés."""
        if message.author.bot or not message.guild:
            return

        # Vérifier si c'est un channel AI ou si le bot est mentionné
        if message.channel.id not in self.ai_channels and self.bot.user not in message.mentions:
            return

        if not AI_ENABLED:
            return

        # Nettoyer le message (retirer la mention du bot)
        content = message.content.replace(f"<@{self.bot.user.id}>", "").strip()
        content = content.replace(f"<@!{self.bot.user.id}>", "").strip()

        if not content:
            return

        async with message.channel.typing():
            self.conversations.add_message(
                message.author.id, message.channel.id, "user", content
            )

            history = self.conversations.get_history(message.author.id, message.channel.id)
            response = await self.get_ai_response(history, message.author.display_name)

            if response:
                if len(response) > 1900:
                    response = response[:1900] + "..."

                self.conversations.add_message(
                    message.author.id, message.channel.id, "assistant", response
                )

                await message.reply(response, mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(AI(bot))
