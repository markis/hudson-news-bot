"""Reddit API client using Async PRAW."""

import asyncio
from logging import Logger
import logging
import sys

import asyncpraw  # type: ignore
from asyncpraw.exceptions import AsyncPRAWException, RedditAPIException  # type: ignore
from asyncpraw.models import Submission, Subreddit  # type: ignore

from hudson_news_bot.config.settings import Config
from hudson_news_bot.news.models import NewsItem


class RedditClient:
    """Reddit API client for posting news articles."""

    config: Config
    logger: Logger
    _reddit: asyncpraw.Reddit | None = None
    _subreddit: Subreddit | None = None

    def __init__(self, config: Config):
        """Initialize Reddit client.

        Args:
            config: Configuration instance
        """
        self.config = config
        self.logger = logging.getLogger(__name__)

    async def _get_reddit_instance(self) -> asyncpraw.Reddit:
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

            self._reddit = asyncpraw.Reddit(
                client_id=self.config.reddit_client_id,
                client_secret=self.config.reddit_client_secret,
                user_agent=self.config.reddit_user_agent,
                username=self.config.reddit_username,
                password=self.config.reddit_password,
            )

            # Test authentication
            try:
                # This will fail if authentication is not working
                user = await self._reddit.user.me()
                if user:
                    self.logger.info(f"Authenticated as Reddit user: {user.name}")
                else:
                    self.logger.info(
                        "Authenticated with Reddit (client credentials only)"
                    )
            except Exception as e:
                self.logger.warning(f"Reddit authentication check failed: {e}")

        return self._reddit

    async def close(self) -> None:
        """Close the Reddit client session."""
        if self._reddit:
            await self._reddit.close()

    async def _get_subreddit(self) -> Subreddit:
        """Get subreddit instance."""
        if self._subreddit is None:
            reddit = await self._get_reddit_instance()
            self._subreddit = await reddit.subreddit(self.config.subreddit_name)
            self.logger.info(f"Connected to subreddit: r/{self.config.subreddit_name}")

        return self._subreddit

    async def submit_news_item(
        self, news_item: NewsItem, dry_run: bool = False
    ) -> Submission | None:
        """Submit a news item to Reddit.

        Args:
            news_item: News item to submit
            dry_run: If True, don't actually submit

        Returns:
            Submission object if successful, None otherwise
        """
        title = news_item.headline
        if len(title) > 300:  # Reddit title limit
            title = title[:299] + "…"

        self.logger.info(f"{'[DRY RUN] ' if dry_run else ''}Submitting: {title}")

        if dry_run:
            self.logger.info(f"Would submit to r/{self.config.subreddit_name}")
            self.logger.info(f"Title: {title}")
            self.logger.info(f"URL: {news_item.link}")
            if news_item.flair:
                self.logger.info(f"Flair: {news_item.flair}")
            if news_item.flair_id:
                self.logger.info(f"Flair ID: {news_item.flair_id}")
            return None

        subreddit = await self._get_subreddit()

        try:
            # Submit with flair_id if available, otherwise use flair_text
            if news_item.flair_id:
                submission = await subreddit.submit(
                    title=title, url=news_item.link, flair_id=news_item.flair_id
                )
            elif news_item.flair:
                submission = await subreddit.submit(
                    title=title, url=news_item.link, flair_text=news_item.flair
                )
            else:
                submission = await subreddit.submit(title=title, url=news_item.link)

            # Construct the submission URL since submission.url requires loading
            submission_url = f"https://reddit.com/r/{self.config.subreddit_name}/comments/{submission.id}"
            self.logger.info(f"Successfully submitted: {submission_url}")
            return submission

        except RedditAPIException as e:
            for item in e.items:
                self.logger.error(
                    f"Reddit API error: {item.error_type} - {item.message}"
                )
            return None

        except AsyncPRAWException as e:
            self.logger.error(f"Reddit error: {e}")
            return None

        except Exception as e:
            self.logger.error(f"Unexpected error submitting to Reddit: {e}")
            return None

    async def submit_multiple_news_items(
        self,
        news_items: list[NewsItem],
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
                await asyncio.sleep(delay_between_posts)

            submission = await self.submit_news_item(news_item, dry_run=dry_run)
            submissions.append(submission)

        success_count = sum(1 for s in submissions if s is not None)

        self.logger.info(
            f"Submitted {success_count}/{len(news_items)} articles successfully"
        )

        return submissions

    async def search_submissions(
        self, query: str, limit: int = 100
    ) -> list[Submission]:
        """Search for submissions in the subreddit.

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of matching submissions
        """
        subreddit = await self._get_subreddit()

        try:
            submissions = [
                submission
                async for submission in subreddit.search(query, limit=limit, sort="new")
            ]
            self.logger.debug(
                f"Found {len(submissions)} submissions for query: {query}"
            )
            return submissions

        except Exception:
            self.logger.exception("Error searching Reddit")
            return []

    async def get_user_submissions(self, limit: int = 100) -> list[Submission]:
        """Get recent submissions from the authenticated user.

        Args:
            limit: Maximum number of submissions to retrieve

        Returns:
            List of user's recent submissions
        """
        reddit = await self._get_reddit_instance()

        try:
            user = await reddit.user.me()
            if not user:
                self.logger.warning(
                    "No authenticated user available for submission check"
                )
                return []

            submissions = [
                submission async for submission in user.submissions.new(limit=limit)
            ]
            self.logger.debug(f"Retrieved {len(submissions)} user submissions")
            return submissions

        except Exception:
            self.logger.exception("Error getting user submissions")
            return []

    async def get_flair_options(self) -> dict[str, str]:
        """Get available flair options for the subreddit.

        Returns:
            Dictionary mapping flair text to flair ID
        """
        subreddit = await self._get_subreddit()

        try:
            flair_options: dict[str, str] = {}
            async for flair in subreddit.flair.link_templates:
                try:
                    text = None
                    flair_id = None

                    if isinstance(flair, dict):
                        text = flair.get("text")
                        flair_id = flair.get("id")
                    elif not isinstance(flair, dict) and hasattr(flair, "text"):
                        text = getattr(flair, "text", None)
                        flair_id = getattr(flair, "id", None)

                    if (
                        text
                        and flair_id
                        and isinstance(text, str)
                        and isinstance(flair_id, str)
                    ):
                        flair_options[text] = flair_id
                except (AttributeError, KeyError, TypeError):
                    continue

            self.logger.debug(f"Retrieved {len(flair_options)} flair options")
            return flair_options

        except Exception:
            self.logger.exception("Error getting flair options")
            return {}

    async def test_connection(self) -> bool:
        """Test Reddit API connection.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            reddit = await self._get_reddit_instance()
            subreddit = await self._get_subreddit()

            # Test basic subreddit access
            subreddit_info = subreddit.display_name
            self.logger.info(f"✅ Successfully connected to r/{subreddit_info}")

            # Test user authentication if available
            try:
                user = await reddit.user.me()
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
        success = asyncio.run(client.test_connection())
        sys.exit(0 if success else 1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
