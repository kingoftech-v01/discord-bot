"""
Centralised configuration for the Discord bot.

This module is the **single source of truth** for every tuneable setting in
the bot.  Values are loaded from environment variables (via a ``.env`` file)
at import time, with sensible defaults provided where appropriate.

How it works:
    1. ``python-dotenv`` reads a ``.env`` file in the project root (if one
       exists) and injects its key-value pairs into ``os.environ``.
    2. Each configuration constant calls ``os.getenv(KEY, default)`` to
       retrieve the value, converting it to the correct Python type.
    3. The module also exposes two small helper classes (``Colors`` and
       ``Emojis``) that centralise embed colour codes and Unicode emoji
       characters used throughout the bot's user-facing messages.
    4. A ``BANNED_WORDS`` list provides the seed data for the profanity
       filter cog.  It contains common slurs and insults in both English
       and French, as well as common obfuscation variants.

Usage in other modules::

    from config import TOKEN, PREFIX, Colors, Emojis, BANNED_WORDS

Security notes:
    * ``DISCORD_TOKEN`` and ``OPENAI_API_KEY`` have **empty-string**
      defaults.  The bot will fail to connect at runtime if these are not
      set -- this is intentional (fail-fast) to avoid accidentally running
      in an unconfigured state.
    * **Never commit your ``.env`` file** to version control.  The
      repository ships a ``.env.example`` template instead.

Sections:
    - Tokens & IDs
    - General settings
    - AI / OpenAI integration
    - XP / Leveling system
    - Economy system
    - Moderation thresholds
    - Banned-words list
    - Trivia game settings
    - Colors (embed hex codes)
    - Emojis (Unicode constants)
"""

import os
from dotenv import load_dotenv

# Read .env file from the project root and populate ``os.environ``.
# Existing environment variables are NOT overridden, so container-level
# or CI/CD-level env vars always take precedence.
load_dotenv()

# === TOKENS & IDs ===
# SECURITY: No fallback values for secrets.  The bot will fail fast at startup
# if DISCORD_TOKEN is not set via environment variable or .env file.
TOKEN = os.getenv("DISCORD_TOKEN", "")           # Discord bot token (required)
APPLICATION_ID = os.getenv("APPLICATION_ID", "")  # Discord application / client ID

# === GENERAL SETTINGS ===
PREFIX = os.getenv("BOT_PREFIX", "!")                   # Default command prefix
DEFAULT_CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))  # Fallback channel for scheduled messages
SEND_HOUR = int(os.getenv("SEND_HOUR", "9"))            # Hour (0-23, UTC) for daily scheduled sends

# === AI / OPENAI INTEGRATION ===
# Toggle the AI chatbot feature on or off without removing the cog.
AI_ENABLED = os.getenv("AI_ENABLED", "true").lower() == "true"
# SECURITY: No fallback value for API keys.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")       # OpenAI API key (required if AI_ENABLED)
AI_MODEL = os.getenv("AI_MODEL", "gpt-3.5-turbo")      # OpenAI model identifier

# === XP / LEVELING SYSTEM ===
XP_PER_MESSAGE = int(os.getenv("XP_PER_MESSAGE", "15"))      # XP awarded per qualifying message
XP_COOLDOWN = int(os.getenv("XP_COOLDOWN", "60"))             # Seconds between XP grants per user
LEVEL_UP_BASE = int(os.getenv("LEVEL_UP_BASE", "100"))        # XP required for level 1
LEVEL_UP_FACTOR = float(os.getenv("LEVEL_UP_FACTOR", "1.5"))  # Multiplier applied each level (geometric)

# === ECONOMY SYSTEM ===
DAILY_REWARD_MIN = int(os.getenv("DAILY_REWARD_MIN", "50"))    # Minimum daily reward amount
DAILY_REWARD_MAX = int(os.getenv("DAILY_REWARD_MAX", "200"))   # Maximum daily reward amount
CURRENCY_NAME = os.getenv("CURRENCY_NAME", "coins")            # Display name for the currency
CURRENCY_SYMBOL = os.getenv("CURRENCY_SYMBOL", "")            # Emoji shown next to currency amounts

# === MODERATION THRESHOLDS ===
WARN_THRESHOLD = int(os.getenv("WARN_THRESHOLD", "3"))    # Warnings before auto-mute
MUTE_DURATION = int(os.getenv("MUTE_DURATION", "3600"))   # Auto-mute duration in seconds (default: 1 hour)
SPAM_THRESHOLD = int(os.getenv("SPAM_THRESHOLD", "5"))    # Max messages within SPAM_INTERVAL before anti-spam triggers
SPAM_INTERVAL = int(os.getenv("SPAM_INTERVAL", "5"))      # Rolling window in seconds for spam detection

# === BANNED WORDS (FR + EN) ===
# Extended list of banned words in both French and English.
# Used by the profanity filter cog (``cogs.profanity_filter``) to detect and
# remove messages containing hate speech, slurs, and insults.
# The list also includes common "leet-speak" / character-substitution variants
# (e.g. "sh1t", "f@ggot") to make circumvention harder.
# NOTE: Maintaining this list in code is simple but inflexible.  For
# server-specific overrides, see the database-backed per-guild word list in
# the profanity filter cog.
BANNED_WORDS = [
    # English - Common insults and slurs
    "fuck", "fucking", "fucker", "fucked", "fck", "f*ck", "f**k",
    "shit", "bullshit", "shitty", "sh*t", "sh1t",
    "bitch", "b*tch", "b1tch",
    "asshole", "a**hole", "assh0le",
    "bastard", "b@stard",
    "dick", "d*ck", "d1ck",
    "cock", "c*ck", "c0ck",
    "pussy", "p*ssy",
    "slut", "sl*t", "whore", "wh*re",
    "retard", "r3tard", "retarded",
    "faggot", "f@ggot", "fag",
    "nigger", "n*gger", "n1gger", "nigga",
    "cunt", "c*nt",
    "damn", "dammit", "goddamn",
    "idiot", "stupid", "dumb", "moron", "imbecile",
    "loser", "sucker", "jerk", "douchebag",
    "kill yourself", "kys", "go die",

    # French - Common insults and slurs
    "merde", "m*rde", "mrd",
    "putain", "put1", "put@in", "ptn",
    "salope", "sal0pe", "s@lope",
    "connard", "conn@rd", "conard",
    "connasse", "conn@sse",
    "enculé", "encule", "nculé", "enc*lé",
    "nique", "niquer", "niqué", "ntm", "nique ta mère", "nique ta mere",
    "fdp", "fils de pute", "fils de p*te",
    "pd", "pédé", "pede", "pédale",
    "tapette", "tapet",
    "batard", "bâtard", "b@tard",
    "con", "c0n",
    "conne", "c0nne",
    "bite", "b1te",
    "couilles", "couille",
    "chier", "fait chier", "fais chier",
    "gueule", "ta gueule", "ferme ta gueule", "tg",
    "crétin", "cretin", "crét1n",
    "abruti", "abrut1",
    "débile", "debile", "déb1le",
    "imbécile", "imbecile",
    "ordure", "0rdure",
    "pouffiasse", "poufiasse",
    "pétasse", "petasse",
    "salaud", "sal@ud",
    "enfoiré", "enfoire", "enf0iré",
    "bouffon", "bouf0n",
    "gogol", "gog0l",
    "attardé", "attarde",
    "mongol", "mong0l",
    "trisomique",
    "nègre", "negre",
    "bougnoule", "bougn0ule",
    "arabe de merde",
    "sale arabe", "sale noir", "sale blanc",
    "racaille",
    "casse toi", "casse-toi", "vas te faire",
    "va te faire foutre", "vtff",
    "je te baise", "je te nique",

    # Spaced-out character variants (bypass attempts)
    "f u c k", "s h i t", "b i t c h",
    "n i g g e r", "f a g g o t",

    # Hate-related terms
    "nazi", "n@zi", "hitler",
    "terroriste", "terr0riste",
]

# === TRIVIA GAME SETTINGS ===
TRIVIA_TIME_LIMIT = int(os.getenv("TRIVIA_TIME_LIMIT", "30"))  # Seconds to answer a trivia question
TRIVIA_REWARD = int(os.getenv("TRIVIA_REWARD", "50"))          # Currency reward for a correct answer

# === EMBED COLOURS ===
class Colors:
    """Centralised colour constants for Discord embed messages.

    Each attribute is an integer representing an RGB hex colour code.
    Using a single class for all colours ensures visual consistency across
    every embed the bot sends, and makes it trivial to re-brand the bot by
    changing values in one place.

    Attributes:
        PRIMARY (int): Discord Blurple -- used for general informational embeds.
        SUCCESS (int): Green -- used for confirmations and successful operations.
        WARNING (int): Yellow -- used for non-critical warnings (cooldowns,
            missing arguments).
        ERROR (int): Red -- used for permission errors and failures.
        INFO (int): Blue -- alias of PRIMARY; kept for semantic clarity.
        LEVEL_UP (int): Gold -- used when a member levels up.
        ECONOMY (int): Emerald -- used for economy-related embeds (balance,
            daily rewards, shop).
    """

    PRIMARY = 0x5865F2  # Discord Blurple
    SUCCESS = 0x57F287  # Green
    WARNING = 0xFEE75C  # Yellow
    ERROR = 0xED4245   # Red
    INFO = 0x5865F2    # Blue
    LEVEL_UP = 0xF1C40F # Gold
    ECONOMY = 0x2ECC71  # Emerald

# === EMOJIS ===
class Emojis:
    """Unicode emoji constants used in bot messages and embeds.

    Storing emojis as named constants avoids scattering raw Unicode
    characters throughout the codebase, makes intent explicit, and allows
    a quick visual audit of every emoji the bot may send.

    Attributes:
        SUCCESS (str): Green check mark -- operation succeeded.
        ERROR (str): Red cross mark -- operation failed.
        WARNING (str): Warning triangle -- non-critical alert.
        INFO (str): Information symbol -- informational notice.
        LOADING (str): Hourglass -- long-running operation in progress.
        COIN (str): Coin emoji -- displayed next to currency amounts.
        XP (str): Sparkles -- displayed next to XP values.
        LEVEL (str): Up arrow -- displayed when a user levels up.
        TROPHY (str): Trophy -- displayed for leaderboards and achievements.
        STAR (str): Star -- general highlight / decoration.
        DICE (str): Game die -- used in game-related messages.
        GAME (str): Video game controller -- used in game-related messages.
    """

    SUCCESS = ""
    ERROR = ""
    WARNING = ""
    INFO = ""
    LOADING = ""
    COIN = ""
    XP = ""
    LEVEL = ""
    TROPHY = ""
    STAR = ""
    DICE = ""
    GAME = ""
