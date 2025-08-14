"""TOML handling utilities."""

import tomllib
from datetime import datetime
from pathlib import Path
from typing import Any


from hudson_news_bot.news.models import NewsCollection, NewsItem


class TOMLHandler:
    """Handles TOML parsing and writing operations."""

    @staticmethod
    def load_config(config_path: str | Path) -> dict[str, Any]:
        """Load configuration from TOML file."""
        config_path = Path(config_path)
        if not config_path.exists():
            return {}

        with open(config_path, "rb") as f:
            return tomllib.load(f)

    @staticmethod
    def parse_news_toml(toml_content: str) -> NewsCollection:
        """Parse TOML content into NewsCollection."""
        try:
            data = tomllib.loads(toml_content)
            news_items: list[NewsItem] = []

            for item_data in data.get("news", []):
                # Parse date
                date_str = item_data.get("publication_date", "")
                try:
                    pub_date = datetime.strptime(date_str, "%Y-%m-%d")
                except ValueError:
                    # Try alternative format or use current date as fallback
                    pub_date = datetime.now()

                news_item = NewsItem(
                    headline=item_data.get("headline", ""),
                    summary=item_data.get("summary", ""),
                    publication_date=pub_date,
                    link=item_data.get("link", ""),
                )
                news_items.append(news_item)

            return NewsCollection(news=news_items)

        except Exception as e:
            raise ValueError(f"Failed to parse TOML content: {e}")

    @staticmethod
    def write_news_toml(
        news_collection: NewsCollection, output_path: str | Path
    ) -> None:
        """Write NewsCollection to TOML file."""
        output_path = Path(output_path)
        toml_content = news_collection.to_toml_string()

        # Ensure directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(toml_content)

    @staticmethod
    def validate_toml_syntax(toml_content: str) -> bool:
        """Validate TOML syntax without full parsing."""
        try:
            tomllib.loads(toml_content)
            return True
        except tomllib.TOMLDecodeError:
            return False
