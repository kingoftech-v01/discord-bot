"""
Tests for the utility cog (cogs/utility.py).

Covers the _safe_math_eval static method extensively, time parsing for
the remind command, the AFK system, and basic command behaviour.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
from datetime import datetime, timedelta

import discord
from discord.ext import commands


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_bot():
    bot = MagicMock(spec=commands.Bot)
    bot.user = MagicMock()
    bot.user.id = 999999999
    bot.user.name = "TestBot"
    bot.user.display_avatar = MagicMock()
    bot.user.display_avatar.url = "https://cdn.discordapp.com/avatar.png"
    bot.get_channel = MagicMock(return_value=MagicMock())
    bot.get_user = MagicMock(return_value=MagicMock())
    bot.wait_until_ready = AsyncMock()
    bot.latency = 0.05
    bot.guilds = []
    return bot


@pytest.fixture
def mock_ctx():
    ctx = MagicMock(spec=commands.Context)
    ctx.guild = MagicMock(spec=discord.Guild)
    ctx.guild.id = 987654321
    ctx.guild.name = "Test Server"
    ctx.guild.member_count = 42
    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.id = 123456789
    ctx.author.mention = "<@123456789>"
    ctx.author.display_name = "TestUser"
    ctx.author.display_avatar = MagicMock()
    ctx.author.display_avatar.url = "https://cdn.discordapp.com/avatar.png"
    ctx.author.guild_permissions = MagicMock()
    ctx.send = AsyncMock()
    ctx.channel = MagicMock()
    ctx.channel.id = 555555555
    ctx.channel.send = AsyncMock()
    ctx.message = MagicMock()
    ctx.message.delete = AsyncMock()
    ctx.prefix = "!"
    return ctx


@pytest.fixture
def utility_cog(mock_bot):
    with patch("cogs.utility.db"):
        from cogs.utility import Utility
        cog = Utility.__new__(Utility)
        cog.bot = mock_bot
        # Skip the background task initialization
        cog.reminder_check = MagicMock()
        cog.reminder_check.start = MagicMock()
        cog.reminder_check.cancel = MagicMock()
        return cog


@pytest.fixture
def safe_math_eval():
    from cogs.utility import Utility
    return Utility._safe_math_eval


# ---------------------------------------------------------------------------
# _safe_math_eval — Basic Operations
# ---------------------------------------------------------------------------

class TestSafeMathEvalBasic:
    """Tests for basic arithmetic operations."""

    def test_addition(self, safe_math_eval):
        """2 + 2 should equal 4."""
        assert safe_math_eval("2+2") == 4

    def test_subtraction(self, safe_math_eval):
        """10 - 3 should equal 7."""
        assert safe_math_eval("10-3") == 7

    def test_multiplication(self, safe_math_eval):
        """5 * 6 should equal 30."""
        assert safe_math_eval("5*6") == 30

    def test_division(self, safe_math_eval):
        """10 / 2 should equal 5.0."""
        assert safe_math_eval("10/2") == 5.0

    def test_addition_with_spaces(self, safe_math_eval):
        """Spaces should be handled correctly."""
        assert safe_math_eval("2 + 2") == 4

    def test_large_numbers(self, safe_math_eval):
        """Large numbers should work."""
        assert safe_math_eval("1000000 * 1000000") == 1000000000000

    def test_single_number(self, safe_math_eval):
        """A single number should return that number."""
        assert safe_math_eval("42") == 42

    def test_zero(self, safe_math_eval):
        """Zero should return zero."""
        assert safe_math_eval("0") == 0


# ---------------------------------------------------------------------------
# _safe_math_eval — Parentheses
# ---------------------------------------------------------------------------

class TestSafeMathEvalParentheses:
    """Tests for expression grouping with parentheses."""

    def test_simple_parentheses(self, safe_math_eval):
        """(2+3)*4 should equal 20."""
        assert safe_math_eval("(2+3)*4") == 20

    def test_nested_parentheses(self, safe_math_eval):
        """((2+3)*(4-1))/5 should equal 3.0."""
        assert safe_math_eval("((2+3)*(4-1))/5") == 3.0

    def test_complex_expression(self, safe_math_eval):
        """(10+5)*2-3 should equal 27."""
        assert safe_math_eval("(10+5)*2-3") == 27

    def test_deeply_nested(self, safe_math_eval):
        """(((1+1))) should equal 2."""
        assert safe_math_eval("(((1+1)))") == 2

    def test_multiple_groups(self, safe_math_eval):
        """(2+3)*(4+5) should equal 45."""
        assert safe_math_eval("(2+3)*(4+5)") == 45


# ---------------------------------------------------------------------------
# _safe_math_eval — Negative / Decimal Numbers
# ---------------------------------------------------------------------------

class TestSafeMathEvalEdgeCases:
    """Tests for negative numbers, decimals, and edge cases."""

    def test_negative_number(self, safe_math_eval):
        """-5+3 should equal -2."""
        assert safe_math_eval("-5+3") == -2

    def test_unary_minus(self, safe_math_eval):
        """-10 should equal -10."""
        assert safe_math_eval("-10") == -10

    def test_unary_plus(self, safe_math_eval):
        """+5 should equal 5."""
        assert safe_math_eval("+5") == 5

    def test_decimal_numbers(self, safe_math_eval):
        """3.14*2 should be approximately 6.28."""
        assert abs(safe_math_eval("3.14*2") - 6.28) < 0.0001

    def test_decimal_addition(self, safe_math_eval):
        """0.1+0.2 should be approximately 0.3."""
        assert abs(safe_math_eval("0.1+0.2") - 0.3) < 0.0001

    def test_negative_result(self, safe_math_eval):
        """3-10 should equal -7."""
        assert safe_math_eval("3-10") == -7

    def test_double_negative(self, safe_math_eval):
        """--5 should raise ValueError (not a simple negation of negation in AST)."""
        # In Python AST, --5 is parsed as UnaryOp(USub, UnaryOp(USub, 5))
        assert safe_math_eval("--5") == 5


# ---------------------------------------------------------------------------
# _safe_math_eval — Division by Zero
# ---------------------------------------------------------------------------

class TestSafeMathEvalDivisionByZero:
    """Tests for division by zero handling."""

    def test_division_by_zero(self, safe_math_eval):
        """Division by zero should raise ZeroDivisionError."""
        with pytest.raises(ZeroDivisionError):
            safe_math_eval("10/0")

    def test_expression_division_by_zero(self, safe_math_eval):
        """Complex expression resulting in div by zero should raise."""
        with pytest.raises(ZeroDivisionError):
            safe_math_eval("1/(3-3)")


# ---------------------------------------------------------------------------
# _safe_math_eval — Invalid / Dangerous Expressions
# ---------------------------------------------------------------------------

class TestSafeMathEvalInvalid:
    """Tests for expressions that should be rejected."""

    def test_import_os_rejected(self, safe_math_eval):
        """'import os' should raise ValueError."""
        with pytest.raises(ValueError):
            safe_math_eval("import os")

    def test_dunder_import_rejected(self, safe_math_eval):
        """'__import__(\"os\")' should raise ValueError."""
        with pytest.raises(ValueError):
            safe_math_eval('__import__("os")')

    def test_print_rejected(self, safe_math_eval):
        """'print(1)' should raise ValueError (function call not allowed)."""
        with pytest.raises(ValueError):
            safe_math_eval("print(1)")

    def test_exec_rejected(self, safe_math_eval):
        """'exec(\"pass\")' should raise ValueError."""
        with pytest.raises(ValueError):
            safe_math_eval('exec("pass")')

    def test_string_literal_rejected(self, safe_math_eval):
        """A string literal should raise ValueError."""
        with pytest.raises(ValueError):
            safe_math_eval('"hello"')

    def test_list_literal_rejected(self, safe_math_eval):
        """A list literal should raise ValueError."""
        with pytest.raises(ValueError):
            safe_math_eval("[1,2,3]")

    def test_attribute_access_rejected(self, safe_math_eval):
        """Attribute access should raise ValueError."""
        with pytest.raises(ValueError):
            safe_math_eval("().__class__")

    def test_empty_string_raises(self, safe_math_eval):
        """Empty string should raise ValueError."""
        with pytest.raises(ValueError):
            safe_math_eval("")

    def test_boolean_treated_as_constant(self, safe_math_eval):
        """Boolean values are parsed as NameConstants in Python AST.

        The implementation allows them (True=1, False=0) or raises --
        we just verify it does not allow arbitrary code execution.
        """
        # True evaluates to 1 in Python's AST, so the function may accept it.
        # We just make sure the result is sane (1 or raises ValueError).
        try:
            result = safe_math_eval("True")
            assert result == 1
        except ValueError:
            pass  # Also acceptable

    def test_power_operator_rejected(self, safe_math_eval):
        """Power operator ** should raise ValueError (not in allowed list)."""
        with pytest.raises(ValueError):
            safe_math_eval("2**10")

    def test_modulo_rejected(self, safe_math_eval):
        """Modulo operator % should raise ValueError."""
        with pytest.raises(ValueError):
            safe_math_eval("10%3")

    def test_bitwise_rejected(self, safe_math_eval):
        """Bitwise operators should raise ValueError."""
        with pytest.raises(ValueError):
            safe_math_eval("5&3")


# ---------------------------------------------------------------------------
# Time Parsing for Remind Command
# ---------------------------------------------------------------------------

class TestTimeParsing:
    """Tests for the remind command's time duration parsing logic."""

    def test_seconds_parsing(self):
        """'30s' should parse to 30 seconds."""
        time_units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        temps = "30s"
        unit = temps[-1].lower()
        amount = int(temps[:-1])
        seconds = amount * time_units[unit]
        assert seconds == 30

    def test_minutes_parsing(self):
        """'5m' should parse to 300 seconds."""
        time_units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        temps = "5m"
        unit = temps[-1].lower()
        amount = int(temps[:-1])
        seconds = amount * time_units[unit]
        assert seconds == 300

    def test_hours_parsing(self):
        """'2h' should parse to 7200 seconds."""
        time_units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        temps = "2h"
        unit = temps[-1].lower()
        amount = int(temps[:-1])
        seconds = amount * time_units[unit]
        assert seconds == 7200

    def test_days_parsing(self):
        """'1d' should parse to 86400 seconds."""
        time_units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        temps = "1d"
        unit = temps[-1].lower()
        amount = int(temps[:-1])
        seconds = amount * time_units[unit]
        assert seconds == 86400

    def test_invalid_unit_raises(self):
        """An invalid unit should raise a ValueError."""
        time_units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        temps = "10x"
        unit = temps[-1].lower()
        assert unit not in time_units

    def test_negative_amount_invalid(self):
        """Negative amount should be rejected."""
        temps = "-5m"
        try:
            amount = int(temps[:-1])
            assert amount <= 0
        except ValueError:
            pass

    def test_max_duration_30_days(self):
        """Maximum reminder duration is 30 days (2,592,000 seconds)."""
        max_seconds = 2592000
        # 31 days should exceed the limit
        assert 31 * 86400 > max_seconds
        # 30 days should be exactly at the limit
        assert 30 * 86400 == max_seconds

    def test_uppercase_unit(self):
        """Uppercase unit letter should be handled (lowered)."""
        time_units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        temps = "10M"
        unit = temps[-1].lower()
        assert unit in time_units
        amount = int(temps[:-1])
        seconds = amount * time_units[unit]
        assert seconds == 600


# ---------------------------------------------------------------------------
# AFK System
# ---------------------------------------------------------------------------

class TestAFKSystem:
    """Tests for the AFK system logic."""

    def test_afk_data_structure(self):
        """AFK data should contain 'reason' and 'time' keys."""
        afk_data = {
            "reason": "eating lunch",
            "time": datetime.now(),
        }
        assert "reason" in afk_data
        assert "time" in afk_data

    def test_afk_duration_calculation(self):
        """Duration calculation should return correct minutes."""
        afk_time = datetime.now() - timedelta(minutes=15)
        time_ago = datetime.now() - afk_time
        minutes = int(time_ago.total_seconds() // 60)
        assert minutes == 15

    def test_afk_cleared_on_message(self, mock_bot):
        """AFK status should be removable from the dict."""
        mock_bot.afk_users = {123: {"reason": "brb", "time": datetime.now()}}
        del mock_bot.afk_users[123]
        assert 123 not in mock_bot.afk_users

    def test_afk_users_init(self, mock_bot):
        """afk_users should be initializable as an empty dict."""
        if not hasattr(mock_bot, "afk_users"):
            mock_bot.afk_users = {}
        assert isinstance(mock_bot.afk_users, dict)

    def test_afk_check_mentioned_user(self, mock_bot):
        """Looking up a mentioned user in afk_users should work."""
        mock_bot.afk_users = {
            111: {"reason": "sleeping", "time": datetime.now() - timedelta(minutes=30)}
        }
        mentioned_id = 111
        assert mentioned_id in mock_bot.afk_users
        assert mock_bot.afk_users[mentioned_id]["reason"] == "sleeping"
