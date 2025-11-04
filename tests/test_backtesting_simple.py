"""
Simple test for backtesting engine functionality.
"""

import asyncio
import pytest
import tempfile
import shutil
import logging
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from nautilus_trader.model.identifiers import InstrumentId, Venue

import sys
sys.path.append('.')

from src.crypto_trading_engine.data.models import DataType, TimeFrame
from src.crypto_trading_engine.data.store import HistoricalDataStore
from src.crypto_trading_engine.data.ingestion import DataIngestionEngine
from src.crypto_trading_engine.backtesting import (
    BacktestEngine, BacktestConfig, Money, BuyAndHoldStrategy
)

# Enable logging
logging.basicConfig(level=logging.INFO)


@pytest.mark.asyncio
async def test_basic_backtesting():
    """Test basic backtesting functionality."""
    # Create temporary directory
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Initialize data store
        store = HistoricalDataStore(data_path=temp_dir)
        await store.initialize()
        
        # Initialize data engine
        parquet_path = Path(temp_dir) / "parquet"
        data_engine = DataIngestionEngine(
            data_store=store,
            parquet_path=str(parquet_path),
            max_workers=2
        )
        
        # Create sample data
        instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
        venue = Venue("BINANCE")
        start_time = datetime(2024, 1, 1)
        end_time = datetime(2024, 1, 3)  # 2 days
        
        job_id = await data_engine.create_ingestion_job(
            data_type=DataType.OHLCV,
            instrument_id=instrument_id,
            venue=venue,
            start_time=start_time,
            end_time=end_time,
            timeframe=TimeFrame.HOUR_1
        )
        
        await data_engine.start_ingestion_job(job_id)
        print("✅ Sample data created")
        
        # Initialize backtesting engine
        backtest_engine = BacktestEngine(store, data_engine)
        
        # Create strategy
        strategy = BuyAndHoldStrategy("test_bnh")
        
        # Create config
        config = BacktestConfig(
            start_date=start_time,
            end_date=end_time,
            initial_capital=Money(Decimal('100000'), 'USD'),
            commission_rate=Decimal('0.001')
        )
        
        print("🚀 Starting backtest...")
        
        # Run backtest
        results = await backtest_engine.run_backtest(
            strategy=strategy,
            config=config,
            instruments=[instrument_id],
            venues=[venue],
            timeframe=TimeFrame.HOUR_1
        )
        
        print("✅ Backtest completed!")
        
        # Print results
        print(f"\n📊 RESULTS:")
        print(f"Strategy: {results.strategy_id}")
        print(f"Initial Capital: ${results.initial_capital.amount:,.2f}")
        print(f"Final Capital: ${results.final_capital.amount:,.2f}")
        print(f"Total Return: {results.return_percentage:.2f}%")
        print(f"Sharpe Ratio: {results.sharpe_ratio:.2f}")
        print(f"Max Drawdown: {results.max_drawdown * 100:.2f}%")
        print(f"Total Trades: {results.total_trades}")
        print(f"Win Rate: {results.win_rate * 100:.1f}%")
        
        # Validate results
        assert results.strategy_id == "test_bnh"
        assert results.initial_capital.amount == Decimal('100000')
        assert len(results.equity_curve) > 0
        assert len(results.trades) >= 1  # Check fills instead of trade count
        
        print("✅ All validations passed!")
        
    finally:
        # Cleanup
        shutil.rmtree(temp_dir)


if __name__ == "__main__":
    asyncio.run(test_basic_backtesting())