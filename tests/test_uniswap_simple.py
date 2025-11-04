"""
Simple test for Uniswap Lending Strategy functionality.
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
from src.crypto_trading_engine.backtesting import BacktestEngine, BacktestConfig, Money
from src.crypto_trading_engine.strategies import UniswapLendingStrategy
from src.crypto_trading_engine.strategies.models import StrategyConfig, LiquidityRange

# Enable logging
logging.basicConfig(level=logging.INFO)


@pytest.mark.asyncio
async def test_uniswap_strategy():
    """Test basic Uniswap strategy functionality."""
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
        instrument_id = InstrumentId.from_str("ETHUSDT.BINANCE")
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
        
        # Create strategy with test-friendly config
        strategy_config = StrategyConfig(
            min_tvl_usd=Decimal('1000'),        # Low threshold for testing
            min_volume_24h_usd=Decimal('100'),   # Low threshold for testing
            min_fee_apy=Decimal('1'),            # Low threshold for testing
            max_impermanent_loss=Decimal('20'),  # High tolerance for testing
            max_position_size_usd=Decimal('5000'),
            max_total_exposure_usd=Decimal('25000'),
            liquidity_range=LiquidityRange.MEDIUM,
            range_width_percentage=Decimal('15'),
            max_gas_price_gwei=Decimal('100'),   # High for testing
            min_profit_threshold_usd=Decimal('1')
        )
        
        strategy = UniswapLendingStrategy("test_uniswap", strategy_config)
        
        # Create config
        config = BacktestConfig(
            start_date=start_time,
            end_date=end_time,
            initial_capital=Money(Decimal('50000'), 'USD'),
            commission_rate=Decimal('0.001')
        )
        
        print("🚀 Starting Uniswap strategy backtest...")
        
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
        print(f"\n📊 BACKTEST RESULTS:")
        print(f"Strategy: {results.strategy_id}")
        print(f"Initial Capital: ${results.initial_capital.amount:,.2f}")
        print(f"Final Capital: ${results.final_capital.amount:,.2f}")
        print(f"Total Return: {results.return_percentage:.2f}%")
        print(f"Sharpe Ratio: {results.sharpe_ratio:.2f}")
        print(f"Max Drawdown: {results.max_drawdown * 100:.2f}%")
        print(f"Total Trades: {results.total_trades}")
        
        # Get strategy-specific performance
        performance = await strategy.get_strategy_performance()
        print(f"\n📈 UNISWAP STRATEGY PERFORMANCE:")
        print(f"Active Positions: {performance['active_positions']}")
        print(f"Total Exposure: ${performance['total_exposure_usd']:,.2f}")
        print(f"Fees Earned: ${performance['total_fees_earned_usd']:,.2f}")
        print(f"Impermanent Loss: ${performance['total_impermanent_loss_usd']:,.2f}")
        print(f"Gas Costs: ${performance['total_gas_costs_usd']:,.2f}")
        print(f"Net Profit: ${performance['net_profit_usd']:,.2f}")
        print(f"Pools Monitored: {performance['pools_monitored']}")
        
        # Get position summary
        position_summary = strategy.get_position_summary()
        if position_summary:
            print(f"\n💰 ACTIVE POSITIONS:")
            for pos in position_summary:
                print(f"  {pos['token_pair']} ({pos['fee_tier']:.2f}%): "
                      f"IL={pos['impermanent_loss_pct']:.2f}%, "
                      f"Fees=${pos['fees_earned_usd']:.2f}, "
                      f"Net=${pos['net_profit_usd']:.2f}")
        else:
            print(f"\n💰 No active positions")
        
        # Validate results
        assert results.strategy_id == "test_uniswap"
        assert results.initial_capital.amount == Decimal('50000')
        assert len(results.equity_curve) > 0
        
        # Validate strategy performance
        assert performance['pools_monitored'] > 0
        assert performance['active_positions'] >= 0
        assert performance['total_exposure_usd'] >= 0
        
        print("✅ All validations passed!")
        
        # Test individual components
        print(f"\n🔧 TESTING INDIVIDUAL COMPONENTS:")
        
        # Test impermanent loss calculator
        from src.crypto_trading_engine.strategies.models import ImpermanentLossCalculator
        
        # Test no price change
        il_no_change = ImpermanentLossCalculator.calculate_theoretical_il(Decimal('1.0'))
        print(f"IL with no price change: {il_no_change * 100:.4f}%")
        assert abs(il_no_change) < Decimal('0.001')
        
        # Test 2x price increase
        il_2x = ImpermanentLossCalculator.calculate_theoretical_il(Decimal('2.0'))
        print(f"IL with 2x price increase: {il_2x * 100:.2f}%")
        assert il_2x < 0  # Should be negative (loss)
        
        # Test breakeven APY calculation
        breakeven_apy = ImpermanentLossCalculator.calculate_breakeven_fee_apy(
            Decimal('2.0'), 30
        )
        print(f"Breakeven APY for 2x price change over 30 days: {breakeven_apy:.2f}%")
        assert breakeven_apy > 0
        
        # Test gas optimizer
        gas_estimate = strategy.gas_optimizer.estimate_gas_cost(
            'mint_position', Decimal('50'), Decimal('2000')
        )
        print(f"Gas estimate for minting position: ${gas_estimate.gas_cost_usd:.2f}")
        assert gas_estimate.gas_cost_usd > 0
        
        should_execute = strategy.gas_optimizer.should_execute_now(
            'mint_position', Decimal('30'), Decimal('100'), Decimal('2000')
        )
        print(f"Should execute with 30 Gwei and $100 profit: {should_execute}")
        
        print("✅ Component tests passed!")
        
    finally:
        # Cleanup
        shutil.rmtree(temp_dir)


if __name__ == "__main__":
    asyncio.run(test_uniswap_strategy())