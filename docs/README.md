# Discord Bot Pro - Documentation

A professional, feature-rich Discord bot with a web dashboard for easy configuration.

## Table of Contents

- [Features](#features)
- [Quick Start](#quick-start)
- [Documentation](#documentation)
- [Architecture](#architecture)
- [Support](#support)

## Features

### Bot Features

- **Moderation Tools**
  - Auto-moderation with profanity filter
  - Warning system with progressive punishments
  - Mute, kick, ban commands
  - Message purge and cleanup

- **Leveling System**
  - XP-based leveling
  - Customizable level roles
  - Leaderboards
  - Level-up announcements

- **Economy System**
  - Virtual currency
  - Daily rewards
  - Shop system
  - User balances

- **Games & Entertainment**
  - Trivia quizzes
  - Polls and voting
  - Dice roller
  - 8-ball

- **Utility Commands**
  - Welcome/goodbye messages
  - Scheduled announcements
  - Reminders
  - Server statistics

- **AI Integration**
  - ChatGPT-powered conversations
  - Code assistance
  - Translation

- **Ticket System**
  - Support ticket creation
  - Staff management
  - Ticket transcripts

### Dashboard Features

- Discord OAuth2 login
- Server selection and management
- Real-time statistics
- Moderation configuration
- Banned words management
- Level roles setup
- User and infraction tracking

## Quick Start

### Prerequisites

- Python 3.10+
- Discord Bot Token
- (Optional) OpenAI API Key for AI features

### Installation

```bash
# Clone the repository
git clone https://github.com/your-repo/discord-bot.git
cd discord-bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your tokens

# Run the bot
python main.py
```

### Docker Installation

```bash
# Development
docker-compose -f docker-compose.dev.yml up --build

# Production
docker-compose -f docker-compose.prod.yml up -d --build
```

## Documentation

| Document | Description |
|----------|-------------|
| [Installation Guide](INSTALLATION.md) | Detailed installation instructions |
| [Configuration](CONFIGURATION.md) | Environment variables and settings |
| [Architecture](ARCHITECTURE.md) | Deep dive into codebase structure, data flow, and design decisions |
| [Security](SECURITY.md) | Security measures, hardening, and contributor security checklist |
| [API Documentation](API.md) | REST API reference with examples |
| [Docker Setup](DOCKER.md) | Container deployment guide |
| [Contributing](CONTRIBUTING.md) | Development workflow, code style, and PR guidelines |

## Architecture

```
discord-bot/
├── main.py              # Bot entry point
├── config.py            # Configuration loader
├── cogs/                # Bot command modules
│   ├── moderation.py
│   ├── leveling.py
│   ├── games.py
│   ├── tickets.py
│   ├── utility.py
│   ├── welcome.py
│   ├── admin.py
│   ├── ai.py
│   ├── scheduler.py
│   ├── reaction_roles.py
│   └── profanity_filter.py
├── utils/
│   └── database.py      # Database operations
├── dashboard/           # Django web dashboard
│   ├── core/           # Main app
│   ├── api/            # REST API
│   └── templates/      # HTML templates
├── docker/             # Docker configurations
├── docs/               # Documentation
└── tests/              # Test suites
```

## Tech Stack

- **Bot**: Discord.py, aiosqlite, APScheduler
- **Dashboard**: Django, django-allauth, Bootstrap 5
- **API**: Django REST Framework, drf-spectacular
- **Database**: SQLite (dev), PostgreSQL (prod)
- **Cache**: Redis
- **Server**: Nginx, Gunicorn

## Support

- [GitHub Issues](https://github.com/your-repo/discord-bot/issues)
- [Discord Server](https://discord.gg/your-server)

## License

MIT License - see [LICENSE](../LICENSE) for details.
