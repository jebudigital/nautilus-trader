"""
Example of professional Uniswap lending strategy configuration.

This shows how to configure the strategy for real trading with:
- Specific pool targets
- Risk management parameters
- Gas optimization settings
- Professional data sources
"""

from decimal import Decimal
import sys
sys.path.append('.')
from src.crypto_trading_engine.strategies.models import StrategyConfig, LiquidityRange

# Professional configuration for WETH/USDC pools
professional_config = StrategyConfig(
    # Target specific pools (real Uniswap V3 addresses)
    target_pools=[
        {
            # WETH/USDC 0.05% pool (high volume, tight spreads)
            'address': '0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640',
            'token0_address': '0xA0b86a33E6441E6C7D3E4C2C4C8C8C8C8C8C8C8C',
            'token0_symbol': 'USDC',
            'token0_decimals': 6,
            'token0_name': 'USD Coin',
            'token1_address': '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',
            'token1_symbol': 'WETH',
            'token1_decimals': 18,
            'token1_name': 'Wrapped Ether',
            'fee_tier': 500,  # 0.05%
            'tick_spacing': 10
        },
        {
            # WETH/USDC 0.30% pool (medium volume, wider spreads)
            'address': '0x8ad599c3A0ff1De082011EFDDc58f1908eb6e6D8',
            'token0_address': '0xA0b86a33E6441E6C7D3E4C2C4C8C8C8C8C8C8C8C',
            'token0_symbol': 'USDC',
            'token0_decimals': 6,
            'token0_name': 'USD Coin',
            'token1_address': '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',
            'token1_symbol': 'WETH',
            'token1_decimals': 18,
            'token1_name': 'Wrapped Ether',
            'fee_tier': 3000,  # 0.30%
            'tick_spacing': 60
        }
    ],
    
    # Pool selection criteria (for discovering new opportunities)
    min_tvl_usd=Decimal('10000000'),        # Minimum $10M TVL
    min_volume_24h_usd=Decimal('1000000'),  # Minimum $1M daily volume
    min_fee_apy=Decimal('8'),               # Minimum 8% fee APY
    max_price_impact=Decimal('0.005'),      # Max 0.5% price impact
    
    # Risk management
    max_impermanent_loss=Decimal('5'),       # Max 5% IL
    max_position_size_usd=Decimal('100000'), # Max $100K per position
    max_total_exposure_usd=Decimal('500000'), # Max $500K total
    
    # Liquidity range strategy
    liquidity_range=LiquidityRange.MEDIUM,
    range_width_percentage=Decimal('15'),    # 15% range width
    rebalance_threshold=Decimal('0.03'),     # 3% price move triggers rebalance
    
    # Gas optimization (conservative for mainnet)
    max_gas_price_gwei=Decimal('30'),        # Max 30 Gwei
    min_profit_threshold_usd=Decimal('50'),  # Min $50 profit after gas
    
    # Timing parameters
    position_hold_min_hours=48,              # Hold positions at least 48h
    rebalance_cooldown_hours=12              # Wait 12h between rebalances
)

# Aggressive configuration for higher returns (higher risk)
aggressive_config = StrategyConfig(
    target_pools=[
        {
            # WETH/USDC 0.05% pool
            'address': '0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640',
            'token0_address': '0xA0b86a33E6441E6C7D3E4C2C4C8C8C8C8C8C8C8C',
            'token0_symbol': 'USDC',
            'token0_decimals': 6,
            'token0_name': 'USD Coin',
            'token1_address': '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',
            'token1_symbol': 'WETH',
            'token1_decimals': 18,
            'token1_name': 'Wrapped Ether',
            'fee_tier': 500,
            'tick_spacing': 10
        }
    ],
    
    # More aggressive criteria
    min_tvl_usd=Decimal('5000000'),         # Lower TVL requirement
    min_volume_24h_usd=Decimal('500000'),   # Lower volume requirement
    min_fee_apy=Decimal('15'),              # Higher APY requirement
    max_price_impact=Decimal('0.01'),       # Allow higher price impact
    
    # Higher risk tolerance
    max_impermanent_loss=Decimal('10'),      # Max 10% IL
    max_position_size_usd=Decimal('200000'), # Max $200K per position
    max_total_exposure_usd=Decimal('1000000'), # Max $1M total
    
    # Tighter ranges for higher fees
    liquidity_range=LiquidityRange.NARROW,
    range_width_percentage=Decimal('8'),     # 8% range width
    rebalance_threshold=Decimal('0.02'),     # 2% price move triggers rebalance
    
    # More aggressive gas settings
    max_gas_price_gwei=Decimal('50'),        # Max 50 Gwei
    min_profit_threshold_usd=Decimal('25'),  # Min $25 profit after gas
    
    # Faster rebalancing
    position_hold_min_hours=12,              # Hold positions at least 12h
    rebalance_cooldown_hours=4               # Wait 4h between rebalances
)

# Conservative configuration for stable returns
conservative_config = StrategyConfig(
    target_pools=[
        {
            # WETH/USDC 0.30% pool (more stable)
            'address': '0x8ad599c3A0ff1De082011EFDDc58f1908eb6e6D8',
            'token0_address': '0xA0b86a33E6441E6C7D3E4C2C4C8C8C8C8C8C8C8C',
            'token0_symbol': 'USDC',
            'token0_decimals': 6,
            'token0_name': 'USD Coin',
            'token1_address': '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',
            'token1_symbol': 'WETH',
            'token1_decimals': 18,
            'token1_name': 'Wrapped Ether',
            'fee_tier': 3000,
            'tick_spacing': 60
        }
    ],
    
    # Very strict criteria
    min_tvl_usd=Decimal('50000000'),        # Minimum $50M TVL
    min_volume_24h_usd=Decimal('5000000'),  # Minimum $5M daily volume
    min_fee_apy=Decimal('5'),               # Lower APY requirement
    max_price_impact=Decimal('0.002'),      # Max 0.2% price impact
    
    # Conservative risk management
    max_impermanent_loss=Decimal('3'),       # Max 3% IL
    max_position_size_usd=Decimal('50000'),  # Max $50K per position
    max_total_exposure_usd=Decimal('200000'), # Max $200K total
    
    # Wide ranges for stability
    liquidity_range=LiquidityRange.WIDE,
    range_width_percentage=Decimal('25'),    # 25% range width
    rebalance_threshold=Decimal('0.05'),     # 5% price move triggers rebalance
    
    # Conservative gas settings
    max_gas_price_gwei=Decimal('20'),        # Max 20 Gwei
    min_profit_threshold_usd=Decimal('100'), # Min $100 profit after gas
    
    # Longer hold times
    position_hold_min_hours=72,              # Hold positions at least 72h
    rebalance_cooldown_hours=24              # Wait 24h between rebalances
)

if __name__ == "__main__":
    # Example usage
    from src.crypto_trading_engine.strategies.uniswap_lending import UniswapLendingStrategy
    
    print("🏦 Professional Uniswap Lending Strategy Configurations")
    print("=" * 60)
    
    # Create strategies with different risk profiles
    professional_strategy = UniswapLendingStrategy(
        "professional_uniswap", 
        professional_config
    )
    
    aggressive_strategy = UniswapLendingStrategy(
        "aggressive_uniswap", 
        aggressive_config
    )
    
    conservative_strategy = UniswapLendingStrategy(
        "conservative_uniswap", 
        conservative_config
    )
    
    print(f"✅ Professional Strategy: {len(professional_config.target_pools)} pools, max IL: {professional_config.max_impermanent_loss}%")
    print(f"✅ Aggressive Strategy: {len(aggressive_config.target_pools)} pools, max IL: {aggressive_config.max_impermanent_loss}%")
    print(f"✅ Conservative Strategy: {len(conservative_config.target_pools)} pools, max IL: {conservative_config.max_impermanent_loss}%")
    
    print("\n📊 Configuration Summary:")
    print(f"Professional - TVL: ${professional_config.min_tvl_usd:,}, Gas: {professional_config.max_gas_price_gwei} Gwei")
    print(f"Aggressive   - TVL: ${aggressive_config.min_tvl_usd:,}, Gas: {aggressive_config.max_gas_price_gwei} Gwei")
    print(f"Conservative - TVL: ${conservative_config.min_tvl_usd:,}, Gas: {conservative_config.max_gas_price_gwei} Gwei")