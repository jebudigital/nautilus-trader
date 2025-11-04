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
            
            headers = self._get_headers()
            
            async with self.session.get(
                f"{self.base_url}/v3/positions",
                headers=headers
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_positions(data.get("positions", []))
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
                    "USDC": Money(Decimal("10000"), Currency.from_str("USDC"))
                }
            
            if self.trading_mode == TradingMode.PAPER:
                # Return simulated balance
                return {
                    "USDC": Money(Decimal("10000"), Currency.from_str("USDC"))
                }
            
            # Live mode - get real balance
            if not self.session:
                return {}
            
            headers = self._get_headers()
            
            async with self.session.get(
                f"{self.base_url}/v3/accounts",
                headers=headers
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    account = data.get("account", {})
                    return self._parse_balance(account)
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
            
            # Convert instrument IDs to market names
            markets = []
            for instrument_id in instrument_ids:
                instrument = self.instruments.get(instrument_id)
                if instrument:
                    markets.append(instrument.symbol)
            
            if not markets:
                return False
            
            # Start WebSocket connection if not already connected
            if not self.ws_connection or self.ws_connection.closed:
                await self._connect_websocket()
            
            # Subscribe to market streams
            for market in markets:
                if market not in self.subscribed_markets:
                    await self._subscribe_to_market(market)
                    self.subscribed_markets.add(market)
            
            # Start market data task if not running
            if not self.market_data_task or self.market_data_task.done():
                self.market_data_task = asyncio.create_task(self._handle_market_data())
            
            logger.info(f"Subscribed to market data for {len(markets)} instruments")
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
            # Convert instrument IDs to market names and remove from subscriptions
            markets = []
            for instrument_id in instrument_ids:
                instrument = self.instruments.get(instrument_id)
                if instrument:
                    market = instrument.symbol
                    markets.append(market)
                    self.subscribed_markets.discard(market)
            
            logger.info(f"Unsubscribed from market data for {len(markets)} instruments")
            return True
            
        except Exception as e:
            logger.error(f"Failed to unsubscribe from market data: {e}")
            if self.on_error_callback:
                self.on_error_callback(e)
            return False
    
    async def get_funding_rates(self, market: str) -> List[FundingRate]:
        """
        Get funding rates for a market.
        
        Args:
            market: Market symbol (e.g., "BTC-USD")
            
        Returns:
            List of funding rates
        """
        try:
            if self.trading_mode == TradingMode.BACKTEST:
                # Return mock funding rates for backtesting
                return [
                    FundingRate(
                        instrument=self.instruments.get(f"{market}.{self.venue}") or Instrument(
                            id=InstrumentId.from_str(f"{market}.{self.venue}"),
                            symbol=market,
                            base_currency="BTC",
                            quote_currency="USD",
                            price_precision=2,
                            size_precision=6,
                            min_quantity=Decimal("0.001"),
                            max_quantity=None,
                            tick_size=Decimal("0.01"),
                            venue=self.venue
                        ),
                        rate=Decimal("0.0001"),
                        timestamp=datetime.now(),
                        venue=self.venue,
                        next_funding_time=datetime.now() + timedelta(hours=8)
                    )
                ]
            
            if not self.session:
                return []
            
            async with self.session.get(
                f"{self.base_url}/v3/historical-funding/{market}"
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_funding_rates(market, data.get("historicalFunding", []))
                else:
                    logger.error(f"Failed to get funding rates for {market}: {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"Failed to get funding rates for {market}: {e}")
            if self.on_error_callback:
                self.on_error_callback(e)
            return []
    
    async def calculate_margin_requirements(self, position_size: Decimal, market: str) -> Dict[str, Decimal]:
        """
        Calculate margin requirements for a position.
        
        Args:
            position_size: Size of the position
            market: Market symbol
            
        Returns:
            Dictionary with margin requirements
        """
        try:
            # Get market info
            instrument = None
            for inst in self.instruments.values():
                if inst.symbol == market:
                    instrument = inst
                    break
            
            if not instrument:
                return {}
            
            # Get current price
            current_price = self.last_prices.get(market)
            if not current_price:
                current_price = Price(Decimal("50000"), 2)  # Default price
            
            # Calculate notional value
            notional_value = abs(position_size) * current_price.as_decimal()
            
            # dYdX typically uses 10x leverage for most markets
            initial_margin_fraction = Decimal("0.1")  # 10% initial margin
            maintenance_margin_fraction = Decimal("0.05")  # 5% maintenance margin
            
            initial_margin = notional_value * initial_margin_fraction
            maintenance_margin = notional_value * maintenance_margin_fraction
            
            return {
                "initial_margin": initial_margin,
                "maintenance_margin": maintenance_margin,
                "notional_value": notional_value,
                "leverage": Decimal("10")
            }
            
        except Exception as e:
            logger.error(f"Failed to calculate margin requirements: {e}")
            return {}
    
    # Private methods
    
    async def _test_connection(self) -> bool:
        """Test connection to dYdX API."""
        try:
            if not self.session:
                return False
            
            async with self.session.get(f"{self.base_url}/v3/time") as response:
                return response.status == 200
                
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False
    
    async def _load_markets(self) -> None:
        """Load available markets from dYdX."""
        try:
            if not self.session:
                return
            
            async with self.session.get(f"{self.base_url}/v3/markets") as response:
                if response.status == 200:
                    data = await response.json()
                    self._parse_markets(data.get("markets", {}))
                else:
                    logger.error(f"Failed to load markets: {response.status}")
                    
        except Exception as e:
            logger.error(f"Failed to load markets: {e}")
    
    def _parse_markets(self, markets_data: Dict[str, Any]) -> None:
        """Parse markets from API response."""
        for market_name, market_data in markets_data.items():
            if market_data.get("status") != "ONLINE":
                continue
            
            # Extract market information
            base_asset = market_data.get("baseAsset", "")
            quote_asset = market_data.get("quoteAsset", "USD")
            
            # Parse precision and size info
            tick_size = Decimal(market_data.get("tickSize", "0.01"))
            step_size = Decimal(market_data.get("stepSize", "0.001"))
            min_order_size = Decimal(market_data.get("minOrderSize", "0.001"))
            
            instrument_id = InstrumentId.from_str(f"{market_name}.{self.venue}")
            
            instrument = Instrument(
                id=instrument_id,
                symbol=market_name,
                base_currency=base_asset,
                quote_currency=quote_asset,
                price_precision=len(str(tick_size).split('.')[-1]) if '.' in str(tick_size) else 0,
                size_precision=len(str(step_size).split('.')[-1]) if '.' in str(step_size) else 0,
                min_quantity=min_order_size,
                max_quantity=None,  # dYdX doesn't specify max order size
                tick_size=tick_size,
                venue=self.venue,
                is_active=True
            )
            
            self.instruments[str(instrument_id)] = instrument
        
        logger.info(f"Loaded {len(self.instruments)} markets from dYdX")
    
    async def _load_account_info(self) -> None:
        """Load account information for live trading."""
        try:
            if not self.session:
                return
            
            headers = self._get_headers()
            
            async with self.session.get(
                f"{self.base_url}/v3/accounts",
                headers=headers
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    self.margin_info = data.get("account", {})
                    logger.info("Account information loaded successfully")
                else:
                    logger.error(f"Failed to load account info: {response.status}")
                    
        except Exception as e:
            logger.error(f"Failed to load account info: {e}")
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for authenticated requests."""
        return {
            "DYDX-API-KEY": self.api_key,
            "DYDX-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json"
        }
    
    async def _simulate_order_execution(self, order: Order) -> bool:
        """Simulate order execution for paper trading."""
        try:
            # Get current market price
            market_price = self.last_prices.get(order.instrument.symbol)
            if not market_price:
                # Use a default price if no market data available
                market_price = Price(Decimal("50000"), 2)  # Default price
            
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
        """Execute a real order on dYdX."""
        try:
            if not self.session:
                return False
            
            # Prepare order parameters
            order_data = {
                "market": order.instrument.symbol,
                "side": order.side.name,
                "type": order.order_type.name,
                "size": str(order.quantity),
                "timeInForce": order.time_in_force.name if order.time_in_force else "GTC"
            }
            
            if order.price:
                order_data["price"] = str(order.price)
            
            headers = self._get_headers()
            
            async with self.session.post(
                f"{self.base_url}/v3/orders",
                json=order_data,
                headers=headers
            ) as response:
                if response.status == 201:
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
    
    def _parse_positions(self, positions_data: List[Dict]) -> List[Position]:
        """Parse positions from API response."""
        positions = []
        
        for pos_data in positions_data:
            market = pos_data.get("market", "")
            size = Decimal(pos_data.get("size", "0"))
            
            if size == 0:
                continue
            
            # Find the instrument
            instrument = None
            for inst in self.instruments.values():
                if inst.symbol == market:
                    instrument = inst
                    break
            
            if not instrument:
                continue
            
            # Determine position side
            side = PositionSide.LONG if size > 0 else PositionSide.SHORT
            
            position_id = PositionId(f"{market}_POSITION")
            position = Position(
                id=position_id,
                instrument=instrument,
                side=side,
                quantity=Quantity(abs(size), instrument.size_precision),
                avg_price=Price(Decimal(pos_data.get("entryPrice", "0")), instrument.price_precision),
                unrealized_pnl=Money(Decimal(pos_data.get("unrealizedPnl", "0")), Currency.from_str("USDC")),
                venue=self.venue,
                strategy_id=StrategyId("DEFAULT-STRATEGY"),
                opened_time=datetime.now(),
                is_simulated=False
            )
            positions.append(position)
        
        return positions
    
    def _parse_balance(self, account_data: Dict[str, Any]) -> Dict[str, Money]:
        """Parse balance from account data."""
        balances = {}
        
        # dYdX uses USDC as the main collateral
        equity = Decimal(account_data.get("equity", "0"))
        if equity > 0:
            balances["USDC"] = Money(equity, Currency.from_str("USDC"))
        
        return balances
    
    def _parse_funding_rates(self, market: str, funding_data: List[Dict]) -> List[FundingRate]:
        """Parse funding rates from API response."""
        funding_rates = []
        
        for rate_data in funding_data:
            rate = Decimal(rate_data.get("rate", "0"))
            effective_at = datetime.fromisoformat(rate_data.get("effectiveAt", "").replace('Z', '+00:00'))
            
            # Find the instrument
            instrument = None
            for inst in self.instruments.values():
                if inst.symbol == market:
                    instrument = inst
                    break
            
            if not instrument:
                continue
            
            funding_rate = FundingRate(
                instrument=instrument,
                rate=rate,
                timestamp=effective_at,
                venue=self.venue,
                next_funding_time=effective_at + timedelta(hours=8)  # dYdX funding every 8 hours
            )
            funding_rates.append(funding_rate)
        
        return funding_rates
    
    async def _connect_websocket(self) -> None:
        """Connect to dYdX WebSocket for market data."""
        try:
            self.ws_connection = await self.session.ws_connect(self.ws_url)
            logger.info("WebSocket connected to dYdX")
            
        except Exception as e:
            logger.error(f"Failed to connect WebSocket: {e}")
    
    async def _subscribe_to_market(self, market: str) -> None:
        """Subscribe to market data for a specific market."""
        try:
            if not self.ws_connection or self.ws_connection.closed:
                return
            
            # Subscribe to orderbook updates
            subscribe_msg = {
                "type": "subscribe",
                "channel": "v3_orderbook",
                "id": market
            }
            
            await self.ws_connection.send_str(json.dumps(subscribe_msg))
            logger.info(f"Subscribed to market data for {market}")
            
        except Exception as e:
            logger.error(f"Failed to subscribe to market {market}: {e}")
    
    async def _handle_market_data(self) -> None:
        """Handle incoming market data from WebSocket."""
        try:
            if not self.ws_connection:
                return
            
            async for msg in self.ws_connection:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        await self._process_market_data(data)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON received: {msg.data}")
                    except Exception as e:
                        logger.error(f"Error processing market data: {e}")
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {self.ws_connection.exception()}")
                    break
                    
        except Exception as e:
            logger.error(f"Market data handler error: {e}")
    
    async def _process_market_data(self, data: Dict[str, Any]) -> None:
        """Process market data message."""
        try:
            if data.get("type") == "channel_data" and data.get("channel") == "v3_orderbook":
                market = data.get("id", "")
                contents = data.get("contents", {})
                
                # Extract best bid/ask prices
                bids = contents.get("bids", [])
                asks = contents.get("asks", [])
                
                if bids and asks:
                    # bids and asks are arrays of [price, size] arrays
                    best_bid = Price(Decimal(bids[0][0]), 8)
                    best_ask = Price(Decimal(asks[0][0]), 8)
                    
                    # Store mid price
                    mid_price = Price((best_bid.as_decimal() + best_ask.as_decimal()) / 2, 8)
                    self.last_prices[market] = mid_price
                    
                    # Create quote tick
                    instrument_id = InstrumentId.from_str(f"{market}.{self.venue}")
                    instrument = self.instruments.get(str(instrument_id))
                    
                    if instrument and self.on_market_data_callback:
                        quote_tick = QuoteTick(
                            instrument_id=instrument_id,
                            bid_price=best_bid,
                            ask_price=best_ask,
                            bid_size=Quantity(Decimal(bids[0][1]), instrument.size_precision),
                            ask_size=Quantity(Decimal(asks[0][1]), instrument.size_precision),
                            ts_event=int(datetime.now().timestamp() * 1_000_000_000),
                            ts_init=int(datetime.now().timestamp() * 1_000_000_000)
                        )
                        
                        self.on_market_data_callback(quote_tick)
                        
        except Exception as e:
            logger.error(f"Error processing market data: {e}")