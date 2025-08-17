"""Tests for news aggregator."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from claude_code_sdk import AssistantMessage, TextBlock

from hudson_news_bot.config.settings import Config
from hudson_news_bot.news.aggregator import NewsAggregator, main
from hudson_news_bot.news.models import NewsCollection, NewsItem


class TestNewsAggregator:
    """Test NewsAggregator class."""

    @pytest.fixture
    def config(self) -> Config:
        """Create test configuration."""
        config = MagicMock(spec=Config)
        config.system_prompt = "Test system prompt"
        config.claude_max_turns = 5
        config.max_articles = 10
        return config

    @pytest.fixture
    def aggregator(self, config: Config) -> NewsAggregator:
        """Create test aggregator instance."""
        return NewsAggregator(config)

    def test_init(self, config: Config) -> None:
        """Test NewsAggregator initialization."""
        aggregator = NewsAggregator(config)

        assert aggregator.config == config
        assert aggregator.logger.name == "hudson_news_bot.news.aggregator"
        assert aggregator.options.system_prompt == "Test system prompt"
        assert aggregator.options.max_turns == 5
        assert aggregator.options.permission_mode == "default"
        assert "WebFetch" in aggregator.options.disallowed_tools
        assert "WebSearch" in aggregator.options.disallowed_tools
        assert "Task" in aggregator.options.allowed_tools

    def test_claude_options_configuration(self, aggregator: NewsAggregator) -> None:
        """Test Claude SDK options are properly configured."""
        options = aggregator.options

        # Test disallowed tools
        assert "WebFetch" in options.disallowed_tools
        assert "WebSearch" in options.disallowed_tools

        # Test allowed tools include playwright tools
        assert "mcp__playwright__browser_navigate" in options.allowed_tools
        assert "mcp__playwright__browser_click" in options.allowed_tools

        # Test permission mode
        assert options.permission_mode == "default"

    def test_config_integration(self) -> None:
        """Test that aggregator properly uses config values."""
        config = MagicMock(spec=Config)
        config.system_prompt = "Custom prompt"
        config.claude_max_turns = 3
        config.max_articles = 5

        aggregator = NewsAggregator(config)

        assert aggregator.config.system_prompt == "Custom prompt"
        assert aggregator.config.claude_max_turns == 3
        assert aggregator.config.max_articles == 5
        assert aggregator.options.system_prompt == "Custom prompt"
        assert aggregator.options.max_turns == 3


class TestMainCLI:
    """Test the main CLI function."""

    @patch("sys.argv", ["aggregator.py", "--test-connection"])
    @patch("hudson_news_bot.news.aggregator.test_connection")
    @patch("sys.exit")
    def test_main_test_connection_success(
        self, mock_exit: MagicMock, mock_test_connection: AsyncMock
    ) -> None:
        """Test main CLI with successful connection test."""
        mock_test_connection.return_value = True

        main()

        mock_exit.assert_called_once_with(0)

    @patch("sys.argv", ["aggregator.py", "--test-connection"])
    @patch("hudson_news_bot.news.aggregator.test_connection")
    @patch("sys.exit")
    def test_main_test_connection_failure(
        self, mock_exit: MagicMock, mock_test_connection: AsyncMock
    ) -> None:
        """Test main CLI with failed connection test."""
        mock_test_connection.return_value = False

        main()

        mock_exit.assert_called_once_with(1)

    @patch("sys.argv", ["aggregator.py"])
    @patch("argparse.ArgumentParser.print_help")
    def test_main_no_args(self, mock_print_help: MagicMock) -> None:
        """Test main CLI with no arguments."""
        main()

        mock_print_help.assert_called_once()

    @patch("sys.argv", ["aggregator.py", "--config", "/path/to/config.toml"])
    @patch("argparse.ArgumentParser.print_help")
    def test_main_config_only(self, mock_print_help: MagicMock) -> None:
        """Test main CLI with config argument only."""
        main()

        mock_print_help.assert_called_once()


class TestAggregateNews:
    """Test the aggregate_news method with comprehensive mocking."""

    @pytest.fixture
    def config(self) -> Config:
        config = MagicMock(spec=Config)
        config.system_prompt = "Test system prompt"
        config.claude_max_turns = 5
        config.max_articles = 3
        return config

    @pytest.fixture
    def aggregator(self, config: Config) -> NewsAggregator:
        return NewsAggregator(config)

    @pytest.fixture
    def sample_toml_response(self) -> str:
        return """```toml
[[news]]
headline = "Hudson Council Approves Budget"
summary = "The Hudson City Council approved a $50M budget for the upcoming fiscal year."
publication_date = "2025-08-14"
link = "https://hudsonohiotoday.com/budget-approval"

[[news]]
headline = "New Park Opens Downtown"
summary = "Hudson's newest park featuring walking trails and playground equipment opened to the public."
publication_date = "2025-08-13"
link = "https://hudsonohiotoday.com/new-park"
```"""

    @pytest.fixture
    def expected_news_collection(self) -> NewsCollection:
        return NewsCollection(
            [
                NewsItem(
                    headline="Hudson Council Approves Budget",
                    summary="The Hudson City Council approved a $50M budget for the upcoming fiscal year.",
                    publication_date=datetime(2025, 8, 14),
                    link="https://hudsonohiotoday.com/budget-approval",
                ),
                NewsItem(
                    headline="New Park Opens Downtown",
                    summary="Hudson's newest park featuring walking trails and playground equipment opened to the public.",
                    publication_date=datetime(2025, 8, 13),
                    link="https://hudsonohiotoday.com/new-park",
                ),
            ]
        )

    @pytest.mark.asyncio
    @patch("hudson_news_bot.news.aggregator.WebsiteScraper")
    @patch("hudson_news_bot.news.aggregator.ClaudeSDKClient")
    async def test_aggregate_news_success(
        self,
        mock_claude_client_class: MagicMock,
        mock_scraper_class: MagicMock,
        aggregator: NewsAggregator,
        sample_toml_response: str,
        expected_news_collection: NewsCollection,
    ) -> None:
        # Mock scraper
        mock_scraper_instance = AsyncMock()
        mock_scraper_class.return_value = mock_scraper_instance
        mock_scraper_instance.scrape_news_sites.return_value = [
            {
                "url": "https://hudsonohiotoday.com/article1",
                "headline": "Test Article",
                "date": "2025-08-14",
                "content": "Test content",
            }
        ]

        # Mock Claude client
        mock_client_instance = AsyncMock()
        mock_claude_client_class.return_value.__aenter__ = AsyncMock(
            return_value=mock_client_instance
        )
        mock_claude_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_message = MagicMock(spec=AssistantMessage)
        mock_text_block = MagicMock(spec=TextBlock)
        mock_text_block.text = sample_toml_response
        mock_message.content = [mock_text_block]

        async def mock_receive_response():
            yield mock_message

        mock_client_instance.receive_response = mock_receive_response

        result = await aggregator.aggregate_news()

        mock_client_instance.query.assert_called_once()
        query_call = mock_client_instance.query.call_args[0][0]
        assert "2025-" in query_call
        assert "Test Article" in query_call

        assert len(result) == 2
        assert result.news[0].headline == expected_news_collection.news[0].headline
        assert result.news[0].link == expected_news_collection.news[0].link
        assert result.news[1].headline == expected_news_collection.news[1].headline

    @pytest.mark.asyncio
    @patch("hudson_news_bot.news.aggregator.WebsiteScraper")
    @patch("hudson_news_bot.news.aggregator.ClaudeSDKClient")
    async def test_aggregate_news_no_response(
        self,
        mock_claude_client_class: MagicMock,
        mock_scraper_class: MagicMock,
        aggregator: NewsAggregator,
    ) -> None:
        # Mock scraper
        mock_scraper_instance = AsyncMock()
        mock_scraper_class.return_value = mock_scraper_instance
        mock_scraper_instance.scrape_news_sites.return_value = [
            {
                "url": "https://hudsonohiotoday.com/article1",
                "headline": "Test Article",
                "date": "2025-08-14",
                "content": "Test content",
            }
        ]

        # Mock Claude client
        mock_client_instance = AsyncMock()
        mock_claude_client_class.return_value.__aenter__ = AsyncMock(
            return_value=mock_client_instance
        )
        mock_claude_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        async def mock_receive_response():
            return
            yield

        mock_client_instance.receive_response = mock_receive_response

        with pytest.raises(Exception, match="No response received from Claude"):
            await aggregator.aggregate_news()

    @pytest.mark.asyncio
    @patch("hudson_news_bot.news.aggregator.WebsiteScraper")
    @patch("hudson_news_bot.news.aggregator.ClaudeSDKClient")
    async def test_aggregate_news_non_text_response(
        self,
        mock_claude_client_class: MagicMock,
        mock_scraper_class: MagicMock,
        aggregator: NewsAggregator,
    ) -> None:
        # Mock scraper
        mock_scraper_instance = AsyncMock()
        mock_scraper_class.return_value = mock_scraper_instance
        mock_scraper_instance.scrape_news_sites.return_value = [
            {
                "url": "https://hudsonohiotoday.com/article1",
                "headline": "Test Article",
                "date": "2025-08-14",
                "content": "Test content",
            }
        ]

        # Mock Claude client
        mock_client_instance = AsyncMock()
        mock_claude_client_class.return_value.__aenter__ = AsyncMock(
            return_value=mock_client_instance
        )
        mock_claude_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_message = MagicMock(spec=AssistantMessage)
        mock_non_text_block = MagicMock()
        mock_message.content = [mock_non_text_block]

        async def mock_receive_response():
            yield mock_message

        mock_client_instance.receive_response = mock_receive_response

        with pytest.raises(Exception, match="No response received from Claude"):
            await aggregator.aggregate_news()

    @pytest.mark.asyncio
    @patch("hudson_news_bot.news.aggregator.WebsiteScraper")
    @patch("hudson_news_bot.news.aggregator.ClaudeSDKClient")
    async def test_aggregate_news_invalid_toml(
        self,
        mock_claude_client_class: MagicMock,
        mock_scraper_class: MagicMock,
        aggregator: NewsAggregator,
    ) -> None:
        # Mock scraper
        mock_scraper_instance = AsyncMock()
        mock_scraper_class.return_value = mock_scraper_instance
        mock_scraper_instance.scrape_news_sites.return_value = [
            {
                "url": "https://hudsonohiotoday.com/article1",
                "headline": "Test Article",
                "date": "2025-08-14",
                "content": "Test content",
            }
        ]

        # Mock Claude client
        mock_client_instance = AsyncMock()
        mock_claude_client_class.return_value.__aenter__ = AsyncMock(
            return_value=mock_client_instance
        )
        mock_claude_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_message = MagicMock(spec=AssistantMessage)
        mock_text_block = MagicMock(spec=TextBlock)
        mock_text_block.text = "```toml\n[[news]]\nheadline = \n```"
        mock_message.content = [mock_text_block]

        async def mock_receive_response():
            yield mock_message

        mock_client_instance.receive_response = mock_receive_response

        with pytest.raises(ValueError, match="Failed to parse Claude response"):
            await aggregator.aggregate_news()

    @pytest.mark.asyncio
    @patch("hudson_news_bot.news.aggregator.WebsiteScraper")
    @patch("hudson_news_bot.news.aggregator.ClaudeSDKClient")
    async def test_aggregate_news_no_toml_content(
        self,
        mock_claude_client_class: MagicMock,
        mock_scraper_class: MagicMock,
        aggregator: NewsAggregator,
    ) -> None:
        # Mock scraper
        mock_scraper_instance = AsyncMock()
        mock_scraper_class.return_value = mock_scraper_instance
        mock_scraper_instance.scrape_news_sites.return_value = [
            {
                "url": "https://hudsonohiotoday.com/article1",
                "headline": "Test Article",
                "date": "2025-08-14",
                "content": "Test content",
            }
        ]

        # Mock Claude client
        mock_client_instance = AsyncMock()
        mock_claude_client_class.return_value.__aenter__ = AsyncMock(
            return_value=mock_client_instance
        )
        mock_claude_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_message = MagicMock(spec=AssistantMessage)
        mock_text_block = MagicMock(spec=TextBlock)
        mock_text_block.text = "Sorry, I couldn't find any news articles today."
        mock_message.content = [mock_text_block]

        async def mock_receive_response():
            yield mock_message

        mock_client_instance.receive_response = mock_receive_response

        with pytest.raises(ValueError, match="No valid TOML content found in response"):
            await aggregator.aggregate_news()


class TestResponseParsing:
    """Test response parsing methods."""

    @pytest.fixture
    def aggregator(self) -> NewsAggregator:
        config = MagicMock(spec=Config)
        config.system_prompt = "Test"
        config.claude_max_turns = 5
        config.max_articles = 10
        return NewsAggregator(config)

    def test_extract_toml_from_response_with_code_block(
        self, aggregator: NewsAggregator
    ) -> None:
        response = """Here are the news articles:

```toml
[[news]]
headline = "Test Article"
summary = "Test summary"
publication_date = "2025-08-14"
link = "https://example.com"
```

Let me know if you need more information."""

        result = aggregator.extract_toml_from_response(response)
        assert result is not None
        assert "[[news]]" in result
        assert "Test Article" in result

    def test_extract_toml_from_response_without_code_block(
        self, aggregator: NewsAggregator
    ) -> None:
        response = """[[news]]
headline = "Test Article"
summary = "Test summary"
publication_date = "2025-08-14"
link = "https://example.com"

Additional text after TOML"""

        result = aggregator.extract_toml_from_response(response)
        assert result is not None
        assert result.startswith("[[news]]")

    def test_extract_toml_from_response_no_toml(
        self, aggregator: NewsAggregator
    ) -> None:
        response = "Sorry, I couldn't find any news articles today."
        result = aggregator.extract_toml_from_response(response)
        assert result is None

    def test_create_analysis_prompt(self, aggregator: NewsAggregator) -> None:
        articles = [
            {
                "url": "https://hudsonohiotoday.com/article1",
                "headline": "Test Article 1",
                "date": "2025-08-14",
                "content": "Test content 1",
            },
            {
                "url": "https://beaconjournal.com/article2",
                "headline": "Test Article 2",
                "date": "2025-08-13",
                "content": "Test content 2",
            },
        ]
        prompt = aggregator.create_analysis_prompt(articles)

        assert "2025-" in prompt
        assert "Test Article 1" in prompt
        assert "Test Article 2" in prompt
        assert "hudsonohiotoday.com" in prompt
        assert "beaconjournal.com" in prompt
