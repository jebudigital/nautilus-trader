"""
Pytest configuration and fixtures.
"""

import pytest
from pathlib import Path

from crypto_trading_engine.config.settings import TradingEngineConfig


@pytest.fixture
def test_config():
    """Provide a test configuration."""
    return TradingEngineConfig(
        trader_id="TEST-TRADER-001",
        environment="test",
        log_level="DEBUG",
    )


@pytest.fixture
def config_dir():
    """Provide path to config directory."""
    return Path(__file__).parent.parent / "config"