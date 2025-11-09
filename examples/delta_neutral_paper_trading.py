"""
Delta-Neutral Strategy Paper Trading Example

This example demonstrates how to run the delta-neutral strategy in paper trading mode
with live market data but simulated execution.

Paper trading allows you to:
1. Test strategy with real-time market data
2. Validate execution logic without risking capital
3. Monitor performance before going live
4. Build confidence in the strategy
"""

import asyncio
import sys
from pathlib import Path
from decimal import Decimal
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.crypto_trading_engine.strategies.delta_neutral import (
    DeltaNeutralStrategy,
    DeltaNeutralConfig
)
from src.crypto_trading_engine.adapters.binance_adapter import BinanceAdapter
from src.crypto_trading_engine.adapters.dydx_adapter import DydxAdapter
from src.crypto_trading_engine.models.trading_mode import TradingMode


async def setup_paper_trading():
    """Set up paper trading environment."""
    print("\n" + "="*60)
    print("Delta-Neutral Strategy - Paper Trading Setup")
    print("="*60)
    
    # Create strategy configuration
    config = DeltaNeutralConfig(
        target_instruments=['BTC', 'ETH'],
        max_position_size_usd=Decimal('5000'),  # Start small
        max_total_exposure_usd=Decimal('20000'),
        rebalance_threshold_pct=Decimal('2'),
        min_funding_rate_apy=Decimal('6'),
        max_leverage=Decimal('3'),
        spot_venue="BINANCE",
        perp_venue="DYDX",
        rebalance_cooldown_minutes=20,
        emergency_exit_loss_pct=Decimal('4')
    )
    
    print("\n📊 Strategy Configuration:")
    print(f"  Target Instruments: {', '.join(config.target_instruments)}")
    print(f"  Max Position Size: ${config.max_position_size_usd:,.2f}")
    print(f"  Max Total Exposure: ${config.max_total_exposure_usd:,.2f}")
    print(f"  Rebalance Threshold: {config.rebalance_threshold_pct}%")
    print(f"  Min Funding APY: {config.min_funding_rate_apy}%")
    print(f"  Max Leverage: {config.max_leverage}x")
    
    # Create strategy instance
    strategy = DeltaNeutralStrategy("delta_neutral_paper", config)
    print(f"\n✓ Created strategy: {strategy.strategy_id}")
    
    return strategy, config


async def setup_exchange_adapters():
    """Set up exchange adapters for paper trading."""
    print("\n🔌 Setting up exchange connections...")
    
    # Binance adapter configuration
    binance_config = {
        'api_key': '',  # Will be loaded from .env
        'api_secret': '',
        'testnet': True  # Use testnet for paper trading
    }
    
    # dYdX adapter configuration
    dydx_config = {
        'api_key': '',
        'api_secret': '',
        'passphrase': '',
        'testnet': True
    }
    
    # Create adapters in paper trading mode
    binance_adapter = BinanceAdapter(binance_config, TradingMode.PAPER)
    dydx_adapter = DydxAdapter(dydx_config, TradingMode.PAPER)
    
    # Connect to exchanges
    print("  Connecting to Binance (paper mode)...")
    binance_connected = await binance_adapter.connect()
    
    print("  Connecting to dYdX (paper mode)...")
    dydx_connected = await dydx_adapter.connect()
    
    if binance_connected and dydx_connected:
        print("✓ All exchanges connected successfully")
        return binance_adapter, dydx_adapter
    else:
        print("❌ Failed to connect to exchanges")
        return None, None


async def monitor_strategy(strategy, duration_minutes=60):
    """
    Monitor strategy performance during paper trading.
    
    Args:
        strategy: Strategy instance
        duration_minutes: How long to run (default 60 minutes)
    """
    print(f"\n📈 Starting paper trading monitor (duration: {duration_minutes} minutes)")
    print("="*60)
    
    start_time = datetime.now()
    check_interval = 60  # Check every minute
    
    try:
        while True:
            # Check if duration exceeded
            elapsed = (datetime.now() - start_time).total_seconds() / 60
            if elapsed >= duration_minutes:
                print(f"\n⏰ Monitoring period complete ({duration_minutes} minutes)")
                break
            
            # Get performance summary
            summary = strategy.get_performance_summary()
            
            # Display current status
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Status Update:")
            print(f"  Active Positions: {summary['active_positions']}")
            print(f"  Total Trades: {summary['total_trades']}")
            print(f"  Funding Earned: ${summary['total_funding_earned_usd']:.2f}")
            print(f"  Rebalance Costs: ${summary['total_rebalance_costs_usd']:.2f}")
            print(f"  Net Profit: ${summary['net_profit_usd']:.2f}")
            
            # Display delta for each instrument
            if summary['current_delta']:
                print(f"  Current Delta:")
                for instrument, delta in summary['current_delta'].items():
                    print(f"    {instrument}: {delta:.6f}")
            
            # Wait before next check
            await asyncio.sleep(check_interval)
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Monitoring interrupted by user")
    
    return summary


async def generate_report(strategy, summary):
    """Generate final paper trading report."""
    print("\n" + "="*60)
    print("Paper Trading Session Report")
    print("="*60)
    
    print(f"\n📊 Performance Summary:")
    print(f"  Total Trades: {summary['total_trades']}")
    print(f"  Active Positions: {summary['active_positions']}")
    print(f"  Funding Earned: ${summary['total_funding_earned_usd']:.2f}")
    print(f"  Rebalance Costs: ${summary['total_rebalance_costs_usd']:.2f}")
    print(f"  Net Profit/Loss: ${summary['net_profit_usd']:.2f}")
    
    if summary['total_funding_earned_usd'] > 0:
        efficiency = (1 - summary['total_rebalance_costs_usd'] / summary['total_funding_earned_usd']) * 100
        print(f"  Cost Efficiency: {efficiency:.1f}%")
    
    print(f"\n⚖️  Delta Status:")
    if summary['current_delta']:
        for instrument, delta in summary['current_delta'].items():
            print(f"  {instrument}: {delta:.6f}")
    else:
        print("  No active positions")
    
    # Position history
    if hasattr(strategy, 'position_history') and strategy.position_history:
        print(f"\n📝 Position History ({len(strategy.position_history)} events):")
        for i, event in enumerate(strategy.position_history[-5:], 1):  # Show last 5 events
            action = event.get('action', 'unknown')
            instrument = event.get('instrument', 'N/A')
            timestamp = event.get('timestamp', 'N/A')
            print(f"  {i}. {action.upper()} {instrument} at {timestamp}")
    
    print("\n" + "="*60)
    print("Next Steps:")
    print("="*60)
    print("\n1. Review Performance:")
    print("   - Is the strategy profitable?")
    print("   - Are rebalancing costs reasonable?")
    print("   - Is delta staying near zero?")
    
    print("\n2. Adjust Parameters:")
    print("   - Increase/decrease position sizes")
    print("   - Adjust rebalance threshold")
    print("   - Modify funding rate requirements")
    
    print("\n3. Extended Testing:")
    print("   - Run for longer periods (24h, 7 days)")
    print("   - Test in different market conditions")
    print("   - Monitor during high volatility")
    
    print("\n4. Promote to Live:")
    print("   - When confident, switch to live trading")
    print("   - Start with small positions")
    print("   - Monitor closely initially")
    
    print("\n" + "="*60 + "\n")


async def main():
    """Main paper trading function."""
    print("\n" + "="*60)
    print("🚀 Delta-Neutral Strategy - Paper Trading")
    print("="*60)
    
    print("\n⚠️  PAPER TRADING MODE")
    print("  - Uses live market data")
    print("  - Simulates order execution")
    print("  - No real capital at risk")
    print("  - Perfect for testing and validation")
    
    # Setup
    strategy, config = await setup_paper_trading()
    
    # Note: For this demo, we're not actually connecting to exchanges
    # In a real implementation, you would:
    # adapters = await setup_exchange_adapters()
    # if not adapters:
    #     return
    
    print("\n" + "="*60)
    print("Paper Trading Options")
    print("="*60)
    print("\n1. Quick Test (5 minutes)")
    print("2. Standard Test (30 minutes)")
    print("3. Extended Test (60 minutes)")
    print("4. Custom Duration")
    print("5. Exit")
    
    choice = input("\nSelect option (1-5): ").strip()
    
    duration_map = {
        '1': 5,
        '2': 30,
        '3': 60
    }
    
    if choice == '5':
        print("\nExiting...")
        return
    
    if choice == '4':
        try:
            duration = int(input("Enter duration in minutes: "))
        except ValueError:
            print("Invalid input, using 30 minutes")
            duration = 30
    else:
        duration = duration_map.get(choice, 30)
    
    print(f"\n✓ Starting paper trading session ({duration} minutes)")
    print("  Press Ctrl+C to stop early")
    
    # In a real implementation, you would start the strategy here
    # For now, we'll simulate monitoring
    print("\n⚠️  Note: This is a demo. In a real implementation:")
    print("  - Strategy would connect to live market data")
    print("  - Orders would be simulated based on real prices")
    print("  - Positions would be tracked in real-time")
    print("  - Performance would be calculated continuously")
    
    # Simulate some activity
    print("\n" + "="*60)
    print("Simulated Paper Trading Activity")
    print("="*60)
    
    print("\n[00:00:00] Strategy initialized")
    print("[00:00:05] Connected to market data feeds")
    print("[00:00:10] Monitoring funding rates...")
    print("[00:01:00] BTC funding rate: 0.015% (5.5% APY) - Below threshold")
    print("[00:02:00] ETH funding rate: 0.020% (7.3% APY) - Above threshold!")
    print("[00:02:05] Opening delta-neutral position for ETH")
    print("[00:02:06]   - Buying 2.5 ETH spot @ $2,000")
    print("[00:02:07]   - Shorting 2.5 ETH perp @ $2,001")
    print("[00:02:08] Position opened successfully")
    print("[00:02:08] Current delta: 0.0000 ETH (neutral)")
    
    # Get final summary
    summary = strategy.get_performance_summary()
    
    # Generate report
    await generate_report(strategy, summary)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nPaper trading session interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
