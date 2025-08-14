"""Duplicate detection system for Reddit submissions."""

import hashlib
import sqlite3
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


from hudson_news_bot.config.settings import Config
from hudson_news_bot.news.models import NewsItem
from hudson_news_bot.reddit.client import RedditClient
from hudson_news_bot.utils.logging import get_logger


class DuplicationChecker:
    """Handles duplicate detection for Reddit submissions."""

    def __init__(self, reddit_client: RedditClient, config: Config):
        """Initialize duplication checker.

        Args:
            reddit_client: Reddit API client
            config: Configuration instance
        """
        self.reddit_client = reddit_client
        self.config = config
        self.logger = get_logger("reddit.deduplicator")

        # Set up database
        self.db_path = Path(config.database_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _init_database(self) -> None:
        """Initialize SQLite database for tracking submissions."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Create table for tracking submitted URLs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS submitted_urls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    url_hash TEXT NOT NULL,
                    normalized_url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    title_hash TEXT NOT NULL,
                    submission_id TEXT,
                    submitted_at TIMESTAMP NOT NULL,
                    source TEXT NOT NULL DEFAULT 'local'
                )
            """)

            # Create indexes for performance
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_url_hash ON submitted_urls(url_hash)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_normalized_url ON submitted_urls(normalized_url)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_title_hash ON submitted_urls(title_hash)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_submitted_at ON submitted_urls(submitted_at)"
            )

            conn.commit()
            self.logger.debug("Database initialized successfully")

    def _normalize_url(self, url: str) -> str:
        """Normalize URL for comparison.

        Args:
            url: Original URL

        Returns:
            Normalized URL
        """
        # Parse URL
        parsed = urllib.parse.urlparse(url)

        # Remove common tracking parameters
        query_params = urllib.parse.parse_qs(parsed.query)
        filtered_params = {
            k: v
            for k, v in query_params.items()
            if not k.lower().startswith(("utm_", "fb_", "gclid", "ref_", "campaign"))
        }

        # Rebuild query string
        new_query = urllib.parse.urlencode(filtered_params, doseq=True)

        # Normalize domain (remove www, ensure lowercase)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]

        # Remove trailing slash from path
        path = parsed.path.rstrip("/")
        if not path:
            path = "/"

        # Rebuild URL
        normalized = urllib.parse.urlunparse(
            (
                parsed.scheme.lower(),
                domain,
                path,
                parsed.params,
                new_query,
                "",  # Remove fragment
            )
        )

        return normalized

    def _hash_string(self, text: str) -> str:
        """Create hash of string for comparison.

        Args:
            text: Text to hash

        Returns:
            SHA-256 hash hex string
        """
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _normalize_title(self, title: str) -> str:
        """Normalize title for comparison.

        Args:
            title: Original title

        Returns:
            Normalized title
        """
        # Convert to lowercase and remove extra whitespace
        normalized = " ".join(title.lower().split())

        # Remove common prefixes/suffixes
        prefixes_to_remove = ["breaking:", "update:", "news:", "report:"]
        suffixes_to_remove = [
            "- cnn",
            "| reuters",
            "| ap news",
            "- bbc",
            "- updated",
            "- update",
            "(updated)",
            "(update)",
        ]

        for prefix in prefixes_to_remove:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix) :].strip()

        for suffix in suffixes_to_remove:
            if normalized.endswith(suffix):
                normalized = normalized[: -len(suffix)].strip()

        return normalized

    async def is_duplicate(self, news_item: NewsItem) -> tuple[bool, str | None]:
        """Check if news item is a duplicate.

        Args:
            news_item: News item to check

        Returns:
            Tuple of (is_duplicate, reason)
        """
        if not self.config.check_for_duplicates:
            return False, None

        self.logger.debug(f"Checking duplicates for: {news_item.headline}")

        # Check local database first
        is_dup, reason = self._check_local_database(news_item)
        if is_dup:
            return is_dup, reason

        # Check Reddit submissions
        is_dup, reason = await self._check_reddit_submissions(news_item)
        if is_dup:
            # Store in local database for future reference
            self._store_submission(news_item, source="reddit")
            return is_dup, reason

        return False, None

    def _check_local_database(self, news_item: NewsItem) -> tuple[bool, str | None]:
        """Check local database for duplicates.

        Args:
            news_item: News item to check

        Returns:
            Tuple of (is_duplicate, reason)
        """
        normalized_url = self._normalize_url(news_item.link)
        url_hash = self._hash_string(normalized_url)

        normalized_title = self._normalize_title(news_item.headline)
        title_hash = self._hash_string(normalized_title)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Check for exact URL match
            cursor.execute(
                "SELECT submission_id, submitted_at FROM submitted_urls WHERE url_hash = ?",
                (url_hash,),
            )
            url_match = cursor.fetchone()

            if url_match:
                return (
                    True,
                    f"URL already submitted (ID: {url_match[0]}, Date: {url_match[1]})",
                )

            # Check for title similarity
            cursor.execute(
                "SELECT submission_id, submitted_at, title FROM submitted_urls WHERE title_hash = ?",
                (title_hash,),
            )
            title_match = cursor.fetchone()

            if title_match:
                return (
                    True,
                    f"Similar title already submitted (ID: {title_match[0]}, Date: {title_match[1]})",
                )

        return False, None

    async def _check_reddit_submissions(
        self, news_item: NewsItem
    ) -> tuple[bool, str | None]:
        """Check Reddit for existing submissions.

        Args:
            news_item: News item to check

        Returns:
            Tuple of (is_duplicate, reason)
        """
        # Search by URL domain
        domain = urllib.parse.urlparse(news_item.link).netloc
        search_queries = [
            f"site:{domain}",
            news_item.headline[:50],  # First 50 chars of headline
        ]

        for query in search_queries:
            submissions = await self.reddit_client.search_submissions(
                query, limit=self.config.max_search_results
            )

            for submission in submissions:
                # Check URL similarity
                if self._urls_are_similar(news_item.link, submission.url):
                    return (
                        True,
                        f"Similar URL found: {submission.url} (ID: {submission.id})",
                    )

                # Check title similarity
                if self._titles_are_similar(news_item.headline, submission.title):
                    return (
                        True,
                        f"Similar title found: {submission.title} (ID: {submission.id})",
                    )

                # Check for duplicates using Reddit's built-in feature
                try:
                    for duplicate in submission.duplicates():
                        if self._urls_are_similar(news_item.link, duplicate.url):
                            return (
                                True,
                                f"Duplicate URL found via Reddit API: {duplicate.url} (ID: {duplicate.id})",
                            )
                except Exception as e:
                    self.logger.debug(
                        f"Error checking duplicates for {submission.id}: {e}"
                    )

        return False, None

    def _urls_are_similar(self, url1: str, url2: str) -> bool:
        """Check if two URLs are similar.

        Args:
            url1: First URL
            url2: Second URL

        Returns:
            True if URLs are similar
        """
        norm1 = self._normalize_url(url1)
        norm2 = self._normalize_url(url2)

        return norm1 == norm2

    def _titles_are_similar(self, title1: str, title2: str) -> bool:
        """Check if two titles are similar.

        Args:
            title1: First title
            title2: Second title

        Returns:
            True if titles are similar
        """
        norm1 = self._normalize_title(title1)
        norm2 = self._normalize_title(title2)

        # Exact match
        if norm1 == norm2:
            return True

        # Check if one title contains the other (for different length versions)
        if len(norm1) > 20 and len(norm2) > 20:
            shorter, longer = (
                (norm1, norm2) if len(norm1) < len(norm2) else (norm2, norm1)
            )
            if shorter in longer and len(shorter) / len(longer) > 0.8:
                return True

        return False

    def store_submission(
        self, news_item: NewsItem, submission_id: str | None = None
    ) -> None:
        """Store submission in local database.

        Args:
            news_item: News item that was submitted
            submission_id: Reddit submission ID if available
        """
        self._store_submission(news_item, submission_id, "local")

    def _store_submission(
        self,
        news_item: NewsItem,
        submission_id: str | None = None,
        source: str = "local",
    ) -> None:
        """Store submission in database.

        Args:
            news_item: News item
            submission_id: Reddit submission ID
            source: Source of the submission record
        """
        normalized_url = self._normalize_url(news_item.link)
        url_hash = self._hash_string(normalized_url)

        normalized_title = self._normalize_title(news_item.headline)
        title_hash = self._hash_string(normalized_title)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO submitted_urls 
                (url, url_hash, normalized_url, title, title_hash, submission_id, submitted_at, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    news_item.link,
                    url_hash,
                    normalized_url,
                    news_item.headline,
                    title_hash,
                    submission_id,
                    datetime.now(),
                    source,
                ),
            )

            conn.commit()

        self.logger.debug(f"Stored submission: {news_item.headline}")

    def cleanup_old_records(self, days_to_keep: int = 30) -> int:
        """Clean up old records from database.

        Args:
            days_to_keep: Number of days to keep records

        Returns:
            Number of records deleted
        """
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute(
                "DELETE FROM submitted_urls WHERE submitted_at < ?", (cutoff_date,)
            )

            deleted_count = cursor.rowcount
            conn.commit()

        self.logger.info(f"Cleaned up {deleted_count} old records")
        return deleted_count

    def get_statistics(self) -> dict[str, Any]:
        """Get database statistics.

        Returns:
            Dictionary with statistics
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Total records
            cursor.execute("SELECT COUNT(*) FROM submitted_urls")
            total_records = cursor.fetchone()[0]

            # Records by source
            cursor.execute(
                "SELECT source, COUNT(*) FROM submitted_urls GROUP BY source"
            )
            by_source = dict(cursor.fetchall())

            # Recent records (last 7 days)
            week_ago = datetime.now() - timedelta(days=7)
            cursor.execute(
                "SELECT COUNT(*) FROM submitted_urls WHERE submitted_at > ?",
                (week_ago,),
            )
            recent_records = cursor.fetchone()[0]

        return {
            "total_records": total_records,
            "by_source": by_source,
            "recent_records": recent_records,
            "database_path": str(self.db_path),
        }
