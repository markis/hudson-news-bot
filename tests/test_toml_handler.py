"""Tests for TOML handler utilities."""

import pytest
import tempfile
from datetime import datetime
from pathlib import Path

from hudson_news_bot.news.models import NewsItem, NewsCollection
from hudson_news_bot.utils.toml_handler import TOMLHandler


class TestTOMLHandler:
    """Test TOML handling utilities."""

    def test_validate_toml_syntax_valid(self) -> None:
        """Test validating valid TOML syntax."""
        valid_toml = """
[[news]]
headline = "Test Headline"
summary = "Test summary"
publication_date = "2025-08-12"
link = "https://example.com"
"""

        assert TOMLHandler.validate_toml_syntax(valid_toml) is True

    def test_validate_toml_syntax_invalid(self) -> None:
        """Test validating invalid TOML syntax."""
        invalid_toml = """
[[news]]
headline = "Test Headline
summary = "Test summary"
"""

        assert TOMLHandler.validate_toml_syntax(invalid_toml) is False

    def test_parse_news_toml(self) -> None:
        """Test parsing TOML into NewsCollection."""
        toml_content = """
[[news]]
headline = "Test Headline 1"
summary = "Test summary 1"
publication_date = "2025-08-12"
link = "https://example.com/1"

[[news]]
headline = "Test Headline 2"
summary = "Test summary 2"
publication_date = "2025-08-12"
link = "https://example.com/2"
"""

        collection = TOMLHandler.parse_news_toml(toml_content)

        assert len(collection) == 2

        item1 = list(collection)[0]
        assert item1.headline == "Test Headline 1"
        assert item1.summary == "Test summary 1"
        assert item1.publication_date.date() == datetime(2025, 8, 12).date()
        assert item1.link == "https://example.com/1"

        item2 = list(collection)[1]
        assert item2.headline == "Test Headline 2"

    def test_parse_news_toml_invalid_date(self) -> None:
        """Test parsing TOML with invalid date."""
        toml_content = """
[[news]]
headline = "Test Headline"
summary = "Test summary"
publication_date = "invalid-date"
link = "https://example.com"
"""

        collection = TOMLHandler.parse_news_toml(toml_content)

        assert len(collection) == 1
        # Should fallback to current date
        item = list(collection)[0]
        assert item.publication_date is not None

    def test_parse_news_toml_malformed(self) -> None:
        """Test parsing malformed TOML."""
        malformed_toml = "this is not valid toml"

        with pytest.raises(ValueError, match="Failed to parse TOML content"):
            TOMLHandler.parse_news_toml(malformed_toml)

    def test_write_news_toml(self) -> None:
        """Test writing NewsCollection to TOML file."""
        items = [
            NewsItem(
                "Test Headline",
                "Test summary",
                datetime(2025, 8, 12),
                "https://example.com",
            ),
        ]
        collection = NewsCollection(news=items)

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "test_news.toml"

            TOMLHandler.write_news_toml(collection, output_path)

            assert output_path.exists()

            # Read back and verify
            with open(output_path, "r", encoding="utf-8") as f:
                content = f.read()

            assert "Test Headline" in content
            assert "Test summary" in content
            assert "2025-08-12" in content
            assert "https://example.com" in content

    def test_load_config_existing_file(self) -> None:
        """Test loading configuration from existing file."""
        config_content = """
[section1]
key1 = "value1"
key2 = 123

[section2]
key3 = true
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(config_content)
            f.flush()

            try:
                config = TOMLHandler.load_config(f.name)

                assert config["section1"]["key1"] == "value1"
                assert config["section1"]["key2"] == 123
                assert config["section2"]["key3"] is True
            finally:
                Path(f.name).unlink()

    def test_load_config_missing_file(self) -> None:
        """Test loading configuration from missing file."""
        result = TOMLHandler.load_config("/path/that/does/not/exist.toml")
        assert result == {}
