"""
Test Binance order routing to compare with dYdX.
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

load_dotenv()


async def test_binance_order():
    """Test if Binance orders are routed properly."""
    
    print("\n🧪 Testing Binance Order Routing")
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
    
    # Register client
    print("2. Registering execution client...")
    exec_engine.register_client(binance_exec_client)
    
    # Connect
    print("3. Connecting...")
    await binance_exec_client._connect()
    
    # Start execution engine
    print("4. Starting execution engine...")
    exec_engine.start()
    
    # Create a test order
    print("5. Creating test order...")
    instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
    
    # Wait for instrument to load
    await asyncio.sleep(2)
    
    instrument = cache.instrument(instrument_id)
    if not instrument:
        print("❌ Instrument not found in cache!")
        print(f"Available instruments: {list(cache.instruments())}")
        return
    
    print(f"✅ Instrument loaded: {instrument.id}")
    
    # Create order
    strategy_id = StrategyId("TEST-STRATEGY-001")
    order = MarketOrder(
        trader_id=trader_id,
        strategy_id=strategy_id,
        instrument_id=instrument_id,
        client_order_id=ClientOrderId("TEST-BIN-001"),
        order_side=OrderSide.BUY,
        quantity=Quantity.from_str("0.001"),
        time_in_force=TimeInForce.GTC,
        init_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )
    
    print(f"6. Submitting order via execution engine...")
    print(f"   Order: {order.side} {order.quantity} {order.instrument_id}")
    print(f"   Client Order ID: {order.client_order_id}")
    
    # Submit order directly to execution engine
    from nautilus_trader.execution.messages import SubmitOrder
    command = SubmitOrder(
        trader_id=trader_id,
        strategy_id=strategy_id,
        order=order,
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )
    
    exec_engine.execute(command)
    
    print("7. Waiting for order processing...")
    await asyncio.sleep(5)
    
    print("\n✅ Test complete")
    print("="*60)
    
    # Cleanup
    exec_engine.stop()
    await binance_exec_client._disconnect()


if __name__ == "__main__":
    asyncio.run(test_binance_order())
