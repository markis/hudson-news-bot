# Hudson News Bot

A Python news aggregation bot that integrates with Reddit using LLM APIs.
The bot aggregates news articles, provides intelligent content summarization,
and includes de-duplication capabilities to prevent duplicate posts.

## Features

- 🔄 **News Aggregation**: Automatically fetches and processes news articles
- 🤖 **LLM Integration**: Uses OpenCode Zen or Perplexity API for intelligent content summarization
- 📱 **Reddit Integration**: Posts content to Reddit with PRAW
- 🚫 **De-duplication**: Prevents duplicate content from being posted
- ⚙️ **Configurable**: Flexible configuration via TOML files and environment variables
- 📊 **Statistics**: Built-in analytics and connection testing
- 🔍 **Dry Run Mode**: Test functionality without actually posting

## Requirements

- Python 3.12+
- Reddit API credentials
- OpenCode Zen API key (or Perplexity API key for backward compatibility)

## Installation

1. **Clone the repository**:

   ```bash
   git clone <repository-url>
   cd hudson-news-bot
   ```

2. **Install dependencies**:

   ```bash
   make install-dev
   ```

3. **Set up environment variables**:

   ```bash
   cp .env.example .env
   # Edit .env with your API credentials
   ```

4. **Configure Reddit API**:
   - Go to <https://www.reddit.com/prefs/apps>
   - Create a new application
   - Add client ID and secret to your `.env` file

5. **Configure LLM API**:
   - Get your API key from [OpenCode Zen](https://opencode.ai/auth)
   - Add it to your `.env` file as `LLM_API_KEY`
   - Or use `PERPLEXITY_API_KEY` for backward compatibility with Perplexity

## Usage

### Quick Start with Make

The project includes a Makefile for streamlined development.
Run `make help` to see all available commands.

```bash
# Setup and run basic development cycle
make install-dev
make run-dry
make quality
make test-cov
```

### Basic Usage

```bash
# Run the bot
make run

# Run in dry-run mode (no actual posting)
make run-dry

# Use custom configuration
make run-custom-config CONFIG=custom_config.toml

# Limit number of articles
make run-limited
```

### Testing and Diagnostics

```bash
# Test all connections
make test-connections

# Show bot statistics
make stats

# Save output to file
make run-save-output OUTPUT=results.toml
```

### Development Commands

```bash
# Run all code quality checks
make quality

# Run tests with coverage
make test-cov

# Generate HTML coverage report
make test-html

# Quick development cycle
make dev

# Pre-commit checks
make pre-commit
```

### Traditional Commands

If you prefer using uv directly:

```bash
# Run the bot
uv run python -m hudson_news_bot.main

# Run tests
uv run pytest

# Type checking
uv run mypy src/

# Linting and formatting
uv run ruff check
uv run ruff format
```

## Configuration

### Environment Variables

Key environment variables (see `.env.example` for complete list):

```bash
# Reddit API
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_client_secret
REDDIT_USERNAME=your_username  # Optional
REDDIT_PASSWORD=your_password  # Optional

# LLM API
LLM_API_KEY=your_api_key  # Get from https://opencode.ai/auth
# Or use PERPLEXITY_API_KEY for backward compatibility
# PERPLEXITY_API_KEY=your_api_key

# Optional settings
LOG_LEVEL=INFO
MAX_ARTICLES=5
SUBREDDIT=news
```

### Custom Configuration

You can override default settings with a TOML configuration file:

```toml
[news]
max_articles = 10
sources = ["example.com", "news.example.org"]

[reddit]
subreddit = "worldnews"
title_template = "Breaking: {title}"

[llm]
model = "claude-haiku-3-5"  # or gpt-5-nano, gemini-3-flash, sonar-pro
base_url = "https://opencode.ai/zen/v1/chat/completions"  # Default for OpenCode Zen

[logging]
level = "DEBUG"
file = "logs/bot.log"
```

### Customizing Prompts

LLM prompts are stored in `config/prompts/` as Jinja2 templates:

- **System Prompt**: `config/prompts/system.jinja`
- **Analysis Prompt**: `config/prompts/analysis.jinja`

Edit these files to customize how the bot analyzes news articles. Changes require restarting the bot.

The analysis prompt supports dynamic variables:
- `{{ today }}` - Current date
- `{{ articles }}` - List of scraped articles
- `{{ flair_options }}` - Available Reddit flairs

Example template syntax:
```jinja
Today is {{ today }}. 
{% for article in articles %}
- {{ article.headline }}
{% endfor %}
```

## Architecture

The project follows a modular architecture:

```text
src/hudson_news_bot/
├── main.py              # Entry point and NewsBot orchestrator
├── config/              # Configuration management
│   ├── __init__.py
│   └── settings.py
├── news/                # News aggregation and LLM integration
│   ├── __init__.py
│   ├── aggregator.py    # NewsAggregator class
│   └── models.py        # Data models
├── reddit/              # Reddit API integration
│   ├── __init__.py
│   ├── client.py        # RedditClient class
│   └── deduplicator.py  # Duplicate detection
└── utils/               # Shared utilities
    ├── __init__.py
    ├── logging.py       # Logging configuration
    └── toml_handler.py  # TOML file handling
```

### Key Components

- **NewsBot**: Main orchestrator that coordinates all components
- **NewsAggregator**: Handles news fetching and LLM API integration (OpenCode Zen or Perplexity)
- **RedditClient**: Manages Reddit API interactions and posting
- **Deduplicator**: Prevents duplicate content using content hashing
- **Config**: Centralized configuration management with TOML support

## Development

### Setting Up Development Environment

```bash
# Install with development dependencies
make install-dev

# Run pre-commit checks
make pre-commit

# Quick development cycle
make dev
```

### Code Quality Standards

- **Type Hints**: Required for all functions (MyPy strict mode)
- **Testing**: pytest with async support and coverage tracking
- **Linting**: Ruff for code formatting and linting
- **Security**: Bandit for security analysis

### Testing

```bash
# Run all tests
make test

# Run with coverage report
make test-cov

# Generate HTML coverage report
make test-html

# Run specific test file (traditional command)
uv run pytest tests/test_deduplicator.py

# Run with verbose output (traditional command)
uv run pytest -v
```

## Troubleshooting

### Common Issues

1. **Reddit API Errors**: Ensure your Reddit app credentials are correct
2. **LLM API Issues**: Verify your API key (`LLM_API_KEY` or `PERPLEXITY_API_KEY`) is correct and has sufficient credits
3. **Connection Failures**: Use `--test-connections` to diagnose network issues
4. **Configuration Problems**: Check your `.env` file and TOML configuration syntax

### Debug Mode

For detailed logging:

```bash
uv run python -m hudson_news_bot.main --log-level DEBUG --log-file debug.log
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run the test suite and code quality checks
5. Submit a pull request

Ensure all code quality checks pass:

```bash
make pre-commit
```

Or run individual checks:

```bash
make quality
make test-cov
```

## License

[Add your license information here]

## Support

For issues and questions:

- Check the troubleshooting section above
- Review the logs with debug mode enabled
- Open an issue on the repository
