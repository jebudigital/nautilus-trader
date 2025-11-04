#!/usr/bin/env python3
"""
Example script to test the trading infrastructure with a simple strategy.
"""

import asyncio
from decimal import Decimal
from datetime import datetime

from nautilus_trader.model.identifiers import ClientOrderId, StrategyId
from nautilus_trader.model.enums import OrderSide, OrderType, TimeInForce
from nautilus_trader.model.objects import Price, Quantity

from src.crypto_trading_engine.adapters.binance_adapter import BinanceAdapter
from src.crypto_trading_engine.models.trading_mode import TradingMode
from src.crypto_trading_engine.models.core import Order


async def test_simple_strategy():
    """Test a simple buy-and-hold strategy simulation."""
    
    print("🚀 Testing Simple Strategy with Binance Adapter")
    print("=" * 50)
    
    # Initialize adapter in paper trading mode
    config = {
        'api_key': 'test_key',
        'api_secret': 'test_secret', 
        'testnet': True
    }
    
    adapter = BinanceAdapter(config, TradingMode.PAPER)
    
    # Set up callbacks to track events
    def on_order_filled(order, fill):
        print(f"📈 Order Filled: {order.id} - {fill.fill_quantity} @ {fill.fill_price}")
    
    def on_error(error):
        print(f"❌ Error: {error}")
    
    adapter.set_callbacks(
        on_order_filled=on_order_filled,
        on_error=on_error
    )
    
    try:
        # Connect to exchange
        print("🔗 Connecting to Binance (Paper Trading)...")
        connected = await adapter.connect()
        print(f"   Connection Status: {'✅ Connected' if connected else '❌ Failed'}")
        
        if not connected:
            return
        
        # Get account balance
        print("\n💰 Account Balance:")
        balance = await adapter.get_balance()
        for currency, amount in balance.items():
            print(f"   {currency}: {amount}")
        
        # Get available instruments
        print("\n📊 Available Instruments:")
        instruments = await adapter.get_instruments()
        print(f"   Found {len(instruments)} instruments")
        if instruments:
            btc_instrument = instruments[0]  # Use first available
            print(f"   Using: {btc_instrument.symbol}")
            
            # Create a simple buy order
            print("\n📝 Creating Buy Order...")
            order = Order(
                id=ClientOrderId("SIMPLE_BUY_001"),
                instrument=btc_instrument,
                side=OrderSide.BUY,
                quantity=Quantity(Decimal("0.001"), btc_instrument.size_precision),
                price=Price(Decimal("45000"), btc_instrument.price_precision),
                order_type=OrderType.LIMIT,
                time_in_force=TimeInForce.GTC,
                strategy_id=StrategyId("SIMPLE-STRATEGY"),
                trading_mode=TradingMode.PAPER,
                created_time=datetime.now(),
                is_simulated=True
            )
            
            # Submit order
            success = await adapter.submit_order(order)
            print(f"   Order Submission: {'✅ Success' if success else '❌ Failed'}")
            
            # Check order status
            if success:
                await asyncio.sleep(1)  # Give time for processing
                status = await adapter.get_order_status(str(order.id))
                print(f"   Order Status: {status}")
                
                # Get positions
                print("\n📍 Current Positions:")
                positions = await adapter.get_positions()
                for pos in positions:
                    print(f"   {pos.instrument.symbol}: {pos.quantity} @ {pos.avg_price}")
        
        print("\n🎯 Strategy Test Summary:")
        print(f"   Adapter: {adapter.venue}")
        print(f"   Mode: {adapter.trading_mode.value}")
        print(f"   Orders: {len(adapter.orders)}")
        print(f"   Positions: {len(adapter.positions)}")
        
    except Exception as e:
        print(f"❌ Strategy test failed: {e}")
    
    finally:
        # Clean up
        print("\n🧹 Cleaning up...")
        await adapter.disconnect()
        print("✅ Test completed!")


if __name__ == "__main__":
    asyncio.run(test_simple_strategy())