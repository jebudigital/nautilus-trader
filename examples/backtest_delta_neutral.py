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
    
    # Binance BTCUSDT spot (use 6 decimal precision to match generated ticks)
    btc_spot = CurrencyPair(
        instrument_id=InstrumentId(Symbol("BTCUSDT"), Venue("BINANCE")),
        raw_symbol=Symbol("BTCUSDT"),
        base_currency=BTC,
        quote_currency=USDT,
        price_precision=6,  # Match generated tick precision
        size_precision=5,
        price_increment=Price.from_str("0.000001"),
        size_increment=Quantity.from_str("0.00001"),
        lot_size=Quantity.from_str("0.00001"),
        max_quantity=Quantity.from_str("9000.0"),
        min_quantity=Quantity.from_str("0.00001"),
        max_price=Price.from_str("1000000.0"),
        min_price=Price.from_str("0.000001"),
        margin_init=Decimal("0"),
        margin_maint=Decimal("0"),
        maker_fee=Decimal("0.001"),
        taker_fee=Decimal("0.001"),
        ts_event=0,
        ts_init=0,
    )
    engine.add_instrument(btc_spot)
    print(f"  ✅ Added {btc_spot.id}")
    
    # dYdX BTC-USD perpetual (use 3 decimal precision to match generated ticks)
    btc_perp = CryptoPerpetual(
        instrument_id=InstrumentId(Symbol("BTC-USD"), Venue("DYDX_V4")),
        raw_symbol=Symbol("BTC-USD"),
        base_currency=BTC,
        quote_currency=USD,
        settlement_currency=USD,
        is_inverse=False,
        price_precision=3,  # Match generated tick precision
        size_precision=1,
        price_increment=Price.from_str("0.001"),
        size_increment=Quantity.from_str("0.1"),
        max_quantity=Quantity.from_str("1000.0"),
        min_quantity=Quantity.from_str("0.1"),
        max_price=Price.from_str("1000000.0"),
        min_price=Price.from_str("0.001"),
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
    
    # Store funding rates for strategy
    funding_rates = data.get('dydx_funding', [])
    print(f"  ✅ Loaded {len(funding_rates)} funding rates")
    
    # Create strategy
    print("\n🎯 Creating strategy...")
    strategy_config = DeltaNeutralConfig(
        spot_instrument="BTCUSDT.BINANCE",
        perp_instrument="BTC-USD.DYDX_V4",
        max_position_size_usd=5000.0,
        rebalance_threshold_pct=2.0,
        min_funding_rate_apy=6.0,
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
        print("\n📊 Backtest Results:")
        print("="*60)
        
        # Account reports
        print("\n💰 Account Performance:")
        print("\nBinance Account:")
        print(engine.trader.generate_account_report(Venue("BINANCE")))
        print("\ndYdX Account:")
        print(engine.trader.generate_account_report(Venue("DYDX_V4")))
        
        # Order and position reports
        print("\n📋 Trading Activity:")
        print("\nOrder Fills:")
        print(engine.trader.generate_order_fills_report())
        print("\nPositions:")
        print(engine.trader.generate_positions_report())
        
        print("\n" + "="*60)
        print("✅ Backtest Complete")
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
