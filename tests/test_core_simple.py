"""
Simplified tests for core interfaces.
"""

from datetime import datetime, timedelta
from decimal import Decimal

from nautilus_trader.model.identifiers import StrategyId, Venue
from nautilus_trader.model.objects import Money, Currency

from crypto_trading_engine.models import TradingMode, BacktestResults
from crypto_trading_engine.core import TradingModeManager
from crypto_trading_engine.core.risk_manager import RiskLevel, RiskAlert, RiskAssessment


def test_trading_mode_manager():
    """Test TradingModeManager basic functionality."""
    manager = TradingModeManager()
    
    # Test initialization
    assert manager.current_mode == TradingMode.BACKTEST
    assert len(manager.strategies) == 0
    assert len(manager.adapters) == 0
    
    # Test mode transitions
    manager.set_trading_mode(TradingMode.PAPER, force=True)
    assert manager.current_mode == TradingMode.PAPER
    assert len(manager.mode_history) == 1
    
    # Test mode validation
    assert manager.validate_mode_transition(TradingMode.BACKTEST, TradingMode.PAPER)
    assert manager.validate_mode_transition(TradingMode.PAPER, TradingMode.LIVE)
    assert not manager.validate_mode_transition(TradingMode.BACKTEST, TradingMode.LIVE)
    
    print("✓ TradingModeManager tests passed")


def test_risk_alert():
    """Test RiskAlert functionality."""
    alert = RiskAlert(
        level=RiskLevel.MEDIUM,
        message="Test alert",
        strategy_id=StrategyId("test-strategy")
    )
    
    assert alert.level == RiskLevel.MEDIUM
    assert alert.message == "Test alert"
    assert alert.strategy_id == StrategyId("test-strategy")
    
    # Test serialization
    data = alert.to_dict()
    assert data['level'] == 'medium'
    assert data['message'] == 'Test alert'
    assert data['strategy_id'] == 'test-strategy'
    
    print("✓ RiskAlert tests passed")


def test_risk_assessment():
    """Test RiskAssessment functionality."""
    assessment = RiskAssessment(
        is_acceptable=True,
        risk_level=RiskLevel.LOW,
        message="Risk is acceptable",
        metrics={"var": 100.0}
    )
    
    assert assessment.is_acceptable
    assert assessment.risk_level == RiskLevel.LOW
    assert assessment.message == "Risk is acceptable"
    assert assessment.metrics["var"] == 100.0
    
    # Test serialization
    data = assessment.to_dict()
    assert data['is_acceptable'] is True
    assert data['risk_level'] == 'low'
    
    print("✓ RiskAssessment tests passed")


def test_backtest_results_promotion():
    """Test backtest results for strategy promotion."""
    strategy_id = StrategyId("test-strategy")
    usd = Currency.from_str('USD')
    
    # Good backtest results
    good_results = BacktestResults(
        strategy_id=strategy_id,
        start_date=datetime(2023, 1, 1),
        end_date=datetime(2023, 12, 31),
        total_return=Decimal('0.20'),
        sharpe_ratio=Decimal('1.5'),  # Above minimum 1.0
        max_drawdown=Decimal('0.08'), # Below maximum 0.1
        win_rate=Decimal('0.65'),     # Above minimum 0.5
        total_trades=100,             # Above minimum 50
        avg_trade_duration=timedelta(hours=2),
        transaction_costs=Money(100, usd)
    )
    
    manager = TradingModeManager()
    
    # Test promotion criteria validation
    validation = manager._validate_backtest_results(good_results)
    assert validation.is_valid
    
    # Bad backtest results
    bad_results = BacktestResults(
        strategy_id=strategy_id,
        start_date=datetime(2023, 1, 1),
        end_date=datetime(2023, 12, 31),
        total_return=Decimal('0.05'),
        sharpe_ratio=Decimal('0.5'),  # Below minimum 1.0
        max_drawdown=Decimal('0.15'), # Above maximum 0.1
        win_rate=Decimal('0.4'),      # Below minimum 0.5
        total_trades=30,              # Below minimum 50
        avg_trade_duration=timedelta(hours=2),
        transaction_costs=Money(100, usd)
    )
    
    validation = manager._validate_backtest_results(bad_results)
    assert not validation.is_valid
    
    print("✓ Backtest promotion tests passed")


if __name__ == "__main__":
    test_trading_mode_manager()
    test_risk_alert()
    test_risk_assessment()
    test_backtest_results_promotion()
    print("All core interface tests passed!")