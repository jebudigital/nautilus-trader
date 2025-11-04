"""
Uniswap V3 Liquidity Provision Strategy

This strategy automatically provides liquidity to profitable Uniswap V3 pools,
managing positions to maximize fee income while minimizing impermanent loss.

Key Features:
- Automated pool selection based on profitability metrics
- Dynamic liquidity range management
- Impermanent loss monitoring and protection
- Gas cost optimization
- Multi-pool portfolio management
"""

import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Set, Any
import json

from ..backtesting.strategy import Strategy
from ..backtesting.models import BacktestConfig, MarketState
from ..data.models import OHLCVData
from .models import (
    UniswapPool, LiquidityPosition, PoolMetrics, StrategyConfig,
    ImpermanentLossCalculator, GasOptimizer, GasEstimate,
    Token, PoolTier, LiquidityRange, ImpermanentLossCalculation,
    PriceDataSource, PoolDataSource, BacktestDataSource
)
from ..data.aggregator import MarketDataAggregator

logger = logging.getLogger(__name__)


class UniswapLendingStrategy(Strategy):
    """
    Advanced Uniswap V3 liquidity provision strategy.
    
    This strategy implements sophisticated liquidity management including:
    - Pool analysis and selection
    - Optimal liquidity range calculation
    - Impermanent loss monitoring
    - Gas cost optimization
    - Dynamic rebalancing
    """
    
    def __init__(
        self, 
        strategy_id: str = "uniswap_lending",
        config: Optional[StrategyConfig] = None,
        market_data_aggregator: Optional[MarketDataAggregator] = None,
        price_data_source: Optional[PriceDataSource] = None,
        pool_data_source: Optional[PoolDataSource] = None
    ):
        """
        Initialize the Uniswap lending strategy.
        
        Args:
            strategy_id: Unique identifier for the strategy
            config: Strategy configuration parameters
            market_data_aggregator: Unified market data aggregator (preferred)
            price_data_source: Source for token prices and gas prices (legacy)
            pool_data_source: Source for pool data and metrics (legacy)
        """
        self.strategy_config = config or StrategyConfig()
        self.strategy_config.validate()
        
        super().__init__(strategy_id, self.strategy_config.__dict__)
        
        # Data sources - prefer aggregator, fallback to individual sources
        if market_data_aggregator:
            self.market_data_aggregator = market_data_aggregator
            self.price_data_source = market_data_aggregator
            self.pool_data_source = market_data_aggregator
        else:
            # Legacy mode - use individual sources or defaults
            self.market_data_aggregator = None
            self.price_data_source = price_data_source or BacktestDataSource()
            self.pool_data_source = pool_data_source or self.price_data_source
        
        # Strategy state
        self.active_positions: Dict[str, LiquidityPosition] = {}  # pool_address -> position
        self.pool_metrics: Dict[str, PoolMetrics] = {}  # pool_address -> metrics
        self.available_pools: Dict[str, UniswapPool] = {}  # pool_address -> pool
        self.last_rebalance_time: Dict[str, datetime] = {}  # pool_address -> timestamp
        
        # Performance tracking
        self.total_fees_earned_usd = Decimal('0')
        self.total_impermanent_loss_usd = Decimal('0')
        self.total_gas_costs_usd = Decimal('0')
        self.position_history: List[Dict] = []
        
        # Gas optimizer
        self.gas_optimizer = GasOptimizer(self.strategy_config.max_gas_price_gwei)
        
        logger.info(f"Initialized UniswapLendingStrategy with config: {self.strategy_config}")
    
    async def on_initialize(self, backtest_config: BacktestConfig) -> None:
        """Initialize the strategy for backtesting."""
        self.log_info("Initializing Uniswap Lending Strategy")
        
        # Initialize available pools (in real implementation, would fetch from Uniswap)
        await self._initialize_pools()
        
        # Set initial market prices
        await self._update_market_prices()
        
        self.log_info(f"Strategy initialized with {len(self.available_pools)} available pools")
    
    async def on_market_data(self, data: OHLCVData, market_state: MarketState) -> None:
        """
        Process market data and make liquidity provision decisions.
        
        Args:
            data: OHLCV market data
            market_state: Current market state
        """
        # Update price cache
        await self._update_price_from_market_data(data, market_state)
        
        # Update pool metrics
        await self._update_pool_metrics()
        
        # Check existing positions
        await self._monitor_existing_positions()
        
        # Look for new opportunities
        await self._evaluate_new_opportunities()
        
        # Rebalance positions if needed
        await self._rebalance_positions()
    
    async def _initialize_pools(self) -> None:
        """Initialize available Uniswap pools for the strategy."""
        # Get pools from strategy configuration
        if not self.strategy_config.target_pools:
            self.log_warning("No target pools configured, using default pools for backtesting")
            await self._initialize_default_pools()
            return
        
        # Initialize pools from configuration
        for pool_config in self.strategy_config.target_pools:
            try:
                # Create tokens from configuration
                token0 = Token(
                    address=pool_config.get('token0_address', ''),
                    symbol=pool_config.get('token0_symbol', ''),
                    decimals=pool_config.get('token0_decimals', 18),
                    name=pool_config.get('token0_name', '')
                )
                
                token1 = Token(
                    address=pool_config.get('token1_address', ''),
                    symbol=pool_config.get('token1_symbol', ''),
                    decimals=pool_config.get('token1_decimals', 18),
                    name=pool_config.get('token1_name', '')
                )
                
                # Create pool
                pool = UniswapPool(
                    address=pool_config['address'],
                    token0=token0,
                    token1=token1,
                    fee_tier=PoolTier(pool_config.get('fee_tier', 3000)),
                    tick_spacing=pool_config.get('tick_spacing', 60),
                    current_tick=0,  # Will be updated from market data
                    sqrt_price_x96=0,  # Will be calculated from price
                    liquidity=Decimal('0')  # Will be fetched from data source
                )
                
                self.available_pools[pool.address] = pool
                
                # Get real pool state and metrics from data sources
                try:
                    # Update pool state from data source
                    updated_pool = await self.pool_data_source.get_pool_state(pool.address)
                    self.available_pools[pool.address] = updated_pool
                    
                    # Get pool metrics from data source
                    metrics = await self.pool_data_source.get_pool_metrics(pool.address)
                    self.pool_metrics[pool.address] = metrics
                    
                except Exception as e:
                    self.log_warning(f"Could not fetch live data for pool {pool.address}, using defaults: {e}")
                    # Initialize with empty metrics that will be updated from market data
                    self.pool_metrics[pool.address] = PoolMetrics(
                        pool=pool,
                        timestamp=datetime.now(),
                        volume_24h_usd=Decimal('0'),
                        volume_7d_usd=Decimal('0'),
                        volume_30d_usd=Decimal('0'),
                        fees_24h_usd=Decimal('0'),
                        fees_7d_usd=Decimal('0'),
                        fees_30d_usd=Decimal('0'),
                        tvl_usd=Decimal('0'),
                        liquidity_utilization=Decimal('0'),
                        price_change_24h=Decimal('0'),
                        price_change_7d=Decimal('0'),
                        volatility_24h=Decimal('0'),
                        fee_apy_24h=Decimal('0'),
                        fee_apy_7d=Decimal('0'),
                        fee_apy_30d=Decimal('0')
                    )
                
                self.log_info(f"Initialized pool {pool.address} ({token0.symbol}/{token1.symbol})")
                
            except Exception as e:
                self.log_error(f"Failed to initialize pool {pool_config.get('address', 'unknown')}: {e}")
        
        self.log_info(f"Initialized {len(self.available_pools)} Uniswap pools")
    
    async def _initialize_default_pools(self) -> None:
        """Initialize default pools for backtesting when no configuration is provided."""
        # Only used for backtesting/testing when no real pool config is provided
        default_pools = [
            {
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
            },
            {
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
        ]
        
        # Temporarily set target_pools for initialization
        self.strategy_config.target_pools = default_pools
        await self._initialize_pools()
    
    async def _update_market_prices(self) -> None:
        """Update current market prices for tokens from data sources."""
        try:
            # Get unique token symbols from all pools
            token_symbols = set()
            for pool in self.available_pools.values():
                token_symbols.add(pool.token0.symbol)
                token_symbols.add(pool.token1.symbol)
            
            # Update prices from data source
            for symbol in token_symbols:
                try:
                    price = await self.price_data_source.get_token_price_usd(symbol)
                    if price > 0:
                        # Update data source cache if it's BacktestDataSource
                        if isinstance(self.price_data_source, BacktestDataSource):
                            self.price_data_source.update_token_price(symbol, price)
                        self.log_info(f"Updated {symbol} price: ${price}")
                except Exception as e:
                    self.log_warning(f"Failed to get price for {symbol}: {e}")
            
            # Update gas price
            try:
                gas_price = await self.price_data_source.get_gas_price_gwei()
                if gas_price > 0:
                    if isinstance(self.price_data_source, BacktestDataSource):
                        self.price_data_source.update_gas_price(gas_price)
                    self.log_info(f"Updated gas price: {gas_price} Gwei")
            except Exception as e:
                self.log_warning(f"Failed to get gas price: {e}")
                
        except Exception as e:
            self.log_error(f"Failed to update market prices: {e}")
    
    async def _update_price_from_market_data(self, data: OHLCVData, market_state: MarketState) -> None:
        """Update price cache from incoming market data."""
        # Extract token symbol from instrument ID
        instrument_str = str(data.instrument_id)
        price = market_state.mid_price
        
        # Map instrument to token symbols
        token_symbol = None
        if 'BTC' in instrument_str.upper():
            token_symbol = 'WBTC'
        elif 'ETH' in instrument_str.upper():
            token_symbol = 'WETH'
        elif 'USDC' in instrument_str.upper():
            token_symbol = 'USDC'
        elif 'USDT' in instrument_str.upper():
            token_symbol = 'USDT'
        elif 'DAI' in instrument_str.upper():
            token_symbol = 'DAI'
        
        if token_symbol:
            # Update price in data source
            if isinstance(self.price_data_source, BacktestDataSource):
                self.price_data_source.update_token_price(token_symbol, price)
            
            self.log_info(f"Updated {token_symbol} price from market data: ${price}")
            
            # Update pool states with new prices
            await self._update_pool_states_from_prices()
    
    async def _update_pool_states_from_prices(self) -> None:
        """Update pool states when token prices change."""
        for pool_address, pool in self.available_pools.items():
            try:
                # Get current prices for pool tokens
                token0_price = await self.price_data_source.get_token_price_usd(pool.token0.symbol)
                token1_price = await self.price_data_source.get_token_price_usd(pool.token1.symbol)
                
                if token0_price > 0 and token1_price > 0:
                    # Calculate new pool price ratio
                    price_ratio = token1_price / token0_price
                    
                    # Update pool state in data source if it's BacktestDataSource
                    if isinstance(self.pool_data_source, BacktestDataSource):
                        # Create updated pool with new price information
                        updated_pool = UniswapPool(
                            address=pool.address,
                            token0=pool.token0,
                            token1=pool.token1,
                            fee_tier=pool.fee_tier,
                            tick_spacing=pool.tick_spacing,
                            current_tick=pool.current_tick,  # Would calculate from price in real implementation
                            sqrt_price_x96=pool.sqrt_price_x96,  # Would calculate from price in real implementation
                            liquidity=pool.liquidity
                        )
                        self.pool_data_source.update_pool_state(updated_pool)
                        self.available_pools[pool_address] = updated_pool
                        
            except Exception as e:
                self.log_warning(f"Failed to update pool state for {pool_address}: {e}")
    
    async def _get_token_price_usd(self, token_symbol: str) -> Decimal:
        """Get token price in USD from data source."""
        try:
            return await self.price_data_source.get_token_price_usd(token_symbol)
        except Exception as e:
            self.log_warning(f"Failed to get price for {token_symbol}: {e}")
            return Decimal('0')
    
    async def _get_gas_price_gwei(self) -> Decimal:
        """Get current gas price in Gwei from data source."""
        try:
            return await self.price_data_source.get_gas_price_gwei()
        except Exception as e:
            self.log_warning(f"Failed to get gas price: {e}")
            return Decimal('20')  # Default fallback
    
    async def _get_eth_price_usd(self) -> Decimal:
        """Get ETH price in USD from data source."""
        return await self._get_token_price_usd('WETH')
    
    async def _update_pool_prices(self) -> None:
        """Update pool prices based on current market prices."""
        for pool in self.available_pools.values():
            # Update pool's current price based on token prices
            token0_price = await self._get_token_price_usd(pool.token0.symbol)
            token1_price = await self._get_token_price_usd(pool.token1.symbol)
            
            # Calculate new price ratio
            price_ratio = token1_price / token0_price
            
            # Update pool's sqrt_price_x96 (simplified)
            sqrt_price = price_ratio ** Decimal('0.5')
            pool.sqrt_price_x96 = int(sqrt_price * (2 ** 96))
            
            # Update current tick (simplified tick calculation)
            # Real implementation would use exact Uniswap math
            import math
            pool.current_tick = int(math.log(float(price_ratio)) / 0.0001)  # Approximate
    
    async def _update_pool_metrics(self) -> None:
        """Update metrics for all pools."""
        for pool_address, pool in self.available_pools.items():
            if pool_address in self.pool_metrics:
                metrics = self.pool_metrics[pool_address]
                
                # Update timestamp
                metrics.timestamp = datetime.now()
                
                # Simulate metric updates based on market conditions
                # In real implementation, would fetch from Uniswap analytics
                
                # Update price changes based on current vs previous prices
                price_change = Decimal('0.01')  # Simplified 1% change
                metrics.price_change_24h = price_change
                
                # Update volatility based on price movements
                metrics.volatility_24h = abs(price_change) * Decimal('5')  # Amplify for volatility
                
                # Recalculate APY based on current conditions
                base_apy = pool.fee_percentage * metrics.liquidity_utilization * Decimal('365')
                volatility_bonus = metrics.volatility_24h * Decimal('50')  # Higher vol = higher fees
                metrics.fee_apy_24h = base_apy + volatility_bonus
                metrics.fee_apy_7d = metrics.fee_apy_24h
                metrics.fee_apy_30d = metrics.fee_apy_24h
    
    async def _monitor_existing_positions(self) -> None:
        """Monitor existing liquidity positions for rebalancing or exit signals."""
        positions_to_close = []
        
        for pool_address, position in self.active_positions.items():
            # Check if position needs attention
            pool = self.available_pools[pool_address]
            
            # Calculate current impermanent loss
            il_calc = await self._calculate_impermanent_loss(position)
            
            # Check exit conditions
            should_exit = await self._should_exit_position(position, il_calc)
            
            if should_exit:
                positions_to_close.append(pool_address)
                self.log_info(f"Marking position {pool_address} for closure: IL={il_calc.impermanent_loss_percentage:.2f}%")
            else:
                # Check if position needs rebalancing
                should_rebalance = await self._should_rebalance_position(position)
                
                if should_rebalance:
                    await self._rebalance_position(position)
        
        # Close positions that need to be exited
        for pool_address in positions_to_close:
            await self._close_position(pool_address)
    
    async def _evaluate_new_opportunities(self) -> None:
        """Evaluate new liquidity provision opportunities."""
        # Don't open new positions if we're at max exposure
        current_exposure = await self._calculate_total_exposure_usd()
        
        if current_exposure >= self.strategy_config.max_total_exposure_usd:
            return
        
        # Evaluate each available pool
        opportunities = []
        
        for pool_address, pool in self.available_pools.items():
            # Skip if we already have a position
            if pool_address in self.active_positions:
                continue
            
            # Evaluate pool profitability
            score = await self._evaluate_pool_opportunity(pool)
            
            if score > 0:
                opportunities.append((pool_address, score))
        
        # Sort by score and take the best opportunity
        opportunities.sort(key=lambda x: x[1], reverse=True)
        
        if opportunities:
            best_pool_address, best_score = opportunities[0]
            await self._open_new_position(best_pool_address)
    
    async def _evaluate_pool_opportunity(self, pool: UniswapPool) -> Decimal:
        """
        Evaluate the profitability of a pool opportunity.
        
        Args:
            pool: Pool to evaluate
            
        Returns:
            Opportunity score (higher is better, 0 or negative means skip)
        """
        metrics = self.pool_metrics.get(pool.address)
        if not metrics:
            return Decimal('0')
        
        # Check minimum criteria
        if metrics.tvl_usd < self.strategy_config.min_tvl_usd:
            return Decimal('0')
        
        if metrics.volume_24h_usd < self.strategy_config.min_volume_24h_usd:
            return Decimal('0')
        
        if metrics.average_fee_apy < self.strategy_config.min_fee_apy:
            return Decimal('0')
        
        # Calculate opportunity score
        score = Decimal('0')
        
        # APY component (30% weight)
        apy_score = min(metrics.average_fee_apy / Decimal('50'), Decimal('1')) * Decimal('30')
        score += apy_score
        
        # Liquidity utilization component (25% weight)
        util_score = min(metrics.liquidity_utilization * Decimal('10'), Decimal('1')) * Decimal('25')
        score += util_score
        
        # Stability component (25% weight) - lower volatility is better
        stability_score = max(Decimal('1') - metrics.volatility_24h / Decimal('0.5'), Decimal('0')) * Decimal('25')
        score += stability_score
        
        # Volume component (20% weight)
        volume_score = min(metrics.volume_24h_usd / Decimal('10000000'), Decimal('1')) * Decimal('20')
        score += volume_score
        
        # Gas cost penalty
        gas_price = await self._get_gas_price_gwei()
        eth_price = await self._get_eth_price_usd()
        gas_estimate = self.gas_optimizer.estimate_gas_cost(
            'mint_position', gas_price, eth_price
        )
        
        if gas_estimate.gas_cost_usd > self.strategy_config.min_profit_threshold_usd:
            score -= Decimal('10')  # Penalty for high gas costs
        
        return score
    
    async def _open_new_position(self, pool_address: str) -> None:
        """
        Open a new liquidity position in the specified pool.
        
        Args:
            pool_address: Address of the pool to provide liquidity to
        """
        pool = self.available_pools[pool_address]
        
        # Calculate position size
        position_size_usd = min(
            self.strategy_config.max_position_size_usd,
            self.get_portfolio_value().amount * Decimal('0.2')  # Max 20% per position
        )
        
        # Calculate optimal liquidity range
        tick_lower, tick_upper = await self._calculate_optimal_range(pool)
        
        # Estimate gas costs
        gas_price = await self._get_gas_price_gwei()
        eth_price = await self._get_eth_price_usd()
        gas_estimate = self.gas_optimizer.estimate_gas_cost(
            'mint_position', gas_price, eth_price
        )
        
        # Check if profitable after gas costs
        expected_daily_fees = position_size_usd * self.pool_metrics[pool_address].fee_apy_24h / Decimal('365') / Decimal('100')
        
        if not self.gas_optimizer.should_execute_now(
            'mint_position', gas_price, expected_daily_fees, eth_price
        ):
            self.log_info(f"Delaying position opening due to high gas costs: {gas_estimate.gas_cost_usd:.2f} USD")
            return
        
        # Create position (simplified - in real implementation would interact with Uniswap)
        position = LiquidityPosition(
            token_id=len(self.active_positions) + 1,  # Simplified token ID
            pool=pool,
            tick_lower=tick_lower,
            tick_upper=tick_upper,
            liquidity=position_size_usd / pool.current_price,  # Simplified liquidity calculation
            created_at=datetime.now()
        )
        
        # Simulate the transaction
        await self._simulate_liquidity_transaction(position, 'open', gas_estimate.gas_cost_usd)
        
        # Add to active positions
        self.active_positions[pool_address] = position
        
        # Record in history
        self.position_history.append({
            'action': 'open',
            'pool_address': pool_address,
            'position_size_usd': float(position_size_usd),
            'tick_lower': tick_lower,
            'tick_upper': tick_upper,
            'gas_cost_usd': float(gas_estimate.gas_cost_usd),
            'timestamp': datetime.now().isoformat()
        })
        
        self.log_info(f"Opened liquidity position in {pool.token0.symbol}/{pool.token1.symbol} pool: ${position_size_usd:.2f}")
    
    async def _calculate_optimal_range(self, pool: UniswapPool) -> Tuple[int, int]:
        """
        Calculate optimal tick range for liquidity provision.
        
        Args:
            pool: Pool to calculate range for
            
        Returns:
            Tuple of (tick_lower, tick_upper)
        """
        current_tick = pool.current_tick
        
        # Calculate range width based on strategy config
        if self.strategy_config.liquidity_range == LiquidityRange.NARROW:
            range_width = int(self.strategy_config.range_width_percentage * 0.5)  # 50% of configured width
        elif self.strategy_config.liquidity_range == LiquidityRange.MEDIUM:
            range_width = int(self.strategy_config.range_width_percentage)
        elif self.strategy_config.liquidity_range == LiquidityRange.WIDE:
            range_width = int(self.strategy_config.range_width_percentage * 1.5)  # 150% of configured width
        else:  # FULL_RANGE
            return -887272, 887272  # Full range ticks
        
        # Convert percentage to ticks (simplified)
        tick_range = int(range_width * 100)  # Approximate conversion
        
        # Ensure ticks are aligned to tick spacing
        tick_spacing = pool.tick_spacing
        
        tick_lower = ((current_tick - tick_range) // tick_spacing) * tick_spacing
        tick_upper = ((current_tick + tick_range) // tick_spacing) * tick_spacing
        
        return tick_lower, tick_upper
    
    async def _simulate_liquidity_transaction(
        self, 
        position: LiquidityPosition, 
        action: str, 
        gas_cost_usd: Decimal
    ) -> None:
        """
        Simulate a liquidity transaction for backtesting.
        
        Args:
            position: Liquidity position
            action: Transaction action ('open', 'close', 'rebalance')
            gas_cost_usd: Gas cost in USD
        """
        # In backtesting, we simulate the transaction by:
        # 1. Deducting gas costs from portfolio
        # 2. Tracking the position
        # 3. Not actually executing blockchain transactions
        
        # Deduct gas costs
        self.total_gas_costs_usd += gas_cost_usd
        
        # For opening positions, we would normally:
        # - Transfer tokens to Uniswap
        # - Receive LP NFT
        # - Start earning fees
        
        # For backtesting, we'll simulate this by tracking the position
        # and calculating theoretical returns
        
        self.log_info(f"Simulated {action} transaction: Gas cost ${gas_cost_usd:.2f}")
    
    async def _calculate_impermanent_loss(self, position: LiquidityPosition) -> ImpermanentLossCalculation:
        """
        Calculate current impermanent loss for a position.
        
        Args:
            position: Liquidity position to analyze
            
        Returns:
            Impermanent loss calculation
        """
        # Get entry and current prices
        entry_price = position.pool.current_price  # Simplified - would track actual entry price
        current_price = position.pool.current_price
        
        # Calculate token amounts at entry and now
        entry_token0, entry_token1 = position.calculate_token_amounts()
        current_token0, current_token1 = position.calculate_token_amounts()
        
        # Estimate fees earned (simplified calculation)
        days_held = (datetime.now() - position.created_at).days
        if days_held == 0:
            days_held = 1  # Minimum 1 day for calculation
        
        pool_metrics = self.pool_metrics[position.pool.address]
        daily_fee_rate = pool_metrics.fee_apy_24h / Decimal('365') / Decimal('100')
        
        position_value_usd = (current_token0 * self.price_cache.get(position.pool.token0.symbol, Decimal('1')) +
                             current_token1 * self.price_cache.get(position.pool.token1.symbol, Decimal('1')))
        
        total_fees_usd = position_value_usd * daily_fee_rate * Decimal(str(days_held))
        
        # Split fees between tokens (simplified)
        fees_token0 = total_fees_usd * Decimal('0.5') / self.price_cache.get(position.pool.token0.symbol, Decimal('1'))
        fees_token1 = total_fees_usd * Decimal('0.5') / self.price_cache.get(position.pool.token1.symbol, Decimal('1'))
        
        return ImpermanentLossCalculation(
            position=position,
            entry_price=entry_price,
            current_price=current_price,
            entry_token0_amount=entry_token0,
            entry_token1_amount=entry_token1,
            current_token0_amount=current_token0,
            current_token1_amount=current_token1,
            fees_earned_token0=fees_token0,
            fees_earned_token1=fees_token1
        )
    
    async def _should_exit_position(
        self, 
        position: LiquidityPosition, 
        il_calc: ImpermanentLossCalculation
    ) -> bool:
        """
        Determine if a position should be closed.
        
        Args:
            position: Liquidity position
            il_calc: Impermanent loss calculation
            
        Returns:
            True if position should be closed
        """
        # Check impermanent loss threshold
        if abs(il_calc.impermanent_loss_percentage) > self.strategy_config.max_impermanent_loss:
            return True
        
        # Check if position is out of range for too long
        if not position.is_in_range:
            hours_out_of_range = (datetime.now() - position.created_at).total_seconds() / 3600
            if hours_out_of_range > 48:  # Close if out of range for 48+ hours
                return True
        
        # Check if pool metrics have deteriorated
        pool_metrics = self.pool_metrics[position.pool.address]
        if pool_metrics.average_fee_apy < self.strategy_config.min_fee_apy:
            return True
        
        # Check minimum hold time
        hours_held = (datetime.now() - position.created_at).total_seconds() / 3600
        if hours_held < self.strategy_config.position_hold_min_hours:
            return False  # Don't close too early
        
        # Check if net profit is negative after fees
        if il_calc.net_profit_loss_usd < -self.strategy_config.min_profit_threshold_usd:
            return True
        
        return False
    
    async def _should_rebalance_position(self, position: LiquidityPosition) -> bool:
        """
        Determine if a position should be rebalanced.
        
        Args:
            position: Liquidity position
            
        Returns:
            True if position should be rebalanced
        """
        # Check cooldown period
        last_rebalance = self.last_rebalance_time.get(position.pool.address)
        if last_rebalance:
            hours_since_rebalance = (datetime.now() - last_rebalance).total_seconds() / 3600
            if hours_since_rebalance < self.config.rebalance_cooldown_hours:
                return False
        
        # Check if price has moved significantly from range center
        current_tick = position.pool.current_tick
        range_center = (position.tick_lower + position.tick_upper) / 2
        
        tick_deviation = abs(current_tick - range_center)
        range_width = position.tick_upper - position.tick_lower
        
        deviation_percentage = tick_deviation / range_width
        
        return deviation_percentage > self.config.rebalance_threshold
    
    async def _rebalance_position(self, position: LiquidityPosition) -> None:
        """
        Rebalance a liquidity position.
        
        Args:
            position: Position to rebalance
        """
        # Calculate new optimal range
        new_tick_lower, new_tick_upper = await self._calculate_optimal_range(position.pool)
        
        # Estimate gas costs for rebalancing
        gas_estimate = self.gas_optimizer.estimate_gas_cost(
            'decrease_liquidity', self.current_gas_price_gwei, self.eth_price_usd
        )
        
        # Check if rebalancing is profitable
        if not gas_estimate.is_profitable:
            self.log_info(f"Skipping rebalance due to high gas costs: ${gas_estimate.gas_cost_usd:.2f}")
            return
        
        # Simulate rebalancing transaction
        await self._simulate_liquidity_transaction(position, 'rebalance', gas_estimate.gas_cost_usd)
        
        # Update position range
        position.tick_lower = new_tick_lower
        position.tick_upper = new_tick_upper
        
        # Update last rebalance time
        self.last_rebalance_time[position.pool.address] = datetime.now()
        
        self.log_info(f"Rebalanced position in {position.pool.token0.symbol}/{position.pool.token1.symbol} pool")
    
    async def _close_position(self, pool_address: str) -> None:
        """
        Close a liquidity position.
        
        Args:
            pool_address: Address of the pool to close position in
        """
        if pool_address not in self.active_positions:
            return
        
        position = self.active_positions[pool_address]
        
        # Calculate final P&L
        il_calc = await self._calculate_impermanent_loss(position)
        
        # Estimate gas costs
        gas_estimate = self.gas_optimizer.estimate_gas_cost(
            'decrease_liquidity', self.current_gas_price_gwei, self.eth_price_usd
        )
        
        # Simulate closing transaction
        await self._simulate_liquidity_transaction(position, 'close', gas_estimate.gas_cost_usd)
        
        # Update totals
        self.total_fees_earned_usd += il_calc.fees_earned_token0 * self.price_cache.get(position.pool.token0.symbol, Decimal('1'))
        self.total_fees_earned_usd += il_calc.fees_earned_token1 * self.price_cache.get(position.pool.token1.symbol, Decimal('1'))
        self.total_impermanent_loss_usd += il_calc.impermanent_loss_usd
        
        # Record in history
        self.position_history.append({
            'action': 'close',
            'pool_address': pool_address,
            'impermanent_loss_usd': float(il_calc.impermanent_loss_usd),
            'fees_earned_usd': float(il_calc.fees_earned_token0 * self.price_cache.get(position.pool.token0.symbol, Decimal('1')) +
                                   il_calc.fees_earned_token1 * self.price_cache.get(position.pool.token1.symbol, Decimal('1'))),
            'net_profit_usd': float(il_calc.net_profit_loss_usd),
            'gas_cost_usd': float(gas_estimate.gas_cost_usd),
            'timestamp': datetime.now().isoformat()
        })
        
        # Remove from active positions
        del self.active_positions[pool_address]
        
        self.log_info(f"Closed position in {position.pool.token0.symbol}/{position.pool.token1.symbol} pool: "
                     f"Net P&L ${il_calc.net_profit_loss_usd:.2f}")
    
    async def _rebalance_positions(self) -> None:
        """Rebalance all positions that need rebalancing."""
        for position in list(self.active_positions.values()):
            if await self._should_rebalance_position(position):
                await self._rebalance_position(position)
    
    async def _calculate_total_exposure_usd(self) -> Decimal:
        """Calculate total USD exposure across all positions."""
        total_exposure = Decimal('0')
        
        for position in self.active_positions.values():
            token0_amount, token1_amount = position.calculate_token_amounts()
            
            token0_value = token0_amount * self.price_cache.get(position.pool.token0.symbol, Decimal('1'))
            token1_value = token1_amount * self.price_cache.get(position.pool.token1.symbol, Decimal('1'))
            
            total_exposure += token0_value + token1_value
        
        return total_exposure
    
    async def get_strategy_performance(self) -> Dict[str, Any]:
        """
        Get comprehensive strategy performance metrics.
        
        Returns:
            Dictionary with performance metrics
        """
        total_exposure = await self._calculate_total_exposure_usd()
        
        net_profit = self.total_fees_earned_usd + self.total_impermanent_loss_usd - self.total_gas_costs_usd
        
        return {
            'active_positions': len(self.active_positions),
            'total_exposure_usd': float(total_exposure),
            'total_fees_earned_usd': float(self.total_fees_earned_usd),
            'total_impermanent_loss_usd': float(self.total_impermanent_loss_usd),
            'total_gas_costs_usd': float(self.total_gas_costs_usd),
            'net_profit_usd': float(net_profit),
            'position_history_count': len(self.position_history),
            'pools_monitored': len(self.available_pools)
        }
    
    def get_position_summary(self) -> List[Dict[str, Any]]:
        """
        Get summary of all active positions.
        
        Returns:
            List of position summaries
        """
        summaries = []
        
        for pool_address, position in self.active_positions.items():
            il_calc = asyncio.run(self._calculate_impermanent_loss(position))
            
            summaries.append({
                'pool_address': pool_address,
                'token_pair': f"{position.pool.token0.symbol}/{position.pool.token1.symbol}",
                'fee_tier': position.pool.fee_tier.value / 10000,  # Convert to percentage
                'is_in_range': position.is_in_range,
                'range_width_pct': float(position.range_width_percentage),
                'impermanent_loss_pct': float(il_calc.impermanent_loss_percentage),
                'fees_earned_usd': float(il_calc.fees_earned_token0 * self.price_cache.get(position.pool.token0.symbol, Decimal('1')) +
                                        il_calc.fees_earned_token1 * self.price_cache.get(position.pool.token1.symbol, Decimal('1'))),
                'net_profit_usd': float(il_calc.net_profit_loss_usd),
                'created_at': position.created_at.isoformat()
            })
        
        return summaries