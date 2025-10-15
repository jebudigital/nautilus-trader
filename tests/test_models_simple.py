"""
Simplified unit tests for trading models.
"""

from datetime import datetime, timedelta
from decimal import Decimal

from nautilus_trader.model.identifiers import StrategyId
from nautilus_trader.model.objects import Money, Currency

from crypto_trading_engine.models import (
    TradingMode, BacktestResults, Token, UniswapPool
)


def test_trading_mode_enum():
    """Test TradingMode enum values."""
    assert TradingMode.BACKTEST.value == "backtest"
    assert TradingMode.PAPER.value == "paper"
    assert TradingMode.LIVE.value == "live"


def test_backtest_results():
    """Test BacktestResults model."""
    strategy_id = StrategyId("test-strategy")
    start_date = datetime(2023, 1, 1)
    end_date = datetime(2023, 12, 31)
    usd = Currency.from_str('USD')
    
    results = BacktestResults(
        strategy_id=strategy_id,
        start_date=start_date,
        end_date=end_date,
        total_return=Decimal('0.15'),
        sharpe_ratio=Decimal('1.2'),
        max_drawdown=Decimal('0.05'),
        win_rate=Decimal('0.6'),
        total_trades=100,
        avg_trade_duration=timedelta(hours=2),
        transaction_costs=Money(100, usd)
    )
    
    results.validate()
    
    # Test serialization
    data = results.to_dict()
    assert data['strategy_id'] == 'test-strategy'
    assert data['total_trades'] == 100


def test_token_model():
    """Test Token model."""
    token = Token(
        address="0x1234567890123456789012345678901234567890",
        symbol="USDC",
        decimals=6,
        name="USD Coin"
    )
    
    token.validate()
    
    # Test serialization
    data = token.to_dict()
    assert data['symbol'] == 'USDC'
    assert data['decimals'] == 6


def test_uniswap_pool():
    """Test UniswapPool model."""
    token0 = Token("0x1234", "USDC", 6, "USD Coin")
    token1 = Token("0x5678", "WETH", 18, "Wrapped Ether")
    
    pool = UniswapPool(
        address="0xabcd",
        token0=token0,
        token1=token1,
        fee_tier=3000,
        liquidity=Decimal('1000000'),
        sqrt_price_x96=1000000,
        tick=100,
        apy=0.15
    )
    
    pool.validate()
    
    # Test fee percentage calculation
    assert pool.get_fee_percentage() == Decimal('0.3')
    
    # Test serialization
    data = pool.to_dict()
    assert data['fee_tier'] == 3000
    assert data['apy'] == 0.15


if __name__ == "__main__":
    test_trading_mode_enum()
    test_backtest_results()
    test_token_model()
    test_uniswap_pool()
    print("All tests passed!")