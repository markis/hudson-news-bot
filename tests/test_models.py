"""Tests for news models."""

from datetime import datetime

from hudson_news_bot.news.models import NewsItem, NewsCollection


class TestNewsItem:
    """Test NewsItem dataclass."""

    def test_news_item_creation(self):
        """Test creating a NewsItem."""
        item = NewsItem(
            headline="Test Headline",
            summary="Test summary content",
            publication_date=datetime(2025, 8, 12),
            link="https://example.com/news",
        )

        assert item.headline == "Test Headline"
        assert item.summary == "Test summary content"
        assert item.publication_date == datetime(2025, 8, 12)
        assert item.link == "https://example.com/news"

    def test_to_toml_dict(self):
        """Test TOML dictionary conversion."""
        item = NewsItem(
            headline="Test Headline",
            summary="Test summary",
            publication_date=datetime(2025, 8, 12),
            link="https://example.com/news",
        )

        toml_dict = item.to_toml_dict()

        assert toml_dict["headline"] == "Test Headline"
        assert toml_dict["summary"] == "Test summary"
        assert toml_dict["publication_date"] == "2025-08-12"
        assert toml_dict["link"] == "https://example.com/news"


class TestNewsCollection:
    """Test NewsCollection dataclass."""

    def test_empty_collection(self):
        """Test empty news collection."""
        collection = NewsCollection(news=[])

        assert len(collection) == 0
        assert list(collection) == []
        assert collection.get_urls() == set()

    def test_collection_with_items(self):
        """Test collection with news items."""
        items = [
            NewsItem(
                "Headline 1",
                "Summary 1",
                datetime(2025, 8, 12),
                "https://example.com/1",
            ),
            NewsItem(
                "Headline 2",
                "Summary 2",
                datetime(2025, 8, 12),
                "https://example.com/2",
            ),
        ]

        collection = NewsCollection(news=items)

        assert len(collection) == 2
        assert list(collection) == items
        assert collection.get_urls() == {
            "https://example.com/1",
            "https://example.com/2",
        }

    def test_add_item(self):
        """Test adding items to collection."""
        collection = NewsCollection(news=[])
        item = NewsItem("Test", "Summary", datetime(2025, 8, 12), "https://example.com")

        collection.add_item(item)

        assert len(collection) == 1
        assert list(collection)[0] == item

    def test_to_toml_string(self):
        """Test TOML string conversion."""
        items = [
            NewsItem(
                "Headline 1",
                "Summary 1",
                datetime(2025, 8, 12),
                "https://example.com/1",
            ),
        ]

        collection = NewsCollection(news=items)
        toml_string = collection.to_toml_string()

        assert 'headline = "Headline 1"' in toml_string
        assert 'summary = "Summary 1"' in toml_string
        assert 'publication_date = "2025-08-12"' in toml_string
        assert 'link = "https://example.com/1"' in toml_string
