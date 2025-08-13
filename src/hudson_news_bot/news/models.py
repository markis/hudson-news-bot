"""Core data models for news aggregation."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterator

import tomli_w


@dataclass
class NewsItem:
    """Represents a single news article."""

    headline: str
    summary: str
    publication_date: datetime
    link: str

    def to_toml_dict(self) -> dict[str, str]:
        """Convert to dictionary suitable for TOML serialization."""
        return {
            "headline": self.headline,
            "summary": self.summary,
            "publication_date": self.publication_date.strftime("%Y-%m-%d"),
            "link": self.link,
        }


def default_news_list() -> "list[NewsItem]":
    return list()


@dataclass
class NewsCollection:
    """Collection of news items with TOML serialization support."""

    news: list[NewsItem] = field(default_factory=default_news_list)

    def to_toml_string(self) -> str:
        """Convert collection to TOML string format."""
        toml_data = {"news": [item.to_toml_dict() for item in self.news]}
        return tomli_w.dumps(toml_data)

    def __len__(self) -> int:
        """Return number of news items."""
        return len(self.news)

    def __iter__(self) -> Iterator[NewsItem]:
        """Make collection iterable."""
        yield from self.news

    def add_item(self, item: NewsItem) -> None:
        """Add a news item to the collection."""
        self.news.append(item)

    def get_urls(self) -> set[str]:
        """Get all unique URLs from the collection."""
        return {item.link for item in self.news}
