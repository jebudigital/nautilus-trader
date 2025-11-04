#!/usr/bin/env python3
"""
Backtesting Engine Demo

This script demonstrates the comprehensive backtesting capabilities of the
crypto trading engine. It shows how to:

1. Set up the backtesting environment
2. Create and configure trading strategies
3. Run backtests with realistic market simulation
4. Analyze performance metrics and results
5. Compare multiple strategies

The backtesting engine provides:
- Realistic order execution with slippage and market impact
- Transaction cost modeling for different venues
- Comprehensive performance metrics calculation
- Support for multiple instruments and timeframes
"""

import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from nautilus_trader.model.identifiers import InstrumentId, Venue

import sys
sys.path.append('.')

from src.crypto_trading_engine.data.models import DataType, TimeFrame
from src.crypto_trading_engine.data.store import HistoricalDataStore
from src.crypto_trading_engine.data.ingestion import DataIngestionEngine
from src.crypto_trading_engine.backtesting import (
    BacktestEngine, BacktestConfig, Money,
    SimpleMovingAverageStrategy, BuyAndHoldStrategy, Strategy
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MomentumStrategy(Strategy):
    """
    Example momentum strategy for demonstration.
    
    Buys when price increases by more than threshold over lookback period,
    sells when price decreases by more than threshold.
    """
    
    def __init__(self, strategy_id: str = "momentum", config=None):
        default_config = {
            "lookback_periods": 24,  # 24 hours for hourly data
            "momentum_threshold": 0.05,  # 5% price change
            "position_size": 0.2  # 20% of portfolio
        }
        
        if config:
            default_config.update(config)
        
        super().__init__(strategy_id, default_config)
        
        # Strategy state
        self.price_history = []
        self.current_position = None
    
    async def on_initialize(self, config):
        """Initialize the strategy."""
        self.log_info(f"Initializing Momentum strategy with {self.config['lookback_periods']} period lookback")
        self.price_history = []
        self.current_position = None
    
    async def on_market_data(self, data, market_state):
        """Process market data and make trading decisions."""
        current_price = float(data.close_price)
        self.price_history.append(current_price)
        
        # Keep only the data we need
        if len(self.price_history) > self.config['lookback_periods'] * 2:
            self.price_history = self.price_history[-self.config['lookback_periods'] * 2:]
        
        # Need enough history to calculate momentum
        if len(self.price_history) < self.config['lookback_periods']:
            return
        
        # Calculate momentum
        lookback_price = self.price_history[-self.config['lookback_periods']]
        momentum = (current_price - lookback_price) / lookback_price
        
        instrument_str = str(data.instrument_id)
        venue_str = str(data.venue)
        
        # Get current position
        position = self.get_position(instrument_str)
        
        # Trading logic
        if momentum > self.config['momentum_threshold']:
            # Strong upward momentum - go long
            if not position or position.side.value != 'long':
                await self._close_position(instrument_str, venue_str, position)
                await self._open_long_position(instrument_str, venue_str, market_state)
                
        elif momentum < -self.config['momentum_threshold']:
            # Strong downward momentum - go short
            if not position or position.side.value != 'short':
                await self._close_position(instrument_str, venue_str, position)
                await self._open_short_position(instrument_str, venue_str, market_state)
    
    async def _close_position(self, instrument_str, venue_str, position):
        """Close existing position."""
        if position and position.side.value != 'flat':
            side = 'sell' if position.side.value == 'long' else 'buy'
            await self.submit_market_order(
                instrument_str, venue_str, side, float(position.quantity)
            )
            self.log_info(f"Closed {position.side.value} position: {position.quantity}")
    
    async def _open_long_position(self, instrument_str, venue_str, market_state):
        """Open long position."""
        portfolio_value = self.get_portfolio_value()
        position_value = portfolio_value.amount * self.config['position_size']
        quantity = position_value / market_state.mid_price
        
        await self.submit_market_order(
            instrument_str, venue_str, 'buy', float(quantity)
        )
        self.log_info(f"Opened long position: {quantity} at {market_state.mid_price}")
    
    async def _open_short_position(self, instrument_str, venue_str, market_state):
        """Open short position."""
        portfolio_value = self.get_portfolio_value()
        position_value = portfolio_value.amount * self.config['position_size']
        quantity = position_value / market_state.mid_price
        
        await self.submit_market_order(
            instrument_str, venue_str, 'sell', float(quantity)
        )
        self.log_info(f"Opened short position: {quantity} at {market_state.mid_price}")


async def setup_test_data(data_engine):
    """Set up test data for backtesting."""
    logger.info("Setting up test data...")
    
    instruments = [
        (InstrumentId.from_str("BTCUSDT.BINANCE"), Venue("BINANCE")),
        (InstrumentId.from_str("ETHUSDT.BINANCE"), Venue("BINANCE")),
    ]
    
    start_time = datetime(2024, 1, 1)
    end_time = datetime(2024, 1, 14)  # Two weeks of data
    
    for instrument_id, venue in instruments:
        logger.info(f"Creating data for {instrument_id} on {venue}")
        
        job_id = await data_engine.create_ingestion_job(
            data_type=DataType.OHLCV,
            instrument_id=instrument_id,
            venue=venue,
            start_time=start_time,
            end_time=end_time,
            timeframe=TimeFrame.HOUR_1
        )
        
        await data_engine.start_ingestion_job(job_id)
        logger.info(f"Completed data ingestion for {instrument_id}")
    
    return instruments, start_time, end_time


async def run_strategy_backtest(backtest_engine, strategy, config, instruments, venues, timeframe):
    """Run backtest for a single strategy."""
    logger.info(f"Running backtest for {strategy.strategy_id}")
    
    try:
        results = await backtest_engine.run_backtest(
            strategy=strategy,
            config=config,
            instruments=instruments,
            venues=venues,
            timeframe=timeframe
        )
        
        logger.info(f"✅ Backtest completed for {strategy.strategy_id}")
        return results
        
    except Exception as e:
        logger.error(f"❌ Backtest failed for {strategy.strategy_id}: {e}")
        return None


def print_strategy_results(results):
    """Print formatted strategy results."""
    if not results:
        return
    
    print(f"\n{'='*60}")
    print(f"STRATEGY: {results.strategy_id.upper()}")
    print(f"{'='*60}")
    
    print(f"📊 PERFORMANCE SUMMARY")
    print(f"   Initial Capital:     ${results.initial_capital.amount:,.2f}")
    print(f"   Final Capital:       ${results.final_capital.amount:,.2f}")
    print(f"   Total Return:        {results.return_percentage:.2f}%")
    print(f"   Annualized Return:   {results.annualized_return * 100:.2f}%")
    
    print(f"\n📈 RISK METRICS")
    print(f"   Volatility:          {results.volatility * 100:.2f}%")
    print(f"   Sharpe Ratio:        {results.sharpe_ratio:.2f}")
    print(f"   Sortino Ratio:       {results.sortino_ratio:.2f}")
    print(f"   Max Drawdown:        {results.max_drawdown * 100:.2f}%")
    print(f"   Calmar Ratio:        {results.calmar_ratio:.2f}")
    
    print(f"\n🎯 TRADING STATISTICS")
    print(f"   Total Trades:        {results.total_trades}")
    print(f"   Winning Trades:      {results.winning_trades}")
    print(f"   Losing Trades:       {results.losing_trades}")
    print(f"   Win Rate:            {results.win_rate * 100:.1f}%")
    print(f"   Profit Factor:       {results.profit_factor:.2f}")
    
    print(f"\n💰 TRADE ANALYSIS")
    print(f"   Avg Winning Trade:   ${results.avg_winning_trade.amount:.2f}")
    print(f"   Avg Losing Trade:    ${results.avg_losing_trade.amount:.2f}")
    print(f"   Largest Win:         ${results.largest_winning_trade.amount:.2f}")
    print(f"   Largest Loss:        ${results.largest_losing_trade.amount:.2f}")
    
    print(f"\n💸 COSTS")
    print(f"   Total Commission:    ${results.total_commission.amount:.2f}")
    print(f"   Total Slippage:      ${results.total_slippage.amount:.2f}")


def compare_strategies(results_list):
    """Compare multiple strategy results."""
    if len(results_list) < 2:
        return
    
    print(f"\n{'='*80}")
    print(f"STRATEGY COMPARISON")
    print(f"{'='*80}")
    
    # Create comparison table
    headers = ["Strategy", "Return %", "Sharpe", "Max DD %", "Win Rate %", "Trades"]
    print(f"{headers[0]:<20} {headers[1]:<10} {headers[2]:<8} {headers[3]:<10} {headers[4]:<12} {headers[5]:<8}")
    print("-" * 80)
    
    for results in results_list:
        if results:
            print(f"{results.strategy_id:<20} "
                  f"{results.return_percentage:>9.2f} "
                  f"{results.sharpe_ratio:>7.2f} "
                  f"{results.max_drawdown * 100:>9.2f} "
                  f"{results.win_rate * 100:>11.1f} "
                  f"{results.total_trades:>7}")
    
    # Find best performing strategy
    best_return = max(results_list, key=lambda x: x.return_percentage if x else -float('inf'))
    best_sharpe = max(results_list, key=lambda x: x.sharpe_ratio if x else -float('inf'))
    best_drawdown = min(results_list, key=lambda x: x.max_drawdown if x else float('inf'))
    
    print(f"\n🏆 WINNERS:")
    print(f"   Best Return:     {best_return.strategy_id} ({best_return.return_percentage:.2f}%)")
    print(f"   Best Sharpe:     {best_sharpe.strategy_id} ({best_sharpe.sharpe_ratio:.2f})")
    print(f"   Lowest Drawdown: {best_drawdown.strategy_id} ({best_drawdown.max_drawdown * 100:.2f}%)")


async def main():
    """Main demo function."""
    logger.info("🚀 Starting Backtesting Engine Demo")
    
    # Initialize data storage
    data_path = "demo_backtest_data"
    parquet_path = Path(data_path) / "parquet"
    
    logger.info(f"📁 Initializing data storage at: {data_path}")
    
    # Create data store and ingestion engine
    store = HistoricalDataStore(data_path=data_path)
    await store.initialize()
    
    data_engine = DataIngestionEngine(
        data_store=store,
        parquet_path=str(parquet_path),
        max_workers=4
    )
    
    # Create backtesting engine
    backtest_engine = BacktestEngine(store, data_engine)
    
    # Set up test data
    instruments_data, start_time, end_time = await setup_test_data(data_engine)
    instruments = [data[0] for data in instruments_data]
    venues = [data[1] for data in instruments_data]
    
    # Backtest configuration
    config = BacktestConfig(
        start_date=start_time,
        end_date=end_time,
        initial_capital=Money(Decimal('100000'), 'USD'),
        commission_rate=Decimal('0.001'),  # 0.1%
        slippage_rate=Decimal('0.0005'),   # 0.05%
        market_impact_rate=Decimal('0.0001')  # 0.01%
    )
    
    logger.info(f"📊 Backtest Configuration:")
    logger.info(f"   Period: {config.start_date} to {config.end_date}")
    logger.info(f"   Initial Capital: ${config.initial_capital.amount:,.2f}")
    logger.info(f"   Commission Rate: {config.commission_rate * 100:.2f}%")
    logger.info(f"   Slippage Rate: {config.slippage_rate * 100:.3f}%")
    
    # Create strategies to test
    strategies = [
        BuyAndHoldStrategy("buy_and_hold", {"allocation": 0.95}),
        SimpleMovingAverageStrategy("sma_crossover", {
            "short_window": 12,
            "long_window": 26,
            "position_size": 0.8
        }),
        MomentumStrategy("momentum", {
            "lookback_periods": 24,
            "momentum_threshold": 0.03,
            "position_size": 0.6
        })
    ]
    
    logger.info(f"🎯 Testing {len(strategies)} strategies:")
    for strategy in strategies:
        logger.info(f"   - {strategy.strategy_id}")
    
    # Run backtests
    results_list = []
    
    for strategy in strategies:
        results = await run_strategy_backtest(
            backtest_engine, strategy, config, instruments, venues, TimeFrame.HOUR_1
        )
        results_list.append(results)
    
    # Display results
    logger.info("📋 Displaying detailed results...")
    
    for results in results_list:
        if results:
            print_strategy_results(results)
    
    # Compare strategies
    valid_results = [r for r in results_list if r is not None]
    if len(valid_results) > 1:
        compare_strategies(valid_results)
    
    # Demonstrate advanced analysis
    logger.info("\n🔍 Advanced Analysis Examples:")
    
    if valid_results:
        best_strategy = max(valid_results, key=lambda x: x.sharpe_ratio)
        
        print(f"\n📈 EQUITY CURVE ANALYSIS (Best Strategy: {best_strategy.strategy_id})")
        print(f"   Data Points: {len(best_strategy.equity_curve)}")
        
        if len(best_strategy.equity_curve) >= 10:
            # Show first and last few points
            print(f"   First 3 points:")
            for i, (timestamp, equity) in enumerate(best_strategy.equity_curve[:3]):
                print(f"     {timestamp}: ${equity:,.2f}")
            
            print(f"   ...")
            print(f"   Last 3 points:")
            for timestamp, equity in best_strategy.equity_curve[-3:]:
                print(f"     {timestamp}: ${equity:,.2f}")
        
        print(f"\n📊 POSITION ANALYSIS")
        print(f"   Final Positions: {len(best_strategy.positions)}")
        for position in best_strategy.positions:
            if position.side.value != 'flat':
                print(f"     {position.instrument_id}: {position.side.value} "
                      f"{position.quantity} @ ${position.avg_price}")
        
        print(f"\n💹 TRADE HISTORY")
        print(f"   Total Fills: {len(best_strategy.trades)}")
        if best_strategy.trades:
            print(f"   First Trade: {best_strategy.trades[0].timestamp} - "
                  f"{best_strategy.trades[0].side.value} {best_strategy.trades[0].quantity} "
                  f"@ ${best_strategy.trades[0].price}")
            print(f"   Last Trade:  {best_strategy.trades[-1].timestamp} - "
                  f"{best_strategy.trades[-1].side.value} {best_strategy.trades[-1].quantity} "
                  f"@ ${best_strategy.trades[-1].price}")
    
    # Performance insights
    print(f"\n💡 KEY INSIGHTS:")
    
    if valid_results:
        avg_return = sum(r.return_percentage for r in valid_results) / len(valid_results)
        avg_sharpe = sum(r.sharpe_ratio for r in valid_results) / len(valid_results)
        avg_drawdown = sum(r.max_drawdown for r in valid_results) / len(valid_results)
        
        print(f"   Average Return:    {avg_return:.2f}%")
        print(f"   Average Sharpe:    {avg_sharpe:.2f}")
        print(f"   Average Drawdown:  {avg_drawdown * 100:.2f}%")
        
        # Strategy recommendations
        if avg_sharpe > 1.0:
            print(f"   ✅ Strong risk-adjusted performance (Sharpe > 1.0)")
        elif avg_sharpe > 0.5:
            print(f"   ⚠️  Moderate risk-adjusted performance (Sharpe 0.5-1.0)")
        else:
            print(f"   ❌ Weak risk-adjusted performance (Sharpe < 0.5)")
        
        if avg_drawdown < 0.1:
            print(f"   ✅ Low drawdown risk (< 10%)")
        elif avg_drawdown < 0.2:
            print(f"   ⚠️  Moderate drawdown risk (10-20%)")
        else:
            print(f"   ❌ High drawdown risk (> 20%)")
    
    logger.info("🎉 Backtesting Demo completed successfully!")
    logger.info(f"📁 Demo data stored in: {data_path}")
    logger.info("💡 Key features demonstrated:")
    logger.info("   ✓ Realistic order execution simulation")
    logger.info("   ✓ Transaction cost modeling")
    logger.info("   ✓ Multiple strategy comparison")
    logger.info("   ✓ Comprehensive performance metrics")
    logger.info("   ✓ Risk-adjusted return analysis")
    logger.info("   ✓ Drawdown and trade statistics")


if __name__ == "__main__":
    asyncio.run(main())