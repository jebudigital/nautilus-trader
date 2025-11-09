"""
Cleanup Obsolete Files

Remove files that are no longer needed after migrating to Nautilus Trader.
This script identifies and removes old custom implementations that have been
replaced by Nautilus framework.
"""

from pathlib import Path
import shutil

# Files and directories to remove
OBSOLETE_ITEMS = [
    # Old custom backtesting engine (replaced by Nautilus BacktestEngine)
    "src/crypto_trading_engine/backtesting/",
    
    # Old custom strategy base (replaced by Nautilus Strategy)
    "src/crypto_trading_engine/core/strategy.py",
    "src/crypto_trading_engine/core/multi_mode_strategy.py",
    "src/crypto_trading_engine/core/trading_mode_manager.py",
    
    # Old custom adapter base (replaced by Nautilus DataClient/ExecutionClient)
    "src/crypto_trading_engine/core/adapter.py",
    
    # Old custom data models (replaced by Nautilus data types)
    "src/crypto_trading_engine/data/models.py",
    "src/crypto_trading_engine/data/aggregator.py",
    "src/crypto_trading_engine/data/ingestion.py",
    "src/crypto_trading_engine/data/live_sources.py",
    "src/crypto_trading_engine/data/store.py",
    "src/crypto_trading_engine/data/validation.py",
    "src/crypto_trading_engine/data/blockchain_monitor.py",
    
    # Old strategy implementation (replaced by delta_neutral_nautilus.py)
    "src/crypto_trading_engine/strategies/delta_neutral.py",
    "src/crypto_trading_engine/strategies/models.py",
    
    # Old model files (replaced by Nautilus types)
    "src/crypto_trading_engine/models/",
    
    # Old adapters (replaced by Nautilus adapters)
    "src/crypto_trading_engine/adapters/binance_adapter.py",
    "src/crypto_trading_engine/adapters/dydx_v4_rest_adapter.py",
    
    # Old example files
    "examples/backtest_delta_neutral_real_data.py",
    "examples/delta_neutral_live_paper_trading.py",
    "examples/test_dydx_rest_adapter.py",
    "examples/test_dydx_simple.py",
    "examples/test_dydx_v4_connection.py",
    
    # Old test file
    "example_strategy_test.py",
    
    # Old demo data
    "demo_backtest_data/",
    
    # Old pickle cache (replaced by Parquet)
    "data/historical/backtest_data.pkl",
    
    # Old review script (replaced by new data management)
    "scripts/review_backtest_data.py",
    
    # Old config files (using .env now)
    "config/",
    
    # Old main entry point (not needed with Nautilus)
    "src/crypto_trading_engine/main.py",
    
    # Old risk manager (using Nautilus RiskEngine)
    "src/crypto_trading_engine/core/risk_manager.py",
]

# Files to keep (for reference)
KEEP_FOR_REFERENCE = [
    "MIGRATION_COMPLETE.md",
    "docs/",
]


def cleanup(dry_run=True):
    """
    Remove obsolete files.
    
    Args:
        dry_run: If True, only show what would be deleted
    """
    print("\n" + "="*60)
    print("🧹 Cleanup Obsolete Files")
    print("="*60)
    
    if dry_run:
        print("\n⚠️  DRY RUN MODE - No files will be deleted")
        print("   Run with --execute to actually delete files\n")
    else:
        print("\n🚨 EXECUTING CLEANUP - Files will be deleted!\n")
    
    project_root = Path(__file__).parent.parent
    
    deleted_count = 0
    kept_count = 0
    not_found_count = 0
    
    for item_path in OBSOLETE_ITEMS:
        full_path = project_root / item_path
        
        if not full_path.exists():
            print(f"⚪ Not found: {item_path}")
            not_found_count += 1
            continue
        
        if full_path.is_file():
            size = full_path.stat().st_size / 1024
            print(f"🗑️  File: {item_path} ({size:.1f} KB)")
            
            if not dry_run:
                full_path.unlink()
                deleted_count += 1
            else:
                kept_count += 1
                
        elif full_path.is_dir():
            # Count files in directory
            file_count = sum(1 for _ in full_path.rglob('*') if _.is_file())
            print(f"📁 Directory: {item_path} ({file_count} files)")
            
            if not dry_run:
                shutil.rmtree(full_path)
                deleted_count += 1
            else:
                kept_count += 1
    
    print("\n" + "="*60)
    print("📊 Summary")
    print("="*60)
    
    if dry_run:
        print(f"  Would delete: {kept_count} items")
        print(f"  Not found: {not_found_count} items")
        print(f"\n💡 Run with --execute to actually delete files")
    else:
        print(f"  ✅ Deleted: {deleted_count} items")
        print(f"  ⚪ Not found: {not_found_count} items")
        print(f"\n✨ Cleanup complete!")
    
    print("\n📝 Files Kept (still in use):")
    print("  ✅ src/crypto_trading_engine/strategies/delta_neutral_nautilus.py")
    print("  ✅ src/crypto_trading_engine/adapters/binance_nautilus_adapter.py")
    print("  ✅ src/crypto_trading_engine/adapters/dydx_v4_nautilus_adapter.py")
    print("  ✅ src/crypto_trading_engine/data/historical_loader.py")
    print("  ✅ src/crypto_trading_engine/data/parquet_loader.py")
    print("  ✅ examples/backtest_delta_neutral.py")
    print("  ✅ scripts/load_historical_data.py")
    print("  ✅ data/historical/parquet/ (date-organized)")


def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Cleanup obsolete files after Nautilus migration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run (show what would be deleted)
  python scripts/cleanup_obsolete_files.py
  
  # Actually delete files
  python scripts/cleanup_obsolete_files.py --execute
        """
    )
    
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Actually delete files (default is dry run)'
    )
    
    args = parser.parse_args()
    
    cleanup(dry_run=not args.execute)


if __name__ == "__main__":
    main()
