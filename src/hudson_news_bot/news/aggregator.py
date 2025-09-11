"""News aggregation using website scraping and Claude for article identification."""

import asyncio
import datetime
from logging import Logger
import logging
import re
import sys
from typing import Final, Optional

from claude_code_sdk import (
    AssistantMessage,
    ClaudeCodeOptions,
    ClaudeSDKClient,
    TextBlock,
)

from hudson_news_bot.config.settings import Config
from hudson_news_bot.news.models import NewsCollection
from hudson_news_bot.news.scraper import NewsItemDict, WebsiteScraper
from hudson_news_bot.reddit.client import RedditClient
from hudson_news_bot.utils.toml_handler import TOMLHandler


class NewsAggregator:
    """Handles news aggregation using Claude Code SDK."""

    config: Final[Config]
    logger: Final[Logger]
    options: Final[ClaudeCodeOptions]

    def __init__(self, config: Config, reddit_client: RedditClient | None = None):
        """Initialize the news aggregator.

        Args:
            config: Configuration instance
            reddit_client: Reddit client for getting flair options (optional)
        """
        self.config = config
        self.reddit_client = reddit_client
        self.logger = logging.getLogger(__name__)
        self.flair_mapping: dict[str, str] = {}

        # Configure Claude SDK options for analyzing scraped content
        self.options = ClaudeCodeOptions(
            system_prompt=config.system_prompt,
            max_turns=config.claude_max_turns,
            permission_mode=config.claude_permission_mode,
            model=config.claude_model,
        )

    async def aggregate_news(self) -> NewsCollection:
        """Aggregate news stories using website scraping and Claude analysis.

        Returns:
            NewsCollection containing discovered news items

        Raises:
            Exception: If news aggregation fails
        """
        self.logger.info(
            f"Starting news aggregation for {self.config.max_articles} articles"
        )

        # Get news sites from configuration
        news_sites = self.config.news_sites

        # Scrape the websites
        scraper = WebsiteScraper(self.config)
        articles = await scraper.scrape_news_sites(news_sites)

        if not articles:
            self.logger.warning("No articles found from scraping")
            return NewsCollection()

        self.logger.info(
            f"Scraped {len(articles)} articles, sending to Claude for analysis"
        )

        # Get flair options if reddit client is available
        flair_options = {}
        if self.reddit_client:
            try:
                flair_options = await self.reddit_client.get_flair_options()
                self.flair_mapping = flair_options  # Store for later use
                self.logger.info(
                    f"Retrieved {len(flair_options)} flair options for categorization"
                )
            except Exception as e:
                self.logger.warning(f"Could not get flair options: {e}")

        # Send scraped content to Claude for analysis
        async with ClaudeSDKClient(options=self.options) as client:
            prompt = self.create_analysis_prompt(articles, flair_options)
            self.logger.debug("Sending analysis prompt to Claude")

            # Send query and collect response
            await client.query(prompt)

            # Build response from text blocks efficiently
            response_parts: list[str] = []
            async for message in client.receive_response():
                self.logger.debug(f"Received message: {message}")
                if isinstance(message, AssistantMessage):
                    for content in message.content:
                        if isinstance(content, TextBlock):
                            response_parts.append(content.text)

            # Parse and return results if response received
            if response_parts:
                return self._parse_response("".join(response_parts))

        raise Exception("No response received from Claude")

    def create_analysis_prompt(
        self, articles: list[NewsItemDict], flair_options: dict[str, str] | None = None
    ) -> str:
        """Create the prompt for Claude to analyze scraped articles.

        Args:
            articles: List of scraped article dictionaries

        Returns:
            Formatted prompt string
        """
        today = datetime.datetime.now().strftime("%Y-%m-%d")

        # Prepare article summaries for Claude efficiently
        article_summaries: list[str] = [
            f"""
Article {i}:
URL: {article.get("url", "N/A")}
Headline: {article.get("headline", "N/A")}
Date: {article.get("date", "N/A")}
Content Preview: {(article.get("content") or "N/A")[:500]}...
"""
            for i, article in enumerate(articles[:20], 1)  # Limit to first 20 articles
        ]

        # Add flair options to prompt if available
        flair_section = ""
        if flair_options:
            flair_list = "\n".join(f"- {text}" for text in flair_options.keys())
            flair_section = f"""

Available Categories for Classification:
{flair_list}

For each article, also assign the most appropriate category from the list above."""

        prompt = f"""Today is {today}. I've scraped the following articles from Hudson, Ohio news sites.
Please analyze them and identify the NEWEST and most relevant local news articles.

{"".join(article_summaries)}

From these articles, select the most recent and relevant Hudson, Ohio news stories.{flair_section}
For each selected article, format your response as valid TOML using this EXACT structure:

[[news]]
headline = "story headline"
summary = "brief 2-3 sentence summary of the article"
publication_date = "YYYY-MM-DD"
link = "https://source.com/article"
{'flair = "category name"' if flair_options else ""}

[[news]]
headline = "second story headline"
summary = "second story summary"
publication_date = "YYYY-MM-DD"
link = "https://source.com/second-article"
{'flair = "category name"' if flair_options else ""}

IMPORTANT:
- Only include articles that are clearly about Hudson, Ohio or directly relevant to Hudson residents
- Prioritize the most recent articles (from today or yesterday)
- Ensure dates are in YYYY-MM-DD format
- Write clear, concise summaries that capture the key points
- Output ONLY the TOML data, no explanatory text
- If no relevant articles are found, return an empty TOML array like this:
{"- Assign the most appropriate flair/category from the provided list" if flair_options else ""}
[[news]]
"""

        return prompt

    def _parse_response(
        self, response: str, flair_mapping: dict[str, str] | None = None
    ) -> NewsCollection:
        """Parse Claude's response into NewsCollection.

        Args:
            response: Raw response from Claude

        Returns:
            NewsCollection instance

        Raises:
            ValueError: If response cannot be parsed
        """
        self.logger.debug(f"Parsing response: {response[:200]}...")

        try:
            # Extract TOML content from response
            toml_content = self.extract_toml_from_response(response)

            if not toml_content:
                raise ValueError("No valid TOML content found in response")

            # Validate TOML syntax
            if not TOMLHandler.validate_toml_syntax(toml_content):
                raise ValueError("Invalid TOML syntax in response")

            # Parse into NewsCollection
            news_collection = TOMLHandler.parse_news_toml(
                toml_content, flair_mapping or self.flair_mapping
            )

            self.logger.info(f"Successfully parsed {len(news_collection)} news items")
            return news_collection

        except Exception as e:
            self.logger.error(f"Failed to parse response: {e}")
            self.logger.debug(f"Raw response: {response}")
            raise ValueError(f"Failed to parse Claude response: {e}")

    def extract_toml_from_response(self, response: str) -> Optional[str]:
        """Extract TOML content from Claude's response.

        Args:
            response: Raw response text

        Returns:
            Extracted TOML content or None if not found
        """
        # First check for direct pattern that indicates TOML content
        if "[[news]]" in response:
            # Check for TOML code blocks first
            toml_match = re.search(
                r"```(?:toml)?\s*((?:\[\[news\]\].*?))```", response, re.DOTALL
            )
            if toml_match:
                return toml_match.group(1).strip()

            # Fallback: extract from first [[news]] occurrence
            start_idx = response.find("[[news]]")
            return response[start_idx:].strip()

        return None


async def test_connection() -> bool:
    """Test connection to Claude SDK.

    Returns:
        True if connection successful, False otherwise
    """
    logger = logging.getLogger(__name__)

    try:
        config = Config()
        aggregator = NewsAggregator(config)

        logger.info("Testing Claude SDK connection...")

        async with ClaudeSDKClient(options=aggregator.options) as client:
            # Simple test query
            await client.query("Please respond with just 'OK' to confirm connection.")
            async for message in client.receive_response():
                text = ""
                if type(message) is AssistantMessage:
                    for content in message.content:
                        if type(content) is TextBlock:
                            text += content.text

                if "OK" in text:
                    logger.info(f"Claude response: {text}")
                    logger.info("✅ Claude SDK connection successful")
                    return True

        logger.warning("⚠️ Claude SDK connection test inconclusive")
        return False

    except Exception:
        logger.exception("❌ Claude SDK connection failed")
        return False


def main() -> None:
    """CLI entry point for testing aggregator."""
    import argparse

    parser = argparse.ArgumentParser(description="News aggregator CLI")
    parser.add_argument(
        "--test-connection", action="store_true", help="Test Claude SDK connection"
    )
    parser.add_argument("--config", type=str, help="Path to configuration file")

    args = parser.parse_args()

    if args.test_connection:
        success = asyncio.run(test_connection())
        sys.exit(0 if success else 1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
