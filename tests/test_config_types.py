"""Tests for configuration TypedDict structures."""

from typing import get_type_hints

from hudson_news_bot.config.settings import (
    ConfigDict,
    NewsConfig,
    RedditConfig,
    ClaudeConfig,
    DatabaseConfig,
    DEFAULT_CONFIG,
)


def test_config_dict_structure():
    """Test that ConfigDict has the expected structure."""
    hints = get_type_hints(ConfigDict)

    assert "news" in hints
    assert "reddit" in hints
    assert "claude" in hints
    assert "database" in hints

    assert hints["news"] == NewsConfig
    assert hints["reddit"] == RedditConfig
    assert hints["claude"] == ClaudeConfig
    assert hints["database"] == DatabaseConfig


def test_news_config_structure():
    """Test that NewsConfig has the expected fields."""
    hints = get_type_hints(NewsConfig)

    assert "max_articles" in hints
    assert "system_prompt" in hints
    assert "news_sites" in hints

    assert hints["max_articles"] is int
    assert hints["system_prompt"] is str
    assert hints["news_sites"] == list[str]


def test_reddit_config_structure():
    """Test that RedditConfig has the expected fields."""
    hints = get_type_hints(RedditConfig)

    assert "subreddit" in hints
    assert "user_agent" in hints
    assert "check_for_duplicates" in hints
    assert "max_search_results" in hints

    assert hints["subreddit"] is str
    assert hints["user_agent"] is str
    assert hints["check_for_duplicates"] is bool
    assert hints["max_search_results"] is int


def test_claude_config_structure():
    """Test that ClaudeConfig has the expected fields."""
    hints = get_type_hints(ClaudeConfig)

    assert "max_turns" in hints
    assert "permission_mode" in hints
    assert "timeout_seconds" in hints

    assert hints["max_turns"] is int
    assert hints["permission_mode"] is str
    assert hints["timeout_seconds"] is int


def test_database_config_structure():
    """Test that DatabaseConfig has the expected fields."""
    hints = get_type_hints(DatabaseConfig)

    assert "path" in hints
    assert hints["path"] is str


def test_default_config_matches_typeddict():
    """Test that DEFAULT_CONFIG conforms to ConfigDict structure."""
    # This test verifies that DEFAULT_CONFIG has all required keys
    assert "news" in DEFAULT_CONFIG
    assert "reddit" in DEFAULT_CONFIG
    assert "claude" in DEFAULT_CONFIG
    assert "database" in DEFAULT_CONFIG

    # Check news config
    assert "max_articles" in DEFAULT_CONFIG["news"]
    assert "system_prompt" in DEFAULT_CONFIG["news"]
    assert "news_sites" in DEFAULT_CONFIG["news"]
    assert isinstance(DEFAULT_CONFIG["news"]["max_articles"], int)
    assert isinstance(DEFAULT_CONFIG["news"]["system_prompt"], str)
    assert isinstance(DEFAULT_CONFIG["news"]["news_sites"], list)

    # Check reddit config
    assert "subreddit" in DEFAULT_CONFIG["reddit"]
    assert "user_agent" in DEFAULT_CONFIG["reddit"]
    assert "check_for_duplicates" in DEFAULT_CONFIG["reddit"]
    assert "max_search_results" in DEFAULT_CONFIG["reddit"]
    assert isinstance(DEFAULT_CONFIG["reddit"]["subreddit"], str)
    assert isinstance(DEFAULT_CONFIG["reddit"]["user_agent"], str)
    assert isinstance(DEFAULT_CONFIG["reddit"]["check_for_duplicates"], bool)
    assert isinstance(DEFAULT_CONFIG["reddit"]["max_search_results"], int)

    # Check claude config
    assert "max_turns" in DEFAULT_CONFIG["claude"]
    assert "permission_mode" in DEFAULT_CONFIG["claude"]
    assert "timeout_seconds" in DEFAULT_CONFIG["claude"]
    assert isinstance(DEFAULT_CONFIG["claude"]["max_turns"], int)
    assert isinstance(DEFAULT_CONFIG["claude"]["permission_mode"], str)
    assert isinstance(DEFAULT_CONFIG["claude"]["timeout_seconds"], int)

    # Check database config
    assert "path" in DEFAULT_CONFIG["database"]
    assert isinstance(DEFAULT_CONFIG["database"]["path"], str)
