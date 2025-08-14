"""Simple tests for logging utilities."""

import logging
import tempfile
from pathlib import Path

from hudson_news_bot.utils.logging import setup_logging, get_logger


class TestLoggingUtilities:
    """Test logging configuration utilities."""

    def test_setup_logging_default(self) -> None:
        """Test default logging setup."""
        logger = setup_logging()

        assert logger is not None
        assert logger.name == "hudson_news_bot"
        assert logger.level == logging.INFO

    def test_setup_logging_debug_level(self) -> None:
        """Test logging setup with DEBUG level."""
        logger = setup_logging(level="DEBUG")

        assert logger.level == logging.DEBUG

    def test_setup_logging_with_file(self) -> None:
        """Test logging setup with file output."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "test.log"

            setup_logging(log_file=str(log_file))

            # Log file should be created
            assert log_file.exists()

    def test_get_logger(self) -> None:
        """Test getting a module-specific logger."""
        logger = get_logger("test_module")

        assert logger.name == "hudson_news_bot.test_module"
        assert isinstance(logger, logging.Logger)

    def test_module_level_loggers_exist(self) -> None:
        """Test that module-level logger instances are created."""
        from hudson_news_bot.utils.logging import (
            main_logger,
            news_logger,
            reddit_logger,
            config_logger,
        )

        assert main_logger.name == "hudson_news_bot.main"
        assert news_logger.name == "hudson_news_bot.news"
        assert reddit_logger.name == "hudson_news_bot.reddit"
        assert config_logger.name == "hudson_news_bot.config"
