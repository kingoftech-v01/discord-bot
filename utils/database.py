"""
Module de gestion de la base de données SQLite.
Gère toutes les opérations de persistance des données.
"""
import sqlite3
import aiosqlite
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import json

DATABASE_PATH = "data/bot.db"


class Database:
    """Gestionnaire de base de données asynchrone."""

    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path

    async def init(self):
        """Initialise la base de données et crée les tables."""
        async with aiosqlite.connect(self.db_path) as db:
            # Table des utilisateurs (XP, niveau, économie)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    xp INTEGER DEFAULT 0,
                    level INTEGER DEFAULT 1,
                    total_xp INTEGER DEFAULT 0,
                    messages_count INTEGER DEFAULT 0,
                    coins INTEGER DEFAULT 0,
                    last_xp_gain TEXT,
                    last_daily TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, guild_id)
                )
            """)

            # Table des avertissements
            await db.execute("""
                CREATE TABLE IF NOT EXISTS warnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    moderator_id INTEGER NOT NULL,
                    reason TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Table des infractions (spam, mots interdits)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS infractions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    details TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Table des reaction roles
            await db.execute("""
                CREATE TABLE IF NOT EXISTS reaction_roles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    emoji TEXT NOT NULL,
                    role_id INTEGER NOT NULL,
                    UNIQUE(message_id, emoji)
                )
            """)

            # Table de configuration des serveurs
            await db.execute("""
                CREATE TABLE IF NOT EXISTS guild_config (
                    guild_id INTEGER PRIMARY KEY,
                    welcome_channel_id INTEGER,
                    log_channel_id INTEGER,
                    level_up_channel_id INTEGER,
                    mute_role_id INTEGER,
                    auto_mod_enabled INTEGER DEFAULT 1,
                    leveling_enabled INTEGER DEFAULT 1,
                    welcome_message TEXT DEFAULT 'Bienvenue {user} sur {server}!',
                    goodbye_message TEXT DEFAULT '{user} a quitté le serveur.',
                    level_up_message TEXT DEFAULT 'Félicitations {user}! Tu es maintenant niveau {level}!',
                    prefix TEXT DEFAULT '!',
                    settings TEXT DEFAULT '{}'
                )
            """)

            # Table des tickets support
            await db.execute("""
                CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    subject TEXT,
                    status TEXT DEFAULT 'open',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    closed_at TEXT
                )
            """)

            # Table des rappels
            await db.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    message TEXT NOT NULL,
                    remind_at TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Table des scores de trivia
            await db.execute("""
                CREATE TABLE IF NOT EXISTS trivia_scores (
                    user_id INTEGER,
                    guild_id INTEGER,
                    correct_answers INTEGER DEFAULT 0,
                    total_questions INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, guild_id)
                )
            """)

            # Table des level roles (rôles attribués par niveau)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS level_roles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    level INTEGER NOT NULL,
                    role_id INTEGER NOT NULL,
                    UNIQUE(guild_id, level)
                )
            """)

            # =========================================
            # TABLES POUR GESTION DES MOTS INTERDITS
            # =========================================

            # Table des mots interdits (multi-langue, par serveur ou global)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS banned_words (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    word TEXT NOT NULL,
                    language TEXT DEFAULT 'all',
                    guild_id INTEGER DEFAULT 0,
                    severity INTEGER DEFAULT 1,
                    added_by INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(word, guild_id)
                )
            """)

            # Table des infractions pour mots interdits
            await db.execute("""
                CREATE TABLE IF NOT EXISTS profanity_infractions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    word_used TEXT NOT NULL,
                    message_content TEXT,
                    action_taken TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Table des sanctions progressives par utilisateur
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_profanity_stats (
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    total_infractions INTEGER DEFAULT 0,
                    warnings_count INTEGER DEFAULT 0,
                    mutes_count INTEGER DEFAULT 0,
                    kicks_count INTEGER DEFAULT 0,
                    is_banned INTEGER DEFAULT 0,
                    last_infraction TEXT,
                    PRIMARY KEY (user_id, guild_id)
                )
            """)

            # Table de configuration des sanctions
            await db.execute("""
                CREATE TABLE IF NOT EXISTS profanity_config (
                    guild_id INTEGER PRIMARY KEY,
                    enabled INTEGER DEFAULT 1,
                    warn_threshold INTEGER DEFAULT 3,
                    mute_threshold INTEGER DEFAULT 5,
                    kick_threshold INTEGER DEFAULT 8,
                    ban_threshold INTEGER DEFAULT 10,
                    mute_duration INTEGER DEFAULT 3600,
                    delete_message INTEGER DEFAULT 1,
                    log_infractions INTEGER DEFAULT 1,
                    dm_user INTEGER DEFAULT 1
                )
            """)

            await db.commit()

        # Insérer les mots interdits par défaut
        await self._init_default_banned_words()

    # ===============================
    # GESTION UTILISATEURS / XP
    # ===============================

    async def get_user(self, user_id: int, guild_id: int) -> Optional[Dict]:
        """Récupère les données d'un utilisateur."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def create_user(self, user_id: int, guild_id: int) -> Dict:
        """Crée un nouvel utilisateur."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO users (user_id, guild_id) VALUES (?, ?)",
                (user_id, guild_id)
            )
            await db.commit()
        return await self.get_user(user_id, guild_id)

    async def get_or_create_user(self, user_id: int, guild_id: int) -> Dict:
        """Récupère ou crée un utilisateur."""
        user = await self.get_user(user_id, guild_id)
        if not user:
            user = await self.create_user(user_id, guild_id)
        return user

    async def add_xp(self, user_id: int, guild_id: int, xp: int) -> Dict:
        """Ajoute de l'XP à un utilisateur."""
        user = await self.get_or_create_user(user_id, guild_id)
        new_xp = user['xp'] + xp
        new_total_xp = user['total_xp'] + xp
        new_messages = user['messages_count'] + 1

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE users
                SET xp = ?, total_xp = ?, messages_count = ?, last_xp_gain = ?
                WHERE user_id = ? AND guild_id = ?
            """, (new_xp, new_total_xp, new_messages, datetime.now().isoformat(), user_id, guild_id))
            await db.commit()

        return await self.get_user(user_id, guild_id)

    async def set_level(self, user_id: int, guild_id: int, level: int, remaining_xp: int = 0):
        """Met à jour le niveau d'un utilisateur."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE users SET level = ?, xp = ?
                WHERE user_id = ? AND guild_id = ?
            """, (level, remaining_xp, user_id, guild_id))
            await db.commit()

    async def get_leaderboard(self, guild_id: int, limit: int = 10) -> List[Dict]:
        """Récupère le classement XP du serveur."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM users
                WHERE guild_id = ?
                ORDER BY total_xp DESC
                LIMIT ?
            """, (guild_id, limit)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_rank(self, user_id: int, guild_id: int) -> int:
        """Récupère le rang d'un utilisateur dans le serveur."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT COUNT(*) + 1 as rank FROM users
                WHERE guild_id = ? AND total_xp > (
                    SELECT total_xp FROM users WHERE user_id = ? AND guild_id = ?
                )
            """, (guild_id, user_id, guild_id)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    # ===============================
    # GESTION ECONOMIE
    # ===============================

    async def add_coins(self, user_id: int, guild_id: int, amount: int):
        """Ajoute des coins à un utilisateur."""
        user = await self.get_or_create_user(user_id, guild_id)
        new_coins = max(0, user['coins'] + amount)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET coins = ? WHERE user_id = ? AND guild_id = ?",
                (new_coins, user_id, guild_id)
            )
            await db.commit()

    async def can_claim_daily(self, user_id: int, guild_id: int) -> bool:
        """Vérifie si l'utilisateur peut réclamer sa récompense quotidienne."""
        user = await self.get_or_create_user(user_id, guild_id)
        if not user['last_daily']:
            return True
        last_daily = datetime.fromisoformat(user['last_daily'])
        return datetime.now() - last_daily > timedelta(hours=24)

    async def claim_daily(self, user_id: int, guild_id: int, amount: int):
        """Réclame la récompense quotidienne."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE users
                SET coins = coins + ?, last_daily = ?
                WHERE user_id = ? AND guild_id = ?
            """, (amount, datetime.now().isoformat(), user_id, guild_id))
            await db.commit()

    async def get_economy_leaderboard(self, guild_id: int, limit: int = 10) -> List[Dict]:
        """Récupère le classement économie du serveur."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM users
                WHERE guild_id = ?
                ORDER BY coins DESC
                LIMIT ?
            """, (guild_id, limit)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    # ===============================
    # GESTION WARNINGS
    # ===============================

    async def add_warning(self, user_id: int, guild_id: int, moderator_id: int, reason: str = None) -> int:
        """Ajoute un avertissement et retourne le nombre total."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO warnings (user_id, guild_id, moderator_id, reason)
                VALUES (?, ?, ?, ?)
            """, (user_id, guild_id, moderator_id, reason))
            await db.commit()
        return await self.get_warning_count(user_id, guild_id)

    async def get_warning_count(self, user_id: int, guild_id: int) -> int:
        """Récupère le nombre d'avertissements d'un utilisateur."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM warnings WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def get_warnings(self, user_id: int, guild_id: int) -> List[Dict]:
        """Récupère tous les avertissements d'un utilisateur."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM warnings WHERE user_id = ? AND guild_id = ? ORDER BY created_at DESC",
                (user_id, guild_id)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def clear_warnings(self, user_id: int, guild_id: int):
        """Supprime tous les avertissements d'un utilisateur."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM warnings WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id)
            )
            await db.commit()

    # ===============================
    # GESTION REACTION ROLES
    # ===============================

    async def add_reaction_role(self, guild_id: int, message_id: int, channel_id: int, emoji: str, role_id: int):
        """Ajoute une configuration de reaction role."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO reaction_roles (guild_id, message_id, channel_id, emoji, role_id)
                VALUES (?, ?, ?, ?, ?)
            """, (guild_id, message_id, channel_id, emoji, role_id))
            await db.commit()

    async def get_reaction_role(self, message_id: int, emoji: str) -> Optional[Dict]:
        """Récupère la configuration d'un reaction role."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM reaction_roles WHERE message_id = ? AND emoji = ?",
                (message_id, emoji)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_all_reaction_roles(self, guild_id: int) -> List[Dict]:
        """Récupère tous les reaction roles d'un serveur."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM reaction_roles WHERE guild_id = ?",
                (guild_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def remove_reaction_role(self, message_id: int, emoji: str):
        """Supprime une configuration de reaction role."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM reaction_roles WHERE message_id = ? AND emoji = ?",
                (message_id, emoji)
            )
            await db.commit()

    # ===============================
    # GESTION CONFIGURATION SERVEUR
    # ===============================

    async def get_guild_config(self, guild_id: int) -> Dict:
        """Récupère la configuration d'un serveur."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM guild_config WHERE guild_id = ?",
                (guild_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)

        # Créer la config par défaut
        await self.create_guild_config(guild_id)
        return await self.get_guild_config(guild_id)

    async def create_guild_config(self, guild_id: int):
        """Crée la configuration par défaut d'un serveur."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO guild_config (guild_id) VALUES (?)",
                (guild_id,)
            )
            await db.commit()

    async def update_guild_config(self, guild_id: int, **kwargs):
        """Met à jour la configuration d'un serveur."""
        if not kwargs:
            return

        set_clause = ", ".join(f"{key} = ?" for key in kwargs.keys())
        values = list(kwargs.values()) + [guild_id]

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                f"UPDATE guild_config SET {set_clause} WHERE guild_id = ?",
                values
            )
            await db.commit()

    # ===============================
    # GESTION TICKETS
    # ===============================

    async def create_ticket(self, guild_id: int, channel_id: int, user_id: int, subject: str = None) -> int:
        """Crée un nouveau ticket."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO tickets (guild_id, channel_id, user_id, subject)
                VALUES (?, ?, ?, ?)
            """, (guild_id, channel_id, user_id, subject))
            await db.commit()
            return cursor.lastrowid

    async def close_ticket(self, ticket_id: int):
        """Ferme un ticket."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE tickets SET status = 'closed', closed_at = ?
                WHERE id = ?
            """, (datetime.now().isoformat(), ticket_id))
            await db.commit()

    async def get_ticket_by_channel(self, channel_id: int) -> Optional[Dict]:
        """Récupère un ticket par son channel."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM tickets WHERE channel_id = ? AND status = 'open'",
                (channel_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    # ===============================
    # GESTION RAPPELS
    # ===============================

    async def add_reminder(self, user_id: int, channel_id: int, message: str, remind_at: datetime) -> int:
        """Ajoute un rappel."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO reminders (user_id, channel_id, message, remind_at)
                VALUES (?, ?, ?, ?)
            """, (user_id, channel_id, message, remind_at.isoformat()))
            await db.commit()
            return cursor.lastrowid

    async def get_due_reminders(self) -> List[Dict]:
        """Récupère les rappels dus."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM reminders WHERE remind_at <= ?",
                (datetime.now().isoformat(),)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def delete_reminder(self, reminder_id: int):
        """Supprime un rappel."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
            await db.commit()

    # ===============================
    # GESTION TRIVIA
    # ===============================

    async def update_trivia_score(self, user_id: int, guild_id: int, correct: bool):
        """Met à jour le score de trivia."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO trivia_scores (user_id, guild_id, correct_answers, total_questions)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(user_id, guild_id) DO UPDATE SET
                    correct_answers = correct_answers + ?,
                    total_questions = total_questions + 1
            """, (user_id, guild_id, 1 if correct else 0, 1 if correct else 0))
            await db.commit()

    async def get_trivia_leaderboard(self, guild_id: int, limit: int = 10) -> List[Dict]:
        """Récupère le classement trivia."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM trivia_scores
                WHERE guild_id = ?
                ORDER BY correct_answers DESC
                LIMIT ?
            """, (guild_id, limit)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    # ===============================
    # GESTION LEVEL ROLES
    # ===============================

    async def add_level_role(self, guild_id: int, level: int, role_id: int):
        """Ajoute un rôle de niveau."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO level_roles (guild_id, level, role_id)
                VALUES (?, ?, ?)
            """, (guild_id, level, role_id))
            await db.commit()

    async def get_level_roles(self, guild_id: int) -> List[Dict]:
        """Récupère tous les rôles de niveau d'un serveur."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM level_roles WHERE guild_id = ? ORDER BY level ASC",
                (guild_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_role_for_level(self, guild_id: int, level: int) -> Optional[int]:
        """Récupère le rôle pour un niveau spécifique."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT role_id FROM level_roles WHERE guild_id = ? AND level = ?",
                (guild_id, level)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def remove_level_role(self, guild_id: int, level: int):
        """Supprime un rôle de niveau."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM level_roles WHERE guild_id = ? AND level = ?",
                (guild_id, level)
            )
            await db.commit()


    # ===============================
    # GESTION MOTS INTERDITS
    # ===============================

    async def _init_default_banned_words(self):
        """Initialise les mots interdits par défaut dans la base."""
        default_words = [
            # Anglais
            ("fuck", "en", 3), ("fucking", "en", 3), ("fucker", "en", 3),
            ("shit", "en", 2), ("bullshit", "en", 2), ("shitty", "en", 2),
            ("bitch", "en", 2), ("asshole", "en", 3), ("bastard", "en", 2),
            ("dick", "en", 2), ("cock", "en", 2), ("pussy", "en", 2),
            ("slut", "en", 3), ("whore", "en", 3), ("cunt", "en", 3),
            ("retard", "en", 3), ("retarded", "en", 3),
            ("faggot", "en", 4), ("fag", "en", 4),
            ("nigger", "en", 5), ("nigga", "en", 4),
            ("kys", "en", 5), ("kill yourself", "en", 5),

            # Français
            ("merde", "fr", 1), ("putain", "fr", 2), ("ptn", "fr", 2),
            ("salope", "fr", 3), ("connard", "fr", 2), ("connasse", "fr", 2),
            ("enculé", "fr", 3), ("encule", "fr", 3), ("nique", "fr", 3),
            ("niquer", "fr", 3), ("ntm", "fr", 4), ("nique ta mère", "fr", 4),
            ("fdp", "fr", 4), ("fils de pute", "fr", 4),
            ("pd", "fr", 3), ("pédé", "fr", 3), ("pédale", "fr", 3),
            ("tapette", "fr", 3), ("batard", "fr", 2), ("bâtard", "fr", 2),
            ("bite", "fr", 2), ("couilles", "fr", 1),
            ("ta gueule", "fr", 2), ("tg", "fr", 2), ("ferme ta gueule", "fr", 2),
            ("crétin", "fr", 1), ("abruti", "fr", 1), ("débile", "fr", 2),
            ("imbécile", "fr", 1), ("ordure", "fr", 2),
            ("pétasse", "fr", 3), ("pouffiasse", "fr", 3),
            ("salaud", "fr", 2), ("enfoiré", "fr", 2),
            ("bouffon", "fr", 1), ("gogol", "fr", 2),
            ("attardé", "fr", 3), ("mongol", "fr", 4), ("trisomique", "fr", 4),
            ("nègre", "fr", 5), ("bougnoule", "fr", 5),
            ("va te faire foutre", "fr", 3), ("vtff", "fr", 3),

            # Espagnol
            ("puta", "es", 3), ("mierda", "es", 2), ("coño", "es", 2),
            ("joder", "es", 2), ("cabron", "es", 2), ("cabrón", "es", 2),
            ("pendejo", "es", 2), ("maricón", "es", 4), ("maricon", "es", 4),
            ("hijo de puta", "es", 4), ("polla", "es", 2), ("gilipollas", "es", 2),

            # Allemand
            ("scheiße", "de", 2), ("scheisse", "de", 2), ("arschloch", "de", 3),
            ("hurensohn", "de", 4), ("fotze", "de", 3), ("wichser", "de", 3),
            ("schwuchtel", "de", 4), ("missgeburt", "de", 4),

            # Italien
            ("cazzo", "it", 2), ("merda", "it", 2), ("stronzo", "it", 2),
            ("puttana", "it", 3), ("vaffanculo", "it", 3), ("frocio", "it", 4),

            # Portugais
            ("porra", "pt", 2), ("caralho", "pt", 2), ("filho da puta", "pt", 4),
            ("viado", "pt", 4), ("puta", "pt", 3), ("merda", "pt", 2),

            # Arabe translittéré
            ("kelb", "ar", 2), ("kess", "ar", 3), ("sharmouta", "ar", 4),
            ("ibn el sharmouta", "ar", 5), ("zebi", "ar", 3), ("nik", "ar", 3),
        ]

        async with aiosqlite.connect(self.db_path) as db:
            for word, lang, severity in default_words:
                await db.execute("""
                    INSERT OR IGNORE INTO banned_words (word, language, guild_id, severity)
                    VALUES (?, ?, 0, ?)
                """, (word.lower(), lang, severity))
            await db.commit()

    async def add_banned_word(self, word: str, language: str = "all", guild_id: int = 0,
                             severity: int = 1, added_by: int = None) -> bool:
        """Ajoute un mot interdit."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute("""
                    INSERT INTO banned_words (word, language, guild_id, severity, added_by)
                    VALUES (?, ?, ?, ?, ?)
                """, (word.lower(), language, guild_id, severity, added_by))
                await db.commit()
                return True
            except Exception:
                return False

    async def remove_banned_word(self, word: str, guild_id: int = 0) -> bool:
        """Supprime un mot interdit."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM banned_words WHERE word = ? AND guild_id = ?",
                (word.lower(), guild_id)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def get_banned_words(self, guild_id: int = 0, language: str = None) -> List[Dict]:
        """Récupère tous les mots interdits (globaux + serveur)."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if language:
                async with db.execute("""
                    SELECT * FROM banned_words
                    WHERE (guild_id = 0 OR guild_id = ?)
                    AND (language = ? OR language = 'all')
                    ORDER BY severity DESC
                """, (guild_id, language)) as cursor:
                    rows = await cursor.fetchall()
            else:
                async with db.execute("""
                    SELECT * FROM banned_words
                    WHERE guild_id = 0 OR guild_id = ?
                    ORDER BY severity DESC
                """, (guild_id,)) as cursor:
                    rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_banned_words_list(self, guild_id: int = 0) -> List[str]:
        """Récupère la liste simple des mots interdits."""
        words = await self.get_banned_words(guild_id)
        return [w['word'] for w in words]

    async def check_message_for_profanity(self, content: str, guild_id: int = 0) -> Optional[Dict]:
        """Vérifie si un message contient des mots interdits."""
        content_lower = content.lower()
        words = await self.get_banned_words(guild_id)

        for word_data in words:
            word = word_data['word']
            # Vérification avec frontières de mots pour éviter les faux positifs
            import re
            pattern = r'\b' + re.escape(word) + r'\b'
            if re.search(pattern, content_lower):
                return word_data

            # Vérification aussi sans frontières pour les variantes
            if word in content_lower:
                return word_data

        return None

    # ===============================
    # GESTION INFRACTIONS PROFANITY
    # ===============================

    async def add_profanity_infraction(self, user_id: int, guild_id: int,
                                       word_used: str, message_content: str,
                                       action_taken: str) -> Dict:
        """Ajoute une infraction et retourne les stats mises à jour."""
        async with aiosqlite.connect(self.db_path) as db:
            # Ajouter l'infraction
            await db.execute("""
                INSERT INTO profanity_infractions
                (user_id, guild_id, word_used, message_content, action_taken)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, guild_id, word_used, message_content[:500], action_taken))

            # Mettre à jour les stats
            await db.execute("""
                INSERT INTO user_profanity_stats (user_id, guild_id, total_infractions, last_infraction)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(user_id, guild_id) DO UPDATE SET
                    total_infractions = total_infractions + 1,
                    last_infraction = ?
            """, (user_id, guild_id, datetime.now().isoformat(), datetime.now().isoformat()))

            # Incrémenter le compteur spécifique selon l'action
            if action_taken == "warn":
                await db.execute("""
                    UPDATE user_profanity_stats
                    SET warnings_count = warnings_count + 1
                    WHERE user_id = ? AND guild_id = ?
                """, (user_id, guild_id))
            elif action_taken == "mute":
                await db.execute("""
                    UPDATE user_profanity_stats
                    SET mutes_count = mutes_count + 1
                    WHERE user_id = ? AND guild_id = ?
                """, (user_id, guild_id))
            elif action_taken == "kick":
                await db.execute("""
                    UPDATE user_profanity_stats
                    SET kicks_count = kicks_count + 1
                    WHERE user_id = ? AND guild_id = ?
                """, (user_id, guild_id))
            elif action_taken == "ban":
                await db.execute("""
                    UPDATE user_profanity_stats
                    SET is_banned = 1
                    WHERE user_id = ? AND guild_id = ?
                """, (user_id, guild_id))

            await db.commit()

        return await self.get_user_profanity_stats(user_id, guild_id)

    async def get_user_profanity_stats(self, user_id: int, guild_id: int) -> Dict:
        """Récupère les statistiques d'infractions d'un utilisateur."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM user_profanity_stats
                WHERE user_id = ? AND guild_id = ?
            """, (user_id, guild_id)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)
                return {
                    'user_id': user_id,
                    'guild_id': guild_id,
                    'total_infractions': 0,
                    'warnings_count': 0,
                    'mutes_count': 0,
                    'kicks_count': 0,
                    'is_banned': 0,
                    'last_infraction': None
                }

    async def get_user_profanity_history(self, user_id: int, guild_id: int, limit: int = 10) -> List[Dict]:
        """Récupère l'historique des infractions d'un utilisateur."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM profanity_infractions
                WHERE user_id = ? AND guild_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (user_id, guild_id, limit)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def reset_user_profanity_stats(self, user_id: int, guild_id: int):
        """Réinitialise les stats de profanity d'un utilisateur."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE user_profanity_stats
                SET total_infractions = 0, warnings_count = 0,
                    mutes_count = 0, kicks_count = 0, is_banned = 0
                WHERE user_id = ? AND guild_id = ?
            """, (user_id, guild_id))
            await db.commit()

    # ===============================
    # CONFIGURATION SANCTIONS
    # ===============================

    async def get_profanity_config(self, guild_id: int) -> Dict:
        """Récupère la configuration des sanctions."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM profanity_config WHERE guild_id = ?",
                (guild_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)

            # Créer config par défaut
            await db.execute(
                "INSERT OR IGNORE INTO profanity_config (guild_id) VALUES (?)",
                (guild_id,)
            )
            await db.commit()

        return await self.get_profanity_config(guild_id)

    async def update_profanity_config(self, guild_id: int, **kwargs):
        """Met à jour la configuration des sanctions."""
        if not kwargs:
            return

        # S'assurer que la config existe
        await self.get_profanity_config(guild_id)

        set_clause = ", ".join(f"{key} = ?" for key in kwargs.keys())
        values = list(kwargs.values()) + [guild_id]

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                f"UPDATE profanity_config SET {set_clause} WHERE guild_id = ?",
                values
            )
            await db.commit()

    async def determine_punishment(self, user_id: int, guild_id: int) -> str:
        """Détermine la sanction appropriée basée sur l'historique."""
        stats = await self.get_user_profanity_stats(user_id, guild_id)
        config = await self.get_profanity_config(guild_id)

        infractions = stats['total_infractions']

        if infractions >= config['ban_threshold']:
            return "ban"
        elif infractions >= config['kick_threshold']:
            return "kick"
        elif infractions >= config['mute_threshold']:
            return "mute"
        elif infractions >= config['warn_threshold']:
            return "warn"
        else:
            return "warn"  # Toujours au moins avertir

    async def get_profanity_leaderboard(self, guild_id: int, limit: int = 10) -> List[Dict]:
        """Récupère le classement des utilisateurs avec le plus d'infractions."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM user_profanity_stats
                WHERE guild_id = ?
                ORDER BY total_infractions DESC
                LIMIT ?
            """, (guild_id, limit)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]


# Instance globale
db = Database()
