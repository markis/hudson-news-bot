#!/bin/bash

# Export environment variables
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUNBUFFERED=1
export UV_CACHE_DIR=/var/cache/uv
export PLAYWRIGHT_BROWSERS_PATH=/opt/playwright

# Source environment variables from /app/.env if it exists
if [ -f /app/.env ]; then
  set -a
  source /app/.env
  set +a
fi

# Log start time
echo "[$(date)] Starting Hudson News Bot run..." >>/var/log/hudson-news-bot.log

# Run the bot
/usr/local/bin/hudson-news-bot --config /app/config/config.toml >>/var/log/hudson-news-bot.log 2>&1

# Log completion
echo "[$(date)] Hudson News Bot run completed" >>/var/log/hudson-news-bot.log
