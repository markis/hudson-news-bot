"""Tests for the deduplication functionality in the scraper."""

import pytest
from unittest.mock import patch

from hudson_news_bot.config.settings import Config
from hudson_news_bot.news.scraper import WebsiteScraper


@pytest.fixture
def scraper():
    """Create a scraper instance."""
    config = Config()
    return WebsiteScraper(config)


class TestDeduplication:
    """Test cases for URL and content deduplication."""

    def test_normalize_url_removes_trailing_slash(self, scraper):
        """Test that trailing slashes are removed."""
        assert (
            scraper._normalize_url("https://example.com/article/")
            == "https://example.com/article"
        )
        assert scraper._normalize_url("https://example.com/") == "https://example.com"

    def test_normalize_url_removes_tracking_params(self, scraper):
        """Test that tracking parameters are removed."""
        assert (
            scraper._normalize_url(
                "https://example.com/article?utm_source=twitter&id=123"
            )
            == "https://example.com/article?id=123"
        )

        assert (
            scraper._normalize_url("https://example.com/article?fbclid=abc123")
            == "https://example.com/article"
        )

    def test_normalize_url_removes_fragments(self, scraper):
        """Test that URL fragments are removed."""
        assert (
            scraper._normalize_url("https://example.com/article#section2")
            == "https://example.com/article"
        )

    def test_normalize_url_case_insensitive(self, scraper):
        """Test that URLs are normalized to lowercase."""
        assert (
            scraper._normalize_url("https://EXAMPLE.COM/Article")
            == "https://example.com/article"
        )

    @pytest.mark.asyncio
    async def test_scrape_deduplicates_urls(self, scraper):
        """Test that duplicate URLs are not fetched twice."""
        with patch.object(scraper, "fetch_all_websites") as mock_fetch:
            # Mock main pages with duplicate links
            mock_fetch.side_effect = [
                # Main pages
                {
                    "https://site1.com": """
                    <html>
                        <a href="/2024/01/15/news">Article 1</a>
                        <a href="/2024/01/15/news/">Article 1 with slash</a>
                        <a href="/2024/01/16/other">Article 2</a>
                    </html>
                    """,
                    "https://site2.com": """
                    <html>
                        <a href="https://site1.com/2024/01/15/news?utm_source=rss">Article 1 duplicate</a>
                        <a href="/2024/01/17/unique">Article 3</a>
                    </html>
                    """,
                },
                # Article pages (should only fetch unique ones)
                {
                    "https://site1.com/2024/01/15/news": """
                    <html>
                        <article>
                            <h1>Article 1</h1>
                            <p>Content for article 1.</p>
                        </article>
                    </html>
                    """,
                    "https://site1.com/2024/01/16/other": """
                    <html>
                        <article>
                            <h1>Article 2</h1>
                            <p>Content for article 2.</p>
                        </article>
                    </html>
                    """,
                    "https://site2.com/2024/01/17/unique": """
                    <html>
                        <article>
                            <h1>Article 3</h1>
                            <p>Content for article 3.</p>
                        </article>
                    </html>
                    """,
                },
            ]

            async with scraper:
                await scraper.scrape_news_sites(
                    ["https://site1.com", "https://site2.com"]
                )

            # Should have fetched main pages once
            assert mock_fetch.call_count == 2

            # Second call should only fetch 3 unique articles (not 4)
            second_call_urls = mock_fetch.call_args_list[1][0][0]
            assert len(second_call_urls) == 3

    @pytest.mark.asyncio
    async def test_scrape_deduplicates_headlines(self, scraper):
        """Test that articles with duplicate headlines are filtered."""
        with patch.object(scraper, "fetch_all_websites") as mock_fetch:
            mock_fetch.side_effect = [
                # Main pages
                {
                    "https://site1.com": """
                    <html>
                        <a href="/article/article1">Article 1</a>
                        <a href="/article/article2">Article 2</a>
                    </html>
                    """
                },
                # Article pages with duplicate headline
                {
                    "https://site1.com/article/article1": """
                    <html>
                        <article>
                            <h1>Breaking News</h1>
                            <p>First version of the story.</p>
                        </article>
                    </html>
                    """,
                    "https://site1.com/article/article2": """
                    <html>
                        <article>
                            <h1>BREAKING NEWS</h1>
                            <p>Second version of the story.</p>
                        </article>
                    </html>
                    """,
                },
            ]

            async with scraper:
                articles = await scraper.scrape_news_sites(["https://site1.com"])

            # Should only have one article (duplicate headline filtered)
            assert len(articles) == 1
            assert articles[0]["headline"] in ["Breaking News", "BREAKING NEWS"]

    @pytest.mark.asyncio
    async def test_scrape_deduplicates_content(self, scraper):
        """Test that articles with duplicate content are filtered."""
        with patch.object(scraper, "fetch_all_websites") as mock_fetch:
            mock_fetch.side_effect = [
                # Main pages
                {
                    "https://site1.com": """
                    <html>
                        <a href="/article/article1">Article 1</a>
                        <a href="/article/article2">Article 2</a>
                    </html>
                    """
                },
                # Article pages with different headlines but same content
                {
                    "https://site1.com/article/article1": """
                    <html>
                        <article>
                            <h1>News Update</h1>
                            <p>This is the same story content that appears in both articles.</p>
                        </article>
                    </html>
                    """,
                    "https://site1.com/article/article2": """
                    <html>
                        <article>
                            <h1>Latest Report</h1>
                            <p>This is the same story content that appears in both articles.</p>
                        </article>
                    </html>
                    """,
                },
            ]

            async with scraper:
                articles = await scraper.scrape_news_sites(["https://site1.com"])

            # Should only have one article (duplicate content filtered)
            assert len(articles) == 1
