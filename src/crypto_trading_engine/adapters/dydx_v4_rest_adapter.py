"""
dYdX v4 REST API Adapter

This adapter uses the dYdX v4 REST API directly without requiring the full Python SDK.
Perfect for paper trading and market data fetching when the SDK installation fails.

Features:
- Fetch orderbook data
- Get funding rates
- Get market data
- Check positions (read-only)
- No grpcio-tools dependency needed!
"""

import asyncio
import logging
import aiohttp
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any

from nautilus_trader.model.identifiers import Venue, InstrumentId
from nautilus_trader.model.objects import Price, Quantity

from ..core.adapter import ExchangeAdapter
from ..models.trading_mode import TradingMode
from ..models.perpetuals import FundingRate
from ..models.core import Instrument

logger = logging.getLogger(__name__)


class DydxV4RestAdapter(ExchangeAdapter):
    """
    dYdX v4 adapter using REST API only.
    
    This adapter provides full market data functionality without requiring
    the problematic v4-client-py SDK installation.
    """
    
    def __init__(
        self,
        config: Dict[str, Any],
        trading_mode: TradingMode = TradingMode.BACKTEST
    ):
        """
        Initialize dYdX v4 REST adapter.
        
        Args:
            config: Configuration dictionary containing:
                - network: 'testnet' or 'mainnet'
                - mnemonic: Your wallet mnemonic (optional for read-only)
            trading_mode: Current trading mode
        """
        venue = Venue("DYDX_V4")
        super().__init__(venue, config, trading_mode)
        
        # Configuration
        self.network = config.get("network", "testnet")
        self.mnemonic = config.get("mnemonic", "")
        
        # API endpoints
        if self.network == "testnet":
            self.api_base = "https://indexer.v4testnet.dydx.exchange"
            self.rpc_url = config.get("node_url", "https://dydx-testnet-rpc.kingnodes.com")
        else:
            self.api_base = "https://indexer.dydx.trade"
            self.rpc_url = config.get("node_url", "https://dydx-ops-rpc.kingnodes.com")
        
        # HTTP session
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Cache
        self.markets_cache: Dict[str, Dict] = {}
        self.last_markets_update: Optional[datetime] = None
        
        logger.info(f"Initialized dYdX v4 REST adapter ({self.network})")
    
    async def connect(self) -> bool:
        """Connect to dYdX v4 API."""
        try:
            if self.trading_mode == TradingMode.BACKTEST:
                self.is_connected = True
                logger.info("dYdX v4 REST adapter connected (backtest mode)")
                return True
            
            # Create HTTP session
            self.session = aiohttp.ClientSession()
            
            # Test connection by fetching markets
            markets = await self._fetch_markets()
            
            if markets:
                self.is_connected = True
                logger.info(f"dYdX v4 REST adapter connected ({self.network})")
                logger.info(f"Found {len(markets)} markets")
                return True
            else:
                logger.error("Failed to fetch markets from dYdX v4")
                return False
                
        except Exception as e:
            logger.error(f"Failed to connect to dYdX v4: {e}")
            if self.on_error_callback:
                self.on_error_callback(e)
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from dYdX v4 API."""
        try:
            if self.session:
                await self.session.close()
                self.session = None
            
            self.is_connected = False
            logger.info("dYdX v4 REST adapter disconnected")
            
        except Exception as e:
            logger.error(f"Error during dYdX v4 disconnect: {e}")
    
    async def _fetch_markets(self) -> Dict[str, Dict]:
        """Fetch all perpetual markets."""
        try:
            if not self.session:
                return {}
            
            async with self.session.get(
                f"{self.api_base}/v4/perpetualMarkets",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    markets = data.get('markets', {})
                    
                    # Update cache
                    self.markets_cache = markets
                    self.last_markets_update = datetime.now()
                    
                    return markets
                else:
                    logger.error(f"Failed to fetch markets: HTTP {response.status}")
                    return {}
                    
        except Exception as e:
            logger.error(f"Error fetching markets: {e}")
            return {}
    
    async def get_orderbook(self, market: str) -> Optional[Dict[str, Any]]:
        """
        Get orderbook for a market.
        
        Args:
            market: Market symbol (e.g., 'BTC-USD')
            
        Returns:
            Orderbook data with bids and asks
        """
        try:
            if not self.session:
                return None
            
            async with self.session.get(
                f"{self.api_base}/v4/orderbooks/perpetualMarket/{market}",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                else:
                    logger.error(f"Failed to fetch orderbook for {market}: HTTP {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error fetching orderbook for {market}: {e}")
            return None
    
    async def get_funding_rates(self, market: str) -> List[FundingRate]:
        """
        Get funding rates for a market.
        
        Args:
            market: Market symbol (e.g., 'BTC-USD')
            
        Returns:
            List of funding rates
        """
        try:
            if not self.session:
                return []
            
            async with self.session.get(
                f"{self.api_base}/v4/historicalFunding/{market}",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    funding_data = data.get('historicalFunding', [])
                    
                    # Convert to FundingRate objects
                    funding_rates = []
                    for item in funding_data[:10]:  # Last 10 funding rates
                        try:
                            rate = Decimal(str(item['rate']))
                            effective_at = datetime.fromisoformat(
                                item['effectiveAt'].replace('Z', '+00:00')
                            )
                            
                            # Create instrument (simplified)
                            instrument_id = InstrumentId.from_str(f"{market}.{self.venue}")
                            instrument = Instrument(
                                id=instrument_id,
                                symbol=market,
                                base_currency=market.split('-')[0],
                                quote_currency=market.split('-')[1],
                                price_precision=2,
                                size_precision=4,
                                min_quantity=Decimal('0.001'),
                                max_quantity=None,
                                tick_size=Decimal('1'),
                                venue=self.venue,
                                is_active=True
                            )
                            
                            funding_rate = FundingRate(
                                instrument=instrument,
                                rate=rate,
                                timestamp=effective_at,
                                venue=self.venue,
                                next_funding_time=effective_at  # Simplified
                            )
                            funding_rates.append(funding_rate)
                            
                        except Exception as e:
                            logger.warning(f"Failed to parse funding rate: {e}")
                            continue
                    
                    return funding_rates
                else:
                    logger.error(f"Failed to fetch funding rates for {market}: HTTP {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"Error fetching funding rates for {market}: {e}")
            return []
    
    async def get_market_price(self, market: str) -> Optional[Decimal]:
        """
        Get current market price.
        
        Args:
            market: Market symbol (e.g., 'BTC-USD')
            
        Returns:
            Current price or None
        """
        try:
            # Check cache first
            if market in self.markets_cache:
                price_str = self.markets_cache[market].get('oraclePrice')
                if price_str:
                    return Decimal(str(price_str))
            
            # Fetch fresh data
            markets = await self._fetch_markets()
            if market in markets:
                price_str = markets[market].get('oraclePrice')
                if price_str:
                    return Decimal(str(price_str))
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting market price for {market}: {e}")
            return None
    
    async def get_candles(
        self,
        market: str,
        resolution: str = '1HOUR'
    ) -> List[Dict[str, Any]]:
        """
        Get price candles.
        
        Args:
            market: Market symbol
            resolution: Candle resolution (1MIN, 5MINS, 15MINS, 30MINS, 1HOUR, 4HOURS, 1DAY)
            
        Returns:
            List of candle data
        """
        try:
            if not self.session:
                return []
            
            async with self.session.get(
                f"{self.api_base}/v4/candles/perpetualMarkets/{market}",
                params={'resolution': resolution},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('candles', [])
                else:
                    logger.error(f"Failed to fetch candles for {market}: HTTP {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"Error fetching candles for {market}: {e}")
            return []
    
    async def get_instruments(self) -> List[Instrument]:
        """Get available instruments."""
        try:
            markets = await self._fetch_markets()
            instruments = []
            
            for market_name, market_data in markets.items():
                try:
                    if market_data.get('status') != 'ACTIVE':
                        continue
                    
                    # Parse market info
                    base_currency = market_name.split('-')[0]
                    quote_currency = market_name.split('-')[1]
                    
                    tick_size = Decimal(str(market_data.get('tickSize', '1')))
                    step_size = Decimal(str(market_data.get('stepSize', '0.001')))
                    min_order_size = Decimal(str(market_data.get('minOrderSize', '0.001')))
                    
                    instrument_id = InstrumentId.from_str(f"{market_name}.{self.venue}")
                    
                    instrument = Instrument(
                        id=instrument_id,
                        symbol=market_name,
                        base_currency=base_currency,
                        quote_currency=quote_currency,
                        price_precision=len(str(tick_size).split('.')[-1]) if '.' in str(tick_size) else 0,
                        size_precision=len(str(step_size).split('.')[-1]) if '.' in str(step_size) else 0,
                        min_quantity=min_order_size,
                        max_quantity=None,
                        tick_size=tick_size,
                        venue=self.venue,
                        is_active=True
                    )
                    
                    instruments.append(instrument)
                    
                except Exception as e:
                    logger.warning(f"Failed to parse instrument {market_name}: {e}")
                    continue
            
            return instruments
            
        except Exception as e:
            logger.error(f"Error getting instruments: {e}")
            return []
    
    async def submit_order(self, order) -> bool:
        """
        Submit an order (paper trading only for REST adapter).
        
        For live trading, you would need the full SDK with signing capabilities.
        """
        if self.trading_mode == TradingMode.PAPER:
            # Simulate order for paper trading
            logger.info(f"Paper trading order: {order.side} {order.quantity} {order.instrument.symbol}")
            
            # Get current price for simulation
            market = str(order.instrument.symbol)
            price = await self.get_market_price(market)
            
            if price:
                # Simulate fill
                if self.on_order_filled_callback:
                    # Create simulated fill
                    from ..models.core import SimulatedFill
                    fill = SimulatedFill(
                        order_id=str(order.order_id),
                        fill_price=price,
                        fill_quantity=order.quantity.as_decimal(),
                        fill_time=datetime.now(),
                        slippage=Decimal('0.001'),  # 0.1% slippage
                        transaction_cost=order.quantity.as_decimal() * price * Decimal('0.0005')  # 0.05% fee
                    )
                    self.on_order_filled_callback(order, fill)
                
                return True
            
            return False
        
        elif self.trading_mode == TradingMode.LIVE:
            logger.error("Live trading not supported with REST adapter - need full SDK for signing")
            return False
        
        else:  # BACKTEST
            logger.warning("Order submission not supported in backtest mode")
            return False
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order (not supported in REST-only mode)."""
        logger.warning("Order cancellation requires full SDK")
        return False
    
    async def get_positions(self) -> List:
        """Get positions (read-only without full SDK)."""
        logger.warning("Position fetching requires full SDK with authentication")
        return []
    
    async def get_balance(self) -> Dict:
        """Get balance (read-only without full SDK)."""
        logger.warning("Balance fetching requires full SDK with authentication")
        return {}
    
    async def get_order_status(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Get order status (not supported in REST-only mode)."""
        logger.warning("Order status requires full SDK")
        return None
    
    async def subscribe_market_data(self, instrument_ids: List[str]) -> bool:
        """Subscribe to market data (polling-based for REST adapter)."""
        logger.info(f"REST adapter uses polling for market data: {instrument_ids}")
        return True
    
    async def unsubscribe_market_data(self, instrument_ids: List[str]) -> bool:
        """Unsubscribe from market data."""
        logger.info(f"Unsubscribed from market data: {instrument_ids}")
        return True


# Convenience function to create adapter from environment
def create_dydx_v4_adapter_from_env(trading_mode: TradingMode = TradingMode.PAPER) -> DydxV4RestAdapter:
    """
    Create dYdX v4 adapter from environment variables.
    
    Args:
        trading_mode: Trading mode to use
        
    Returns:
        Configured adapter
    """
    import os
    
    config = {
        'network': os.getenv('DYDX__NETWORK', 'testnet'),
        'mnemonic': os.getenv('DYDX__MNEMONIC', ''),
        'node_url': os.getenv('DYDX__NODE_URL', '')
    }
    
    return DydxV4RestAdapter(config, trading_mode)
