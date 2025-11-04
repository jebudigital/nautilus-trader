"""
Tests for the backtesting engine.
"""

import asyncio
import pytest
import pytest_asyncio
import tempfile
import shutil
from datetime import datetime, timedelta
from decimal import Decimal

from nautilus_trader.model.identifiers import InstrumentId, Venue

import sys
sys.path.append('.')

from src.crypto_trading_engine.data.models import TimeFrame
from src.crypto_trading_engine.data.store import HistoricalDataStore
from src.crypto_trading_engine.data.ingestion import DataIngestionEngine
from src.crypto_trading_engine.backtesting import (
    BacktestEngine, BacktestConfig, Money, Strategy,
    SimpleMovingAverageStrategy, BuyAndHoldStrategy
)


@pytest.fixture
def temp_data_dir():
    """Create temporary directory for test data."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest_asyncio.fixture
async def data_store(temp_data_dir):
    """Create test data store."""
    store = HistoricalDataStore(data_path=temp_data_dir)
    await store.initialize()
    return store


@pytest_asyncio.fixture
async def data_engine(data_store, temp_data_dir):
    """Create test data ingestion engine."""
    from pathlib import Path
    parquet_path = Path(temp_data_dir) / "parquet"
    engine = DataIngestionEngine(
        data_store=data_store,
        parquet_path=str(parquet_path),
        max_workers=2
    )
    return engine


@pytest_asyncio.fixture
async def backtest_engine(data_store, data_engine):
    """Create test backtest engine."""
    engine = BacktestEngine(data_store, data_engine)
    return engine


@pytest_asyncio.fixture
async def sample_data(data_engine):
    """Create sample market data for testing."""
    from src.crypto_trading_engine.data.models import DataType
    
    instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
    venue = Venue("BINANCE")
    start_time = datetime(2024, 1, 1)
    end_time = datetime(2024, 1, 7)  # One week
    
    # Create ingestion job
    job_id = await data_engine.create_ingestion_job(
        data_type=DataType.OHLCV,
        instrument_id=instrument_id,
        venue=venue,
        start_time=start_time,
        end_time=end_time,
        timeframe=TimeFrame.HOUR_1
    )
    
    # Start ingestion
    await data_engine.start_ingestion_job(job_id)
    
    return {
        'instrument_id': instrument_id,
        'venue': venue,
        'start_time': start_time,
        'end_time': end_time,
        'timeframe': TimeFrame.HOUR_1
    }


class TestBacktestEngine:
    """Test cases for BacktestEngine."""
    
    @pytest.mark.asyncio
    async def test_engine_initialization(self, backtest_engine):
        """Test engine initialization."""
        assert backtest_engine.current_time is None
        assert backtest_engine.portfolio_value.amount == 0
        assert backtest_engine.cash_balance.amount == 0
        assert len(backtest_engine.positions) == 0
        assert len(backtest_engine.orders) == 0
        assert len(backtest_engine.fills) == 0
    
    @pytest.mark.asyncio
    async def test_backtest_config_validation(self):
        """Test backtest configuration validation."""
        # Valid config
        config = BacktestConfig(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 7),
            initial_capital=Money(Decimal('100000'), 'USD')
        )
        config.validate()  # Should not raise
        
        # Invalid config - start after end
        with pytest.raises(ValueError, match="Start date must be before end date"):
            invalid_config = BacktestConfig(
                start_date=datetime(2024, 1, 7),
                end_date=datetime(2024, 1, 1),
                initial_capital=Money(Decimal('100000'), 'USD')
            )
            invalid_config.validate()
        
        # Invalid config - negative capital
        with pytest.raises(ValueError, match="Initial capital must be positive"):
            invalid_config = BacktestConfig(
                start_date=datetime(2024, 1, 1),
                end_date=datetime(2024, 1, 7),
                initial_capital=Money(Decimal('-1000'), 'USD')
            )
            invalid_config.validate()
    
    @pytest.mark.asyncio
    async def test_buy_and_hold_strategy(self, backtest_engine, sample_data):
        """Test buy and hold strategy."""
        # Create strategy
        strategy = BuyAndHoldStrategy("test_bnh")
        
        # Create config
        config = BacktestConfig(
            start_date=sample_data['start_time'],
            end_date=sample_data['end_time'],
            initial_capital=Money(Decimal('100000'), 'USD'),
            commission_rate=Decimal('0.001')
        )
        
        # Run backtest
        results = await backtest_engine.run_backtest(
            strategy=strategy,
            config=config,
            instruments=[sample_data['instrument_id']],
            venues=[sample_data['venue']],
            timeframe=sample_data['timeframe']
        )
        
        # Validate results
        assert results.strategy_id == "test_bnh"
        assert results.initial_capital.amount == Decimal('100000')
        assert results.total_trades >= 1  # Should have at least one buy
        assert results.start_date == config.start_date
        assert results.end_date == config.end_date
        
        # Should have some equity curve data
        assert len(results.equity_curve) > 0
        
        # Validate results structure
        results.validate()
    
    @pytest.mark.asyncio
    async def test_sma_crossover_strategy(self, backtest_engine, sample_data):
        """Test simple moving average crossover strategy."""
        # Create strategy with short windows for testing
        strategy = SimpleMovingAverageStrategy(
            "test_sma",
            config={
                "short_window": 3,
                "long_window": 6,
                "position_size": 0.1
            }
        )
        
        # Create config
        config = BacktestConfig(
            start_date=sample_data['start_time'],
            end_date=sample_data['end_time'],
            initial_capital=Money(Decimal('100000'), 'USD'),
            commission_rate=Decimal('0.001'),
            slippage_rate=Decimal('0.0005')
        )
        
        # Run backtest
        results = await backtest_engine.run_backtest(
            strategy=strategy,
            config=config,
            instruments=[sample_data['instrument_id']],
            venues=[sample_data['venue']],
            timeframe=sample_data['timeframe']
        )
        
        # Validate results
        assert results.strategy_id == "test_sma"
        assert results.initial_capital.amount == Decimal('100000')
        assert results.start_date == config.start_date
        assert results.end_date == config.end_date
        
        # Should have equity curve data
        assert len(results.equity_curve) > 0
        
        # Performance metrics should be calculated
        assert results.sharpe_ratio is not None
        assert results.max_drawdown >= 0
        assert 0 <= results.win_rate <= 1
        
        # Validate results structure
        results.validate()
    
    @pytest.mark.asyncio
    async def test_portfolio_initialization(self, backtest_engine):
        """Test portfolio initialization."""
        initial_capital = Money(Decimal('50000'), 'USD')
        
        backtest_engine._initialize_portfolio(initial_capital)
        
        assert backtest_engine.cash_balance == initial_capital
        assert backtest_engine.portfolio_value == initial_capital
        assert len(backtest_engine.positions) == 0
        assert len(backtest_engine.orders) == 0
        assert len(backtest_engine.fills) == 0
    
    @pytest.mark.asyncio
    async def test_order_submission_and_execution(self, backtest_engine, sample_data):
        """Test order submission and execution."""
        from src.crypto_trading_engine.backtesting.models import (
            Order, OrderSide, OrderType
        )
        import uuid
        
        # Initialize portfolio
        initial_capital = Money(Decimal('100000'), 'USD')
        backtest_engine._initialize_portfolio(initial_capital)
        
        # Set current time
        backtest_engine.current_time = datetime(2024, 1, 1, 12, 0, 0)
        
        # Create market state
        from src.crypto_trading_engine.backtesting.models import MarketState
        market_state = MarketState(
            timestamp=backtest_engine.current_time,
            instrument_id=sample_data['instrument_id'],
            venue=sample_data['venue'],
            bid_price=Decimal('50000'),
            ask_price=Decimal('50010'),
            mid_price=Decimal('50005'),
            volume=Decimal('1000')
        )
        
        backtest_engine.market_states[str(sample_data['instrument_id'])] = market_state
        
        # Create and submit order
        order = Order(
            order_id=str(uuid.uuid4()),
            instrument_id=sample_data['instrument_id'],
            venue=sample_data['venue'],
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal('1.0')
        )
        
        # Submit order
        order_id = await backtest_engine.submit_order(order)
        assert order_id == order.order_id
        assert order_id in backtest_engine.orders
        
        # Execute order
        result = await backtest_engine._execute_order(order)
        
        assert result.executed is True
        assert len(result.fills) == 1
        assert result.fills[0].fill_quantity == Decimal('1.0')
        assert result.remaining_quantity == Decimal('0')
    
    @pytest.mark.asyncio
    async def test_performance_metrics_calculation(self, backtest_engine, sample_data):
        """Test performance metrics calculation."""
        # Create simple strategy for testing
        strategy = BuyAndHoldStrategy("test_metrics")
        
        config = BacktestConfig(
            start_date=sample_data['start_time'],
            end_date=sample_data['end_time'],
            initial_capital=Money(Decimal('100000'), 'USD')
        )
        
        # Run backtest
        results = await backtest_engine.run_backtest(
            strategy=strategy,
            config=config,
            instruments=[sample_data['instrument_id']],
            venues=[sample_data['venue']],
            timeframe=sample_data['timeframe']
        )
        
        # Check that all performance metrics are calculated
        assert results.total_return is not None
        assert results.annualized_return is not None
        assert results.volatility is not None
        assert results.sharpe_ratio is not None
        assert results.sortino_ratio is not None
        assert results.max_drawdown is not None
        assert results.calmar_ratio is not None
        assert results.win_rate is not None
        assert results.profit_factor is not None
        
        # Check that metrics are reasonable
        assert results.max_drawdown >= 0
        assert 0 <= results.win_rate <= 1
        assert results.total_trades >= 0
        assert results.winning_trades >= 0
        assert results.losing_trades >= 0
        assert results.winning_trades + results.losing_trades <= results.total_trades
    
    @pytest.mark.asyncio
    async def test_transaction_costs(self, backtest_engine, sample_data):
        """Test transaction cost calculation."""
        strategy = BuyAndHoldStrategy("test_costs")
        
        # Config with higher commission for testing
        config = BacktestConfig(
            start_date=sample_data['start_time'],
            end_date=sample_data['end_time'],
            initial_capital=Money(Decimal('100000'), 'USD'),
            commission_rate=Decimal('0.01'),  # 1% commission
            slippage_rate=Decimal('0.005')    # 0.5% slippage
        )
        
        results = await backtest_engine.run_backtest(
            strategy=strategy,
            config=config,
            instruments=[sample_data['instrument_id']],
            venues=[sample_data['venue']],
            timeframe=sample_data['timeframe']
        )
        
        # Should have transaction costs
        assert results.total_commission.amount > 0
        
        # Final capital should be less than initial due to costs
        # (assuming no significant price appreciation)
        cost_impact = results.total_commission.amount
        assert cost_impact > 0
    
    @pytest.mark.asyncio
    async def test_multiple_instruments(self, backtest_engine, data_engine):
        """Test backtesting with multiple instruments."""
        # Create data for multiple instruments
        instruments_data = []
        
        for symbol in ['BTCUSDT.BINANCE', 'ETHUSDT.BINANCE']:
            instrument_id = InstrumentId.from_str(symbol)
            venue = Venue("BINANCE")
            start_time = datetime(2024, 1, 1)
            end_time = datetime(2024, 1, 3)  # Shorter period for multiple instruments
            
            # Create ingestion job
            from src.crypto_trading_engine.data.models import DataType
            job_id = await data_engine.create_ingestion_job(
                data_type=DataType.OHLCV,
                instrument_id=instrument_id,
                venue=venue,
                start_time=start_time,
                end_time=end_time,
                timeframe=TimeFrame.HOUR_1
            )
            
            await data_engine.start_ingestion_job(job_id)
            
            instruments_data.append({
                'instrument_id': instrument_id,
                'venue': venue
            })
        
        # Create strategy
        strategy = BuyAndHoldStrategy("test_multi")
        
        config = BacktestConfig(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 3),
            initial_capital=Money(Decimal('100000'), 'USD')
        )
        
        # Run backtest with multiple instruments
        results = await backtest_engine.run_backtest(
            strategy=strategy,
            config=config,
            instruments=[data['instrument_id'] for data in instruments_data],
            venues=[data['venue'] for data in instruments_data],
            timeframe=TimeFrame.HOUR_1
        )
        
        # Should complete successfully
        assert results.strategy_id == "test_multi"
        assert len(results.equity_curve) > 0
    
    @pytest.mark.asyncio
    async def test_error_handling(self, backtest_engine):
        """Test error handling in backtesting."""
        strategy = BuyAndHoldStrategy("test_error")
        
        # Test with no market data
        config = BacktestConfig(
            start_date=datetime(2020, 1, 1),  # Date with no data
            end_date=datetime(2020, 1, 2),
            initial_capital=Money(Decimal('100000'), 'USD')
        )
        
        with pytest.raises(ValueError, match="No market data available"):
            await backtest_engine.run_backtest(
                strategy=strategy,
                config=config,
                instruments=[InstrumentId.from_str("NONEXISTENT.EXCHANGE")],
                venues=[Venue("NONEXISTENT")],
                timeframe=TimeFrame.HOUR_1
            )


if __name__ == "__main__":
    pytest.main([__file__])