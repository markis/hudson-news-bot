"""Website scraper module using Playwright for JavaScript-rendered content."""

import asyncio
import hashlib
import json
import logging
import os
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Final, Optional, Tuple, TypedDict
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import Tag
from playwright.async_api import async_playwright, Browser, BrowserContext, Playwright
from playwright.async_api import TimeoutError as PlaywrightTimeout

from hudson_news_bot.config.settings import Config

USER_AGENT: Final = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"


def get_hudson_hub_times_email() -> str | None:
    """Get Hudson Hub Times email from environment."""
    return os.getenv("HUDSON_HUB_TIMES_EMAIL")


def get_hudson_hub_times_password() -> str | None:
    """Get Hudson Hub Times password from environment."""
    return os.getenv("HUDSON_HUB_TIMES_PASSWORD")


class NewsItemDict(TypedDict):
    url: str
    headline: str | None
    date: str | None
    content: str | None
    summary: str | None


class WebsiteScraper:
    """Downloads and extracts content from news websites using Playwright with cookies."""

    def __init__(self, config: Config) -> None:
        """Initialize the enhanced website scraper.

        Args:
            config: Configuration instance
        """
        self.config: Final = config
        self.logger: Final = logging.getLogger(__name__)
        self.browser: Browser | None = None
        self.playwright: Playwright | None = None
        self.browser_context: BrowserContext | None = None

        # Set up database for tracking scraped URLs
        self.db_path: Final = Path(config.database_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

        # Cookie persistence setup
        self.cookies_path: Final = self.db_path.parent / "playwright_cookies.json"

        # Cache configuration
        self.skip_recently_scraped: Final = config.skip_recently_scraped
        self.scraping_cache_hours: Final = config.scraping_cache_hours

        # Authentication credentials
        self.hudson_hub_times_email = get_hudson_hub_times_email()
        self.hudson_hub_times_password = get_hudson_hub_times_password()

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

    async def authenticate_hudson_hub_times(self) -> bool:
        """Authenticate with Hudson Hub Times login.

        Returns:
            True if authentication successful, False otherwise
        """
        if not self.hudson_hub_times_email or not self.hudson_hub_times_password:
            self.logger.warning(
                "Hudson Hub Times credentials not configured, skipping authentication"
            )
            return False

        if not self.browser_context:
            raise RuntimeError("Browser context not initialized")

        self.logger.info("Attempting to authenticate with Hudson Hub Times")

        page = None
        try:
            page = await self.browser_context.new_page()

            # Navigate to the login page
            login_url = "https://login.beaconjournal.com/NABJ-GUP/authenticate/"
            self.logger.debug(f"Navigating to login page: {login_url}")
            await page.goto(login_url, wait_until="domcontentloaded", timeout=30000)

            # Wait for the login form to load
            await page.wait_for_selector("#login-form-email", timeout=10000)

            # Fill in email
            self.logger.debug("Filling email field")
            await page.fill("#login-form-email", self.hudson_hub_times_email)

            # Fill in password
            self.logger.debug("Filling password field")
            await page.fill("#login-form-password", self.hudson_hub_times_password)

            # Wait for submit button to be enabled (JavaScript may disable it initially)
            self.logger.debug("Waiting for submit button to be enabled")
            submit_button_selector = 'button[type="submit"]:not([disabled])'
            try:
                await page.wait_for_selector(submit_button_selector, timeout=10000)
                self.logger.debug("Submit button is now enabled")
            except Exception as e:
                self.logger.warning(
                    f"Submit button may still be disabled, continuing anyway: {e}"
                )

            # Submit the form
            self.logger.debug("Submitting login form")
            await page.click('button[type="submit"]')

            # Wait for navigation or success indicator
            try:
                # Wait for either successful redirect or error message
                await page.wait_for_load_state("domcontentloaded", timeout=15000)

                # Check if we're still on the login page (indicates failure)
                current_url = page.url
                if "authenticate" in current_url.lower():
                    # Look for error messages
                    error_selector = ".validation, .error, .alert"
                    error_elements = await page.query_selector_all(error_selector)
                    if error_elements:
                        error_text = await error_elements[0].text_content()
                        self.logger.error(f"Login failed: {error_text}")
                        return False
                    else:
                        self.logger.warning(
                            "Still on login page, authentication may have failed"
                        )
                        return False
                else:
                    self.logger.info(
                        f"Successfully authenticated with Hudson Hub Times - redirected to: {current_url}"
                    )
                    return True

            except PlaywrightTimeout:
                self.logger.warning("Login process timed out, checking current page")
                current_url = page.url
                if "authenticate" not in current_url.lower():
                    self.logger.info(
                        "Authentication appears successful based on URL change"
                    )
                    return True
                else:
                    self.logger.error("Authentication failed - still on login page")
                    return False

        except Exception as e:
            self.logger.error(f"Error during Hudson Hub Times authentication: {e}")
            return False
        finally:
            if page:
                await page.close()

    async def __aenter__(self) -> "WebsiteScraper":
        """Async context manager entry - launch browser and authenticate."""
        self.playwright = await async_playwright().start()
        if self.playwright:
            self.browser = await self.playwright.chromium.launch(
                headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"]
            )

            # Create a persistent browser context
            self.browser_context = await self.browser.new_context(user_agent=USER_AGENT)

            # Load saved cookies if they exist
            if self.cookies_path.exists():
                try:
                    with open(self.cookies_path, "r") as f:
                        cookies = json.load(f)

                    await self.browser_context.add_cookies(cookies)
                    self.logger.info(
                        f"Loaded {len(cookies)} cookies from previous session"
                    )
                except Exception as e:
                    self.logger.warning(f"Failed to load cookies: {e}")

            # Authenticate with Hudson Hub Times
            await self.authenticate_hudson_hub_times()

        self.logger.info("Playwright browser launched with cookies")
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit - close browser."""
        if self.browser_context:
            # Save cookies before closing context
            try:
                cookies = await self.browser_context.cookies()

                # Save cookies to file if we have any
                if cookies:
                    with open(self.cookies_path, "w") as f:
                        json.dump(cookies, f, indent=2)
                    self.logger.info(f"Saved {len(cookies)} cookies for next session")

            except Exception as e:
                self.logger.warning(f"Failed to save cookies: {e}")

            await self.browser_context.close()

        if self.browser:
            await self.browser.close()
            self.logger.info("Browser closed")
        if self.playwright:
            await self.playwright.stop()

    async def fetch_website(
        self, url: str, force: bool = False, retry_count: int = 0
    ) -> tuple[str, str]:
        """Fetch HTML content from a website using Playwright.

        Args:
            url: Website URL to fetch
            force: Force fetching even if recently scraped
            retry_count: Current retry attempt number

        Returns:
            Tuple of (url, html_content)
        """
        if not self.browser_context:
            raise RuntimeError(
                "Browser context not initialized. Use async context manager."
            )

        # Check if this is a main news site URL (should never be cached)
        is_news_site = self._is_news_site_url(url)

        # Check if URL was recently scraped (unless force=True or it's a news site)
        if not force and not is_news_site and self._check_if_recently_scraped(url):
            self.logger.info(f"Skipping recently scraped URL: {url}")
            return url, ""

        page = None
        try:
            self.logger.debug(
                f"Fetching {url} with Playwright (attempt {retry_count + 1})"
            )
            page = await self.browser_context.new_page()

            # Set a reasonable viewport and user agent
            await page.set_viewport_size({"width": 1280, "height": 720})
            await page.set_extra_http_headers({"User-Agent": USER_AGENT})

            # Navigate to the page with increased timeout
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)

            # Wait for essential content to appear
            try:
                await page.wait_for_selector(
                    "article, main, .article-content, .story-content, h1", timeout=5000
                )
            except PlaywrightTimeout:
                self.logger.debug(
                    f"No content selector found for {url}, continuing anyway"
                )

            # Get the page content
            html = await page.content()
            self.logger.info(f"Successfully fetched {url} ({len(html)} bytes)")

            # Store successful fetch only for article URLs, not news sites
            if not is_news_site:
                self._store_scraped_article(url, success=True)

            return url, html

        except PlaywrightTimeout:
            # Retry for news sites (not article pages) up to 2 times
            if is_news_site and retry_count < 2:
                self.logger.warning(
                    f"Timeout fetching {url}, retrying... (attempt {retry_count + 2}/3)"
                )
                if page:
                    await page.close()
                # Wait a bit before retry
                await asyncio.sleep(2)
                return await self.fetch_website(url, force, retry_count + 1)

            self.logger.error(
                f"Timeout fetching {url} after {retry_count + 1} attempts"
            )
            if not is_news_site:
                self._store_scraped_article(url, success=False)
            return url, ""
        except Exception as e:
            self.logger.error(f"Failed to fetch {url}: {e}")
            if not is_news_site:
                self._store_scraped_article(url, success=False)
            return url, ""
        finally:
            if page:
                await page.close()

    # Copy all the other methods from the original scraper
    async def fetch_all_websites(self, urls: list[str]) -> dict[str, str]:
        """Fetch HTML content from multiple websites concurrently."""
        semaphore = asyncio.Semaphore(2)

        async def fetch_with_limit(url: str) -> Tuple[str, str]:
            async with semaphore:
                return await self.fetch_website(url)

        tasks = [fetch_with_limit(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed_results: list[tuple[str, str]] = []
        for i, result in enumerate(results):
            if isinstance(result, BaseException):
                self.logger.error(f"Error fetching {urls[i]}: {result}")
                processed_results.append((urls[i], ""))
            else:
                processed_results.append(result)

        return dict(processed_results)

    def extract_article_links(self, html: str, base_url: str) -> list[str]:
        """Extract article links from HTML content."""
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        links: set[str] = set()

        article_patterns = [
            r"/\d{4}/\d{2}/\d{2}/",
            r"/article/",
            r"/local-news/",
            r"/news/",
            r"/story/",
            r"/posts/\d+",
        ]

        exclude_patterns = [
            r"/news/national/",
            r"/category/",
            r"/tag/",
            r"/page/\d+",
            r"#",
        ]

        for link in soup.find_all("a", href=True):
            if isinstance(link, Tag) and (href := link.get("href", "")):
                href = str(href).strip()
                absolute_url = urljoin(base_url, href)

                if any(
                    re.search(pattern, absolute_url.lower())
                    for pattern in article_patterns
                ):
                    if not any(
                        pattern in absolute_url.lower() for pattern in exclude_patterns
                    ):
                        links.add(absolute_url)

        return list(links)

    def extract_article_content(self, html: str, url: str) -> NewsItemDict:
        """Extract article content and metadata from HTML."""
        if not html:
            return NewsItemDict(
                url=url, headline=None, date=None, content=None, summary=None
            )

        soup = BeautifulSoup(html, "html.parser")
        result = NewsItemDict(
            url=url, headline=None, date=None, content=None, summary=None
        )

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
                for script in element(["script", "style"]):
                    script.decompose()

                paragraphs = element.find_all("p")
                if paragraphs:
                    content = " ".join(
                        p.text.strip() for p in paragraphs[:10] if p.text.strip()
                    )
                    if content:
                        result["content"] = content[:2000]
                        if len(paragraphs) > 1:
                            result["summary"] = " ".join(
                                p.text.strip() for p in paragraphs[:2] if p.text.strip()
                            )[:300]
                        break

        return result

    async def scrape_news_sites(self, sites: list[str]) -> list[NewsItemDict]:
        """Scrape multiple news sites and extract articles with deduplication."""
        async with self:
            # Fetch all main pages
            self.logger.info(f"Fetching {len(sites)} news sites...")
            site_content = await self.fetch_all_websites(sites)

            # Track all article URLs to avoid duplicates
            all_article_urls: set[str] = set()
            articles_to_fetch: list[str] = []

            # First pass: collect all unique article URLs
            for site_url, html in site_content.items():
                if not html:
                    continue

                article_links = self.extract_article_links(html, site_url)
                self.logger.info(
                    f"Found {len(article_links)} article links on {site_url}"
                )

                for link in article_links:
                    normalized_url = self._normalize_url(link)
                    if normalized_url not in all_article_urls:
                        all_article_urls.add(normalized_url)

                        if not self._check_if_recently_scraped(link):
                            articles_to_fetch.append(link)
                        else:
                            self.logger.debug(f"Skipping recently scraped: {link}")

            self.logger.info(
                f"Found {len(articles_to_fetch)} new article URLs to fetch "
                f"(filtered from {len(all_article_urls)} unique URLs)"
            )

            # Fetch all unique article pages that haven't been scraped recently
            all_articles: list[NewsItemDict] = []
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
                            self._store_scraped_article(
                                article_url,
                                headline=article_data.get("headline"),
                                success=False,
                            )
                            continue

                        # Deduplicate by headline
                        headline_normalized = article_data["headline"].lower().strip()
                        if headline_normalized in seen_headlines:
                            self.logger.debug(
                                f"Skipping duplicate headline: {article_data['headline']}"
                            )
                            continue

                        # Deduplicate by content hash
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

            # Clean up old records periodically
            import random

            if random.random() < 0.1:
                self.cleanup_old_scraped_records()

            return all_articles

    def _is_news_site_url(self, url: str) -> bool:
        """Check if a URL is a main news site URL."""
        normalized_url = self._normalize_url(url)
        return any(
            self._normalize_url(str(news_site)) == normalized_url
            for news_site in getattr(self.config, "news_sites", [])
        )

    def _normalize_url(self, url: str) -> str:
        """Normalize URL for deduplication."""
        url = url.rstrip("/").lower()
        fragment_pos = url.find("#")
        if fragment_pos != -1:
            url = url[:fragment_pos]

        query_pos = url.find("?")
        if query_pos != -1:
            base_url = url[:query_pos]
            params = url[query_pos + 1 :].lower()

            tracking_prefixes = {"utm_", "fbclid", "gclid"}
            tracking_substrings = {"ref=", "source="}

            essential_params = [
                param
                for param in params.split("&")
                if not (
                    any(param.startswith(prefix) for prefix in tracking_prefixes)
                    or any(substring in param for substring in tracking_substrings)
                )
            ]

            if essential_params:
                url = f"{base_url}?{'&'.join(essential_params)}"
            else:
                url = base_url

        return url.lower()

    def _hash_string(self, text: str) -> str:
        """Create hash of string for comparison."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _check_if_recently_scraped(self, url: str) -> bool:
        """Check if URL was recently scraped."""
        if not self.skip_recently_scraped:
            return False

        normalized_url = self._normalize_url(url)
        url_hash = self._hash_string(normalized_url)

        cutoff_time = (
            datetime.now() - timedelta(hours=int(self.scraping_cache_hours))
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
        """Store scraped article in database."""
        normalized_url = self._normalize_url(url)
        url_hash = self._hash_string(normalized_url)

        content_hash = None
        if content:
            content_hash = self._hash_string(content[:500].lower().strip())

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
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
        """Clean up old scraped article records from database."""
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
