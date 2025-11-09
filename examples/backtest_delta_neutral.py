"""
Backtest Delta-Neutral Strategy

Run backtest using Nautilus BacktestEngine with historical data.
"""

import sys
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timedelta

# Add project root
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.model.identifiers import Venue, InstrumentId, Symbol
from nautilus_trader.model.currencies import USD, BTC, USDT
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.model.enums import OmsType, AccountType
from nautilus_trader.model.instruments import CurrencyPair, CryptoPerpetual
from nautilus_trader.test_kit.providers import TestInstrumentProvider

from src.crypto_trading_engine.strategies.delta_neutral_nautilus import (
    DeltaNeutralStrategy,
    DeltaNeutralConfig
)
from src.crypto_trading_engine.data.parquet_loader import ParquetDataLoader


async def run_backtest(start_date: str = None, end_date: str = None):
    """
    Run backtest for delta-neutral strategy.
    
    Args:
        start_date: Start date (YYYY-MM-DD), defaults to 7 days ago
        end_date: End date (YYYY-MM-DD), defaults to today
    """
    print("\n" + "="*60)
    print("🔬 Delta-Neutral Strategy Backtest")
    print("="*60)
    
    # Backtest period
    if not start_date:
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")
    
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    days = (end - start).days
    
    print(f"\n📅 Period: {start_date} to {end_date}")
    print(f"📊 Duration: {days} days")
    
    # Create backtest engine
    engine = BacktestEngine()
    
    print("\n⚙️  Configuring backtest engine...")
    
    # Add venues
    engine.add_venue(
        venue=Venue("BINANCE"),
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,  # Use MARGIN for multi-currency
        base_currency=USD,
        starting_balances=[Money(10000, USD)],
    )
    
    engine.add_venue(
        venue=Venue("DYDX_V4"),
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        base_currency=USD,
        starting_balances=[Money(10000, USD)],
    )
    
    print("  ✅ Venues configured")
    
    # Add instruments
    print("\n📊 Loading instruments...")
    
    # Binance BTCUSDT spot (real exchange specifications)
    btc_spot = CurrencyPair(
        instrument_id=InstrumentId(Symbol("BTCUSDT"), Venue("BINANCE")),
        raw_symbol=Symbol("BTCUSDT"),
        base_currency=BTC,
        quote_currency=USDT,
        price_precision=2,  # Binance uses 2 decimals for BTCUSDT
        size_precision=5,   # Binance uses 5 decimals for BTC quantity
        price_increment=Price.from_str("0.01"),
        size_increment=Quantity.from_str("0.00001"),
        lot_size=Quantity.from_str("0.00001"),
        max_quantity=Quantity.from_str("9000.0"),
        min_quantity=Quantity.from_str("0.00001"),
        max_price=Price.from_str("1000000.0"),
        min_price=Price.from_str("0.01"),
        margin_init=Decimal("0"),
        margin_maint=Decimal("0"),
        maker_fee=Decimal("0.001"),
        taker_fee=Decimal("0.001"),
        ts_event=0,
        ts_init=0,
    )
    engine.add_instrument(btc_spot)
    print(f"  ✅ Added {btc_spot.id}")
    
    # dYdX BTC-USD perpetual (real exchange specifications)
    btc_perp = CryptoPerpetual(
        instrument_id=InstrumentId(Symbol("BTC-USD"), Venue("DYDX_V4")),
        raw_symbol=Symbol("BTC-USD"),
        base_currency=BTC,
        quote_currency=USD,
        settlement_currency=USD,
        is_inverse=False,
        price_precision=1,  # dYdX uses 1 decimal for BTC-USD
        size_precision=4,   # dYdX uses 4 decimals for size
        price_increment=Price.from_str("0.1"),
        size_increment=Quantity.from_str("0.0001"),
        max_quantity=Quantity.from_str("1000.0"),
        min_quantity=Quantity.from_str("0.0001"),
        max_price=Price.from_str("1000000.0"),
        min_price=Price.from_str("0.1"),
        margin_init=Decimal("0.1"),
        margin_maint=Decimal("0.05"),
        maker_fee=Decimal("0.0002"),
        taker_fee=Decimal("0.0005"),
        ts_event=0,
        ts_init=0,
    )
    engine.add_instrument(btc_perp)
    print(f"  ✅ Added {btc_perp.id}")
    
    # Load historical data from Parquet
    print("\n📈 Loading historical data...")
    
    loader = ParquetDataLoader()
    
    # Check if data is available
    is_available, error_msg = loader.check_data_availability(start_date, end_date)
    
    if not is_available:
        print("\n❌ Data not available for the specified date range")
        print(error_msg)
        print("\n💡 To load data, run:")
        print(f"   python scripts/load_historical_data.py --start {start_date} --end {end_date}")
        return
    
    # Load data
    try:
        data = loader.load_data(start_date, end_date)
    except FileNotFoundError as e:
        print(f"\n❌ Error loading data: {e}")
        return
    
    # Add data to backtest engine
    print("\n📊 Adding data to backtest engine...")
        
    # Add Binance data
    binance_bars = data.get('binance_bars', [])
    binance_ticks = data.get('binance_ticks', [])
    if binance_bars:
        engine.add_data(binance_bars)
        print(f"  ✅ Added {len(binance_bars)} Binance bars")
    if binance_ticks:
        engine.add_data(binance_ticks)
        print(f"  ✅ Added {len(binance_ticks)} Binance quote ticks")
    
    # Add dYdX data
    dydx_bars = data.get('dydx_bars', [])
    dydx_ticks = data.get('dydx_ticks', [])
    if dydx_bars:
        engine.add_data(dydx_bars)
        print(f"  ✅ Added {len(dydx_bars)} dYdX bars")
    if dydx_ticks:
        engine.add_data(dydx_ticks)
        print(f"  ✅ Added {len(dydx_ticks)} dYdX quote ticks")
    
    # Add funding rates as data (Nautilus FundingRateUpdate)
    funding_rates = data.get('dydx_funding', [])
    if funding_rates:
        engine.add_data(funding_rates)
        print(f"  ✅ Added {len(funding_rates)} funding rate events")
    
    # Create strategy
    print("\n🎯 Creating strategy...")
    strategy_config = DeltaNeutralConfig(
        spot_instrument="BTCUSDT.BINANCE",
        perp_instrument="BTC-USD.DYDX_V4",
        max_position_size_usd=5000.0,
        rebalance_threshold_pct=2.0,
        min_funding_rate_apy=2.0,  # Realistic threshold (was 6.0, but rates rarely exceed 5%)
    )
    
    strategy = DeltaNeutralStrategy(config=strategy_config)
    engine.add_strategy(strategy)
    print(f"  ✅ Strategy added: {strategy.id}")
    
    # Run backtest
    print("\n🚀 Running backtest...")
    
    if (binance_bars or binance_ticks) and (dydx_bars or dydx_ticks):
        total_data = len(binance_bars) + len(dydx_bars) + len(binance_ticks) + len(dydx_ticks)
        print(f"  📊 Processing {total_data} data points")
        
        # Run the backtest
        engine.run()
        
        # Get results
        print("\n" + "="*60)
        print("📊 BACKTEST RESULTS")
        print("="*60)
        
        # Get account states
        binance_account = engine.trader.generate_account_report(Venue("BINANCE"))
        dydx_account = engine.trader.generate_account_report(Venue("DYDX_V4"))
        
        # Get order and position reports
        order_fills = engine.trader.generate_order_fills_report()
        positions = engine.trader.generate_positions_report()
        
        # Calculate summary statistics
        print("\n💰 ACCOUNT SUMMARY")
        print("-" * 60)
        
        # Parse account data
        binance_start = 10000.0
        dydx_start = 10000.0
        
        # Get final balances from the last row
        if not binance_account.empty:
            binance_end = float(binance_account.iloc[-1]['total'])
        else:
            binance_end = binance_start
            
        if not dydx_account.empty:
            dydx_end = float(dydx_account.iloc[-1]['total'])
        else:
            dydx_end = dydx_start
        
        binance_pnl = binance_end - binance_start
        dydx_pnl = dydx_end - dydx_start
        total_pnl = binance_pnl + dydx_pnl
        total_return = (total_pnl / (binance_start + dydx_start)) * 100
        
        print(f"\n📈 Binance (Spot):")
        print(f"   Starting Balance:  ${binance_start:,.2f}")
        print(f"   Ending Balance:    ${binance_end:,.2f}")
        print(f"   P&L:               ${binance_pnl:+,.2f} ({(binance_pnl/binance_start)*100:+.2f}%)")
        
        print(f"\n📉 dYdX (Perpetual):")
        print(f"   Starting Balance:  ${dydx_start:,.2f}")
        print(f"   Ending Balance:    ${dydx_end:,.2f}")
        print(f"   P&L:               ${dydx_pnl:+,.2f} ({(dydx_pnl/dydx_start)*100:+.2f}%)")
        
        print(f"\n💵 Combined Portfolio:")
        print(f"   Starting Capital:  ${binance_start + dydx_start:,.2f}")
        print(f"   Ending Capital:    ${binance_end + dydx_end:,.2f}")
        print(f"   Total P&L:         ${total_pnl:+,.2f}")
        print(f"   Total Return:      {total_return:+.2f}%")
        
        # Trading statistics
        print("\n" + "-" * 60)
        print("📋 TRADING STATISTICS")
        print("-" * 60)
        
        num_fills = len(order_fills) if not order_fills.empty else 0
        num_positions = len(positions) if not positions.empty else 0
        
        # Count closed positions
        if not positions.empty and 'ts_closed' in positions.columns:
            closed_positions = positions[positions['ts_closed'] > 0]
            num_closed = len(closed_positions)
        else:
            num_closed = 0
        
        print(f"\n   Total Order Fills:     {num_fills:,}")
        print(f"   Total Positions:       {num_positions:,}")
        print(f"   Closed Positions:      {num_closed:,}")
        print(f"   Open Positions:        {num_positions - num_closed:,}")
        
        # Calculate win rate if we have closed positions
        if not positions.empty and 'realized_pnl' in positions.columns:
            closed_pos = positions[positions['ts_closed'] > 0]
            if len(closed_pos) > 0:
                # Parse realized_pnl (format: "123.45 USD")
                realized_pnls = []
                for pnl_str in closed_pos['realized_pnl']:
                    try:
                        # Extract numeric value from string like "-5.00117965 USDT"
                        pnl_value = float(str(pnl_str).split()[0])
                        realized_pnls.append(pnl_value)
                    except:
                        pass
                
                if realized_pnls:
                    winning_trades = sum(1 for pnl in realized_pnls if pnl > 0)
                    losing_trades = sum(1 for pnl in realized_pnls if pnl < 0)
                    total_trades = len(realized_pnls)
                    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
                    
                    avg_win = sum(pnl for pnl in realized_pnls if pnl > 0) / winning_trades if winning_trades > 0 else 0
                    avg_loss = sum(pnl for pnl in realized_pnls if pnl < 0) / losing_trades if losing_trades > 0 else 0
                    
                    print(f"\n   Winning Trades:        {winning_trades:,}")
                    print(f"   Losing Trades:         {losing_trades:,}")
                    print(f"   Win Rate:              {win_rate:.1f}%")
                    if avg_win > 0:
                        print(f"   Average Win:           ${avg_win:,.2f}")
                    if avg_loss < 0:
                        print(f"   Average Loss:          ${avg_loss:,.2f}")
        
        # Time period
        print("\n" + "-" * 60)
        print("📅 BACKTEST PERIOD")
        print("-" * 60)
        print(f"\n   Start Date:  {start_date}")
        print(f"   End Date:    {end_date}")
        print(f"   Duration:    {days} days")
        
        # Strategy parameters
        print("\n" + "-" * 60)
        print("⚙️  STRATEGY PARAMETERS")
        print("-" * 60)
        print(f"\n   Position Size:         ${strategy.config.max_position_size_usd:,.2f}")
        print(f"   Min Funding APY:       {strategy.config.min_funding_rate_apy:.1f}%")
        print(f"   Rebalance Threshold:   {strategy.config.rebalance_threshold_pct:.1f}%")
        print(f"   Max Leverage:          {strategy.config.max_leverage:.1f}x")
        
        print("\n" + "="*60)
        print("✅ BACKTEST COMPLETE")
        print("="*60)
    
    else:
        print("  ❌ No data available for backtesting")
        print("  💡 Check data loading")


if __name__ == "__main__":
    import asyncio
    import argparse
    
    parser = argparse.ArgumentParser(description="Run delta-neutral strategy backtest")
    parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)')
    
    args = parser.parse_args()
    
    asyncio.run(run_backtest(start_date=args.start, end_date=args.end))
