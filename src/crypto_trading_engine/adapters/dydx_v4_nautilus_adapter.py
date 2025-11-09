"""
dYdX v4 Nautilus Adapter

Pure REST API implementation for dYdX v4 (no SDK required).
Handles order signing, submission, and market data.

Authentication:
- Market data: No auth required
- Account data: API key + HMAC signature
- Order submission: Wallet signature (Ethereum-style)
"""

import asyncio
import aiohttp
import hashlib
import hmac
import time
import json
import base64
from decimal import Decimal
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

# Ethereum wallet signing
from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3

from nautilus_trader.adapters.env import get_env_key
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.live.data_client import LiveDataClient, LiveMarketDataClient
from nautilus_trader.live.execution_client import LiveExecutionClient
from nautilus_trader.model.data import QuoteTick, Bar, BarType, FundingRateUpdate
from nautilus_trader.model.enums import AccountType, OmsType, OrderSide, OrderType, OrderStatus
from nautilus_trader.model.identifiers import ClientId, Venue, InstrumentId, AccountId, ClientOrderId, VenueOrderId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Price, Quantity, Money, Currency
from nautilus_trader.model.events import OrderFilled, OrderRejected, OrderAccepted
from nautilus_trader.core.datetime import dt_to_unix_nanos


class DydxV4DataClient(LiveMarketDataClient):
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
        # Create instrument provider
        from nautilus_trader.common.providers import InstrumentProvider
        instrument_provider = InstrumentProvider()
        
        super().__init__(
            loop=loop,
            client_id=ClientId("DYDX_V4"),
            venue=Venue("DYDX_V4"),
            instrument_provider=instrument_provider,
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
                        
                        # Create proper Nautilus CryptoPerpetual instrument
                        instrument = self._create_instrument(market_name, market_data)
                        if instrument:
                            self._instruments[instrument.id] = instrument
                            # Add to cache so strategy can access it
                            self._cache.add_instrument(instrument)
                    
                    self._log.info(f"Loaded {len(self._instruments)} instruments to cache")
                    
        except Exception as e:
            self._log.error(f"Failed to load instruments: {e}")
    
    def _create_instrument(self, market_name: str, market_data: Dict) -> Optional[Instrument]:
        """Create a Nautilus instrument from dYdX market data."""
        try:
            from nautilus_trader.model.instruments import CryptoPerpetual
            from nautilus_trader.model.objects import Price, Quantity
            from nautilus_trader.model.identifiers import Symbol
            
            instrument_id = InstrumentId.from_str(f"{market_name}.{self.venue}")
            
            # Parse market data
            step_size = Decimal(market_data.get('stepSize', '0.001'))
            tick_size = Decimal(market_data.get('tickSize', '1'))
            min_order_size = Decimal(market_data.get('minOrderSize', '0.001'))
            
            # Create Price and Quantity objects first to get their precision
            price_increment = Price.from_str(str(tick_size))
            size_increment = Quantity.from_str(str(step_size))
            min_quantity = Quantity.from_str(str(min_order_size))
            
            # Create instrument
            instrument = CryptoPerpetual(
                instrument_id=instrument_id,
                raw_symbol=Symbol(market_name),
                base_currency=Currency.from_str(market_name.split('-')[0]),
                quote_currency=Currency.from_str(market_name.split('-')[1]),
                settlement_currency=Currency.from_str("USD"),
                is_inverse=False,
                price_precision=price_increment.precision,
                size_precision=size_increment.precision,
                price_increment=price_increment,
                size_increment=size_increment,
                max_quantity=Quantity.from_str("1000000"),
                min_quantity=min_quantity,
                max_price=Price.from_str("1000000"),
                min_price=Price.from_str("0.01"),
                margin_init=Decimal("0.1"),  # 10x max leverage
                margin_maint=Decimal("0.05"),
                maker_fee=Decimal("0.0002"),  # 0.02%
                taker_fee=Decimal("0.0005"),  # 0.05%
                ts_event=self._clock.timestamp_ns(),
                ts_init=self._clock.timestamp_ns(),
            )
            
            return instrument
            
        except Exception as e:
            self._log.error(f"Failed to create instrument {market_name}: {e}")
            return None
    
    async def _subscribe_quote_ticks(self, instrument_id: InstrumentId):
        """Subscribe to quote ticks for an instrument."""
        if instrument_id in self._quote_tasks:
            return  # Already subscribed
        
        # Start polling task for quotes
        task = self._loop.create_task(self._poll_quotes(instrument_id))
        self._quote_tasks[instrument_id] = task
        
        self._log.info(f"Subscribed to quotes for {instrument_id}")
    
    async def _subscribe_funding_rates(self, instrument_id: InstrumentId):
        """Subscribe to funding rate updates for an instrument."""
        # Funding rates are polled as part of quote subscription
        # Ensure quote subscription is active
        await self._subscribe_quote_ticks(instrument_id)
        self._log.info(f"Subscribed to funding rates for {instrument_id}")
    
    async def _request_instrument(self, instrument_id: InstrumentId):
        """Request instrument details."""
        # Check if already loaded
        if instrument_id in self._instruments:
            self._log.info(f"Instrument {instrument_id} already loaded")
            return
        
        # Load specific instrument
        market_name = instrument_id.symbol.value
        
        try:
            async with self._client.get(
                f"{self.api_base}/v4/perpetualMarkets",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    markets = data.get('markets', {})
                    
                    if market_name in markets:
                        market_data = markets[market_name]
                        instrument = self._create_instrument(market_name, market_data)
                        
                        if instrument:
                            self._instruments[instrument.id] = instrument
                            self._cache.add_instrument(instrument)
                            self._log.info(f"✅ Loaded instrument {instrument_id}")
                    else:
                        self._log.error(f"Market {market_name} not found")
                        
        except Exception as e:
            self._log.error(f"Failed to request instrument {instrument_id}: {e}")
    
    async def _unsubscribe_quote_ticks(self, instrument_id: InstrumentId):
        """Unsubscribe from quote ticks."""
        task = self._quote_tasks.pop(instrument_id, None)
        if task and not task.done():
            task.cancel()
        
        self._log.info(f"Unsubscribed from quotes for {instrument_id}")
    
    async def _poll_quotes(self, instrument_id):
        """Poll for quote updates and funding rates."""
        # Handle both InstrumentId and subscription message
        if hasattr(instrument_id, 'instrument_id'):
            instrument_id = instrument_id.instrument_id
        
        market = instrument_id.symbol.value
        funding_check_counter = 0
        funding_fetched = False
        
        # Fetch funding rate immediately on startup
        self._log.info(f"Fetching initial funding rate for {market}...")
        try:
            funding_rate = await self.get_funding_rate(market)
            if funding_rate is not None:
                funding_update = FundingRateUpdate(
                    instrument_id=instrument_id,
                    rate=funding_rate,
                    ts_event=self._clock.timestamp_ns(),
                    ts_init=self._clock.timestamp_ns(),
                )
                self._handle_data(funding_update)
                funding_apy = funding_rate * Decimal('3') * Decimal('365') * Decimal('100')
                self._log.info(f"✅ Initial funding rate for {market}: {funding_rate:.6f} ({funding_apy:.2f}% APY)")
                funding_fetched = True
            else:
                self._log.warning(f"⚠️  Could not fetch initial funding rate for {market}")
        except Exception as e:
            self._log.error(f"Error fetching initial funding rate: {e}")
        
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
                
                # Fetch funding rate every 30 seconds (more frequent than before)
                funding_check_counter += 1
                if funding_check_counter >= 30:
                    funding_check_counter = 0
                    funding_rate = await self.get_funding_rate(market)
                    if funding_rate is not None:
                        # Create funding rate update
                        funding_update = FundingRateUpdate(
                            instrument_id=instrument_id,
                            rate=funding_rate,
                            ts_event=self._clock.timestamp_ns(),
                            ts_init=self._clock.timestamp_ns(),
                        )
                        self._handle_data(funding_update)
                        if not funding_fetched:
                            funding_apy = funding_rate * Decimal('3') * Decimal('365') * Decimal('100')
                            self._log.info(f"✅ Funding rate for {market}: {funding_rate:.6f} ({funding_apy:.2f}% APY)")
                            funding_fetched = True
                
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
    
    Handles order submission and position management using REST API.
    """
    
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        client: aiohttp.ClientSession,
        msgbus: MessageBus,
        cache: Cache,
        clock: LiveClock,
        network: str = "testnet",
        private_key: str = "",
        wallet_address: str = "",
        account_number: str = "0",
    ):
        """
        Initialize dYdX v4 execution client.
        
        dYdX V4 uses ONLY wallet-based authentication (no API keys!).
        
        Args:
            loop: Event loop
            client: HTTP client session
            msgbus: Message bus
            cache: Cache
            clock: Clock
            network: Network ('testnet' or 'mainnet')
            private_key: Ethereum private key (0x... format)
            wallet_address: Ethereum wallet address (optional, derived from private_key)
            account_number: dYdX subaccount number (default: 0)
        """
        # Create a simple instrument provider from cache
        from nautilus_trader.common.providers import InstrumentProvider
        instrument_provider = InstrumentProvider()
        
        super().__init__(
            loop=loop,
            client_id=ClientId("DYDX_V4"),
            venue=Venue("DYDX_V4"),
            oms_type=OmsType.NETTING,
            account_type=AccountType.MARGIN,
            base_currency=Currency.from_str("USD"),
            instrument_provider=instrument_provider,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
        )
        
        self._client = client
        self.network = network
        self.account_number = account_number
        
        # Wallet for signing (ONLY authentication method in V4!)
        self.private_key = private_key
        self.eth_wallet_address = None  # Ethereum address
        self.dydx_address = wallet_address  # dYdX Cosmos address (dydx...)
        self.wallet_account = None
        
        if private_key:
            try:
                # Create eth_account from private key
                if private_key.startswith('0x'):
                    private_key = private_key[2:]
                self.wallet_account = Account.from_key(private_key)
                self.eth_wallet_address = self.wallet_account.address
                
                # If dYdX address not provided, we need to derive it
                # For now, require it to be provided in config
                if not self.dydx_address:
                    self._log.error("❌ dYdX address (dydx...) must be provided in DYDX__WALLET_ADDRESS")
                    self._log.error(f"   Ethereum address: {self.eth_wallet_address}")
                else:
                    self._log.info(f"✅ Wallet initialized")
                    self._log.info(f"   Ethereum: {self.eth_wallet_address}")
                    self._log.info(f"   dYdX: {self.dydx_address}")
            except Exception as e:
                self._log.error(f"❌ Failed to initialize wallet: {e}")
        else:
            self._log.warning("⚠️  No private key provided - running in paper trading mode")
        
        # API endpoints
        if network == "testnet":
            self.api_base = "https://indexer.v4testnet.dydx.exchange"
            self.validator_endpoint = "https://dydx-testnet-api.polkachu.com"
        else:
            self.api_base = "https://indexer.dydx.trade"
            self.validator_endpoint = "https://dydx-ops-rest.kingnodes.com"
        
        # Order tracking
        self._pending_orders: Dict[ClientOrderId, Any] = {}
    
    async def _connect(self):
        """Connect to dYdX v4 for execution."""
        print("🔵 dYdX execution client _connect called")
        self._log.info(f"Connecting dYdX v4 execution client ({self.network})...")
        
        # Verify wallet (dYdX V4 uses wallet, not API keys!)
        if not self.wallet_account:
            print("⚠️  No wallet configured - running in paper trading mode")
            self._log.warning("No wallet configured - running in paper trading mode")
        else:
            print(f"🔵 Wallet configured: {self.dydx_address}")
            # Test connection by fetching account
            try:
                print("🔵 Fetching account...")
                account = await self._get_account()
                print(f"🔵 Account fetched: {account is not None}")
                if account:
                    self._log.info(f"✅ Connected to dYdX account: {self.dydx_address}")
                    equity = account.get('subaccounts', [{}])[0].get('equity', '0')
                    self._log.info(f"   Account equity: ${equity}")
                    print(f"✅ Account equity: ${equity}")
                    
                    # Generate account state so portfolio knows about this account
                    print("🔵 Calling _update_account_state...")
                    await self._update_account_state()
                    print("✅ _update_account_state completed")
                else:
                    print("⚠️  Account not found - creating dummy account state for testing")
                    self._log.warning("⚠️  Account not found - creating dummy account state")
                    # Create a dummy account state with zero balance so orders can be submitted
                    await self._create_dummy_account_state()
            except Exception as e:
                print(f"❌ Failed to connect: {e}")
                import traceback
                traceback.print_exc()
                self._log.error(f"Failed to connect: {e}")
        
        print("✅ dYdX v4 execution client connected")
        self._log.info("dYdX v4 execution client connected")
    
    async def _update_account_state(self):
        """Update account state and publish to message bus."""
        print("🔵 _update_account_state called")
        try:
            from nautilus_trader.model.objects import AccountBalance, MarginBalance
            
            print("🔵 Fetching account data...")
            account_data = await self._get_account()
            print(f"🔵 Account data: {account_data is not None}")
            if not account_data:
                print("⚠️  No account data returned")
                return
            
            subaccount = account_data.get('subaccounts', [{}])[0]
            equity = subaccount.get('equity', '0')
            
            # Create account balances
            balances = [
                AccountBalance(
                    total=Money(equity, Currency.from_str("USD")),
                    locked=Money(0, Currency.from_str("USD")),
                    free=Money(equity, Currency.from_str("USD")),
                )
            ]
            
            # Create margin balances (for margin account)
            margins = [
                MarginBalance(
                    initial=Money(0, Currency.from_str("USD")),
                    maintenance=Money(0, Currency.from_str("USD")),
                )
            ]
            
            # Create account ID
            account_id = AccountId(f"{self.venue}-{self.account_number}")
            
            # Generate account state using Nautilus method
            print(f"🔵 Generating account state for {account_id}...")
            
            # Use the internal method to send account state
            from nautilus_trader.model.events import AccountState
            account_state = AccountState(
                account_id=account_id,
                account_type=self.account_type,
                base_currency=self.base_currency,
                reported=True,
                balances=balances,
                margins=margins,
                info={},
                event_id=UUID4(),
                ts_event=self._clock.timestamp_ns(),
                ts_init=self._clock.timestamp_ns(),
            )
            
            # Send through message bus
            self._msgbus.send(endpoint="Portfolio.update_account", msg=account_state)
            
            self._log.info(f"Account state updated - ${equity}")
            print(f"✅ Account state published for {account_id} - ${equity}")
            
        except Exception as e:
            print(f"❌ Failed to update account state: {e}")
            import traceback
            traceback.print_exc()
            self._log.error(f"Failed to update account state: {e}")
    
    async def _create_dummy_account_state(self):
        """Create a dummy account state for testing when account doesn't exist."""
        try:
            from nautilus_trader.model.objects import AccountBalance, MarginBalance
            
            # Create account balances with zero balance
            balances = [
                AccountBalance(
                    total=Money(0, Currency.from_str("USD")),
                    locked=Money(0, Currency.from_str("USD")),
                    free=Money(0, Currency.from_str("USD")),
                )
            ]
            
            # Create margin balances
            margins = [
                MarginBalance(
                    initial=Money(0, Currency.from_str("USD")),
                    maintenance=Money(0, Currency.from_str("USD")),
                )
            ]
            
            # Create account ID
            account_id = AccountId(f"{self.venue}-{self.account_number}")
            
            # Generate dummy account state
            print(f"🔵 Generating dummy account state for {account_id}...")
            
            from nautilus_trader.model.events import AccountState
            account_state = AccountState(
                account_id=account_id,
                account_type=self.account_type,
                base_currency=self.base_currency,
                reported=True,
                balances=balances,
                margins=margins,
                info={},
                event_id=UUID4(),
                ts_event=self._clock.timestamp_ns(),
                ts_init=self._clock.timestamp_ns(),
            )
            
            # Send through message bus
            self._msgbus.send(endpoint="Portfolio.update_account", msg=account_state)
            
            self._log.info(f"Dummy account state created for {account_id}")
            print(f"✅ Dummy account state published for {account_id}")
            
        except Exception as e:
            print(f"❌ Failed to create dummy account state: {e}")
            import traceback
            traceback.print_exc()
            self._log.error(f"Failed to create dummy account state: {e}")
    
    async def _disconnect(self):
        """Disconnect from dYdX v4."""
        self._log.info("dYdX v4 execution client disconnected")
    
    def submit_order(self, command):
        """
        Submit an order (synchronous command handler).
        
        This is the method called by ExecutionEngine when routing SubmitOrder commands.
        We schedule the async _submit_order as a task.
        
        Args:
            command: SubmitOrder command containing the order
        """
        print(f"🔵 dYdX submit_order command handler called for {command.order.client_order_id}")
        self._log.info(f"submit_order command received for {command.order.client_order_id}")
        
        # Schedule the async submission
        task = self._loop.create_task(self._submit_order(command.order))
        
        # Add error handling
        def handle_task_result(t):
            try:
                t.result()
            except Exception as e:
                self._log.error(f"Order submission failed: {e}")
                import traceback
                traceback.print_exc()
        
        task.add_done_callback(handle_task_result)
    
    def _sign_order(self, order_params: Dict[str, Any]) -> str:
        """
        Sign an order using EIP-712 typed structured data.
        
        This is required for:
        - Placing orders
        - Canceling orders
        - Any state-changing operations
        
        dYdX V4 uses EIP-712 signatures to prove wallet ownership.
        
        Args:
            order_params: Order parameters dict
            
        Returns:
            Ethereum signature (hex string with 0x prefix)
        """
        if not self.wallet_account:
            raise ValueError("Wallet not initialized - cannot sign orders")
        
        # Create EIP-712 structured message
        structured_data = self._create_order_message(order_params)
        
        # Sign with EIP-712
        try:
            # Use eth_account's sign_typed_data for EIP-712
            from eth_account.messages import encode_structured_data
            
            signable_message = encode_structured_data(structured_data)
            signed_message = self.wallet_account.sign_message(signable_message)
            
            # Return signature as hex string
            return signed_message.signature.hex()
            
        except Exception as e:
            self._log.error(f"Failed to sign order: {e}")
            # Fallback to simple signing for testing
            self._log.warning("Using fallback signing method")
            simple_message = json.dumps(order_params, sort_keys=True)
            message_hash = encode_defunct(text=simple_message)
            signed_message = self.wallet_account.sign_message(message_hash)
            return signed_message.signature.hex()
    
    def _create_order_message(self, order_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create EIP-712 structured message for dYdX V4 order signing.
        
        dYdX V4 uses EIP-712 typed structured data signing.
        
        Args:
            order_params: Order parameters
            
        Returns:
            EIP-712 structured message dict
        """
        # EIP-712 domain for dYdX V4
        domain = {
            "name": "dYdX",
            "version": "1.0",
            "chainId": 5 if self.network == "testnet" else 1,  # Goerli testnet or mainnet
        }
        
        # Order message structure
        message = {
            "market": order_params.get("market", ""),
            "side": order_params.get("side", ""),
            "type": order_params.get("type", ""),
            "size": order_params.get("size", ""),
            "price": order_params.get("price", "0"),
            "clientId": order_params.get("clientId", ""),
            "timeInForce": order_params.get("timeInForce", "IOC"),
            "postOnly": order_params.get("postOnly", False),
            "reduceOnly": order_params.get("reduceOnly", False),
        }
        
        # EIP-712 structured data
        structured_data = {
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                ],
                "Order": [
                    {"name": "market", "type": "string"},
                    {"name": "side", "type": "string"},
                    {"name": "type", "type": "string"},
                    {"name": "size", "type": "string"},
                    {"name": "price", "type": "string"},
                    {"name": "clientId", "type": "string"},
                    {"name": "timeInForce", "type": "string"},
                    {"name": "postOnly", "type": "bool"},
                    {"name": "reduceOnly", "type": "bool"},
                ],
            },
            "primaryType": "Order",
            "domain": domain,
            "message": message,
        }
        
        return structured_data
    
    async def _get_account(self) -> Optional[Dict]:
        """
        Get account information using dYdX address.
        
        No authentication needed for public account queries in V4!
        """
        if not self.dydx_address:
            self._log.error("No dYdX address available")
            return None
        
        try:
            url = f"{self.api_base}/v4/addresses/{self.dydx_address}"
            print(f"🔵 Fetching account from: {url}")
            
            async with self._client.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                print(f"🔵 Response status: {response.status}")
                response_text = await response.text()
                print(f"🔵 Response: {response_text[:200]}")
                
                if response.status == 200:
                    data = await response.json()
                    return data
                else:
                    self._log.error(f"Failed to get account: {response.status} - {response_text}")
                    return None
                    
        except Exception as e:
            print(f"❌ Error getting account: {e}")
            import traceback
            traceback.print_exc()
            self._log.error(f"Error getting account: {e}")
            return None
    
    async def _submit_order(self, order):
        """
        Submit an order to dYdX v4 with wallet signature.
        
        Flow:
        1. Prepare order parameters
        2. Sign order with wallet (Ethereum signature)
        3. Submit to dYdX validator via REST
        4. Monitor order status
        """
        print(f"🔵 dYdX _submit_order called: {order.side} {order.quantity} {order.instrument_id}")
        self._log.info(f"Order submission: {order.side} {order.quantity} {order.instrument_id}")
        
        # Extract market from instrument
        market = order.instrument_id.symbol.value
        
        # Prepare order parameters
        order_params = {
            "market": market,
            "side": "BUY" if order.side == OrderSide.BUY else "SELL",
            "type": "MARKET" if order.order_type == OrderType.MARKET else "LIMIT",
            "size": str(float(order.quantity)),
            "clientId": str(order.client_order_id),
            "timeInForce": "IOC",  # Immediate or Cancel for market orders
            "postOnly": False,
            "reduceOnly": order.reduce_only if hasattr(order, 'reduce_only') else False,
        }
        
        if order.order_type == OrderType.LIMIT and hasattr(order, 'price'):
            order_params["price"] = str(float(order.price))
            order_params["timeInForce"] = "GTC"  # Good til Cancel for limit orders
        
        # Store pending order
        self._pending_orders[order.client_order_id] = order
        
        # Check if we have wallet for signing
        if not self.wallet_account:
            self._log.warning("No wallet configured - running in paper trading mode")
            
            # Generate accepted event
            self._generate_order_accepted(order)
            
            # Simulate fill after 1 second
            await asyncio.sleep(1)
            self._generate_order_filled(order)
            return
        
        try:
            # Sign the order with wallet
            self._log.info(f"Signing order with wallet {self.dydx_address}")
            signature = self._sign_order(order_params)
            
            # Prepare request
            timestamp = str(int(time.time() * 1000))
            request_path = "/v4/orders"
            body = json.dumps(order_params)
            
            # Create headers with wallet signature ONLY
            # dYdX V4 doesn't use API keys!
            headers = {
                "Content-Type": "application/json",
                "DYDX-SIGNATURE": signature,  # Wallet signature
                "DYDX-TIMESTAMP": timestamp,
                "DYDX-WALLET-ADDRESS": self.dydx_address,
            }
            
            # Submit order
            url = f"{self.validator_endpoint}{request_path}"
            self._log.info(f"Submitting order to {url}")
            
            async with self._client.post(
                url,
                json=order_params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                response_text = await response.text()
                
                if response.status in [200, 201]:
                    data = json.loads(response_text)
                    self._log.info(f"Order accepted: {data}")
                    
                    # Generate accepted event
                    venue_order_id = data.get('order', {}).get('id', f"DYDX-{timestamp}")
                    self._generate_order_accepted(order, venue_order_id)
                    
                    # Start monitoring order status
                    self._loop.create_task(self._monitor_order(order, venue_order_id))
                    
                else:
                    error_msg = f"Order rejected: {response.status} - {response_text}"
                    self._log.error(error_msg)
                    self._generate_order_rejected(order, error_msg)
                    
        except Exception as e:
            error_msg = f"Order submission failed: {str(e)}"
            self._log.error(error_msg)
            self._generate_order_rejected(order, error_msg)
    
    async def _monitor_order(self, order, venue_order_id: str):
        """Monitor order status until filled or canceled."""
        max_attempts = 30  # 30 seconds max
        attempt = 0
        
        while attempt < max_attempts:
            try:
                # Query order status
                url = f"{self.api_base}/v4/orders/{venue_order_id}"
                
                async with self._client.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        data = await response.json()
                        order_data = data.get('order', {})
                        status = order_data.get('status', '')
                        
                        if status == 'FILLED':
                            # Generate fill event
                            self._generate_order_filled_from_data(order, order_data, venue_order_id)
                            return
                        elif status in ['CANCELED', 'REJECTED']:
                            # Generate rejection
                            self._generate_order_rejected(order, f"Order {status.lower()}")
                            return
                
                await asyncio.sleep(1)
                attempt += 1
                
            except Exception as e:
                self._log.error(f"Error monitoring order: {e}")
                await asyncio.sleep(1)
                attempt += 1
        
        # Timeout
        self._log.warning(f"Order monitoring timeout for {venue_order_id}")
    
    def _generate_order_filled_from_data(self, order, order_data: Dict, venue_order_id: str):
        """Generate order filled event from dYdX order data."""
        from nautilus_trader.core.uuid import UUID4
        
        fill_price = Price.from_str(order_data.get('price', '0'))
        fill_qty = Quantity.from_str(order_data.get('size', '0'))
        
        # Calculate commission (dYdX charges 0.05% taker fee)
        notional = float(fill_price) * float(fill_qty)
        commission = Money(notional * 0.0005, Currency.from_str("USD"))
        
        event = OrderFilled(
            trader_id=order.trader_id,
            strategy_id=order.strategy_id,
            instrument_id=order.instrument_id,
            client_order_id=order.client_order_id,
            venue_order_id=VenueOrderId(venue_order_id),
            account_id=AccountId(f"{self.venue}-{self.account_number}"),
            trade_id=UUID4(),
            order_side=order.side,
            order_type=order.order_type,
            last_qty=fill_qty,
            last_px=fill_price,
            currency=Currency.from_str("USD"),
            commission=commission,
            liquidity_side=None,
            event_id=UUID4(),
            ts_event=self._clock.timestamp_ns(),
            ts_init=self._clock.timestamp_ns(),
        )
        
        self._send_order_event(event)
    
    def _generate_order_accepted(self, order, venue_order_id: str = None):
        """Generate order accepted event."""
        from nautilus_trader.core.uuid import UUID4
        
        if not venue_order_id:
            venue_order_id = f"DYDX-{int(time.time() * 1000)}"
        
        event = OrderAccepted(
            trader_id=order.trader_id,
            strategy_id=order.strategy_id,
            instrument_id=order.instrument_id,
            client_order_id=order.client_order_id,
            venue_order_id=VenueOrderId(venue_order_id),
            account_id=AccountId(f"{self.venue}-{self.account_number}"),
            event_id=UUID4(),
            ts_event=self._clock.timestamp_ns(),
            ts_init=self._clock.timestamp_ns(),
        )
        
        self._send_order_event(event)
    
    def _generate_order_filled(self, order):
        """Generate order filled event (for paper trading)."""
        from nautilus_trader.core.uuid import UUID4
        
        # Get current market price (simplified)
        fill_price = Price.from_str("100000.0")  # Would fetch from market data
        
        event = OrderFilled(
            trader_id=order.trader_id,
            strategy_id=order.strategy_id,
            instrument_id=order.instrument_id,
            client_order_id=order.client_order_id,
            venue_order_id=VenueOrderId(f"DYDX-{int(time.time() * 1000)}"),
            account_id=AccountId(f"{self.venue}-{self.account_number}"),
            trade_id=UUID4(),
            order_side=order.side,
            order_type=order.order_type,
            last_qty=order.quantity,
            last_px=fill_price,
            currency=Currency.from_str("USD"),
            commission=Money(2.50, Currency.from_str("USD")),
            liquidity_side=None,
            event_id=UUID4(),
            ts_event=self._clock.timestamp_ns(),
            ts_init=self._clock.timestamp_ns(),
        )
        
        self._send_order_event(event)
    
    def _generate_order_rejected(self, order, reason: str):
        """Generate order rejected event."""
        from nautilus_trader.core.uuid import UUID4
        
        event = OrderRejected(
            trader_id=order.trader_id,
            strategy_id=order.strategy_id,
            instrument_id=order.instrument_id,
            client_order_id=order.client_order_id,
            account_id=AccountId(f"{self.venue}-{self.account_number}"),
            reason=reason,
            event_id=UUID4(),
            ts_event=self._clock.timestamp_ns(),
            ts_init=self._clock.timestamp_ns(),
        )
        
        self._send_order_event(event)


    async def _subscribe_funding_rates(self, instrument_id: InstrumentId):
        """Subscribe to funding rate updates."""
        if instrument_id in self._quote_tasks:
            return  # Already subscribed
        
        # Start polling task for funding rates
        task = self._loop.create_task(self._poll_funding_rates(instrument_id))
        self._quote_tasks[instrument_id] = task
        
        self._log.info(f"Subscribed to funding rates for {instrument_id}")
    
    async def _poll_funding_rates(self, instrument_id: InstrumentId):
        """Poll for funding rate updates."""
        market = instrument_id.symbol.value
        
        while True:
            try:
                funding_rate = await self.get_funding_rate(market)
                
                if funding_rate is not None:
                    # Create FundingRateUpdate
                    update = FundingRateUpdate(
                        instrument_id=instrument_id,
                        rate=funding_rate,
                        ts_event=self._clock.timestamp_ns(),
                        ts_init=self._clock.timestamp_ns(),
                    )
                    
                    # Publish to message bus
                    self._handle_data(update)
                
                # Poll every hour (funding updates every 8 hours)
                await asyncio.sleep(3600)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._log.error(f"Error polling funding rates for {market}: {e}")
                await asyncio.sleep(300)  # Back off on error


def create_dydx_v4_clients(
    loop: asyncio.AbstractEventLoop,
    msgbus: MessageBus,
    cache: Cache,
    clock: LiveClock,
    network: str = "testnet",
    private_key: str = "",
    wallet_address: str = "",
    account_number: str = "0",
) -> tuple[DydxV4DataClient, DydxV4ExecutionClient]:
    """
    Create dYdX v4 data and execution clients.
    
    dYdX V4 uses ONLY wallet-based authentication.
    No API keys, secrets, or passphrases needed!
    
    Args:
        loop: Event loop
        msgbus: Message bus
        cache: Cache
        clock: Clock
        network: Network ('testnet' or 'mainnet')
        private_key: Ethereum private key (0x... format)
        wallet_address: Ethereum wallet address (optional, derived from key)
        account_number: Subaccount number (default: 0)
        
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
        private_key=private_key,
        wallet_address=wallet_address,
        account_number=account_number,
    )
    
    return data_client, exec_client
