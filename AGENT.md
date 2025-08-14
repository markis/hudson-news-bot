# AGENT.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Hudson News Bot is a Python news aggregation bot that integrates with Reddit using the Claude SDK. It aggregates news articles, provides content summarization, and includes deduplication capabilities to prevent duplicate posts.

## Essential Commands

Use the included Makefile for streamlined development. Run `make help` to see all available commands.

### Quick Start
```bash
# Setup development environment
make install-dev

# Run all code quality checks
make quality

# Run tests with coverage
make test-cov

# Complete pre-commit workflow
make pre-commit
```

### Development Setup
```bash
make install-dev    # Install dependencies with development tools
make install        # Install production dependencies only
```

### Running the Application
```bash
make run            # Basic run
make run-dry        # Dry-run with debug logging
make test-connections # Test API connections
make stats          # Show bot statistics
```

### Code Quality (Required Before Commits)
```bash
make quality        # Run all checks: lint, typecheck, security
make lint           # Ruff linting only
make format         # Format code with ruff
make typecheck      # MyPy type checking
make security       # Bandit security analysis
```

### Testing
```bash
make test           # Run tests
make test-cov       # Run tests with coverage report
make test-html      # Generate HTML coverage report
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
