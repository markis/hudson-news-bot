FROM mcr.microsoft.com/playwright/python:v1.54.0-noble

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1 \
  UV_CACHE_DIR=/tmp/uv-cache

# Install system dependencies including cron
RUN apt-get update && apt-get install -y \
  curl \
  nodejs \
  npm \
  cron \
  && rm -rf /var/lib/apt/lists/*

# Note: Authentication will be handled at runtime:
# - For Pro/Max users: claude login (preferred)
# - For API users: ANTHROPIC_API_KEY environment variable
# Install Claude Code SDK CLI (required dependency)
RUN npm install -g @anthropic-ai/claude-code

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Create app directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Copy application code first
COPY src/ src/
COPY config/ config/

# Install the project and its dependencies globally using system Python
RUN uv pip install --system -e .

# Install shell only chromium for Playwright
RUN playwright install --with-deps --only-shell chromium

# Create cron job script
RUN echo '#!/bin/bash\n\
  export PYTHONDONTWRITEBYTECODE=1\n\
  export PYTHONUNBUFFERED=1\n\
  export UV_CACHE_DIR=/tmp/uv-cache\n\
  # Source environment variables from /app/.env if it exists\n\
  if [ -f /app/.env ]; then\n\
  set -a\n\
  source /app/.env\n\
  set +a\n\
  fi\n\
  # Log start time\n\
  echo "[$(date)] Starting Hudson News Bot run..." >> /var/log/hudson-news-bot.log\n\
  # Run the bot\n\
  /usr/local/bin/hudson-news-bot >> /var/log/hudson-news-bot.log 2>&1\n\
  echo "[$(date)] Hudson News Bot run completed" >> /var/log/hudson-news-bot.log\n' > /usr/local/bin/run-hudson-bot.sh \
  && chmod +x /usr/local/bin/run-hudson-bot.sh

# Setup cron job (runs every 6 hours by default)
# The cron schedule can be overridden at runtime
RUN echo "# Hudson News Bot Cron Job\n\
  # Default: Run every 6 hours at minute 0\n\
  0 */6 * * * root /usr/local/bin/run-hudson-bot.sh\n\
  # Also run on container startup\n\
  @reboot root /usr/local/bin/run-hudson-bot.sh\n" > /etc/cron.d/hudson-news-bot \
  && chmod 0644 /etc/cron.d/hudson-news-bot

# Create log file and directory with proper permissions
RUN mkdir -p /var/log \
  && touch /var/log/hudson-news-bot.log \
  && chmod 666 /var/log/hudson-news-bot.log

# Health check - verify cron is running
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD service cron status || exit 1

# Create entrypoint script to handle environment variables and start cron
RUN echo '#!/bin/bash\n\
  # If CRON_SCHEDULE is set, update the cron job\n\
  if [ ! -z "$CRON_SCHEDULE" ]; then\n\
  echo "# Hudson News Bot Cron Job (Custom Schedule)" > /etc/cron.d/hudson-news-bot\n\
  echo "$CRON_SCHEDULE root /usr/local/bin/run-hudson-bot.sh" >> /etc/cron.d/hudson-news-bot\n\
  echo "@reboot root /usr/local/bin/run-hudson-bot.sh" >> /etc/cron.d/hudson-news-bot\n\
  fi\n\
  # Start cron service\n\
  service cron start\n\
  # Run once on startup\n\
  /usr/local/bin/run-hudson-bot.sh\n\
  # Tail the log file to keep container running\n\
  tail -f /var/log/hudson-news-bot.log\n' > /entrypoint.sh \
  && chmod +x /entrypoint.sh

# Default command - run the entrypoint script
CMD ["/entrypoint.sh"]
