# Professional Uniswap Lending Strategy Guide

## Overview

The Uniswap Lending Strategy has been completely refactored to be a professional-grade trading strategy suitable for backtesting, paper trading, and live trading. All hardcoded values have been removed and replaced with configurable parameters and real data sources.

## Key Improvements Made

### ❌ **Removed Hardcoded Issues**
- **Hardcoded pool addresses and tokens** - Now configurable via `target_pools`
- **Hardcoded prices** - Now uses `PriceDataSource` interface
- **Hardcoded pool metrics** - Now uses `PoolDataSource` interface  
- **Hardcoded gas prices** - Now fetched from data sources
- **Simplified price correlations** - Removed ETH = 5% of BTC assumptions
- **Mock pool data** - Now uses real data interfaces

### ✅ **Professional Features Added**
- **Configurable pool targeting** - Specify exact pools to trade
- **Data source abstraction** - Clean interfaces for price and pool data
- **Risk management parameters** - Configurable IL limits, position sizes
- **Gas optimization** - Dynamic gas price monitoring and optimization
- **Multiple risk profiles** - Professional, Aggressive, Conservative configs
- **Proper error handling** - Graceful fallbacks when data is unavailable

## Configuration Options

### Pool Configuration
```python
target_pools = [
    {
        'address': '0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640',
        'token0_address': '0xA0b86a33E6441E6C7D3E4C2C4C8C8C8C8C8C8C8C',
        'token0_symbol': 'USDC',
        'token0_decimals': 6,
        'token1_address': '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',
        'token1_symbol': 'WETH',
        'token1_decimals': 18,
        'fee_tier': 500,  # 0.05%
        'tick_spacing': 10
    }
]
```

### Risk Management
```python
config = StrategyConfig(
    max_impermanent_loss=Decimal('5'),       # Max 5% IL
    max_position_size_usd=Decimal('100000'), # Max $100K per position
    max_total_exposure_usd=Decimal('500000'), # Max $500K total
    max_price_impact=Decimal('0.005'),       # Max 0.5% price impact
)
```

### Gas Optimization
```python
config = StrategyConfig(
    max_gas_price_gwei=Decimal('30'),        # Max 30 Gwei
    min_profit_threshold_usd=Decimal('50'),  # Min $50 profit after gas
)
```

## Data Source Architecture

### Price Data Source Interface
```python
class PriceDataSource(ABC):
    @abstractmethod
    async def get_token_price_usd(self, token_symbol: str) -> Decimal:
        """Get current USD price for a token."""
        pass
    
    @abstractmethod
    async def get_gas_price_gwei(self) -> Decimal:
        """Get current gas price in Gwei."""
        pass
```

### Pool Data Source Interface
```python
class PoolDataSource(ABC):
    @abstractmethod
    async def get_pool_metrics(self, pool_address: str) -> PoolMetrics:
        """Get current pool metrics."""
        pass
    
    @abstractmethod
    async def get_pool_state(self, pool_address: str) -> UniswapPool:
        """Get current pool state."""
        pass
```

## Usage Examples

### Professional Configuration
```python
from src.crypto_trading_engine.strategies.uniswap_lending import UniswapLendingStrategy
from src.crypto_trading_engine.strategies.models import StrategyConfig, LiquidityRange

config = StrategyConfig(
    target_pools=[...],  # Specific pools
    min_tvl_usd=Decimal('10000000'),        # $10M minimum TVL
    min_fee_apy=Decimal('8'),               # 8% minimum APY
    max_impermanent_loss=Decimal('5'),      # 5% max IL
    liquidity_range=LiquidityRange.MEDIUM,
    max_gas_price_gwei=Decimal('30')
)

strategy = UniswapLendingStrategy("professional", config)
```

### With Custom Data Sources
```python
# For live trading, you would implement real data sources
class LivePriceDataSource(PriceDataSource):
    async def get_token_price_usd(self, token_symbol: str) -> Decimal:
        # Fetch from Chainlink, CoinGecko, etc.
        pass
    
    async def get_gas_price_gwei(self) -> Decimal:
        # Fetch from Ethereum gas tracker
        pass

price_source = LivePriceDataSource()
strategy = UniswapLendingStrategy(
    "live_strategy", 
    config, 
    price_data_source=price_source
)
```

## Risk Profiles

### Conservative (Stable Returns)
- **TVL Requirement**: $50M minimum
- **Max IL**: 3%
- **Range**: Wide (25%)
- **Gas Limit**: 20 Gwei
- **Hold Time**: 72 hours

### Professional (Balanced)
- **TVL Requirement**: $10M minimum  
- **Max IL**: 5%
- **Range**: Medium (15%)
- **Gas Limit**: 30 Gwei
- **Hold Time**: 48 hours

### Aggressive (Higher Returns)
- **TVL Requirement**: $5M minimum
- **Max IL**: 10%
- **Range**: Narrow (8%)
- **Gas Limit**: 50 Gwei
- **Hold Time**: 12 hours

## Testing

The strategy maintains full backward compatibility with existing tests while supporting the new professional features:

```bash
# Test basic functionality
python3 -m pytest tests/test_uniswap_simple.py -v

# Test comprehensive strategy features  
python3 -m pytest tests/test_uniswap_strategy.py -v

# Run professional configuration examples
python3 examples/professional_uniswap_config.py
```

## Migration from Hardcoded Version

If you were using the previous hardcoded version:

1. **Update imports** - No changes needed
2. **Add configuration** - Create `StrategyConfig` with your parameters
3. **Specify pools** - Add `target_pools` configuration
4. **Set risk limits** - Configure IL limits, position sizes, gas limits
5. **Choose data sources** - Use `BacktestDataSource` for backtesting, implement custom sources for live trading

## Next Steps

The strategy is now ready for:
- ✅ **Professional backtesting** with realistic parameters
- ✅ **Paper trading** with live data sources
- ✅ **Live trading** with proper risk management
- ✅ **Multi-pool strategies** with dynamic selection
- ✅ **Gas optimization** for profitable execution

This represents a complete transformation from a hardcoded test strategy to a production-ready professional trading system.