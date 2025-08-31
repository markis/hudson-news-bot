"""Tests for cookie persistence in the website scraper."""

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from hudson_news_bot.config.settings import Config
from hudson_news_bot.news.scraper import WebsiteScraper


@pytest.fixture
def config(tmp_path: Path):
    """Create a test configuration."""
    config = MagicMock(spec=Config)
    config.database_path = str(tmp_path / "test.db")
    config.skip_recently_scraped = False
    config.scraping_cache_hours = 24
    config.news_sites = ["https://example.com"]
    return config


@pytest.fixture
def scraper(config):
    """Create a scraper instance."""
    return WebsiteScraper(config)


class TestCookiePersistence:
    """Test cases for cookie persistence."""

    @pytest.mark.asyncio
    async def test_cookie_save_and_load(self, scraper, tmp_path):
        """Test that cookies are saved and loaded correctly."""
        # Set up mock cookies
        test_cookies = [
            {
                "name": "session_id",
                "value": "test_session_123",
                "domain": "example.com",
                "path": "/",
            },
            {
                "name": "user_pref",
                "value": "dark_mode",
                "domain": "example.com",
                "path": "/",
            },
        ]

        # Mock browser context
        mock_context = AsyncMock()
        mock_context.cookies.return_value = test_cookies
        mock_context.add_cookies.return_value = None
        mock_context.close.return_value = None

        # Mock browser
        mock_browser = AsyncMock()
        mock_browser.new_context.return_value = mock_context
        mock_browser.close.return_value = None

        # Mock playwright
        mock_playwright = AsyncMock()
        mock_playwright.chromium.launch.return_value = mock_browser
        mock_playwright.stop.return_value = None

        scraper.playwright = mock_playwright
        scraper.browser = mock_browser
        scraper.browser_context = mock_context

        # Test saving cookies on exit
        await scraper.__aexit__(None, None, None)

        # Verify cookies were saved
        assert scraper.cookies_path.exists()
        with open(scraper.cookies_path, "r") as f:
            saved_cookies = json.load(f)

        assert len(saved_cookies) == 2
        assert saved_cookies[0]["name"] == "session_id"
        assert saved_cookies[1]["name"] == "user_pref"

    @pytest.mark.asyncio
    async def test_cookie_loading_on_start(self, scraper):
        """Test that cookies are loaded when starting the scraper."""
        # Pre-create cookies file
        test_cookies = [
            {
                "name": "existing_session",
                "value": "existing_value_456",
                "domain": "example.com",
                "path": "/",
            }
        ]

        with open(scraper.cookies_path, "w") as f:
            json.dump(test_cookies, f)

        # Mock browser context
        mock_context = AsyncMock()
        mock_context.add_cookies.return_value = None

        # Mock browser
        mock_browser = AsyncMock()
        mock_browser.new_context.return_value = mock_context

        # Mock playwright
        mock_playwright = AsyncMock()
        mock_playwright.chromium.launch.return_value = mock_browser
        mock_playwright.stop.return_value = None

        # Mock the async_playwright() function
        with patch(
            "hudson_news_bot.news.scraper.async_playwright"
        ) as mock_async_playwright:
            mock_async_playwright_instance = AsyncMock()
            mock_async_playwright_instance.start = AsyncMock(
                return_value=mock_playwright
            )
            mock_async_playwright.return_value = mock_async_playwright_instance

            # Test loading cookies on enter
            await scraper.__aenter__()

            # Verify add_cookies was called with the right cookies
            mock_context.add_cookies.assert_called_once_with(test_cookies)

    @pytest.mark.asyncio
    async def test_cookie_loading_with_missing_file(self, scraper):
        """Test that scraper works normally when cookies file doesn't exist."""
        # Ensure cookies file doesn't exist
        if scraper.cookies_path.exists():
            scraper.cookies_path.unlink()

        # Mock browser context
        mock_context = AsyncMock()
        mock_context.add_cookies.return_value = None

        # Mock browser
        mock_browser = AsyncMock()
        mock_browser.new_context.return_value = mock_context

        # Mock playwright
        mock_playwright = AsyncMock()
        mock_playwright.chromium.launch.return_value = mock_browser

        scraper.playwright = mock_playwright
        scraper.browser = mock_browser

        # Test that it doesn't crash when no cookies file exists
        result = await scraper.__aenter__()

        # Should return the scraper instance
        assert result == scraper
        # add_cookies should not be called
        mock_context.add_cookies.assert_not_called()
