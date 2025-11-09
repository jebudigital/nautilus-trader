"""
Tests for delta-neutral strategy implementation.
"""

import pytest
from decimal import Decimal
from datetime import datetime

from src.crypto_trading_engine.strategies.delta_neutral import (
    DeltaNeutralStrategy,
    DeltaNeutralConfig
)


class TestDeltaNeutralConfig:
    """Test delta-neutral configuration."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = DeltaNeutralConfig()
        
        assert config.target_instruments == ['BTC', 'ETH']
        assert config.max_position_size_usd == Decimal('10000')
        assert config.max_total_exposure_usd == Decimal('50000')
        assert config.rebalance_threshold_pct == Decimal('2')
        assert config.min_funding_rate_apy == Decimal('5')
        assert config.max_leverage == Decimal('3')
        assert config.spot_venue == "BINANCE"
        assert config.perp_venue == "DYDX"
    
    def test_custom_config(self):
        """Test custom configuration values."""
        config = DeltaNeutralConfig(
            target_instruments=['BTC'],
            max_position_size_usd=Decimal('5000'),
            rebalance_threshold_pct=Decimal('1')
        )
        
        assert config.target_instruments == ['BTC']
        assert config.max_position_size_usd == Decimal('5000')
        assert config.rebalance_threshold_pct == Decimal('1')
    
    def test_config_validation_positive_values(self):
        """Test that configuration validates positive values."""
        config = DeltaNeutralConfig(max_position_size_usd=Decimal('-100'))
        
        with pytest.raises(ValueError, match="Max position size must be positive"):
            config.validate()
    
    def test_config_validation_threshold_range(self):
        """Test that rebalance threshold is within valid range."""
        config = DeltaNeutralConfig(rebalance_threshold_pct=Decimal('150'))
        
        with pytest.raises(ValueError, match="Rebalance threshold must be between 0 and 100"):
            config.validate()
    
    def test_config_validation_leverage(self):
        """Test that leverage is positive."""
        config = DeltaNeutralConfig(max_leverage=Decimal('-1'))
        
        with pytest.raises(ValueError, match="Max leverage must be positive"):
            config.validate()


class TestDeltaNeutralStrategy:
    """Test delta-neutral strategy."""
    
    def test_strategy_initialization(self):
        """Test strategy initialization."""
        config = DeltaNeutralConfig()
        strategy = DeltaNeutralStrategy("test_strategy", config)
        
        assert strategy.strategy_id == "test_strategy"
        assert strategy.strategy_config == config
        assert len(strategy.spot_positions) == 0
        assert len(strategy.perp_positions) == 0
        assert strategy.total_funding_earned_usd == Decimal('0')
    
    def test_strategy_default_initialization(self):
        """Test strategy initialization with default config."""
        strategy = DeltaNeutralStrategy()
        
        assert strategy.strategy_id == "delta_neutral"
        assert strategy.strategy_config is not None
        assert isinstance(strategy.strategy_config, DeltaNeutralConfig)
    
    def test_target_delta_initialization(self):
        """Test that target delta is initialized to zero."""
        config = DeltaNeutralConfig(target_instruments=['BTC', 'ETH'])
        strategy = DeltaNeutralStrategy("test", config)
        
        # Target delta should be set after initialization
        # (would be set in on_initialize, but we can check the structure)
        assert hasattr(strategy, 'target_delta')
        assert hasattr(strategy, 'current_delta')
    
    def test_performance_summary(self):
        """Test performance summary generation."""
        strategy = DeltaNeutralStrategy()
        summary = strategy.get_performance_summary()
        
        assert 'total_funding_earned_usd' in summary
        assert 'total_rebalance_costs_usd' in summary
        assert 'net_profit_usd' in summary
        assert 'active_positions' in summary
        assert 'total_trades' in summary
        assert 'current_delta' in summary
        
        assert summary['total_funding_earned_usd'] == 0.0
        assert summary['active_positions'] == 0
        assert summary['total_trades'] == 0
    
    def test_multiple_instruments(self):
        """Test strategy with multiple instruments."""
        config = DeltaNeutralConfig(
            target_instruments=['BTC', 'ETH', 'SOL']
        )
        strategy = DeltaNeutralStrategy("multi_instrument", config)
        
        assert len(strategy.strategy_config.target_instruments) == 3
    
    def test_conservative_config(self):
        """Test conservative configuration."""
        config = DeltaNeutralConfig(
            max_position_size_usd=Decimal('5000'),
            rebalance_threshold_pct=Decimal('1'),
            min_funding_rate_apy=Decimal('10'),
            max_leverage=Decimal('2')
        )
        
        config.validate()  # Should not raise
        
        assert config.max_position_size_usd == Decimal('5000')
        assert config.rebalance_threshold_pct == Decimal('1')
        assert config.min_funding_rate_apy == Decimal('10')
        assert config.max_leverage == Decimal('2')
    
    def test_aggressive_config(self):
        """Test aggressive configuration."""
        config = DeltaNeutralConfig(
            max_position_size_usd=Decimal('50000'),
            rebalance_threshold_pct=Decimal('5'),
            min_funding_rate_apy=Decimal('3'),
            max_leverage=Decimal('10')
        )
        
        config.validate()  # Should not raise
        
        assert config.max_position_size_usd == Decimal('50000')
        assert config.rebalance_threshold_pct == Decimal('5')
        assert config.min_funding_rate_apy == Decimal('3')
        assert config.max_leverage == Decimal('10')


class TestDeltaCalculation:
    """Test delta calculation logic."""
    
    def test_initial_delta_is_zero(self):
        """Test that initial delta is zero."""
        strategy = DeltaNeutralStrategy()
        
        # Before any positions, delta should be zero
        for instrument in strategy.strategy_config.target_instruments:
            assert strategy.current_delta.get(instrument, Decimal('0')) == Decimal('0')
    
    def test_position_tracking_structures(self):
        """Test that position tracking structures exist."""
        strategy = DeltaNeutralStrategy()
        
        assert hasattr(strategy, 'spot_positions')
        assert hasattr(strategy, 'perp_positions')
        assert hasattr(strategy, 'spot_prices')
        assert hasattr(strategy, 'perp_prices')
        assert hasattr(strategy, 'funding_rates')
        assert isinstance(strategy.spot_positions, dict)
        assert isinstance(strategy.perp_positions, dict)


class TestRiskManagement:
    """Test risk management features."""
    
    def test_position_size_limits(self):
        """Test position size limits."""
        config = DeltaNeutralConfig(
            max_position_size_usd=Decimal('10000')
        )
        strategy = DeltaNeutralStrategy("test", config)
        
        assert strategy.strategy_config.max_position_size_usd == Decimal('10000')
    
    def test_total_exposure_limits(self):
        """Test total exposure limits."""
        config = DeltaNeutralConfig(
            max_total_exposure_usd=Decimal('50000')
        )
        strategy = DeltaNeutralStrategy("test", config)
        
        assert strategy.strategy_config.max_total_exposure_usd == Decimal('50000')
    
    def test_leverage_limits(self):
        """Test leverage limits."""
        config = DeltaNeutralConfig(
            max_leverage=Decimal('5')
        )
        strategy = DeltaNeutralStrategy("test", config)
        
        assert strategy.strategy_config.max_leverage == Decimal('5')
    
    def test_emergency_exit_threshold(self):
        """Test emergency exit threshold."""
        config = DeltaNeutralConfig(
            emergency_exit_loss_pct=Decimal('3')
        )
        strategy = DeltaNeutralStrategy("test", config)
        
        assert strategy.strategy_config.emergency_exit_loss_pct == Decimal('3')


class TestRebalancing:
    """Test rebalancing logic."""
    
    def test_rebalance_threshold(self):
        """Test rebalance threshold configuration."""
        config = DeltaNeutralConfig(
            rebalance_threshold_pct=Decimal('2')
        )
        strategy = DeltaNeutralStrategy("test", config)
        
        assert strategy.strategy_config.rebalance_threshold_pct == Decimal('2')
    
    def test_rebalance_cooldown(self):
        """Test rebalance cooldown period."""
        config = DeltaNeutralConfig(
            rebalance_cooldown_minutes=30
        )
        strategy = DeltaNeutralStrategy("test", config)
        
        assert strategy.strategy_config.rebalance_cooldown_minutes == 30
    
    def test_last_rebalance_tracking(self):
        """Test that last rebalance time is tracked."""
        strategy = DeltaNeutralStrategy()
        
        assert hasattr(strategy, 'last_rebalance_time')
        assert isinstance(strategy.last_rebalance_time, dict)


class TestFundingRates:
    """Test funding rate logic."""
    
    def test_min_funding_rate_requirement(self):
        """Test minimum funding rate requirement."""
        config = DeltaNeutralConfig(
            min_funding_rate_apy=Decimal('8')
        )
        strategy = DeltaNeutralStrategy("test", config)
        
        assert strategy.strategy_config.min_funding_rate_apy == Decimal('8')
    
    def test_funding_rate_tracking(self):
        """Test funding rate tracking structure."""
        strategy = DeltaNeutralStrategy()
        
        assert hasattr(strategy, 'funding_rates')
        assert isinstance(strategy.funding_rates, dict)
    
    def test_funding_earned_tracking(self):
        """Test funding earned tracking."""
        strategy = DeltaNeutralStrategy()
        
        assert hasattr(strategy, 'total_funding_earned_usd')
        assert strategy.total_funding_earned_usd == Decimal('0')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
