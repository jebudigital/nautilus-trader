"""
Test that both Binance and dYdX execution clients receive orders properly.
"""

import asyncio
import os
from pathlib import Path
import sys

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.cache.cache import Cache
from nautilus_trader.model.identifiers import TraderId, InstrumentId, ClientOrderId, StrategyId
from nautilus_trader.portfolio.portfolio import Portfolio
from nautilus_trader.execution.engine import ExecutionEngine
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.objects import Quantity
from nautilus_trader.model.orders import MarketOrder
from nautilus_trader.core.uuid import UUID4

from nautilus_trader.adapters.binance.factories import BinanceLiveExecClientFactory
from nautilus_trader.adapters.binance.config import BinanceExecClientConfig

from src.crypto_trading_engine.adapters.dydx_v4_nautilus_adapter import create_dydx_v4_clients

load_dotenv()


async def test_dual_routing():
    """Test that both Binance and dYdX receive orders."""
    
    print("\n🧪 Testing Dual Exchange Order Routing")
    print("="*60)
    
    # Create components
    loop = asyncio.get_event_loop()
    clock = LiveClock()
    trader_id = TraderId("TEST-001")
    msgbus = MessageBus(trader_id=trader_id, clock=clock)
    cache = Cache(database=None)
    portfolio = Portfolio(msgbus=msgbus, cache=cache, clock=clock)
    exec_engine = ExecutionEngine(msgbus=msgbus, cache=cache, clock=clock)
    
    # Create Binance client
    print("\n1. Creating Binance execution client...")
    binance_exec_config = BinanceExecClientConfig(
        api_key=os.getenv('BINANCE__API_KEY', ''),
        api_secret=os.getenv('BINANCE__API_SECRET', ''),
        testnet=True,
    )
    
    binance_exec_client = BinanceLiveExecClientFactory.create(
        loop=loop,
        name="BINANCE",
        msgbus=msgbus,
        cache=cache,
        clock=clock,
        config=binance_exec_config,
    )
    
    # Create dYdX client
    print("2. Creating dYdX execution client...")
    _, dydx_exec_client = create_dydx_v4_clients(
        loop=loop,
        msgbus=msgbus,
        cache=cache,
        clock=clock,
        network=os.getenv('DYDX__NETWORK', 'mainnet'),
        private_key=os.getenv('DYDX__PRIVATE_KEY', ''),
        wallet_address=os.getenv('DYDX__WALLET_ADDRESS', ''),
        account_number=os.getenv('DYDX__ACCOUNT_NUMBER', '0'),
    )
    
    # Register clients
    print("3. Registering execution clients...")
    exec_engine.register_client(binance_exec_client)
    exec_engine.register_client(dydx_exec_client)
    print(f"   ✅ Registered {len(list(exec_engine.registered_clients))} clients")
    
    # Connect
    print("4. Connecting clients...")
    await binance_exec_client._connect()
    await dydx_exec_client._connect()
    
    # Start execution engine
    print("5. Starting execution engine...")
    exec_engine.start()
    
    # Wait for instruments
    await asyncio.sleep(2)
    
    # Test Binance order
    print("\n6. Testing Binance order routing...")
    binance_instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
    binance_instrument = cache.instrument(binance_instrument_id)
    
    if binance_instrument:
        print(f"   ✅ Binance instrument loaded: {binance_instrument.id}")
        
        strategy_id = StrategyId("TEST-STRATEGY-001")
        binance_order = MarketOrder(
            trader_id=trader_id,
            strategy_id=strategy_id,
            instrument_id=binance_instrument_id,
            client_order_id=ClientOrderId("TEST-BIN-001"),
            order_side=OrderSide.BUY,
            quantity=Quantity.from_str("0.001"),
            time_in_force=TimeInForce.GTC,
            init_id=UUID4(),
            ts_init=clock.timestamp_ns(),
        )
        
        from nautilus_trader.execution.messages import SubmitOrder
        command = SubmitOrder(
            trader_id=trader_id,
            strategy_id=strategy_id,
            order=binance_order,
            command_id=UUID4(),
            ts_init=clock.timestamp_ns(),
        )
        
        print(f"   📤 Submitting Binance order...")
        exec_engine.execute(command)
    else:
        print(f"   ⚠️  Binance instrument not found")
    
    # Test dYdX order
    print("\n7. Testing dYdX order routing...")
    dydx_instrument_id = InstrumentId.from_str("BTC-USD.DYDX_V4")
    dydx_instrument = cache.instrument(dydx_instrument_id)
    
    if dydx_instrument:
        print(f"   ✅ dYdX instrument loaded: {dydx_instrument.id}")
        
        dydx_order = MarketOrder(
            trader_id=trader_id,
            strategy_id=strategy_id,
            instrument_id=dydx_instrument_id,
            client_order_id=ClientOrderId("TEST-DYDX-001"),
            order_side=OrderSide.SELL,
            quantity=Quantity.from_str("0.001"),
            time_in_force=TimeInForce.GTC,
            init_id=UUID4(),
            ts_init=clock.timestamp_ns(),
        )
        
        from nautilus_trader.execution.messages import SubmitOrder
        command = SubmitOrder(
            trader_id=trader_id,
            strategy_id=strategy_id,
            order=dydx_order,
            command_id=UUID4(),
            ts_init=clock.timestamp_ns(),
        )
        
        print(f"   📤 Submitting dYdX order...")
        exec_engine.execute(command)
    else:
        print(f"   ⚠️  dYdX instrument not found")
    
    print("\n8. Waiting for order processing...")
    await asyncio.sleep(3)
    
    print("\n✅ Test complete - Check logs above for routing confirmation")
    print("="*60)
    
    # Cleanup
    exec_engine.stop()
    await binance_exec_client._disconnect()
    await dydx_exec_client._disconnect()


if __name__ == "__main__":
    asyncio.run(test_dual_routing())
