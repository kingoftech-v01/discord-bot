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

            await db.commit()

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


# Instance globale
db = Database()
