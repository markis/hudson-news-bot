"""Website scraper module using Playwright for JavaScript-rendered content."""

import asyncio
import hashlib
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import Tag
from playwright.async_api import async_playwright, Browser, Playwright
from playwright.async_api import TimeoutError as PlaywrightTimeout

from hudson_news_bot.config.settings import Config
from hudson_news_bot.utils.logging import get_logger


class WebsiteScraper:
    """Downloads and extracts content from news websites using Playwright."""

    def __init__(self, config: Config):
        """Initialize the website scraper.

        Args:
            config: Configuration instance
        """
        self.config = config
        self.logger = get_logger("news.scraper")
        self.browser: Browser | None = None
        self.playwright: Playwright | None = None

        # Set up database for tracking scraped URLs
        self.db_path = Path(config.database_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

        # Cache configuration
        self.skip_recently_scraped = config.skip_recently_scraped
        self.scraping_cache_hours = config.scraping_cache_hours

    def _init_database(self) -> None:
        """Initialize SQLite database for tracking scraped articles."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Create table for tracking scraped articles
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scraped_articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    url_hash TEXT NOT NULL UNIQUE,
                    normalized_url TEXT NOT NULL,
                    headline TEXT,
                    content_hash TEXT,
                    scraped_at TIMESTAMP NOT NULL,
                    scrape_success BOOLEAN DEFAULT 1
                )
            """)

            # Create indexes for performance
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_scraped_url_hash ON scraped_articles(url_hash)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_scraped_at ON scraped_articles(scraped_at)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_scrape_success ON scraped_articles(scrape_success)"
            )

            conn.commit()
            self.logger.debug("Scraping database initialized")

    async def __aenter__(self) -> "WebsiteScraper":
        """Async context manager entry - launch browser."""
        self.playwright = await async_playwright().start()
        if self.playwright:
            self.browser = await self.playwright.chromium.launch(
                headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"]
            )
        self.logger.info("Playwright browser launched")
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit - close browser."""
        if self.browser:
            await self.browser.close()
            self.logger.info("Browser closed")
        if self.playwright:
            await self.playwright.stop()

    async def fetch_website(self, url: str, force: bool = False) -> Tuple[str, str]:
        """Fetch HTML content from a website using Playwright.

        Args:
            url: Website URL to fetch
            force: Force fetching even if recently scraped

        Returns:
            Tuple of (url, html_content)
        """
        if not self.browser:
            raise RuntimeError("Browser not initialized. Use async context manager.")

        # Check if URL was recently scraped (unless force=True)
        if not force and self._check_if_recently_scraped(url):
            self.logger.info(f"Skipping recently scraped URL: {url}")
            return url, ""

        page = None
        try:
            self.logger.debug(f"Fetching {url} with Playwright")
            page = await self.browser.new_page()

            # Set a reasonable viewport and user agent
            await page.set_viewport_size({"width": 1280, "height": 720})
            await page.set_extra_http_headers(
                {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
                }
            )

            # Navigate to the page with timeout
            await page.goto(url, wait_until="networkidle", timeout=30000)

            # Wait a bit for any lazy-loaded content
            await page.wait_for_timeout(2000)

            # Get the page content
            html = await page.content()
            self.logger.info(f"Successfully fetched {url} ({len(html)} bytes)")

            # Store successful fetch (will be updated with content later)
            self._store_scraped_article(url, success=True)

            return url, html

        except PlaywrightTimeout:
            self.logger.error(f"Timeout fetching {url}")
            self._store_scraped_article(url, success=False)
            return url, ""
        except Exception as e:
            self.logger.error(f"Failed to fetch {url}: {e}")
            self._store_scraped_article(url, success=False)
            return url, ""
        finally:
            if page:
                await page.close()

    async def fetch_all_websites(self, urls: List[str]) -> Dict[str, str]:
        """Fetch HTML content from multiple websites concurrently.

        Args:
            urls: List of website URLs to fetch

        Returns:
            Dictionary mapping URL to HTML content
        """
        # Fetch pages with some concurrency limit to avoid overwhelming the browser
        semaphore = asyncio.Semaphore(3)  # Limit to 3 concurrent pages

        async def fetch_with_limit(url: str) -> Tuple[str, str]:
            async with semaphore:
                return await self.fetch_website(url)

        tasks = [fetch_with_limit(url) for url in urls]
        results = await asyncio.gather(*tasks)
        return dict(results)

    def extract_article_links(self, html: str, base_url: str) -> List[str]:
        """Extract article links from HTML content.

        Args:
            html: HTML content
            base_url: Base URL for resolving relative links

        Returns:
            List of absolute article URLs
        """
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        links: set[str] = set()

        # Common patterns for article links
        article_patterns = [
            r"/\d{4}/\d{2}/\d{2}/",  # Date-based URLs (strict format)
            r"/article/",
            r"/story/",
            r"/posts/\d+",  # Post with ID
        ]

        # Patterns to exclude (category/tag pages)
        exclude_patterns = [
            r"/category/",
            r"/tag/",
            r"/page/\d+",
            r"#",
        ]

        for link in soup.find_all("a", href=True):
            if isinstance(link, Tag) and (href := link.get("href", "")):
                href = str(href).strip()
                absolute_url = urljoin(base_url, href)

                # Check if it looks like an article URL and not an excluded pattern
                if any(
                    re.search(pattern, absolute_url.lower())
                    for pattern in article_patterns
                ):
                    if not any(
                        pattern in absolute_url.lower() for pattern in exclude_patterns
                    ):
                        links.add(absolute_url)

        return list(links)

    def extract_article_content(self, html: str, url: str) -> Dict[str, Optional[str]]:
        """Extract article content and metadata from HTML.

        Args:
            html: HTML content
            url: Article URL

        Returns:
            Dictionary with headline, summary, date, and content
        """
        if not html:
            return {"headline": None, "summary": None, "date": None, "content": None}

        soup = BeautifulSoup(html, "html.parser")
        result = {
            "url": url,
            "headline": None,
            "summary": None,
            "date": None,
            "content": None,
        }

        # Extract headline - try multiple selectors
        headline_selectors = [
            "h1.article-title",
            "h1.headline",
            "h1[itemprop='headline']",
            "h1",
            "h2.article-title",
            "title",
        ]
        for selector in headline_selectors:
            element = soup.select_one(selector)
            if element and element.text.strip():
                result["headline"] = element.text.strip()
                break

        # Extract date - look for various date indicators
        date_selectors = [
            "time[datetime]",
            "meta[property='article:published_time']",
            "meta[name='publish_date']",
            "span.date",
            "div.published-date",
        ]

        for selector in date_selectors:
            if selector.startswith("meta"):
                element = soup.select_one(selector)
                if element and hasattr(element, "get"):
                    date_str = element.get("content")
                    if date_str and isinstance(date_str, str):
                        try:
                            result["date"] = datetime.fromisoformat(
                                date_str.replace("Z", "+00:00")
                            ).strftime("%Y-%m-%d")
                            break
                        except Exception:
                            continue
            else:
                element = soup.select_one(selector)
                if element:
                    date_str = (
                        element.get("datetime")
                        if hasattr(element, "get")
                        else element.text
                    )
                    if date_str:
                        try:
                            if "datetime" in selector:
                                result["date"] = datetime.fromisoformat(
                                    str(date_str).replace("Z", "+00:00")
                                ).strftime("%Y-%m-%d")
                            else:
                                # Try to parse text date
                                result["date"] = str(date_str).strip()
                            break
                        except Exception:
                            continue

        # If no structured date found, search in text
        if not result["date"]:
            date_patterns = [
                r"\d{4}-\d{2}-\d{2}",
                r"\d{1,2}/\d{1,2}/\d{4}",
                r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}",
            ]
            text = soup.get_text()
            for pattern in date_patterns:
                match = re.search(pattern, text)
                if match:
                    result["date"] = match.group(0)
                    break

        # Extract article content - try various content selectors
        content_selectors = [
            "article",
            "div.article-content",
            "div.story-content",
            "div.entry-content",
            "main",
            "div[itemprop='articleBody']",
        ]

        for selector in content_selectors:
            element = soup.select_one(selector)
            if element:
                # Remove script and style tags
                for script in element(["script", "style"]):
                    script.decompose()

                paragraphs = element.find_all("p")
                if paragraphs:
                    content = " ".join(
                        p.text.strip() for p in paragraphs[:10] if p.text.strip()
                    )
                    if content:
                        result["content"] = content[:2000]  # Limit content length
                        if len(paragraphs) > 1:
                            result["summary"] = " ".join(
                                p.text.strip() for p in paragraphs[:2] if p.text.strip()
                            )[:300]
                        break

        return result

    async def scrape_news_sites(self, sites: list[str]) -> list[dict[str, str | None]]:
        """Scrape multiple news sites and extract articles with deduplication.

        Args:
            sites: List of news site URLs

        Returns:
            List of unique article dictionaries
        """
        async with self:
            # Fetch all main pages (these are usually index pages, not cached)
            self.logger.info(f"Fetching {len(sites)} news sites...")
            site_content = await self.fetch_all_websites(sites)

            # Track all article URLs to avoid duplicates
            all_article_urls: set[str] = set()
            articles_to_fetch: list[str] = []

            # First pass: collect all unique article URLs
            for site_url, html in site_content.items():
                if not html:
                    continue

                # Extract article links from main page
                article_links = self.extract_article_links(html, site_url)
                self.logger.info(
                    f"Found {len(article_links)} article links on {site_url}"
                )

                # Limit number of articles to fetch per site
                for link in article_links[:5]:
                    # Normalize URL for deduplication
                    normalized_url = self._normalize_url(link)
                    if normalized_url not in all_article_urls:
                        all_article_urls.add(normalized_url)

                        # Check if already scraped recently
                        if not self._check_if_recently_scraped(link):
                            articles_to_fetch.append(link)
                        else:
                            self.logger.debug(f"Skipping recently scraped: {link}")

            self.logger.info(
                f"Found {len(articles_to_fetch)} new article URLs to fetch "
                f"(filtered from {len(all_article_urls)} unique URLs)"
            )

            # Fetch all unique article pages that haven't been scraped recently
            all_articles: list[dict[str, str | None]] = []
            seen_headlines: set[str] = set()
            seen_content_hashes: set[int] = set()

            if articles_to_fetch:
                article_content = await self.fetch_all_websites(articles_to_fetch)

                for article_url, article_html in article_content.items():
                    if article_html:
                        article_data = self.extract_article_content(
                            article_html, article_url
                        )

                        # Skip if missing required data
                        if not (article_data["headline"] and article_data["content"]):
                            # Store failed extraction
                            self._store_scraped_article(
                                article_url,
                                headline=article_data.get("headline"),
                                success=False,
                            )
                            continue

                        # Deduplicate by headline (case-insensitive)
                        headline_normalized = article_data["headline"].lower().strip()
                        if headline_normalized in seen_headlines:
                            self.logger.debug(
                                f"Skipping duplicate headline: {article_data['headline']}"
                            )
                            continue

                        # Deduplicate by content hash (first 500 chars)
                        content_hash = hash(
                            article_data["content"][:500].lower().strip()
                        )
                        if content_hash in seen_content_hashes:
                            self.logger.debug(
                                f"Skipping duplicate content for: {article_data['headline']}"
                            )
                            continue

                        # Add to results and mark as seen
                        seen_headlines.add(headline_normalized)
                        seen_content_hashes.add(content_hash)
                        all_articles.append(article_data)

                        # Update stored article with extracted content
                        self._store_scraped_article(
                            article_url,
                            headline=article_data["headline"],
                            content=article_data["content"],
                            success=True,
                        )

            self.logger.info(
                f"Extracted {len(all_articles)} unique articles after deduplication"
            )

            # Clean up old records periodically (every 10th run roughly)
            import random

            if random.random() < 0.1:
                self.cleanup_old_scraped_records()

            return all_articles

    def _normalize_url(self, url: str) -> str:
        """Normalize URL for deduplication by removing common variations.

        Args:
            url: URL to normalize

        Returns:
            Normalized URL string
        """
        # Remove trailing slashes
        url = url.rstrip("/")

        # Remove common tracking parameters
        if "?" in url:
            base_url, params = url.split("?", 1)
            # Keep only essential parameters (you might want to customize this)
            essential_params: list[str] = []
            for param in params.split("&"):
                if not any(
                    tracking in param.lower()
                    for tracking in ["utm_", "fbclid", "gclid", "ref=", "source="]
                ):
                    essential_params.append(param)
            if essential_params:
                url = f"{base_url}?{'&'.join(essential_params)}"
            else:
                url = base_url

        # Remove fragment identifiers
        if "#" in url:
            url = url.split("#")[0]

        # Convert to lowercase for comparison
        return url.lower()

    def _hash_string(self, text: str) -> str:
        """Create hash of string for comparison.

        Args:
            text: Text to hash

        Returns:
            SHA-256 hash hex string
        """
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _check_if_recently_scraped(self, url: str) -> bool:
        """Check if URL was recently scraped.

        Args:
            url: URL to check

        Returns:
            True if URL was recently scraped and should be skipped
        """
        if not self.skip_recently_scraped:
            return False

        normalized_url = self._normalize_url(url)
        url_hash = self._hash_string(normalized_url)

        # Calculate cutoff time
        cutoff_time = (
            datetime.now() - timedelta(hours=self.scraping_cache_hours)
        ).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT scraped_at, scrape_success 
                FROM scraped_articles 
                WHERE url_hash = ? AND scraped_at > ?
            """,
                (url_hash, cutoff_time),
            )

            result = cursor.fetchone()
            if result:
                self.logger.debug(
                    f"URL recently scraped (at {result[0]}), skipping: {url}"
                )
                return True

        return False

    def _store_scraped_article(
        self,
        url: str,
        headline: Optional[str] = None,
        content: Optional[str] = None,
        success: bool = True,
    ) -> None:
        """Store scraped article in database.

        Args:
            url: Article URL
            headline: Article headline if extracted
            content: Article content if extracted
            success: Whether scraping was successful
        """
        normalized_url = self._normalize_url(url)
        url_hash = self._hash_string(normalized_url)

        content_hash = None
        if content:
            content_hash = self._hash_string(content[:500].lower().strip())

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Use INSERT OR REPLACE to update if URL already exists
            cursor.execute(
                """
                INSERT OR REPLACE INTO scraped_articles
                (url, url_hash, normalized_url, headline, content_hash, scraped_at, scrape_success)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    url,
                    url_hash,
                    normalized_url,
                    headline,
                    content_hash,
                    datetime.now().isoformat(),
                    success,
                ),
            )

            conn.commit()
            self.logger.debug(f"Stored scraped article: {url[:100]}")

    def cleanup_old_scraped_records(self, days_to_keep: int = 7) -> int:
        """Clean up old scraped article records from database.

        Args:
            days_to_keep: Number of days to keep records

        Returns:
            Number of records deleted
        """
        cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM scraped_articles WHERE scraped_at < ?", (cutoff_date,)
            )

            deleted_count = cursor.rowcount
            conn.commit()

        self.logger.info(f"Cleaned up {deleted_count} old scraped article records")
        return deleted_count
