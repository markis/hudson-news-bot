"""Tests for configuration management."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from hudson_news_bot.config.settings import Config


class TestConfig:
    """Test configuration management."""

    def test_config_with_valid_file(self) -> None:
        """Test loading valid configuration file."""
        config_content = """
[news]
max_articles = 10
system_prompt = "Test prompt"

[reddit]
subreddit = "test"
user_agent = "test-bot/1.0"
check_for_duplicates = false
max_search_results = 50

[claude]
max_turns = 5
permission_mode = "readWrite"
timeout_seconds = 600

[database]
path = "test.db"
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(config_content)
            f.flush()

            try:
                config = Config(f.name)

                assert config.max_articles == 10
                assert config.system_prompt == "Test prompt"
                assert config.subreddit_name == "test"
                assert config.reddit_user_agent == "test-bot/1.0"
                assert config.check_for_duplicates is False
                assert config.max_search_results == 50
                assert config.claude_max_turns == 5
                assert config.claude_permission_mode == "readWrite"
                assert config.claude_timeout_seconds == 600
                assert config.database_path == "test.db"
            finally:
                Path(f.name).unlink()

    def test_config_defaults_when_missing_values(self) -> None:
        """Test default values when configuration values are missing."""
        config_content = """
[news]
system_prompt = "Test prompt"
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(config_content)
            f.flush()

            try:
                config = Config(f.name)

                # Test defaults
                assert config.max_articles == 5
                assert config.subreddit_name == "news"
                assert config.reddit_user_agent == "hudson-news-bot/0.1.0"
                assert config.check_for_duplicates is True
                assert config.max_search_results == 100
                assert config.claude_max_turns == 3
                assert config.claude_permission_mode == "plan"
                assert config.claude_timeout_seconds == 300
                assert config.database_path == "data/submissions.db"
            finally:
                Path(f.name).unlink()

    @patch.dict(
        os.environ,
        {
            "REDDIT_CLIENT_ID": "test_client_id",
            "REDDIT_CLIENT_SECRET": "test_client_secret",
            "REDDIT_USERNAME": "test_user",
            "REDDIT_PASSWORD": "test_pass",
            "ANTHROPIC_API_KEY": "test_api_key",
        },
    )
    def test_environment_variables(self) -> None:
        """Test reading environment variables."""
        config_content = """
[news]
system_prompt = "Test prompt"
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(config_content)
            f.flush()

            try:
                config = Config(f.name)

                assert config.reddit_client_id == "test_client_id"
                assert config.reddit_client_secret == "test_client_secret"
                assert config.reddit_username == "test_user"
                assert config.reddit_password == "test_pass"
                assert config.anthropic_api_key == "test_api_key"
            finally:
                Path(f.name).unlink()

    @patch.dict(os.environ, {}, clear=True)
    def test_validation_missing_credentials(self) -> None:
        """Test validation with missing credentials."""
        config_content = """
[news]
max_articles = 5
system_prompt = "Test prompt"
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(config_content)
            f.flush()

            try:
                config = Config(f.name)
                is_valid, errors = config.validate()

                assert not is_valid
                assert any("REDDIT_CLIENT_ID" in error for error in errors)
                assert any("REDDIT_CLIENT_SECRET" in error for error in errors)
            finally:
                Path(f.name).unlink()

    @patch.dict(
        os.environ,
        {
            "REDDIT_CLIENT_ID": "test_client_id",
            "REDDIT_CLIENT_SECRET": "test_client_secret",
            "ANTHROPIC_API_KEY": "test_api_key",
        },
    )
    def test_validation_success(self) -> None:
        """Test successful validation."""
        config_content = """
[news]
max_articles = 5
system_prompt = "Test prompt"
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(config_content)
            f.flush()

            try:
                config = Config(f.name)
                is_valid, errors = config.validate()

                assert is_valid
                assert errors == []
            finally:
                Path(f.name).unlink()

    def test_validation_invalid_values(self) -> None:
        """Test validation with invalid configuration values."""
        config_content = """
[news]
max_articles = 0
system_prompt = ""
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(config_content)
            f.flush()

            try:
                config = Config(f.name)
                is_valid, errors = config.validate()

                assert not is_valid
                assert any(
                    "max_articles must be greater than 0" in error for error in errors
                )
                assert any("system_prompt cannot be empty" in error for error in errors)
            finally:
                Path(f.name).unlink()
