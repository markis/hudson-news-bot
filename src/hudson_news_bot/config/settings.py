"""Configuration management for the news aggregation bot."""

import copy
import os
import sys
from functools import cached_property
from pathlib import Path
from typing import Any, Final, NotRequired, TypedDict, cast

from hudson_news_bot.utils.toml_handler import TOMLHandler


class NewsConfig(TypedDict):
    """Configuration for news aggregation."""

    max_articles: int
    news_sites: list[str]
    skip_recently_scraped: bool
    scraping_cache_hours: int


class RedditConfig(TypedDict):
    """Configuration for Reddit integration."""

    subreddit: str
    user_agent: str
    check_for_duplicates: bool
    max_search_results: int


class LLMConfig(TypedDict):
    """Configuration for LLM API."""

    model: str
    max_tokens: int
    timeout_seconds: int
    base_url: NotRequired[str]


class DatabaseConfig(TypedDict):
    """Configuration for database."""

    path: str


class ConfigDict(TypedDict):
    """Complete configuration structure."""

    news: NewsConfig
    reddit: RedditConfig
    llm: LLMConfig
    database: DatabaseConfig


DEFAULT_CONFIG: Final[ConfigDict] = {
    "news": {
        "max_articles": 5,
        "news_sites": [
            "https://www.beaconjournal.com/communities/hudsonhubtimes/",
            "https://fox8.com/tag/hudson-news/",
            "https://thesummiteer.org/posts",
            "https://www.news5cleveland.com/news/local-news/oh-summit/",
            "https://www.wkyc.com/section/summit-county",
        ],
        "skip_recently_scraped": True,
        "scraping_cache_hours": 2160,  # 90 days
    },
    "reddit": {
        "subreddit": "news",
        "user_agent": "hudson-news-bot/0.1.0",
        "check_for_duplicates": True,
        "max_search_results": 100,
    },
    "llm": {
        "model": "minimax-m2.5-free",
        "max_tokens": 4096,
        "timeout_seconds": 300,
        "base_url": "https://opencode.ai/zen/v1",
    },
    "database": {"path": "data/submissions.db"},
}


class Config:
    """Configuration management using TOML files and environment variables."""

    _config_path: Final[Path]
    _data: Final[ConfigDict]

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

    def _get_config_data(self, config_path: Path) -> ConfigDict:
        """Load configuration data from the specified TOML file."""
        data = TOMLHandler.load_config(config_path)
        merged_data = deep_merge_dicts(cast(dict[str, Any], DEFAULT_CONFIG), data)
        return cast(ConfigDict, merged_data)

    @cached_property
    def subreddit_name(self) -> str:
        """Get Reddit subreddit name."""
        return str(self._data.get("reddit", {}).get("subreddit", "news"))

    @cached_property
    def max_articles(self) -> int:
        """Get maximum number of articles to aggregate."""
        return int(self._data.get("news", {}).get("max_articles", 5))

    @cached_property
    def reddit_user_agent(self) -> str:
        """Get Reddit API user agent."""
        return str(
            self._data.get("reddit", {}).get("user_agent", "hudson-news-bot/0.1.0")
        )

    @cached_property
    def check_for_duplicates(self) -> bool:
        """Whether to check for duplicate submissions."""
        return bool(self._data.get("reddit", {}).get("check_for_duplicates", True))

    @cached_property
    def max_search_results(self) -> int:
        """Maximum search results for duplicate checking."""
        return int(self._data.get("reddit", {}).get("max_search_results", 100))

    @cached_property
    def llm_model(self) -> str:
        """LLM model name."""
        return str(self._data.get("llm", {}).get("model", "sonar-pro"))

    @cached_property
    def llm_max_tokens(self) -> int:
        """Maximum tokens for LLM response."""
        return int(self._data.get("llm", {}).get("max_tokens", 4096))

    @cached_property
    def llm_timeout_seconds(self) -> int:
        """LLM request timeout in seconds."""
        return int(self._data.get("llm", {}).get("timeout_seconds", 300))

    @cached_property
    def llm_base_url(self) -> str:
        """LLM API base URL."""
        return str(
            self._data.get("llm", {}).get("base_url", "https://api.perplexity.ai")
        )

    @cached_property
    def database_path(self) -> str:
        """Get database path."""
        return str(self._data.get("database", {}).get("path", "data/submissions.db"))

    @cached_property
    def skip_recently_scraped(self) -> bool:
        """Whether to skip recently scraped URLs."""
        return bool(self._data.get("news", {}).get("skip_recently_scraped", True))

    @cached_property
    def scraping_cache_hours(self) -> int:
        """Number of hours to cache scraped URLs."""
        return int(self._data.get("news", {}).get("scraping_cache_hours", 24))

    @cached_property
    def prompts_dir(self) -> Path:
        """Get prompts directory path."""
        # Check for environment variable first (useful for containers)
        prompts_path = os.getenv("PROMPTS_DIR")
        if prompts_path:
            return Path(prompts_path)

        # Try /app/config/prompts (container default)
        container_path = Path("/app/config/prompts")
        if container_path.exists():
            return container_path

        # Fall back to relative path for development
        project_root = Path(__file__).parent.parent.parent.parent
        return project_root / "config" / "prompts"

    @cached_property
    def news_sites(self) -> list[str]:
        """Get list of news sites to scrape."""
        default_sites: list[str] = []
        sites: list[str] = self._data.get("news", {}).get("news_sites", default_sites)
        return sites

    @cached_property
    def perplexity_api_key(self) -> str | None:
        """Get Perplexity API key from environment."""
        return os.getenv("PERPLEXITY_API_KEY")

    @cached_property
    def llm_api_key(self) -> str | None:
        """Get LLM API key from environment (checks both new and old names)."""
        # Check new name first, fall back to old name for backward compatibility
        return os.getenv("LLM_API_KEY") or os.getenv("PERPLEXITY_API_KEY")

    @cached_property
    def reddit_client_id(self) -> str | None:
        """Get Reddit client ID from environment."""
        return os.getenv("REDDIT_CLIENT_ID")

    @cached_property
    def reddit_client_secret(self) -> str | None:
        """Get Reddit client secret from environment."""
        return os.getenv("REDDIT_CLIENT_SECRET")

    @cached_property
    def reddit_username(self) -> str | None:
        """Get Reddit username from environment."""
        return os.getenv("REDDIT_USERNAME")

    @cached_property
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

        # Validate config values
        if self.max_articles <= 0:
            errors.append("max_articles must be greater than 0")

        return len(errors) == 0, errors


def deep_merge_dicts(dict1: dict[str, Any], dict2: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively combine two dictionaries where dict2 overrides values in dict1 for common keys.
    For nested dictionaries, performs a deep merge rather than simple replacement.

    Args:
        dict1 (dict): The base dictionary
        dict2 (dict): The dictionary with overriding values

    Returns:
        dict: A new dictionary with the deeply combined key-value pairs
    """

    result = copy.deepcopy(dict1)  # Create a deep copy to avoid modifying the original

    for key, value in dict2.items():
        # If both values are dictionaries, recursively merge them
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge_dicts(result[key], cast(dict[str, Any], value))
        else:
            # Otherwise just override/add the value
            result[key] = copy.deepcopy(value)
    return result


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
