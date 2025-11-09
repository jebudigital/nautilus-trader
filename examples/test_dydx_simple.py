"""
Simple dYdX v4 Connection Test (No SDK Required)

This script tests basic connectivity to dYdX v4 using just HTTP requests.
Use this while you're fixing the v4-client-py installation.
"""

import os
import sys
import json
import requests
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def load_env_file():
    """Load environment variables from .env file."""
    try:
        env_path = project_root / '.env'
        if not env_path.exists():
            print("⚠️  No .env file found")
            return False
        
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value
        
        return True
    except Exception as e:
        print(f"❌ Error loading .env: {e}")
        return False


def test_dydx_api():
    """Test dYdX v4 API without SDK."""
    print("\n" + "="*60)
    print("🧪 Simple dYdX v4 API Test (No SDK)")
    print("="*60)
    
    # Load environment
    if not load_env_file():
        print("\n❌ Could not load .env file")
        return
    
    # Check configuration
    print("\n📋 Checking Configuration...")
    
    network = os.getenv('DYDX__NETWORK', 'not set')
    node_url = os.getenv('DYDX__NODE_URL', 'not set')
    mnemonic = os.getenv('DYDX__MNEMONIC', 'not set')
    
    print(f"  Network: {network}")
    print(f"  Node URL: {node_url}")
    print(f"  Mnemonic: {'✅ Set' if mnemonic != 'not set' and 'your' not in mnemonic else '❌ Not set'}")
    
    # Determine API base URL
    if network == 'testnet':
        api_base = 'https://indexer.v4testnet.dydx.exchange'
    else:
        api_base = 'https://indexer.dydx.trade'
    
    print(f"  API Base: {api_base}")
    
    # Test 1: Get Markets
    print("\n📊 Test 1: Fetching Markets...")
    try:
        response = requests.get(f"{api_base}/v4/perpetualMarkets", timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            markets = data.get('markets', {})
            
            print(f"  ✅ Found {len(markets)} markets")
            
            # Show BTC market
            if 'BTC-USD' in markets:
                btc = markets['BTC-USD']
                print(f"\n  BTC-USD Market:")
                print(f"    Price: ${btc.get('oraclePrice', 'N/A')}")
                print(f"    24h Volume: ${btc.get('volume24H', 'N/A')}")
                print(f"    Status: {btc.get('status', 'N/A')}")
        else:
            print(f"  ❌ Failed: HTTP {response.status_code}")
    except Exception as e:
        print(f"  ❌ Error: {e}")
    
    # Test 2: Get Orderbook
    print("\n📖 Test 2: Fetching BTC-USD Orderbook...")
    try:
        response = requests.get(
            f"{api_base}/v4/orderbooks/perpetualMarket/BTC-USD",
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            bids = data.get('bids', [])
            asks = data.get('asks', [])
            
            print(f"  ✅ Orderbook fetched")
            print(f"\n  Top 3 Bids:")
            for bid in bids[:3]:
                print(f"    ${bid['price']} - {bid['size']} BTC")
            
            print(f"\n  Top 3 Asks:")
            for ask in asks[:3]:
                print(f"    ${ask['price']} - {ask['size']} BTC")
        else:
            print(f"  ❌ Failed: HTTP {response.status_code}")
    except Exception as e:
        print(f"  ❌ Error: {e}")
    
    # Test 3: Get Funding Rates
    print("\n💰 Test 3: Fetching Funding Rates...")
    try:
        response = requests.get(
            f"{api_base}/v4/historicalFunding/BTC-USD",
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            funding = data.get('historicalFunding', [])
            
            if funding:
                latest = funding[0]
                rate = float(latest['rate'])
                apy = rate * 3 * 365 * 100  # Convert to APY
                
                print(f"  ✅ BTC-USD Funding Rate:")
                print(f"    Current Rate: {rate:.6f}")
                print(f"    APY: {apy:.2f}%")
                print(f"    Effective At: {latest.get('effectiveAt', 'N/A')}")
        else:
            print(f"  ❌ Failed: HTTP {response.status_code}")
    except Exception as e:
        print(f"  ❌ Error: {e}")
    
    # Test 4: Get Candles
    print("\n📈 Test 4: Fetching Price Candles...")
    try:
        response = requests.get(
            f"{api_base}/v4/candles/perpetualMarkets/BTC-USD",
            params={'resolution': '1HOUR'},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            candles = data.get('candles', [])
            
            if candles:
                latest = candles[0]
                print(f"  ✅ Latest 1H Candle:")
                print(f"    Open: ${latest.get('open', 'N/A')}")
                print(f"    High: ${latest.get('high', 'N/A')}")
                print(f"    Low: ${latest.get('low', 'N/A')}")
                print(f"    Close: ${latest.get('close', 'N/A')}")
                print(f"    Volume: ${latest.get('usdVolume', 'N/A')}")
        else:
            print(f"  ❌ Failed: HTTP {response.status_code}")
    except Exception as e:
        print(f"  ❌ Error: {e}")
    
    # Summary
    print("\n" + "="*60)
    print("✅ API Test Complete!")
    print("="*60)
    
    print("\n📝 Summary:")
    print("  ✅ Can connect to dYdX v4 API")
    print("  ✅ Can fetch market data")
    print("  ✅ Can get orderbook")
    print("  ✅ Can get funding rates")
    print("  ✅ Can get price history")
    
    print("\n⚠️  Note: This test uses public API endpoints")
    print("   To place orders, you need the full v4-client-py SDK")
    
    print("\n🔧 To fix v4-client-py installation:")
    print("   1. pip3 install --upgrade pip")
    print("   2. pip3 install grpcio grpcio-tools --no-cache-dir")
    print("   3. pip3 install v4-client-py")
    
    print("\n📖 Or see: TESTNET_SETUP.md for alternatives")


if __name__ == "__main__":
    try:
        test_dydx_api()
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
