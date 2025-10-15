"""
Binance exchange adapter implementation.
"""

import asyncio
import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any, Callable
import aiohttp
import websockets

from nautilus_trader.model.identifiers import Venue, InstrumentId, ClientOrderId, PositionId, StrategyId
from nautilus_trader.model.enums import OrderSide, OrderType, TimeInForce, PositionSide
from nautilus_trader.model.objects import Money, Price, Quantity, Currency
from nautilus_trader.model.data import QuoteTick

from ..core.adapter import ExchangeAdapter
from ..models.trading_mode import TradingMode
from ..models.core import Order, Position, Instrument, SimulatedFill


logger = logging.getLogger(__name__)


class BinanceAdapter(ExchangeAdapter):
    """
    Binance exchange adapter with REST and WebSocket connectivity.
    
    Supports spot and futures trading with real-time market data streaming.
    """
    
    def __init__(
        self,
        config: Dict[str, Any],
        trading_mode: TradingMode = TradingMode.BACKTEST
    ):
        """
        Initialize Binance adapter.
        
        Args:
            config: Configuration dictionary containing:
                - api_key: Binance API key
                - api_secret: Binance API secret
                - testnet: Whether to use testnet (default: True)
                - base_url: Base URL for REST API
                - ws_url: WebSocket URL
            trading_mode: Current trading mode
        """
        venue = Venue("BINANCE")
        super().__init__(venue, config, trading_mode)
        
        # Configuration
        self.api_key = config.get("api_key", "")
        self.api_secret = config.get("api_secret", "")
        self.testnet = config.get("testnet", True)
        
        # URLs
        if self.testnet:
            self.base_url = config.get("base_url", "https://testnet.binance.vision/api")
            self.ws_url = config.get("ws_url", "wss://testnet.binance.vision/ws")
        else:
            self.base_url = config.get("base_url", "https://api.binance.com/api")
            self.ws_url = config.get("ws_url", "wss://stream.binance.com:9443/ws")
        
        # Connection management
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws_connection: Optional[websockets.WebSocketServerProtocol] = None
        self.subscribed_symbols: set = set()
        
        # Market data
        self.market_data_task: Optional[asyncio.Task] = None
        self.last_prices: Dict[str, Price] = {}
        
        logger.info(f"Initialized Binance adapter in {trading_mode.value} mode")
    
    async def connect(self) -> bool:
        """
        Connect to Binance API.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            if self.trading_mode == TradingMode.BACKTEST:
                # No real connection needed for backtesting
                self.is_connected = True
                logger.info("Binance adapter connected (backtest mode)")
                return True
            
            # Create HTTP session
            self.session = aiohttp.ClientSession()
            
            # Test connection
            if not await self._test_connection():
                await self.disconnect()
                return False
            
            # Load instruments
            await self._load_instruments()
            
            # Load account information if in live mode
            if self.trading_mode == TradingMode.LIVE:
                await self._load_account_info()
            
            self.is_connected = True
            logger.info(f"Binance adapter connected successfully ({self.trading_mode.value} mode)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Binance: {e}")
            if self.on_error_callback:
                self.on_error_callback(e)
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from Binance API."""
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
            if self.ws_connection:
                await self.ws_connection.close()
                self.ws_connection = None
            
            # Close HTTP session
            if self.session:
                await self.session.close()
                self.session = None
            
            self.is_connected = False
            self.subscribed_symbols.clear()
            logger.info("Binance adapter disconnected")
            
        except Exception as e:
            logger.error(f"Error during Binance disconnect: {e}")
    
    async def submit_order(self, order: Order) -> bool:
        """
        Submit an order to Binance.
        
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
            
            order = self.orders.get(order_id)
            if not order:
                return False
            
            params = {
                "symbol": order.instrument.symbol,
                "orderId": order_id,
                "timestamp": int(datetime.now().timestamp() * 1000)
            }
            
            # Add signature for authenticated request
            params = self._sign_request(params)
            
            async with self.session.delete(
                f"{self.base_url}/v3/order",
                params=params,
                headers=self._get_headers()
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
                        "orderId": order_id,
                        "status": "FILLED",  # Assume filled for simulation
                        "executedQty": str(order.quantity),
                        "price": str(order.price) if order.price else "0"
                    }
                return None
            
            # Live mode - get real order status
            if not self.session:
                return None
            
            order = self.orders.get(order_id)
            if not order:
                return None
            
            params = {
                "symbol": order.instrument.symbol,
                "orderId": order_id,
                "timestamp": int(datetime.now().timestamp() * 1000)
            }
            
            params = self._sign_request(params)
            
            async with self.session.get(
                f"{self.base_url}/v3/order",
                params=params,
                headers=self._get_headers()
            ) as response:
                if response.status == 200:
                    return await response.json()
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
            
            params = {
                "timestamp": int(datetime.now().timestamp() * 1000)
            }
            
            params = self._sign_request(params)
            
            async with self.session.get(
                f"{self.base_url}/v3/account",
                params=params,
                headers=self._get_headers()
            ) as response:
                if response.status == 200:
                    account_data = await response.json()
                    return self._parse_positions(account_data.get("balances", []))
                else:
                    logger.error(f"Failed to get positions: {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            if self.on_error_callback:
                self.on_error_callback(e)
            return []
    
    async def get_balance(self) -> Dict[str, Money]:
        """
        Get account balance.
        
        Returns:
            Dictionary of currency balances
        """
        try:
            if self.trading_mode == TradingMode.BACKTEST:
                # Return mock balance for backtesting
                return {
                    "USDT": Money(Decimal("10000"), Currency.from_str("USDT")),
                    "BTC": Money(Decimal("1"), Currency.from_str("BTC"))
                }
            
            if self.trading_mode == TradingMode.PAPER:
                # Return simulated balance
                return {
                    "USDT": Money(Decimal("10000"), Currency.from_str("USDT")),
                    "BTC": Money(Decimal("1"), Currency.from_str("BTC"))
                }
            
            # Live mode - get real balance
            if not self.session:
                return {}
            
            params = {
                "timestamp": int(datetime.now().timestamp() * 1000)
            }
            
            params = self._sign_request(params)
            
            async with self.session.get(
                f"{self.base_url}/v3/account",
                params=params,
                headers=self._get_headers()
            ) as response:
                if response.status == 200:
                    account_data = await response.json()
                    return self._parse_balances(account_data.get("balances", []))
                else:
                    logger.error(f"Failed to get balance: {response.status}")
                    return {}
                    
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            if self.on_error_callback:
                self.on_error_callback(e)
            return {}
    
    async def get_instruments(self) -> List[Instrument]:
        """
        Get available instruments.
        
        Returns:
            List of available instruments
        """
        return list(self.instruments.values())
    
    async def subscribe_market_data(self, instrument_ids: List[str]) -> bool:
        """
        Subscribe to market data for instruments.
        
        Args:
            instrument_ids: List of instrument IDs to subscribe to
            
        Returns:
            True if subscription successful, False otherwise
        """
        try:
            if self.trading_mode == TradingMode.BACKTEST:
                # No real subscription needed for backtesting
                return True
            
            # Convert instrument IDs to symbols
            symbols = []
            for instrument_id in instrument_ids:
                instrument = self.instruments.get(instrument_id)
                if instrument:
                    symbols.append(instrument.symbol.lower())
            
            if not symbols:
                return False
            
            # Start WebSocket connection if not already connected
            if not self.ws_connection:
                await self._connect_websocket()
            
            # Subscribe to ticker streams
            for symbol in symbols:
                stream_name = f"{symbol}@ticker"
                if stream_name not in self.subscribed_symbols:
                    self.subscribed_symbols.add(stream_name)
            
            # Start market data task if not running
            if not self.market_data_task or self.market_data_task.done():
                self.market_data_task = asyncio.create_task(self._handle_market_data())
            
            logger.info(f"Subscribed to market data for {len(symbols)} instruments")
            return True
            
        except Exception as e:
            logger.error(f"Failed to subscribe to market data: {e}")
            if self.on_error_callback:
                self.on_error_callback(e)
            return False
    
    async def unsubscribe_market_data(self, instrument_ids: List[str]) -> bool:
        """
        Unsubscribe from market data for instruments.
        
        Args:
            instrument_ids: List of instrument IDs to unsubscribe from
            
        Returns:
            True if unsubscription successful, False otherwise
        """
        try:
            # Convert instrument IDs to symbols and remove from subscriptions
            symbols = []
            for instrument_id in instrument_ids:
                instrument = self.instruments.get(instrument_id)
                if instrument:
                    symbol = instrument.symbol.lower()
                    symbols.append(symbol)
                    stream_name = f"{symbol}@ticker"
                    self.subscribed_symbols.discard(stream_name)
            
            logger.info(f"Unsubscribed from market data for {len(symbols)} instruments")
            return True
            
        except Exception as e:
            logger.error(f"Failed to unsubscribe from market data: {e}")
            if self.on_error_callback:
                self.on_error_callback(e)
            return False
    
    # Private methods
    
    async def _test_connection(self) -> bool:
        """Test connection to Binance API."""
        try:
            if not self.session:
                return False
            
            async with self.session.get(f"{self.base_url}/v3/ping") as response:
                return response.status == 200
                
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False
    
    async def _load_instruments(self) -> None:
        """Load available instruments from Binance."""
        try:
            if not self.session:
                return
            
            async with self.session.get(f"{self.base_url}/v3/exchangeInfo") as response:
                if response.status == 200:
                    data = await response.json()
                    self._parse_instruments(data.get("symbols", []))
                else:
                    logger.error(f"Failed to load instruments: {response.status}")
                    
        except Exception as e:
            logger.error(f"Failed to load instruments: {e}")
    
    def _parse_instruments(self, symbols_data: List[Dict]) -> None:
        """Parse instruments from exchange info."""
        for symbol_data in symbols_data:
            if symbol_data.get("status") != "TRADING":
                continue
            
            symbol = symbol_data["symbol"]
            base_asset = symbol_data["baseAsset"]
            quote_asset = symbol_data["quoteAsset"]
            
            # Extract precision and filters
            price_precision = symbol_data.get("quotePrecision", 8)
            quantity_precision = symbol_data.get("baseAssetPrecision", 8)
            
            # Parse filters
            min_qty = Decimal("0.001")
            max_qty = None
            tick_size = Decimal("0.01")
            
            for filter_data in symbol_data.get("filters", []):
                if filter_data["filterType"] == "LOT_SIZE":
                    min_qty = Decimal(filter_data["minQty"])
                    if filter_data["maxQty"] != "0.00000000":
                        max_qty = Decimal(filter_data["maxQty"])
                elif filter_data["filterType"] == "PRICE_FILTER":
                    tick_size = Decimal(filter_data["tickSize"])
            
            instrument_id = InstrumentId.from_str(f"{symbol}.{self.venue}")
            
            instrument = Instrument(
                id=instrument_id,
                symbol=symbol,
                base_currency=base_asset,
                quote_currency=quote_asset,
                price_precision=price_precision,
                size_precision=quantity_precision,
                min_quantity=min_qty,
                max_quantity=max_qty,
                tick_size=tick_size,
                venue=self.venue,
                is_active=True
            )
            
            self.instruments[str(instrument_id)] = instrument
        
        logger.info(f"Loaded {len(self.instruments)} instruments from Binance")
    
    async def _load_account_info(self) -> None:
        """Load account information for live trading."""
        try:
            if not self.session:
                return
            
            params = {
                "timestamp": int(datetime.now().timestamp() * 1000)
            }
            
            params = self._sign_request(params)
            
            async with self.session.get(
                f"{self.base_url}/v3/account",
                params=params,
                headers=self._get_headers()
            ) as response:
                if response.status == 200:
                    account_data = await response.json()
                    logger.info("Account information loaded successfully")
                else:
                    logger.error(f"Failed to load account info: {response.status}")
                    
        except Exception as e:
            logger.error(f"Failed to load account info: {e}")
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for authenticated requests."""
        return {
            "X-MBX-APIKEY": self.api_key,
            "Content-Type": "application/json"
        }
    
    def _sign_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Sign request parameters for authentication."""
        # This is a simplified version - in production, implement proper HMAC signing
        # For now, just return params as-is for testnet
        return params
    
    async def _simulate_order_execution(self, order: Order) -> bool:
        """Simulate order execution for paper trading."""
        try:
            # Get current market price
            market_price = self.last_prices.get(order.instrument.symbol)
            if not market_price:
                # Use a default price if no market data available
                market_price = Price(Decimal("50000"), 2)  # Default BTC price
            
            # Simulate the fill
            simulated_fill = self.simulate_order_execution(order, market_price)
            
            # Store the order
            self.orders[str(order.id)] = order
            
            # Call the fill callback
            if self.on_order_filled_callback:
                self.on_order_filled_callback(order, simulated_fill)
            
            logger.info(f"Simulated order execution: {order.id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to simulate order execution: {e}")
            return False
    
    async def _execute_live_order(self, order: Order) -> bool:
        """Execute a real order on Binance."""
        try:
            if not self.session:
                return False
            
            # Prepare order parameters
            params = {
                "symbol": order.instrument.symbol,
                "side": order.side.name,
                "type": order.order_type.name,
                "quantity": str(order.quantity),
                "timestamp": int(datetime.now().timestamp() * 1000)
            }
            
            if order.price:
                params["price"] = str(order.price)
            
            if order.time_in_force:
                params["timeInForce"] = order.time_in_force.name
            
            # Sign the request
            params = self._sign_request(params)
            
            async with self.session.post(
                f"{self.base_url}/v3/order",
                data=params,
                headers=self._get_headers()
            ) as response:
                if response.status == 200:
                    order_result = await response.json()
                    self.orders[str(order.id)] = order
                    logger.info(f"Live order executed: {order.id}")
                    return True
                else:
                    logger.error(f"Failed to execute live order: {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to execute live order: {e}")
            return False
    
    def _parse_positions(self, balances_data: List[Dict]) -> List[Position]:
        """Parse positions from account balances."""
        positions = []
        
        for balance in balances_data:
            asset = balance["asset"]
            free = Decimal(balance["free"])
            locked = Decimal(balance["locked"])
            total = free + locked
            
            if total > 0:
                # Create a position for non-zero balances
                instrument_id = InstrumentId.from_str(f"{asset}USDT.{self.venue}")
                instrument = self.instruments.get(str(instrument_id))
                
                if instrument:
                    position_id = PositionId(f"{asset}_POSITION")
                    position = Position(
                        id=position_id,
                        instrument=instrument,
                        side=PositionSide.LONG,
                        quantity=Quantity(total, instrument.size_precision),
                        avg_price=Price(Decimal("1"), instrument.price_precision),
                        unrealized_pnl=Money(Decimal("0"), Currency.from_str("USDT")),
                        venue=self.venue,
                        strategy_id=StrategyId("DEFAULT-STRATEGY"),
                        opened_time=datetime.now(),
                        is_simulated=False
                    )
                    positions.append(position)
        
        return positions
    
    def _parse_balances(self, balances_data: List[Dict]) -> Dict[str, Money]:
        """Parse balances from account data."""
        balances = {}
        
        for balance in balances_data:
            asset = balance["asset"]
            free = Decimal(balance["free"])
            locked = Decimal(balance["locked"])
            total = free + locked
            
            if total > 0:
                currency = Currency.from_str(asset)
                balances[asset] = Money(total, currency)
        
        return balances
    
    async def _connect_websocket(self) -> None:
        """Connect to Binance WebSocket for market data."""
        try:
            # Create WebSocket URL with subscribed streams
            if self.subscribed_symbols:
                streams = "/".join(self.subscribed_symbols)
                ws_url = f"{self.ws_url}/{streams}"
            else:
                ws_url = self.ws_url
            
            self.ws_connection = await websockets.connect(ws_url)
            logger.info("WebSocket connected to Binance")
            
        except Exception as e:
            logger.error(f"Failed to connect WebSocket: {e}")
    
    async def _handle_market_data(self) -> None:
        """Handle incoming market data from WebSocket."""
        try:
            if not self.ws_connection:
                return
            
            async for message in self.ws_connection:
                try:
                    data = json.loads(message)
                    await self._process_market_data(data)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON received: {message}")
                except Exception as e:
                    logger.error(f"Error processing market data: {e}")
                    
        except websockets.exceptions.ConnectionClosed:
            logger.warning("WebSocket connection closed")
        except Exception as e:
            logger.error(f"Market data handler error: {e}")
    
    async def _process_market_data(self, data: Dict[str, Any]) -> None:
        """Process market data message."""
        try:
            if data.get("e") == "24hrTicker":
                symbol = data["s"]
                price = Price(Decimal(data["c"]), 8)  # Close price
                
                # Store last price
                self.last_prices[symbol] = price
                
                # Create quote tick
                instrument_id = InstrumentId.from_str(f"{symbol}.{self.venue}")
                instrument = self.instruments.get(str(instrument_id))
                
                if instrument and self.on_market_data_callback:
                    # Create a simple quote tick (simplified for this implementation)
                    quote_tick = QuoteTick(
                        instrument_id=instrument_id,
                        bid_price=price,
                        ask_price=price,
                        bid_size=Quantity(Decimal("1"), instrument.size_precision),
                        ask_size=Quantity(Decimal("1"), instrument.size_precision),
                        ts_event=int(datetime.now().timestamp() * 1_000_000_000),
                        ts_init=int(datetime.now().timestamp() * 1_000_000_000)
                    )
                    
                    self.on_market_data_callback(quote_tick)
                    
        except Exception as e:
            logger.error(f"Error processing market data: {e}")