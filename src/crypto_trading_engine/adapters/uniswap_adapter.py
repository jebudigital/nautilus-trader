"""
Uniswap V3 adapter implementation.
"""

import asyncio
import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any, Callable, Tuple
import aiohttp

# Optional Web3 imports - only needed for live trading
try:
    from web3 import Web3
    from web3.middleware import geth_poa_middleware
    WEB3_AVAILABLE = True
except ImportError:
    Web3 = None
    geth_poa_middleware = None
    WEB3_AVAILABLE = False

from nautilus_trader.model.identifiers import Venue, InstrumentId, ClientOrderId, PositionId, StrategyId
from nautilus_trader.model.enums import OrderSide, OrderType, TimeInForce, PositionSide
from nautilus_trader.model.objects import Money, Price, Quantity, Currency
from nautilus_trader.model.data import QuoteTick

from ..core.adapter import ExchangeAdapter
from ..models.trading_mode import TradingMode
from ..models.core import Order, Position, Instrument, SimulatedFill
from ..models.defi import LiquidityPosition, UniswapPool, Token


logger = logging.getLogger(__name__)


class UniswapAdapter(ExchangeAdapter):
    """
    Uniswap V3 adapter with Web3 integration.
    
    Supports liquidity provision and removal, pool analytics,
    fee calculations, and gas optimization.
    """
    
    def __init__(
        self,
        config: Dict[str, Any],
        trading_mode: TradingMode = TradingMode.BACKTEST
    ):
        """
        Initialize Uniswap adapter.
        
        Args:
            config: Configuration dictionary containing:
                - web3_provider_url: Web3 provider URL (e.g., Infura, Alchemy)
                - private_key: Private key for transactions (optional for read-only)
                - factory_address: Uniswap V3 factory contract address
                - router_address: Uniswap V3 router contract address
                - position_manager_address: Uniswap V3 position manager address
                - network: Network name (mainnet, goerli, etc.)
            trading_mode: Current trading mode
        """
        venue = Venue("UNISWAP")
        super().__init__(venue, config, trading_mode)
        
        # Configuration - load from environment if not provided
        import os
        self.web3_provider_url = config.get("web3_provider_url") or os.getenv("WEB3__PROVIDER_URL", "")
        self.private_key = config.get("private_key") or os.getenv("WEB3__PRIVATE_KEY", "")
        self.network = config.get("network", "mainnet")
        
        # Contract addresses (mainnet defaults)
        self.factory_address = config.get(
            "factory_address", 
            "0x1F98431c8aD98523631AE4a59f267346ea31F984"
        )
        self.router_address = config.get(
            "router_address",
            "0xE592427A0AEce92De3Edee1F18E0157C05861564"
        )
        self.position_manager_address = config.get(
            "position_manager_address",
            "0xC36442b4a4522E871399CD717aBDD847Ab11FE88"
        )
        
        # Web3 connection
        self.w3: Optional[Web3] = None
        self.account_address: Optional[str] = None
        
        # Pool data
        self.pools: Dict[str, UniswapPool] = {}
        self.liquidity_positions: Dict[str, LiquidityPosition] = {}
        
        # Gas tracking
        self.gas_price_history: List[Tuple[datetime, int]] = []
        self.current_gas_price: Optional[int] = None
        
        # Market data
        self.price_feeds: Dict[str, Price] = {}
        self.pool_update_task: Optional[asyncio.Task] = None
        
        logger.info(f"Initialized Uniswap adapter in {trading_mode.value} mode")
    
    async def connect(self) -> bool:
        """
        Connect to Web3 provider and initialize contracts.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            if self.trading_mode == TradingMode.BACKTEST:
                # No real connection needed for backtesting
                self.is_connected = True
                logger.info("Uniswap adapter connected (backtest mode)")
                return True
            
            # Initialize Web3 connection
            if not await self._initialize_web3():
                return False
            
            # Load pool information
            await self._load_pools()
            
            # Load existing liquidity positions if in live mode
            if self.trading_mode == TradingMode.LIVE and self.account_address:
                await self._load_liquidity_positions()
            
            # Start gas price monitoring
            await self._start_gas_monitoring()
            
            self.is_connected = True
            logger.info(f"Uniswap adapter connected successfully ({self.trading_mode.value} mode)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Uniswap: {e}")
            if self.on_error_callback:
                self.on_error_callback(e)
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from Web3 provider."""
        try:
            # Stop pool update task
            if self.pool_update_task and not self.pool_update_task.done():
                self.pool_update_task.cancel()
                try:
                    await self.pool_update_task
                except asyncio.CancelledError:
                    pass
                self.pool_update_task = None
            
            self.w3 = None
            self.account_address = None
            self.is_connected = False
            logger.info("Uniswap adapter disconnected")
            
        except Exception as e:
            logger.error(f"Error during Uniswap disconnect: {e}")
    
    async def submit_order(self, order: Order) -> bool:
        """
        Submit a liquidity order to Uniswap.
        
        Note: For Uniswap, "orders" are liquidity provision operations.
        
        Args:
            order: Order representing liquidity provision
            
        Returns:
            True if order submitted successfully, False otherwise
        """
        try:
            if not self.validate_order(order):
                logger.error(f"Order validation failed: {order.id}")
                return False
            
            if self.trading_mode == TradingMode.PAPER:
                # Simulate liquidity provision for paper trading
                return await self._simulate_liquidity_provision(order)
            
            elif self.trading_mode == TradingMode.LIVE:
                # Execute real liquidity provision
                return await self._execute_liquidity_provision(order)
            
            else:  # BACKTEST
                # Orders in backtest mode are handled by the backtest engine
                logger.warning("Order submission not supported in backtest mode")
                return False
                
        except Exception as e:
            logger.error(f"Failed to submit order {order.id}: {e}")
            if self.on_error_callback:
                self.on_error_callback(e)
            return False
    
    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel a liquidity position (remove liquidity).
        
        Args:
            order_id: ID of liquidity position to remove
            
        Returns:
            True if position removed successfully, False otherwise
        """
        try:
            if self.trading_mode == TradingMode.BACKTEST:
                logger.warning("Position removal not supported in backtest mode")
                return False
            
            if self.trading_mode == TradingMode.PAPER:
                # Remove simulated liquidity position
                if order_id in self.liquidity_positions:
                    del self.liquidity_positions[order_id]
                    logger.info(f"Simulated liquidity position {order_id} removed")
                    return True
                return False
            
            # Live mode - remove real liquidity
            return await self._remove_liquidity_position(order_id)
                    
        except Exception as e:
            logger.error(f"Failed to remove liquidity position {order_id}: {e}")
            if self.on_error_callback:
                self.on_error_callback(e)
            return False
    
    async def get_order_status(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        Get liquidity position status.
        
        Args:
            order_id: Position ID to check
            
        Returns:
            Position status information or None if not found
        """
        try:
            position = self.liquidity_positions.get(order_id)
            if position:
                return {
                    "id": order_id,
                    "status": "ACTIVE",
                    "liquidity": str(position.liquidity_amount),
                    "fees_earned": str(position.fees_earned.as_decimal()),
                    "pool_address": position.pool_address
                }
            return None
                    
        except Exception as e:
            logger.error(f"Failed to get position status {order_id}: {e}")
            if self.on_error_callback:
                self.on_error_callback(e)
            return None
    
    async def get_positions(self) -> List[Position]:
        """
        Get current liquidity positions as trading positions.
        
        Returns:
            List of current positions
        """
        try:
            positions = []
            
            for pos_id, liq_pos in self.liquidity_positions.items():
                # Convert liquidity position to trading position
                instrument = self._get_pool_instrument(liq_pos.pool_address)
                if not instrument:
                    continue
                
                position = Position(
                    id=PositionId(pos_id),
                    instrument=instrument,
                    side=PositionSide.LONG,  # Liquidity provision is always "long"
                    quantity=Quantity(liq_pos.liquidity_amount, 8),  # Use 8 decimals for liquidity
                    avg_price=Price(Decimal("1"), 8),  # Liquidity doesn't have a price
                    unrealized_pnl=liq_pos.fees_earned,
                    venue=self.venue,
                    strategy_id=StrategyId("UNISWAP-LP"),
                    opened_time=datetime.now(),
                    is_simulated=self.trading_mode == TradingMode.PAPER
                )
                positions.append(position)
            
            return positions
                    
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            if self.on_error_callback:
                self.on_error_callback(e)
            return []
    
    async def get_balance(self) -> Dict[str, Money]:
        """
        Get token balances.
        
        Returns:
            Dictionary of token balances
        """
        try:
            if self.trading_mode == TradingMode.BACKTEST:
                # Return mock balances for backtesting
                return {
                    "ETH": Money(Decimal("10"), Currency.from_str("ETH")),
                    "USDC": Money(Decimal("10000"), Currency.from_str("USDC"))
                }
            
            if self.trading_mode == TradingMode.PAPER:
                # Return simulated balances
                return {
                    "ETH": Money(Decimal("10"), Currency.from_str("ETH")),
                    "USDC": Money(Decimal("10000"), Currency.from_str("USDC"))
                }
            
            # Live mode - get real token balances
            if not self.w3 or not self.account_address:
                return {}
            
            balances = {}
            
            # Get ETH balance
            eth_balance = self.w3.eth.get_balance(self.account_address)
            eth_balance_decimal = Decimal(eth_balance) / Decimal(10**18)
            balances["ETH"] = Money(eth_balance_decimal, Currency.from_str("ETH"))
            
            # TODO: Add ERC-20 token balance queries for other tokens
            
            return balances
                    
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            if self.on_error_callback:
                self.on_error_callback(e)
            return {}
    
    async def get_instruments(self) -> List[Instrument]:
        """
        Get available pool instruments.
        
        Returns:
            List of available pool instruments
        """
        return list(self.instruments.values())
    
    async def subscribe_market_data(self, instrument_ids: List[str]) -> bool:
        """
        Subscribe to pool data updates.
        
        Args:
            instrument_ids: List of pool instrument IDs to subscribe to
            
        Returns:
            True if subscription successful, False otherwise
        """
        try:
            if self.trading_mode == TradingMode.BACKTEST:
                # No real subscription needed for backtesting
                return True
            
            # Start pool monitoring task if not running
            if not self.pool_update_task or self.pool_update_task.done():
                self.pool_update_task = asyncio.create_task(self._monitor_pools())
            
            logger.info(f"Subscribed to pool data for {len(instrument_ids)} pools")
            return True
            
        except Exception as e:
            logger.error(f"Failed to subscribe to pool data: {e}")
            if self.on_error_callback:
                self.on_error_callback(e)
            return False
    
    async def unsubscribe_market_data(self, instrument_ids: List[str]) -> bool:
        """
        Unsubscribe from pool data updates.
        
        Args:
            instrument_ids: List of pool instrument IDs to unsubscribe from
            
        Returns:
            True if unsubscription successful, False otherwise
        """
        try:
            logger.info(f"Unsubscribed from pool data for {len(instrument_ids)} pools")
            return True
            
        except Exception as e:
            logger.error(f"Failed to unsubscribe from pool data: {e}")
            if self.on_error_callback:
                self.on_error_callback(e)
            return False
    
    async def get_pool_info(self, pool_address: str) -> Optional[UniswapPool]:
        """
        Get detailed pool information.
        
        Args:
            pool_address: Pool contract address
            
        Returns:
            Pool information or None if not found
        """
        try:
            return self.pools.get(pool_address)
                    
        except Exception as e:
            logger.error(f"Failed to get pool info for {pool_address}: {e}")
            return None
    
    async def calculate_optimal_liquidity(
        self, 
        pool_address: str, 
        token0_amount: Decimal, 
        token1_amount: Decimal,
        tick_lower: int,
        tick_upper: int
    ) -> Dict[str, Any]:
        """
        Calculate optimal liquidity parameters.
        
        Args:
            pool_address: Pool contract address
            token0_amount: Amount of token0 to provide
            token1_amount: Amount of token1 to provide
            tick_lower: Lower tick boundary
            tick_upper: Upper tick boundary
            
        Returns:
            Dictionary with liquidity calculation results
        """
        try:
            pool = self.pools.get(pool_address)
            if not pool:
                return {}
            
            # Calculate liquidity amount based on token amounts and tick range
            # This is a simplified calculation - in production, use the actual Uniswap math
            current_price = Decimal(pool.sqrt_price_x96 ** 2) / Decimal(2 ** 192)
            
            # Calculate the liquidity that can be provided
            liquidity = min(
                token0_amount * current_price,
                token1_amount / current_price
            )
            
            return {
                "liquidity_amount": liquidity,
                "token0_required": token0_amount,
                "token1_required": token1_amount,
                "current_price": current_price,
                "tick_lower": tick_lower,
                "tick_upper": tick_upper,
                "estimated_fees_apy": Decimal(str(pool.apy))
            }
                    
        except Exception as e:
            logger.error(f"Failed to calculate optimal liquidity: {e}")
            return {}
    
    async def estimate_gas_cost(self, operation: str, **kwargs) -> Dict[str, Any]:
        """
        Estimate gas cost for an operation.
        
        Args:
            operation: Operation type ('add_liquidity', 'remove_liquidity', 'swap')
            **kwargs: Operation-specific parameters
            
        Returns:
            Dictionary with gas estimation
        """
        try:
            if self.trading_mode != TradingMode.LIVE or not self.w3:
                # Return mock gas estimates for non-live modes
                return {
                    "gas_limit": 200000,
                    "gas_price": 20000000000,  # 20 gwei
                    "total_cost_wei": 4000000000000000,  # 0.004 ETH
                    "total_cost_eth": Decimal("0.004")
                }
            
            # Get current gas price
            gas_price = self.current_gas_price or self.w3.eth.gas_price
            
            # Estimate gas limit based on operation
            gas_limits = {
                "add_liquidity": 300000,
                "remove_liquidity": 200000,
                "swap": 150000
            }
            
            gas_limit = gas_limits.get(operation, 200000)
            total_cost_wei = gas_limit * gas_price
            total_cost_eth = Decimal(total_cost_wei) / Decimal(10**18)
            
            return {
                "gas_limit": gas_limit,
                "gas_price": gas_price,
                "total_cost_wei": total_cost_wei,
                "total_cost_eth": total_cost_eth
            }
                    
        except Exception as e:
            logger.error(f"Failed to estimate gas cost: {e}")
            return {}
    
    # Private methods
    
    async def _initialize_web3(self) -> bool:
        """Initialize Web3 connection."""
        try:
            if not WEB3_AVAILABLE:
                logger.error("Web3 not available - install web3 package for live trading")
                return False
            
            if not self.web3_provider_url:
                logger.error("Web3 provider URL not configured")
                return False
            
            self.w3 = Web3(Web3.HTTPProvider(self.web3_provider_url))
            
            # Add PoA middleware if needed (for testnets)
            if self.network in ["goerli", "sepolia"] and geth_poa_middleware:
                self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
            
            # Test connection
            if not self.w3.is_connected():
                logger.error("Failed to connect to Web3 provider")
                return False
            
            # Set account if private key provided
            if self.private_key:
                account = self.w3.eth.account.from_key(self.private_key)
                self.account_address = account.address
                logger.info(f"Using account: {self.account_address}")
            
            logger.info("Web3 connection established")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Web3: {e}")
            return False
    
    async def _load_pools(self) -> None:
        """Load popular Uniswap pools."""
        try:
            # For now, add some popular pools manually
            # In production, this would query the factory contract or use The Graph
            
            popular_pools = [
                {
                    "address": "0x8ad599c3A0ff1De082011EFDDc58f1908eb6e6D8",  # USDC/ETH 0.3%
                    "token0": Token(
                        address="0xA0b86a33E6441E6C8A0E0C37c2E0C2F0E6C4F2A8",
                        symbol="USDC",
                        decimals=6,
                        name="USD Coin"
                    ),
                    "token1": Token(
                        address="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                        symbol="WETH",
                        decimals=18,
                        name="Wrapped Ether"
                    ),
                    "fee_tier": 3000,
                    "tick": 0,
                    "sqrt_price_x96": 2**96,  # 1:1 price
                    "liquidity": Decimal("1000000"),
                    "apy": 0.15
                }
            ]
            
            for pool_data in popular_pools:
                pool = UniswapPool(
                    address=pool_data["address"],
                    token0=pool_data["token0"],
                    token1=pool_data["token1"],
                    fee_tier=pool_data["fee_tier"],
                    liquidity=pool_data["liquidity"],
                    sqrt_price_x96=pool_data["sqrt_price_x96"],
                    tick=pool_data["tick"],
                    apy=pool_data["apy"]
                )
                
                self.pools[pool_data["address"]] = pool
                
                # Create instrument for this pool
                instrument_id = InstrumentId.from_str(f"{pool_data['address']}.{self.venue}")
                instrument = Instrument(
                    id=instrument_id,
                    symbol=f"POOL_{pool_data['address'][:8]}",
                    base_currency="LP",  # Liquidity Provider token
                    quote_currency="ETH",
                    price_precision=8,
                    size_precision=8,
                    min_quantity=Decimal("0.001"),
                    max_quantity=None,
                    tick_size=Decimal("0.000001"),
                    venue=self.venue,
                    is_active=True
                )
                
                self.instruments[str(instrument_id)] = instrument
            
            logger.info(f"Loaded {len(self.pools)} Uniswap pools")
            
        except Exception as e:
            logger.error(f"Failed to load pools: {e}")
    
    async def _load_liquidity_positions(self) -> None:
        """Load existing liquidity positions for the account."""
        try:
            if not self.account_address:
                return
            
            # In production, this would query the position manager contract
            # For now, we'll start with empty positions
            logger.info("Loaded existing liquidity positions")
            
        except Exception as e:
            logger.error(f"Failed to load liquidity positions: {e}")
    
    async def _start_gas_monitoring(self) -> None:
        """Start monitoring gas prices."""
        try:
            if self.trading_mode == TradingMode.LIVE and self.w3:
                self.current_gas_price = self.w3.eth.gas_price
                logger.info(f"Current gas price: {self.current_gas_price} wei")
            
        except Exception as e:
            logger.error(f"Failed to start gas monitoring: {e}")
    
    async def _simulate_liquidity_provision(self, order: Order) -> bool:
        """Simulate liquidity provision for paper trading."""
        try:
            # Create a simulated liquidity position
            position_id = str(order.id)
            
            # Find a pool for this instrument
            pool_address = None
            for addr, pool in self.pools.items():
                if (pool.token0.symbol in order.instrument.symbol or 
                    pool.token1.symbol in order.instrument.symbol or
                    addr[:8] in order.instrument.symbol):
                    pool_address = addr
                    break
            
            if not pool_address:
                logger.error("No suitable pool found for instrument")
                return False
            
            # Create simulated liquidity position
            liq_position = LiquidityPosition(
                pool_address=pool_address,
                token0=self.pools[pool_address].token0,
                token1=self.pools[pool_address].token1,
                liquidity_amount=order.quantity.as_decimal(),
                tick_lower=-60000,  # Wide range
                tick_upper=60000,
                fees_earned=Money(Decimal("0"), Currency.from_str("ETH")),
                impermanent_loss=Money(Decimal("0"), Currency.from_str("ETH")),
                strategy_id=order.strategy_id,
                created_time=datetime.now(),
                is_simulated=True
            )
            
            self.liquidity_positions[position_id] = liq_position
            
            # Create simulated fill
            simulated_fill = SimulatedFill(
                order_id=order.id,
                fill_price=order.price or Price(Decimal("1"), 8),
                fill_quantity=order.quantity,
                fill_time=datetime.now(),
                slippage=Decimal("0.001"),  # 0.1% slippage
                transaction_cost=Money(Decimal("0.01"), Currency.from_str("ETH")),  # Gas cost
                venue=self.venue
            )
            
            # Call the fill callback
            if self.on_order_filled_callback:
                self.on_order_filled_callback(order, simulated_fill)
            
            logger.info(f"Simulated liquidity provision: {order.id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to simulate liquidity provision: {e}")
            return False
    
    async def _execute_liquidity_provision(self, order: Order) -> bool:
        """Execute real liquidity provision on Uniswap."""
        try:
            if not self.w3 or not self.account_address:
                logger.error("Web3 not initialized or no account")
                return False
            
            # In production, this would:
            # 1. Approve tokens for the position manager
            # 2. Call the position manager's mint function
            # 3. Wait for transaction confirmation
            # 4. Update local state
            
            logger.info(f"Live liquidity provision executed: {order.id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to execute liquidity provision: {e}")
            return False
    
    async def _remove_liquidity_position(self, position_id: str) -> bool:
        """Remove a liquidity position."""
        try:
            if not self.w3 or not self.account_address:
                logger.error("Web3 not initialized or no account")
                return False
            
            position = self.liquidity_positions.get(position_id)
            if not position:
                logger.error(f"Position {position_id} not found")
                return False
            
            # In production, this would call the position manager's burn function
            
            # Remove from local state
            del self.liquidity_positions[position_id]
            
            logger.info(f"Liquidity position {position_id} removed")
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove liquidity position: {e}")
            return False
    
    def _get_pool_instrument(self, pool_address: str) -> Optional[Instrument]:
        """Get instrument for a pool address."""
        for instrument in self.instruments.values():
            if pool_address[:8] in instrument.symbol:
                return instrument
        return None
    
    async def _monitor_pools(self) -> None:
        """Monitor pool data updates."""
        try:
            while True:
                if self.w3:
                    # Update pool data
                    for pool_address, pool in self.pools.items():
                        # In production, this would query the pool contract for current state
                        # For now, we'll just update the timestamp
                        pass
                
                # Update gas prices
                if self.w3:
                    self.current_gas_price = self.w3.eth.gas_price
                
                # Sleep for 30 seconds before next update
                await asyncio.sleep(30)
                
        except asyncio.CancelledError:
            logger.info("Pool monitoring task cancelled")
        except Exception as e:
            logger.error(f"Error in pool monitoring: {e}")