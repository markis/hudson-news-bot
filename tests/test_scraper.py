"""Tests for the website scraper module."""

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
    config.skip_recently_scraped = True
    config.scraping_cache_hours = 24
    config.news_sites = ["https://example.com"]
    return config


@pytest.fixture
def scraper(config):
    """Create a scraper instance."""
    return WebsiteScraper(config)


class TestWebsiteScraper:
    """Test cases for WebsiteScraper."""

    def test_extract_article_links(self, scraper):
        """Test extracting article links from HTML."""
        html = """
        <html>
            <a href="/2024/01/15/news-story">News Story</a>
            <a href="/article/breaking-news">Breaking News</a>
            <a href="/about">About Us</a>
            <a href="https://example.com/story/latest">Latest Story</a>
        </html>
        """
        base_url = "https://example.com"

        links = scraper.extract_article_links(html, base_url)

        # Should find 3 links - the ones with article patterns
        assert len(links) == 3
        assert "https://example.com/2024/01/15/news-story" in links
        assert "https://example.com/article/breaking-news" in links
        assert "https://example.com/story/latest" in links

    def test_extract_article_links_empty_html(self, scraper):
        """Test extracting links from empty HTML."""
        links = scraper.extract_article_links("", "https://example.com")
        assert links == []

    def test_extract_article_content(self, scraper):
        """Test extracting article content from HTML."""
        html = """
        <html>
            <head><title>Test Article</title></head>
            <body>
                <article>
                    <h1>Main Headline</h1>
                    <p>First paragraph of content.</p>
                    <p>Second paragraph with more details.</p>
                    <time>2024-01-15</time>
                </article>
            </body>
        </html>
        """
        url = "https://example.com/article"

        content = scraper.extract_article_content(html, url)

        assert content["headline"] == "Main Headline"
        assert "First paragraph" in content["content"]
        assert "Second paragraph" in content["content"]
        assert content["url"] == url

    def test_extract_article_content_empty_html(self, scraper):
        """Test extracting content from empty HTML."""
        content = scraper.extract_article_content("", "https://example.com")
        assert content["headline"] is None
        assert content["content"] is None

    @pytest.mark.asyncio
    async def test_fetch_website_success(self, scraper):
        """Test successful website fetching with Playwright."""
        mock_page = AsyncMock()
        mock_page.content.return_value = "<html>Test HTML</html>"
        mock_page.goto.return_value = None
        mock_page.wait_for_timeout.return_value = None
        mock_page.set_viewport_size.return_value = None
        mock_page.set_extra_http_headers.return_value = None
        mock_page.close.return_value = None

        mock_browser_context = AsyncMock()
        mock_browser_context.new_page.return_value = mock_page

        scraper.browser_context = mock_browser_context

        # Force fetch to bypass cache
        url, html = await scraper.fetch_website("https://example.com", force=True)

        assert url == "https://example.com"
        assert html == "<html>Test HTML</html>"

    @pytest.mark.asyncio
    async def test_fetch_website_failure(self, scraper):
        """Test website fetching with error."""
        mock_browser_context = AsyncMock()
        mock_browser_context.new_page.side_effect = Exception("Browser error")

        scraper.browser_context = mock_browser_context

        url, html = await scraper.fetch_website("https://example.com")

        assert url == "https://example.com"
        assert html == ""

    @pytest.mark.asyncio
    async def test_scrape_news_sites(self, scraper):
        """Test scraping multiple news sites."""
        with patch.object(scraper, "fetch_all_websites") as mock_fetch_all:
            # Mock main page fetch
            mock_fetch_all.side_effect = [
                {
                    "https://example.com": """
                    <html>
                        <a href="/2024/01/15/news">News Article</a>
                    </html>
                    """
                },
                {
                    "https://example.com/2024/01/15/news": """
                    <html>
                        <article>
                            <h1>Test News</h1>
                            <p>News content here.</p>
                        </article>
                    </html>
                    """
                },
            ]

            async with scraper:
                articles = await scraper.scrape_news_sites(["https://example.com"])

            assert len(articles) > 0
            if articles:
                assert articles[0]["headline"] is not None
