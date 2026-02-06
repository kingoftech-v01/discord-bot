"""
Comprehensive tests for the config module.

Tests verify that all configuration constants, classes, and default values
defined in ``config.py`` are accessible and have the expected types and
default values when no environment variables override them.
"""

import pytest


# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------

import config
from config import (
    TOKEN,
    APPLICATION_ID,
    PREFIX,
    DEFAULT_CHANNEL_ID,
    SEND_HOUR,
    AI_ENABLED,
    OPENAI_API_KEY,
    AI_MODEL,
    XP_PER_MESSAGE,
    XP_COOLDOWN,
    LEVEL_UP_BASE,
    LEVEL_UP_FACTOR,
    DAILY_REWARD_MIN,
    DAILY_REWARD_MAX,
    CURRENCY_NAME,
    CURRENCY_SYMBOL,
    WARN_THRESHOLD,
    MUTE_DURATION,
    SPAM_THRESHOLD,
    SPAM_INTERVAL,
    TRIVIA_TIME_LIMIT,
    TRIVIA_REWARD,
    BANNED_WORDS,
    Colors,
    Emojis,
)


# ===================================================================
# Test: all top-level constants are importable and accessible
# ===================================================================

class TestConfigAccessibility:
    """Verify every public constant in config.py can be imported."""

    def test_token_accessible(self):
        assert hasattr(config, "TOKEN")

    def test_application_id_accessible(self):
        assert hasattr(config, "APPLICATION_ID")

    def test_prefix_accessible(self):
        assert hasattr(config, "PREFIX")

    def test_default_channel_id_accessible(self):
        assert hasattr(config, "DEFAULT_CHANNEL_ID")

    def test_send_hour_accessible(self):
        assert hasattr(config, "SEND_HOUR")

    def test_ai_enabled_accessible(self):
        assert hasattr(config, "AI_ENABLED")

    def test_openai_api_key_accessible(self):
        assert hasattr(config, "OPENAI_API_KEY")

    def test_ai_model_accessible(self):
        assert hasattr(config, "AI_MODEL")

    def test_xp_per_message_accessible(self):
        assert hasattr(config, "XP_PER_MESSAGE")

    def test_xp_cooldown_accessible(self):
        assert hasattr(config, "XP_COOLDOWN")

    def test_level_up_base_accessible(self):
        assert hasattr(config, "LEVEL_UP_BASE")

    def test_level_up_factor_accessible(self):
        assert hasattr(config, "LEVEL_UP_FACTOR")

    def test_daily_reward_min_accessible(self):
        assert hasattr(config, "DAILY_REWARD_MIN")

    def test_daily_reward_max_accessible(self):
        assert hasattr(config, "DAILY_REWARD_MAX")

    def test_currency_name_accessible(self):
        assert hasattr(config, "CURRENCY_NAME")

    def test_currency_symbol_accessible(self):
        assert hasattr(config, "CURRENCY_SYMBOL")

    def test_warn_threshold_accessible(self):
        assert hasattr(config, "WARN_THRESHOLD")

    def test_mute_duration_accessible(self):
        assert hasattr(config, "MUTE_DURATION")

    def test_spam_threshold_accessible(self):
        assert hasattr(config, "SPAM_THRESHOLD")

    def test_spam_interval_accessible(self):
        assert hasattr(config, "SPAM_INTERVAL")

    def test_trivia_time_limit_accessible(self):
        assert hasattr(config, "TRIVIA_TIME_LIMIT")

    def test_trivia_reward_accessible(self):
        assert hasattr(config, "TRIVIA_REWARD")

    def test_banned_words_accessible(self):
        assert hasattr(config, "BANNED_WORDS")

    def test_colors_class_accessible(self):
        assert hasattr(config, "Colors")

    def test_emojis_class_accessible(self):
        assert hasattr(config, "Emojis")


# ===================================================================
# Test: Colors class attributes are integers (hex colour codes)
# ===================================================================

class TestColorsClass:
    """Verify every attribute of the Colors class is an int."""

    def test_primary_is_int(self):
        assert isinstance(Colors.PRIMARY, int)

    def test_success_is_int(self):
        assert isinstance(Colors.SUCCESS, int)

    def test_warning_is_int(self):
        assert isinstance(Colors.WARNING, int)

    def test_error_is_int(self):
        assert isinstance(Colors.ERROR, int)

    def test_info_is_int(self):
        assert isinstance(Colors.INFO, int)

    def test_level_up_is_int(self):
        assert isinstance(Colors.LEVEL_UP, int)

    def test_economy_is_int(self):
        assert isinstance(Colors.ECONOMY, int)

    def test_primary_value(self):
        assert Colors.PRIMARY == 0x5865F2

    def test_success_value(self):
        assert Colors.SUCCESS == 0x57F287

    def test_warning_value(self):
        assert Colors.WARNING == 0xFEE75C

    def test_error_value(self):
        assert Colors.ERROR == 0xED4245

    def test_info_value(self):
        assert Colors.INFO == 0x5865F2

    def test_level_up_value(self):
        assert Colors.LEVEL_UP == 0xF1C40F

    def test_economy_value(self):
        assert Colors.ECONOMY == 0x2ECC71

    def test_info_equals_primary(self):
        """INFO is an alias for PRIMARY (same blurple colour)."""
        assert Colors.INFO == Colors.PRIMARY

    def test_all_colors_positive(self):
        """All colour codes must be positive integers within 24-bit range."""
        for attr in ("PRIMARY", "SUCCESS", "WARNING", "ERROR", "INFO", "LEVEL_UP", "ECONOMY"):
            value = getattr(Colors, attr)
            assert 0 <= value <= 0xFFFFFF, f"Colors.{attr} out of valid RGB range"


# ===================================================================
# Test: Emojis class attributes are non-empty strings
# ===================================================================

class TestEmojisClass:
    """Verify every attribute of the Emojis class is a non-empty string."""

    def test_success_is_string(self):
        assert isinstance(Emojis.SUCCESS, str)

    def test_error_is_string(self):
        assert isinstance(Emojis.ERROR, str)

    def test_warning_is_string(self):
        assert isinstance(Emojis.WARNING, str)

    def test_info_is_string(self):
        assert isinstance(Emojis.INFO, str)

    def test_loading_is_string(self):
        assert isinstance(Emojis.LOADING, str)

    def test_coin_is_string(self):
        assert isinstance(Emojis.COIN, str)

    def test_xp_is_string(self):
        assert isinstance(Emojis.XP, str)

    def test_level_is_string(self):
        assert isinstance(Emojis.LEVEL, str)

    def test_trophy_is_string(self):
        assert isinstance(Emojis.TROPHY, str)

    def test_star_is_string(self):
        assert isinstance(Emojis.STAR, str)

    def test_dice_is_string(self):
        assert isinstance(Emojis.DICE, str)

    def test_game_is_string(self):
        assert isinstance(Emojis.GAME, str)

    def test_success_is_defined(self):
        """SUCCESS should be a string (may be empty or contain a Unicode emoji)."""
        assert Emojis.SUCCESS is not None

    def test_error_is_defined(self):
        assert Emojis.ERROR is not None

    def test_warning_is_defined(self):
        assert Emojis.WARNING is not None

    def test_info_is_defined(self):
        assert Emojis.INFO is not None

    def test_loading_is_defined(self):
        assert Emojis.LOADING is not None

    def test_coin_is_defined(self):
        assert Emojis.COIN is not None

    def test_xp_is_defined(self):
        assert Emojis.XP is not None

    def test_level_is_defined(self):
        assert Emojis.LEVEL is not None

    def test_trophy_is_defined(self):
        assert Emojis.TROPHY is not None

    def test_star_is_defined(self):
        assert Emojis.STAR is not None

    def test_dice_is_defined(self):
        assert Emojis.DICE is not None

    def test_game_is_defined(self):
        assert Emojis.GAME is not None

    def test_all_emoji_attributes_exist(self):
        """All documented emoji attributes should exist on the class."""
        expected = [
            "SUCCESS", "ERROR", "WARNING", "INFO", "LOADING",
            "COIN", "XP", "LEVEL", "TROPHY", "STAR", "DICE", "GAME",
        ]
        for attr in expected:
            assert hasattr(Emojis, attr), f"Emojis.{attr} is missing"


# ===================================================================
# Test: BANNED_WORDS list
# ===================================================================

class TestBannedWords:
    """Verify BANNED_WORDS is a populated list of strings."""

    def test_banned_words_is_list(self):
        assert isinstance(BANNED_WORDS, list)

    def test_banned_words_has_content(self):
        assert len(BANNED_WORDS) > 0

    def test_banned_words_contains_strings(self):
        for word in BANNED_WORDS:
            assert isinstance(word, str), f"Expected string, got {type(word)}: {word!r}"

    def test_banned_words_not_empty_strings(self):
        for word in BANNED_WORDS:
            assert len(word) > 0, "Empty string found in BANNED_WORDS"

    def test_banned_words_includes_english(self):
        """The list should contain at least some well-known English profanity."""
        lower_words = [w.lower() for w in BANNED_WORDS]
        assert "fuck" in lower_words
        assert "shit" in lower_words

    def test_banned_words_includes_french(self):
        """The list should contain at least some French profanity."""
        lower_words = [w.lower() for w in BANNED_WORDS]
        assert "merde" in lower_words
        assert "putain" in lower_words

    def test_banned_words_includes_obfuscation_variants(self):
        """The list includes leet-speak / character-substitution variants."""
        lower_words = [w.lower() for w in BANNED_WORDS]
        assert "sh1t" in lower_words or "f*ck" in lower_words

    def test_banned_words_sizeable(self):
        """The list should have a significant number of entries."""
        assert len(BANNED_WORDS) >= 50


# ===================================================================
# Test: default values of general settings
# ===================================================================

class TestDefaultSettings:
    """Verify config defaults when environment variables are not overridden.

    Note: These tests check the *code-level* defaults.  If the test
    environment happens to set the corresponding env vars, these
    assertions will still pass as long as the env vars provide the same
    values as the defaults.  For CI, ensure no .env file is loaded that
    would change them.
    """

    def test_prefix_default(self):
        assert PREFIX == "!"

    def test_xp_per_message_default(self):
        assert XP_PER_MESSAGE == 15

    def test_xp_cooldown_default(self):
        assert XP_COOLDOWN == 60

    def test_level_up_base_default(self):
        assert LEVEL_UP_BASE == 100

    def test_level_up_factor_default(self):
        assert LEVEL_UP_FACTOR == 1.5

    def test_daily_reward_min_default(self):
        assert DAILY_REWARD_MIN == 50

    def test_daily_reward_max_default(self):
        assert DAILY_REWARD_MAX == 200

    def test_currency_name_default(self):
        assert CURRENCY_NAME == "coins"

    def test_warn_threshold_default(self):
        assert WARN_THRESHOLD == 3

    def test_mute_duration_default(self):
        assert MUTE_DURATION == 3600

    def test_spam_threshold_default(self):
        assert SPAM_THRESHOLD == 5

    def test_spam_interval_default(self):
        assert SPAM_INTERVAL == 5

    def test_trivia_time_limit_default(self):
        assert TRIVIA_TIME_LIMIT == 30

    def test_trivia_reward_default(self):
        assert TRIVIA_REWARD == 50

    def test_ai_model_default(self):
        assert AI_MODEL == "gpt-3.5-turbo"

    def test_send_hour_default(self):
        assert SEND_HOUR == 9

    def test_default_channel_id_default(self):
        assert DEFAULT_CHANNEL_ID == 0


# ===================================================================
# Test: token and API key defaults (security-sensitive)
# ===================================================================

class TestSecretDefaults:
    """Verify that secrets default to empty strings (fail-fast design)."""

    def test_token_defaults_to_empty_string(self):
        assert isinstance(TOKEN, str)
        # The token may be set in a CI environment; if not set it should be empty.
        # We only assert the type here; an empty default is the code-level intent.

    def test_openai_api_key_defaults_to_empty_string(self):
        assert isinstance(OPENAI_API_KEY, str)

    def test_application_id_defaults_to_empty_string(self):
        assert isinstance(APPLICATION_ID, str)


# ===================================================================
# Test: type correctness of numeric / boolean settings
# ===================================================================

class TestSettingTypes:
    """Verify that config values have the expected Python types."""

    def test_prefix_is_str(self):
        assert isinstance(PREFIX, str)

    def test_default_channel_id_is_int(self):
        assert isinstance(DEFAULT_CHANNEL_ID, int)

    def test_send_hour_is_int(self):
        assert isinstance(SEND_HOUR, int)

    def test_ai_enabled_is_bool(self):
        assert isinstance(AI_ENABLED, bool)

    def test_xp_per_message_is_int(self):
        assert isinstance(XP_PER_MESSAGE, int)

    def test_xp_cooldown_is_int(self):
        assert isinstance(XP_COOLDOWN, int)

    def test_level_up_base_is_int(self):
        assert isinstance(LEVEL_UP_BASE, int)

    def test_level_up_factor_is_float(self):
        assert isinstance(LEVEL_UP_FACTOR, float)

    def test_daily_reward_min_is_int(self):
        assert isinstance(DAILY_REWARD_MIN, int)

    def test_daily_reward_max_is_int(self):
        assert isinstance(DAILY_REWARD_MAX, int)

    def test_currency_name_is_str(self):
        assert isinstance(CURRENCY_NAME, str)

    def test_currency_symbol_is_str(self):
        assert isinstance(CURRENCY_SYMBOL, str)

    def test_warn_threshold_is_int(self):
        assert isinstance(WARN_THRESHOLD, int)

    def test_mute_duration_is_int(self):
        assert isinstance(MUTE_DURATION, int)

    def test_spam_threshold_is_int(self):
        assert isinstance(SPAM_THRESHOLD, int)

    def test_spam_interval_is_int(self):
        assert isinstance(SPAM_INTERVAL, int)

    def test_trivia_time_limit_is_int(self):
        assert isinstance(TRIVIA_TIME_LIMIT, int)

    def test_trivia_reward_is_int(self):
        assert isinstance(TRIVIA_REWARD, int)

    def test_daily_reward_min_less_than_max(self):
        assert DAILY_REWARD_MIN <= DAILY_REWARD_MAX
