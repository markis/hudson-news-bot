# AGENT.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Hudson News Bot is a Python news aggregation bot that integrates with Reddit using the Claude SDK. It aggregates news articles, provides content summarization, and includes deduplication capabilities to prevent duplicate posts.

## Essential Commands

### Development Setup
```bash
# Install dependencies with development tools
uv sync --group dev

# Install production dependencies only
uv sync
```

### Running the Application
```bash
# Basic run
uv run python -m hudson_news_bot.main

# Common development options
uv run python -m hudson_news_bot.main --dry-run --log-level DEBUG
uv run python -m hudson_news_bot.main --test-connections
uv run python -m hudson_news_bot.main --stats
```

### Code Quality (Required Before Commits)
```bash
# Type checking (strict mode enabled)
uv run mypy src/

# Linting and formatting
uv run ruff check
uv run ruff format

# Security analysis
uv run bandit -r src/

# Testing with coverage
uv run pytest --cov=hudson_news_bot --cov-report=term-missing
```

## Architecture

The codebase follows a modular structure with clear separation of concerns:

- **src/hudson_news_bot/main.py**: Entry point with `NewsBot` orchestrator class
- **news/**: News aggregation using Claude SDK (`NewsAggregator` class)
- **reddit/**: Reddit API interactions (`RedditClient`) and deduplication logic
- **config/**: Configuration management with TOML support
- **utils/**: Shared utilities for logging and TOML handling

Key architectural patterns:
- Async/await for main operations
- Dependency injection via configuration
- CLI interface with comprehensive argument parsing
- Structured logging with configurable levels

## Configuration

- Environment variables documented in `.env.example`
- Reddit API credentials required (client ID/secret)
- Claude authentication via CLI login (preferred) or API key
- Custom configuration files supported via `--config` flag

## Development Standards

- **Python 3.12+** required
- **MyPy strict mode** - all functions must have type hints
- **Ruff** for linting and formatting
- **pytest** with async support for testing
- **Coverage tracking** with HTML reports
- **Security scanning** with bandit

## Testing Strategy

1. Unit tests in `tests/` directory
2. Integration tests via `--dry-run` and `--test-connections`
3. Connection validation for Reddit and Claude APIs
4. Coverage reporting required for all new code
