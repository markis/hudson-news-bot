"""Tests for the scraper URL caching functionality."""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hudson_news_bot.config.settings import Config
from hudson_news_bot.news.scraper import WebsiteScraper


@pytest.fixture
def mock_config(tmp_path: Path) -> MagicMock:
    """Create a mock configuration for testing."""
    config = MagicMock(spec=Config)
    config.database_path = str(tmp_path / "test.db")
    config.skip_recently_scraped = True
    config.scraping_cache_hours = 24
    config.news_sites = ["https://example.com"]
    config.max_articles = 5
    return config


@pytest.fixture
def scraper(mock_config: MagicMock) -> WebsiteScraper:
    """Create a WebsiteScraper instance for testing."""
    return WebsiteScraper(mock_config)


class TestScraperCache:
    """Test the scraper URL caching functionality."""

    def test_database_initialization(self, scraper: WebsiteScraper) -> None:
        """Test that the database is properly initialized."""
        # Check that database file exists
        assert scraper.db_path.exists()

        # Check that the scraped_articles table exists
        with sqlite3.connect(scraper.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='scraped_articles'"
            )
            result = cursor.fetchone()
            assert result is not None
            assert result[0] == "scraped_articles"

    def test_store_scraped_article(self, scraper: WebsiteScraper) -> None:
        """Test storing a scraped article."""
        url = "https://example.com/article1"
        headline = "Test Article"
        content = "This is test content for the article."

        scraper._store_scraped_article(url, headline, content, success=True)

        # Verify the article was stored
        with sqlite3.connect(scraper.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM scraped_articles WHERE url = ?", (url,))
            result = cursor.fetchone()

            assert result is not None
            assert result[1] == url  # url
            assert result[4] == headline  # headline
            assert result[7] == 1  # scrape_success

    def test_check_if_recently_scraped(self, scraper: WebsiteScraper) -> None:
        """Test checking if a URL was recently scraped."""
        url = "https://example.com/article2"

        # Initially should not be scraped
        assert not scraper._check_if_recently_scraped(url)

        # Store the article
        scraper._store_scraped_article(url, "Test", "Content", success=True)

        # Now it should be marked as recently scraped
        assert scraper._check_if_recently_scraped(url)

    def test_check_if_recently_scraped_expired(self, scraper: WebsiteScraper) -> None:
        """Test that old scraped URLs are not considered recent."""
        url = "https://example.com/article3"

        # Store article with old timestamp
        old_time = (datetime.now() - timedelta(hours=25)).isoformat()

        with sqlite3.connect(scraper.db_path) as conn:
            cursor = conn.cursor()
            normalized_url = scraper._normalize_url(url)
            url_hash = scraper._hash_string(normalized_url)

            cursor.execute(
                """
                INSERT INTO scraped_articles
                (url, url_hash, normalized_url, headline, content_hash, scraped_at, scrape_success)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (url, url_hash, normalized_url, "Old Article", None, old_time, 1),
            )
            conn.commit()

        # Should not be considered recently scraped (older than 24 hours)
        assert not scraper._check_if_recently_scraped(url)

    def test_skip_recently_scraped_disabled(self, mock_config: MagicMock) -> None:
        """Test that URL checking can be disabled."""
        mock_config.skip_recently_scraped = False
        scraper = WebsiteScraper(mock_config)

        url = "https://example.com/article4"
        scraper._store_scraped_article(url, "Test", "Content", success=True)

        # Should return False even though article was just scraped
        assert not scraper._check_if_recently_scraped(url)

    def test_normalize_url(self, scraper: WebsiteScraper) -> None:
        """Test URL normalization."""
        # Test removing tracking parameters
        url1 = "https://example.com/article?utm_source=test&id=123"
        normalized1 = scraper._normalize_url(url1)
        assert "utm_source" not in normalized1
        assert "id=123" in normalized1

        # Test removing trailing slashes
        url2 = "https://example.com/article/"
        normalized2 = scraper._normalize_url(url2)
        assert not normalized2.endswith("/")

        # Test removing fragments
        url3 = "https://example.com/article#section"
        normalized3 = scraper._normalize_url(url3)
        assert "#" not in normalized3

        # Test case normalization
        url4 = "HTTPS://EXAMPLE.COM/Article"
        normalized4 = scraper._normalize_url(url4)
        assert normalized4 == normalized4.lower()

    def test_cleanup_old_scraped_records(self, scraper: WebsiteScraper) -> None:
        """Test cleanup of old scraped records."""
        # Insert some old and new records
        with sqlite3.connect(scraper.db_path) as conn:
            cursor = conn.cursor()

            # Old record (10 days ago)
            old_time = (datetime.now() - timedelta(days=10)).isoformat()
            cursor.execute(
                """
                INSERT INTO scraped_articles
                (url, url_hash, normalized_url, scraped_at, scrape_success)
                VALUES (?, ?, ?, ?, ?)
            """,
                ("https://example.com/old", "hash1", "normalized1", old_time, 1),
            )

            # Recent record (1 day ago)
            recent_time = (datetime.now() - timedelta(days=1)).isoformat()
            cursor.execute(
                """
                INSERT INTO scraped_articles
                (url, url_hash, normalized_url, scraped_at, scrape_success)
                VALUES (?, ?, ?, ?, ?)
            """,
                ("https://example.com/new", "hash2", "normalized2", recent_time, 1),
            )

            conn.commit()

        # Run cleanup (keep 7 days)
        deleted_count = scraper.cleanup_old_scraped_records(days_to_keep=7)

        assert deleted_count == 1  # Should delete only the old record

        # Verify correct record was deleted
        with sqlite3.connect(scraper.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT url FROM scraped_articles")
            remaining = cursor.fetchall()

            assert len(remaining) == 1
            assert remaining[0][0] == "https://example.com/new"

    @pytest.mark.asyncio
    async def test_fetch_website_with_cache(self, scraper: WebsiteScraper) -> None:
        """Test that fetch_website respects the cache."""
        url = "https://example.com/cached-article"

        # Store as recently scraped
        scraper._store_scraped_article(url, "Cached", "Content", success=True)

        # Mock browser context
        mock_context = AsyncMock()
        scraper.browser_context = mock_context

        # Should return empty content due to cache
        result_url, html = await scraper.fetch_website(url)

        assert result_url == url
        assert html == ""  # Empty because it was skipped

        # With force=True, should attempt to fetch
        with patch.object(scraper, "browser_context") as mock_browser_context:
            mock_page = AsyncMock()
            mock_page.content = AsyncMock(return_value="<html>New content</html>")
            mock_page.set_viewport_size = AsyncMock()
            mock_page.set_extra_http_headers = AsyncMock()
            mock_page.goto = AsyncMock()
            mock_page.wait_for_timeout = AsyncMock()
            mock_page.close = AsyncMock()
            mock_browser_context.new_page = AsyncMock(return_value=mock_page)

            result_url, html = await scraper.fetch_website(url, force=True)

            assert result_url == url
            # Should have fetched new content
            assert html == "<html>New content</html>"

    def test_hash_string(self, scraper: WebsiteScraper) -> None:
        """Test string hashing."""
        text = "test content"
        hash1 = scraper._hash_string(text)
        hash2 = scraper._hash_string(text)

        # Same input should produce same hash
        assert hash1 == hash2

        # Different input should produce different hash
        hash3 = scraper._hash_string("different content")
        assert hash1 != hash3

        # Hash should be 64 characters (SHA-256 hex)
        assert len(hash1) == 64
