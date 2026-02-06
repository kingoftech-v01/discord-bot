"""
Comprehensive tests for three low-coverage Discord bot cogs:
  - cogs/ai.py (AI chatbot with OpenAI integration)
  - cogs/games.py (Economy and casual games)
  - cogs/utility.py (Server utilities, reminders, AFK, polls, memes, calc)

Every test imports the real cog classes and exercises the actual code paths
rather than testing logic in isolation. Database access and HTTP calls are
mocked at the module level so no real I/O is performed.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
from datetime import datetime, timedelta
import asyncio
import random

import discord
from discord.ext import commands


# ============================================================================
# SHARED FIXTURES
# ============================================================================

@pytest.fixture
def mock_bot():
    """Create a mock Discord bot with common attributes."""
    bot = MagicMock(spec=commands.Bot)
    bot.user = MagicMock()
    bot.user.id = 999999999
    bot.user.name = "TestBot"
    bot.user.display_avatar = MagicMock()
    bot.user.display_avatar.url = "https://cdn.discordapp.com/avatar.png"
    bot.get_channel = MagicMock(return_value=MagicMock())
    bot.get_user = MagicMock(return_value=MagicMock())
    bot.wait_until_ready = AsyncMock()
    bot.wait_for = AsyncMock()
    bot.latency = 0.05
    bot.guilds = []
    return bot


@pytest.fixture
def mock_ctx():
    """Create a mock command context with all commonly needed attributes."""
    ctx = MagicMock(spec=commands.Context)
    ctx.guild = MagicMock(spec=discord.Guild)
    ctx.guild.id = 987654321
    ctx.guild.name = "Test Server"
    ctx.guild.member_count = 42
    ctx.guild.icon = MagicMock()
    ctx.guild.icon.url = "https://cdn.discordapp.com/icon.png"
    ctx.guild.owner = MagicMock(spec=discord.Member)
    ctx.guild.owner.mention = "<@111>"
    ctx.guild.created_at = datetime(2020, 1, 15)
    ctx.guild.text_channels = [MagicMock() for _ in range(5)]
    ctx.guild.voice_channels = [MagicMock() for _ in range(2)]
    ctx.guild.categories = [MagicMock() for _ in range(3)]
    ctx.guild.roles = [MagicMock() for _ in range(4)]
    ctx.guild.premium_subscription_count = 0
    ctx.guild.premium_tier = 0
    ctx.guild.get_member = MagicMock(return_value=None)

    # Members list for serverinfo (online/bot counting)
    member1 = MagicMock()
    member1.status = discord.Status.online
    member1.bot = False
    member2 = MagicMock()
    member2.status = discord.Status.offline
    member2.bot = True
    ctx.guild.members = [member1, member2]

    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.id = 123456789
    ctx.author.mention = "<@123456789>"
    ctx.author.display_name = "TestUser"
    ctx.author.display_avatar = MagicMock()
    ctx.author.display_avatar.url = "https://cdn.discordapp.com/avatar.png"
    ctx.author.display_avatar.is_animated = MagicMock(return_value=False)
    ctx.author.display_avatar.replace = MagicMock(return_value="https://cdn.discordapp.com/avatar_replaced.png")
    ctx.author.bot = False
    ctx.author.nick = None
    ctx.author.color = discord.Color.default()
    ctx.author.created_at = datetime(2019, 3, 10, 14, 30)
    ctx.author.joined_at = datetime(2020, 6, 15, 12, 0)
    ctx.author.premium_since = None
    ctx.author.roles = [MagicMock()]  # @everyone
    ctx.author.guild_permissions = MagicMock()

    ctx.send = AsyncMock()
    ctx.channel = MagicMock()
    ctx.channel.id = 555555555
    ctx.channel.send = AsyncMock()
    ctx.channel.mention = "<#555555555>"
    ctx.message = MagicMock()
    ctx.message.delete = AsyncMock()
    ctx.prefix = "!"

    # typing() context manager
    ctx.typing = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(), __aexit__=AsyncMock()
    ))

    return ctx


# ============================================================================
# HELPER: Build an aiohttp mock session
# ============================================================================

def _make_aiohttp_session(status=200, json_data=None, text_data="error"):
    """Return a mock aiohttp.ClientSession that can be used as async context manager."""
    mock_response = AsyncMock()
    mock_response.status = status
    mock_response.json = AsyncMock(return_value=json_data or {})
    mock_response.text = AsyncMock(return_value=text_data)

    mock_post_cm = AsyncMock()
    mock_post_cm.__aenter__ = AsyncMock(return_value=mock_response)
    mock_post_cm.__aexit__ = AsyncMock(return_value=False)

    mock_get_cm = AsyncMock()
    mock_get_cm.__aenter__ = AsyncMock(return_value=mock_response)
    mock_get_cm.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_post_cm)
    mock_session.get = MagicMock(return_value=mock_get_cm)

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)

    return mock_session_cm, mock_session, mock_response


# ############################################################################
#
#                              AI COG TESTS
#
# ############################################################################

class TestAICogInit:
    """Tests for AI cog initialization."""

    def test_ai_init_sets_bot(self, mock_bot):
        from cogs.ai import AI
        cog = AI(mock_bot)
        assert cog.bot is mock_bot

    def test_ai_init_creates_conversation_manager(self, mock_bot):
        from cogs.ai import AI, ConversationManager
        cog = AI(mock_bot)
        assert isinstance(cog.conversations, ConversationManager)

    def test_ai_init_channels_empty(self, mock_bot):
        from cogs.ai import AI
        cog = AI(mock_bot)
        assert len(cog.ai_channels) == 0

    def test_ai_init_system_prompt_nonempty(self, mock_bot):
        from cogs.ai import AI
        cog = AI(mock_bot)
        assert len(cog.system_prompt) > 0
        assert "Discord" in cog.system_prompt


class TestGetAIResponse:
    """Tests for AI.get_ai_response -- the primary OpenAI API call."""

    @pytest.mark.asyncio
    @patch('cogs.ai.OPENAI_API_KEY', '')
    async def test_returns_none_without_api_key(self, mock_bot):
        from cogs.ai import AI
        cog = AI(mock_bot)
        result = await cog.get_ai_response([{"role": "user", "content": "hi"}], "User")
        assert result is None

    @pytest.mark.asyncio
    @patch('cogs.ai.OPENAI_API_KEY', 'test-key')
    @patch('cogs.ai.aiohttp.ClientSession')
    async def test_success_returns_content(self, mock_aiohttp, mock_bot):
        from cogs.ai import AI
        cog = AI(mock_bot)

        session_cm, session, response = _make_aiohttp_session(
            status=200,
            json_data={"choices": [{"message": {"content": "Hello world"}}]}
        )
        mock_aiohttp.return_value = session_cm

        result = await cog.get_ai_response([{"role": "user", "content": "hi"}], "User")
        assert result == "Hello world"

    @pytest.mark.asyncio
    @patch('cogs.ai.OPENAI_API_KEY', 'test-key')
    @patch('cogs.ai.aiohttp.ClientSession')
    async def test_non_200_returns_none(self, mock_aiohttp, mock_bot):
        from cogs.ai import AI
        cog = AI(mock_bot)

        session_cm, _, _ = _make_aiohttp_session(status=500, text_data="Internal Server Error")
        mock_aiohttp.return_value = session_cm

        result = await cog.get_ai_response([{"role": "user", "content": "hi"}], "User")
        assert result is None

    @pytest.mark.asyncio
    @patch('cogs.ai.OPENAI_API_KEY', 'test-key')
    @patch('cogs.ai.aiohttp.ClientSession')
    async def test_timeout_returns_none(self, mock_aiohttp, mock_bot):
        from cogs.ai import AI
        cog = AI(mock_bot)

        mock_aiohttp.return_value.__aenter__ = AsyncMock(side_effect=asyncio.TimeoutError)
        mock_aiohttp.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await cog.get_ai_response([{"role": "user", "content": "hi"}], "User")
        assert result is None

    @pytest.mark.asyncio
    @patch('cogs.ai.OPENAI_API_KEY', 'test-key')
    @patch('cogs.ai.aiohttp.ClientSession')
    async def test_generic_exception_returns_none(self, mock_aiohttp, mock_bot):
        from cogs.ai import AI
        cog = AI(mock_bot)

        mock_aiohttp.return_value.__aenter__ = AsyncMock(side_effect=RuntimeError("boom"))
        mock_aiohttp.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await cog.get_ai_response([{"role": "user", "content": "hi"}], "User")
        assert result is None


class TestGetFreeAIResponse:
    """Tests for AI.get_free_ai_response -- the HuggingFace fallback."""

    @pytest.mark.asyncio
    @patch('cogs.ai.aiohttp.ClientSession')
    async def test_success_returns_generated_text(self, mock_aiohttp, mock_bot):
        from cogs.ai import AI
        cog = AI(mock_bot)

        session_cm, _, _ = _make_aiohttp_session(
            status=200,
            json_data=[{"generated_text": "free response"}]
        )
        mock_aiohttp.return_value = session_cm

        result = await cog.get_free_ai_response("hi")
        assert result == "free response"

    @pytest.mark.asyncio
    @patch('cogs.ai.aiohttp.ClientSession')
    async def test_empty_list_returns_none(self, mock_aiohttp, mock_bot):
        from cogs.ai import AI
        cog = AI(mock_bot)

        session_cm, _, _ = _make_aiohttp_session(status=200, json_data=[])
        mock_aiohttp.return_value = session_cm

        result = await cog.get_free_ai_response("hi")
        assert result is None

    @pytest.mark.asyncio
    @patch('cogs.ai.aiohttp.ClientSession')
    async def test_non_list_returns_none(self, mock_aiohttp, mock_bot):
        from cogs.ai import AI
        cog = AI(mock_bot)

        session_cm, _, _ = _make_aiohttp_session(status=200, json_data={"error": "model loading"})
        mock_aiohttp.return_value = session_cm

        result = await cog.get_free_ai_response("hi")
        assert result is None

    @pytest.mark.asyncio
    @patch('cogs.ai.aiohttp.ClientSession')
    async def test_non_200_returns_none(self, mock_aiohttp, mock_bot):
        from cogs.ai import AI
        cog = AI(mock_bot)

        session_cm, _, _ = _make_aiohttp_session(status=503)
        mock_aiohttp.return_value = session_cm

        result = await cog.get_free_ai_response("hi")
        assert result is None

    @pytest.mark.asyncio
    @patch('cogs.ai.aiohttp.ClientSession')
    async def test_exception_returns_none(self, mock_aiohttp, mock_bot):
        from cogs.ai import AI
        cog = AI(mock_bot)

        mock_aiohttp.return_value.__aenter__ = AsyncMock(side_effect=Exception("network error"))
        mock_aiohttp.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await cog.get_free_ai_response("hi")
        assert result is None


class TestAskCommand:
    """Tests for AI.ask -- the main Q&A command."""

    @pytest.mark.asyncio
    @patch('cogs.ai.AI_ENABLED', False)
    async def test_ask_disabled(self, mock_bot, mock_ctx):
        from cogs.ai import AI
        cog = AI(mock_bot)
        await cog.ask(cog, mock_ctx, question="hello")
        mock_ctx.send.assert_awaited()
        args = mock_ctx.send.call_args
        assert "activée" in str(args) or "ERROR" in str(args)

    @pytest.mark.asyncio
    @patch('cogs.ai.AI_ENABLED', True)
    @patch('cogs.ai.OPENAI_API_KEY', 'test-key')
    @patch('cogs.ai.aiohttp.ClientSession')
    async def test_ask_success_primary_api(self, mock_aiohttp, mock_bot, mock_ctx):
        from cogs.ai import AI
        cog = AI(mock_bot)

        session_cm, _, _ = _make_aiohttp_session(
            status=200,
            json_data={"choices": [{"message": {"content": "AI answer"}}]}
        )
        mock_aiohttp.return_value = session_cm

        await cog.ask(cog, mock_ctx, question="What is Python?")

        # Verify conversation history was updated
        history = cog.conversations.get_history(mock_ctx.author.id, mock_ctx.channel.id)
        assert len(history) == 2  # user message + assistant response
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"

        # Verify embed was sent
        mock_ctx.send.assert_awaited()
        call_kwargs = mock_ctx.send.call_args
        assert call_kwargs is not None

    @pytest.mark.asyncio
    @patch('cogs.ai.AI_ENABLED', True)
    @patch('cogs.ai.OPENAI_API_KEY', '')
    @patch('cogs.ai.aiohttp.ClientSession')
    async def test_ask_fallback_to_free_api(self, mock_aiohttp, mock_bot, mock_ctx):
        from cogs.ai import AI
        cog = AI(mock_bot)

        # Free API returns a response
        session_cm, _, _ = _make_aiohttp_session(
            status=200,
            json_data=[{"generated_text": "free answer"}]
        )
        mock_aiohttp.return_value = session_cm

        await cog.ask(cog, mock_ctx, question="hello")
        mock_ctx.send.assert_awaited()

    @pytest.mark.asyncio
    @patch('cogs.ai.AI_ENABLED', True)
    @patch('cogs.ai.OPENAI_API_KEY', '')
    @patch('cogs.ai.aiohttp.ClientSession')
    async def test_ask_both_apis_fail(self, mock_aiohttp, mock_bot, mock_ctx):
        from cogs.ai import AI
        cog = AI(mock_bot)

        # Both APIs return None
        session_cm, _, _ = _make_aiohttp_session(status=500)
        mock_aiohttp.return_value = session_cm

        await cog.ask(cog, mock_ctx, question="hello")
        mock_ctx.send.assert_awaited()
        args_str = str(mock_ctx.send.call_args)
        assert "Impossible" in args_str or "ERROR" in args_str

    @pytest.mark.asyncio
    @patch('cogs.ai.AI_ENABLED', True)
    @patch('cogs.ai.OPENAI_API_KEY', 'test-key')
    @patch('cogs.ai.aiohttp.ClientSession')
    async def test_ask_truncates_long_response(self, mock_aiohttp, mock_bot, mock_ctx):
        from cogs.ai import AI
        cog = AI(mock_bot)

        long_text = "x" * 2000
        session_cm, _, _ = _make_aiohttp_session(
            status=200,
            json_data={"choices": [{"message": {"content": long_text}}]}
        )
        mock_aiohttp.return_value = session_cm

        await cog.ask(cog, mock_ctx, question="generate long text")

        # The assistant response stored in history should be truncated
        history = cog.conversations.get_history(mock_ctx.author.id, mock_ctx.channel.id)
        assert len(history[1]["content"]) <= 1903  # 1900 + "..."


class TestImagineCommand:
    """Tests for AI.imagine -- DALL-E image generation."""

    @pytest.mark.asyncio
    @patch('cogs.ai.AI_ENABLED', False)
    async def test_imagine_disabled(self, mock_bot, mock_ctx):
        from cogs.ai import AI
        cog = AI(mock_bot)
        await cog.imagine(cog, mock_ctx, prompt="a cat")
        mock_ctx.send.assert_awaited()
        assert "configurée" in str(mock_ctx.send.call_args) or "ERROR" in str(mock_ctx.send.call_args)

    @pytest.mark.asyncio
    @patch('cogs.ai.AI_ENABLED', True)
    @patch('cogs.ai.OPENAI_API_KEY', '')
    async def test_imagine_no_api_key(self, mock_bot, mock_ctx):
        from cogs.ai import AI
        cog = AI(mock_bot)
        await cog.imagine(cog, mock_ctx, prompt="a cat")
        mock_ctx.send.assert_awaited()

    @pytest.mark.asyncio
    @patch('cogs.ai.AI_ENABLED', True)
    @patch('cogs.ai.OPENAI_API_KEY', 'test-key')
    @patch('cogs.ai.aiohttp.ClientSession')
    async def test_imagine_success(self, mock_aiohttp, mock_bot, mock_ctx):
        from cogs.ai import AI
        cog = AI(mock_bot)

        session_cm, _, _ = _make_aiohttp_session(
            status=200,
            json_data={"data": [{"url": "https://example.com/image.png"}]}
        )
        mock_aiohttp.return_value = session_cm

        await cog.imagine(cog, mock_ctx, prompt="a cat")
        # First call: loading message; second call: embed with image
        assert mock_ctx.send.await_count >= 2

    @pytest.mark.asyncio
    @patch('cogs.ai.AI_ENABLED', True)
    @patch('cogs.ai.OPENAI_API_KEY', 'test-key')
    @patch('cogs.ai.aiohttp.ClientSession')
    async def test_imagine_api_error(self, mock_aiohttp, mock_bot, mock_ctx):
        from cogs.ai import AI
        cog = AI(mock_bot)

        session_cm, _, _ = _make_aiohttp_session(
            status=400,
            json_data={"error": {"message": "Bad prompt"}}
        )
        mock_aiohttp.return_value = session_cm

        await cog.imagine(cog, mock_ctx, prompt="bad prompt")
        assert mock_ctx.send.await_count >= 2  # loading + error

    @pytest.mark.asyncio
    @patch('cogs.ai.AI_ENABLED', True)
    @patch('cogs.ai.OPENAI_API_KEY', 'test-key')
    @patch('cogs.ai.aiohttp.ClientSession')
    async def test_imagine_timeout(self, mock_aiohttp, mock_bot, mock_ctx):
        from cogs.ai import AI
        cog = AI(mock_bot)

        mock_aiohttp.return_value.__aenter__ = AsyncMock(side_effect=asyncio.TimeoutError)
        mock_aiohttp.return_value.__aexit__ = AsyncMock(return_value=False)

        await cog.imagine(cog, mock_ctx, prompt="a cat")
        assert mock_ctx.send.await_count >= 2

    @pytest.mark.asyncio
    @patch('cogs.ai.AI_ENABLED', True)
    @patch('cogs.ai.OPENAI_API_KEY', 'test-key')
    @patch('cogs.ai.aiohttp.ClientSession')
    async def test_imagine_generic_exception(self, mock_aiohttp, mock_bot, mock_ctx):
        from cogs.ai import AI
        cog = AI(mock_bot)

        mock_aiohttp.return_value.__aenter__ = AsyncMock(side_effect=RuntimeError("boom"))
        mock_aiohttp.return_value.__aexit__ = AsyncMock(return_value=False)

        await cog.imagine(cog, mock_ctx, prompt="a cat")
        assert mock_ctx.send.await_count >= 2


class TestTranslateCommand:
    """Tests for AI.translate."""

    @pytest.mark.asyncio
    @patch('cogs.ai.AI_ENABLED', False)
    async def test_translate_disabled(self, mock_bot, mock_ctx):
        from cogs.ai import AI
        cog = AI(mock_bot)
        await cog.translate(cog, mock_ctx, langue="en", texte="Bonjour")
        mock_ctx.send.assert_awaited()

    @pytest.mark.asyncio
    @patch('cogs.ai.AI_ENABLED', True)
    @patch('cogs.ai.OPENAI_API_KEY', 'test-key')
    @patch('cogs.ai.aiohttp.ClientSession')
    async def test_translate_success(self, mock_aiohttp, mock_bot, mock_ctx):
        from cogs.ai import AI
        cog = AI(mock_bot)

        session_cm, _, _ = _make_aiohttp_session(
            status=200,
            json_data={"choices": [{"message": {"content": "Hello"}}]}
        )
        mock_aiohttp.return_value = session_cm

        await cog.translate(cog, mock_ctx, langue="en", texte="Bonjour")
        mock_ctx.send.assert_awaited()
        call_kwargs = mock_ctx.send.call_args
        embed = call_kwargs.kwargs.get('embed') or (call_kwargs.args[0] if call_kwargs.args else None)
        # Verify the command completed (embed sent)
        assert call_kwargs is not None

    @pytest.mark.asyncio
    @patch('cogs.ai.AI_ENABLED', True)
    @patch('cogs.ai.OPENAI_API_KEY', 'test-key')
    @patch('cogs.ai.aiohttp.ClientSession')
    async def test_translate_api_failure(self, mock_aiohttp, mock_bot, mock_ctx):
        from cogs.ai import AI
        cog = AI(mock_bot)

        session_cm, _, _ = _make_aiohttp_session(status=500)
        mock_aiohttp.return_value = session_cm

        await cog.translate(cog, mock_ctx, langue="en", texte="Bonjour")
        args_str = str(mock_ctx.send.call_args)
        assert "Impossible" in args_str or "traduire" in args_str


class TestSummarizeCommand:
    """Tests for AI.summarize."""

    @pytest.mark.asyncio
    @patch('cogs.ai.AI_ENABLED', False)
    async def test_summarize_disabled(self, mock_bot, mock_ctx):
        from cogs.ai import AI
        cog = AI(mock_bot)
        await cog.summarize(cog, mock_ctx, texte="Long text here")
        mock_ctx.send.assert_awaited()

    @pytest.mark.asyncio
    @patch('cogs.ai.AI_ENABLED', True)
    @patch('cogs.ai.OPENAI_API_KEY', 'test-key')
    @patch('cogs.ai.aiohttp.ClientSession')
    async def test_summarize_success(self, mock_aiohttp, mock_bot, mock_ctx):
        from cogs.ai import AI
        cog = AI(mock_bot)

        session_cm, _, _ = _make_aiohttp_session(
            status=200,
            json_data={"choices": [{"message": {"content": "- Point 1\n- Point 2"}}]}
        )
        mock_aiohttp.return_value = session_cm

        await cog.summarize(cog, mock_ctx, texte="Very long text")
        mock_ctx.send.assert_awaited()

    @pytest.mark.asyncio
    @patch('cogs.ai.AI_ENABLED', True)
    @patch('cogs.ai.OPENAI_API_KEY', 'test-key')
    @patch('cogs.ai.aiohttp.ClientSession')
    async def test_summarize_api_failure(self, mock_aiohttp, mock_bot, mock_ctx):
        from cogs.ai import AI
        cog = AI(mock_bot)

        session_cm, _, _ = _make_aiohttp_session(status=500)
        mock_aiohttp.return_value = session_cm

        await cog.summarize(cog, mock_ctx, texte="text")
        assert "résumer" in str(mock_ctx.send.call_args) or "Impossible" in str(mock_ctx.send.call_args)


class TestExplainCommand:
    """Tests for AI.explain."""

    @pytest.mark.asyncio
    @patch('cogs.ai.AI_ENABLED', False)
    async def test_explain_disabled(self, mock_bot, mock_ctx):
        from cogs.ai import AI
        cog = AI(mock_bot)
        await cog.explain(cog, mock_ctx, sujet="quantum physics")
        mock_ctx.send.assert_awaited()

    @pytest.mark.asyncio
    @patch('cogs.ai.AI_ENABLED', True)
    @patch('cogs.ai.OPENAI_API_KEY', 'test-key')
    @patch('cogs.ai.aiohttp.ClientSession')
    async def test_explain_success(self, mock_aiohttp, mock_bot, mock_ctx):
        from cogs.ai import AI
        cog = AI(mock_bot)

        session_cm, _, _ = _make_aiohttp_session(
            status=200,
            json_data={"choices": [{"message": {"content": "Quantum physics is..."}}]}
        )
        mock_aiohttp.return_value = session_cm

        await cog.explain(cog, mock_ctx, sujet="quantum physics")
        mock_ctx.send.assert_awaited()

    @pytest.mark.asyncio
    @patch('cogs.ai.AI_ENABLED', True)
    @patch('cogs.ai.OPENAI_API_KEY', 'test-key')
    @patch('cogs.ai.aiohttp.ClientSession')
    async def test_explain_api_failure(self, mock_aiohttp, mock_bot, mock_ctx):
        from cogs.ai import AI
        cog = AI(mock_bot)

        session_cm, _, _ = _make_aiohttp_session(status=500)
        mock_aiohttp.return_value = session_cm

        await cog.explain(cog, mock_ctx, sujet="topic")
        assert "expliquer" in str(mock_ctx.send.call_args) or "Impossible" in str(mock_ctx.send.call_args)


class TestCodeCommand:
    """Tests for AI.code."""

    @pytest.mark.asyncio
    @patch('cogs.ai.AI_ENABLED', False)
    async def test_code_disabled(self, mock_bot, mock_ctx):
        from cogs.ai import AI
        cog = AI(mock_bot)
        await cog.code(cog, mock_ctx, langage="python", description="hello world")
        mock_ctx.send.assert_awaited()

    @pytest.mark.asyncio
    @patch('cogs.ai.AI_ENABLED', True)
    @patch('cogs.ai.OPENAI_API_KEY', 'test-key')
    @patch('cogs.ai.aiohttp.ClientSession')
    async def test_code_success(self, mock_aiohttp, mock_bot, mock_ctx):
        from cogs.ai import AI
        cog = AI(mock_bot)

        session_cm, _, _ = _make_aiohttp_session(
            status=200,
            json_data={"choices": [{"message": {"content": "print('hello')"}}]}
        )
        mock_aiohttp.return_value = session_cm

        await cog.code(cog, mock_ctx, langage="python", description="hello world")
        mock_ctx.send.assert_awaited()
        sent = str(mock_ctx.send.call_args)
        assert "python" in sent

    @pytest.mark.asyncio
    @patch('cogs.ai.AI_ENABLED', True)
    @patch('cogs.ai.OPENAI_API_KEY', 'test-key')
    @patch('cogs.ai.aiohttp.ClientSession')
    async def test_code_truncates_long_output(self, mock_aiohttp, mock_bot, mock_ctx):
        from cogs.ai import AI
        cog = AI(mock_bot)

        long_code = "x = 1\n" * 500  # > 1900 chars
        session_cm, _, _ = _make_aiohttp_session(
            status=200,
            json_data={"choices": [{"message": {"content": long_code}}]}
        )
        mock_aiohttp.return_value = session_cm

        await cog.code(cog, mock_ctx, langage="python", description="big code")
        sent = str(mock_ctx.send.call_args)
        assert "tronqué" in sent or len(sent) < 2100

    @pytest.mark.asyncio
    @patch('cogs.ai.AI_ENABLED', True)
    @patch('cogs.ai.OPENAI_API_KEY', 'test-key')
    @patch('cogs.ai.aiohttp.ClientSession')
    async def test_code_api_failure(self, mock_aiohttp, mock_bot, mock_ctx):
        from cogs.ai import AI
        cog = AI(mock_bot)

        session_cm, _, _ = _make_aiohttp_session(status=500)
        mock_aiohttp.return_value = session_cm

        await cog.code(cog, mock_ctx, langage="python", description="hello")
        assert "Impossible" in str(mock_ctx.send.call_args) or "code" in str(mock_ctx.send.call_args)


class TestClearAICommand:
    """Tests for AI.clearai -- clearing conversation history."""

    @pytest.mark.asyncio
    async def test_clearai_clears_history(self, mock_bot, mock_ctx):
        from cogs.ai import AI
        cog = AI(mock_bot)

        # Add some history first
        cog.conversations.add_message(mock_ctx.author.id, mock_ctx.channel.id, "user", "hello")
        cog.conversations.add_message(mock_ctx.author.id, mock_ctx.channel.id, "assistant", "hi")

        await cog.clearai(cog, mock_ctx)

        history = cog.conversations.get_history(mock_ctx.author.id, mock_ctx.channel.id)
        assert len(history) == 0
        mock_ctx.send.assert_awaited()
        assert "effacé" in str(mock_ctx.send.call_args)


class TestAIChannelCommand:
    """Tests for AI.aichannel -- managing auto-response channels."""

    @pytest.mark.asyncio
    async def test_aichannel_add_default_channel(self, mock_bot, mock_ctx):
        from cogs.ai import AI
        cog = AI(mock_bot)

        await cog.aichannel(cog, mock_ctx, action="add", channel=None)
        assert mock_ctx.channel.id in cog.ai_channels
        mock_ctx.send.assert_awaited()

    @pytest.mark.asyncio
    async def test_aichannel_add_specific_channel(self, mock_bot, mock_ctx):
        from cogs.ai import AI
        cog = AI(mock_bot)

        ch = MagicMock()
        ch.id = 777777777
        ch.mention = "<#777777777>"

        await cog.aichannel(cog, mock_ctx, action="add", channel=ch)
        assert 777777777 in cog.ai_channels

    @pytest.mark.asyncio
    async def test_aichannel_remove(self, mock_bot, mock_ctx):
        from cogs.ai import AI
        cog = AI(mock_bot)
        cog.ai_channels.add(mock_ctx.channel.id)

        await cog.aichannel(cog, mock_ctx, action="remove", channel=None)
        assert mock_ctx.channel.id not in cog.ai_channels

    @pytest.mark.asyncio
    async def test_aichannel_invalid_action(self, mock_bot, mock_ctx):
        from cogs.ai import AI
        cog = AI(mock_bot)

        await cog.aichannel(cog, mock_ctx, action="invalid", channel=None)
        assert "add ou remove" in str(mock_ctx.send.call_args)

    @pytest.mark.asyncio
    async def test_aichannel_case_insensitive(self, mock_bot, mock_ctx):
        from cogs.ai import AI
        cog = AI(mock_bot)

        await cog.aichannel(cog, mock_ctx, action="ADD", channel=None)
        assert mock_ctx.channel.id in cog.ai_channels


class TestAIOnMessage:
    """Tests for AI.on_message -- auto-response listener."""

    def _make_message(self, mock_bot, author_bot=False, guild=True, channel_id=555,
                      content="hello bot", mentions=None):
        msg = MagicMock(spec=discord.Message)
        msg.author = MagicMock()
        msg.author.id = 123456789
        msg.author.bot = author_bot
        msg.author.display_name = "TestUser"
        msg.guild = MagicMock() if guild else None
        msg.channel = MagicMock()
        msg.channel.id = channel_id
        msg.channel.typing = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(), __aexit__=AsyncMock()
        ))
        msg.content = content
        msg.mentions = mentions or []
        msg.reply = AsyncMock()
        return msg

    @pytest.mark.asyncio
    async def test_ignores_bot_messages(self, mock_bot):
        from cogs.ai import AI
        cog = AI(mock_bot)
        msg = self._make_message(mock_bot, author_bot=True)
        await cog.on_message(msg)
        msg.reply.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ignores_dm_messages(self, mock_bot):
        from cogs.ai import AI
        cog = AI(mock_bot)
        msg = self._make_message(mock_bot, guild=False)
        await cog.on_message(msg)
        msg.reply.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ignores_non_ai_channel_no_mention(self, mock_bot):
        from cogs.ai import AI
        cog = AI(mock_bot)
        msg = self._make_message(mock_bot, channel_id=999)
        # Not in ai_channels and bot not mentioned
        await cog.on_message(msg)
        msg.reply.assert_not_awaited()

    @pytest.mark.asyncio
    @patch('cogs.ai.AI_ENABLED', False)
    async def test_ignores_when_ai_disabled(self, mock_bot):
        from cogs.ai import AI
        cog = AI(mock_bot)
        cog.ai_channels.add(555)
        msg = self._make_message(mock_bot, channel_id=555)
        await cog.on_message(msg)
        msg.reply.assert_not_awaited()

    @pytest.mark.asyncio
    @patch('cogs.ai.AI_ENABLED', True)
    async def test_ignores_empty_content_after_mention_strip(self, mock_bot):
        from cogs.ai import AI
        cog = AI(mock_bot)
        cog.ai_channels.add(555)
        # Content is just the mention, becomes empty after stripping
        msg = self._make_message(
            mock_bot, channel_id=555,
            content=f"<@{mock_bot.user.id}>"
        )
        await cog.on_message(msg)
        msg.reply.assert_not_awaited()

    @pytest.mark.asyncio
    @patch('cogs.ai.AI_ENABLED', True)
    @patch('cogs.ai.OPENAI_API_KEY', 'test-key')
    @patch('cogs.ai.aiohttp.ClientSession')
    async def test_responds_in_ai_channel(self, mock_aiohttp, mock_bot):
        from cogs.ai import AI
        cog = AI(mock_bot)
        cog.ai_channels.add(555)

        session_cm, _, _ = _make_aiohttp_session(
            status=200,
            json_data={"choices": [{"message": {"content": "bot reply"}}]}
        )
        mock_aiohttp.return_value = session_cm

        msg = self._make_message(mock_bot, channel_id=555, content="hello")
        await cog.on_message(msg)
        msg.reply.assert_awaited_once()
        assert "bot reply" in str(msg.reply.call_args)

    @pytest.mark.asyncio
    @patch('cogs.ai.AI_ENABLED', True)
    @patch('cogs.ai.OPENAI_API_KEY', 'test-key')
    @patch('cogs.ai.aiohttp.ClientSession')
    async def test_responds_when_mentioned(self, mock_aiohttp, mock_bot):
        from cogs.ai import AI
        cog = AI(mock_bot)

        session_cm, _, _ = _make_aiohttp_session(
            status=200,
            json_data={"choices": [{"message": {"content": "mention reply"}}]}
        )
        mock_aiohttp.return_value = session_cm

        msg = self._make_message(
            mock_bot, channel_id=999,
            content=f"<@{mock_bot.user.id}> what is Python?",
            mentions=[mock_bot.user]
        )
        await cog.on_message(msg)
        msg.reply.assert_awaited_once()

    @pytest.mark.asyncio
    @patch('cogs.ai.AI_ENABLED', True)
    @patch('cogs.ai.OPENAI_API_KEY', 'test-key')
    @patch('cogs.ai.aiohttp.ClientSession')
    async def test_truncates_long_on_message_response(self, mock_aiohttp, mock_bot):
        from cogs.ai import AI
        cog = AI(mock_bot)
        cog.ai_channels.add(555)

        long_text = "y" * 2000
        session_cm, _, _ = _make_aiohttp_session(
            status=200,
            json_data={"choices": [{"message": {"content": long_text}}]}
        )
        mock_aiohttp.return_value = session_cm

        msg = self._make_message(mock_bot, channel_id=555, content="tell me")
        await cog.on_message(msg)
        reply_text = msg.reply.call_args[0][0]
        assert len(reply_text) <= 1903

    @pytest.mark.asyncio
    @patch('cogs.ai.AI_ENABLED', True)
    @patch('cogs.ai.OPENAI_API_KEY', 'test-key')
    @patch('cogs.ai.aiohttp.ClientSession')
    async def test_no_reply_when_response_is_none(self, mock_aiohttp, mock_bot):
        from cogs.ai import AI
        cog = AI(mock_bot)
        cog.ai_channels.add(555)

        session_cm, _, _ = _make_aiohttp_session(status=500)
        mock_aiohttp.return_value = session_cm

        msg = self._make_message(mock_bot, channel_id=555, content="hello")
        await cog.on_message(msg)
        msg.reply.assert_not_awaited()


class TestAISetup:
    """Test the module-level setup function."""

    @pytest.mark.asyncio
    async def test_setup_adds_cog(self, mock_bot):
        from cogs.ai import setup
        mock_bot.add_cog = AsyncMock()
        await setup(mock_bot)
        mock_bot.add_cog.assert_awaited_once()


# ############################################################################
#
#                            GAMES COG TESTS
#
# ############################################################################

@pytest.fixture
def games_cog(mock_bot):
    from cogs.games import Games
    return Games(mock_bot)


class TestGamesCogInit:
    """Tests for Games cog initialization."""

    def test_games_init(self, mock_bot):
        from cogs.games import Games
        cog = Games(mock_bot)
        assert cog.bot is mock_bot
        assert isinstance(cog.trivia_sessions, dict)
        assert len(cog.trivia_sessions) == 0


class TestDailyCommand:
    """Tests for Games.daily -- daily reward claiming."""

    @pytest.mark.asyncio
    @patch('cogs.games.db')
    async def test_daily_already_claimed(self, mock_db, games_cog, mock_ctx):
        mock_db.get_or_create_user = AsyncMock(return_value={"coins": 100})
        mock_db.can_claim_daily = AsyncMock(return_value=False)

        await games_cog.daily(games_cog, mock_ctx)
        mock_ctx.send.assert_awaited()
        embed = mock_ctx.send.call_args.kwargs.get('embed')
        assert embed is not None

    @pytest.mark.asyncio
    @patch('cogs.games.db')
    async def test_daily_success(self, mock_db, games_cog, mock_ctx):
        mock_db.get_or_create_user = AsyncMock(return_value={"coins": 100})
        mock_db.can_claim_daily = AsyncMock(return_value=True)
        mock_db.claim_daily = AsyncMock()
        mock_db.get_user = AsyncMock(return_value={"coins": 200})

        await games_cog.daily(games_cog, mock_ctx)
        mock_db.claim_daily.assert_awaited_once()
        mock_ctx.send.assert_awaited()
        embed = mock_ctx.send.call_args.kwargs.get('embed')
        assert embed is not None


class TestBalanceCommand:
    """Tests for Games.balance."""

    @pytest.mark.asyncio
    @patch('cogs.games.db')
    async def test_balance_self(self, mock_db, games_cog, mock_ctx):
        mock_db.get_or_create_user = AsyncMock(return_value={"coins": 500})
        await games_cog.balance(games_cog, mock_ctx, membre=None)
        mock_db.get_or_create_user.assert_awaited_with(mock_ctx.author.id, mock_ctx.guild.id)
        mock_ctx.send.assert_awaited()

    @pytest.mark.asyncio
    @patch('cogs.games.db')
    async def test_balance_other_member(self, mock_db, games_cog, mock_ctx):
        other = MagicMock(spec=discord.Member)
        other.id = 111
        other.display_name = "Other"
        other.display_avatar = MagicMock()
        other.display_avatar.url = "https://cdn.discordapp.com/avatar.png"
        mock_db.get_or_create_user = AsyncMock(return_value={"coins": 1000})

        await games_cog.balance(games_cog, mock_ctx, membre=other)
        mock_db.get_or_create_user.assert_awaited_with(111, mock_ctx.guild.id)


class TestRichestCommand:
    """Tests for Games.richest -- paginated leaderboard."""

    @pytest.mark.asyncio
    @patch('cogs.games.db')
    async def test_richest_first_page(self, mock_db, games_cog, mock_ctx):
        users = [{"user_id": i, "coins": 1000 - i * 10} for i in range(15)]
        mock_db.get_economy_leaderboard = AsyncMock(return_value=users)

        await games_cog.richest(games_cog, mock_ctx, page=1)
        mock_ctx.send.assert_awaited()

    @pytest.mark.asyncio
    @patch('cogs.games.db')
    async def test_richest_second_page(self, mock_db, games_cog, mock_ctx):
        users = [{"user_id": i, "coins": 1000 - i * 10} for i in range(15)]
        mock_db.get_economy_leaderboard = AsyncMock(return_value=users)

        await games_cog.richest(games_cog, mock_ctx, page=2)
        mock_ctx.send.assert_awaited()

    @pytest.mark.asyncio
    @patch('cogs.games.db')
    async def test_richest_invalid_page(self, mock_db, games_cog, mock_ctx):
        mock_db.get_economy_leaderboard = AsyncMock(return_value=[])

        await games_cog.richest(games_cog, mock_ctx, page=5)
        assert "invalide" in str(mock_ctx.send.call_args) or "ERROR" in str(mock_ctx.send.call_args)

    @pytest.mark.asyncio
    @patch('cogs.games.db')
    async def test_richest_empty_leaderboard(self, mock_db, games_cog, mock_ctx):
        mock_db.get_economy_leaderboard = AsyncMock(return_value=[])

        await games_cog.richest(games_cog, mock_ctx, page=1)
        mock_ctx.send.assert_awaited()

    @pytest.mark.asyncio
    @patch('cogs.games.db')
    async def test_richest_page_zero_invalid(self, mock_db, games_cog, mock_ctx):
        mock_db.get_economy_leaderboard = AsyncMock(return_value=[{"user_id": 1, "coins": 100}])

        await games_cog.richest(games_cog, mock_ctx, page=0)
        assert "invalide" in str(mock_ctx.send.call_args)

    @pytest.mark.asyncio
    @patch('cogs.games.db')
    async def test_richest_with_known_member(self, mock_db, games_cog, mock_ctx):
        users = [{"user_id": 123, "coins": 1000}]
        mock_db.get_economy_leaderboard = AsyncMock(return_value=users)
        member_mock = MagicMock()
        member_mock.display_name = "KnownUser"
        mock_ctx.guild.get_member = MagicMock(return_value=member_mock)

        await games_cog.richest(games_cog, mock_ctx, page=1)
        mock_ctx.send.assert_awaited()


class TestGiveCommand:
    """Tests for Games.give -- coin transfers."""

    @pytest.mark.asyncio
    @patch('cogs.games.db')
    async def test_give_to_bot(self, mock_db, games_cog, mock_ctx):
        recipient = MagicMock(spec=discord.Member)
        recipient.bot = True
        await games_cog.give(games_cog, mock_ctx, membre=recipient, montant=100)
        assert "bot" in str(mock_ctx.send.call_args).lower()

    @pytest.mark.asyncio
    @patch('cogs.games.db')
    async def test_give_to_self(self, mock_db, games_cog, mock_ctx):
        await games_cog.give(games_cog, mock_ctx, membre=mock_ctx.author, montant=100)
        assert "vous-même" in str(mock_ctx.send.call_args) or "ERROR" in str(mock_ctx.send.call_args)

    @pytest.mark.asyncio
    @patch('cogs.games.db')
    async def test_give_negative_amount(self, mock_db, games_cog, mock_ctx):
        recipient = MagicMock(spec=discord.Member)
        recipient.bot = False
        await games_cog.give(games_cog, mock_ctx, membre=recipient, montant=-50)
        assert "positif" in str(mock_ctx.send.call_args)

    @pytest.mark.asyncio
    @patch('cogs.games.db')
    async def test_give_zero_amount(self, mock_db, games_cog, mock_ctx):
        recipient = MagicMock(spec=discord.Member)
        recipient.bot = False
        await games_cog.give(games_cog, mock_ctx, membre=recipient, montant=0)
        assert "positif" in str(mock_ctx.send.call_args)

    @pytest.mark.asyncio
    @patch('cogs.games.db')
    async def test_give_insufficient_balance(self, mock_db, games_cog, mock_ctx):
        recipient = MagicMock(spec=discord.Member)
        recipient.bot = False
        mock_db.get_or_create_user = AsyncMock(return_value={"coins": 50})

        await games_cog.give(games_cog, mock_ctx, membre=recipient, montant=100)
        assert "pas assez" in str(mock_ctx.send.call_args) or "ERROR" in str(mock_ctx.send.call_args)

    @pytest.mark.asyncio
    @patch('cogs.games.db')
    async def test_give_success(self, mock_db, games_cog, mock_ctx):
        recipient = MagicMock(spec=discord.Member)
        recipient.bot = False
        recipient.id = 999
        recipient.mention = "<@999>"
        mock_db.get_or_create_user = AsyncMock(return_value={"coins": 500})
        mock_db.add_coins = AsyncMock()

        await games_cog.give(games_cog, mock_ctx, membre=recipient, montant=100)
        # Verify both debit and credit
        assert mock_db.add_coins.await_count == 2
        embed = mock_ctx.send.call_args.kwargs.get('embed')
        assert embed is not None


class TestTriviaStatsCommand:
    """Tests for Games.triviastats."""

    @pytest.mark.asyncio
    @patch('cogs.games.db')
    async def test_triviastats_empty(self, mock_db, games_cog, mock_ctx):
        mock_db.get_trivia_leaderboard = AsyncMock(return_value=[])
        await games_cog.triviastats(games_cog, mock_ctx)
        mock_ctx.send.assert_awaited()
        embed = mock_ctx.send.call_args.kwargs.get('embed')
        assert embed is not None
        assert "Aucune" in embed.description

    @pytest.mark.asyncio
    @patch('cogs.games.db')
    async def test_triviastats_with_data(self, mock_db, games_cog, mock_ctx):
        data = [
            {"user_id": 123, "correct_answers": 10, "total_questions": 15},
            {"user_id": 456, "correct_answers": 5, "total_questions": 20},
        ]
        mock_db.get_trivia_leaderboard = AsyncMock(return_value=data)
        member_mock = MagicMock()
        member_mock.display_name = "Player"
        mock_ctx.guild.get_member = MagicMock(return_value=member_mock)

        await games_cog.triviastats(games_cog, mock_ctx)
        mock_ctx.send.assert_awaited()
        embed = mock_ctx.send.call_args.kwargs.get('embed')
        assert "Player" in embed.description

    @pytest.mark.asyncio
    @patch('cogs.games.db')
    async def test_triviastats_unknown_member(self, mock_db, games_cog, mock_ctx):
        data = [{"user_id": 999, "correct_answers": 3, "total_questions": 5}]
        mock_db.get_trivia_leaderboard = AsyncMock(return_value=data)
        mock_ctx.guild.get_member = MagicMock(return_value=None)

        await games_cog.triviastats(games_cog, mock_ctx)
        mock_ctx.send.assert_awaited()
        embed = mock_ctx.send.call_args.kwargs.get('embed')
        assert "Utilisateur" in embed.description

    @pytest.mark.asyncio
    @patch('cogs.games.db')
    async def test_triviastats_zero_total(self, mock_db, games_cog, mock_ctx):
        """Zero total_questions should not cause division by zero."""
        data = [{"user_id": 123, "correct_answers": 0, "total_questions": 0}]
        mock_db.get_trivia_leaderboard = AsyncMock(return_value=data)
        mock_ctx.guild.get_member = MagicMock(return_value=None)

        await games_cog.triviastats(games_cog, mock_ctx)
        mock_ctx.send.assert_awaited()


class TestRollCommand:
    """Tests for Games.roll -- dice rolling."""

    @pytest.mark.asyncio
    async def test_roll_default(self, games_cog, mock_ctx):
        await games_cog.roll(games_cog, mock_ctx, des="1d6")
        mock_ctx.send.assert_awaited()

    @pytest.mark.asyncio
    async def test_roll_multiple_dice(self, games_cog, mock_ctx):
        await games_cog.roll(games_cog, mock_ctx, des="3d20")
        mock_ctx.send.assert_awaited()

    @pytest.mark.asyncio
    async def test_roll_no_d_invalid(self, games_cog, mock_ctx):
        await games_cog.roll(games_cog, mock_ctx, des="20")
        assert "invalide" in str(mock_ctx.send.call_args).lower()

    @pytest.mark.asyncio
    async def test_roll_too_many_dice(self, games_cog, mock_ctx):
        await games_cog.roll(games_cog, mock_ctx, des="101d6")
        assert "invalide" in str(mock_ctx.send.call_args).lower()

    @pytest.mark.asyncio
    async def test_roll_too_many_sides(self, games_cog, mock_ctx):
        await games_cog.roll(games_cog, mock_ctx, des="1d1001")
        assert "invalide" in str(mock_ctx.send.call_args).lower()

    @pytest.mark.asyncio
    async def test_roll_too_few_sides(self, games_cog, mock_ctx):
        await games_cog.roll(games_cog, mock_ctx, des="1d1")
        assert "invalide" in str(mock_ctx.send.call_args).lower()

    @pytest.mark.asyncio
    async def test_roll_zero_dice(self, games_cog, mock_ctx):
        await games_cog.roll(games_cog, mock_ctx, des="0d6")
        assert "invalide" in str(mock_ctx.send.call_args).lower()

    @pytest.mark.asyncio
    async def test_roll_implicit_one_die(self, games_cog, mock_ctx):
        """'d20' should be parsed as 1d20."""
        await games_cog.roll(games_cog, mock_ctx, des="d20")
        mock_ctx.send.assert_awaited()
        # Should succeed, not show error
        sent = str(mock_ctx.send.call_args)
        assert "invalide" not in sent.lower()

    @pytest.mark.asyncio
    async def test_roll_non_numeric(self, games_cog, mock_ctx):
        await games_cog.roll(games_cog, mock_ctx, des="xdy")
        assert "invalide" in str(mock_ctx.send.call_args).lower()


class TestCoinflipCommand:
    """Tests for Games.coinflip."""

    @pytest.mark.asyncio
    async def test_coinflip_sends_embed(self, games_cog, mock_ctx):
        await games_cog.coinflip(games_cog, mock_ctx)
        mock_ctx.send.assert_awaited()
        call_kwargs = mock_ctx.send.call_args
        assert call_kwargs is not None


class TestEightBallCommand:
    """Tests for Games.eightball."""

    @pytest.mark.asyncio
    async def test_eightball_responds(self, games_cog, mock_ctx):
        await games_cog.eightball(games_cog, mock_ctx, question="Will I pass?")
        mock_ctx.send.assert_awaited()
        call_kwargs = mock_ctx.send.call_args
        assert call_kwargs is not None


class TestRPSCommand:
    """Tests for Games.rps -- Rock-Paper-Scissors."""

    @pytest.mark.asyncio
    async def test_rps_valid_french_pierre(self, games_cog, mock_ctx):
        await games_cog.rps(games_cog, mock_ctx, choix="pierre")
        mock_ctx.send.assert_awaited()

    @pytest.mark.asyncio
    async def test_rps_valid_french_feuille(self, games_cog, mock_ctx):
        await games_cog.rps(games_cog, mock_ctx, choix="feuille")
        mock_ctx.send.assert_awaited()

    @pytest.mark.asyncio
    async def test_rps_valid_french_ciseaux(self, games_cog, mock_ctx):
        await games_cog.rps(games_cog, mock_ctx, choix="ciseaux")
        mock_ctx.send.assert_awaited()

    @pytest.mark.asyncio
    async def test_rps_english_rock(self, games_cog, mock_ctx):
        await games_cog.rps(games_cog, mock_ctx, choix="rock")
        mock_ctx.send.assert_awaited()
        sent = str(mock_ctx.send.call_args)
        # Should not show error
        assert "Choisissez" not in sent

    @pytest.mark.asyncio
    async def test_rps_english_paper(self, games_cog, mock_ctx):
        await games_cog.rps(games_cog, mock_ctx, choix="paper")
        mock_ctx.send.assert_awaited()

    @pytest.mark.asyncio
    async def test_rps_english_scissors(self, games_cog, mock_ctx):
        await games_cog.rps(games_cog, mock_ctx, choix="scissors")
        mock_ctx.send.assert_awaited()

    @pytest.mark.asyncio
    async def test_rps_invalid_choice(self, games_cog, mock_ctx):
        await games_cog.rps(games_cog, mock_ctx, choix="banana")
        assert "Choisissez" in str(mock_ctx.send.call_args)

    @pytest.mark.asyncio
    async def test_rps_case_insensitive(self, games_cog, mock_ctx):
        await games_cog.rps(games_cog, mock_ctx, choix="PIERRE")
        mock_ctx.send.assert_awaited()
        sent = str(mock_ctx.send.call_args)
        assert "Choisissez" not in sent


class TestSlotCommand:
    """Tests for Games.slot -- slot machine."""

    @pytest.mark.asyncio
    async def test_slot_sends_embed(self, games_cog, mock_ctx):
        await games_cog.slot(games_cog, mock_ctx)
        mock_ctx.send.assert_awaited()
        call_kwargs = mock_ctx.send.call_args
        assert call_kwargs is not None

    @pytest.mark.asyncio
    async def test_slot_triple_match_jackpot(self, games_cog, mock_ctx):
        """Triple matching symbols should trigger JACKPOT."""
        with patch('cogs.games.random.choices', return_value=["A", "A", "A"]):
            await games_cog.slot(games_cog, mock_ctx)
            embed = mock_ctx.send.call_args.kwargs.get('embed')
            assert embed is not None
            # Check the result field for JACKPOT
            result_field = next(f for f in embed.fields if f.name == "Résultat")
            assert "JACKPOT" in result_field.value

    @pytest.mark.asyncio
    async def test_slot_two_adjacent_first_pair(self, games_cog, mock_ctx):
        """First two reels matching should give x2."""
        with patch('cogs.games.random.choices', return_value=["A", "A", "B"]):
            await games_cog.slot(games_cog, mock_ctx)
            embed = mock_ctx.send.call_args.kwargs.get('embed')
            result_field = next(f for f in embed.fields if f.name == "Résultat")
            assert "x2" in result_field.value

    @pytest.mark.asyncio
    async def test_slot_two_adjacent_second_pair(self, games_cog, mock_ctx):
        """Last two reels matching should give x2."""
        with patch('cogs.games.random.choices', return_value=["A", "B", "B"]):
            await games_cog.slot(games_cog, mock_ctx)
            embed = mock_ctx.send.call_args.kwargs.get('embed')
            result_field = next(f for f in embed.fields if f.name == "Résultat")
            assert "x2" in result_field.value

    @pytest.mark.asyncio
    async def test_slot_no_match(self, games_cog, mock_ctx):
        """No matching symbols should say 'Pas de chance'."""
        with patch('cogs.games.random.choices', return_value=["A", "B", "C"]):
            await games_cog.slot(games_cog, mock_ctx)
            embed = mock_ctx.send.call_args.kwargs.get('embed')
            result_field = next(f for f in embed.fields if f.name == "Résultat")
            assert "Pas de chance" in result_field.value

    @pytest.mark.asyncio
    async def test_slot_first_last_match_not_adjacent(self, games_cog, mock_ctx):
        """First and last matching but not middle should NOT be a win."""
        with patch('cogs.games.random.choices', return_value=["A", "B", "A"]):
            await games_cog.slot(games_cog, mock_ctx)
            embed = mock_ctx.send.call_args.kwargs.get('embed')
            result_field = next(f for f in embed.fields if f.name == "Résultat")
            assert "Pas de chance" in result_field.value

    @pytest.mark.asyncio
    async def test_slot_embed_has_description(self, games_cog, mock_ctx):
        """Slot embed should show the reels in description."""
        with patch('cogs.games.random.choices', return_value=["X", "Y", "Z"]):
            await games_cog.slot(games_cog, mock_ctx)
            embed = mock_ctx.send.call_args.kwargs.get('embed')
            assert "X" in embed.description
            assert "Y" in embed.description
            assert "Z" in embed.description

    @pytest.mark.asyncio
    async def test_slot_embed_title(self, games_cog, mock_ctx):
        """Slot embed should have the correct title."""
        await games_cog.slot(games_cog, mock_ctx)
        embed = mock_ctx.send.call_args.kwargs.get('embed')
        assert "Machine" in embed.title


class TestGamesSetup:
    """Test the module-level setup function for Games."""

    @pytest.mark.asyncio
    async def test_setup_adds_cog(self, mock_bot):
        from cogs.games import setup
        mock_bot.add_cog = AsyncMock()
        await setup(mock_bot)
        mock_bot.add_cog.assert_awaited_once()


# ############################################################################
#
#                           UTILITY COG TESTS
#
# ############################################################################

@pytest.fixture
def utility_cog(mock_bot):
    """Create a Utility cog with the background task mocked out."""
    with patch("cogs.utility.db"):
        from cogs.utility import Utility
        cog = Utility.__new__(Utility)
        cog.bot = mock_bot
        cog.reminder_check = MagicMock()
        cog.reminder_check.start = MagicMock()
        cog.reminder_check.cancel = MagicMock()
        return cog


class TestUtilityCogInit:
    """Tests for Utility cog initialization and unloading."""

    @pytest.mark.asyncio
    @patch('cogs.utility.db')
    async def test_init_starts_reminder_task(self, mock_db, mock_bot):
        from cogs.utility import Utility
        cog = Utility(mock_bot)
        assert cog.bot is mock_bot
        # The task should have been started (it creates an asyncio task in __init__)
        assert cog.reminder_check.is_running()

    def test_cog_unload_cancels_task(self, utility_cog):
        utility_cog.cog_unload()
        utility_cog.reminder_check.cancel.assert_called_once()


class TestReminderCheck:
    """Tests for Utility.reminder_check background task."""

    @pytest.mark.asyncio
    @patch('cogs.utility.db')
    async def test_reminder_check_sends_reminders(self, mock_db, mock_bot):
        from cogs.utility import Utility

        reminders = [
            {"id": 1, "channel_id": 555, "user_id": 123, "message": "Test reminder"}
        ]
        mock_db.get_due_reminders = AsyncMock(return_value=reminders)
        mock_db.delete_reminder = AsyncMock()

        mock_channel = MagicMock()
        mock_channel.send = AsyncMock()
        mock_bot.get_channel = MagicMock(return_value=mock_channel)

        mock_user = MagicMock()
        mock_user.mention = "<@123>"
        mock_bot.get_user = MagicMock(return_value=mock_user)

        cog = Utility(mock_bot)
        # Call the underlying coroutine directly via .coro attribute
        await cog.reminder_check.coro(cog)
        mock_channel.send.assert_awaited_once()
        mock_db.delete_reminder.assert_awaited_once_with(1)

    @pytest.mark.asyncio
    @patch('cogs.utility.db')
    async def test_reminder_check_no_channel(self, mock_db, mock_bot):
        from cogs.utility import Utility

        reminders = [
            {"id": 2, "channel_id": 999, "user_id": 123, "message": "Lost reminder"}
        ]
        mock_db.get_due_reminders = AsyncMock(return_value=reminders)
        mock_db.delete_reminder = AsyncMock()
        mock_bot.get_channel = MagicMock(return_value=None)

        cog = Utility(mock_bot)
        await cog.reminder_check.coro(cog)
        # Still deletes the reminder even when channel is missing
        mock_db.delete_reminder.assert_awaited_once_with(2)

    @pytest.mark.asyncio
    @patch('cogs.utility.db')
    async def test_reminder_check_no_user(self, mock_db, mock_bot):
        from cogs.utility import Utility

        reminders = [
            {"id": 3, "channel_id": 555, "user_id": 999, "message": "Orphan reminder"}
        ]
        mock_db.get_due_reminders = AsyncMock(return_value=reminders)
        mock_db.delete_reminder = AsyncMock()

        mock_channel = MagicMock()
        mock_channel.send = AsyncMock()
        mock_bot.get_channel = MagicMock(return_value=mock_channel)
        mock_bot.get_user = MagicMock(return_value=None)

        cog = Utility(mock_bot)
        await cog.reminder_check.coro(cog)
        # Should still delete the reminder
        mock_db.delete_reminder.assert_awaited_once_with(3)
        # But should NOT try to send (no user found)
        mock_channel.send.assert_not_awaited()

    @pytest.mark.asyncio
    @patch('cogs.utility.db')
    async def test_reminder_check_exception_handled(self, mock_db, mock_bot):
        from cogs.utility import Utility

        reminders = [
            {"id": 4, "channel_id": 555, "user_id": 123, "message": "Broken"}
        ]
        mock_db.get_due_reminders = AsyncMock(return_value=reminders)
        mock_db.delete_reminder = AsyncMock()

        mock_channel = MagicMock()
        mock_channel.send = AsyncMock(side_effect=Exception("send failed"))
        mock_bot.get_channel = MagicMock(return_value=mock_channel)
        mock_bot.get_user = MagicMock(return_value=MagicMock(mention="<@123>"))

        cog = Utility(mock_bot)
        # Should not raise
        await cog.reminder_check.coro(cog)
        mock_db.delete_reminder.assert_awaited_once_with(4)

    @pytest.mark.asyncio
    @patch('cogs.utility.db')
    async def test_reminder_check_empty(self, mock_db, mock_bot):
        from cogs.utility import Utility

        mock_db.get_due_reminders = AsyncMock(return_value=[])
        mock_db.delete_reminder = AsyncMock()

        cog = Utility(mock_bot)
        await cog.reminder_check.coro(cog)
        mock_db.delete_reminder.assert_not_awaited()


class TestPingCommand:
    """Tests for Utility.ping."""

    @pytest.mark.asyncio
    async def test_ping_sends_embed(self, utility_cog, mock_ctx):
        from cogs.utility import Utility
        mock_message = MagicMock()
        mock_message.edit = AsyncMock()
        mock_ctx.send = AsyncMock(return_value=mock_message)

        await Utility.ping(utility_cog, mock_ctx)
        mock_ctx.send.assert_awaited()
        mock_message.edit.assert_awaited()

    @pytest.mark.asyncio
    async def test_ping_latency_color(self, utility_cog, mock_ctx, mock_bot):
        from cogs.utility import Utility
        mock_bot.latency = 0.300  # 300ms -> should be WARNING color
        mock_message = MagicMock()
        mock_message.edit = AsyncMock()
        mock_ctx.send = AsyncMock(return_value=mock_message)

        await Utility.ping(utility_cog, mock_ctx)
        mock_message.edit.assert_awaited()


class TestServerInfoCommand:
    """Tests for Utility.serverinfo."""

    @pytest.mark.asyncio
    async def test_serverinfo_with_icon(self, utility_cog, mock_ctx):
        from cogs.utility import Utility
        await Utility.serverinfo(utility_cog, mock_ctx)
        mock_ctx.send.assert_awaited()

    @pytest.mark.asyncio
    async def test_serverinfo_without_icon(self, utility_cog, mock_ctx):
        from cogs.utility import Utility
        mock_ctx.guild.icon = None
        await Utility.serverinfo(utility_cog, mock_ctx)
        mock_ctx.send.assert_awaited()

    @pytest.mark.asyncio
    async def test_serverinfo_with_boosts(self, utility_cog, mock_ctx):
        from cogs.utility import Utility
        mock_ctx.guild.premium_subscription_count = 5
        mock_ctx.guild.premium_tier = 2
        await Utility.serverinfo(utility_cog, mock_ctx)
        mock_ctx.send.assert_awaited()


class TestUserInfoCommand:
    """Tests for Utility.userinfo."""

    @pytest.mark.asyncio
    async def test_userinfo_self(self, utility_cog, mock_ctx):
        from cogs.utility import Utility
        await Utility.userinfo(utility_cog, mock_ctx, membre=None)
        mock_ctx.send.assert_awaited()

    @pytest.mark.asyncio
    async def test_userinfo_other_member(self, utility_cog, mock_ctx):
        from cogs.utility import Utility
        other = MagicMock(spec=discord.Member)
        other.id = 777
        other.display_name = "OtherUser"
        other.display_avatar = MagicMock()
        other.display_avatar.url = "https://cdn.discordapp.com/other.png"
        other.nick = "Nick"
        other.bot = False
        other.color = discord.Color.blue()
        other.created_at = datetime(2018, 1, 1, 0, 0)
        other.joined_at = datetime(2020, 6, 1, 12, 0)
        other.premium_since = None
        role1 = MagicMock()
        role1.mention = "@everyone"
        role2 = MagicMock()
        role2.mention = "@Mod"
        other.roles = [role1, role2]
        other.__str__ = MagicMock(return_value="OtherUser#1234")

        await Utility.userinfo(utility_cog, mock_ctx, membre=other)
        mock_ctx.send.assert_awaited()

    @pytest.mark.asyncio
    async def test_userinfo_with_premium(self, utility_cog, mock_ctx):
        from cogs.utility import Utility
        mock_ctx.author.premium_since = datetime(2021, 5, 1)
        mock_ctx.author.__str__ = MagicMock(return_value="TestUser#0001")
        await Utility.userinfo(utility_cog, mock_ctx, membre=None)
        mock_ctx.send.assert_awaited()

    @pytest.mark.asyncio
    async def test_userinfo_many_roles(self, utility_cog, mock_ctx):
        from cogs.utility import Utility
        # Create 15 roles (1 @everyone + 14 others)
        roles = [MagicMock() for _ in range(15)]
        for i, r in enumerate(roles):
            r.mention = f"@Role{i}"
        mock_ctx.author.roles = roles
        mock_ctx.author.__str__ = MagicMock(return_value="TestUser#0001")
        await Utility.userinfo(utility_cog, mock_ctx, membre=None)
        mock_ctx.send.assert_awaited()

    @pytest.mark.asyncio
    async def test_userinfo_no_joined_at(self, utility_cog, mock_ctx):
        from cogs.utility import Utility
        mock_ctx.author.joined_at = None
        mock_ctx.author.__str__ = MagicMock(return_value="TestUser#0001")
        await Utility.userinfo(utility_cog, mock_ctx, membre=None)
        mock_ctx.send.assert_awaited()


class TestAvatarCommand:
    """Tests for Utility.avatar."""

    @pytest.mark.asyncio
    @patch('discord.ui.view.asyncio.get_running_loop', return_value=MagicMock())
    async def test_avatar_non_animated(self, mock_loop, utility_cog, mock_ctx):
        from cogs.utility import Utility
        mock_ctx.author.display_avatar.is_animated = MagicMock(return_value=False)
        await Utility.avatar(utility_cog, mock_ctx, membre=None)
        mock_ctx.send.assert_awaited()

    @pytest.mark.asyncio
    @patch('discord.ui.view.asyncio.get_running_loop', return_value=MagicMock())
    async def test_avatar_animated(self, mock_loop, utility_cog, mock_ctx):
        from cogs.utility import Utility
        mock_ctx.author.display_avatar.is_animated = MagicMock(return_value=True)
        await Utility.avatar(utility_cog, mock_ctx, membre=None)
        mock_ctx.send.assert_awaited()
        # The view should have 3 buttons (PNG, JPG, GIF)


class TestRemindCommand:
    """Tests for Utility.remind -- time parsing and reminder creation."""

    @pytest.mark.asyncio
    @patch('cogs.utility.db')
    async def test_remind_valid_minutes(self, mock_db, utility_cog, mock_ctx):
        from cogs.utility import Utility
        mock_db.add_reminder = AsyncMock()
        await Utility.remind(utility_cog, mock_ctx, temps="10m", message="test")
        mock_db.add_reminder.assert_awaited_once()
        mock_ctx.send.assert_awaited()

    @pytest.mark.asyncio
    @patch('cogs.utility.db')
    async def test_remind_valid_hours(self, mock_db, utility_cog, mock_ctx):
        from cogs.utility import Utility
        mock_db.add_reminder = AsyncMock()
        await Utility.remind(utility_cog, mock_ctx, temps="2h", message="test")
        mock_db.add_reminder.assert_awaited_once()

    @pytest.mark.asyncio
    @patch('cogs.utility.db')
    async def test_remind_valid_days(self, mock_db, utility_cog, mock_ctx):
        from cogs.utility import Utility
        mock_db.add_reminder = AsyncMock()
        await Utility.remind(utility_cog, mock_ctx, temps="1d", message="test")
        mock_db.add_reminder.assert_awaited_once()

    @pytest.mark.asyncio
    @patch('cogs.utility.db')
    async def test_remind_valid_seconds(self, mock_db, utility_cog, mock_ctx):
        from cogs.utility import Utility
        mock_db.add_reminder = AsyncMock()
        await Utility.remind(utility_cog, mock_ctx, temps="30s", message="test")
        mock_db.add_reminder.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_remind_invalid_unit(self, utility_cog, mock_ctx):
        from cogs.utility import Utility
        await Utility.remind(utility_cog, mock_ctx, temps="10x", message="test")
        assert "invalide" in str(mock_ctx.send.call_args).lower()

    @pytest.mark.asyncio
    async def test_remind_negative_amount(self, utility_cog, mock_ctx):
        from cogs.utility import Utility
        await Utility.remind(utility_cog, mock_ctx, temps="-5m", message="test")
        assert "invalide" in str(mock_ctx.send.call_args).lower()

    @pytest.mark.asyncio
    async def test_remind_zero_amount(self, utility_cog, mock_ctx):
        from cogs.utility import Utility
        await Utility.remind(utility_cog, mock_ctx, temps="0m", message="test")
        assert "invalide" in str(mock_ctx.send.call_args).lower()

    @pytest.mark.asyncio
    async def test_remind_exceeds_30_days(self, utility_cog, mock_ctx):
        from cogs.utility import Utility
        await Utility.remind(utility_cog, mock_ctx, temps="31d", message="test")
        assert "30 jours" in str(mock_ctx.send.call_args)

    @pytest.mark.asyncio
    async def test_remind_non_numeric(self, utility_cog, mock_ctx):
        from cogs.utility import Utility
        await Utility.remind(utility_cog, mock_ctx, temps="abcm", message="test")
        assert "invalide" in str(mock_ctx.send.call_args).lower()


class TestPollCommand:
    """Tests for Utility.poll -- simple yes/no poll."""

    @pytest.mark.asyncio
    async def test_poll_creates_embed(self, utility_cog, mock_ctx):
        from cogs.utility import Utility
        mock_message = MagicMock()
        mock_message.add_reaction = AsyncMock()
        mock_ctx.send = AsyncMock(return_value=mock_message)

        await Utility.poll(utility_cog, mock_ctx, question="Do you like tests?")
        mock_ctx.send.assert_awaited()
        assert mock_message.add_reaction.await_count == 2


class TestMultipollCommand:
    """Tests for Utility.multipoll -- multi-option poll."""

    @pytest.mark.asyncio
    async def test_multipoll_success(self, utility_cog, mock_ctx):
        from cogs.utility import Utility
        mock_message = MagicMock()
        mock_message.add_reaction = AsyncMock()
        mock_ctx.send = AsyncMock(return_value=mock_message)

        await Utility.multipoll(utility_cog, mock_ctx, question="Favorite?", options="A | B | C")
        mock_ctx.send.assert_awaited()
        assert mock_message.add_reaction.await_count == 3

    @pytest.mark.asyncio
    async def test_multipoll_too_few_options(self, utility_cog, mock_ctx):
        from cogs.utility import Utility
        await Utility.multipoll(utility_cog, mock_ctx, question="One?", options="Single")
        assert "2 options" in str(mock_ctx.send.call_args) or "ERROR" in str(mock_ctx.send.call_args)

    @pytest.mark.asyncio
    async def test_multipoll_too_many_options(self, utility_cog, mock_ctx):
        from cogs.utility import Utility
        options = " | ".join(f"Option{i}" for i in range(11))
        await Utility.multipoll(utility_cog, mock_ctx, question="Too many?", options=options)
        assert "10" in str(mock_ctx.send.call_args)


class TestMemeCommand:
    """Tests for Utility.meme -- Reddit meme fetching."""

    @pytest.mark.asyncio
    @patch('cogs.utility.aiohttp.ClientSession')
    async def test_meme_success(self, mock_aiohttp, utility_cog, mock_ctx):
        from cogs.utility import Utility
        post_data = {
            "data": {
                "children": [
                    {
                        "data": {
                            "over_18": False,
                            "url_overridden_by_dest": "https://i.redd.it/meme.jpg",
                            "title": "Funny meme",
                            "permalink": "/r/memes/comments/123/funny_meme/",
                            "ups": 1234,
                            "subreddit": "memes"
                        }
                    }
                ]
            }
        }

        session_cm, session, response = _make_aiohttp_session(status=200, json_data=post_data)
        mock_aiohttp.return_value = session_cm

        await Utility.meme(utility_cog, mock_ctx)
        mock_ctx.send.assert_awaited()

    @pytest.mark.asyncio
    @patch('cogs.utility.aiohttp.ClientSession')
    async def test_meme_api_error(self, mock_aiohttp, utility_cog, mock_ctx):
        from cogs.utility import Utility
        session_cm, _, _ = _make_aiohttp_session(status=500)
        mock_aiohttp.return_value = session_cm

        await Utility.meme(utility_cog, mock_ctx)
        assert "Impossible" in str(mock_ctx.send.call_args) or "ERROR" in str(mock_ctx.send.call_args)

    @pytest.mark.asyncio
    @patch('cogs.utility.aiohttp.ClientSession')
    async def test_meme_no_sfw_posts(self, mock_aiohttp, utility_cog, mock_ctx):
        from cogs.utility import Utility
        post_data = {
            "data": {
                "children": [
                    {
                        "data": {
                            "over_18": True,
                            "url_overridden_by_dest": "https://i.redd.it/nsfw.jpg",
                            "title": "NSFW"
                        }
                    }
                ]
            }
        }

        session_cm, _, _ = _make_aiohttp_session(status=200, json_data=post_data)
        mock_aiohttp.return_value = session_cm

        await Utility.meme(utility_cog, mock_ctx)
        assert "Aucun" in str(mock_ctx.send.call_args) or "ERROR" in str(mock_ctx.send.call_args)

    @pytest.mark.asyncio
    @patch('cogs.utility.aiohttp.ClientSession')
    async def test_meme_exception(self, mock_aiohttp, utility_cog, mock_ctx):
        from cogs.utility import Utility

        # The exception must occur inside the try block (during session.get),
        # not during ClientSession() construction. Build a session whose
        # get() raises inside the `async with session.get(...)` block.
        mock_session = MagicMock()
        mock_get_cm = AsyncMock()
        mock_get_cm.__aenter__ = AsyncMock(side_effect=Exception("network down"))
        mock_get_cm.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = MagicMock(return_value=mock_get_cm)

        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)
        mock_aiohttp.return_value = mock_session_cm

        await Utility.meme(utility_cog, mock_ctx)
        embed_or_str = mock_ctx.send.call_args
        assert embed_or_str is not None


class TestSayCommand:
    """Tests for Utility.say -- message echo."""

    @pytest.mark.asyncio
    async def test_say_sends_message(self, utility_cog, mock_ctx):
        from cogs.utility import Utility
        await Utility.say(utility_cog, mock_ctx, message="Hello world!")
        mock_ctx.send.assert_awaited_with("Hello world!")

    @pytest.mark.asyncio
    async def test_say_deletes_original(self, utility_cog, mock_ctx):
        from cogs.utility import Utility
        await Utility.say(utility_cog, mock_ctx, message="echo")
        mock_ctx.message.delete.assert_awaited()

    @pytest.mark.asyncio
    async def test_say_delete_forbidden(self, utility_cog, mock_ctx):
        from cogs.utility import Utility
        mock_ctx.message.delete = AsyncMock(side_effect=discord.Forbidden(MagicMock(), ""))
        await Utility.say(utility_cog, mock_ctx, message="echo")
        # Should not raise, message should still be sent
        mock_ctx.send.assert_awaited_with("echo")


class TestEmbedCommand:
    """Tests for Utility.embed_cmd -- custom embed creation."""

    @pytest.mark.asyncio
    async def test_embed_cmd_sends_embed(self, utility_cog, mock_ctx):
        from cogs.utility import Utility
        await Utility.embed_cmd(utility_cog, mock_ctx, titre="Title", description="Body text")
        mock_ctx.send.assert_awaited()
        call_kwargs = mock_ctx.send.call_args
        assert call_kwargs is not None


class TestAFKCommand:
    """Tests for Utility.afk -- setting AFK status."""

    @pytest.mark.asyncio
    async def test_afk_default_reason(self, utility_cog, mock_ctx, mock_bot):
        from cogs.utility import Utility
        await Utility.afk(utility_cog, mock_ctx, raison="AFK")
        assert mock_ctx.author.id in mock_bot.afk_users
        assert mock_bot.afk_users[mock_ctx.author.id]["reason"] == "AFK"

    @pytest.mark.asyncio
    async def test_afk_custom_reason(self, utility_cog, mock_ctx, mock_bot):
        from cogs.utility import Utility
        await Utility.afk(utility_cog, mock_ctx, raison="eating lunch")
        assert mock_bot.afk_users[mock_ctx.author.id]["reason"] == "eating lunch"

    @pytest.mark.asyncio
    async def test_afk_creates_dict_if_missing(self, utility_cog, mock_ctx, mock_bot):
        from cogs.utility import Utility
        # Remove afk_users if it exists
        if hasattr(mock_bot, 'afk_users'):
            delattr(mock_bot, 'afk_users')
        await Utility.afk(utility_cog, mock_ctx, raison="brb")
        assert hasattr(mock_bot, 'afk_users')
        assert mock_ctx.author.id in mock_bot.afk_users


class TestUtilityOnMessage:
    """Tests for Utility.on_message -- AFK system listener."""

    def _make_message(self, mock_bot, author_id=123456789, author_bot=False,
                      guild=True, mentions=None):
        msg = MagicMock(spec=discord.Message)
        msg.author = MagicMock()
        msg.author.id = author_id
        msg.author.bot = author_bot
        msg.author.mention = f"<@{author_id}>"
        msg.author.display_name = "TestUser"
        msg.guild = MagicMock() if guild else None
        msg.channel = MagicMock()
        msg.channel.send = AsyncMock()
        msg.mentions = mentions or []
        return msg

    @pytest.mark.asyncio
    async def test_ignores_bot_messages(self, utility_cog, mock_bot):
        from cogs.utility import Utility
        msg = self._make_message(mock_bot, author_bot=True)
        await Utility.on_message(utility_cog, msg)
        msg.channel.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ignores_dm_messages(self, utility_cog, mock_bot):
        from cogs.utility import Utility
        msg = self._make_message(mock_bot, guild=False)
        await Utility.on_message(utility_cog, msg)
        msg.channel.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_clears_afk_on_message(self, utility_cog, mock_bot):
        from cogs.utility import Utility
        mock_bot.afk_users = {123456789: {"reason": "brb", "time": datetime.now()}}
        msg = self._make_message(mock_bot, author_id=123456789)

        await Utility.on_message(utility_cog, msg)
        assert 123456789 not in mock_bot.afk_users
        msg.channel.send.assert_awaited()

    @pytest.mark.asyncio
    async def test_notifies_when_afk_user_mentioned(self, utility_cog, mock_bot):
        from cogs.utility import Utility
        afk_user = MagicMock()
        afk_user.id = 777
        afk_user.display_name = "AFKPerson"
        mock_bot.afk_users = {
            777: {"reason": "sleeping", "time": datetime.now() - timedelta(minutes=10)}
        }

        msg = self._make_message(mock_bot, author_id=999, mentions=[afk_user])
        await Utility.on_message(utility_cog, msg)
        # Should send a notification about the AFK user
        msg.channel.send.assert_awaited()
        assert "AFK" in str(msg.channel.send.call_args)

    @pytest.mark.asyncio
    async def test_creates_afk_dict_if_missing(self, utility_cog, mock_bot):
        from cogs.utility import Utility
        if hasattr(mock_bot, 'afk_users'):
            delattr(mock_bot, 'afk_users')
        msg = self._make_message(mock_bot)
        await Utility.on_message(utility_cog, msg)
        assert hasattr(mock_bot, 'afk_users')


class TestCalcCommand:
    """Tests for Utility.calc -- safe math evaluation."""

    @pytest.mark.asyncio
    async def test_calc_simple_addition(self, utility_cog, mock_ctx):
        from cogs.utility import Utility
        await Utility.calc(utility_cog, mock_ctx, expression="2+2")
        mock_ctx.send.assert_awaited()
        # Should not be an error
        assert "ERROR" not in str(mock_ctx.send.call_args)

    @pytest.mark.asyncio
    async def test_calc_complex_expression(self, utility_cog, mock_ctx):
        from cogs.utility import Utility
        await Utility.calc(utility_cog, mock_ctx, expression="(10+5)*2-3")
        mock_ctx.send.assert_awaited()

    @pytest.mark.asyncio
    async def test_calc_division_by_zero(self, utility_cog, mock_ctx):
        from cogs.utility import Utility
        await Utility.calc(utility_cog, mock_ctx, expression="10/0")
        sent = str(mock_ctx.send.call_args)
        assert "zéro" in sent.lower() or "error" in sent.lower()

    @pytest.mark.asyncio
    async def test_calc_invalid_expression(self, utility_cog, mock_ctx):
        from cogs.utility import Utility
        await Utility.calc(utility_cog, mock_ctx, expression='print("hack")')
        sent = str(mock_ctx.send.call_args)
        assert "ERROR" in sent or "Impossible" in sent or "autorisé" in sent

    @pytest.mark.asyncio
    async def test_calc_syntax_error(self, utility_cog, mock_ctx):
        from cogs.utility import Utility
        await Utility.calc(utility_cog, mock_ctx, expression="2++")
        mock_ctx.send.assert_awaited()

    @pytest.mark.asyncio
    async def test_calc_negative_numbers(self, utility_cog, mock_ctx):
        from cogs.utility import Utility
        await Utility.calc(utility_cog, mock_ctx, expression="-5+3")
        mock_ctx.send.assert_awaited()

    @pytest.mark.asyncio
    async def test_calc_power_operator_rejected(self, utility_cog, mock_ctx):
        from cogs.utility import Utility
        await Utility.calc(utility_cog, mock_ctx, expression="2**10")
        sent = str(mock_ctx.send.call_args)
        assert "ERROR" in sent or "autorisé" in sent


class TestSafeMathEval:
    """Additional tests for Utility._safe_math_eval to exercise more branches."""

    def test_multiplication(self):
        from cogs.utility import Utility
        assert Utility._safe_math_eval("3*4") == 12

    def test_division(self):
        from cogs.utility import Utility
        assert Utility._safe_math_eval("10/4") == 2.5

    def test_parentheses(self):
        from cogs.utility import Utility
        assert Utility._safe_math_eval("(2+3)*4") == 20

    def test_unary_minus(self):
        from cogs.utility import Utility
        assert Utility._safe_math_eval("-10") == -10

    def test_unary_plus(self):
        from cogs.utility import Utility
        assert Utility._safe_math_eval("+5") == 5

    def test_syntax_error_raises_value_error(self):
        from cogs.utility import Utility
        with pytest.raises(ValueError):
            Utility._safe_math_eval("2 +")

    def test_string_rejected(self):
        from cogs.utility import Utility
        with pytest.raises(ValueError):
            Utility._safe_math_eval('"hello"')

    def test_function_call_rejected(self):
        from cogs.utility import Utility
        with pytest.raises(ValueError):
            Utility._safe_math_eval("abs(-5)")

    def test_division_by_zero_explicit(self):
        from cogs.utility import Utility
        with pytest.raises(ZeroDivisionError):
            Utility._safe_math_eval("1/0")


class TestUtilitySetup:
    """Test the module-level setup function for Utility."""

    @pytest.mark.asyncio
    @patch('cogs.utility.db')
    async def test_setup_adds_cog(self, mock_db, mock_bot):
        from cogs.utility import setup
        mock_bot.add_cog = AsyncMock()
        await setup(mock_bot)
        mock_bot.add_cog.assert_awaited_once()
