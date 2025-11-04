"""
Models and data structures for DeFi trading strategies.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum

from nautilus_trader.model.identifiers import InstrumentId, Venue
from abc import ABC, abstractmethod


class PoolTier(Enum):
    """Uniswap V3 fee tiers."""
    TIER_0_01 = 100      # 0.01%
    TIER_0_05 = 500      # 0.05%
    TIER_0_30 = 3000     # 0.30%
    TIER_1_00 = 10000    # 1.00%


class LiquidityRange(Enum):
    """Liquidity provision range strategies."""
    NARROW = "narrow"      # Tight range around current price
    MEDIUM = "medium"      # Moderate range
    WIDE = "wide"         # Wide range for stability
    FULL_RANGE = "full"   # Full price range


@dataclass
class Token:
    """Represents an ERC-20 token."""
    address: str
    symbol: str
    decimals: int
    name: Optional[str] = None
    
    def validate(self) -> None:
        """Validate token parameters."""
        if not self.address or len(self.address) != 42:
            raise ValueError("Invalid token address")
        if not self.symbol:
            raise ValueError("Token symbol required")
        if self.decimals < 0 or self.decimals > 18:
            raise ValueError("Invalid token decimals")


@dataclass
class UniswapPool:
    """Represents a Uniswap V3 liquidity pool."""
    address: str
    token0: Token
    token1: Token
    fee_tier: PoolTier
    tick_spacing: int
    current_tick: int
    sqrt_price_x96: int
    liquidity: Decimal
    fee_growth_global_0_x128: int = 0
    fee_growth_global_1_x128: int = 0
    protocol_fees_token0: Decimal = Decimal('0')
    protocol_fees_token1: Decimal = Decimal('0')
    
    @property
    def current_price(self) -> Decimal:
        """Calculate current price from sqrt_price_x96."""
        # Price = (sqrt_price_x96 / 2^96)^2
        sqrt_price = Decimal(self.sqrt_price_x96) / Decimal(2 ** 96)
        return sqrt_price ** 2
    
    @property
    def fee_percentage(self) -> Decimal:
        """Get fee percentage as decimal."""
        return Decimal(self.fee_tier.value) / Decimal('1000000')
    
    def validate(self) -> None:
        """Validate pool parameters."""
        if not self.address or len(self.address) != 42:
            raise ValueError("Invalid pool address")
        self.token0.validate()
        self.token1.validate()
        if self.liquidity < 0:
            raise ValueError("Liquidity cannot be negative")
        if self.sqrt_price_x96 <= 0:
            raise ValueError("Invalid sqrt price")


@dataclass
class LiquidityPosition:
    """Represents a liquidity position in a Uniswap V3 pool."""
    token_id: int
    pool: UniswapPool
    tick_lower: int
    tick_upper: int
    liquidity: Decimal
    fee_growth_inside_0_last_x128: int = 0
    fee_growth_inside_1_last_x128: int = 0
    tokens_owed_0: Decimal = Decimal('0')
    tokens_owed_1: Decimal = Decimal('0')
    created_at: datetime = field(default_factory=datetime.now)
    
    @property
    def price_lower(self) -> Decimal:
        """Calculate lower price bound from tick."""
        return Decimal(1.0001) ** self.tick_lower
    
    @property
    def price_upper(self) -> Decimal:
        """Calculate upper price bound from tick."""
        return Decimal(1.0001) ** self.tick_upper
    
    @property
    def is_in_range(self) -> bool:
        """Check if current price is within position range."""
        return self.tick_lower <= self.pool.current_tick <= self.tick_upper
    
    @property
    def range_width_percentage(self) -> Decimal:
        """Calculate range width as percentage of current price."""
        current_price = self.pool.current_price
        width = self.price_upper - self.price_lower
        return (width / current_price) * Decimal('100')
    
    def calculate_token_amounts(self) -> Tuple[Decimal, Decimal]:
        """Calculate current token amounts in the position."""
        if not self.is_in_range:
            # Position is out of range
            if self.pool.current_tick < self.tick_lower:
                # All in token0
                return self._calculate_token0_amount(), Decimal('0')
            else:
                # All in token1
                return Decimal('0'), self._calculate_token1_amount()
        
        # Position is in range, calculate both amounts
        amount0 = self._calculate_token0_amount()
        amount1 = self._calculate_token1_amount()
        return amount0, amount1
    
    def _calculate_token0_amount(self) -> Decimal:
        """Calculate token0 amount using Uniswap V3 math."""
        # Simplified calculation - in real implementation would use exact Uniswap math
        if self.pool.current_tick >= self.tick_upper:
            return Decimal('0')
        
        # Use liquidity and price range to calculate amount
        sqrt_price_current = Decimal(self.pool.sqrt_price_x96) / Decimal(2 ** 96)
        
        # Use math.pow for power operations with Decimal conversion
        import math
        sqrt_price_upper = Decimal(str(math.pow(1.0001, self.tick_upper / 2)))
        
        if self.pool.current_tick < self.tick_lower:
            sqrt_price_lower = Decimal(str(math.pow(1.0001, self.tick_lower / 2)))
            return self.liquidity * (sqrt_price_upper - sqrt_price_lower) / (sqrt_price_upper * sqrt_price_lower)
        else:
            return self.liquidity * (sqrt_price_upper - sqrt_price_current) / (sqrt_price_upper * sqrt_price_current)
    
    def _calculate_token1_amount(self) -> Decimal:
        """Calculate token1 amount using Uniswap V3 math."""
        # Simplified calculation - in real implementation would use exact Uniswap math
        if self.pool.current_tick < self.tick_lower:
            return Decimal('0')
        
        sqrt_price_current = Decimal(self.pool.sqrt_price_x96) / Decimal(2 ** 96)
        
        # Use math.pow for power operations with Decimal conversion
        import math
        sqrt_price_lower = Decimal(str(math.pow(1.0001, self.tick_lower / 2)))
        
        if self.pool.current_tick >= self.tick_upper:
            sqrt_price_upper = Decimal(str(math.pow(1.0001, self.tick_upper / 2)))
            return self.liquidity * (sqrt_price_upper - sqrt_price_lower)
        else:
            return self.liquidity * (sqrt_price_current - sqrt_price_lower)
    
    def validate(self) -> None:
        """Validate position parameters."""
        if self.token_id < 0:
            raise ValueError("Invalid token ID")
        if self.tick_lower >= self.tick_upper:
            raise ValueError("Lower tick must be less than upper tick")
        if self.liquidity < 0:
            raise ValueError("Liquidity cannot be negative")
        self.pool.validate()


@dataclass
class PoolMetrics:
    """Comprehensive metrics for a Uniswap pool."""
    pool: UniswapPool
    timestamp: datetime
    
    # Volume metrics
    volume_24h_usd: Decimal
    volume_7d_usd: Decimal
    volume_30d_usd: Decimal
    
    # Fee metrics
    fees_24h_usd: Decimal
    fees_7d_usd: Decimal
    fees_30d_usd: Decimal
    
    # Liquidity metrics
    tvl_usd: Decimal
    liquidity_utilization: Decimal  # Volume / TVL ratio
    
    # Price metrics
    price_change_24h: Decimal
    price_change_7d: Decimal
    volatility_24h: Decimal
    
    # APY calculations
    fee_apy_24h: Decimal
    fee_apy_7d: Decimal
    fee_apy_30d: Decimal
    
    @property
    def average_fee_apy(self) -> Decimal:
        """Calculate average fee APY across time periods."""
        return (self.fee_apy_24h + self.fee_apy_7d + self.fee_apy_30d) / Decimal('3')
    
    @property
    def liquidity_score(self) -> Decimal:
        """Calculate liquidity attractiveness score (0-100)."""
        # Combine multiple factors into a single score
        volume_score = min(self.liquidity_utilization * Decimal('100'), Decimal('50'))
        apy_score = min(self.average_fee_apy * Decimal('10'), Decimal('30'))
        stability_score = max(Decimal('20') - abs(self.price_change_24h) * Decimal('100'), Decimal('0'))
        
        return volume_score + apy_score + stability_score
    
    def validate(self) -> None:
        """Validate pool metrics."""
        self.pool.validate()
        if self.volume_24h_usd < 0:
            raise ValueError("Volume cannot be negative")
        if self.tvl_usd < 0:
            raise ValueError("TVL cannot be negative")
        if self.liquidity_utilization < 0:
            raise ValueError("Liquidity utilization cannot be negative")


@dataclass
class ImpermanentLossCalculation:
    """Calculation of impermanent loss for a position."""
    position: LiquidityPosition
    entry_price: Decimal
    current_price: Decimal
    entry_token0_amount: Decimal
    entry_token1_amount: Decimal
    current_token0_amount: Decimal
    current_token1_amount: Decimal
    fees_earned_token0: Decimal
    fees_earned_token1: Decimal
    
    @property
    def price_ratio_change(self) -> Decimal:
        """Calculate price ratio change since entry."""
        return self.current_price / self.entry_price
    
    @property
    def hodl_value_usd(self) -> Decimal:
        """Calculate value if tokens were held without providing liquidity."""
        token0_value = self.entry_token0_amount * self.current_price
        token1_value = self.entry_token1_amount
        return token0_value + token1_value
    
    @property
    def lp_value_usd(self) -> Decimal:
        """Calculate current LP position value including fees."""
        token0_value = (self.current_token0_amount + self.fees_earned_token0) * self.current_price
        token1_value = self.current_token1_amount + self.fees_earned_token1
        return token0_value + token1_value
    
    @property
    def impermanent_loss_percentage(self) -> Decimal:
        """Calculate impermanent loss as percentage."""
        if self.hodl_value_usd == 0:
            return Decimal('0')
        
        loss = (self.lp_value_usd - self.hodl_value_usd) / self.hodl_value_usd
        return loss * Decimal('100')
    
    @property
    def impermanent_loss_usd(self) -> Decimal:
        """Calculate impermanent loss in USD."""
        return self.lp_value_usd - self.hodl_value_usd
    
    @property
    def net_profit_loss_usd(self) -> Decimal:
        """Calculate net profit/loss including fees."""
        fees_usd = (self.fees_earned_token0 * self.current_price) + self.fees_earned_token1
        return self.impermanent_loss_usd + fees_usd
    
    def validate(self) -> None:
        """Validate calculation parameters."""
        self.position.validate()
        if self.entry_price <= 0:
            raise ValueError("Entry price must be positive")
        if self.current_price <= 0:
            raise ValueError("Current price must be positive")


class ImpermanentLossCalculator:
    """Calculator for impermanent loss analysis."""
    
    @staticmethod
    def calculate_theoretical_il(price_change_ratio: Decimal) -> Decimal:
        """
        Calculate theoretical impermanent loss for a given price change.
        
        Formula: IL = 2 * sqrt(price_ratio) / (1 + price_ratio) - 1
        
        Args:
            price_change_ratio: New price / original price
            
        Returns:
            Impermanent loss as decimal (negative values indicate loss)
        """
        if price_change_ratio <= 0:
            raise ValueError("Price change ratio must be positive")
        
        sqrt_ratio = price_change_ratio ** Decimal('0.5')
        il = (2 * sqrt_ratio) / (1 + price_change_ratio) - 1
        return il
    
    @staticmethod
    def calculate_breakeven_fee_apy(
        price_change_ratio: Decimal, 
        time_period_days: int
    ) -> Decimal:
        """
        Calculate the fee APY needed to break even with impermanent loss.
        
        Args:
            price_change_ratio: Price change ratio
            time_period_days: Time period in days
            
        Returns:
            Required fee APY to break even
        """
        il = ImpermanentLossCalculator.calculate_theoretical_il(price_change_ratio)
        
        if time_period_days <= 0:
            raise ValueError("Time period must be positive")
        
        # Convert IL to annual rate
        annual_il = abs(il) * (Decimal('365') / Decimal(str(time_period_days)))
        
        return annual_il * Decimal('100')  # Convert to percentage


@dataclass
class GasEstimate:
    """Gas estimation for Uniswap operations."""
    operation: str
    gas_limit: int
    gas_price_gwei: Decimal
    gas_cost_eth: Decimal
    gas_cost_usd: Decimal
    
    @property
    def is_profitable(self) -> bool:
        """Check if operation is profitable after gas costs."""
        # This would be implemented based on expected returns
        return self.gas_cost_usd < Decimal('50')  # Simplified threshold
    
    def validate(self) -> None:
        """Validate gas estimate."""
        if self.gas_limit <= 0:
            raise ValueError("Gas limit must be positive")
        if self.gas_price_gwei < 0:
            raise ValueError("Gas price cannot be negative")
        if self.gas_cost_eth < 0:
            raise ValueError("Gas cost cannot be negative")


class GasOptimizer:
    """Optimizer for gas costs in DeFi operations."""
    
    def __init__(self, max_gas_price_gwei: Decimal = Decimal('100')):
        """
        Initialize gas optimizer.
        
        Args:
            max_gas_price_gwei: Maximum acceptable gas price in Gwei
        """
        self.max_gas_price_gwei = max_gas_price_gwei
        self.gas_estimates = {
            'mint_position': 200000,      # Gas for minting new position
            'increase_liquidity': 150000,  # Gas for adding liquidity
            'decrease_liquidity': 120000,  # Gas for removing liquidity
            'collect_fees': 100000,       # Gas for collecting fees
            'burn_position': 80000        # Gas for burning position
        }
    
    def estimate_gas_cost(
        self, 
        operation: str, 
        gas_price_gwei: Decimal,
        eth_price_usd: Decimal
    ) -> GasEstimate:
        """
        Estimate gas cost for a DeFi operation.
        
        Args:
            operation: Type of operation
            gas_price_gwei: Current gas price in Gwei
            eth_price_usd: ETH price in USD
            
        Returns:
            Gas estimate with costs
        """
        if operation not in self.gas_estimates:
            raise ValueError(f"Unknown operation: {operation}")
        
        gas_limit = self.gas_estimates[operation]
        gas_cost_eth = (gas_limit * gas_price_gwei) / Decimal('1000000000')  # Convert from Gwei
        gas_cost_usd = gas_cost_eth * eth_price_usd
        
        return GasEstimate(
            operation=operation,
            gas_limit=gas_limit,
            gas_price_gwei=gas_price_gwei,
            gas_cost_eth=gas_cost_eth,
            gas_cost_usd=gas_cost_usd
        )
    
    def should_execute_now(
        self, 
        operation: str, 
        current_gas_price_gwei: Decimal,
        expected_profit_usd: Decimal,
        eth_price_usd: Decimal
    ) -> bool:
        """
        Determine if operation should be executed now based on gas costs.
        
        Args:
            operation: Type of operation
            current_gas_price_gwei: Current gas price
            expected_profit_usd: Expected profit from operation
            eth_price_usd: ETH price in USD
            
        Returns:
            True if operation should be executed now
        """
        if current_gas_price_gwei > self.max_gas_price_gwei:
            return False
        
        gas_estimate = self.estimate_gas_cost(operation, current_gas_price_gwei, eth_price_usd)
        
        # Execute if profit exceeds gas cost by at least 20%
        min_profit_threshold = gas_estimate.gas_cost_usd * Decimal('1.2')
        
        return expected_profit_usd >= min_profit_threshold
    
    def get_optimal_gas_price(
        self, 
        operation: str,
        target_profit_margin: Decimal,
        expected_profit_usd: Decimal,
        eth_price_usd: Decimal
    ) -> Decimal:
        """
        Calculate optimal gas price for desired profit margin.
        
        Args:
            operation: Type of operation
            target_profit_margin: Desired profit margin (e.g., 0.2 for 20%)
            expected_profit_usd: Expected profit from operation
            eth_price_usd: ETH price in USD
            
        Returns:
            Optimal gas price in Gwei
        """
        if operation not in self.gas_estimates:
            raise ValueError(f"Unknown operation: {operation}")
        
        gas_limit = self.gas_estimates[operation]
        
        # Calculate max acceptable gas cost
        max_gas_cost_usd = expected_profit_usd / (1 + target_profit_margin)
        max_gas_cost_eth = max_gas_cost_usd / eth_price_usd
        
        # Calculate max gas price
        max_gas_price_gwei = (max_gas_cost_eth * Decimal('1000000000')) / gas_limit
        
        return min(max_gas_price_gwei, self.max_gas_price_gwei)


@dataclass
class StrategyConfig:
    """Configuration for Uniswap lending strategy."""
    
    # Target pools configuration
    target_pools: Optional[List[Dict[str, Any]]] = None  # Pool configurations
    
    # Pool selection criteria
    min_tvl_usd: Decimal = Decimal('1000000')        # Minimum $1M TVL
    min_volume_24h_usd: Decimal = Decimal('100000')  # Minimum $100K daily volume
    min_fee_apy: Decimal = Decimal('5')              # Minimum 5% fee APY
    max_price_impact: Decimal = Decimal('0.01')      # Max 1% price impact
    
    # Risk management
    max_impermanent_loss: Decimal = Decimal('10')    # Max 10% IL
    max_position_size_usd: Decimal = Decimal('50000') # Max $50K per position
    max_total_exposure_usd: Decimal = Decimal('200000') # Max $200K total
    
    # Liquidity range strategy
    liquidity_range: LiquidityRange = LiquidityRange.MEDIUM
    range_width_percentage: Decimal = Decimal('20')   # 20% range width
    rebalance_threshold: Decimal = Decimal('0.05')    # 5% price move triggers rebalance
    
    # Gas optimization
    max_gas_price_gwei: Decimal = Decimal('50')       # Max 50 Gwei
    min_profit_threshold_usd: Decimal = Decimal('10') # Min $10 profit after gas
    
    # Timing parameters
    position_hold_min_hours: int = 24                 # Hold positions at least 24h
    rebalance_cooldown_hours: int = 6                 # Wait 6h between rebalances
    
    def validate(self) -> None:
        """Validate strategy configuration."""
        if self.min_tvl_usd <= 0:
            raise ValueError("Minimum TVL must be positive")
        if self.min_volume_24h_usd <= 0:
            raise ValueError("Minimum volume must be positive")
        if self.min_fee_apy < 0:
            raise ValueError("Minimum fee APY cannot be negative")
        if not (0 < self.max_price_impact < 1):
            raise ValueError("Max price impact must be between 0 and 1")
        if self.max_impermanent_loss < 0:
            raise ValueError("Max impermanent loss cannot be negative")
        if self.max_position_size_usd <= 0:
            raise ValueError("Max position size must be positive")
        if self.range_width_percentage <= 0:
            raise ValueError("Range width percentage must be positive")
        if self.rebalance_threshold <= 0:
            raise ValueError("Rebalance threshold must be positive")
        if self.max_gas_price_gwei <= 0:
            raise ValueError("Max gas price must be positive")
        if self.position_hold_min_hours < 0:
            raise ValueError("Position hold time cannot be negative")
        if self.rebalance_cooldown_hours < 0:
            raise ValueError("Rebalance cooldown cannot be negative")


class PriceDataSource(ABC):
    """Abstract interface for price data sources."""
    
    @abstractmethod
    async def get_token_price_usd(self, token_symbol: str) -> Decimal:
        """Get current USD price for a token."""
        pass
    
    @abstractmethod
    async def get_gas_price_gwei(self) -> Decimal:
        """Get current gas price in Gwei."""
        pass


class PoolDataSource(ABC):
    """Abstract interface for Uniswap pool data sources."""
    
    @abstractmethod
    async def get_pool_metrics(self, pool_address: str) -> PoolMetrics:
        """Get current pool metrics."""
        pass
    
    @abstractmethod
    async def get_pool_state(self, pool_address: str) -> UniswapPool:
        """Get current pool state."""
        pass
    
    @abstractmethod
    async def get_available_pools(self, token0: str, token1: str) -> List[UniswapPool]:
        """Get available pools for a token pair."""
        pass


class BacktestDataSource(PriceDataSource, PoolDataSource):
    """Data source implementation for backtesting."""
    
    def __init__(self):
        self.price_cache: Dict[str, Decimal] = {}
        self.pool_cache: Dict[str, UniswapPool] = {}
        self.pool_metrics_cache: Dict[str, PoolMetrics] = {}
        self.gas_price_gwei = Decimal('20')
    
    async def get_token_price_usd(self, token_symbol: str) -> Decimal:
        """Get token price from cache or market data."""
        return self.price_cache.get(token_symbol, Decimal('0'))
    
    async def get_gas_price_gwei(self) -> Decimal:
        """Get current gas price."""
        return self.gas_price_gwei
    
    async def get_pool_metrics(self, pool_address: str) -> PoolMetrics:
        """Get pool metrics from cache."""
        if pool_address not in self.pool_metrics_cache:
            raise ValueError(f"Pool metrics not available for {pool_address}")
        return self.pool_metrics_cache[pool_address]
    
    async def get_pool_state(self, pool_address: str) -> UniswapPool:
        """Get pool state from cache."""
        if pool_address not in self.pool_cache:
            raise ValueError(f"Pool state not available for {pool_address}")
        return self.pool_cache[pool_address]
    
    async def get_available_pools(self, token0: str, token1: str) -> List[UniswapPool]:
        """Get available pools for token pair."""
        return [pool for pool in self.pool_cache.values() 
                if (pool.token0.symbol == token0 and pool.token1.symbol == token1) or
                   (pool.token0.symbol == token1 and pool.token1.symbol == token0)]
    
    def update_token_price(self, token_symbol: str, price_usd: Decimal) -> None:
        """Update token price in cache."""
        self.price_cache[token_symbol] = price_usd
    
    def update_gas_price(self, gas_price_gwei: Decimal) -> None:
        """Update gas price."""
        self.gas_price_gwei = gas_price_gwei
    
    def update_pool_state(self, pool: UniswapPool) -> None:
        """Update pool state in cache."""
        self.pool_cache[pool.address] = pool
    
    def update_pool_metrics(self, pool_address: str, metrics: PoolMetrics) -> None:
        """Update pool metrics in cache."""
        self.pool_metrics_cache[pool_address] = metrics