# Discord Bot Dockerfile
#
# Builds a minimal container for the Discord bot process.
# Uses Python 3.11-slim as base, installs only required system and Python
# dependencies, and runs the bot as a non-root user for security.
#
# Build context should be the project root (not this directory).
# Usage: docker build -f docker/bot/Dockerfile -t discord-bot .
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Create directories for data and logs
RUN mkdir -p /app/data /app/logs

# Create non-root user for security
RUN useradd -m -u 1000 botuser && \
    chown -R botuser:botuser /app
USER botuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import discord; print('OK')" || exit 1

# Run the bot
CMD ["python", "main.py"]
