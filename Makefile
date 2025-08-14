# Hudson News Bot Makefile
# 
# This Makefile provides convenient shortcuts for common development tasks.
# Run 'make help' to see all available commands.

.PHONY: help install install-dev run run-dry run-debug test-connections stats lint format typecheck security test test-cov test-html quality clean

# Default target
help: ## Show this help message
	@echo "Hudson News Bot - Available Commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

# Setup Commands
install: ## Install production dependencies
	uv sync

install-dev: ## Install development dependencies
	uv sync --group dev

# Application Commands
run: ## Run the bot
	uv run python -m hudson_news_bot.main

run-dry: ## Run the bot in dry-run mode (no actual posting)
	uv run python -m hudson_news_bot.main --dry-run --log-level DEBUG

run-debug: ## Run the bot with debug logging
	uv run python -m hudson_news_bot.main --log-level DEBUG

test-connections: ## Test all API connections
	uv run python -m hudson_news_bot.main --test-connections

stats: ## Show bot statistics
	uv run python -m hudson_news_bot.main --stats

# Code Quality Commands
lint: ## Check code with ruff linter
	uv run ruff check

format: ## Format code with ruff
	uv run ruff format

typecheck: ## Run type checking with mypy
	uv run mypy src/

security: ## Run security analysis with bandit
	uv run bandit -r src/

quality: lint typecheck security ## Run all code quality checks

# Testing Commands
test: ## Run tests
	uv run pytest

test-cov: ## Run tests with coverage report
	uv run pytest --cov=hudson_news_bot --cov-report=term-missing

test-html: ## Run tests with HTML coverage report
	uv run pytest --cov=hudson_news_bot --cov-report=html

# Utility Commands
clean: ## Clean up generated files
	rm -rf .coverage htmlcov/ .pytest_cache/ .mypy_cache/ .ruff_cache/
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

# Application shortcuts with common options
run-limited: ## Run bot with max 3 articles
	uv run python -m hudson_news_bot.main --max-articles 3

run-custom-config: ## Run bot with custom config (CONFIG=path/to/config.toml)
	@if [ -z "$(CONFIG)" ]; then echo "Usage: make run-custom-config CONFIG=path/to/config.toml"; exit 1; fi
	uv run python -m hudson_news_bot.main --config $(CONFIG)

run-save-output: ## Run bot and save output (OUTPUT=filename.toml)
	@if [ -z "$(OUTPUT)" ]; then echo "Usage: make run-save-output OUTPUT=filename.toml"; exit 1; fi
	uv run python -m hudson_news_bot.main --output $(OUTPUT)

# Development workflow shortcuts
dev-setup: install-dev ## Complete development setup
	@echo "Development environment ready!"
	@echo "Run 'make quality' to check code quality"
	@echo "Run 'make test-cov' to run tests with coverage"

pre-commit: quality test ## Run all pre-commit checks
	@echo "All pre-commit checks passed!"

# Quick development cycle
dev: format lint test ## Quick development cycle: format, lint, test
	@echo "Development cycle complete!"