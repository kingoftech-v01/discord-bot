"""AI chatbot cog with OpenAI API integration and conversation memory.

Falls back to free Hugging Face DialoGPT when OpenAI is unavailable.
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
    """Per-user, per-channel conversation history with auto-truncation."""

    def __init__(self, max_history: int = 10):
        self.conversations: Dict[str, List[Dict]] = {}
        self.max_history = max_history  # Exchange pairs, not messages

    def get_key(self, user_id: int, channel_id: int) -> str:
        return f"{user_id}_{channel_id}"

    def add_message(self, user_id: int, channel_id: int, role: str, content: str):
        """Add message and truncate to max_history * 2 (user + assistant pairs)."""
        key = self.get_key(user_id, channel_id)
        if key not in self.conversations:
            self.conversations[key] = []

        self.conversations[key].append({"role": role, "content": content})

        # Limit token usage by keeping only recent exchanges
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
    """AI chatbot cog with per-user conversation memory.

    Integrates with the OpenAI chat completions API (or any compatible
    endpoint) to provide conversational AI features. Also includes
    specialized commands for translation, summarization, explanation,
    code generation, and image generation (DALL-E 3).

    Falls back to a free Hugging Face DialoGPT endpoint when the primary
    API key is missing or the request fails.

    Attributes:
        bot: The bot instance this cog is attached to.
        conversations: The ``ConversationManager`` tracking per-user history.
        ai_channels: Set of channel IDs where the bot auto-responds to every
            message (configured via the ``aichannel`` command).
        system_prompt: The system-level instruction sent to the AI model
            before every conversation to define its personality and rules.
    """

    def __init__(self, bot: commands.Bot):
        """Initialize the AI cog with a conversation manager and system prompt.

        Args:
            bot: The bot instance to bind this cog to.
        """
        self.bot = bot
        self.conversations = ConversationManager()
        self.ai_channels = set()  # Channel IDs where the AI auto-responds
        self.system_prompt = """Tu es un assistant Discord amical et serviable.
Tu réponds de manière concise et utile en français.
Tu peux aider avec des questions générales, la programmation, et divertir les utilisateurs.
Tu es poli, respectueux et tu évites tout contenu inapproprié.
Garde tes réponses courtes (max 2000 caractères pour Discord)."""

    async def get_ai_response(self, messages: List[Dict], user_name: str) -> Optional[str]:
        """Send a chat completion request to the OpenAI-compatible API.

        Prepends the system prompt to the conversation messages and posts
        the request with a 30-second timeout. Returns ``None`` on any
        failure (missing key, HTTP error, timeout).

        Args:
            messages: The conversation history as a list of message dicts
                (each with ``role`` and ``content`` keys).
            user_name: The display name of the requesting user (reserved
                for future personalization).

        Returns:
            The AI-generated response string, or ``None`` if the request
            failed.
        """
        if not OPENAI_API_KEY:
            return None

        # Prepend the system prompt to set the AI's behavior
        full_messages = [
            {"role": "system", "content": self.system_prompt},
            *messages
        ]

        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }

        # Compatible with OpenAI, OpenRouter, Together AI, etc.
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
        """Fallback: get a response from the free Hugging Face DialoGPT API.

        Used when the primary OpenAI API key is missing or the primary
        request fails. Has a shorter 15-second timeout and simpler
        single-turn interface (no conversation history).

        Args:
            prompt: The user's message text to send to DialoGPT.

        Returns:
            The generated text response, or ``None`` if the request failed.
        """
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
        """Ask the AI assistant a question with full conversation memory.

        The user's question is added to the per-user/per-channel conversation
        history, the full history is sent to the AI, and the response is
        saved back into the history for follow-up context. Falls back to the
        free DialoGPT API if the primary API is unavailable.

        Responses are truncated to 1900 characters to stay within Discord's
        2000-character message limit (with room for the ellipsis).

        Args:
            ctx: The invocation context.
            question: The user's question or message for the AI.
        """
        if not AI_ENABLED:
            return await ctx.send(f"{Emojis.ERROR} L'AI n'est pas activée sur ce bot.")

        async with ctx.typing():
            # Record the user's message in conversation history
            self.conversations.add_message(
                ctx.author.id, ctx.channel.id, "user", question
            )

            # Retrieve the full conversation history for context
            history = self.conversations.get_history(ctx.author.id, ctx.channel.id)

            # Try the primary OpenAI-compatible API first
            response = await self.get_ai_response(history, ctx.author.display_name)

            # Fall back to the free Hugging Face API if the primary fails
            if not response:
                response = await self.get_free_ai_response(question)

            if not response:
                return await ctx.send(
                    f"{Emojis.ERROR} Impossible d'obtenir une réponse. L'API AI est peut-être indisponible."
                )

            # Truncate to stay within Discord's 2000-character message limit
            if len(response) > 1900:
                response = response[:1900] + "..."

            # Save the assistant's response for future conversation context
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
        """Generate an image from a text description using DALL-E 3.

        Requires a valid ``OPENAI_API_KEY`` with DALL-E access. Sends a
        1024x1024 image generation request with a 60-second timeout. The
        resulting image is displayed in an embed.

        Args:
            ctx: The invocation context.
            prompt: A natural-language description of the image to generate.
        """
        if not AI_ENABLED or not OPENAI_API_KEY:
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
                    timeout=60  # Image generation can be slow
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
        """Translate text to a target language using the AI model.

        Sends a single-turn translation prompt (no conversation history)
        and displays the original and translated text side by side. Both
        fields are truncated to 500 characters for embed limits.

        Args:
            ctx: The invocation context.
            langue: The target language code or name (e.g., ``"en"``, ``"es"``).
            texte: The text to translate.
        """
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
        """Summarize a long text into key bullet points using AI.

        Sends a single-turn summarization prompt and displays the result
        in an embed. Useful for condensing articles or lengthy messages.

        Args:
            ctx: The invocation context.
            texte: The long text to summarize.
        """
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
        """Explain a concept in simple terms (ELI5-style) using AI.

        Sends a single-turn explanation prompt and displays the result in
        an embed. The subject is truncated to 100 characters in the title.

        Args:
            ctx: The invocation context.
            sujet: The concept or topic to explain.
        """
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
        """Generate a code snippet in a specified programming language using AI.

        The response is wrapped in a Discord code block with syntax
        highlighting for the requested language. Truncated to 1900
        characters if the generated code is too long.

        Args:
            ctx: The invocation context.
            langage: The programming language (e.g., ``"python"``, ``"javascript"``).
            description: A natural-language description of what the code should do.
        """
        if not AI_ENABLED:
            return await ctx.send(f"{Emojis.ERROR} L'AI n'est pas activée.")

        prompt = f"Écris du code {langage} qui fait: {description}. Donne uniquement le code avec des commentaires explicatifs."

        async with ctx.typing():
            messages = [{"role": "user", "content": prompt}]
            response = await self.get_ai_response(messages, ctx.author.display_name)

            if not response:
                return await ctx.send(f"{Emojis.ERROR} Impossible de générer le code.")

            # Truncate long responses to stay within Discord's message limit
            if len(response) > 1900:
                response = response[:1900] + "\n... (code tronqué)"

            await ctx.send(f"```{langage}\n{response}\n```")

    @commands.hybrid_command(name="clearai", aliases=["resetai"])
    async def clearai(self, ctx: commands.Context):
        """Clear your AI conversation history in the current channel.

        Removes all stored messages for your user/channel combination,
        effectively starting a fresh conversation with no prior context.

        Args:
            ctx: The invocation context.
        """
        self.conversations.clear(ctx.author.id, ctx.channel.id)
        await ctx.send(f"{Emojis.SUCCESS} Historique de conversation effacé.")

    @commands.hybrid_command(name="aichannel")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(action="add/remove", channel="Le channel")
    async def aichannel(self, ctx: commands.Context, action: str, channel: Optional[discord.TextChannel] = None):
        """Add or remove a channel from the AI auto-response list (admin only).

        In channels on the auto-response list, the bot will reply to every
        non-bot message automatically (without requiring a command prefix).
        The channel IDs are stored in-memory and lost on restart.

        Args:
            ctx: The invocation context.
            action: Either ``"add"`` to enable or ``"remove"`` to disable
                auto-responses in the target channel.
            channel: The target text channel. Defaults to the current channel.
        """
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
        """Auto-respond to messages in designated AI channels or when mentioned.

        Triggers when a non-bot user sends a message in a channel that is
        in the ``ai_channels`` set, or when the bot is directly mentioned.
        Strips the bot mention from the content, records the message in
        conversation history, gets an AI response, and replies.

        Args:
            message: The incoming Discord message event.
        """
        if message.author.bot or not message.guild:
            return

        # Only respond in designated AI channels or when the bot is @mentioned
        if message.channel.id not in self.ai_channels and self.bot.user not in message.mentions:
            return

        if not AI_ENABLED:
            return

        # Strip bot mention tags from the message content
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
                # Truncate to stay within Discord's message limit
                if len(response) > 1900:
                    response = response[:1900] + "..."

                self.conversations.add_message(
                    message.author.id, message.channel.id, "assistant", response
                )

                await message.reply(response, mention_author=False)


async def setup(bot: commands.Bot):
    """Load the AI cog into the bot.

    Args:
        bot: The bot instance to register the cog with.
    """
    await bot.add_cog(AI(bot))
