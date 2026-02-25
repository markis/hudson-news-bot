"""Tests for news aggregator."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from hudson_news_bot.config.settings import Config
from hudson_news_bot.news.aggregator import NewsAggregator, main
from hudson_news_bot.news.models import NewsCollection, NewsItem
from hudson_news_bot.news.scraper import NewsItemDict


class TestNewsAggregator:
    """Test NewsAggregator class."""

    @pytest.fixture
    def config(self) -> Config:
        """Create test configuration."""
        config = MagicMock(spec=Config)
        config.system_prompt = "Test system prompt"
        config.max_articles = 10
        config.perplexity_api_key = "test-api-key"
        config.llm_base_url = "https://api.test.com"
        config.llm_timeout_seconds = 30
        config.llm_model = "test-model"
        config.llm_max_tokens = 4096
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
        assert aggregator.client is not None

    def test_config_integration(self) -> None:
        """Test that aggregator properly uses config values."""
        config = MagicMock(spec=Config)
        config.system_prompt = "Custom prompt"
        config.max_articles = 5
        config.perplexity_api_key = "test-api-key"
        config.llm_base_url = "https://api.test.com"
        config.llm_timeout_seconds = 30
        config.llm_model = "test-model"
        config.llm_max_tokens = 4096

        aggregator = NewsAggregator(config)

        assert aggregator.config.system_prompt == "Custom prompt"
        assert aggregator.config.max_articles == 5


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
        config.max_articles = 3
        config.news_sites = ["https://example.com"]
        config.perplexity_api_key = "test-api-key"
        config.llm_base_url = "https://api.test.com"
        config.llm_timeout_seconds = 30
        config.llm_model = "test-model"
        config.llm_max_tokens = 4096
        return config

    @pytest.fixture
    def aggregator(self, config: Config) -> NewsAggregator:
        return NewsAggregator(config)

    @pytest.fixture
    def sample_json_response(self) -> str:
        return """{
  "news": [
    {
      "headline": "Hudson Council Approves Budget",
      "summary": "The Hudson City Council approved a $50M budget for the upcoming fiscal year.",
      "publication_date": "2025-08-14",
      "link": "https://hudson.com/budget-approval"
    },
    {
      "headline": "New Park Opens Downtown",
      "summary": "Hudson's newest park featuring walking trails and playground equipment opened to the public.",
      "publication_date": "2025-08-13",
      "link": "https://hudson.com/new-park"
    }
  ]
}"""

    @pytest.fixture
    def expected_news_collection(self) -> NewsCollection:
        return NewsCollection(
            [
                NewsItem(
                    headline="Hudson Council Approves Budget",
                    summary="The Hudson City Council approved a $50M budget for the upcoming fiscal year.",
                    publication_date=datetime(2025, 8, 14),
                    link="https://hudson.com/budget-approval",
                ),
                NewsItem(
                    headline="New Park Opens Downtown",
                    summary="Hudson's newest park featuring walking trails and playground equipment opened to the public.",
                    publication_date=datetime(2025, 8, 13),
                    link="https://hudson.com/new-park",
                ),
            ]
        )

    @pytest.mark.asyncio
    @patch("hudson_news_bot.news.aggregator.WebsiteScraper")
    async def test_aggregate_news_success(
        self,
        mock_scraper_class: MagicMock,
        aggregator: NewsAggregator,
        sample_json_response: str,
        expected_news_collection: NewsCollection,
    ) -> None:
        # Mock scraper
        mock_scraper_instance = AsyncMock()
        mock_scraper_class.return_value = mock_scraper_instance
        mock_scraper_instance.scrape_news_sites.return_value = [
            {
                "url": "https://hudson.com/article1",
                "headline": "Test Article",
                "date": "2025-08-14",
                "content": "Test content",
            }
        ]

        # Mock OpenAI client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = sample_json_response

        aggregator.client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )

        result = await aggregator.aggregate_news()

        aggregator.client.chat.completions.create.assert_called_once()
        call_args = aggregator.client.chat.completions.create.call_args
        assert call_args[1]["model"] == "test-model"
        assert call_args[1]["max_tokens"] == 4096
        assert len(call_args[1]["messages"]) == 2
        assert "Test Article" in call_args[1]["messages"][1]["content"]

        assert len(result) == 2
        assert result.news[0].headline == expected_news_collection.news[0].headline
        assert result.news[0].link == expected_news_collection.news[0].link
        assert result.news[1].headline == expected_news_collection.news[1].headline

    @pytest.mark.asyncio
    @patch("hudson_news_bot.news.aggregator.WebsiteScraper")
    async def test_aggregate_news_no_response(
        self,
        mock_scraper_class: MagicMock,
        aggregator: NewsAggregator,
    ) -> None:
        # Mock scraper
        mock_scraper_instance = AsyncMock()
        mock_scraper_class.return_value = mock_scraper_instance
        mock_scraper_instance.scrape_news_sites.return_value = [
            {
                "url": "https://hudson.com/article1",
                "headline": "Test Article",
                "date": "2025-08-14",
                "content": "Test content",
            }
        ]

        # Mock OpenAI client with no content in response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None

        aggregator.client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )

        with pytest.raises(Exception, match="No response received from LLM"):
            await aggregator.aggregate_news()

    @pytest.mark.asyncio
    @patch("hudson_news_bot.news.aggregator.WebsiteScraper")
    async def test_aggregate_news_invalid_json(
        self,
        mock_scraper_class: MagicMock,
        aggregator: NewsAggregator,
    ) -> None:
        # Mock scraper
        mock_scraper_instance = AsyncMock()
        mock_scraper_class.return_value = mock_scraper_instance
        mock_scraper_instance.scrape_news_sites.return_value = [
            {
                "url": "https://hudson.com/article1",
                "headline": "Test Article",
                "date": "2025-08-14",
                "content": "Test content",
            }
        ]

        # Mock OpenAI client with invalid JSON (incomplete)
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"news": [{"headline": '

        aggregator.client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )

        with pytest.raises(Exception, match="LLM API request failed"):
            await aggregator.aggregate_news()

    @pytest.mark.asyncio
    @patch("hudson_news_bot.news.aggregator.WebsiteScraper")
    async def test_aggregate_news_with_flair(
        self,
        mock_scraper_class: MagicMock,
        aggregator: NewsAggregator,
    ) -> None:
        # Mock scraper
        mock_scraper_instance = AsyncMock()
        mock_scraper_class.return_value = mock_scraper_instance
        mock_scraper_instance.scrape_news_sites.return_value = [
            {
                "url": "https://hudson.com/article1",
                "headline": "Test Article",
                "date": "2025-08-14",
                "content": "Test content",
            }
        ]

        # Set up flair mapping
        aggregator.flair_mapping = {"Local News": "flair-template-123"}

        # Mock OpenAI client with structured JSON response including flair
        json_response = """{
  "news": [{
    "headline": "Hudson Council Approves Budget",
    "summary": "The Hudson City Council approved a $50M budget.",
    "publication_date": "2025-08-14",
    "link": "https://hudson.com/budget-approval",
    "flair": "Local News"
  }]
}"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json_response

        aggregator.client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )

        result = await aggregator.aggregate_news()

        assert len(result) == 1
        assert result.news[0].headline == "Hudson Council Approves Budget"
        assert result.news[0].flair_id == "flair-template-123"

    @pytest.mark.asyncio
    @patch("hudson_news_bot.news.aggregator.WebsiteScraper")
    async def test_aggregate_news_empty_results(
        self,
        mock_scraper_class: MagicMock,
        aggregator: NewsAggregator,
    ) -> None:
        # Mock scraper
        mock_scraper_instance = AsyncMock()
        mock_scraper_class.return_value = mock_scraper_instance
        mock_scraper_instance.scrape_news_sites.return_value = [
            {
                "url": "https://hudson.com/article1",
                "headline": "Test Article",
                "date": "2025-08-14",
                "content": "Test content",
            }
        ]

        # Mock OpenAI client with empty news array (valid JSON, no results)
        json_response = '{"news": []}'
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json_response

        aggregator.client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )

        result = await aggregator.aggregate_news()
        assert len(result) == 0


class TestResponseParsing:
    """Test response parsing methods."""

    @pytest.fixture
    def aggregator(self) -> NewsAggregator:
        config = MagicMock(spec=Config)
        config.system_prompt = "Test"
        config.max_articles = 10
        config.perplexity_api_key = "test-api-key"
        config.llm_base_url = "https://api.test.com"
        config.llm_timeout_seconds = 30
        config.llm_model = "test-model"
        config.llm_max_tokens = 4096
        return NewsAggregator(config)

    def test_create_analysis_prompt(self, aggregator: NewsAggregator) -> None:
        articles: list[NewsItemDict] = [
            NewsItemDict(
                url="https://hudson.com/article1",
                headline="Test Article 1",
                date="2025-08-14",
                content="Test content 1",
                summary="",
            ),
            NewsItemDict(
                url="https://beaconjournal.com/article2",
                headline="Test Article 2",
                date="2025-08-13",
                content="Test content 2",
                summary="",
            ),
        ]
        prompt = aggregator.create_analysis_prompt(articles)

        assert "2025-" in prompt
        assert "Test Article 1" in prompt
        assert "Test Article 2" in prompt
        assert "hudson.com" in prompt
        assert "beaconjournal.com" in prompt
