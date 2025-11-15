"""
Hyperliquid Adapter for NautilusTrader

Hyperliquid is a decentralized perpetuals exchange with:
- On-chain settlement (Arbitrum)
- No API keys (wallet-based auth)
- High leverage (up to 50x)
- Low fees (maker rebates)
"""

import asyncio
import hashlib
import hmac
import json
import time
from decimal import Decimal
from typing import Optional, Dict, List, Any
from datetime import datetime

import aiohttp
from eth_account import Account
from eth_account.messages import encode_defunct

from nautilus_trader.adapters.env import get_env_key
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, Logger
from nautilus_trader.common.enums import LogColor
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.execution.messages import (
    SubmitOrder,
    CancelOrder,
    ModifyOrder,
)
from nautilus_trader.live.data_client import LiveMarketDataClient
from nautilus_trader.live.execution_client import LiveExecutionClient
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.enums import (
    AccountType,
    LiquiditySide,
    OmsType,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
    TrailingOffsetType,
    TriggerType,
)
from nautilus_trader.model.identifiers import (
    AccountId,
    ClientId,
    ClientOrderId,
    InstrumentId,
    Symbol,
    TradeId,
    Venue,
    VenueOrderId,
)
from nautilus_trader.model.instruments import CryptoPerpetual
from nautilus_trader.model.objects import (
    AccountBalance,
    Currency,
    MarginBalance,
    Money,
    Price,
    Quantity,
)
from nautilus_trader.msgbus.bus import MessageBus


VENUE = Venue("HYPERLIQUID")


class HyperliquidHttpClient:
    """HTTP client for Hyperliquid API"""
    
    BASE_URL = "https://api.hyperliquid.xyz"
    
    def __init__(
        self,
        private_key: str,
        wallet_address: str,
        testnet: bool = False,
        session: Optional[aiohttp.ClientSession] = None,
    ):
        self.private_key = private_key
        self.wallet_address = wallet_address
        self.testnet = testnet
        self._session = session
        self._own_session = session is None
        
        # Create account from private key
        self.account = Account.from_key(private_key)
        
        if testnet:
            self.BASE_URL = "https://api.hyperliquid-testnet.xyz"
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session
    
    def _sign_message(self, message: str) -> str:
        """Sign message with private key"""
        message_hash = encode_defunct(text=message)
        signed = self.account.sign_message(message_hash)
        return signed.signature.hex()
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        signed: bool = False,
    ) -> Dict:
        """Make HTTP request"""
        session = await self._get_session()
        url = f"{self.BASE_URL}{endpoint}"
        
        headers = {"Content-Type": "application/json"}
        
        if signed and data:
            # Add signature
            timestamp = int(time.time() * 1000)
            data["timestamp"] = timestamp
            message = json.dumps(data, separators=(',', ':'))
            signature = self._sign_message(message)
            data["signature"] = signature
        
        async with session.request(method, url, json=data, headers=headers) as response:
            response.raise_for_status()
            return await response.json()
    
    async def get_user_state(self) -> Dict:
        """Get user account state"""
        data = {
            "type": "clearinghouseState",
            "user": self.wallet_address,
        }
        return await self._request("POST", "/info", data=data)
    
    async def get_meta(self) -> Dict:
        """Get exchange metadata (instruments)"""
        data = {"type": "meta"}
        return await self._request("POST", "/info", data=data)
    
    async def get_all_mids(self) -> Dict:
        """Get all mid prices"""
        data = {"type": "allMids"}
        return await self._request("POST", "/info", data=data)
    
    async def place_order(
        self,
        coin: str,
        is_buy: bool,
        sz: float,
        limit_px: float,
        order_type: Dict,
        reduce_only: bool = False,
    ) -> Dict:
        """Place order"""
        data = {
            "type": "order",
            "orders": [{
                "coin": coin,
                "is_buy": is_buy,
                "sz": sz,
                "limit_px": limit_px,
                "order_type": order_type,
                "reduce_only": reduce_only,
            }],
            "grouping": "na",
        }
        return await self._request("POST", "/exchange", data=data, signed=True)
    
    async def cancel_order(self, coin: str, oid: int) -> Dict:
        """Cancel order"""
        data = {
            "type": "cancel",
            "cancels": [{
                "coin": coin,
                "oid": oid,
            }],
        }
        return await self._request("POST", "/exchange", data=data, signed=True)
    
    async def get_open_orders(self) -> Dict:
        """Get open orders"""
        data = {
            "type": "openOrders",
            "user": self.wallet_address,
        }
        return await self._request("POST", "/info", data=data)
    
    async def close(self):
        """Close session"""
        if self._own_session and self._session:
            await self._session.close()


class HyperliquidDataClient(LiveMarketDataClient):
    """Hyperliquid data client"""
    
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        client: HyperliquidHttpClient,
        msgbus: MessageBus,
        cache: Cache,
        clock: LiveClock,
        logger: Logger,
    ):
        super().__init__(
            loop=loop,
            client_id=ClientId(f"{VENUE}-DATA"),
            venue=VENUE,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            logger=logger,
        )
        
        self._client = client
        self._instruments: Dict[InstrumentId, CryptoPerpetual] = {}
        self._update_task: Optional[asyncio.Task] = None
    
    async def _connect(self):
        """Connect to Hyperliquid"""
        self._log.info("Connecting to Hyperliquid...")
        
        # Load instruments
        await self._load_instruments()
        
        # Start update loop
        self._update_task = self._loop.create_task(self._update_loop())
        
        self._log.info("Connected to Hyperliquid", LogColor.GREEN)
    
    async def _disconnect(self):
        """Disconnect from Hyperliquid"""
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
        
        await self._client.close()
        self._log.info("Disconnected from Hyperliquid")
    
    async def _load_instruments(self):
        """Load instruments from exchange"""
        self._log.info("Loading instruments...")
        
        meta = await self._client.get_meta()
        universe = meta.get("universe", [])
        
        for asset in universe:
            coin = asset["name"]
            sz_decimals = asset["szDecimals"]
            
            # Create instrument
            instrument_id = InstrumentId(Symbol(f"{coin}-PERP"), VENUE)
            
            instrument = CryptoPerpetual(
                instrument_id=instrument_id,
                raw_symbol=Symbol(coin),
                base_currency=Currency.from_str(coin),
                quote_currency=USD,
                settlement_currency=USD,
                is_inverse=False,
                price_precision=2,
                size_precision=sz_decimals,
                price_increment=Price.from_str("0.01"),
                size_increment=Quantity.from_str(f"0.{'0' * (sz_decimals - 1)}1"),
                max_quantity=Quantity.from_str("1000000"),
                min_quantity=Quantity.from_str(f"0.{'0' * (sz_decimals - 1)}1"),
                max_price=Price.from_str("1000000"),
                min_price=Price.from_str("0.01"),
                margin_init=Decimal("0.02"),  # 50x max leverage
                margin_maint=Decimal("0.01"),
                maker_fee=Decimal("-0.00002"),  # Maker rebate
                taker_fee=Decimal("0.00035"),
                ts_event=self._clock.timestamp_ns(),
                ts_init=self._clock.timestamp_ns(),
            )
            
            self._instruments[instrument_id] = instrument
            self._cache.add_instrument(instrument)
        
        self._log.info(f"Loaded {len(self._instruments)} instruments")
    
    async def _update_loop(self):
        """Update loop for market data via WebSocket"""
        import websockets
        import json
        
        ws_url = "wss://api.hyperliquid.xyz/ws" if not self._client.testnet else "wss://api.hyperliquid-testnet.xyz/ws"
        
        while True:
            try:
                async with websockets.connect(ws_url) as websocket:
                    self._log.info("WebSocket connected")
                    
                    # Subscribe to all mids (prices)
                    subscribe_msg = {
                        "method": "subscribe",
                        "subscription": {
                            "type": "allMids"
                        }
                    }
                    await websocket.send(json.dumps(subscribe_msg))
                    
                    # Subscribe to user events
                    subscribe_user = {
                        "method": "subscribe",
                        "subscription": {
                            "type": "userEvents",
                            "user": self._client.wallet_address
                        }
                    }
                    await websocket.send(json.dumps(subscribe_user))
                    
                    # Listen for messages
                    while True:
                        message = await websocket.recv()
                        data = json.loads(message)
                        
                        # Handle different message types
                        if data.get("channel") == "allMids":
                            # Price updates
                            mids = data.get("data", {}).get("mids", {})
                            # TODO: Convert to Nautilus quote ticks
                            
                        elif data.get("channel") == "user":
                            # User events (fills, orders, etc.)
                            user_data = data.get("data", [])
                            for event in user_data:
                                if event.get("type") == "fill":
                                    self._log.info(f"Fill: {event}")
                                    # TODO: Generate fill event
                                elif event.get("type") == "order":
                                    self._log.info(f"Order: {event}")
                                    # TODO: Generate order event
            
            except websockets.exceptions.ConnectionClosed:
                self._log.warning("WebSocket disconnected, reconnecting...")
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._log.error(f"Error in WebSocket loop: {e}")
                await asyncio.sleep(5)


class HyperliquidExecutionClient(LiveExecutionClient):
    """Hyperliquid execution client"""
    
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        client: HyperliquidHttpClient,
        msgbus: MessageBus,
        cache: Cache,
        clock: LiveClock,
        logger: Logger,
        account_id: AccountId,
    ):
        super().__init__(
            loop=loop,
            client_id=ClientId(f"{VENUE}-EXEC"),
            venue=VENUE,
            oms_type=OmsType.NETTING,
            account_type=AccountType.MARGIN,
            base_currency=USD,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            logger=logger,
        )
        
        self._client = client
        self._account_id = account_id
        self._order_id_map: Dict[ClientOrderId, int] = {}  # Nautilus -> Hyperliquid
    
    async def _connect(self):
        """Connect to Hyperliquid"""
        self._log.info("Connecting to Hyperliquid execution...")
        
        # Get account state
        await self._update_account()
        
        self._log.info("Connected to Hyperliquid execution", LogColor.GREEN)
    
    async def _disconnect(self):
        """Disconnect from Hyperliquid"""
        await self._client.close()
        self._log.info("Disconnected from Hyperliquid execution")
    
    async def _update_account(self):
        """Update account state"""
        state = await self._client.get_user_state()
        
        # Parse account balance
        margin_summary = state.get("marginSummary", {})
        account_value = float(margin_summary.get("accountValue", 0))
        
        # Create account balance
        balance = AccountBalance(
            total=Money(account_value, USD),
            locked=Money(0, USD),
            free=Money(account_value, USD),
        )
        
        # TODO: Generate account state event
        self._log.info(f"Account value: ${account_value:,.2f}")
    
    def submit_order(self, command: SubmitOrder):
        """Submit order"""
        self._loop.create_task(self._submit_order(command))
    
    async def _submit_order(self, command: SubmitOrder):
        """Submit order async"""
        try:
            order = command.order
            
            # Parse instrument
            coin = order.instrument_id.symbol.value.replace("-PERP", "")
            
            # Convert order
            is_buy = order.side == OrderSide.BUY
            sz = float(order.quantity)
            limit_px = float(order.price) if order.price else 0
            
            # Order type
            if order.order_type == OrderType.LIMIT:
                order_type = {"limit": {"tif": "Gtc"}}
            elif order.order_type == OrderType.MARKET:
                order_type = {"market": {}}
            else:
                self._log.error(f"Unsupported order type: {order.order_type}")
                return
            
            # Place order
            result = await self._client.place_order(
                coin=coin,
                is_buy=is_buy,
                sz=sz,
                limit_px=limit_px,
                order_type=order_type,
            )
            
            # Parse result
            if result.get("status") == "ok":
                response = result.get("response", {})
                data = response.get("data", {})
                statuses = data.get("statuses", [])
                
                if statuses and statuses[0].get("filled"):
                    # Order filled
                    filled = statuses[0]["filled"]
                    oid = filled.get("oid")
                    
                    if oid:
                        self._order_id_map[order.client_order_id] = oid
                    
                    self._log.info(f"Order filled: {order.client_order_id}")
                    # TODO: Generate fill event
            else:
                self._log.error(f"Order rejected: {result}")
        
        except Exception as e:
            self._log.error(f"Error submitting order: {e}")
    
    def cancel_order(self, command: CancelOrder):
        """Cancel order"""
        self._loop.create_task(self._cancel_order(command))
    
    async def _cancel_order(self, command: CancelOrder):
        """Cancel order async"""
        try:
            # Get Hyperliquid order ID
            oid = self._order_id_map.get(command.client_order_id)
            if not oid:
                self._log.error(f"Order ID not found: {command.client_order_id}")
                return
            
            # Parse instrument
            instrument = self._cache.instrument(command.instrument_id)
            if not instrument:
                self._log.error(f"Instrument not found: {command.instrument_id}")
                return
            
            coin = instrument.raw_symbol.value
            
            # Cancel order
            result = await self._client.cancel_order(coin=coin, oid=oid)
            
            if result.get("status") == "ok":
                self._log.info(f"Order cancelled: {command.client_order_id}")
                # TODO: Generate cancel event
            else:
                self._log.error(f"Cancel failed: {result}")
        
        except Exception as e:
            self._log.error(f"Error cancelling order: {e}")
