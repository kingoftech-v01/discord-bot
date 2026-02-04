# Configuration Guide

Complete reference for all configuration options.

## Environment Variables

### Discord Configuration (Required)

| Variable | Description | Default |
|----------|-------------|---------|
| `DISCORD_TOKEN` | Bot token from Discord Developer Portal | - |
| `APPLICATION_ID` | Application ID from Discord | - |
| `DISCORD_CLIENT_SECRET` | OAuth2 client secret (for dashboard) | - |

### General Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `BOT_PREFIX` | Command prefix | `!` |
| `CHANNEL_ID` | Default announcement channel | `0` |
| `SEND_HOUR` | Hour for scheduled messages (0-23) | `9` |

### AI Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `AI_ENABLED` | Enable AI features | `true` |
| `OPENAI_API_KEY` | OpenAI API key | - |
| `AI_MODEL` | GPT model to use | `gpt-3.5-turbo` |
| `AI_CHANNEL_ID` | Channel for AI responses | - |

### Leveling System

| Variable | Description | Default |
|----------|-------------|---------|
| `XP_PER_MESSAGE` | XP gained per message | `15` |
| `XP_COOLDOWN` | Seconds between XP gains | `60` |
| `LEVEL_UP_BASE` | Base XP for level 1 | `100` |
| `LEVEL_UP_FACTOR` | XP multiplier per level | `1.5` |

### Economy System

| Variable | Description | Default |
|----------|-------------|---------|
| `DAILY_REWARD_MIN` | Minimum daily reward | `50` |
| `DAILY_REWARD_MAX` | Maximum daily reward | `200` |
| `CURRENCY_NAME` | Currency name | `coins` |
| `CURRENCY_SYMBOL` | Currency symbol | (empty) |

### Moderation

| Variable | Description | Default |
|----------|-------------|---------|
| `WARN_THRESHOLD` | Warnings before action | `3` |
| `MUTE_DURATION` | Default mute in seconds | `3600` |
| `SPAM_THRESHOLD` | Messages for spam detection | `5` |
| `SPAM_INTERVAL` | Seconds for spam detection | `5` |

### Dashboard (Django)

| Variable | Description | Default |
|----------|-------------|---------|
| `DJANGO_SECRET_KEY` | Django secret key | - |
| `DEBUG` | Debug mode | `True` |
| `ALLOWED_HOSTS` | Comma-separated hosts | `localhost,127.0.0.1` |
| `DASHBOARD_URL` | Base URL for OAuth | `http://localhost:8000` |

### Database

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_PATH` | SQLite file path | `data/bot.db` |
| `DATABASE_URL` | PostgreSQL connection URL | - |
| `POSTGRES_USER` | PostgreSQL username | `discord_bot` |
| `POSTGRES_PASSWORD` | PostgreSQL password | - |
| `POSTGRES_DB` | PostgreSQL database name | `discord_bot` |
| `POSTGRES_HOST` | PostgreSQL host | `db` |
| `POSTGRES_PORT` | PostgreSQL port | `5432` |

### Redis

| Variable | Description | Default |
|----------|-------------|---------|
| `REDIS_URL` | Redis connection URL | `redis://redis:6379/0` |

### Docker

| Variable | Description | Default |
|----------|-------------|---------|
| `COMPOSE_PROJECT_NAME` | Docker project name | `discord-bot` |
| `GUNICORN_WORKERS` | Number of workers | `4` |
| `GUNICORN_THREADS` | Threads per worker | `2` |

### Logging

| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_LEVEL` | Logging level | `INFO` |
| `LOG_FILE` | Log file path | `logs/bot.log` |

### API

| Variable | Description | Default |
|----------|-------------|---------|
| `API_RATE_LIMIT` | Requests per minute | `60` |
| `API_SECRET_KEY` | API authentication key | - |

## Bot Configuration (config.py)

The `config.py` file contains additional configuration that can be modified:

```python
# Banned words list (loaded from database)
BANNED_WORDS = [...]

# Trivia categories
TRIVIA_CATEGORIES = [...]

# Level role rewards
LEVEL_ROLES = {
    5: "Newcomer",
    10: "Regular",
    25: "Veteran",
    50: "Elite",
}
```

## Dashboard Configuration (settings.py)

Key Django settings:

```python
# Static files
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Session settings
SESSION_COOKIE_AGE = 86400 * 7  # 1 week

# Security (production)
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
```

## Profanity Filter Configuration

Configure via dashboard or database:

| Setting | Description | Default |
|---------|-------------|---------|
| `enabled` | Filter active | `1` |
| `warn_threshold` | Warnings before mute | `3` |
| `mute_threshold` | Infractions before mute | `5` |
| `kick_threshold` | Infractions before kick | `8` |
| `ban_threshold` | Infractions before ban | `10` |
| `mute_duration` | Mute duration in seconds | `3600` |
| `delete_message` | Delete offending messages | `1` |
| `dm_user` | DM user on infraction | `1` |

## Per-Server Configuration

Each server can have custom settings stored in `guild_config` table:

| Field | Description |
|-------|-------------|
| `prefix` | Custom command prefix |
| `welcome_channel` | Welcome message channel |
| `log_channel` | Moderation log channel |
| `welcome_message` | Custom welcome message |
| `goodbye_message` | Custom goodbye message |
| `level_up_message` | Custom level up message |
| `auto_mod_enabled` | Auto-moderation toggle |
| `leveling_enabled` | Leveling system toggle |

### Message Variables

Welcome/goodbye/level messages support variables:

| Variable | Description |
|----------|-------------|
| `{user}` | User mention |
| `{username}` | Username |
| `{server}` | Server name |
| `{member_count}` | Total members |
| `{level}` | New level (level up only) |

Example:
```
Welcome {user} to {server}! You are member #{member_count}!
```

## Best Practices

### Security

1. Never commit `.env` file
2. Use strong, unique secrets
3. Enable `DEBUG=False` in production
4. Use HTTPS in production
5. Rotate tokens periodically

### Performance

1. Use PostgreSQL for production
2. Enable Redis caching
3. Adjust worker count based on CPU cores
4. Set appropriate rate limits

### Monitoring

1. Set `LOG_LEVEL=INFO` for production
2. Monitor log files
3. Set up alerts for errors
4. Track API usage
