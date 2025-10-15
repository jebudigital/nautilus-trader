"""
Configuration settings for the trading engine.
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional

from pydantic import BaseModel, Field

# For now, create a simple BaseSettings replacement
class BaseSettings(BaseModel):
    """Simple BaseSettings replacement for basic functionality."""
    
    class Config:
        env_file = ".env"
        env_nested_delimiter = "__"


class ExchangeConfig(BaseModel):
    """Configuration for exchange connections."""
    
    api_key: str = Field(..., description="Exchange API key")
    api_secret: str = Field(..., description="Exchange API secret")
    sandbox: bool = Field(default=True, description="Use sandbox/testnet")
    rate_limit: int = Field(default=10, description="Rate limit per second")


class Web3Config(BaseModel):
    """Configuration for Web3 connections."""
    
    provider_url: str = Field(..., description="Web3 provider URL")
    private_key: str = Field(..., description="Private key for transactions")
    gas_limit: int = Field(default=500000, description="Default gas limit")
    gas_price_gwei: float = Field(default=20.0, description="Gas price in Gwei")


class RiskConfig(BaseModel):
    """Risk management configuration."""
    
    max_portfolio_loss_pct: float = Field(default=5.0, description="Max daily loss %")
    max_position_size_pct: float = Field(default=10.0, description="Max position size %")
    max_leverage: float = Field(default=3.0, description="Maximum leverage")
    var_confidence: float = Field(default=0.95, description="VaR confidence level")


class TradingEngineConfig(BaseSettings):
    """Main trading engine configuration."""
    
    # Core settings
    trader_id: str = Field(default="TRADER-001", description="Unique trader ID")
    environment: str = Field(default="dev", description="Environment name")
    
    # Exchange configurations
    binance: Optional[ExchangeConfig] = None
    dydx: Optional[ExchangeConfig] = None
    
    # Web3 configuration
    web3: Optional[Web3Config] = None
    
    # Risk management
    risk: RiskConfig = Field(default_factory=RiskConfig)
    
    # Strategy settings
    strategies_enabled: list[str] = Field(default_factory=list)
    
    # Logging
    log_level: str = Field(default="INFO")
    log_file: Optional[str] = None
    
    class Config:
        env_file = ".env"
        env_nested_delimiter = "__"


def load_config(environment: str = "dev", config_path: Optional[Path] = None) -> TradingEngineConfig:
    """
    Load configuration for the specified environment.
    
    Args:
        environment: Environment name (dev, test, prod)
        config_path: Optional path to configuration file
        
    Returns:
        TradingEngineConfig: Loaded configuration
    """
    # Set environment variable for pydantic-settings
    os.environ["ENVIRONMENT"] = environment
    
    # Load base configuration
    config = TradingEngineConfig()
    
    # Load environment-specific overrides
    env_config_path = Path(f"config/{environment}.env")
    if env_config_path.exists():
        config = TradingEngineConfig(_env_file=env_config_path)
    
    # Load custom config file if provided
    if config_path and config_path.exists():
        config = TradingEngineConfig(_env_file=config_path)
    
    return config