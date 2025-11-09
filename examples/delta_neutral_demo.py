"""
Delta-Neutral Strategy Demo

This example demonstrates how to set up and run a delta-neutral strategy
that maintains market-neutral exposure across spot and perpetual markets.

The strategy:
1. Monitors funding rates on perpetual markets
2. Opens positions when funding rates are attractive
3. Maintains delta neutrality by balancing spot and perp positions
4. Rebalances when delta deviates beyond threshold
"""

import asyncio
import sys
from pathlib import Path
from decimal import Decimal

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.crypto_trading_engine.strategies.delta_neutral import (
    DeltaNeutralStrategy,
    DeltaNeutralConfig
)


def create_conservative_config() -> DeltaNeutralConfig:
    """Create a conservative delta-neutral configuration."""
    return DeltaNeutralConfig(
        target_instruments=['BTC', 'ETH'],
        max_position_size_usd=Decimal('5000'),
        max_total_exposure_usd=Decimal('20000'),
        rebalance_threshold_pct=Decimal('1.5'),  # Rebalance at 1.5% deviation
        min_funding_rate_apy=Decimal('8'),  # Require 8% APY minimum
        max_leverage=Decimal('2'),
        spot_venue="BINANCE",
        perp_venue="DYDX",
        rebalance_cooldown_minutes=30,
        emergency_exit_loss_pct=Decimal('3')
    )


def create_aggressive_config() -> DeltaNeutralConfig:
    """Create an aggressive delta-neutral configuration."""
    return DeltaNeutralConfig(
        target_instruments=['BTC', 'ETH', 'SOL'],
        max_position_size_usd=Decimal('20000'),
        max_total_exposure_usd=Decimal('100000'),
        rebalance_threshold_pct=Decimal('3'),  # Allow more deviation
        min_funding_rate_apy=Decimal('5'),  # Lower funding requirement
        max_leverage=Decimal('5'),
        spot_venue="BINANCE",
        perp_venue="DYDX",
        rebalance_cooldown_minutes=15,
        emergency_exit_loss_pct=Decimal('5')
    )


def create_balanced_config() -> DeltaNeutralConfig:
    """Create a balanced delta-neutral configuration."""
    return DeltaNeutralConfig(
        target_instruments=['BTC', 'ETH'],
        max_position_size_usd=Decimal('10000'),
        max_total_exposure_usd=Decimal('50000'),
        rebalance_threshold_pct=Decimal('2'),
        min_funding_rate_apy=Decimal('6'),
        max_leverage=Decimal('3'),
        spot_venue="BINANCE",
        perp_venue="DYDX",
        rebalance_cooldown_minutes=20,
        emergency_exit_loss_pct=Decimal('4')
    )


def print_config_summary(config: DeltaNeutralConfig, name: str) -> None:
    """Print a summary of the configuration."""
    print(f"\n{'='*60}")
    print(f"{name} Configuration")
    print(f"{'='*60}")
    print(f"Target Instruments: {', '.join(config.target_instruments)}")
    print(f"Max Position Size: ${config.max_position_size_usd:,.2f}")
    print(f"Max Total Exposure: ${config.max_total_exposure_usd:,.2f}")
    print(f"Rebalance Threshold: {config.rebalance_threshold_pct}%")
    print(f"Min Funding Rate APY: {config.min_funding_rate_apy}%")
    print(f"Max Leverage: {config.max_leverage}x")
    print(f"Spot Venue: {config.spot_venue}")
    print(f"Perp Venue: {config.perp_venue}")
    print(f"Rebalance Cooldown: {config.rebalance_cooldown_minutes} minutes")
    print(f"Emergency Exit Loss: {config.emergency_exit_loss_pct}%")
    print(f"{'='*60}\n")


def main():
    """Main demo function."""
    print("\n" + "="*60)
    print("Delta-Neutral Strategy Configuration Demo")
    print("="*60)
    
    # Create different risk profiles
    conservative = create_conservative_config()
    balanced = create_balanced_config()
    aggressive = create_aggressive_config()
    
    # Print summaries
    print_config_summary(conservative, "CONSERVATIVE")
    print_config_summary(balanced, "BALANCED")
    print_config_summary(aggressive, "AGGRESSIVE")
    
    # Create strategy instances
    print("\nCreating strategy instances...")
    
    conservative_strategy = DeltaNeutralStrategy(
        strategy_id="delta_neutral_conservative",
        config=conservative
    )
    print(f"✓ Created conservative strategy: {conservative_strategy.strategy_id}")
    
    balanced_strategy = DeltaNeutralStrategy(
        strategy_id="delta_neutral_balanced",
        config=balanced
    )
    print(f"✓ Created balanced strategy: {balanced_strategy.strategy_id}")
    
    aggressive_strategy = DeltaNeutralStrategy(
        strategy_id="delta_neutral_aggressive",
        config=aggressive
    )
    print(f"✓ Created aggressive strategy: {aggressive_strategy.strategy_id}")
    
    # Strategy comparison
    print("\n" + "="*60)
    print("Strategy Comparison")
    print("="*60)
    print(f"{'Metric':<30} {'Conservative':<15} {'Balanced':<15} {'Aggressive':<15}")
    print("-"*75)
    print(f"{'Max Position Size':<30} ${conservative.max_position_size_usd:>13,.0f} ${balanced.max_position_size_usd:>13,.0f} ${aggressive.max_position_size_usd:>13,.0f}")
    print(f"{'Max Total Exposure':<30} ${conservative.max_total_exposure_usd:>13,.0f} ${balanced.max_total_exposure_usd:>13,.0f} ${aggressive.max_total_exposure_usd:>13,.0f}")
    print(f"{'Rebalance Threshold':<30} {conservative.rebalance_threshold_pct:>13}% {balanced.rebalance_threshold_pct:>13}% {aggressive.rebalance_threshold_pct:>13}%")
    print(f"{'Min Funding APY':<30} {conservative.min_funding_rate_apy:>13}% {balanced.min_funding_rate_apy:>13}% {aggressive.min_funding_rate_apy:>13}%")
    print(f"{'Max Leverage':<30} {conservative.max_leverage:>13}x {balanced.max_leverage:>13}x {aggressive.max_leverage:>13}x")
    print(f"{'Emergency Exit Loss':<30} {conservative.emergency_exit_loss_pct:>13}% {balanced.emergency_exit_loss_pct:>13}% {aggressive.emergency_exit_loss_pct:>13}%")
    print("="*75)
    
    # Usage recommendations
    print("\n" + "="*60)
    print("Usage Recommendations")
    print("="*60)
    print("\n📊 CONSERVATIVE Profile:")
    print("   - Best for: Risk-averse traders, smaller accounts")
    print("   - Characteristics: Lower leverage, tighter rebalancing, higher funding requirements")
    print("   - Expected: Lower returns, lower risk, more stable")
    
    print("\n⚖️  BALANCED Profile:")
    print("   - Best for: Most traders, medium-sized accounts")
    print("   - Characteristics: Moderate leverage, balanced rebalancing, reasonable funding requirements")
    print("   - Expected: Moderate returns, moderate risk, good risk/reward ratio")
    
    print("\n🚀 AGGRESSIVE Profile:")
    print("   - Best for: Experienced traders, larger accounts")
    print("   - Characteristics: Higher leverage, wider rebalancing tolerance, lower funding requirements")
    print("   - Expected: Higher returns, higher risk, more volatility")
    
    print("\n" + "="*60)
    print("Next Steps")
    print("="*60)
    print("\n1. Choose a configuration that matches your risk tolerance")
    print("2. Run backtests to validate strategy performance")
    print("3. Test in paper trading mode with live data")
    print("4. Monitor performance and adjust parameters as needed")
    print("5. Promote to live trading when confident")
    
    print("\n" + "="*60)
    print("Key Strategy Mechanics")
    print("="*60)
    print("\n📈 Position Opening:")
    print("   - Monitor funding rates on perpetual markets")
    print("   - Open when funding APY exceeds minimum threshold")
    print("   - Simultaneously buy spot and short perpetual")
    print("   - Maintain 1:1 ratio for delta neutrality")
    
    print("\n⚖️  Delta Management:")
    print("   - Calculate portfolio delta continuously")
    print("   - Rebalance when deviation exceeds threshold")
    print("   - Adjust spot or perp positions to restore neutrality")
    print("   - Respect cooldown period between rebalances")
    
    print("\n💰 Profit Sources:")
    print("   - Funding rate payments (primary)")
    print("   - Basis spread capture (secondary)")
    print("   - Volatility trading (tertiary)")
    
    print("\n🛡️  Risk Management:")
    print("   - Emergency exit on excessive losses")
    print("   - Position size limits per instrument")
    print("   - Total exposure limits across portfolio")
    print("   - Leverage limits to control risk")
    
    print("\n" + "="*60)
    print("Demo completed successfully!")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
