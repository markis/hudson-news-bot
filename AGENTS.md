# AGENTS.md

This file provides guidance for AI coding agents working in this repository.

## Project Overview

Hudson News Bot is a Python 3.12+ news aggregation bot that scrapes Hudson, Ohio news sites, uses LLM API (Perplexity) for intelligent content analysis, and posts to Reddit with deduplication. Key technologies: `asyncio`, `asyncpraw`, `playwright`, `openai` (AsyncOpenAI client).

## Build System & Dependencies

- **Package Manager**: `uv` (fast Python package installer)
- **Build Backend**: `hatchling`
- **Python Version**: 3.12+ (specified in `.python-version`)
- **Type Checker**: MyPy (strict mode) + Pyright (strict mode)
- **Linter/Formatter**: Ruff
- **Test Framework**: pytest with pytest-asyncio

## Essential Commands

All commands use the included Makefile. Run `make help` for a complete list.

### Setup & Installation

```bash
make install-dev              # Install all dependencies (dev + prod)
make install                  # Install production dependencies only
make install-playwright       # Install Playwright browsers (required for scraping)
```

### Running Tests

```bash
# Run all tests
make test                     # Basic test run
make test-cov                 # With coverage report (term output)
make test-html                # Generate HTML coverage report

# Run a single test file
uv run pytest tests/test_deduplicator.py

# Run a specific test
uv run pytest tests/test_deduplicator.py::TestDuplicationChecker::test_normalize_url

# Run with verbose output
uv run pytest -v

# Run with debug output
uv run pytest -s

# Run async tests (automatically configured via pytest-asyncio)
uv run pytest tests/test_scraper.py
```

### Code Quality (Required Before Commits)

```bash
make quality                  # Run ALL checks: lint + typecheck + security
make lint                     # Ruff linting only
make format                   # Format code with Ruff
make typecheck                # MyPy type checking
make security                 # Bandit security analysis

# Pre-commit workflow (quality + tests)
make pre-commit               # Runs quality checks AND tests

# Quick dev cycle (format + lint + test)
make dev
```

### Running the Application

```bash
make run                      # Normal execution
make run-dry                  # Dry-run with DEBUG logging (no posting)
make run-debug                # Run with DEBUG logging
make test-connections         # Test Reddit + Perplexity API connections
make stats                    # Display bot statistics
```

## Project Architecture

```
src/hudson_news_bot/
├── main.py                   # Entry point & NewsBot orchestrator
├── config/
│   └── settings.py           # Config management with TOML + env vars
├── news/
│   ├── aggregator.py         # NewsAggregator (Perplexity API integration)
│   ├── models.py             # NewsItem & NewsCollection dataclasses
│   └── scraper.py            # WebsiteScraper (Playwright-based)
├── reddit/
│   ├── client.py             # RedditClient (asyncpraw wrapper)
│   └── deduplicator.py       # DuplicationChecker (SQLite-based)
└── utils/
    ├── logging.py            # Logging setup
    └── toml_handler.py       # TOML parsing/writing utilities
```

**Key Patterns**:
- Async/await throughout (main operations are async)
- Dependency injection via `Config` class
- Dataclasses for models (`@dataclass`)
- Type hints required for all functions (MyPy strict mode)
- Final variables marked with `Final` type annotation

## Code Style Guidelines

### Imports

**Order**: Standard library → Third-party → Local modules (separated by blank lines)

```python
# Standard library (alphabetical)
import asyncio
import logging
from datetime import datetime
from typing import Any, Final

# Third-party packages (alphabetical)
from asyncpraw import Reddit
from openai import AsyncOpenAI

# Local modules (absolute imports, alphabetical)
from hudson_news_bot.config.settings import Config
from hudson_news_bot.news.models import NewsItem
```

**Rules**:
- Always use absolute imports: `from hudson_news_bot.module import Class`
- Never use relative imports: `from ..module import Class` ❌
- Import specific items, not entire modules (except standard library)
- Group and alphabetize within each section

### Formatting

- **Line Length**: 88 characters (Ruff default)
- **Indentation**: 2 spaces (`.editorconfig` standard)
- **Strings**: Double quotes `"` preferred
- **Trailing Commas**: Use in multi-line lists/dicts
- **Docstrings**: Triple double-quotes, Google style

```python
def example_function(param1: str, param2: int) -> bool:
    """Short one-line summary.

    Longer description if needed.

    Args:
        param1: Description of param1
        param2: Description of param2

    Returns:
        Description of return value

    Raises:
        ValueError: When something goes wrong
    """
    pass
```

### Type Hints

**Required for all functions** (MyPy strict mode enforced).

```python
# Good examples
def process_news(items: list[NewsItem]) -> NewsCollection:
    """Process news items."""
    return NewsCollection(items)

async def fetch_data(url: str) -> dict[str, Any]:
    """Fetch data asynchronously."""
    pass

# Modern union syntax (Python 3.10+)
def get_config(path: str | None = None) -> Config:
    """Load config with optional path."""
    pass

# Use Final for constants
from typing import Final

MAX_RETRIES: Final = 3
DEFAULT_TIMEOUT: Final[int] = 30
```

**Common patterns**:
- Use built-in generics: `list[str]`, `dict[str, int]` (not `List`, `Dict`)
- Use `| None` instead of `Optional[...]`
- Mark class-level constants with `Final`
- Use TypedDict for structured dictionaries

### Naming Conventions

- **Classes**: `PascalCase` (e.g., `NewsAggregator`, `RedditClient`)
- **Functions/Methods**: `snake_case` (e.g., `aggregate_news`, `is_duplicate`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `MAX_ARTICLES`, `DEFAULT_CONFIG`)
- **Private methods**: `_leading_underscore` (e.g., `_normalize_url`, `_filter_invalid`)
- **Type aliases**: `PascalCase` (e.g., `NewsConfig`, `ConfigDict`)

### Error Handling

```python
# Log exceptions with context
try:
    result = await some_operation()
except SpecificError as e:
    self.logger.error(f"Operation failed: {e}")
    self.logger.exception("Full error details:")  # Includes traceback
    raise  # Re-raise if caller should handle

# Use descriptive error messages
raise ValueError(f"Invalid configuration: {field} must be positive")

# Validate early, fail fast
if not config.is_valid():
    self.logger.error("Configuration validation failed")
    return False
```

### Async Patterns

```python
# Async function definition
async def fetch_news(url: str) -> dict[str, Any]:
    """Fetch news from URL."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()

# Async iteration
async for item in async_generator():
    process_item(item)

# Async API calls
client = AsyncOpenAI(api_key=api_key, base_url=base_url)
response = await client.chat.completions.create(
    model="model-name",
    messages=[{"role": "user", "content": "prompt"}],
)

# Cleanup in finally blocks
try:
    await bot.run()
finally:
    await bot.cleanup()
```

## Testing Guidelines

- **File naming**: `test_<module>.py` (e.g., `test_deduplicator.py`)
- **Class naming**: `TestClassName` (e.g., `TestDuplicationChecker`)
- **Method naming**: `test_<description>` (e.g., `test_normalize_url`)
- **Fixtures**: Use `setup_method` and `teardown_method` for per-test setup
- **Async tests**: Mark with `@pytest.mark.asyncio`
- **Mocking**: Use `unittest.mock.MagicMock` for dependencies
- **Coverage**: All new code must include tests

```python
class TestMyClass:
    """Test MyClass functionality."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.mock_client = MagicMock()
        self.instance = MyClass(self.mock_client)

    @pytest.mark.asyncio
    async def test_async_method(self) -> None:
        """Test async method."""
        result = await self.instance.async_method()
        assert result is not None
```

## Configuration

- **Environment Variables**: `.env.example` documents all required/optional vars
- **TOML Config**: `config/config.toml` for structured configuration
- **Defaults**: Defined in `config/settings.py` as `DEFAULT_CONFIG`
- **Priority**: CLI args > TOML file > Environment vars > Defaults

## Development Workflow

1. **Before starting**: `make install-dev` (one time setup)
2. **Write code**: Follow type hints, import order, naming conventions
3. **Run tests**: `make test` or `uv run pytest path/to/test_file.py`
4. **Format code**: `make format` (auto-fixes style issues)
5. **Check quality**: `make quality` (lint, typecheck, security)
6. **Pre-commit**: `make pre-commit` (quality + tests)
7. **Commit**: Write clear commit message describing changes

## Common Tasks

**Add a new dependency**:
```bash
# Edit pyproject.toml [project.dependencies] or [dependency-groups.dev]
uv sync --group dev
```

**Debug failing test**:
```bash
uv run pytest tests/test_file.py::test_name -s -v
```

**Type check single file**:
```bash
uv run mypy src/hudson_news_bot/module.py
```

**Security scan**:
```bash
make security  # Excludes B608, B112, B311 by default
```

## Important Notes

- **Never commit** without running `make quality` and `make test`
- **Type hints are mandatory** - code will not pass CI without them
- **Use async/await** for I/O operations (network, file, database)
- **Test connections** with `make test-connections` when working on API integrations
- **Dry-run testing** with `make run-dry` before actual posting
- **Database**: SQLite at `~/.local/share/hudson-news-bot/submissions.db` by default

## Resources

- Makefile: Run `make help` for all available commands
- README.md: User-facing documentation and setup instructions
- .editorconfig: Editor configuration (2-space indentation, LF line endings)
- pyrightconfig.json: Pyright strict mode configuration
- pyproject.toml: Project metadata, dependencies, tool configuration
