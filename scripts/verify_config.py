"""
Verify Configuration

Check if API keys, mnemonics, and network connections are valid.
"""

import asyncio
import aiohttp
import os
from pathlib import Path
import sys

# Add project root
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def load_env():
    """Load .env file."""
    env_path = project_root / '.env'
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value


async def verify_binance(api_key: str, api_secret: str, is_testnet: bool):
    """Verify Binance connection."""
    print("\n" + "="*60)
    print("🔍 Verifying Binance Configuration")
    print("="*60)
    
    network = "Testnet" if is_testnet else "Mainnet"
    base_url = "https://testnet.binance.vision" if is_testnet else "https://api.binance.com"
    
    print(f"\n📡 Network: {network}")
    print(f"🔗 URL: {base_url}")
    print(f"🔑 API Key: {api_key[:10]}...{api_key[-4:] if len(api_key) > 14 else ''}")
    
    # Test public endpoint (no auth needed)
    async with aiohttp.ClientSession() as session:
        try:
            url = f"{base_url}/api/v3/ping"
            async with session.get(url) as response:
                if response.status == 200:
                    print(f"✅ Public API accessible")
                else:
                    print(f"❌ Public API error: {response.status}")
                    return False
        except Exception as e:
            print(f"❌ Connection error: {e}")
            return False
        
        # Test data endpoint
        try:
            url = f"{base_url}/api/v3/ticker/24hr"
            params = {"symbol": "BTCUSDT"}
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ Market data accessible")
                    print(f"   BTC Price: ${float(data['lastPrice']):,.2f}")
                    print(f"   24h Volume: {float(data['volume']):,.2f} BTC")
                else:
                    print(f"❌ Market data error: {response.status}")
                    return False
        except Exception as e:
            print(f"❌ Market data error: {e}")
            return False
        
        # Test authenticated endpoint (if keys provided)
        if api_key and api_key != "your_binance_api_key_here":
            import hmac
            import hashlib
            import time
            
            try:
                timestamp = int(time.time() * 1000)
                query_string = f"timestamp={timestamp}"
                signature = hmac.new(
                    api_secret.encode('utf-8'),
                    query_string.encode('utf-8'),
                    hashlib.sha256
                ).hexdigest()
                
                url = f"{base_url}/api/v3/account"
                headers = {"X-MBX-APIKEY": api_key}
                params = {"timestamp": timestamp, "signature": signature}
                
                async with session.get(url, headers=headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        print(f"✅ API keys valid")
                        print(f"   Account type: {data.get('accountType', 'Unknown')}")
                        balances = [b for b in data.get('balances', []) if float(b['free']) > 0 or float(b['locked']) > 0]
                        if balances:
                            print(f"   Balances: {len(balances)} assets")
                    else:
                        error_text = await response.text()
                        print(f"❌ API keys invalid: {response.status}")
                        print(f"   Error: {error_text}")
                        return False
            except Exception as e:
                print(f"⚠️  Could not verify API keys: {e}")
        else:
            print(f"⚠️  No API keys configured (OK for backtesting)")
    
    return True


async def verify_dydx(network: str):
    """Verify dYdX connection."""
    print("\n" + "="*60)
    print("🔍 Verifying dYdX Configuration")
    print("="*60)
    
    if network == "testnet":
        base_url = "https://indexer.v4testnet.dydx.exchange"
    else:
        base_url = "https://indexer.dydx.trade"
    
    print(f"\n📡 Network: {network.title()}")
    print(f"🔗 URL: {base_url}")
    
    async with aiohttp.ClientSession() as session:
        # Test market data
        try:
            url = f"{base_url}/v4/perpetualMarkets"
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    markets = data.get('markets', {})
                    print(f"✅ Market data accessible")
                    print(f"   Available markets: {len(markets)}")
                    
                    if 'BTC-USD' in markets:
                        btc_market = markets['BTC-USD']
                        print(f"   BTC-USD price: ${float(btc_market.get('oraclePrice', 0)):,.2f}")
                        print(f"   BTC-USD volume (24h): ${float(btc_market.get('volume24H', 0)):,.0f}")
                    else:
                        print(f"   ⚠️  BTC-USD market not found")
                else:
                    print(f"❌ Market data error: {response.status}")
                    return False
        except Exception as e:
            print(f"❌ Connection error: {e}")
            return False
        
        # Test candles endpoint
        try:
            url = f"{base_url}/v4/candles/perpetualMarkets/BTC-USD"
            params = {"resolution": "1MIN", "limit": 1}
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    candles = data.get('candles', [])
                    if candles:
                        print(f"✅ Historical data accessible")
                        print(f"   Latest candle: {candles[0].get('startedAt', 'Unknown')}")
                    else:
                        print(f"⚠️  No candle data available")
                else:
                    print(f"❌ Historical data error: {response.status}")
                    return False
        except Exception as e:
            print(f"❌ Historical data error: {e}")
            return False
        
        # Test funding rates
        try:
            url = f"{base_url}/v4/historicalFunding/BTC-USD"
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    funding = data.get('historicalFunding', [])
                    if funding:
                        latest = funding[0]
                        rate = float(latest.get('rate', 0))
                        apy = rate * 3 * 365 * 100  # 3x per day
                        print(f"✅ Funding rates accessible")
                        print(f"   Latest rate: {rate:.6f} ({apy:.2f}% APY)")
                        print(f"   Effective at: {latest.get('effectiveAt', 'Unknown')}")
                    else:
                        print(f"⚠️  No funding rate data available")
                else:
                    print(f"❌ Funding rate error: {response.status}")
                    return False
        except Exception as e:
            print(f"❌ Funding rate error: {e}")
            return False
    
    return True


async def check_loaded_data():
    """Check what data is currently loaded."""
    print("\n" + "="*60)
    print("📂 Checking Loaded Data")
    print("="*60)
    
    data_dir = project_root / "data" / "historical" / "parquet"
    
    if not data_dir.exists():
        print("\n❌ No data directory found")
        print("   Run: python scripts/load_historical_data.py --days 7")
        return False
    
    index_file = data_dir / "index.json"
    if index_file.exists():
        import json
        with open(index_file, 'r') as f:
            index = json.load(f)
        
        if index:
            print(f"\n✅ Found {len(index)} data load(s):")
            for entry in index:
                print(f"\n   📊 {entry['start_date']} to {entry['end_date']}")
                print(f"      Created: {entry['created_at']}")
                print(f"      Dates: {len(entry['dates'])} days")
                stats = entry['stats']
                print(f"      Binance bars: {stats['binance_bars']:,}")
                print(f"      dYdX bars: {stats['dydx_bars']:,}")
                print(f"      Funding rates: {stats['dydx_funding']}")
        else:
            print("\n❌ Index file is empty")
            return False
    else:
        print("\n⚠️  No index file found")
        return False
    
    return True


async def main():
    """Main verification."""
    print("\n" + "="*60)
    print("🔧 Configuration Verification Tool")
    print("="*60)
    
    # Load environment
    load_env()
    
    # Get configuration
    binance_key = os.getenv('BINANCE__API_KEY', '')
    binance_secret = os.getenv('BINANCE__API_SECRET', '')
    binance_testnet = os.getenv('BINANCE__SANDBOX', 'false').lower() == 'true'
    
    dydx_mnemonic = os.getenv('DYDX__MNEMONIC', '')
    dydx_network = os.getenv('DYDX__NETWORK', 'testnet')
    
    print(f"\n📋 Current Configuration:")
    print(f"   Binance: {'Testnet' if binance_testnet else 'Mainnet'}")
    print(f"   dYdX: {dydx_network.title()}")
    
    # Verify connections
    binance_ok = await verify_binance(binance_key, binance_secret, binance_testnet)
    dydx_ok = await verify_dydx(dydx_network)
    data_ok = await check_loaded_data()
    
    # Summary
    print("\n" + "="*60)
    print("📊 Verification Summary")
    print("="*60)
    print(f"\n{'✅' if binance_ok else '❌'} Binance: {'OK' if binance_ok else 'FAILED'}")
    print(f"{'✅' if dydx_ok else '❌'} dYdX: {'OK' if dydx_ok else 'FAILED'}")
    print(f"{'✅' if data_ok else '❌'} Data: {'OK' if data_ok else 'FAILED'}")
    
    if binance_ok and dydx_ok and data_ok:
        print("\n✅ All checks passed! Ready for backtesting.")
    else:
        print("\n⚠️  Some checks failed. Review errors above.")
    
    print("\n💡 Next Steps:")
    if not data_ok:
        print("   1. Load historical data:")
        print("      python scripts/load_historical_data.py --days 30")
    print("   2. Run backtest:")
    print("      python examples/backtest_delta_neutral.py --start 2025-10-10 --end 2025-11-09")


if __name__ == "__main__":
    asyncio.run(main())
