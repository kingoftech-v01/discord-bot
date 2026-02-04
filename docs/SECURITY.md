# Security Guide

This document describes the security measures implemented in Discord Bot Pro and provides guidelines for maintaining security when developing new features.

## Table of Contents

- [Overview](#overview)
- [Bot Security](#bot-security)
- [Dashboard Security](#dashboard-security)
- [API Security](#api-security)
- [Database Security](#database-security)
- [Deployment Security](#deployment-security)
- [Security Checklist for Contributors](#security-checklist-for-contributors)
- [Reporting Vulnerabilities](#reporting-vulnerabilities)

## Overview

Security is enforced at multiple layers:

```
[Internet]
    |
[Nginx] -----> Rate limiting, HTTPS termination, security headers
    |
[Django] ----> CSRF, session auth, permission checks, throttling
    |
[Bot] -------> Permission checks, input validation, safe evaluation
    |
[Database] --> Parameterized queries, column whitelists
```

## Bot Security

### No `eval()` or `exec()`

The calculator command (`!calc`) uses a safe AST-based parser instead of Python's `eval()`. The parser only allows:
- Numeric literals (integers and floats)
- Basic arithmetic operators: `+`, `-`, `*`, `/`
- Parentheses for grouping
- Unary operators: `+`, `-` (for negative numbers)

Any other Python expression (function calls, attribute access, imports) will be rejected.

**Location**: `cogs/utility.py` - `Utility._safe_math_eval()`

### Secret Management

All secrets are loaded from environment variables with **no fallback values**:

```python
# CORRECT - fails fast if not set
TOKEN = os.getenv("DISCORD_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# WRONG - never do this
TOKEN = os.getenv("DISCORD_TOKEN", "your-token-here")
```

The bot checks for empty token at startup and exits with a clear error message.

### Permission Checks

Bot commands verify Discord permissions before executing:

```python
@commands.has_permissions(ban_members=True)  # User must have ban permission
async def ban(self, ctx, member: discord.Member, *, reason: str):
    ...
```

The moderation cog also enforces role hierarchy:
- The bot cannot moderate users with a higher role
- The command user cannot moderate users with a higher or equal role

### Input Validation

- Command arguments are validated via Discord.py's type system
- The `say` and `embed` commands require `manage_messages` permission
- Reminder durations are capped at 30 days
- Poll options are capped at 10

## Dashboard Security

### Authentication

- Discord OAuth2 via `django-allauth`
- No local username/password authentication
- OAuth tokens are stored securely in Django's database
- Session-based authentication with HTTP-only cookies

### Authorization

Every dashboard view verifies:
1. User is logged in (`@login_required`)
2. User has Admin or Manage Server permission on the target Discord guild
3. The bot is present in the guild

```python
# Permission check pattern used in all views
guilds = get_user_guilds(request)  # Fetches from Discord API
guild = next((g for g in guilds if str(g['id']) == str(guild_id)), None)
if not guild:
    messages.error(request, "Access denied.")
    return redirect('dashboard')
```

### Django Security Settings (Production)

When `DEBUG=False`, the following protections are automatically enabled:

| Setting | Value | Purpose |
|---------|-------|---------|
| `SECURE_SSL_REDIRECT` | `True` | Force HTTPS |
| `SECURE_HSTS_SECONDS` | `31536000` | HTTP Strict Transport Security (1 year) |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | `True` | HSTS for all subdomains |
| `SECURE_HSTS_PRELOAD` | `True` | Allow HSTS preload list inclusion |
| `SESSION_COOKIE_SECURE` | `True` | Cookies only over HTTPS |
| `CSRF_COOKIE_SECURE` | `True` | CSRF cookie only over HTTPS |
| `SESSION_COOKIE_HTTPONLY` | `True` | No JavaScript access to session cookie |
| `CSRF_COOKIE_HTTPONLY` | `True` | No JavaScript access to CSRF cookie |
| `SECURE_CONTENT_TYPE_NOSNIFF` | `True` | Prevent MIME type sniffing |
| `X_FRAME_OPTIONS` | `DENY` | Prevent clickjacking |

**Location**: `dashboard/dashboard/settings.py`

### CSRF Protection

Django's CSRF middleware is enabled for all form submissions. The dashboard templates include `{% csrf_token %}` in all forms.

### Error Handling

Internal error details are never exposed to users:

```python
# CORRECT
except Exception:
    return JsonResponse({'error': 'An internal error occurred'}, status=500)

# WRONG - exposes stack traces and internal state
except Exception as e:
    return JsonResponse({'error': str(e)}, status=500)
```

## API Security

### Authentication & Permissions

All API endpoints (except health check) require:
1. Session authentication (from Discord OAuth login)
2. `IsGuildAdmin` permission (verifies Discord server admin rights)

### Rate Limiting

Two layers of rate limiting:

1. **Nginx**: Configured in `docker/nginx/nginx.conf`
   - General: 10 requests/second per IP
   - API: 30 requests/minute per IP

2. **Django REST Framework**: Configured in `settings.py`
   - Anonymous: 20 requests/minute
   - Authenticated: 60 requests/minute

### Input Validation

DRF serializers validate all API input:
- String lengths are limited
- Numeric values have min/max bounds
- Required fields are enforced
- Read-only fields cannot be modified via API

### CORS

Cross-Origin Resource Sharing is restricted to configured origins:
```python
CORS_ALLOWED_ORIGINS = os.getenv('CORS_ALLOWED_ORIGINS', '...').split(',')
```

## Database Security

### Parameterized Queries

All user-provided values use parameterized queries (the `?` placeholder):

```python
# CORRECT - parameterized
await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))

# WRONG - string interpolation (SQL injection vulnerable)
await db.execute(f"SELECT * FROM users WHERE user_id = {user_id}")
```

### Column Name Whitelists

Dynamic column names in UPDATE queries are validated against whitelists:

```python
GUILD_CONFIG_COLUMNS = {
    'welcome_channel_id', 'log_channel_id', 'prefix', ...
}

async def update_guild_config(self, guild_id, **kwargs):
    # Reject any column name not in the whitelist
    invalid_keys = set(kwargs.keys()) - self.GUILD_CONFIG_COLUMNS
    if invalid_keys:
        raise ValueError(f"Invalid guild_config columns: {invalid_keys}")
    ...
```

**Affected methods**:
- `Database.update_guild_config()` - `GUILD_CONFIG_COLUMNS` whitelist
- `Database.update_profanity_config()` - `PROFANITY_CONFIG_COLUMNS` whitelist

### No Raw SQL in Django

Dashboard and API use Django ORM exclusively. No raw SQL queries are used in the Django codebase.

## Deployment Security

### Docker

- Non-root users inside containers
- Health checks for all services
- Resource limits (CPU, memory) in production compose
- Internal Docker network (services not exposed directly)
- Nginx reverse proxy for external access

### Nginx

- TLS/HTTPS termination
- Security headers (X-Frame-Options, X-Content-Type-Options, etc.)
- Rate limiting zones
- Gzip compression (with security considerations)
- Static file serving (no Django overhead)

### Environment Variables

- `.env` file is in `.gitignore` (never committed)
- `.env.example` provides the template without real values
- Docker Compose reads from `.env` automatically
- Production secrets should use a secrets manager

## Security Checklist for Contributors

When adding new features or modifying existing code, verify:

### Code
- [ ] No use of `eval()`, `exec()`, or `__import__()`
- [ ] All SQL uses parameterized queries (`?` placeholders)
- [ ] No string formatting/f-strings in SQL queries
- [ ] Command permissions are appropriate (e.g., `has_permissions`)
- [ ] User input is validated before use
- [ ] Error messages don't expose internal state
- [ ] No hardcoded secrets or tokens
- [ ] API endpoints have proper authentication/permissions

### Configuration
- [ ] New secrets are loaded from environment variables
- [ ] New secrets are added to `.env.example` (without real values)
- [ ] DEBUG mode is not enabled in production
- [ ] New API endpoints have rate limiting

### Dependencies
- [ ] New dependencies are from trusted sources
- [ ] Dependencies are pinned to specific versions
- [ ] No known vulnerabilities (check with `pip-audit` or `safety`)

## Reporting Vulnerabilities

If you discover a security vulnerability:

1. **Do NOT** open a public GitHub issue
2. Contact the maintainers privately
3. Provide a detailed description and steps to reproduce
4. Allow reasonable time for a fix before disclosure

We follow responsible disclosure practices and will credit reporters in the changelog.
