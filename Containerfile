FROM mcr.microsoft.com/playwright/python:v1.54.0-noble

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1 \
  UV_CACHE_DIR=/tmp/uv-cache

# Install system dependencies
RUN apt-get update && apt-get install -y \
  curl \
  nodejs \
  npm \
  && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Create app directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install Python dependencies globally
RUN uv sync --frozen --no-dev

# Install Claude Code SDK CLI (required dependency)
RUN npm install -g @anthropic-ai/claude-code
RUN npm install -g @playwright/mcp@latest

# Install playwright and its dependencies
RUN pip install playwright
RUN playwright install --with-deps --only-shell chromium

# Note: Authentication will be handled at runtime:
# - For Pro/Max users: claude login (preferred)
# - For API users: ANTHROPIC_API_KEY environment variable

# Copy application code
COPY src/ src/
COPY config/ config/

# Install the project globally
RUN uv pip install --system -e .

# Create non-root user
RUN useradd --create-home --shell /bin/bash app \
  && chown -R app:app /app
USER app

RUN claude mcp add playwright mcp-server-playwright -- "--config=/app/config/playwright.json --browser=chromium --executable-path=/opt/microsoft/playwright/chromium-*/chrome-linux/chrome --headless"

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD uv run python -m hudson_news_bot.config.settings --validate || exit 1

# Default command
CMD ["hudson-news-bot"]
