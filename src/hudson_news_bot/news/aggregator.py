"""News aggregation using Claude Code SDK."""

import asyncio
import datetime
import re
import sys
from typing import Optional

from claude_code_sdk import (
    AssistantMessage,
    ClaudeCodeOptions,
    ClaudeSDKClient,
    TextBlock,
)

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
        # Use bypassPermissions to allow web access for fetching real news
        self.options = ClaudeCodeOptions(
            system_prompt=config.system_prompt,
            max_turns=config.claude_max_turns,
            permission_mode="default",
            disallowed_tools=["WebFetch", "WebSearch"],
            allowed_tools=[
                "Task",
                "Read",
                "ListMcpResourcesTool",
                "ReadMcpResourceTool",
                "mcp__playwright__browser_close",
                "mcp__playwright__browser_resize",
                "mcp__playwright__browser_console_messages",
                "mcp__playwright__browser_handle_dialog",
                "mcp__playwright__browser_evaluate",
                "mcp__playwright__browser_file_upload",
                "mcp__playwright__browser_install",
                "mcp__playwright__browser_press_key",
                "mcp__playwright__browser_type",
                "mcp__playwright__browser_navigate",
                "mcp__playwright__browser_navigate_back",
                "mcp__playwright__browser_navigate_forward",
                "mcp__playwright__browser_network_requests",
                "mcp__playwright__browser_take_screenshot",
                "mcp__playwright__browser_snapshot",
                "mcp__playwright__browser_click",
                "mcp__playwright__browser_drag",
                "mcp__playwright__browser_hover",
                "mcp__playwright__browser_select_option",
                "mcp__playwright__browser_tab_list",
                "mcp__playwright__browser_tab_new",
                "mcp__playwright__browser_tab_select",
                "mcp__playwright__browser_tab_close",
                "mcp__playwright__browser_wait_for",
            ],
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
            prompt = self._create_aggregation_prompt()
            self.logger.debug(f"Sending prompt to Claude: {prompt}")

            # Send query and collect response
            await client.query(prompt)

            # Build response from text blocks
            response_chunks: list[str] = []
            async for message in client.receive_response():
                self.logger.debug(f"Received message: {message}")
                if isinstance(message, AssistantMessage):
                    response_chunks.extend(
                        content.text
                        for content in message.content
                        if isinstance(content, TextBlock)
                    )

            # Parse and return results if response received
            if response_chunks:
                content = " ".join(response_chunks)
                return self._parse_response(content)

        raise Exception("No response received from Claude")

    def _create_aggregation_prompt(self) -> str:
        """Create the prompt for news aggregation.

        Returns:
            Formatted prompt string
        """
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        return (
            f"Today is {today} and I need you to find up to {self.config.max_articles} articles from these websites."
            """
            - https://hudsonohiotoday.com/
            - https://thesummiteer.org/posts
            - https://www.beaconjournal.com/communities/hudsonhubtimes/
            - https://www.news5cleveland.com/news/local-news/oh-summit/
            - https://www.wkyc.com/section/summit-county
            """
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
