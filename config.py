"""
Configuration centralisée du bot Discord.
Charge les variables depuis .env ou utilise des valeurs par défaut.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# === TOKENS ET IDs ===
TOKEN = os.getenv("DISCORD_TOKEN", "YOUR_DISCORD_BOT_TOKEN")
APPLICATION_ID = os.getenv("APPLICATION_ID", "YOUR_APPLICATION_ID")

# === CONFIGURATION GENERALE ===
PREFIX = os.getenv("BOT_PREFIX", "!")
DEFAULT_CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
SEND_HOUR = int(os.getenv("SEND_HOUR", "9"))

# === CONFIGURATION XP/LEVELING ===
XP_PER_MESSAGE = int(os.getenv("XP_PER_MESSAGE", "15"))
XP_COOLDOWN = int(os.getenv("XP_COOLDOWN", "60"))  # secondes
LEVEL_UP_BASE = int(os.getenv("LEVEL_UP_BASE", "100"))
LEVEL_UP_FACTOR = float(os.getenv("LEVEL_UP_FACTOR", "1.5"))

# === CONFIGURATION ECONOMIE ===
DAILY_REWARD_MIN = int(os.getenv("DAILY_REWARD_MIN", "50"))
DAILY_REWARD_MAX = int(os.getenv("DAILY_REWARD_MAX", "200"))
CURRENCY_NAME = os.getenv("CURRENCY_NAME", "coins")
CURRENCY_SYMBOL = os.getenv("CURRENCY_SYMBOL", "")

# === CONFIGURATION MODERATION ===
WARN_THRESHOLD = int(os.getenv("WARN_THRESHOLD", "3"))  # Warnings avant mute
MUTE_DURATION = int(os.getenv("MUTE_DURATION", "3600"))  # 1 heure en secondes
SPAM_THRESHOLD = int(os.getenv("SPAM_THRESHOLD", "5"))  # Messages en 5 secondes
SPAM_INTERVAL = int(os.getenv("SPAM_INTERVAL", "5"))  # Intervalle en secondes

# === MOTS INTERDITS ===
BANNED_WORDS = [
    "badword1", "badword2", "badword3", "idiot", "stupid", "dumb", "fool",
    "moron", "shut up", "loser", "hate", "kill", "die", "suck", "bastard",
    "asshole", "bitch", "crap", "damn", "fuck", "shit", "piss", "dick",
    "cock", "pussy", "slut", "whore", "retard"
]

# === CONFIGURATION TRIVIA ===
TRIVIA_TIME_LIMIT = int(os.getenv("TRIVIA_TIME_LIMIT", "30"))  # secondes
TRIVIA_REWARD = int(os.getenv("TRIVIA_REWARD", "50"))

# === COULEURS EMBEDS ===
class Colors:
    PRIMARY = 0x5865F2  # Discord Blurple
    SUCCESS = 0x57F287  # Green
    WARNING = 0xFEE75C  # Yellow
    ERROR = 0xED4245   # Red
    INFO = 0x5865F2    # Blue
    LEVEL_UP = 0xF1C40F # Gold
    ECONOMY = 0x2ECC71  # Emerald

# === EMOJIS ===
class Emojis:
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
