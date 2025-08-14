"""Tests for Reddit API client - simplified version."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asyncpraw.exceptions import AsyncPRAWException, RedditAPIException  # type: ignore

from hudson_news_bot.config.settings import Config
from hudson_news_bot.news.models import NewsItem
from hudson_news_bot.reddit.client import RedditClient


class TestRedditClient:
    """Test Reddit API client functionality."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.mock_config = MagicMock(spec=Config)
        self.mock_config.reddit_client_id = "test_client_id"
        self.mock_config.reddit_client_secret = "test_client_secret"
        self.mock_config.reddit_user_agent = "test-bot/1.0"
        self.mock_config.reddit_username = "test_user"
        self.mock_config.reddit_password = "test_pass"
        self.mock_config.subreddit_name = "test"

        self.test_news_item = NewsItem(
            headline="Test News Headline",
            summary="Test summary",
            publication_date=datetime(2025, 8, 12),
            link="https://example.com/news",
        )

    def test_client_initialization(self) -> None:
        """Test RedditClient initialization."""
        client = RedditClient(self.mock_config)

        assert client.config == self.mock_config

    @pytest.mark.asyncio
    @patch.object(RedditClient, "_get_subreddit")
    async def test_submit_news_item_dry_run(
        self, mock_get_subreddit: MagicMock
    ) -> None:
        """Test news item submission in dry run mode."""
        client = RedditClient(self.mock_config)
        result = await client.submit_news_item(self.test_news_item, dry_run=True)

        assert result is None

    @pytest.mark.asyncio
    @patch.object(RedditClient, "_get_subreddit")
    async def test_submit_news_item_success(
        self, mock_get_subreddit: AsyncMock
    ) -> None:
        """Test successful news item submission."""
        mock_subreddit = MagicMock()
        mock_submission = MagicMock()
        mock_submission.url = "https://reddit.com/r/test/123"
        mock_subreddit.submit = AsyncMock(return_value=mock_submission)
        mock_get_subreddit.return_value = mock_subreddit

        client = RedditClient(self.mock_config)
        result = await client.submit_news_item(self.test_news_item, dry_run=False)

        assert result == mock_submission

    @pytest.mark.asyncio
    @patch.object(RedditClient, "_get_subreddit")
    async def test_submit_news_item_reddit_api_exception(
        self, mock_get_subreddit: AsyncMock
    ) -> None:
        """Test news item submission with Reddit API exception."""
        mock_subreddit = MagicMock()

        mock_error_item = MagicMock()
        mock_error_item.error_type = "ALREADY_SUBMITTED"
        mock_error_item.message = "That link has already been submitted"

        mock_exception = RedditAPIException([mock_error_item])
        mock_subreddit.submit = AsyncMock(side_effect=mock_exception)
        mock_get_subreddit.return_value = mock_subreddit

        client = RedditClient(self.mock_config)
        result = await client.submit_news_item(self.test_news_item, dry_run=False)

        assert result is None

    @pytest.mark.asyncio
    @patch.object(RedditClient, "_get_subreddit")
    async def test_submit_news_item_praw_exception(
        self, mock_get_subreddit: AsyncMock
    ) -> None:
        """Test news item submission with AsyncPRAW exception."""
        mock_subreddit = MagicMock()
        mock_subreddit.submit = AsyncMock(
            side_effect=AsyncPRAWException("AsyncPRAW error")
        )
        mock_get_subreddit.return_value = mock_subreddit

        client = RedditClient(self.mock_config)
        result = await client.submit_news_item(self.test_news_item, dry_run=False)

        assert result is None

    @pytest.mark.asyncio
    @patch.object(RedditClient, "submit_news_item")
    async def test_submit_multiple_news_items_dry_run(
        self, mock_submit: MagicMock
    ) -> None:
        """Test multiple news item submission in dry run mode."""
        mock_submit.return_value = None

        news_items = [self.test_news_item, self.test_news_item]
        client = RedditClient(self.mock_config)

        results = await client.submit_multiple_news_items(news_items, dry_run=True)

        assert len(results) == 2
        assert all(r is None for r in results)
        assert mock_submit.call_count == 2

    @pytest.mark.asyncio
    @patch.object(RedditClient, "_get_subreddit")
    async def test_search_submissions_success(
        self, mock_get_subreddit: AsyncMock
    ) -> None:
        """Test successful submission search."""
        mock_subreddit = MagicMock()
        mock_submissions = [MagicMock(), MagicMock()]

        # Create an async iterator mock
        async def async_iter():
            for submission in mock_submissions:
                yield submission

        mock_subreddit.search.return_value = async_iter()
        mock_get_subreddit.return_value = mock_subreddit

        client = RedditClient(self.mock_config)
        results = await client.search_submissions("test query", limit=50)

        assert results == mock_submissions

    @pytest.mark.asyncio
    @patch.object(RedditClient, "_get_subreddit")
    async def test_get_recent_submissions_success(
        self, mock_get_subreddit: AsyncMock
    ) -> None:
        """Test successful recent submissions retrieval."""
        mock_subreddit = MagicMock()
        mock_submissions = [MagicMock(), MagicMock()]

        # Create an async iterator mock
        async def async_iter():
            for submission in mock_submissions:
                yield submission

        mock_subreddit.new.return_value = async_iter()
        mock_get_subreddit.return_value = mock_subreddit

        client = RedditClient(self.mock_config)
        results = await client.get_recent_submissions(limit=25)

        assert results == mock_submissions

    @pytest.mark.asyncio
    @patch.object(RedditClient, "_get_reddit_instance")
    @patch.object(RedditClient, "_get_subreddit")
    async def test_test_connection_success(
        self, mock_get_subreddit: MagicMock, mock_get_reddit: MagicMock
    ) -> None:
        """Test successful connection test."""
        mock_reddit = MagicMock()
        mock_user = MagicMock()
        mock_user.name = "test_user"
        mock_reddit.user.me.return_value = mock_user
        mock_get_reddit.return_value = mock_reddit

        mock_subreddit = MagicMock()
        mock_subreddit.display_name = "test"
        mock_get_subreddit.return_value = mock_subreddit

        client = RedditClient(self.mock_config)
        result = await client.test_connection()

        assert result is True

    @pytest.mark.asyncio
    @patch.object(RedditClient, "_get_reddit_instance")
    async def test_test_connection_failure(self, mock_get_reddit: MagicMock) -> None:
        """Test connection test failure."""
        mock_get_reddit.side_effect = Exception("Connection failed")

        client = RedditClient(self.mock_config)
        result = await client.test_connection()

        assert result is False
