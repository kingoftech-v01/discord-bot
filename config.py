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

# === CONFIGURATION AI ===
AI_ENABLED = os.getenv("AI_ENABLED", "true").lower() == "true"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY")
AI_MODEL = os.getenv("AI_MODEL", "gpt-3.5-turbo")

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

# === MOTS INTERDITS (FR + EN) ===
# Liste étendue de mots interdits français et anglais
BANNED_WORDS = [
    # Anglais - Insultes courantes
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

    # Français - Insultes courantes
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

    # Variantes avec espaces/caractères
    "f u c k", "s h i t", "b i t c h",
    "n i g g e r", "f a g g o t",

    # Termes haineux
    "nazi", "n@zi", "hitler",
    "terroriste", "terr0riste",
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
