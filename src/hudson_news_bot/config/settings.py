"""Configuration management for the news aggregation bot."""

import os
import sys
from pathlib import Path
from typing import Any, Final

from hudson_news_bot.utils.toml_handler import TOMLHandler

DEFAULT_SYSTEM_PROMPT: Final = """
You are a news aggregation bot. Discover 5 current trending news stories from reliable sources. For each story, extract:
- headline (clear, concise)
- summary (2-3 sentences max)
- publication_date (YYYY-MM-DD format)
- link (original source URL)

Format your response as valid TOML using this exact structure:
[[news]]
headline = "story headline"
summary = "brief summary"
publication_date = "2025-08-12"
link = "https://source.com/article"

Only include real, verifiable news from the last 24 hours. Ensure all URLs are accessible.
"""


class Config:
    """Configuration management using TOML files and environment variables."""

    _config_path: Final[Path]
    _data: Final[dict[str, Any]]

    def __init__(
        self,
        config_path: str | Path | None = None,
    ) -> None:
        """Initialize configuration.

        Args:
            config_path: Path to configuration file. Defaults to config/config.toml
        """
        if config_path is None:
            # Default to config/config.toml relative to project root
            project_root = Path(__file__).parent.parent.parent.parent
            config_path = project_root / "config" / "config.toml"

        self._config_path = Path(config_path)
        self._data = self._get_config_data(self._config_path)

    def _get_config_data(self, config_path: Path) -> dict[str, Any]:
        """Load configuration data from the specified TOML file."""
        try:
            return TOMLHandler.load_config(config_path)
        except FileNotFoundError:
            # Create default config if it doesn't exist
            self._create_default_config()
            return TOMLHandler.load_config(config_path)

    def _create_default_config(self) -> None:
        """Create a default configuration file."""
        default_config = {
            "news": {
                "max_articles": 5,
                "system_prompt": DEFAULT_SYSTEM_PROMPT,
            },
            "reddit": {
                "subreddit": "news",
                "user_agent": "hudson-news-bot/0.1.0",
                "check_for_duplicates": True,
                "max_search_results": 100,
            },
            "claude": {
                "max_turns": 3,
                "permission_mode": "readOnly",
                "timeout_seconds": 300,
            },
            "database": {"path": "data/submissions.db"},
        }

        # Ensure config directory exists
        self._config_path.parent.mkdir(parents=True, exist_ok=True)

        import tomli_w

        with open(self._config_path, "wb") as f:
            tomli_w.dump(default_config, f)

    @property
    def subreddit_name(self) -> str:
        """Get Reddit subreddit name."""
        return str(self._data.get("reddit", {}).get("subreddit", "news"))

    @property
    def max_articles(self) -> int:
        """Get maximum number of articles to aggregate."""
        return int(self._data.get("news", {}).get("max_articles", 5))

    @property
    def system_prompt(self) -> str:
        """Get Claude system prompt for news aggregation."""
        return str(self._data.get("news", {}).get("system_prompt", ""))

    @property
    def reddit_user_agent(self) -> str:
        """Get Reddit API user agent."""
        return str(
            self._data.get("reddit", {}).get("user_agent", "hudson-news-bot/0.1.0")
        )

    @property
    def check_for_duplicates(self) -> bool:
        """Whether to check for duplicate submissions."""
        return bool(self._data.get("reddit", {}).get("check_for_duplicates", True))

    @property
    def max_search_results(self) -> int:
        """Maximum search results for duplicate checking."""
        return int(self._data.get("reddit", {}).get("max_search_results", 100))

    @property
    def claude_max_turns(self) -> int:
        """Maximum turns for Claude conversation."""
        return int(self._data.get("claude", {}).get("max_turns", 3))

    @property
    def claude_permission_mode(self) -> str:
        """Claude permission mode."""
        return str(self._data.get("claude", {}).get("permission_mode", "readOnly"))

    @property
    def claude_timeout_seconds(self) -> int:
        """Claude request timeout in seconds."""
        return int(self._data.get("claude", {}).get("timeout_seconds", 300))

    @property
    def database_path(self) -> str:
        """Database path for submission tracking."""
        return str(self._data.get("database", {}).get("path", "data/submissions.db"))

    @property
    def anthropic_api_key(self) -> str | None:
        """Get Anthropic API key from environment."""
        return os.getenv("ANTHROPIC_API_KEY")

    @property
    def reddit_client_id(self) -> str | None:
        """Get Reddit client ID from environment."""
        return os.getenv("REDDIT_CLIENT_ID")

    @property
    def reddit_client_secret(self) -> str | None:
        """Get Reddit client secret from environment."""
        return os.getenv("REDDIT_CLIENT_SECRET")

    @property
    def reddit_username(self) -> str | None:
        """Get Reddit username from environment."""
        return os.getenv("REDDIT_USERNAME")

    @property
    def reddit_password(self) -> str | None:
        """Get Reddit password from environment."""
        return os.getenv("REDDIT_PASSWORD")

    def validate(self) -> tuple[bool, list[str]]:
        """Validate configuration and environment variables.

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors: list[str] = []

        # Check configuration file exists
        if not self._config_path.exists():
            errors.append(f"Configuration file not found: {self._config_path}")

        # Validate required Reddit credentials
        if not self.reddit_client_id:
            errors.append("REDDIT_CLIENT_ID environment variable is required")

        if not self.reddit_client_secret:
            errors.append("REDDIT_CLIENT_SECRET environment variable is required")

        # Check Claude authentication
        if not self.anthropic_api_key:
            # Check if Claude CLI might be logged in (this is harder to verify)
            errors.append(
                "ANTHROPIC_API_KEY not found. Ensure 'claude login' is completed or set API key"
            )

        # Validate config values
        if self.max_articles <= 0:
            errors.append("max_articles must be greater than 0")

        if not self.system_prompt.strip():
            errors.append("system_prompt cannot be empty")

        return len(errors) == 0, errors


def main() -> None:
    """CLI entry point for configuration validation."""
    import argparse

    parser = argparse.ArgumentParser(description="Configuration management")
    parser.add_argument(
        "--validate", action="store_true", help="Validate configuration"
    )
    parser.add_argument("--config", type=str, help="Path to configuration file")

    args = parser.parse_args()

    if args.validate:
        config = Config(args.config)
        is_valid, errors = config.validate()

        if is_valid:
            print("✅ Configuration is valid")
            sys.exit(0)
        else:
            print("❌ Configuration validation failed:")
            for error in errors:
                print(f"  - {error}")
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
