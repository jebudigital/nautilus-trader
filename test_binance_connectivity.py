"""
Test Binance API connectivity and credentials.
"""

import asyncio
import os
from pathlib import Path
import sys

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
import aiohttp

load_dotenv()


async def test_binance_connectivity():
    """Test Binance API connectivity and credentials."""
    
    print("\n🧪 Testing Binance API Connectivity")
    print("="*60)
    
    api_key = os.getenv('BINANCE__API_KEY', '')
    api_secret = os.getenv('BINANCE__API_SECRET', '')
    testnet = os.getenv('BINANCE__SANDBOX', 'false').lower() == 'true'
    
    print(f"\n1. Configuration:")
    print(f"   API Key: {api_key[:10]}...{api_key[-4:] if len(api_key) > 14 else ''}")
    print(f"   API Secret: {'*' * 10}...{api_secret[-4:] if len(api_secret) > 14 else ''}")
    print(f"   Testnet: {testnet}")
    
    if testnet:
        base_url = "https://testnet.binance.vision"
    else:
        base_url = "https://api.binance.com"
    
    print(f"   Base URL: {base_url}")
    
    async with aiohttp.ClientSession() as session:
        # Test 1: Public endpoint (no auth)
        print("\n2. Testing public endpoint (server time)...")
        try:
            async with session.get(f"{base_url}/api/v3/time") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"   ✅ Server time: {data.get('serverTime')}")
                else:
                    print(f"   ❌ Failed: {response.status}")
                    text = await response.text()
                    print(f"   Response: {text}")
        except Exception as e:
            print(f"   ❌ Error: {e}")
        
        # Test 2: Exchange info (no auth)
        print("\n3. Testing exchange info...")
        try:
            async with session.get(f"{base_url}/api/v3/exchangeInfo?symbol=BTCUSDT") as response:
                if response.status == 200:
                    data = await response.json()
                    symbols = data.get('symbols', [])
                    if symbols:
                        symbol = symbols[0]
                        print(f"   ✅ Symbol: {symbol.get('symbol')}")
                        print(f"   Status: {symbol.get('status')}")
                        print(f"   Base: {symbol.get('baseAsset')}")
                        print(f"   Quote: {symbol.get('quoteAsset')}")
                    else:
                        print(f"   ⚠️  No symbols found")
                else:
                    print(f"   ❌ Failed: {response.status}")
        except Exception as e:
            print(f"   ❌ Error: {e}")
        
        # Test 3: Account endpoint (requires auth)
        print("\n4. Testing authenticated endpoint (account info)...")
        if not api_key or not api_secret:
            print("   ⚠️  No API credentials provided")
        else:
            try:
                import hmac
                import hashlib
                import time
                
                timestamp = int(time.time() * 1000)
                query_string = f"timestamp={timestamp}"
                
                signature = hmac.new(
                    api_secret.encode('utf-8'),
                    query_string.encode('utf-8'),
                    hashlib.sha256
                ).hexdigest()
                
                headers = {
                    'X-MBX-APIKEY': api_key
                }
                
                url = f"{base_url}/api/v3/account?{query_string}&signature={signature}"
                
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        print(f"   ✅ Account authenticated!")
                        print(f"   Can Trade: {data.get('canTrade')}")
                        print(f"   Can Withdraw: {data.get('canWithdraw')}")
                        print(f"   Can Deposit: {data.get('canDeposit')}")
                        
                        # Show balances
                        balances = data.get('balances', [])
                        non_zero = [b for b in balances if float(b.get('free', 0)) > 0 or float(b.get('locked', 0)) > 0]
                        
                        if non_zero:
                            print(f"\n   💰 Balances:")
                            for balance in non_zero[:10]:  # Show first 10
                                asset = balance.get('asset')
                                free = float(balance.get('free', 0))
                                locked = float(balance.get('locked', 0))
                                if free > 0 or locked > 0:
                                    print(f"      {asset}: {free:.8f} (free) + {locked:.8f} (locked)")
                        else:
                            print(f"\n   ⚠️  No balances found (account may be empty)")
                    
                    elif response.status == 401:
                        print(f"   ❌ Authentication failed (401)")
                        text = await response.text()
                        print(f"   Response: {text}")
                        print(f"\n   Possible issues:")
                        print(f"   - Invalid API key")
                        print(f"   - Invalid API secret")
                        print(f"   - API key not enabled for trading")
                        print(f"   - Wrong testnet/mainnet setting")
                    
                    elif response.status == 403:
                        print(f"   ❌ Forbidden (403)")
                        text = await response.text()
                        print(f"   Response: {text}")
                        print(f"\n   Possible issues:")
                        print(f"   - API key doesn't have required permissions")
                        print(f"   - IP restriction enabled")
                    
                    else:
                        print(f"   ❌ Failed: {response.status}")
                        text = await response.text()
                        print(f"   Response: {text}")
                        
            except Exception as e:
                print(f"   ❌ Error: {e}")
                import traceback
                traceback.print_exc()
        
        # Test 4: Try to get current BTC price
        print("\n5. Testing market data (BTC price)...")
        try:
            async with session.get(f"{base_url}/api/v3/ticker/price?symbol=BTCUSDT") as response:
                if response.status == 200:
                    data = await response.json()
                    price = float(data.get('price', 0))
                    print(f"   ✅ BTC Price: ${price:,.2f}")
                else:
                    print(f"   ❌ Failed: {response.status}")
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    print("\n" + "="*60)
    print("✅ Connectivity test complete")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(test_binance_connectivity())
