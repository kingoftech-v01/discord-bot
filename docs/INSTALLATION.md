# Installation Guide

This guide covers all installation methods for Discord Bot Pro.

## Table of Contents

- [Requirements](#requirements)
- [Discord Setup](#discord-setup)
- [Local Installation](#local-installation)
- [Docker Installation](#docker-installation)
- [Dashboard Setup](#dashboard-setup)
- [Troubleshooting](#troubleshooting)

## Requirements

### Minimum Requirements

- Python 3.10 or higher
- 512MB RAM
- 1GB disk space

### Recommended for Production

- Python 3.11+
- 2GB RAM
- PostgreSQL 14+
- Redis 7+
- Docker & Docker Compose

## Discord Setup

### 1. Create a Discord Application

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application"
3. Name your application and create it

### 2. Create a Bot

1. Go to the "Bot" section
2. Click "Add Bot"
3. Copy the **Token** (keep it secret!)
4. Enable these Privileged Gateway Intents:
   - Presence Intent
   - Server Members Intent
   - Message Content Intent

### 3. Get Application ID

1. Go to "General Information"
2. Copy the **Application ID**

### 4. OAuth2 Setup (for Dashboard)

1. Go to "OAuth2" section
2. Copy the **Client Secret**
3. Add redirect URL: `http://localhost:8000/accounts/discord/login/callback/`
   (Change domain for production)

### 5. Invite Bot to Server

1. Go to "OAuth2" > "URL Generator"
2. Select scopes: `bot`, `applications.commands`
3. Select permissions:
   - Manage Roles
   - Manage Channels
   - Kick Members
   - Ban Members
   - Manage Messages
   - Read Messages
   - Send Messages
   - Embed Links
   - Attach Files
   - Read Message History
   - Add Reactions
4. Copy and open the generated URL

## Local Installation

### Step 1: Clone Repository

```bash
git clone https://github.com/your-repo/discord-bot.git
cd discord-bot
```

### Step 2: Create Virtual Environment

```bash
# Linux/macOS
python3 -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate
```

### Step 3: Install Dependencies

```bash
# Bot dependencies
pip install -r requirements.txt

# Dashboard dependencies
pip install -r dashboard/requirements.txt
```

### Step 4: Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your values:

```env
DISCORD_TOKEN=your_bot_token
APPLICATION_ID=your_app_id
DISCORD_CLIENT_SECRET=your_client_secret
DJANGO_SECRET_KEY=generate_a_secret_key
```

### Step 5: Initialize Database

```bash
# Bot database is created automatically on first run

# Dashboard migrations
cd dashboard
python manage.py migrate
cd ..
```

### Step 6: Run the Bot

```bash
python main.py
```

### Step 7: Run the Dashboard (Optional)

```bash
cd dashboard
python manage.py runserver
```

Dashboard available at: http://localhost:8000

## Docker Installation

### Development Mode

```bash
# Build and start containers
docker-compose -f docker-compose.dev.yml up --build

# Run in background
docker-compose -f docker-compose.dev.yml up -d --build

# View logs
docker-compose -f docker-compose.dev.yml logs -f

# Stop containers
docker-compose -f docker-compose.dev.yml down
```

### Production Mode

```bash
# Configure environment
cp .env.example .env
# Edit .env with production values

# Build and start
docker-compose -f docker-compose.prod.yml up -d --build

# Run migrations
docker-compose -f docker-compose.prod.yml exec dashboard python manage.py migrate

# Collect static files
docker-compose -f docker-compose.prod.yml exec dashboard python manage.py collectstatic --noinput

# View logs
docker-compose -f docker-compose.prod.yml logs -f
```

## Dashboard Setup

### Local Development

```bash
cd dashboard

# Create Django superuser (optional)
python manage.py createsuperuser

# Run development server
python manage.py runserver
```

### Production with Gunicorn

```bash
cd dashboard
gunicorn --bind 0.0.0.0:8000 --workers 4 dashboard.wsgi:application
```

### Configure Discord OAuth

1. In Discord Developer Portal, add redirect URI:
   - Development: `http://localhost:8000/accounts/discord/login/callback/`
   - Production: `https://your-domain.com/accounts/discord/login/callback/`

2. Make sure `DISCORD_CLIENT_SECRET` is set in `.env`

## Troubleshooting

### Bot won't start

1. Check token is correct in `.env`
2. Verify bot has required intents enabled
3. Check Python version: `python --version`

### Dashboard login fails

1. Verify OAuth redirect URI matches exactly
2. Check `DISCORD_CLIENT_SECRET` is set
3. Ensure bot is in the server

### Database errors

```bash
# Reset bot database
rm data/bot.db
python main.py  # Recreates database

# Reset dashboard database
cd dashboard
rm db.sqlite3
python manage.py migrate
```

### Docker issues

```bash
# Clean rebuild
docker-compose down -v
docker system prune -f
docker-compose up --build
```

### Permission errors

Ensure bot role is above roles it needs to manage in Discord server settings.

## Next Steps

- [Configuration Guide](CONFIGURATION.md) - Customize your bot
- [API Documentation](API.md) - Integrate with external services
- [Docker Guide](DOCKER.md) - Advanced deployment options
