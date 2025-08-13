"""Main application orchestrator for the news aggregation bot."""

import asyncio
import sys
from typing import Any, List, Optional

from hudson_news_bot.config.settings import Config
from hudson_news_bot.news.aggregator import NewsAggregator
from hudson_news_bot.news.models import NewsCollection, NewsItem
from hudson_news_bot.reddit.client import RedditClient
from hudson_news_bot.reddit.deduplicator import DuplicationChecker
from hudson_news_bot.utils.logging import get_logger, setup_logging
from hudson_news_bot.utils.toml_handler import TOMLHandler


class NewsBot:
    """Main orchestrator for news aggregation and Reddit posting."""

    def __init__(self, config: Config):
        """Initialize the news bot.

        Args:
            config: Configuration instance
        """
        self.config = config
        self.logger = get_logger("main")

        # Initialize components
        self.news_aggregator = NewsAggregator(config)
        self.reddit_client = RedditClient(config)
        self.deduplicator = DuplicationChecker(self.reddit_client, config)

    async def run(
        self, dry_run: bool = False, output_file: Optional[str] = None
    ) -> bool:
        """Run the complete news aggregation and posting workflow.

        Args:
            dry_run: If True, don't actually post to Reddit
            output_file: Optional file to save news items as TOML

        Returns:
            True if workflow completed successfully
        """
        self.logger.info("Starting news aggregation workflow")

        try:
            # Step 1: Validate configuration
            self.logger.info("Validating configuration...")
            is_valid, errors = self.config.validate()
            if not is_valid:
                self.logger.error("Configuration validation failed:")
                for error in errors:
                    self.logger.error(f"  - {error}")
                return False

            # Step 2: Aggregate news
            self.logger.info("Aggregating news from Claude SDK...")
            news_collection = await self.news_aggregator.aggregate_news()

            if not news_collection or len(news_collection) == 0:
                self.logger.warning("No news items were aggregated")
                return False

            self.logger.info(
                f"Successfully aggregated {len(news_collection)} news items"
            )

            # Step 3: Save to file if requested
            if output_file:
                self.logger.info(f"Saving news items to {output_file}")
                TOMLHandler.write_news_toml(news_collection, output_file)

            # Step 4: Filter duplicates
            self.logger.info("Checking for duplicates...")
            unique_news_items = await self._filter_duplicates(news_collection)

            if not unique_news_items:
                self.logger.info("All news items were duplicates, nothing to post")
                return True

            self.logger.info(f"Found {len(unique_news_items)} unique items to post")

            # Step 5: Post to Reddit
            self.logger.info(f"{'[DRY RUN] ' if dry_run else ''}Posting to Reddit...")
            submissions = self.reddit_client.submit_multiple_news_items(
                unique_news_items, dry_run=dry_run
            )

            # Step 6: Record successful submissions
            if not dry_run:
                for news_item, submission in zip(unique_news_items, submissions):
                    if submission:
                        self.deduplicator.store_submission(news_item, submission.id)

            # Step 7: Cleanup old records
            self.logger.info("Cleaning up old duplicate records...")
            deleted_count = self.deduplicator.cleanup_old_records()
            self.logger.debug(f"Deleted {deleted_count} old records")

            # Step 8: Report results
            successful_count = sum(1 for s in submissions if s is not None)
            self.logger.info(
                f"Workflow completed: {successful_count}/{len(unique_news_items)} items posted successfully"
            )

            return True

        except Exception as e:
            self.logger.error(f"Workflow failed: {e}")
            self.logger.exception("Full error details:")
            return False

    async def _filter_duplicates(
        self, news_collection: NewsCollection
    ) -> List[NewsItem]:
        """Filter out duplicate news items.

        Args:
            news_collection: Collection of news items to filter

        Returns:
            List of unique news items
        """
        unique_items: list[NewsItem] = []

        for news_item in news_collection:
            is_duplicate, reason = self.deduplicator.is_duplicate(news_item)

            if is_duplicate:
                self.logger.info(f"Skipping duplicate: {news_item.headline} ({reason})")
            else:
                unique_items.append(news_item)

        return unique_items

    def get_statistics(self) -> dict[str, Any]:
        """Get bot statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            "config": {
                "subreddit": self.config.subreddit_name,
                "max_articles": self.config.max_articles,
                "check_duplicates": self.config.check_for_duplicates,
            },
            "duplicates": self.deduplicator.get_statistics(),
        }


async def main() -> None:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Hudson News Bot - Aggregate and post news to Reddit"
    )
    parser.add_argument("--config", type=str, help="Path to configuration file")
    parser.add_argument(
        "--dry-run", action="store_true", help="Don't actually post to Reddit"
    )
    parser.add_argument("--output", type=str, help="Save aggregated news to TOML file")
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level",
    )
    parser.add_argument(
        "--log-file", type=str, help="Log to file in addition to console"
    )
    parser.add_argument("--stats", action="store_true", help="Show statistics and exit")
    parser.add_argument(
        "--test-connections", action="store_true", help="Test all connections and exit"
    )

    args = parser.parse_args()

    # Set up logging
    setup_logging(level=args.log_level, log_file=args.log_file)

    logger = get_logger("main")

    try:
        # Load configuration
        config = Config(args.config)

        # Initialize bot
        bot = NewsBot(config)

        # Handle special commands
        if args.stats:
            stats = bot.get_statistics()
            logger.info("Bot Statistics:")
            for category, data in stats.items():
                logger.info(f"  {category.title()}:")
                for key, value in data.items():
                    logger.info(f"    {key}: {value}")
            return

        if args.test_connections:
            logger.info("Testing connections...")

            # Test Reddit
            reddit_ok = bot.reddit_client.test_connection()

            # Test Claude SDK
            from hudson_news_bot.news.aggregator import test_connection

            claude_ok = await test_connection()

            if reddit_ok and claude_ok:
                logger.info("✅ All connections successful")
                sys.exit(0)
            else:
                logger.error("❌ Some connections failed")
                sys.exit(1)

        # Run main workflow
        success = await bot.run(dry_run=args.dry_run, output_file=args.output)

        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.exception("Full error details:")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
