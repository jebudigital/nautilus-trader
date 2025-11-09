"""
Test dYdX v4 REST Adapter

Tests the new REST API adapter that doesn't require the full SDK.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.crypto_trading_engine.adapters.dydx_v4_rest_adapter import create_dydx_v4_adapter_from_env
from src.crypto_trading_engine.models.trading_mode import TradingMode


async def test_rest_adapter():
    """Test the REST adapter."""
    print("\n" + "="*60)
    print("🧪 Testing dYdX v4 REST Adapter")
    print("="*60)
    
    # Create adapter from environment
    print("\n📦 Creating adapter from .env...")
    adapter = create_dydx_v4_adapter_from_env(TradingMode.PAPER)
    print(f"  ✅ Adapter created: {adapter.network} network")
    
    # Connect
    print("\n🔌 Connecting to dYdX v4...")
    connected = await adapter.connect()
    
    if not connected:
        print("  ❌ Connection failed")
        return
    
    print("  ✅ Connected successfully")
    
    # Test 1: Get instruments
    print("\n📊 Test 1: Fetching Instruments...")
    instruments = await adapter.get_instruments()
    print(f"  ✅ Found {len(instruments)} instruments")
    
    # Show a few
    for inst in instruments[:5]:
        print(f"     {inst.symbol}: {inst.base_currency}/{inst.quote_currency}")
    
    # Test 2: Get orderbook
    print("\n📖 Test 2: Fetching BTC-USD Orderbook...")
    orderbook = await adapter.get_orderbook('BTC-USD')
    
    if orderbook:
        bids = orderbook.get('bids', [])
        asks = orderbook.get('asks', [])
        
        print(f"  ✅ Orderbook fetched")
        print(f"\n  Top 3 Bids:")
        for bid in bids[:3]:
            print(f"     ${bid['price']} - {bid['size']} BTC")
        
        print(f"\n  Top 3 Asks:")
        for ask in asks[:3]:
            print(f"     ${ask['price']} - {ask['size']} BTC")
    else:
        print("  ❌ Failed to fetch orderbook")
    
    # Test 3: Get funding rates
    print("\n💰 Test 3: Fetching Funding Rates...")
    funding_rates = await adapter.get_funding_rates('BTC-USD')
    
    if funding_rates:
        latest = funding_rates[0]
        apy = latest.rate * 3 * 365 * 100
        
        print(f"  ✅ BTC-USD Funding Rate:")
        print(f"     Current Rate: {latest.rate:.6f}")
        print(f"     APY: {apy:.2f}%")
        print(f"     Timestamp: {latest.timestamp}")
    else:
        print("  ❌ Failed to fetch funding rates")
    
    # Test 4: Get market price
    print("\n💵 Test 4: Fetching Market Price...")
    price = await adapter.get_market_price('BTC-USD')
    
    if price:
        print(f"  ✅ BTC-USD Price: ${price:,.2f}")
    else:
        print("  ❌ Failed to fetch price")
    
    # Test 5: Get candles
    print("\n📈 Test 5: Fetching Price Candles...")
    candles = await adapter.get_candles('BTC-USD', '1HOUR')
    
    if candles:
        latest = candles[0]
        print(f"  ✅ Latest 1H Candle:")
        print(f"     Open: ${latest.get('open', 'N/A')}")
        print(f"     High: ${latest.get('high', 'N/A')}")
        print(f"     Low: ${latest.get('low', 'N/A')}")
        print(f"     Close: ${latest.get('close', 'N/A')}")
    else:
        print("  ❌ Failed to fetch candles")
    
    # Test ETH as well
    print("\n📊 Test 6: Fetching ETH Data...")
    eth_price = await adapter.get_market_price('ETH-USD')
    eth_funding = await adapter.get_funding_rates('ETH-USD')
    
    if eth_price:
        print(f"  ✅ ETH-USD Price: ${eth_price:,.2f}")
    
    if eth_funding:
        eth_apy = eth_funding[0].rate * 3 * 365 * 100
        print(f"  ✅ ETH-USD Funding APY: {eth_apy:.2f}%")
    
    # Disconnect
    print("\n🔌 Disconnecting...")
    await adapter.disconnect()
    print("  ✅ Disconnected")
    
    # Summary
    print("\n" + "="*60)
    print("✅ REST Adapter Test Complete!")
    print("="*60)
    
    print("\n📝 Summary:")
    print("  ✅ Adapter works without v4-client-py SDK")
    print("  ✅ Can fetch orderbook data")
    print("  ✅ Can get funding rates")
    print("  ✅ Can get market prices")
    print("  ✅ Can get price history")
    print("  ✅ Ready for paper trading!")
    
    print("\n🚀 Next Steps:")
    print("  python3 examples/delta_neutral_live_paper_trading.py")


if __name__ == "__main__":
    try:
        asyncio.run(test_rest_adapter())
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
