"""Main application orchestrator for the news aggregation bot."""

import asyncio
import logging
import sys
from datetime import datetime, timedelta
from typing import Any, List

from hudson_news_bot.config.settings import Config
from hudson_news_bot.news.aggregator import NewsAggregator
from hudson_news_bot.news.models import NewsCollection, NewsItem
from hudson_news_bot.reddit.client import RedditClient
from hudson_news_bot.reddit.deduplicator import DuplicationChecker
from hudson_news_bot.utils.logging import setup_logging
from hudson_news_bot.utils.toml_handler import TOMLHandler


class NewsBot:
    """Main orchestrator for news aggregation and Reddit posting."""

    def __init__(self, config: Config):
        """Initialize the news bot.

        Args:
            config: Configuration instance
        """
        self.config = config
        self.logger = logging.getLogger(__name__)

        # Initialize components
        self.reddit_client = RedditClient(config)
        self.news_aggregator = NewsAggregator(config, self.reddit_client)
        self.deduplicator = DuplicationChecker(self.reddit_client, config)

    async def cleanup(self) -> None:
        """Clean up resources."""
        await self.reddit_client.close()

    async def run(self, dry_run: bool = False, output_file: str | None = None) -> bool:
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

            # For dry runs, filter out Reddit-related validation errors
            if dry_run:
                non_reddit_errors = [
                    error
                    for error in errors
                    if not any(
                        reddit_term in error
                        for reddit_term in ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET"]
                    )
                ]
                if non_reddit_errors:
                    self.logger.error("Configuration validation failed:")
                    for error in non_reddit_errors:
                        self.logger.error(f"  - {error}")
                    return False
                elif errors:
                    self.logger.info("Skipping Reddit validation for dry run")
            elif not is_valid:
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

            # Step 3.1: Filter invalid items
            self.logger.info("Filtering invalid news items...")
            valid_items = self._filter_invalid(news_collection)

            if len(valid_items) < len(news_collection):
                filtered_count = len(news_collection) - len(valid_items)
                self.logger.info(
                    f"Filtered out {filtered_count} invalid items (missing headline or link)"
                )

            if not valid_items:
                self.logger.info(
                    "No valid news items found (all items are missing headline or link)"
                )
                return True

            # Step 3.2: Filter by date (only keep today and yesterday)
            self.logger.info("Filtering news items by date...")
            date_filtered_items = self._filter_by_date(valid_items)

            if len(date_filtered_items) < len(valid_items):
                filtered_count = len(valid_items) - len(date_filtered_items)
                self.logger.info(
                    f"Filtered out {filtered_count} items older than yesterday"
                )

            if not date_filtered_items:
                self.logger.info(
                    "No recent news items found (all items are older than yesterday)"
                )
                return True

            # Step 4: Filter duplicates
            if dry_run:
                self.logger.info("Skipping duplicate check for dry run")
                unique_news_items = list(date_filtered_items)
            else:
                self.logger.info("Checking for duplicates...")
                unique_news_items = await self._filter_duplicates(date_filtered_items)

            if not unique_news_items:
                self.logger.info("All news items were duplicates, nothing to post")
                return True

            self.logger.info(f"Found {len(unique_news_items)} unique items to post")

            # Step 5: Post to Reddit (articles already categorized during aggregation)
            self.logger.info(f"{'[DRY RUN] ' if dry_run else ''}Posting to Reddit...")
            submissions = await self.reddit_client.submit_multiple_news_items(
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
            is_duplicate, reason = await self.deduplicator.is_duplicate(news_item)

            if is_duplicate:
                self.logger.info(f"Skipping duplicate: {news_item.headline} ({reason})")
            else:
                unique_items.append(news_item)

        return unique_items

    def _filter_invalid(self, news_collection: NewsCollection) -> NewsCollection:
        """Filter out news items that are missing essential fields.

        Args:
            news_collection: Collection of news items to filter

        Returns:
            NewsCollection with only valid items (those with headline and link)
        """
        return NewsCollection(
            news_item
            for news_item in news_collection
            if news_item.headline and news_item.link
        )

    def _filter_by_date(self, news_collection: NewsCollection) -> NewsCollection:
        """Filter news items to only include those from today and yesterday.

        Args:
            news_collection: Collection of news items to filter

        Returns:
            NewsCollection with items from today and yesterday only
        """
        yesterday = (datetime.now() - timedelta(days=1)).date()
        return NewsCollection(
            news_item
            for news_item in news_collection
            if news_item.publication_date.date() >= yesterday
        )

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

    logger = logging.getLogger(__name__)

    bot: NewsBot | None = None

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

            try:
                # Test Reddit
                reddit_ok = await bot.reddit_client.test_connection()

                # Test Claude SDK
                from hudson_news_bot.news.aggregator import test_connection

                claude_ok = await test_connection()

                if reddit_ok and claude_ok:
                    logger.info("✅ All connections successful")
                    sys.exit(0)
                else:
                    logger.error("❌ Some connections failed")
                    sys.exit(1)
            finally:
                await bot.cleanup()

        # Run main workflow
        try:
            success = await bot.run(dry_run=args.dry_run, output_file=args.output)
        finally:
            await bot.cleanup()
        if not success:
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        if bot is not None:
            await bot.cleanup()
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.exception("Full error details:")
        if bot is not None:
            await bot.cleanup()
        sys.exit(1)


def sync_main() -> None:
    """Synchronous entry point for compatibility with older Python versions."""
    asyncio.run(main())


if __name__ == "__main__":
    asyncio.run(main())
