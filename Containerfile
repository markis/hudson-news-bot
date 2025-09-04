# syntax=docker/dockerfile:1
FROM ubuntu:24.04

# =============================================================================
# Environment Configuration
# =============================================================================
ENV PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1 \
  UV_FROZEN=true \
  UV_NO_EDITABLE=true \
  UV_NO_MANAGED_PYTHON=true \
  UV_COMPILE_BYTECODE=true \
  UV_SYSTEM_PYTHON=true \
  UV_CACHE_DIR=/var/cache/uv \
  UV_PROJECT_ENVIRONMENT=/usr/ \
  PLAYWRIGHT_BROWSERS_PATH=/opt/playwright \
  HATCH_BUILD_HOOK_ENABLE_MYPYC=1

# =============================================================================
# System Dependencies & Browser Setup
# =============================================================================
RUN apt-get update && apt-get install -y --no-install-recommends \
  curl \
  python3 \
  nodejs \
  npm \
  cron \
  && npm install -g @anthropic-ai/claude-code \
  && rm -rf /var/lib/apt/lists/*

# =============================================================================
# Python Environment Setup
# =============================================================================
WORKDIR /app

# Copy dependency files first for better layer caching
COPY pyproject.toml uv.lock ./

# Copy application code
COPY src/ src/
COPY config/ config/

# Install dependencies using uv with caching
RUN --mount=from=ghcr.io/astral-sh/uv,source=/uv,target=/bin/uv \
  --mount=type=cache,target=/var/cache/uv/ \
  uv sync \
  && playwright install --with-deps --only-shell chromium \
  && rm -rf /var/lib/apt/lists/*

# =============================================================================
# Runtime Scripts & Configuration
# =============================================================================
# Copy shell scripts
COPY scripts/run-hudson-bot.sh /usr/local/bin/run-hudson-bot.sh
COPY scripts/entrypoint.sh /entrypoint.sh

# Setup cron job and logging in a single layer
RUN chmod +x /usr/local/bin/run-hudson-bot.sh /entrypoint.sh \
  && echo "# Hudson News Bot Cron Job" > /etc/cron.d/hudson-news-bot \
  && echo "# Default: Run every 6 hours at minute 0" >> /etc/cron.d/hudson-news-bot \
  && echo "0 */6 * * * root /usr/local/bin/run-hudson-bot.sh" >> /etc/cron.d/hudson-news-bot \
  && echo "# Also run on container startup" >> /etc/cron.d/hudson-news-bot \
  && echo "@reboot root /usr/local/bin/run-hudson-bot.sh" >> /etc/cron.d/hudson-news-bot \
  && chmod 0644 /etc/cron.d/hudson-news-bot \
  && mkdir -p /var/log \
  && touch /var/log/hudson-news-bot.log \
  && chmod 666 /var/log/hudson-news-bot.log

# =============================================================================
# Health Check & Runtime
# =============================================================================
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD service cron status || exit 1

CMD ["/entrypoint.sh"]
