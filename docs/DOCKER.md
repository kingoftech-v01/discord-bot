# Docker Deployment Guide

Complete guide for deploying Discord Bot Pro with Docker.

## Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- 2GB RAM minimum
- Domain name (for production)

## Quick Start

### Development

```bash
# Start all services
docker-compose -f docker-compose.dev.yml up --build

# Run in background
docker-compose -f docker-compose.dev.yml up -d --build

# View logs
docker-compose -f docker-compose.dev.yml logs -f bot
docker-compose -f docker-compose.dev.yml logs -f dashboard

# Stop services
docker-compose -f docker-compose.dev.yml down
```

### Production

```bash
# Configure environment
cp .env.example .env
nano .env  # Edit with production values

# Start services
docker-compose -f docker-compose.prod.yml up -d --build

# Run migrations
docker-compose -f docker-compose.prod.yml exec dashboard python manage.py migrate

# Create admin user
docker-compose -f docker-compose.prod.yml exec dashboard python manage.py createsuperuser
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Nginx                                │
│                    (Reverse Proxy)                           │
│                     Port 80/443                              │
└─────────────────┬───────────────────────────────────────────┘
                  │
        ┌─────────┴─────────┐
        │                   │
        ▼                   ▼
┌───────────────┐   ┌───────────────┐
│   Dashboard   │   │    Static     │
│   (Gunicorn)  │   │    Files      │
│   Port 8000   │   │               │
└───────┬───────┘   └───────────────┘
        │
        ├──────────────────┬──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│  PostgreSQL   │  │    Redis      │  │  Discord Bot  │
│   Database    │  │    Cache      │  │               │
│   Port 5432   │  │   Port 6379   │  │               │
└───────────────┘  └───────────────┘  └───────────────┘
```

## Services

### Bot Service

The Discord bot runs as a standalone container:

```yaml
bot:
  build:
    context: .
    dockerfile: docker/bot/Dockerfile
  environment:
    - DISCORD_TOKEN=${DISCORD_TOKEN}
    - DATABASE_URL=postgresql://...
  volumes:
    - bot-data:/app/data
    - bot-logs:/app/logs
```

### Dashboard Service

Django application with Gunicorn:

```yaml
dashboard:
  build:
    context: .
    dockerfile: docker/dashboard/Dockerfile
  environment:
    - DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY}
    - DATABASE_URL=postgresql://...
  volumes:
    - static-files:/app/staticfiles
```

### Database Service

PostgreSQL for production:

```yaml
db:
  image: postgres:15-alpine
  environment:
    - POSTGRES_USER=${POSTGRES_USER}
    - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
    - POSTGRES_DB=${POSTGRES_DB}
  volumes:
    - postgres-data:/var/lib/postgresql/data
```

### Redis Service

Caching and session storage:

```yaml
redis:
  image: redis:7-alpine
  command: redis-server --appendonly yes
  volumes:
    - redis-data:/data
```

### Nginx Service

Reverse proxy for production:

```yaml
nginx:
  build:
    context: ./docker/nginx
  ports:
    - "80:80"
    - "443:443"
  volumes:
    - static-files:/app/staticfiles:ro
```

## Configuration

### Environment Variables

Required for production:

```env
# Discord
DISCORD_TOKEN=your_bot_token
APPLICATION_ID=your_app_id
DISCORD_CLIENT_SECRET=your_secret

# Django
DJANGO_SECRET_KEY=generate_strong_key
DEBUG=False
ALLOWED_HOSTS=your-domain.com

# Database
POSTGRES_USER=discord_bot
POSTGRES_PASSWORD=strong_password_here
POSTGRES_DB=discord_bot

# Docker
COMPOSE_PROJECT_NAME=discord-bot
```

### SSL/HTTPS Setup

1. Obtain SSL certificates (Let's Encrypt recommended):

```bash
# Install certbot
apt install certbot

# Get certificates
certbot certonly --standalone -d your-domain.com
```

2. Copy certificates:

```bash
mkdir -p docker/nginx/ssl
cp /etc/letsencrypt/live/your-domain.com/fullchain.pem docker/nginx/ssl/
cp /etc/letsencrypt/live/your-domain.com/privkey.pem docker/nginx/ssl/
```

3. Update nginx.conf to enable HTTPS (uncomment SSL server block)

### Custom Domain

1. Point your domain to server IP
2. Update `.env`:
   ```env
   ALLOWED_HOSTS=your-domain.com,www.your-domain.com
   DASHBOARD_URL=https://your-domain.com
   ```
3. Update Discord OAuth redirect URL

## Management Commands

### View Logs

```bash
# All services
docker-compose -f docker-compose.prod.yml logs -f

# Specific service
docker-compose -f docker-compose.prod.yml logs -f bot
docker-compose -f docker-compose.prod.yml logs -f dashboard

# Last 100 lines
docker-compose -f docker-compose.prod.yml logs --tail=100 bot
```

### Execute Commands

```bash
# Django management
docker-compose -f docker-compose.prod.yml exec dashboard python manage.py migrate
docker-compose -f docker-compose.prod.yml exec dashboard python manage.py collectstatic
docker-compose -f docker-compose.prod.yml exec dashboard python manage.py createsuperuser

# Database shell
docker-compose -f docker-compose.prod.yml exec db psql -U discord_bot -d discord_bot

# Redis CLI
docker-compose -f docker-compose.prod.yml exec redis redis-cli
```

### Backup & Restore

#### Database Backup

```bash
# Backup
docker-compose -f docker-compose.prod.yml exec db pg_dump -U discord_bot discord_bot > backup.sql

# Restore
docker-compose -f docker-compose.prod.yml exec -T db psql -U discord_bot discord_bot < backup.sql
```

#### Volume Backup

```bash
# Backup all volumes
docker run --rm -v discord-bot_postgres-data:/data -v $(pwd):/backup alpine tar czf /backup/postgres-backup.tar.gz /data
docker run --rm -v discord-bot_redis-data:/data -v $(pwd):/backup alpine tar czf /backup/redis-backup.tar.gz /data
```

### Updates

```bash
# Pull latest code
git pull origin main

# Rebuild and restart
docker-compose -f docker-compose.prod.yml up -d --build

# Run migrations
docker-compose -f docker-compose.prod.yml exec dashboard python manage.py migrate
```

## Scaling

### Horizontal Scaling

For high traffic, scale the dashboard:

```bash
docker-compose -f docker-compose.prod.yml up -d --scale dashboard=3
```

Update nginx.conf for load balancing:

```nginx
upstream dashboard {
    least_conn;
    server dashboard:8000;
    server dashboard:8000;
    server dashboard:8000;
}
```

### Resource Limits

Adjust in docker-compose.prod.yml:

```yaml
deploy:
  resources:
    limits:
      cpus: '1'
      memory: 1G
    reservations:
      cpus: '0.5'
      memory: 512M
```

## Monitoring

### Health Checks

All services include health checks:

```bash
# Check service health
docker-compose -f docker-compose.prod.yml ps

# Detailed health
docker inspect discord-bot-prod --format='{{.State.Health.Status}}'
```

### Resource Usage

```bash
# Live stats
docker stats

# Specific container
docker stats discord-bot-prod discord-dashboard-prod
```

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker-compose -f docker-compose.prod.yml logs bot

# Check configuration
docker-compose -f docker-compose.prod.yml config

# Rebuild from scratch
docker-compose -f docker-compose.prod.yml down -v
docker system prune -f
docker-compose -f docker-compose.prod.yml up --build
```

### Database Connection Issues

```bash
# Check database is running
docker-compose -f docker-compose.prod.yml ps db

# Test connection
docker-compose -f docker-compose.prod.yml exec dashboard python -c "import django; django.setup(); from django.db import connection; connection.ensure_connection(); print('OK')"
```

### Permission Errors

```bash
# Fix volume permissions
docker-compose -f docker-compose.prod.yml exec bot chown -R botuser:botuser /app/data
docker-compose -f docker-compose.prod.yml exec dashboard chown -R dashuser:dashuser /app/staticfiles
```

### Network Issues

```bash
# List networks
docker network ls

# Inspect network
docker network inspect discord-bot_bot-network

# Recreate network
docker-compose -f docker-compose.prod.yml down
docker network rm discord-bot_bot-network
docker-compose -f docker-compose.prod.yml up -d
```
