"""Configuration management for the news aggregation bot."""

import copy
import os
import sys
from functools import cached_property
from pathlib import Path
from typing import Any, Final, cast

from hudson_news_bot.utils.toml_handler import TOMLHandler

DEFAULT_SYSTEM_PROMPT: Final = """
You are a news aggregation bot focused exclusively on Hudson, Ohio.
Your job is to find up to real, verifiable local news stories published within the last 24 hours and output them as valid TOML in the exact structure specified below.
You must strictly follow all constraints and output requirements.

Requirements
- Scope: Only include current, trending news about Hudson, Ohio (city, government, schools, roads, events, businesses, public safety, infrastructure). Exclude non-Hudson items.
- Time window: Last 24 hours only. Verify publication dates on-page.
- Fetching:
  1) Use Playwright to fetch the fully rendered page and extract the visible content.
- Verification:
  - Ensure the final URL is directly accessible.
  - Confirm the article is about Hudson, Ohio.
  - Extract a clear headline, a concise 2–3 sentence summary, and the correct publication date in YYYY-MM-DD (convert from local timezone if needed).
- Output:
  - Valid TOML only, no extra commentary.
  - Use exactly this structure for each story:
    [[news]]
    headline = "story headline"
    summary = "brief summary"
    publication_date = "2025-08-12"
    link = "https://source.com/article"
  - If no qualifying articles are found, output exactly:
    [[news]]
- Limits: Up to 5 stories. No duplicates. De-duplicate syndicated/reposted content by choosing the original or most authoritative version.

Process
1) Discover
   - For each listed site, open the homepage or posts list and identify items within the last 24 hours. Prefer items with explicit timestamps and clear Hudson locality.
2) Fetch
   - Fetch each candidate article page with Playwright.
3) Validate
   - Confirm publication date is within the last 24 hours.
   - Confirm explicit Hudson, Ohio relevance (title/body/section tags).
   - Ensure the final URL is publicly accessible without login.
4) Extract
   - headline: from  or on-page headline (h1). Clean site name suffixes.
   - summary: 2–3 sentences capturing the core facts (who/what/where/when). Avoid opinions and boilerplate.
   - publication_date: normalize to YYYY-MM-DD from the page timestamp; if only time is shown, infer date from site timezone (local area).
   - link: canonical article URL.
5) Output
   - Produce only valid TOML with one or more [[news]] tables as specified. No markdown fences, no extra text.

Quality checks before output
- All links load and are not 404/soft paywall blocked.
- Dates are within last 24 hours and in YYYY-MM-DD format.
- No more than 5 items.
- No non-Hudson items.
- TOML parses successfully.

Failure mode
- If no qualifying articles are found after checking all provided sites, output exactly:
```toml
  [[news]]
```
"""
DEFAULT_CONFIG: Final = {
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
        data = TOMLHandler.load_config(config_path)
        return deep_merge_dicts(DEFAULT_CONFIG, data)

    @cached_property
    def subreddit_name(self) -> str:
        """Get Reddit subreddit name."""
        return str(self._data.get("reddit", {}).get("subreddit", "news"))

    @cached_property
    def max_articles(self) -> int:
        """Get maximum number of articles to aggregate."""
        return int(self._data.get("news", {}).get("max_articles", 5))

    @cached_property
    def system_prompt(self) -> str:
        """Get Claude system prompt for news aggregation."""
        return str(self._data.get("news", {}).get("system_prompt", ""))

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
    def claude_max_turns(self) -> int:
        """Maximum turns for Claude conversation."""
        return int(self._data.get("claude", {}).get("max_turns", 3))

    @cached_property
    def claude_permission_mode(self) -> str:
        """Claude permission mode."""
        return str(self._data.get("claude", {}).get("permission_mode", "readOnly"))

    @cached_property
    def claude_timeout_seconds(self) -> int:
        """Claude request timeout in seconds."""
        return int(self._data.get("claude", {}).get("timeout_seconds", 300))

    @cached_property
    def database_path(self) -> str:
        """Database path for submission tracking."""
        return str(self._data.get("database", {}).get("path", "data/submissions.db"))

    @cached_property
    def anthropic_api_key(self) -> str | None:
        """Get Anthropic API key from environment."""
        return os.getenv("ANTHROPIC_API_KEY")

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

        # Check Claude authentication
        # if not self.anthropic_api_key:
        #     # Check if Claude CLI might be logged in (this is harder to verify)
        #     errors.append(
        #         "ANTHROPIC_API_KEY not found. Ensure 'claude login' is completed or set API key"
        #     )

        # Validate config values
        if self.max_articles <= 0:
            errors.append("max_articles must be greater than 0")

        if not self.system_prompt.strip():
            errors.append("system_prompt cannot be empty")

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
