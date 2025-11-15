"""
0x Protocol Adapter for NautilusTrader (Arbitrum L2)

0x is a DEX aggregator that finds the best prices across multiple DEXs:
- Aggregates liquidity from Uniswap, SushiSwap, Curve, etc.
- Best execution prices
- Low gas costs on Arbitrum
- Simple API for swaps
"""

import asyncio
from decimal import Decimal
from typing import Optional, Dict, List
from datetime import datetime
import time

from web3 import Web3
from web3.middleware import geth_poa_middleware
import aiohttp

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, Logger
from nautilus_trader.common.enums import LogColor
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.execution.messages import SubmitOrder, CancelOrder
from nautilus_trader.live.data_client import LiveMarketDataClient
from nautilus_trader.live.execution_client import LiveExecutionClient
from nautilus_trader.model.currencies import USD, ETH
from nautilus_trader.model.enums import (
    AccountType,
    OmsType,
    OrderSide,
    OrderType,
)
from nautilus_trader.model.identifiers import (
    AccountId,
    ClientId,
    ClientOrderId,
    InstrumentId,
    Symbol,
    Venue,
)
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.objects import (
    AccountBalance,
    Currency,
    Money,
    Price,
    Quantity,
)
from nautilus_trader.msgbus.bus import MessageBus


VENUE = Venue("ZEROX")

# 0x API endpoints
ZEROX_API_ARBITRUM = "https://arbitrum.api.0x.org"

# Common token addresses (Arbitrum)
TOKENS_ARBITRUM = {
    "WETH": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
    "USDC": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",  # Native USDC
    "USDC.e": "0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8",  # Bridged USDC
    "USDT": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",
    "WBTC": "0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
    "ARB": "0x912CE59144191C1204E64559FE8253a0e49E6548",
}

# ERC20 ABI (minimal for approve and balanceOf)
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [
            {"name": "_owner", "type": "address"},
            {"name": "_spender", "type": "address"},
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function",
    },
]


class ZeroXHttpClient:
    """HTTP client for 0x Protocol on Arbitrum"""
    
    def __init__(
        self,
        rpc_url: str,
        private_key: str,
        wallet_address: str,
        api_key: Optional[str] = None,
        session: Optional[aiohttp.ClientSession] = None,
    ):
        self.rpc_url = rpc_url
        self.private_key = private_key
        self.wallet_address = wallet_address
        self.api_key = api_key
        self._session = session
        self._own_session = session is None
        
        # Create Web3 instance (Arbitrum)
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        
        # Create account
        self.account = self.w3.eth.account.from_key(private_key)
        
        # Verify chain ID (Arbitrum = 42161)
        self.chain_id = self.w3.eth.chain_id
        if self.chain_id != 42161:
            print(f"Warning: Expected Arbitrum (42161), got chain {self.chain_id}")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def get_quote(
        self,
        sell_token: str,
        buy_token: str,
        sell_amount: int,
        slippage_percentage: float = 0.01,
    ) -> Dict:
        """Get swap quote from 0x API"""
        session = await self._get_session()
        
        params = {
            "sellToken": sell_token,
            "buyToken": buy_token,
            "sellAmount": str(sell_amount),
            "slippagePercentage": str(slippage_percentage),
            "takerAddress": self.wallet_address,
        }
        
        headers = {}
        if self.api_key:
            headers["0x-api-key"] = self.api_key
        
        url = f"{ZEROX_API_ARBITRUM}/swap/v1/quote"
        
        async with session.get(url, params=params, headers=headers) as response:
            response.raise_for_status()
            return await response.json()
    
    async def get_price(self, sell_token: str, buy_token: str, sell_amount: int) -> Dict:
        """Get price without executing swap"""
        session = await self._get_session()
        
        params = {
            "sellToken": sell_token,
            "buyToken": buy_token,
            "sellAmount": str(sell_amount),
        }
        
        headers = {}
        if self.api_key:
            headers["0x-api-key"] = self.api_key
        
        url = f"{ZEROX_API_ARBITRUM}/swap/v1/price"
        
        async with session.get(url, params=params, headers=headers) as response:
            response.raise_for_status()
            return await response.json()
    
    def get_balance(self, token_address: str) -> float:
        """Get token balance"""
        if token_address.upper() == "ETH":
            # Native ETH balance
            balance_wei = self.w3.eth.get_balance(self.wallet_address)
            return float(self.w3.from_wei(balance_wei, 'ether'))
        else:
            # ERC20 token balance
            token_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=ERC20_ABI,
            )
            balance = token_contract.functions.balanceOf(self.wallet_address).call()
            decimals = token_contract.functions.decimals().call()
            return float(balance) / (10 ** decimals)
    
    async def approve_token(self, token_address: str, spender: str, amount: int) -> Optional[str]:
        """Approve token spending"""
        token_contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(token_address),
            abi=ERC20_ABI,
        )
        
        # Check current allowance
        allowance = token_contract.functions.allowance(
            self.wallet_address, spender
        ).call()
        
        if allowance >= amount:
            return None  # Already approved
        
        # Build approval transaction
        approve_txn = token_contract.functions.approve(
            spender, amount
        ).build_transaction({
            'from': self.wallet_address,
            'gas': 100000,
            'gasPrice': self.w3.eth.gas_price,
            'nonce': self.w3.eth.get_transaction_count(self.wallet_address),
            'chainId': self.chain_id,
        })
        
        # Sign and send
        signed_txn = self.w3.eth.account.sign_transaction(approve_txn, self.private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
        
        # Wait for confirmation
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        
        return receipt.transactionHash.hex()
    
    async def execute_swap(self, quote: Dict) -> str:
        """Execute swap using 0x quote"""
        # Build transaction from quote
        swap_txn = {
            'from': self.wallet_address,
            'to': quote['to'],
            'data': quote['data'],
            'value': int(quote['value']),
            'gas': int(quote['gas']),
            'gasPrice': int(quote['gasPrice']),
            'nonce': self.w3.eth.get_transaction_count(self.wallet_address),
            'chainId': self.chain_id,
        }
        
        # Sign transaction
        signed_txn = self.w3.eth.account.sign_transaction(swap_txn, self.private_key)
        
        # Send transaction
        tx_hash = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
        
        # Wait for confirmation
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        
        if receipt.status == 1:
            return receipt.transactionHash.hex()
        else:
            raise Exception(f"Swap failed: {receipt}")
    
    async def swap(
        self,
        sell_token: str,
        buy_token: str,
        sell_amount: int,
        slippage_percentage: float = 0.01,
    ) -> str:
        """Execute swap via 0x Protocol"""
        # Get quote
        quote = await self.get_quote(
            sell_token=sell_token,
            buy_token=buy_token,
            sell_amount=sell_amount,
            slippage_percentage=slippage_percentage,
        )
        
        # Approve token if needed (not needed for ETH)
        if sell_token.upper() != "ETH":
            allowance_target = quote.get('allowanceTarget')
            if allowance_target:
                await self.approve_token(sell_token, allowance_target, sell_amount)
        
        # Execute swap
        tx_hash = await self.execute_swap(quote)
        
        return tx_hash
    
    async def close(self):
        """Close session"""
        if self._own_session and self._session:
            await self._session.close()


class ZeroXDataClient(LiveMarketDataClient):
    """0x data client"""
    
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        client: ZeroXHttpClient,
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
        self._instruments: Dict[InstrumentId, CurrencyPair] = {}
        self._update_task: Optional[asyncio.Task] = None
    
    async def _connect(self):
        """Connect to 0x"""
        self._log.info("Connecting to 0x on Arbitrum...")
        
        # Load instruments
        await self._load_instruments()
        
        # Start update loop
        self._update_task = self._loop.create_task(self._update_loop())
        
        self._log.info("Connected to 0x", LogColor.GREEN)
    
    async def _disconnect(self):
        """Disconnect from 0x"""
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
        
        await self._client.close()
        self._log.info("Disconnected from 0x")
    
    async def _load_instruments(self):
        """Load instruments"""
        self._log.info("Loading instruments...")
        
        # Define common trading pairs on Arbitrum
        pairs = [
            ("WETH", "USDC", 18, 6),  # WETH/USDC
            ("WBTC", "USDC", 8, 6),   # WBTC/USDC
            ("WETH", "USDT", 18, 6),  # WETH/USDT
            ("ARB", "USDC", 18, 6),   # ARB/USDC
        ]
        
        for base, quote, base_decimals, quote_decimals in pairs:
            symbol_str = f"{base}{quote}"
            instrument_id = InstrumentId(Symbol(symbol_str), VENUE)
            
            instrument = CurrencyPair(
                instrument_id=instrument_id,
                raw_symbol=Symbol(symbol_str),
                base_currency=Currency.from_str(base),
                quote_currency=Currency.from_str(quote),
                price_precision=quote_decimals,
                size_precision=base_decimals,
                price_increment=Price.from_str(f"0.{'0' * (quote_decimals - 1)}1"),
                size_increment=Quantity.from_str(f"0.{'0' * (base_decimals - 1)}1"),
                max_quantity=Quantity.from_str("1000000"),
                min_quantity=Quantity.from_str(f"0.{'0' * (base_decimals - 1)}1"),
                max_price=Price.from_str("1000000"),
                min_price=Price.from_str(f"0.{'0' * (quote_decimals - 1)}1"),
                margin_init=Decimal("1.0"),  # No margin on DEX
                margin_maint=Decimal("1.0"),
                maker_fee=Decimal("0.0"),  # 0x has no protocol fee
                taker_fee=Decimal("0.0"),  # Gas is the only cost
                ts_event=self._clock.timestamp_ns(),
                ts_init=self._clock.timestamp_ns(),
            )
            
            self._instruments[instrument_id] = instrument
            self._cache.add_instrument(instrument)
        
        self._log.info(f"Loaded {len(self._instruments)} instruments")
    
    async def _update_loop(self):
        """Update loop for market data"""
        while True:
            try:
                await asyncio.sleep(5)
                # TODO: Update prices from 0x API
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._log.error(f"Error in update loop: {e}")


class ZeroXExecutionClient(LiveExecutionClient):
    """0x execution client"""
    
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        client: ZeroXHttpClient,
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
            account_type=AccountType.CASH,  # DEX is cash account
            base_currency=USD,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            logger=logger,
        )
        
        self._client = client
        self._account_id = account_id
    
    async def _connect(self):
        """Connect to 0x"""
        self._log.info("Connecting to 0x execution...")
        
        # Get account state
        await self._update_account()
        
        self._log.info("Connected to 0x execution", LogColor.GREEN)
    
    async def _disconnect(self):
        """Disconnect from 0x"""
        await self._client.close()
        self._log.info("Disconnected from 0x execution")
    
    async def _update_account(self):
        """Update account state"""
        # Get ETH balance
        eth_balance = self._client.get_balance("ETH")
        
        # Get USDC balance
        usdc_balance = self._client.get_balance(TOKENS_ARBITRUM["USDC"])
        
        self._log.info(f"ETH balance: {eth_balance:.4f}")
        self._log.info(f"USDC balance: {usdc_balance:.2f}")
    
    def submit_order(self, command: SubmitOrder):
        """Submit order"""
        self._loop.create_task(self._submit_order(command))
    
    async def _submit_order(self, command: SubmitOrder):
        """Submit order async"""
        try:
            order = command.order
            
            # Parse tokens from instrument
            symbol = order.instrument_id.symbol.value
            
            # Map symbol to tokens (e.g., "WETHUSDC" -> WETH, USDC)
            if symbol.startswith("WETH"):
                sell_token = TOKENS_ARBITRUM["WETH"]
                buy_token = TOKENS_ARBITRUM["USDC"]
            else:
                self._log.error(f"Unsupported symbol: {symbol}")
                return
            
            # Determine direction
            if order.side == OrderSide.BUY:
                # Buy base with quote (sell USDC, buy WETH)
                sell_token, buy_token = buy_token, sell_token
            
            # Calculate amount in wei
            sell_amount = int(float(order.quantity) * 1e18)  # Assuming 18 decimals
            
            # Execute swap
            self._log.info(f"Executing swap: {order.client_order_id}")
            tx_hash = await self._client.swap(
                sell_token=sell_token,
                buy_token=buy_token,
                sell_amount=sell_amount,
                slippage_percentage=0.01,  # 1% slippage
            )
            
            self._log.info(f"Swap executed: {tx_hash}")
            # TODO: Generate fill event
        
        except Exception as e:
            self._log.error(f"Error submitting order: {e}")
    
    def cancel_order(self, command: CancelOrder):
        """Cancel order (not applicable for DEX swaps)"""
        self._log.warning("Cannot cancel DEX swaps (atomic)")
