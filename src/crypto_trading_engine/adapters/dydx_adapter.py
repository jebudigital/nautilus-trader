"""
dYdX perpetual exchange adapter implementation.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any, Callable
import aiohttp

from nautilus_trader.model.identifiers import Venue, InstrumentId, ClientOrderId, PositionId, StrategyId
from nautilus_trader.model.enums import OrderSide, OrderType, TimeInForce, PositionSide
from nautilus_trader.model.objects import Money, Price, Quantity, Currency
from nautilus_trader.model.data import QuoteTick

from ..core.adapter import ExchangeAdapter
from ..models.trading_mode import TradingMode
from ..models.core import Order, Position, Instrument, SimulatedFill
from ..models.perpetuals import FundingRate


logger = logging.getLogger(__name__)


class DydxAdapter(ExchangeAdapter):
    """
    dYdX perpetual exchange adapter.
    
    Supports perpetual contract trading with position management,
    margin calculations, and funding rate monitoring.
    """
    
    def __init__(
        self,
        config: Dict[str, Any],
        trading_mode: TradingMode = TradingMode.BACKTEST
    ):
        """
        Initialize dYdX adapter.
        
        Args:
            config: Configuration dictionary containing:
                - api_key: dYdX API key
                - api_secret: dYdX API secret
                - passphrase: dYdX passphrase
                - testnet: Whether to use testnet (default: True)
                - base_url: Base URL for REST API
                - ws_url: WebSocket URL
            trading_mode: Current trading mode
        """
        venue = Venue("DYDX")
        super().__init__(venue, config, trading_mode)
        
        # Configuration
        self.api_key = config.get("api_key", "")
        self.api_secret = config.get("api_secret", "")
        self.passphrase = config.get("passphrase", "")
        self.testnet = config.get("testnet", True)
        
        # URLs
        if self.testnet:
            self.base_url = config.get("base_url", "https://api.stage.dydx.exchange")
            self.ws_url = config.get("ws_url", "wss://api.stage.dydx.exchange/v3/ws")
        else:
            self.base_url = config.get("base_url", "https://api.dydx.exchange")
            self.ws_url = config.get("ws_url", "wss://api.dydx.exchange/v3/ws")
        
        # Connection management
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws_connection: Optional[aiohttp.ClientWebSocketResponse] = None
        self.subscribed_markets: set = set()
        
        # Market data
        self.market_data_task: Optional[asyncio.Task] = None
        self.last_prices: Dict[str, Price] = {}
        self.funding_rates: Dict[str, FundingRate] = {}
        
        # Position tracking
        self.margin_info: Dict[str, Any] = {}
        
        logger.info(f"Initialized dYdX adapter in {trading_mode.value} mode")
    
    async def connect(self) -> bool:
        """
        Connect to dYdX API.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            if self.trading_mode == TradingMode.BACKTEST:
                # No real connection needed for backtesting
                self.is_connected = True
                logger.info("dYdX adapter connected (backtest mode)")
                return True
            
            # Create HTTP session
            self.session = aiohttp.ClientSession()
            
            # Test connection
            if not await self._test_connection():
                await self.disconnect()
                return False
            
            # Load markets (instruments)
            await self._load_markets()
            
            # Load account information if in live mode
            if self.trading_mode == TradingMode.LIVE:
                await self._load_account_info()
            
            self.is_connected = True
            logger.info(f"dYdX adapter connected successfully ({self.trading_mode.value} mode)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to dYdX: {e}")
            if self.on_error_callback:
                self.on_error_callback(e)
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from dYdX API."""
        try:
            # Stop market data task
            if self.market_data_task and not self.market_data_task.done():
                self.market_data_task.cancel()
                try:
                    await self.market_data_task
                except asyncio.CancelledError:
                    pass
                self.market_data_task = None
            
            # Close WebSocket connection
            if self.ws_connection and not self.ws_connection.closed:
                await self.ws_connection.close()
                self.ws_connection = None
            
            # Close HTTP session
            if self.session:
                await self.session.close()
                self.session = None
            
            self.is_connected = False
            self.subscribed_markets.clear()
            logger.info("dYdX adapter disconnected")
            
        except Exception as e:
            logger.error(f"Error during dYdX disconnect: {e}")
    
    async def submit_order(self, order: Order) -> bool:
        """
        Submit an order to dYdX.
        
        Args:
            order: Order to submit
            
        Returns:
            True if order submitted successfully, False otherwise
        """
        try:
            if not self.validate_order(order):
                logger.error(f"Order validation failed: {order.id}")
                return False
            
            if self.trading_mode == TradingMode.PAPER:
                # Simulate order execution for paper trading
                return await self._simulate_order_execution(order)
            
            elif self.trading_mode == TradingMode.LIVE:
                # Execute real order
                return await self._execute_live_order(order)
            
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
        Cancel an order.
        
        Args:
            order_id: ID of order to cancel
            
        Returns:
            True if order cancelled successfully, False otherwise
        """
        try:
            if self.trading_mode == TradingMode.BACKTEST:
                logger.warning("Order cancellation not supported in backtest mode")
                return False
            
            if self.trading_mode == TradingMode.PAPER:
                # Remove from simulated orders
                if order_id in self.orders:
                    del self.orders[order_id]
                    logger.info(f"Simulated order {order_id} cancelled")
                    return True
                return False
            
            # Live mode - cancel real order
            if not self.session:
                return False
            
            headers = self._get_headers()
            
            async with self.session.delete(
                f"{self.base_url}/v3/orders/{order_id}",
                headers=headers
            ) as response:
                if response.status == 200:
                    if order_id in self.orders:
                        del self.orders[order_id]
                    logger.info(f"Order {order_id} cancelled successfully")
                    return True
                else:
                    logger.error(f"Failed to cancel order {order_id}: {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            if self.on_error_callback:
                self.on_error_callback(e)
            return False
    
    async def get_order_status(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        Get order status.
        
        Args:
            order_id: Order ID to check
            
        Returns:
            Order status information or None if not found
        """
        try:
            if self.trading_mode == TradingMode.BACKTEST:
                return None
            
            if self.trading_mode == TradingMode.PAPER:
                # Return simulated order status
                order = self.orders.get(order_id)
                if order:
                    return {
                        "id": order_id,
                        "status": "FILLED",  # Assume filled for simulation
                        "size": str(order.quantity),
                        "price": str(order.price) if order.price else "0"
                    }
                return None
            
            # Live mode - get real order status
            if not self.session:
                return None
            
            headers = self._get_headers()
            
            async with self.session.get(
                f"{self.base_url}/v3/orders/{order_id}",
                headers=headers
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("order")
                else:
                    logger.error(f"Failed to get order status {order_id}: {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"Failed to get order status {order_id}: {e}")
            if self.on_error_callback:
                self.on_error_callback(e)
            return None
    
    async def get_positions(self) -> List[Position]:
        """
        Get current positions.
        
        Returns:
            List of current positions
        """
        try:
            if self.trading_mode == TradingMode.BACKTEST:
                return list(self.positions.values())
            
            if self.trading_mode == TradingMode.PAPER:
                # Return simulated positions
                return [pos for pos in self.positions.values() if pos.is_simulated]
            
            # Live mode - get real positions
            if not self.session:
                return []
            