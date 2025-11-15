"""
Backtest Hyperliquid + 0x Delta Neutral Strategy

Run backtest using Nautilus BacktestEngine with historical data.
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.objects import Money
from nautilus_trader.model.enums import OmsType, AccountType

print("\n" + "="*60)
print("🔬 Hyperliquid + 0x Delta Neutral Backtest (Arbitrum L2)")
print("="*60)
print("\n⚠️  Historical data loading not yet implemented")
print("\nTo run backtest, you need to:")
print("1. Download historical data for ETH/USDC from 0x/Uniswap")
print("2. Download historical data for ETH-PERP from Hyperliquid")
print("3. Implement data loading in this script")
print("\nSee: https://hyperliquid.gitbook.io/ for API docs")
print("\n" + "="*60)

# Placeholder for future implementation
def run_backtest():
    """Run backtest (to be implemented)"""
    
    # Create backtest engine
    engine = BacktestEngine()
    
    # Add venues
    engine.add_venue(
        venue=Venue("ZEROX"),
        oms_type=OmsType.NETTING,
        account_type=AccountType.CASH,
        base_currency=USD,
        starting_balances=[Money(10000, USD)],
    )
    
    engine.add_venue(
        venue=Venue("HYPERLIQUID"),
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        base_currency=USD,
        starting_balances=[Money(10000, USD)],
    )
    
    print("\n✅ Backtest engine configured")
    print("📊 TODO: Load historical data and run backtest")


if __name__ == "__main__":
    run_backtest()
