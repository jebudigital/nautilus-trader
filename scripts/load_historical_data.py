"""
Load Historical Data

Download and save historical data to Parquet format for backtesting.
This should be run separately before backtesting.

Usage:
    python scripts/load_historical_data.py --start 2025-11-01 --end 2025-11-08 --symbols BTCUSDT
"""

import asyncio
import argparse
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import sys

# Add project root
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.crypto_trading_engine.data.historical_loader import HistoricalDataLoader


def save_to_parquet(data: dict, start_date: str, end_date: str, output_dir: Path):
    """
    Save data to Parquet files organized by date.
    
    Structure:
        data/historical/parquet/
            YYYY/MM/DD/
                binance_btcusdt_bars.parquet
                binance_btcusdt_ticks.parquet
                dydx_btcusd_bars.parquet
                dydx_btcusd_ticks.parquet
                dydx_funding.parquet
    
    Args:
        data: Dictionary with bars, ticks, and funding data
        start_date: Start date string (YYYY-MM-DD)
        end_date: End date string (YYYY-MM-DD)
        output_dir: Output directory for Parquet files
    """
    print("\n💾 Saving to Parquet format (organized by date)...")
    
    # Group data by date
    def group_by_date(items, get_timestamp):
        """Group items by date."""
        by_date = {}
        for item in items:
            ts = get_timestamp(item)
            date = datetime.fromtimestamp(ts / 1e9).date()
            date_str = date.strftime("%Y-%m-%d")
            if date_str not in by_date:
                by_date[date_str] = []
            by_date[date_str].append(item)
        return by_date
    
    # Group all data by date
    binance_bars_by_date = {}
    binance_ticks_by_date = {}
    dydx_bars_by_date = {}
    dydx_ticks_by_date = {}
    
    if 'binance_bars' in data and data['binance_bars']:
        binance_bars_by_date = group_by_date(data['binance_bars'], lambda x: x.ts_event)
    
    if 'binance_ticks' in data and data['binance_ticks']:
        binance_ticks_by_date = group_by_date(data['binance_ticks'], lambda x: x.ts_event)
    
    if 'dydx_bars' in data and data['dydx_bars']:
        dydx_bars_by_date = group_by_date(data['dydx_bars'], lambda x: x.ts_event)
    
    if 'dydx_ticks' in data and data['dydx_ticks']:
        dydx_ticks_by_date = group_by_date(data['dydx_ticks'], lambda x: x.ts_event)
    
    # Get all unique dates
    all_dates = set()
    all_dates.update(binance_bars_by_date.keys())
    all_dates.update(binance_ticks_by_date.keys())
    all_dates.update(dydx_bars_by_date.keys())
    all_dates.update(dydx_ticks_by_date.keys())
    
    total_files = 0
    
    # Save data for each date
    for date_str in sorted(all_dates):
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        year = date_obj.strftime("%Y")
        month = date_obj.strftime("%m")
        day = date_obj.strftime("%d")
        
        # Create directory structure: YYYY/MM/DD/
        date_dir = output_dir / year / month / day
        date_dir.mkdir(parents=True, exist_ok=True)
        
        # Save Binance bars
        if date_str in binance_bars_by_date:
            bars = binance_bars_by_date[date_str]
            df = pd.DataFrame([
                {
                    'timestamp': datetime.fromtimestamp(bar.ts_event / 1e9),
                    'open': float(bar.open),
                    'high': float(bar.high),
                    'low': float(bar.low),
                    'close': float(bar.close),
                    'volume': float(bar.volume),
                }
                for bar in bars
            ])
            filepath = date_dir / "binance_btcusdt_bars.parquet"
            df.to_parquet(filepath, index=False, compression='snappy')
            total_files += 1
        
        # Save Binance ticks
        if date_str in binance_ticks_by_date:
            ticks = binance_ticks_by_date[date_str]
            df = pd.DataFrame([
                {
                    'timestamp': datetime.fromtimestamp(tick.ts_event / 1e9),
                    'bid_price': float(tick.bid_price),
                    'ask_price': float(tick.ask_price),
                    'bid_size': float(tick.bid_size),
                    'ask_size': float(tick.ask_size),
                }
                for tick in ticks
            ])
            filepath = date_dir / "binance_btcusdt_ticks.parquet"
            df.to_parquet(filepath, index=False, compression='snappy')
            total_files += 1
        
        # Save dYdX bars
        if date_str in dydx_bars_by_date:
            bars = dydx_bars_by_date[date_str]
            df = pd.DataFrame([
                {
                    'timestamp': datetime.fromtimestamp(bar.ts_event / 1e9),
                    'open': float(bar.open),
                    'high': float(bar.high),
                    'low': float(bar.low),
                    'close': float(bar.close),
                    'volume': float(bar.volume),
                }
                for bar in bars
            ])
            filepath = date_dir / "dydx_btcusd_bars.parquet"
            df.to_parquet(filepath, index=False, compression='snappy')
            total_files += 1
        
        # Save dYdX ticks
        if date_str in dydx_ticks_by_date:
            ticks = dydx_ticks_by_date[date_str]
            df = pd.DataFrame([
                {
                    'timestamp': datetime.fromtimestamp(tick.ts_event / 1e9),
                    'bid_price': float(tick.bid_price),
                    'ask_price': float(tick.ask_price),
                    'bid_size': float(tick.bid_size),
                    'ask_size': float(tick.ask_size),
                }
                for tick in ticks
            ])
            filepath = date_dir / "dydx_btcusd_ticks.parquet"
            df.to_parquet(filepath, index=False, compression='snappy')
            total_files += 1
    
    # Save funding rates (not split by date, as they're less frequent)
    if 'dydx_funding' in data and data['dydx_funding']:
        df = pd.DataFrame(data['dydx_funding'])
        # Add date column for easier filtering
        if 'effectiveAt' in df.columns:
            df['date'] = pd.to_datetime(df['effectiveAt']).dt.date
        
        # Save to root of date range
        start_obj = datetime.strptime(start_date, "%Y-%m-%d")
        year = start_obj.strftime("%Y")
        month = start_obj.strftime("%m")
        
        funding_dir = output_dir / year / month
        funding_dir.mkdir(parents=True, exist_ok=True)
        
        filepath = funding_dir / f"dydx_funding_{start_date}_to_{end_date}.parquet"
        df.to_parquet(filepath, index=False, compression='snappy')
        print(f"  ✅ Funding rates: {filepath.relative_to(output_dir)} ({len(df)} rows)")
        total_files += 1
    
    print(f"\n📁 Saved {total_files} files to: {output_dir}")
    print(f"   Date range: {start_date} to {end_date}")
    print(f"   Dates covered: {len(all_dates)}")
    
    # Create index file for quick lookup
    index_data = {
        'start_date': start_date,
        'end_date': end_date,
        'created_at': datetime.now().isoformat(),
        'dates': sorted(list(all_dates)),
        'stats': {
            'binance_bars': len(data.get('binance_bars', [])),
            'binance_ticks': len(data.get('binance_ticks', [])),
            'dydx_bars': len(data.get('dydx_bars', [])),
            'dydx_ticks': len(data.get('dydx_ticks', [])),
            'dydx_funding': len(data.get('dydx_funding', [])),
        }
    }
    
    index_file = output_dir / "index.json"
    import json
    
    # Load existing index if it exists
    existing_index = []
    if index_file.exists():
        with open(index_file, 'r') as f:
            existing_index = json.load(f)
    
    # Add new entry
    existing_index.append(index_data)
    
    # Save updated index
    with open(index_file, 'w') as f:
        json.dump(existing_index, f, indent=2)
    
    print(f"  ✅ Updated index: {index_file.name}")


async def load_data(start_date: str, end_date: str, output_dir: Path):
    """
    Load historical data for the specified date range.
    
    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        output_dir: Output directory for Parquet files
    """
    print("\n" + "="*60)
    print("📊 Historical Data Loader")
    print("="*60)
    
    # Calculate days
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    days = (end - start).days
    
    print(f"\n📅 Date Range:")
    print(f"  Start: {start_date}")
    print(f"  End:   {end_date}")
    print(f"  Days:  {days}")
    
    if days <= 0:
        print("\n❌ Error: End date must be after start date")
        return
    
    if days > 30:
        print("\n⚠️  Warning: Loading more than 30 days of data")
        response = input("Continue? (y/N): ")
        if response.lower() != 'y':
            print("Cancelled")
            return
    
    # Load data
    print("\n🔄 Fetching data from APIs...")
    async with HistoricalDataLoader() as loader:
        data = await loader.load_all_data(days=days)
    
    # Save to Parquet
    save_to_parquet(data, start_date, end_date, output_dir)
    
    print("\n" + "="*60)
    print("✅ Data loading complete!")
    print("="*60)
    print(f"\n💡 To use this data in backtesting:")
    print(f"   python examples/backtest_delta_neutral.py --start {start_date} --end {end_date}")


def list_available_data(data_dir: Path):
    """List all available Parquet data files."""
    print("\n" + "="*60)
    print("📂 Available Data Files")
    print("="*60)
    
    if not data_dir.exists():
        print("\n❌ No data directory found")
        print(f"   Expected: {data_dir}")
        return
    
    # Check for index file
    index_file = data_dir / "index.json"
    
    if index_file.exists():
        import json
        with open(index_file, 'r') as f:
            index = json.load(f)
        
        if index:
            print(f"\n✅ Found {len(index)} data load(s):\n")
            
            for entry in index:
                print(f"📊 {entry['start_date']} to {entry['end_date']}")
                print(f"   Created: {entry['created_at']}")
                print(f"   Dates: {len(entry['dates'])} days")
                stats = entry['stats']
                print(f"   Binance bars: {stats['binance_bars']:,}")
                print(f"   Binance ticks: {stats['binance_ticks']:,}")
                print(f"   dYdX bars: {stats['dydx_bars']:,}")
                print(f"   dYdX ticks: {stats['dydx_ticks']:,}")
                print(f"   Funding rates: {stats['dydx_funding']}")
                print()
        else:
            print("\n❌ Index file is empty")
    else:
        # Fallback: scan directory structure
        print("\n📁 Scanning directory structure...")
        
        dates = []
        for year_dir in sorted(data_dir.glob("*")):
            if not year_dir.is_dir() or not year_dir.name.isdigit():
                continue
            
            for month_dir in sorted(year_dir.glob("*")):
                if not month_dir.is_dir() or not month_dir.name.isdigit():
                    continue
                
                for day_dir in sorted(month_dir.glob("*")):
                    if not day_dir.is_dir() or not day_dir.name.isdigit():
                        continue
                    
                    date_str = f"{year_dir.name}-{month_dir.name}-{day_dir.name}"
                    dates.append(date_str)
        
        if dates:
            print(f"\n✅ Found data for {len(dates)} dates:")
            print(f"   First: {dates[0]}")
            print(f"   Last:  {dates[-1]}")
        else:
            print("\n❌ No data files found")


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Load historical data for backtesting",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Load last 7 days
  python scripts/load_historical_data.py --days 7
  
  # Load specific date range
  python scripts/load_historical_data.py --start 2025-11-01 --end 2025-11-08
  
  # List available data
  python scripts/load_historical_data.py --list
        """
    )
    
    parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)')
    parser.add_argument('--days', type=int, help='Number of days from today (alternative to start/end)')
    parser.add_argument('--output', type=str, default='data/historical/parquet', help='Output directory')
    parser.add_argument('--list', action='store_true', help='List available data files')
    
    args = parser.parse_args()
    
    output_dir = Path(args.output)
    
    # List mode
    if args.list:
        list_available_data(output_dir)
        return
    
    # Determine date range
    if args.days:
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    elif args.start and args.end:
        start_date = args.start
        end_date = args.end
    else:
        # Default: last 7 days
        print("⚠️  No date range specified, using last 7 days")
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    
    # Load data
    asyncio.run(load_data(start_date, end_date, output_dir))


if __name__ == "__main__":
    main()
