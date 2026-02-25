"""Core data models for news aggregation."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Iterator

import tomli_w


@dataclass
class NewsItem:
    """Represents a single news article."""

    headline: str
    summary: str
    publication_date: datetime
    link: str
    flair: str | None = None
    flair_id: str | None = None

    def to_toml_dict(self) -> dict[str, str]:
        """Convert to dictionary suitable for TOML serialization."""
        result = {
            "headline": self.headline,
            "summary": self.summary,
            "publication_date": self.publication_date.strftime("%Y-%m-%d"),
            "link": self.link,
        }
        if self.flair:
            result["flair"] = self.flair
        if self.flair_id:
            result["flair_id"] = self.flair_id
        return result


@dataclass
class NewsCollection:
    """Collection of news items with TOML serialization support."""

    news: Final[list[NewsItem]]

    def __init__(self, news: Iterable[NewsItem] | None = None) -> None:
        self.news = list(news) if news is not None else []

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
