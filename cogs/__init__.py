"""
Bot command modules (cogs).

Each file in this package is a discord.py *cog* -- a self-contained group of
commands, listeners, and background tasks that can be loaded and unloaded at
runtime.  The bot automatically discovers and loads every ``.py`` file in this
directory during startup (see ``main.py:load_cogs``).

Cog overview:
    - ``admin.py``           -- Server configuration, help, owner-only commands.
    - ``ai.py``              -- OpenAI chatbot integration (ask, imagine, translate).
    - ``games.py``           -- Economy system and mini-games (trivia, slots, dice).
    - ``leveling.py``        -- XP / leveling system with level roles and leaderboards.
    - ``moderation.py``      -- Auto-moderation and manual moderation commands.
    - ``profanity_filter.py``-- Multi-language profanity filter with progressive punishments.
    - ``reaction_roles.py``  -- Reaction-based role assignment.
    - ``scheduler.py``       -- Scheduled and recurring announcements (APScheduler).
    - ``tickets.py``         -- Support ticket system with persistent UI views.
    - ``utility.py``         -- Utility commands (ping, reminders, polls, calculator).
    - ``welcome.py``         -- Welcome / goodbye messages and daily scheduled sends.

Adding a new cog:
    1. Create ``cogs/my_feature.py`` with a class extending ``commands.Cog``.
    2. Add an ``async def setup(bot)`` entry point.
    3. The file is automatically loaded on next bot restart.
"""
