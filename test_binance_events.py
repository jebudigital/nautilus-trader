"""
Test that Binance order events work properly.
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


async def test_binance_events():
    """Test that Binance order events are generated properly."""
    
    print("\n🧪 Testing Binance Order Event Flow")
    print("="*60)
    
    # Enable logging
    import logging
    logging.basicConfig(level=logging.INFO)
    
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
    testnet = os.getenv('BINANCE__SANDBOX', 'false').lower() == 'true'
    print(f"   Using {'TESTNET' if testnet else 'MAINNET'}")
    
    binance_exec_config = BinanceExecClientConfig(
        api_key=os.getenv('BINANCE__API_KEY', ''),
        api_secret=os.getenv('BINANCE__API_SECRET', ''),
        testnet=testnet,
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
    
    # Also create data client for WebSocket updates
    print("3. Creating Binance data client...")
    from nautilus_trader.adapters.binance.factories import BinanceLiveDataClientFactory
    from nautilus_trader.adapters.binance.config import BinanceDataClientConfig
    from nautilus_trader.data.engine import DataEngine
    
    data_engine = DataEngine(msgbus=msgbus, cache=cache, clock=clock)
    
    binance_data_config = BinanceDataClientConfig(
        api_key=os.getenv('BINANCE__API_KEY', ''),
        api_secret=os.getenv('BINANCE__API_SECRET', ''),
        testnet=testnet,
    )
    
    binance_data_client = BinanceLiveDataClientFactory.create(
        loop=loop,
        name="BINANCE",
        msgbus=msgbus,
        cache=cache,
        clock=clock,
        config=binance_data_config,
    )
    
    data_engine.register_client(binance_data_client)
    
    # Connect
    print("4. Connecting data client...")
    await binance_data_client._connect()
    
    print("5. Connecting execution client...")
    await binance_exec_client._connect()
    
    # Start engines
    print("6. Starting engines...")
    data_engine.start()
    exec_engine.start()
    
    # Wait for connection
    await asyncio.sleep(2)
    
    # Check if we have an account
    accounts = list(cache.accounts())
    print(f"5. Accounts loaded: {len(accounts)}")
    for account in accounts:
        print(f"   - {account.id}")
    
    # Create a test order
    print("6. Creating test order...")
    instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
    
    # Check if instrument exists
    instrument = cache.instrument(instrument_id)
    if not instrument:
        print("   ⚠️  Instrument not in cache, creating manually...")
        from nautilus_trader.model.instruments import CurrencyPair
        from nautilus_trader.model.identifiers import Symbol
        from nautilus_trader.model.objects import Price, Quantity, Currency
        from decimal import Decimal
        
        instrument = CurrencyPair(
            instrument_id=instrument_id,
            raw_symbol=Symbol("BTCUSDT"),
            base_currency=Currency.from_str("BTC"),
            quote_currency=Currency.from_str("USDT"),
            price_precision=2,
            size_precision=5,
            price_increment=Price.from_str("0.01"),
            size_increment=Quantity.from_str("0.00001"),
            max_quantity=Quantity.from_str("9000"),
            min_quantity=Quantity.from_str("0.00001"),
            max_price=Price.from_str("1000000"),
            min_price=Price.from_str("0.01"),
            margin_init=Decimal("1.0"),
            margin_maint=Decimal("1.0"),
            maker_fee=Decimal("0.001"),
            taker_fee=Decimal("0.001"),
            ts_event=clock.timestamp_ns(),
            ts_init=clock.timestamp_ns(),
        )
        cache.add_instrument(instrument)
    
    print(f"   ✅ Instrument: {instrument.id}")
    
    # Create order - BUY since we now have USDT
    strategy_id = StrategyId("TEST-STRATEGY-001")
    
    # Check balances
    accounts = list(cache.accounts())
    if accounts:
        account = accounts[0]
        print(f"\n   Account balances:")
        try:
            balances = account.balances()
            for currency, balance in balances.items():
                if balance.total.as_double() > 0:
                    print(f"      {currency}: {balance.total.as_double():.8f}")
        except:
            pass
    
    # Buy 0.00006 BTC = ~$6.31 worth (above $5 minimum)
    # We have $168.89 USDT so this should work
    order = MarketOrder(
        trader_id=trader_id,
        strategy_id=strategy_id,
        instrument_id=instrument_id,
        client_order_id=ClientOrderId("TEST-BIN-001"),
        order_side=OrderSide.BUY,
        quantity=Quantity.from_str("0.00006"),
        time_in_force=TimeInForce.GTC,
        init_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )
    
    print(f"7. Submitting order via execution engine...")
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
    
    print("8. Waiting for order events...")
    await asyncio.sleep(10)  # Wait longer for fill
    
    # Check order status
    print("\n9. Checking order status...")
    cached_order = cache.order(order.client_order_id)
    if cached_order:
        print(f"   Order status: {cached_order.status}")
        print(f"   Order state: {cached_order.status.name}")
        
        # Check for rejection reason
        if str(cached_order.status) == "REJECTED":
            # Get all events for this order
            try:
                events = cache.events()
                for event in events:
                    if hasattr(event, 'client_order_id') and event.client_order_id == order.client_order_id:
                        if hasattr(event, 'reason'):
                            print(f"   ❌ Rejection reason: {event.reason}")
            except:
                pass
        
        if cached_order.is_closed:
            print("   ✅ Order completed!")
        else:
            print("   ⚠️  Order still pending")
    else:
        print("   ❌ Order not found in cache")
    
    print("\n✅ Test complete")
    print("="*60)
    
    # Cleanup
    data_engine.stop()
    exec_engine.stop()
    await binance_data_client._disconnect()
    await binance_exec_client._disconnect()


if __name__ == "__main__":
    asyncio.run(test_binance_events())
