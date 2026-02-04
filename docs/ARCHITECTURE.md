# Architecture Guide

This document provides a deep dive into the project architecture for developers who want to understand, maintain, or extend the codebase.

## Table of Contents

- [High-Level Overview](#high-level-overview)
- [Bot Architecture](#bot-architecture)
- [Dashboard Architecture](#dashboard-architecture)
- [Database Design](#database-design)
- [Data Flow](#data-flow)
- [Cog System](#cog-system)
- [Security Architecture](#security-architecture)
- [API Architecture](#api-architecture)

## High-Level Overview

The project consists of two independent applications that share a single SQLite database:

```
+-------------------+       +-------------------+
|   Discord Bot     |       |  Web Dashboard    |
|   (discord.py)    |       |  (Django)         |
|                   |       |                   |
|  main.py          |       |  dashboard/       |
|  config.py        |       |    core/ (views)  |
|  cogs/            |       |    api/ (REST)    |
|  utils/database.py|       |    templates/     |
+--------+----------+       +---------+---------+
         |                             |
         |    +------------------+     |
         +--->|  SQLite Database |<----+
              |  (data/bot.db)   |
              +------------------+
```

### Key Design Decisions

1. **Shared Database**: The bot and dashboard access the same SQLite file. Django models use `managed=False` so they don't try to create/alter tables that the bot owns.
2. **Modular Cog System**: Bot features are split into independent cogs (modules) that can be loaded/unloaded at runtime.
3. **Async-First**: The bot uses `aiosqlite` for non-blocking database access within Discord.py's async event loop.
4. **Unmanaged Models**: Django models reflect the bot's tables but don't manage migrations for them. The bot creates and owns the schema via `database.py`.

## Bot Architecture

### Entry Point: `main.py`

The bot starts in `main.py` with the `DiscordBot` class (extends `commands.Bot`). Startup flow:

```
main.py
  -> DiscordBot.__init__()     # Configure intents, prefix
  -> setup_hook()              # Called by discord.py before connecting
      -> db.initialize()       # Create database tables if needed
      -> load_cogs()           # Load all cog modules from cogs/ directory
  -> on_ready()                # Bot is connected to Discord
  -> bot.run(TOKEN)            # Start the event loop
```

### Configuration: `config.py`

All configuration is loaded from environment variables (via `.env` file using `python-dotenv`). The file provides:

- **Secrets**: `TOKEN`, `APPLICATION_ID`, `OPENAI_API_KEY` (no fallback values for security)
- **Feature config**: XP rates, economy settings, moderation thresholds
- **Helper classes**: `Colors` (embed color constants), `Emojis` (Unicode emoji constants)
- **Banned words**: Hardcoded fallback list used when database words aren't loaded yet

### Database: `utils/database.py`

The `Database` class is a singleton (global `db` instance) that wraps all SQLite operations:

```python
from utils.database import db

# All methods are async and use aiosqlite internally
user = await db.get_or_create_user(user_id, guild_id, username)
await db.add_xp(user_id, guild_id, 15)
```

Key characteristics:
- Creates all tables on `initialize()` with `CREATE TABLE IF NOT EXISTS`
- Uses parameterized queries (?) for all user-provided values
- Column name whitelists (`GUILD_CONFIG_COLUMNS`, `PROFANITY_CONFIG_COLUMNS`) prevent SQL injection in dynamic update queries
- Each method opens/closes its own connection (no persistent connection pool)

### Tables Overview

| Table | Purpose | Primary Key |
|-------|---------|-------------|
| `users` | XP, levels, economy data | `(user_id, guild_id)` |
| `warnings` | Moderation warnings | `id` (autoincrement) |
| `guild_config` | Per-server settings | `guild_id` |
| `tickets` | Support tickets | `id` (autoincrement) |
| `reminders` | User reminders | `id` (autoincrement) |
| `reaction_roles` | Reaction-role mappings | `id` (autoincrement) |
| `level_roles` | Level reward roles | `id` (autoincrement) |
| `trivia_scores` | Trivia game scores | `(user_id, guild_id)` |
| `banned_words` | Profanity filter words | `id` (autoincrement) |
| `profanity_infractions` | Infraction logs | `id` (autoincrement) |
| `user_profanity_stats` | Per-user infraction stats | `(user_id, guild_id)` |
| `profanity_config` | Per-server filter config | `guild_id` |

## Cog System

Each cog is a self-contained module in the `cogs/` directory. Cogs are loaded automatically at startup.

### Cog Lifecycle

```python
class MyCog(commands.Cog):
    def __init__(self, bot):
        # Called when cog is loaded
        self.bot = bot

    def cog_unload(self):
        # Called when cog is unloaded (cleanup)
        pass

async def setup(bot):
    # Required entry point - called by bot.load_extension()
    await bot.add_cog(MyCog(bot))
```

### Cog Map

| Cog File | Class | Purpose |
|----------|-------|---------|
| `moderation.py` | `Moderation` | AutoMod (spam/caps/invite detection), ban/kick/mute/warn/purge |
| `leveling.py` | `Leveling` | XP per message, level-up, level roles, leaderboard |
| `profanity_filter.py` | `ProfanityFilter` | Multi-language word detection, progressive punishments |
| `games.py` | `Games` | Economy (daily/balance/give), trivia, dice, coinflip, slots, RPS |
| `tickets.py` | `Tickets` | Ticket creation, persistent UI views, transcripts |
| `utility.py` | `Utility` | Ping, serverinfo, userinfo, avatar, remind, poll, calculator, AFK |
| `welcome.py` | `Welcome` | Member join/leave messages, daily scheduled messages |
| `admin.py` | `Admin` | Server config commands, help, botinfo, owner commands |
| `ai.py` | `AI` | OpenAI integration, conversation history, ask/imagine/translate |
| `scheduler.py` | `Scheduler` | APScheduler for daily/recurring/one-time announcements |
| `reaction_roles.py` | `ReactionRoles` | Reaction-based role assignment, role menus |

### Adding a New Cog

1. Create `cogs/my_feature.py`:
```python
"""
Cog for my new feature.
"""
import discord
from discord.ext import commands
from utils.database import db

class MyFeature(commands.Cog):
    """Description of the feature."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="mycommand")
    async def my_command(self, ctx: commands.Context, arg: str):
        """Command description shown in help."""
        await ctx.send(f"Hello {arg}!")

async def setup(bot: commands.Bot):
    await bot.add_cog(MyFeature(bot))
```

2. The cog is auto-discovered - no registration needed. `main.py` loads all `.py` files in `cogs/`.

3. Add database methods to `utils/database.py` if your feature needs persistence.

4. Add tests to `tests/test_bot/test_my_feature.py`.

## Dashboard Architecture

### Django Project Structure

```
dashboard/
├── dashboard/          # Django project settings
│   ├── settings.py     # Configuration (reads from .env)
│   ├── urls.py         # Root URL routing
│   └── wsgi.py         # WSGI entry point
├── core/               # Main dashboard app
│   ├── models.py       # Database models (managed=False)
│   ├── views.py        # Web views (server-rendered HTML)
│   ├── adapters.py     # Discord OAuth2 adapter
│   ├── context_processors.py  # Template context
│   └── admin.py        # Django admin config
├── api/                # REST API app
│   ├── serializers.py  # DRF serializers
│   ├── views.py        # API viewsets
│   └── urls.py         # API URL routing
├── templates/          # HTML templates (Bootstrap 5)
└── static/             # CSS, JS, images
```

### Authentication Flow

```
User -> "Login with Discord" button
  -> Discord OAuth2 (via django-allauth)
  -> Discord redirects back with auth code
  -> django-allauth exchanges code for token
  -> DiscordSocialAccountAdapter.populate_user()
  -> User is logged in, token stored for API calls
  -> Dashboard fetches user's guilds from Discord API
  -> Only shows guilds where user has Admin/Manage Server permission
```

### Dashboard Views

Each view:
1. Verifies user is authenticated (`@login_required`)
2. Fetches user's Discord guilds via API
3. Verifies user has admin permissions for the requested guild
4. Queries the shared database for guild data
5. Renders a template with the data

### Key Pattern: `get_user_guilds(request)`

This helper function is used by all guild-specific views to verify access:

```python
def get_user_guilds(request):
    # 1. Get Discord OAuth token from django-allauth
    # 2. Call Discord API: GET /users/@me/guilds
    # 3. Filter guilds where user has Admin or Manage Server permission
    # 4. Check which guilds have the bot present (via GuildConfig table)
    # 5. Return list of accessible guilds
```

## API Architecture

### REST API (Django REST Framework)

The API is versioned and nested under guilds:

```
/api/health/                          # Health check (public)
/api/docs/                            # Swagger UI
/api/redoc/                           # ReDoc
/api/schema/                          # OpenAPI schema

/api/v1/guilds/                       # List user's guilds
/api/v1/guilds/{id}/                  # Guild details + stats

/api/v1/guilds/{id}/users/            # Guild users (CRUD)
/api/v1/guilds/{id}/warnings/         # Warnings (CRUD)
/api/v1/guilds/{id}/profanity/words/  # Banned words (CRUD)
/api/v1/guilds/{id}/profanity/config/ # Profanity config
/api/v1/guilds/{id}/profanity/infractions/  # Infractions (read-only)
/api/v1/guilds/{id}/level-roles/      # Level roles (CRUD)
/api/v1/guilds/{id}/leaderboard/      # XP leaderboard
```

### Permission System

All API endpoints require:
1. **Authentication**: Session-based (from Discord OAuth login)
2. **Guild Admin**: `IsGuildAdmin` permission class verifies the user has Discord Admin/Manage Server permissions for the requested guild

### Rate Limiting

- Anonymous: 20 requests/minute
- Authenticated: 60 requests/minute
- Configured in `settings.py` via DRF throttling

## Data Flow

### XP Gain Flow (Example)

```
1. User sends a message in Discord
2. Leveling.on_message() listener fires
3. Check cooldown (60s since last XP gain)
4. If eligible: db.add_xp(user_id, guild_id, 15)
5. db.add_xp() adds XP and checks if level-up threshold is reached
6. If leveled up:
   a. Send level-up embed to channel
   b. Check for level role rewards
   c. Assign new roles if applicable
7. Data is immediately visible in dashboard (shared DB)
```

### Profanity Detection Flow

```
1. User sends a message
2. ProfanityFilter.on_message() listener fires
3. Load banned words from DB (cached per guild)
4. Check message against word list with word boundary detection
5. If match found:
   a. Delete message (if configured)
   b. Log infraction to profanity_infractions table
   c. Increment user_profanity_stats counters
   d. Determine punishment based on total infractions:
      - < warn_threshold: delete only
      - >= warn_threshold: warn
      - >= mute_threshold: mute (timeout)
      - >= kick_threshold: kick
      - >= ban_threshold: ban
   e. DM user (if configured)
   f. Log to mod log channel (if configured)
```

## Security Architecture

See [SECURITY.md](SECURITY.md) for the full security documentation.

Key security measures:
- **No `eval()`**: Calculator uses AST-based safe math evaluation
- **SQL injection prevention**: Column name whitelists for dynamic queries
- **No hardcoded secrets**: All tokens loaded from environment variables
- **Django security hardening**: HSTS, secure cookies, CSRF protection in production
- **API rate limiting**: Both Nginx-level and DRF-level
- **Discord permission checks**: Both bot and dashboard verify guild admin permissions
- **Error sanitization**: Internal errors are not exposed to API clients

## Extending the Project

### Adding a New Feature Checklist

1. [ ] Create cog in `cogs/` (or add to existing cog)
2. [ ] Add database methods to `utils/database.py` if needed
3. [ ] Add Django model in `dashboard/core/models.py` (managed=False)
4. [ ] Add API serializer in `dashboard/api/serializers.py`
5. [ ] Add API view in `dashboard/api/views.py`
6. [ ] Register API URL in `dashboard/api/urls.py`
7. [ ] Add dashboard view/template if needed
8. [ ] Write tests in `tests/`
9. [ ] Update documentation

### Environment Requirements

- **Bot**: Requires `DISCORD_TOKEN` and Discord intents (Presence, Members, Message Content)
- **Dashboard**: Requires `DJANGO_SECRET_KEY`, `DISCORD_CLIENT_SECRET`, and configured OAuth redirect URI
- **AI features**: Requires `OPENAI_API_KEY`
- **Docker**: Requires Docker and Docker Compose v2
