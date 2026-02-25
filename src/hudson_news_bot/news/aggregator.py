"""News aggregation using website scraping and LLM for article identification."""

import asyncio
import datetime
from logging import Logger
import logging
import sys
from typing import Final

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from hudson_news_bot.config.settings import Config
from hudson_news_bot.news.models import NewsCollection, NewsItem
from hudson_news_bot.news.scraper import NewsItemDict, WebsiteScraper
from hudson_news_bot.reddit.client import RedditClient


class NewsItemResponse(BaseModel):
    """Pydantic model for structured LLM response - single news item."""

    headline: str = Field(description="Story headline")
    summary: str = Field(description="Brief 2-3 sentence summary of the article")
    publication_date: str = Field(description="Publication date in YYYY-MM-DD format")
    link: str = Field(description="Full URL to the article")
    flair: str | None = Field(
        default=None, description="Category/flair from the provided list"
    )


class NewsResponse(BaseModel):
    """Pydantic model for structured LLM response - collection of news items."""

    news: list[NewsItemResponse] = Field(
        description="List of relevant Hudson, Ohio news articles"
    )


class NewsAggregator:
    """Handles news aggregation using OpenAI-compatible LLM API."""

    config: Final[Config]
    logger: Final[Logger]
    client: Final[AsyncOpenAI]

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

        # Configure OpenAI client for analyzing scraped content
        api_key = config.perplexity_api_key
        if not api_key or not api_key.strip():
            raise ValueError(
                "PERPLEXITY_API_KEY environment variable is required and must not be empty"
            )

        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=config.llm_base_url,
            timeout=config.llm_timeout_seconds,
        )

    async def aggregate_news(self) -> NewsCollection:
        """Aggregate news stories using website scraping and LLM analysis.

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
            f"Scraped {len(articles)} articles, sending to LLM for analysis"
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

        # Send scraped content to LLM for analysis with structured output
        prompt = self.create_analysis_prompt(articles, flair_options)
        self.logger.debug("Sending analysis prompt to LLM with structured output")

        try:
            response = await self.client.chat.completions.create(
                model=self.config.llm_model,
                messages=[
                    {"role": "system", "content": self.config.system_prompt},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=self.config.llm_max_tokens,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "hudson_news_response",
                        "schema": NewsResponse.model_json_schema(),
                    },
                },
            )

            # Parse structured response
            if response.choices and response.choices[0].message.content:
                response_text = response.choices[0].message.content
                return self._parse_structured_response(response_text)

        except Exception as e:
            self.logger.error(f"LLM API request failed: {e}")
            raise Exception(f"LLM API request failed: {e}")

        raise Exception("No response received from LLM")

    def create_analysis_prompt(
        self, articles: list[NewsItemDict], flair_options: dict[str, str] | None = None
    ) -> str:
        """Create the prompt for LLM to analyze scraped articles.

        Args:
            articles: List of scraped article dictionaries
            flair_options: Optional mapping of flair text to template IDs

        Returns:
            Formatted prompt string
        """
        today = datetime.datetime.now().strftime("%Y-%m-%d")

        # Prepare article summaries efficiently
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
For each selected article, format your response as valid JSON using this EXACT structure:

{{
  "news": [
    {{
      "headline": "story headline",
      "summary": "brief 2-3 sentence summary of the article",
      "publication_date": "YYYY-MM-DD",
      "link": "https://source.com/article"{"," if flair_options else ""}
      {'      "flair": "category name"' if flair_options else ""}
    }},
    {{
      "headline": "second story headline",
      "summary": "second story summary",
      "publication_date": "YYYY-MM-DD",
      "link": "https://source.com/second-article"{"," if flair_options else ""}
      {'      "flair": "category name"' if flair_options else ""}
    }}
  ]
}}

IMPORTANT:
- Only include articles that are clearly about Hudson, Ohio or directly relevant to Hudson residents
- Prioritize the most recent articles (from today or yesterday)
- Ensure dates are in YYYY-MM-DD format
- Write clear, concise summaries that capture the key points
- Output ONLY the JSON data, no explanatory text
- If no relevant articles are found, return an empty array: {{"news": []}}
{"- Assign the most appropriate flair/category from the provided list" if flair_options else ""}
"""

        return prompt

    def _parse_structured_response(self, response: str) -> NewsCollection:
        """Parse structured LLM response into NewsCollection.

        Args:
            response: Structured JSON response from LLM

        Returns:
            NewsCollection instance

        Raises:
            ValueError: If response cannot be parsed
        """
        self.logger.debug(f"Parsing structured response: {response[:200]}...")

        try:
            # Parse with Pydantic model
            news_response = NewsResponse.model_validate_json(response)

            # Convert to NewsItem objects
            news_items: list[NewsItem] = []
            for item in news_response.news:
                # Parse date
                pub_date = datetime.datetime.strptime(item.publication_date, "%Y-%m-%d")

                # Get flair ID if flair text is provided
                flair_id = None
                if item.flair:
                    flair_id = self.flair_mapping.get(item.flair)
                    if flair_id is None:
                        self.logger.warning(
                            f"Flair '{item.flair}' not found in mapping"
                        )

                news_items.append(
                    NewsItem(
                        headline=item.headline,
                        summary=item.summary,
                        publication_date=pub_date,
                        link=item.link,
                        flair_id=flair_id,
                    )
                )

            self.logger.info(
                f"Successfully parsed {len(news_items)} news items from structured output"
            )
            return NewsCollection(news_items)

        except Exception as e:
            self.logger.error(f"Failed to parse structured response: {e}")
            self.logger.debug(f"Raw response: {response}")
            raise ValueError(f"Failed to parse structured LLM response: {e}")


async def test_connection() -> bool:
    """Test connection to LLM API.

    Returns:
        True if connection successful, False otherwise
    """
    logger = logging.getLogger(__name__)

    try:
        config = Config()

        logger.info("Testing LLM API connection...")

        # Create OpenAI client
        api_key = config.perplexity_api_key
        if not api_key:
            logger.error("❌ PERPLEXITY_API_KEY not set")
            return False

        client = AsyncOpenAI(
            api_key=api_key,
            base_url=config.llm_base_url,
            timeout=config.llm_timeout_seconds,
        )

        # Simple test query
        response = await client.chat.completions.create(
            model=config.llm_model,
            messages=[
                {"role": "user", "content": "Respond with just 'OK'."},
            ],
            max_tokens=10,
        )

        if response.choices and response.choices[0].message.content:
            text = response.choices[0].message.content
            if "OK" in text:
                logger.info(f"LLM response: {text}")
                logger.info("✅ LLM API connection successful")
                return True

        logger.warning("⚠️ LLM API connection test inconclusive")
        return False

    except Exception:
        logger.exception("❌ LLM API connection failed")
        return False


def main() -> None:
    """CLI entry point for testing aggregator."""
    import argparse

    parser = argparse.ArgumentParser(description="News aggregator CLI")
    parser.add_argument(
        "--test-connection", action="store_true", help="Test LLM API connection"
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
