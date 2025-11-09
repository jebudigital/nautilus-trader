"""
dYdX v4 Nautilus Adapter

Proper Nautilus integration for dYdX v4 using DataClient and ExecutionClient patterns.
"""

import asyncio
import aiohttp
from decimal import Decimal
from typing import Optional, List, Dict, Any

from nautilus_trader.adapters.env import get_env_key
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.live.data_client import LiveDataClient
from nautilus_trader.live.execution_client import LiveExecutionClient
from nautilus_trader.model.data import QuoteTick, Bar, BarType
from nautilus_trader.model.enums import AccountType, OmsType, OrderSide, OrderType
from nautilus_trader.model.identifiers import ClientId, Venue, InstrumentId, AccountId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Price, Quantity, Money, Currency


class DydxV4DataClient(LiveDataClient):
    """
    dYdX v4 data client for Nautilus Trader.
    
    Provides market data using REST API (no SDK needed).
    """
    
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        client: aiohttp.ClientSession,
        msgbus: MessageBus,
        cache: Cache,
        clock: LiveClock,
        network: str = "testnet",
    ):
        """
        Initialize dYdX v4 data client.
        
        Args:
            loop: Event loop
            client: HTTP client session
            msgbus: Message bus
            cache: Cache
            clock: Clock
            network: Network ('testnet' or 'mainnet')
        """
        super().__init__(
            loop=loop,
            client_id=ClientId("DYDX_V4"),
            venue=Venue("DYDX_V4"),
            msgbus=msgbus,
            cache=cache,
            clock=clock,
        )
        
        self._client = client
        self.network = network
        
        # API endpoints
        if network == "testnet":
            self.api_base = "https://indexer.v4testnet.dydx.exchange"
        else:
            self.api_base = "https://indexer.dydx.trade"
        
        # Cache
        self._instruments: Dict[InstrumentId, Instrument] = {}
        self._quote_tasks: Dict[InstrumentId, asyncio.Task] = {}
    
    async def _connect(self):
        """Connect to dYdX v4 API."""
        self._log.info(f"Connecting to dYdX v4 ({self.network})...")
        
        # Load instruments
        await self._load_instruments()
        
        self._log.info(f"Connected to dYdX v4 with {len(self._instruments)} instruments")
    
    async def _disconnect(self):
        """Disconnect from dYdX v4 API."""
        # Cancel all quote tasks
        for task in self._quote_tasks.values():
            if not task.done():
                task.cancel()
        
        self._quote_tasks.clear()
        self._log.info("Disconnected from dYdX v4")
    
    async def _load_instruments(self):
        """Load available instruments from dYdX."""
        try:
            async with self._client.get(
                f"{self.api_base}/v4/perpetualMarkets",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    markets = data.get('markets', {})
                    
                    for market_name, market_data in markets.items():
                        if market_data.get('status') != 'ACTIVE':
                            continue
                        
                        # Create Nautilus instrument
                        # Note: This is simplified - full implementation would use proper Nautilus instrument types
                        instrument_id = InstrumentId.from_str(f"{market_name}.{self.venue}")
                        self._instruments[instrument_id] = market_data
                    
                    self._log.info(f"Loaded {len(self._instruments)} instruments")
                    
        except Exception as e:
            self._log.error(f"Failed to load instruments: {e}")
    
    async def _subscribe_quote_ticks(self, instrument_id: InstrumentId):
        """Subscribe to quote ticks for an instrument."""
        if instrument_id in self._quote_tasks:
            return  # Already subscribed
        
        # Start polling task for quotes
        task = self._loop.create_task(self._poll_quotes(instrument_id))
        self._quote_tasks[instrument_id] = task
        
        self._log.info(f"Subscribed to quotes for {instrument_id}")
    
    async def _unsubscribe_quote_ticks(self, instrument_id: InstrumentId):
        """Unsubscribe from quote ticks."""
        task = self._quote_tasks.pop(instrument_id, None)
        if task and not task.done():
            task.cancel()
        
        self._log.info(f"Unsubscribed from quotes for {instrument_id}")
    
    async def _poll_quotes(self, instrument_id: InstrumentId):
        """Poll for quote updates."""
        market = instrument_id.symbol.value
        
        while True:
            try:
                # Fetch orderbook
                async with self._client.get(
                    f"{self.api_base}/v4/orderbooks/perpetualMarket/{market}",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        bids = data.get('bids', [])
                        asks = data.get('asks', [])
                        
                        if bids and asks:
                            # Create quote tick
                            bid_price = Price.from_str(bids[0]['price'])
                            ask_price = Price.from_str(asks[0]['price'])
                            bid_size = Quantity.from_str(bids[0]['size'])
                            ask_size = Quantity.from_str(asks[0]['size'])
                            
                            quote = QuoteTick(
                                instrument_id=instrument_id,
                                bid_price=bid_price,
                                ask_price=ask_price,
                                bid_size=bid_size,
                                ask_size=ask_size,
                                ts_event=self._clock.timestamp_ns(),
                                ts_init=self._clock.timestamp_ns(),
                            )
                            
                            # Publish to message bus
                            self._handle_data(quote)
                
                # Poll every 1 second
                await asyncio.sleep(1)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._log.error(f"Error polling quotes for {market}: {e}")
                await asyncio.sleep(5)  # Back off on error
    
    async def get_funding_rate(self, market: str) -> Optional[Decimal]:
        """
        Get current funding rate for a market.
        
        Args:
            market: Market symbol (e.g., 'BTC-USD')
            
        Returns:
            Current funding rate or None
        """
        try:
            async with self._client.get(
                f"{self.api_base}/v4/historicalFunding/{market}",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    funding = data.get('historicalFunding', [])
                    
                    if funding:
                        return Decimal(str(funding[0]['rate']))
            
            return None
            
        except Exception as e:
            self._log.error(f"Error fetching funding rate for {market}: {e}")
            return None


class DydxV4ExecutionClient(LiveExecutionClient):
    """
    dYdX v4 execution client for Nautilus Trader.
    
    Handles order submission and position management.
    """
    
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        client: aiohttp.ClientSession,
        msgbus: MessageBus,
        cache: Cache,
        clock: LiveClock,
        network: str = "testnet",
        mnemonic: str = "",
    ):
        """
        Initialize dYdX v4 execution client.
        
        Args:
            loop: Event loop
            client: HTTP client session
            msgbus: Message bus
            cache: Cache
            clock: Clock
            network: Network ('testnet' or 'mainnet')
            mnemonic: Wallet mnemonic for signing
        """
        super().__init__(
            loop=loop,
            client_id=ClientId("DYDX_V4"),
            venue=Venue("DYDX_V4"),
            oms_type=OmsType.NETTING,
            account_type=AccountType.MARGIN,
            base_currency=Currency.from_str("USDC"),
            msgbus=msgbus,
            cache=cache,
            clock=clock,
        )
        
        self._client = client
        self.network = network
        self.mnemonic = mnemonic
        
        # API endpoints
        if network == "testnet":
            self.api_base = "https://indexer.v4testnet.dydx.exchange"
        else:
            self.api_base = "https://indexer.dydx.trade"
    
    async def _connect(self):
        """Connect to dYdX v4 for execution."""
        self._log.info(f"Connecting dYdX v4 execution client ({self.network})...")
        
        # TODO: Initialize signing keys from mnemonic
        # For now, this is read-only (paper trading)
        
        self._log.info("dYdX v4 execution client connected")
    
    async def _disconnect(self):
        """Disconnect from dYdX v4."""
        self._log.info("dYdX v4 execution client disconnected")
    
    async def _submit_order(self, order):
        """Submit an order to dYdX v4."""
        # TODO: Implement order submission with signing
        # For paper trading, this simulates the order
        self._log.info(f"Paper trading order: {order.side} {order.quantity} {order.instrument_id}")
        
        # Simulate immediate fill for paper trading
        # In live mode, would actually submit to dYdX
        pass


def create_dydx_v4_clients(
    loop: asyncio.AbstractEventLoop,
    msgbus: MessageBus,
    cache: Cache,
    clock: LiveClock,
    network: str = "testnet",
    mnemonic: str = "",
) -> tuple[DydxV4DataClient, DydxV4ExecutionClient]:
    """
    Create dYdX v4 data and execution clients.
    
    Args:
        loop: Event loop
        msgbus: Message bus
        cache: Cache
        clock: Clock
        network: Network ('testnet' or 'mainnet')
        mnemonic: Wallet mnemonic
        
    Returns:
        Tuple of (data_client, execution_client)
    """
    # Create shared HTTP client
    client = aiohttp.ClientSession()
    
    data_client = DydxV4DataClient(
        loop=loop,
        client=client,
        msgbus=msgbus,
        cache=cache,
        clock=clock,
        network=network,
    )
    
    exec_client = DydxV4ExecutionClient(
        loop=loop,
        client=client,
        msgbus=msgbus,
        cache=cache,
        clock=clock,
        network=network,
        mnemonic=mnemonic,
    )
    
    return data_client, exec_client
