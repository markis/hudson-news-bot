"""News aggregation using Claude Code SDK."""

import asyncio
import re
import sys
from typing import Optional

from claude_code_sdk import ClaudeCodeOptions, ClaudeSDKClient

from hudson_news_bot.config.settings import Config
from hudson_news_bot.news.models import NewsCollection
from hudson_news_bot.utils.logging import get_logger
from hudson_news_bot.utils.toml_handler import TOMLHandler


class NewsAggregator:
    """Handles news aggregation using Claude Code SDK."""

    def __init__(self, config: Config):
        """Initialize the news aggregator.

        Args:
            config: Configuration instance
        """
        self.config = config
        self.logger = get_logger("news.aggregator")

        # Configure Claude SDK options
        self.options = ClaudeCodeOptions(
            system_prompt=config.system_prompt,
            max_turns=config.claude_max_turns,
            permission_mode="default",  # Use valid literal value
        )

    async def aggregate_news(self) -> NewsCollection:
        """Aggregate news stories using Claude SDK.

        Returns:
            NewsCollection containing discovered news items

        Raises:
            Exception: If news aggregation fails
        """
        self.logger.info(
            f"Starting news aggregation for {self.config.max_articles} articles"
        )

        async with ClaudeSDKClient(options=self.options) as client:
            response_content = ""
            prompt = self._create_aggregation_prompt()
            self.logger.debug(f"Sending prompt to Claude: {prompt}")

            # Start the conversation
            await client.query(prompt)
            async for message in client.receive_response():
                if content := getattr(message, "content", None):
                    response_content = content
                    break

            # Parse the response
            if response_content:
                return self._parse_response(response_content)

        raise Exception("No response received from Claude")

    def _create_aggregation_prompt(self) -> str:
        """Create the prompt for news aggregation.

        Returns:
            Formatted prompt string
        """
        return (
            f"Find {self.config.max_articles} current trending news stories from reliable sources. "
            "For each story, extract the headline, summary, publication date, and link. "
            "Format your response as valid TOML using the exact structure specified in the system prompt. "
            "Only include real, verifiable news from the last 24 hours."
        )

    def _parse_response(self, response: str) -> NewsCollection:
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
            toml_content = self._extract_toml_from_response(response)

            if not toml_content:
                raise ValueError("No valid TOML content found in response")

            # Validate TOML syntax
            if not TOMLHandler.validate_toml_syntax(toml_content):
                raise ValueError("Invalid TOML syntax in response")

            # Parse into NewsCollection
            news_collection = TOMLHandler.parse_news_toml(toml_content)

            self.logger.info(f"Successfully parsed {len(news_collection)} news items")
            return news_collection

        except Exception as e:
            self.logger.error(f"Failed to parse response: {e}")
            self.logger.debug(f"Raw response: {response}")
            raise ValueError(f"Failed to parse Claude response: {e}")

    def _extract_toml_from_response(self, response: str) -> Optional[str]:
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
    logger = get_logger("news.aggregator.test")

    try:
        config = Config()
        aggregator = NewsAggregator(config)

        logger.info("Testing Claude SDK connection...")

        async with ClaudeSDKClient(options=aggregator.options) as client:
            # Simple test query
            await client.query("Please respond with just 'OK' to confirm connection.")
            async for message in client.receive_response():
                if (content := getattr(message, "content", None)) and "OK" in content:
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
