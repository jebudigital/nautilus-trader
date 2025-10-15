"""
Tests for configuration management.
"""

import pytest
from pathlib import Path

from crypto_trading_engine.config.settings import load_config, TradingEngineConfig


def test_load_default_config():
    """Test loading default configuration."""
    config = load_config("test")
    
    assert config.environment == "test"
    assert config.trader_id is not None
    assert config.risk.max_portfolio_loss_pct > 0


def test_config_validation():
    """Test configuration validation."""
    config = TradingEngineConfig(
        trader_id="TEST-001",
        environment="test"
    )
    
    assert config.trader_id == "TEST-001"
    assert config.environment == "test"
    assert config.risk.max_leverage == 3.0  # Default value


def test_load_nonexistent_config():
    """Test loading configuration with nonexistent file."""
    config = load_config("nonexistent")
    
    # Should still return a valid config with defaults
    assert isinstance(config, TradingEngineConfig)
    assert config.environment == "nonexistent"