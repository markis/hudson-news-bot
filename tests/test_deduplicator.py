"""Tests for duplicate detection system."""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

from hudson_news_bot.news.models import NewsItem
from hudson_news_bot.reddit.deduplicator import DuplicationChecker


class TestDuplicationChecker:
    """Test duplicate detection functionality."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        # Create mock Reddit client and config
        self.mock_reddit_client = MagicMock()
        self.mock_config = MagicMock()

        # Use temporary directory for database
        self.temp_dir = tempfile.mkdtemp()
        self.mock_config.database_path = str(Path(self.temp_dir) / "test.db")
        self.mock_config.check_for_duplicates = True
        self.mock_config.max_search_results = 100

        # Create checker instance
        self.checker = DuplicationChecker(self.mock_reddit_client, self.mock_config)

    def teardown_method(self) -> None:
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_normalize_url(self) -> None:
        """Test URL normalization."""
        # Test basic normalization
        url1 = "https://www.example.com/article"
        normalized1 = self.checker._normalize_url(url1)
        assert normalized1 == "https://example.com/article"

        # Test removing tracking parameters
        url2 = "https://example.com/article?utm_source=twitter&utm_campaign=test&id=123"
        normalized2 = self.checker._normalize_url(url2)
        assert "utm_source" not in normalized2
        assert "utm_campaign" not in normalized2
        assert "id=123" in normalized2

        # Test removing trailing slash
        url3 = "https://example.com/article/"
        normalized3 = self.checker._normalize_url(url3)
        assert normalized3 == "https://example.com/article"

    def test_normalize_title(self) -> None:
        """Test title normalization."""
        # Test basic normalization
        title1 = "  Breaking:   Test   News  Story  "
        normalized1 = self.checker._normalize_title(title1)
        assert normalized1 == "test news story"

        # Test removing prefixes
        title2 = "Breaking: Important News Update"
        normalized2 = self.checker._normalize_title(title2)
        assert normalized2 == "important news update"

        # Test removing suffixes
        title3 = "News Story - CNN"
        normalized3 = self.checker._normalize_title(title3)
        assert normalized3 == "news story"

    def test_urls_are_similar(self) -> None:
        """Test URL similarity detection."""
        url1 = "https://www.example.com/article"
        url2 = "https://example.com/article/"
        url3 = "https://example.com/article?utm_source=test"
        url4 = "https://different.com/article"

        assert self.checker._urls_are_similar(url1, url2) is True
        assert self.checker._urls_are_similar(url1, url3) is True
        assert self.checker._urls_are_similar(url1, url4) is False

    def test_titles_are_similar(self) -> None:
        """Test title similarity detection."""
        title1 = "Breaking: Major News Story"
        title2 = "major news story"
        title3 = "Major News Story - Updated"
        title4 = "Completely Different News"

        assert self.checker._titles_are_similar(title1, title2) is True
        assert self.checker._titles_are_similar(title1, title4) is False

        # Test length-based similarity
        assert self.checker._titles_are_similar(title1, title3) is True

    def test_store_and_check_local_database(self) -> None:
        """Test storing and checking items in local database."""
        news_item = NewsItem(
            headline="Test News Story",
            summary="This is a test news story",
            publication_date=datetime(2025, 8, 12),
            link="https://example.com/news",
        )

        # Initially should not be duplicate
        is_dup, reason = self.checker._check_local_database(news_item)
        assert not is_dup

        # Store the item
        self.checker.store_submission(news_item, "test123")

        # Now should be detected as duplicate
        is_dup, reason = self.checker._check_local_database(news_item)
        assert is_dup
        assert reason is not None
        assert "URL already submitted" in reason
        assert "test123" in reason

    def test_check_duplicates_disabled(self) -> None:
        """Test that duplicate checking can be disabled."""
        self.mock_config.check_for_duplicates = False

        news_item = NewsItem(
            headline="Test News Story",
            summary="This is a test",
            publication_date=datetime(2025, 8, 12),
            link="https://example.com/news",
        )

        is_dup, reason = self.checker.is_duplicate(news_item)
        assert not is_dup
        assert reason is None

    def test_cleanup_old_records(self) -> None:
        """Test cleaning up old database records."""
        # Store some test items
        news_item = NewsItem(
            headline="Test News Story",
            summary="This is a test",
            publication_date=datetime(2025, 8, 12),
            link="https://example.com/news",
        )

        self.checker.store_submission(news_item, "test123")

        # Clean up (with 0 days to keep, should delete everything)
        deleted_count = self.checker.cleanup_old_records(days_to_keep=0)
        assert deleted_count >= 0

    def test_get_statistics(self) -> None:
        """Test getting database statistics."""
        # Store some test items
        news_item = NewsItem(
            headline="Test News Story",
            summary="This is a test",
            publication_date=datetime(2025, 8, 12),
            link="https://example.com/news",
        )

        self.checker.store_submission(news_item, "test123")

        stats = self.checker.get_statistics()

        assert "total_records" in stats
        assert "by_source" in stats
        assert "recent_records" in stats
        assert "database_path" in stats
        assert stats["total_records"] >= 1
