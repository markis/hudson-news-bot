"""Reddit API client using PRAW."""

import sys
import time
from typing import Any, List, Optional

import praw  # type: ignore
from praw.exceptions import RedditAPIException, PRAWException  # type: ignore
from praw.models import Submission  # type: ignore

from hudson_news_bot.config.settings import Config
from hudson_news_bot.news.models import NewsItem
from hudson_news_bot.utils.logging import get_logger


class RedditClient:
    """Reddit API client for posting news articles."""

    def __init__(self, config: Config):
        """Initialize Reddit client.

        Args:
            config: Configuration instance
        """
        self.config = config
        self.logger = get_logger("reddit.client")
        self._reddit: Optional[praw.Reddit] = None
        self._subreddit = None

    def _get_reddit_instance(self) -> praw.Reddit:
        """Get or create Reddit instance.

        Returns:
            Configured Reddit instance

        Raises:
            ValueError: If required credentials are missing
        """
        if self._reddit is None:
            # Validate credentials
            if not self.config.reddit_client_id:
                raise ValueError("REDDIT_CLIENT_ID environment variable is required")

            if not self.config.reddit_client_secret:
                raise ValueError(
                    "REDDIT_CLIENT_SECRET environment variable is required"
                )

            self.logger.info("Initializing Reddit client")

            self._reddit = praw.Reddit(
                client_id=self.config.reddit_client_id,
                client_secret=self.config.reddit_client_secret,
                user_agent=self.config.reddit_user_agent,
                username=self.config.reddit_username,
                password=self.config.reddit_password,
            )

            # Test authentication
            try:
                # This will fail if authentication is not working
                user = self._reddit.user.me()
                if user:
                    self.logger.info(f"Authenticated as Reddit user: {user.name}")
                else:
                    self.logger.info(
                        "Authenticated with Reddit (client credentials only)"
                    )
            except Exception as e:
                self.logger.warning(f"Reddit authentication check failed: {e}")

        return self._reddit

    def _get_subreddit(self) -> Any:
        """Get subreddit instance."""
        if self._subreddit is None:
            reddit = self._get_reddit_instance()
            self._subreddit = reddit.subreddit(self.config.subreddit_name)
            self.logger.info(f"Connected to subreddit: r/{self.config.subreddit_name}")

        return self._subreddit

    def submit_news_item(
        self, news_item: NewsItem, dry_run: bool = False
    ) -> Optional[Submission]:
        """Submit a news item to Reddit.

        Args:
            news_item: News item to submit
            dry_run: If True, don't actually submit

        Returns:
            Submission object if successful, None otherwise
        """
        subreddit = self._get_subreddit()

        title = news_item.headline
        if len(title) > 300:  # Reddit title limit
            title = title[:297] + "..."

        self.logger.info(f"{'[DRY RUN] ' if dry_run else ''}Submitting: {title}")

        if dry_run:
            self.logger.info(f"Would submit to r/{self.config.subreddit_name}")
            self.logger.info(f"Title: {title}")
            self.logger.info(f"URL: {news_item.link}")
            return None

        try:
            submission = subreddit.submit(title=title, url=news_item.link)

            self.logger.info(f"Successfully submitted: {submission.url}")
            return submission

        except RedditAPIException as e:
            for item in e.items:
                self.logger.error(
                    f"Reddit API error: {item.error_type} - {item.message}"
                )
            return None

        except PRAWException as e:
            self.logger.error(f"Reddit error: {e}")
            return None

        except Exception as e:
            self.logger.error(f"Unexpected error submitting to Reddit: {e}")
            return None

    def submit_multiple_news_items(
        self,
        news_items: List[NewsItem],
        dry_run: bool = False,
        delay_between_posts: int = 60,
    ) -> list[Submission | None]:
        """Submit multiple news items with rate limiting.

        Args:
            news_items: List of news items to submit
            dry_run: If True, don't actually submit
            delay_between_posts: Seconds to wait between submissions

        Returns:
            List of submission objects (None for failed submissions)
        """
        submissions: list[Submission | None] = []

        for i, news_item in enumerate(news_items):
            if i > 0 and not dry_run:
                self.logger.info(
                    f"Waiting {delay_between_posts} seconds before next submission..."
                )
                time.sleep(delay_between_posts)

            submission = self.submit_news_item(news_item, dry_run=dry_run)
            submissions.append(submission)

        success_count = sum(1 for s in submissions if s is not None)

        self.logger.info(
            f"Submitted {success_count}/{len(news_items)} articles successfully"
        )

        return submissions

    def search_submissions(self, query: str, limit: int = 100) -> List[Submission]:
        """Search for submissions in the subreddit.

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of matching submissions
        """
        subreddit = self._get_subreddit()

        try:
            submissions = list(subreddit.search(query, limit=limit, sort="new"))
            self.logger.debug(
                f"Found {len(submissions)} submissions for query: {query}"
            )
            return submissions

        except Exception as e:
            self.logger.error(f"Error searching Reddit: {e}")
            return []

    def get_recent_submissions(self, limit: int = 100) -> List[Submission]:
        """Get recent submissions from the subreddit.

        Args:
            limit: Maximum number of submissions to retrieve

        Returns:
            List of recent submissions
        """
        subreddit = self._get_subreddit()

        try:
            submissions = list(subreddit.new(limit=limit))
            self.logger.debug(f"Retrieved {len(submissions)} recent submissions")
            return submissions

        except Exception as e:
            self.logger.error(f"Error getting recent submissions: {e}")
            return []

    def test_connection(self) -> bool:
        """Test Reddit API connection.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            reddit = self._get_reddit_instance()
            subreddit = self._get_subreddit()

            # Test basic subreddit access
            subreddit_info = subreddit.display_name
            self.logger.info(f"✅ Successfully connected to r/{subreddit_info}")

            # Test user authentication if available
            try:
                user = reddit.user.me()
                if user:
                    self.logger.info(f"✅ Authenticated as user: {user.name}")
            except Exception:
                self.logger.info(
                    "✅ Connected with client credentials (no user authentication)"
                )

            return True

        except Exception as e:
            self.logger.error(f"❌ Reddit connection failed: {e}")
            return False


def main() -> None:
    """CLI entry point for testing Reddit client."""
    import argparse

    parser = argparse.ArgumentParser(description="Reddit client CLI")
    parser.add_argument(
        "--test-connection", action="store_true", help="Test Reddit API connection"
    )
    parser.add_argument("--config", type=str, help="Path to configuration file")

    args = parser.parse_args()

    if args.test_connection:
        config = Config(args.config)
        client = RedditClient(config)
        success = client.test_connection()
        sys.exit(0 if success else 1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
