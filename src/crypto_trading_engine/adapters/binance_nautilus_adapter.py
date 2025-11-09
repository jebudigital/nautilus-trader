"""
Binance Adapter for Nautilus Trader

Proper Nautilus integration using DataClient and ExecutionClient.
"""

import asyncio
from decimal import Decimal
from typing import Optional

from nautilus_trader.adapters.binance.common.enums import BinanceAccountType
from nautilus_trader.adapters.binance.factories import get_cached_binance_http_client
from nautilus_trader.adapters.binance.factories import BinanceLiveDataClientFactory
from nautilus_trader.adapters.binance.factories import BinanceLiveExecClientFactory
from nautilus_trader.adapters.binance.config import BinanceDataClientConfig
from nautilus_trader.adapters.binance.config import BinanceExecClientConfig
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import MessageBus, Clock
from nautilus_trader.live.data_client import LiveDataClient
from nautilus_trader.live.execution_client import LiveExecutionClient


def create_binance_clients(
    api_key: str,
    api_secret: str,
    is_testnet: bool = True,
    account_type: BinanceAccountType = BinanceAccountType.SPOT,
    cache: Optional[Cache] = None,
    msgbus: Optional[MessageBus] = None,
    clock: Optional[Clock] = None
) -> tuple[LiveDataClient, LiveExecutionClient]:
    """
    Create Binance data and execution clients for Nautilus.
    
    Args:
        api_key: Binance API key
        api_secret: Binance API secret
        is_testnet: Whether to use testnet
        account_type: Account type (SPOT, MARGIN, FUTURES)
        cache: Nautilus cache
        msgbus: Nautilus message bus
        clock: Nautilus clock
        
    Returns:
        Tuple of (data_client, execution_client)
    """
    # Data client config
    data_config = BinanceDataClientConfig(
        api_key=api_key,
        api_secret=api_secret,
        account_type=account_type,
        testnet=is_testnet,
        base_url_http=None,  # Use default
        base_url_ws=None,  # Use default
    )
    
    # Execution client config
    exec_config = BinanceExecClientConfig(
        api_key=api_key,
        api_secret=api_secret,
        account_type=account_type,
        testnet=is_testnet,
        base_url_http=None,  # Use default
    )
    
    # Create clients using Nautilus factories
    data_client = BinanceLiveDataClientFactory.create(
        loop=asyncio.get_event_loop(),
        name="BINANCE",
        config=data_config,
        msgbus=msgbus,
        cache=cache,
        clock=clock,
    )
    
    exec_client = BinanceLiveExecClientFactory.create(
        loop=asyncio.get_event_loop(),
        name="BINANCE",
        config=exec_config,
        msgbus=msgbus,
        cache=cache,
        clock=clock,
    )
    
    return data_client, exec_client
