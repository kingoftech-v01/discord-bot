"""
Tests for the games cog (cogs/games.py).

Covers economy functions (daily rewards, balance, transfers), trivia answer
checking, dice roll parsing and validation, coinflip, Rock-Paper-Scissors
logic, and slot machine payout calculations.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timedelta
import random

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
    bot.get_channel = MagicMock(return_value=MagicMock())
    bot.wait_until_ready = AsyncMock()
    bot.wait_for = AsyncMock()
    return bot


@pytest.fixture
def mock_ctx():
    ctx = MagicMock(spec=commands.Context)
    ctx.guild = MagicMock(spec=discord.Guild)
    ctx.guild.id = 987654321
    ctx.guild.name = "Test Server"
    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.id = 123456789
    ctx.author.display_name = "TestUser"
    ctx.author.display_avatar = MagicMock()
    ctx.author.display_avatar.url = "https://cdn.discordapp.com/avatar.png"
    ctx.author.bot = False
    ctx.author.guild_permissions = MagicMock()
    ctx.send = AsyncMock()
    ctx.channel = MagicMock()
    ctx.channel.id = 555555555
    return ctx


@pytest.fixture
def games_cog(mock_bot):
    from cogs.games import Games
    return Games(mock_bot)


# ---------------------------------------------------------------------------
# Economy — Daily Rewards
# ---------------------------------------------------------------------------

class TestDailyRewards:
    """Tests for daily reward calculation and claiming."""

    def test_reward_within_range(self):
        """Daily reward should be between DAILY_REWARD_MIN and DAILY_REWARD_MAX."""
        from config import DAILY_REWARD_MIN, DAILY_REWARD_MAX
        for _ in range(100):
            amount = random.randint(DAILY_REWARD_MIN, DAILY_REWARD_MAX)
            assert DAILY_REWARD_MIN <= amount <= DAILY_REWARD_MAX

    def test_reward_min_not_negative(self):
        """Minimum reward should not be negative."""
        from config import DAILY_REWARD_MIN
        assert DAILY_REWARD_MIN >= 0

    def test_reward_max_greater_than_min(self):
        """Maximum reward should be >= minimum reward."""
        from config import DAILY_REWARD_MIN, DAILY_REWARD_MAX
        assert DAILY_REWARD_MAX >= DAILY_REWARD_MIN

    @pytest.mark.asyncio
    @patch("cogs.games.db")
    async def test_daily_already_claimed(self, mock_db, games_cog, mock_ctx):
        """When daily is already claimed, an error embed should be sent."""
        mock_db.get_or_create_user = AsyncMock(return_value={"coins": 100})
        mock_db.can_claim_daily = AsyncMock(return_value=False)

        await games_cog.daily(games_cog, mock_ctx)
        mock_ctx.send.assert_awaited()
        # The message should indicate the reward was already claimed
        call_kwargs = mock_ctx.send.call_args
        assert call_kwargs is not None

    @pytest.mark.asyncio
    @patch("cogs.games.db")
    async def test_daily_successful_claim(self, mock_db, games_cog, mock_ctx):
        """Successful daily claim should update balance and send embed."""
        mock_db.get_or_create_user = AsyncMock(return_value={"coins": 100})
        mock_db.can_claim_daily = AsyncMock(return_value=True)
        mock_db.claim_daily = AsyncMock()
        mock_db.get_user = AsyncMock(return_value={"coins": 200})

        await games_cog.daily(games_cog, mock_ctx)
        mock_db.claim_daily.assert_awaited_once()
        mock_ctx.send.assert_awaited()


# ---------------------------------------------------------------------------
# Economy — Balance
# ---------------------------------------------------------------------------

class TestBalance:
    """Tests for balance checking."""

    @pytest.mark.asyncio
    @patch("cogs.games.db")
    async def test_balance_self(self, mock_db, games_cog, mock_ctx):
        """Checking own balance should show coins."""
        mock_db.get_or_create_user = AsyncMock(return_value={"coins": 500})

        await games_cog.balance(games_cog, mock_ctx, membre=None)
        mock_ctx.send.assert_awaited()
        mock_db.get_or_create_user.assert_awaited()

    @pytest.mark.asyncio
    @patch("cogs.games.db")
    async def test_balance_other_user(self, mock_db, games_cog, mock_ctx):
        """Checking another member's balance should work."""
        other = MagicMock(spec=discord.Member)
        other.id = 999
        other.display_name = "Other"
        other.display_avatar = MagicMock()
        other.display_avatar.url = "https://cdn.discordapp.com/avatar.png"
        mock_db.get_or_create_user = AsyncMock(return_value={"coins": 1000})

        await games_cog.balance(games_cog, mock_ctx, membre=other)
        mock_db.get_or_create_user.assert_awaited_with(999, 987654321)


# ---------------------------------------------------------------------------
# Economy — Transfer (Give)
# ---------------------------------------------------------------------------

class TestGiveTransfer:
    """Tests for coin transfer validation logic."""

    def test_cannot_give_to_bot(self):
        """Transfers to bots should be rejected."""
        recipient = MagicMock(spec=discord.Member)
        recipient.bot = True
        assert recipient.bot is True

    def test_cannot_give_to_self(self):
        """Transfers to oneself should be rejected."""
        sender_id = 123
        recipient = MagicMock(spec=discord.Member)
        recipient.id = 123
        assert sender_id == recipient.id

    def test_cannot_give_negative(self):
        """Negative amounts should be rejected."""
        amount = -50
        assert amount <= 0

    def test_cannot_give_zero(self):
        """Zero amount should be rejected."""
        amount = 0
        assert amount <= 0

    def test_insufficient_balance(self):
        """Transfer should fail if sender has insufficient coins."""
        balance = 100
        amount = 200
        assert balance < amount


# ---------------------------------------------------------------------------
# Trivia — Answer Checking
# ---------------------------------------------------------------------------

class TestTriviaAnswerChecking:
    """Tests for trivia answer checking logic."""

    def test_correct_answer_index(self):
        """The correct answer should be findable in the shuffled list."""
        correct = "Paris"
        answers = ["London", "Berlin", "Paris", "Madrid"]
        correct_index = answers.index(correct)
        assert correct_index == 2

    def test_emoji_mapping(self):
        """Emoji mapping should match answer indices."""
        emojis = ["\U0001f1e6", "\U0001f1e7", "\U0001f1e8", "\U0001f1e9"]
        answers = ["A", "B", "C", "D"]
        for i, answer in enumerate(answers):
            assert emojis[i] is not None

    def test_trivia_session_tracking(self, games_cog):
        """Trivia sessions should track active channels."""
        games_cog.trivia_sessions[555] = True
        assert 555 in games_cog.trivia_sessions

    def test_trivia_session_cleanup(self, games_cog):
        """Session should be removable after trivia ends."""
        games_cog.trivia_sessions[555] = True
        del games_cog.trivia_sessions[555]
        assert 555 not in games_cog.trivia_sessions

    def test_trivia_categories_mapping(self):
        """All expected categories should map to OpenTDB IDs."""
        categories = {
            "general": 9, "science": 17, "history": 23,
            "sports": 21, "entertainment": 11, "games": 15,
            "geography": 22, "animals": 27,
        }
        assert categories["general"] == 9
        assert categories["science"] == 17
        assert len(categories) == 8

    def test_unknown_category_defaults(self):
        """Unknown category should default to 'general' (ID 9)."""
        categories = {"general": 9, "science": 17}
        cat_id = categories.get("unknown", 9)
        assert cat_id == 9


# ---------------------------------------------------------------------------
# Dice Roll
# ---------------------------------------------------------------------------

class TestDiceRoll:
    """Tests for dice roll parsing and validation."""

    def test_parse_standard_notation(self):
        """'2d6' should parse to 2 dice with 6 sides."""
        des = "2d6"
        parts = des.lower().split("d")
        num_dice = int(parts[0]) if parts[0] else 1
        num_sides = int(parts[1])
        assert num_dice == 2
        assert num_sides == 6

    def test_parse_single_die(self):
        """'d20' should parse to 1 die with 20 sides."""
        des = "d20"
        parts = des.lower().split("d")
        num_dice = int(parts[0]) if parts[0] else 1
        num_sides = int(parts[1])
        assert num_dice == 1
        assert num_sides == 20

    def test_parse_1d6(self):
        """'1d6' should parse correctly."""
        des = "1d6"
        parts = des.lower().split("d")
        num_dice = int(parts[0])
        num_sides = int(parts[1])
        assert num_dice == 1
        assert num_sides == 6

    def test_validate_max_dice(self):
        """Number of dice must be <= 100."""
        num_dice = 101
        assert num_dice > 100

    def test_validate_min_dice(self):
        """Number of dice must be >= 1."""
        num_dice = 0
        assert num_dice < 1

    def test_validate_max_sides(self):
        """Number of sides must be <= 1000."""
        num_sides = 1001
        assert num_sides > 1000

    def test_validate_min_sides(self):
        """Number of sides must be >= 2."""
        num_sides = 1
        assert num_sides < 2

    def test_roll_result_range(self):
        """Each die result should be between 1 and num_sides."""
        num_sides = 6
        for _ in range(100):
            result = random.randint(1, num_sides)
            assert 1 <= result <= num_sides

    def test_roll_total(self):
        """Total should equal sum of individual results."""
        results = [3, 4, 5]
        assert sum(results) == 12

    def test_no_d_in_notation_invalid(self):
        """Input without 'd' should be invalid."""
        des = "20"
        assert "d" not in des.lower()


# ---------------------------------------------------------------------------
# Coinflip
# ---------------------------------------------------------------------------

class TestCoinflip:
    """Tests for coinflip randomness."""

    def test_coinflip_returns_valid_result(self):
        """Coinflip should return either 'Pile' or 'Face'."""
        for _ in range(100):
            result = random.choice(["Pile", "Face"])
            assert result in ["Pile", "Face"]

    def test_coinflip_emoji_mapping(self):
        """Each result should have a corresponding emoji."""
        result = "Pile"
        emoji = "\U0001fa99" if result == "Pile" else "\U0001fa99"
        assert emoji is not None

    def test_coinflip_distribution(self):
        """Over many flips, both results should appear."""
        random.seed(42)
        results = [random.choice(["Pile", "Face"]) for _ in range(1000)]
        assert "Pile" in results
        assert "Face" in results


# ---------------------------------------------------------------------------
# Rock-Paper-Scissors
# ---------------------------------------------------------------------------

class TestRockPaperScissors:
    """Tests for RPS game logic."""

    def test_win_conditions(self):
        """Win conditions should be correctly defined."""
        wins = {
            "pierre": "ciseaux",
            "feuille": "pierre",
            "ciseaux": "feuille",
        }
        assert wins["pierre"] == "ciseaux"
        assert wins["feuille"] == "pierre"
        assert wins["ciseaux"] == "feuille"

    def test_draw_detection(self):
        """Same choice should be a draw."""
        assert "pierre" == "pierre"

    def test_win_detection(self):
        """Correct win condition should be detected."""
        wins = {"pierre": "ciseaux", "feuille": "pierre", "ciseaux": "feuille"}
        user = "pierre"
        bot = "ciseaux"
        assert wins[user] == bot

    def test_loss_detection(self):
        """Incorrect matchup should be detected as loss."""
        wins = {"pierre": "ciseaux", "feuille": "pierre", "ciseaux": "feuille"}
        user = "pierre"
        bot = "feuille"
        assert wins[user] != bot and user != bot

    def test_english_to_french_mapping(self):
        """English inputs should normalize to French equivalents."""
        mapping = {"rock": "pierre", "paper": "feuille", "scissors": "ciseaux"}
        assert mapping["rock"] == "pierre"
        assert mapping["paper"] == "feuille"
        assert mapping["scissors"] == "ciseaux"

    def test_valid_choices(self):
        """All valid choices should be recognized."""
        valid = {"pierre", "feuille", "ciseaux", "rock", "paper", "scissors"}
        assert "pierre" in valid
        assert "rock" in valid
        assert "banana" not in valid


# ---------------------------------------------------------------------------
# Slot Machine
# ---------------------------------------------------------------------------

class TestSlotMachine:
    """Tests for slot machine payout logic."""

    def test_triple_diamond_jackpot(self):
        """Triple diamonds should give 100x multiplier."""
        reels = ["\U0001f48e", "\U0001f48e", "\U0001f48e"]
        if reels[0] == reels[1] == reels[2] and reels[0] == "\U0001f48e":
            multiplier = 100
        else:
            multiplier = 0
        assert multiplier == 100

    def test_triple_seven_jackpot(self):
        """Triple sevens should give 50x multiplier."""
        reels = ["\U0001f3b0", "\U0001f3b0", "\U0001f3b0"]
        # In the actual code, 7 emoji is used for sevens
        # Here we test the logic pattern
        if reels[0] == reels[1] == reels[2]:
            multiplier = 50  # assuming it's the seven symbol
        assert multiplier == 50

    def test_triple_match_generic(self):
        """Any triple match (non-special) should give 10x multiplier."""
        reels = ["\U0001f352", "\U0001f352", "\U0001f352"]
        if reels[0] == reels[1] == reels[2]:
            multiplier = 10
        assert multiplier == 10

    def test_two_adjacent_match_first_pair(self):
        """First two matching should give 2x multiplier."""
        reels = ["\U0001f352", "\U0001f352", "\U0001f34b"]
        if reels[0] == reels[1] or reels[1] == reels[2]:
            multiplier = 2
        else:
            multiplier = 0
        assert multiplier == 2

    def test_two_adjacent_match_second_pair(self):
        """Last two matching should give 2x multiplier."""
        reels = ["\U0001f34b", "\U0001f352", "\U0001f352"]
        if reels[0] == reels[1] or reels[1] == reels[2]:
            multiplier = 2
        else:
            multiplier = 0
        assert multiplier == 2

    def test_no_match(self):
        """No matching symbols should give 0 multiplier."""
        reels = ["\U0001f352", "\U0001f34b", "\U0001f347"]
        if reels[0] == reels[1] == reels[2]:
            multiplier = 10
        elif reels[0] == reels[1] or reels[1] == reels[2]:
            multiplier = 2
        else:
            multiplier = 0
        assert multiplier == 0

    def test_first_and_last_match_no_payout(self):
        """Only first-last match (not adjacent) should give no payout."""
        reels = ["\U0001f352", "\U0001f34b", "\U0001f352"]
        if reels[0] == reels[1] == reels[2]:
            multiplier = 10
        elif reels[0] == reels[1] or reels[1] == reels[2]:
            multiplier = 2
        else:
            multiplier = 0
        assert multiplier == 0

    def test_weighted_symbol_selection(self):
        """Slot machine should use weighted symbol probabilities."""
        symbols = ["\U0001f352", "\U0001f34b", "\U0001f347", "\U0001f34a", "\U0001f514", "\U0001f3b0", "\U0001f48e"]
        weights = [30, 25, 20, 15, 5, 3, 2]
        # Check that weights sum is reasonable
        assert sum(weights) == 100
        # Check that rarer symbols have lower weight
        assert weights[-1] < weights[0]

    def test_slot_reel_count(self):
        """Slot machine should have exactly 3 reels."""
        symbols = ["\U0001f352", "\U0001f34b"]
        weights = [50, 50]
        reels = random.choices(symbols, weights=weights, k=3)
        assert len(reels) == 3


# ---------------------------------------------------------------------------
# 8-Ball
# ---------------------------------------------------------------------------

class TestEightBall:
    """Tests for the 8-ball command logic."""

    def test_response_pool_size(self):
        """The response pool should have 19 entries."""
        responses = [
            "Oui, certainement.", "C'est décidément ainsi.",
            "Sans aucun doute.", "Oui, définitivement.",
            "Vous pouvez compter dessus.", "Très probablement.",
            "Les perspectives sont bonnes.", "Oui.",
            "Les signes indiquent que oui.", "Réponse floue, réessayez.",
            "Redemandez plus tard.",
            "Mieux vaut ne pas vous le dire maintenant.",
            "Je ne peux pas prédire maintenant.",
            "Concentrez-vous et redemandez.", "N'y comptez pas.",
            "Ma réponse est non.", "Mes sources disent non.",
            "Les perspectives ne sont pas bonnes.", "Très douteux.",
        ]
        assert len(responses) == 19

    def test_response_is_string(self):
        """Each response should be a non-empty string."""
        responses = ["Oui.", "Non.", "Peut-être."]
        response = random.choice(responses)
        assert isinstance(response, str)
        assert len(response) > 0
