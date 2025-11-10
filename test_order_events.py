"""
Test that order events are properly generated and flow back to strategy.
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
from nautilus_trader.core.uuid import UUID4

from src.crypto_trading_engine.adapters.dydx_v4_nautilus_adapter import create_dydx_v4_clients

load_dotenv()


async def test_order_events():
    """Test that order events are generated properly."""
    
    print("\n🧪 Testing Order Event Flow")
    print("="*60)
    
    # Create components
    loop = asyncio.get_event_loop()
    clock = LiveClock()
    trader_id = TraderId("TEST-001")
    msgbus = MessageBus(trader_id=trader_id, clock=clock)
    cache = Cache(database=None)
    portfolio = Portfolio(msgbus=msgbus, cache=cache, clock=clock)
    exec_engine = ExecutionEngine(msgbus=msgbus, cache=cache, clock=clock)
    
    # Create dYdX client (without wallet for paper trading)
    print("\n1. Creating dYdX execution client (paper mode)...")
    _, dydx_exec_client = create_dydx_v4_clients(
        loop=loop,
        msgbus=msgbus,
        cache=cache,
        clock=clock,
        network=os.getenv('DYDX__NETWORK', 'mainnet'),
        private_key='',  # No wallet = paper trading mode
        wallet_address='',
        account_number='0',
    )
    
    # Register client
    print("2. Registering execution client...")
    exec_engine.register_client(dydx_exec_client)
    
    # Create data client to load instruments
    print("3. Creating dYdX data client...")
    dydx_data_client, _ = create_dydx_v4_clients(
        loop=loop,
        msgbus=msgbus,
        cache=cache,
        clock=clock,
        network=os.getenv('DYDX__NETWORK', 'mainnet'),
        private_key='',
        wallet_address='',
        account_number='0',
    )
    
    # Connect data client to load instruments
    print("4. Connecting data client...")
    await dydx_data_client._connect()
    
    # Connect execution client
    print("5. Connecting execution client...")
    await dydx_exec_client._connect()
    
    # Start execution engine
    print("6. Starting execution engine...")
    exec_engine.start()
    
    # Wait for instruments
    await asyncio.sleep(2)
    
    # Create a test order
    print("7. Creating test order...")
    instrument_id = InstrumentId.from_str("BTC-USD.DYDX_V4")
    
    instrument = cache.instrument(instrument_id)
    if not instrument:
        print("❌ Instrument not found in cache!")
        return
    
    print(f"✅ Instrument loaded: {instrument.id}")
    
    # Create order
    from nautilus_trader.model.orders import MarketOrder
    strategy_id = StrategyId("TEST-STRATEGY-001")
    order = MarketOrder(
        trader_id=trader_id,
        strategy_id=strategy_id,
        instrument_id=instrument_id,
        client_order_id=ClientOrderId("TEST-DYDX-001"),
        order_side=OrderSide.SELL,
        quantity=Quantity.from_str("0.001"),
        time_in_force=TimeInForce.GTC,
        init_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )
    
    print(f"8. Submitting order via execution engine...")
    print(f"   Order: {order.side} {order.quantity} {order.instrument_id}")
    print(f"   Client Order ID: {order.client_order_id}")
    
    # Submit order
    from nautilus_trader.execution.messages import SubmitOrder
    command = SubmitOrder(
        trader_id=trader_id,
        strategy_id=strategy_id,
        order=order,
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )
    
    exec_engine.execute(command)
    
    print("9. Waiting for order events...")
    await asyncio.sleep(3)
    
    # Check order status
    print("\n10. Checking order status...")
    cached_order = cache.order(order.client_order_id)
    if cached_order:
        print(f"   Order status: {cached_order.status}")
        print(f"   Order state: {cached_order.status.name}")
        
        if cached_order.is_closed:
            print("   ✅ Order completed!")
        else:
            print("   ⚠️  Order still pending")
    else:
        print("   ❌ Order not found in cache")
    
    print("\n✅ Test complete")
    print("="*60)
    
    # Cleanup
    exec_engine.stop()
    await dydx_data_client._disconnect()
    await dydx_exec_client._disconnect()


if __name__ == "__main__":
    asyncio.run(test_order_events())
