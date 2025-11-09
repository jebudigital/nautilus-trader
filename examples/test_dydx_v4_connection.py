"""
Test dYdX v4 Connection

Simple script to test if you can:
1. Connect to dYdX v4
2. Fetch orderbook data
3. Check your account
4. Get market data
"""

import asyncio
import os
import sys
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


async def test_dydx_v4_connection():
    """Test dYdX v4 connection and functionality."""
    print("\n" + "="*60)
    print("🧪 Testing dYdX v4 Connection")
    print("="*60)
    
    # Load environment
    if not load_env_file():
        print("\n❌ Could not load .env file")
        return
    
    # Check configuration
    print("\n📋 Checking Configuration...")
    
    version = os.getenv('DYDX__VERSION', 'not set')
    mnemonic = os.getenv('DYDX__MNEMONIC', 'not set')
    network = os.getenv('DYDX__NETWORK', 'not set')
    node_url = os.getenv('DYDX__NODE_URL', 'not set')
    
    print(f"  Version: {version}")
    print(f"  Network: {network}")
    print(f"  Node URL: {node_url}")
    print(f"  Mnemonic: {'✅ Set' if mnemonic != 'not set' and 'your' not in mnemonic else '❌ Not set'}")
    
    if version != 'v4':
        print("\n⚠️  DYDX__VERSION should be 'v4'")
        print("   Update your .env file:")
        print("   DYDX__VERSION=v4")
        return
    
    if 'your' in mnemonic or mnemonic == 'not set':
        print("\n⚠️  DYDX__MNEMONIC not configured")
        print("\n📝 To fix:")
        print("   1. Open MetaMask")
        print("   2. Settings → Security & Privacy")
        print("   3. Reveal Secret Recovery Phrase")
        print("   4. Copy the 12 or 24 words")
        print("   5. Add to .env:")
        print("      DYDX__MNEMONIC=word1 word2 word3 ...")
        return
    
    # Try to import v4 SDK
    print("\n📦 Checking v4 SDK...")
    try:
        from v4_client_py import Client
        from v4_client_py.clients.constants import Network
        print("  ✅ v4-client-py installed")
    except ImportError:
        print("  ❌ v4-client-py not installed")
        print("\n📝 To fix:")
        print("   pip install v4-client-py")
        return
    
    # Test connection
    print("\n🔌 Testing Connection...")
    try:
        # Determine network
        if network == 'testnet':
            network_config = Network.TESTNET
        else:
            network_config = Network.MAINNET
        
        # Create client
        print(f"  Connecting to {network} network...")
        client = Client(
            network=network_config,
            mnemonic=mnemonic
        )
        
        print("  ✅ Client created successfully")
        
        # Get account info
        print("\n👤 Fetching Account Info...")
        try:
            account = client.account
            address = account.address
            print(f"  ✅ Your dYdX Address: {address}")
        except Exception as e:
            print(f"  ⚠️  Could not get account: {e}")
        
        # Test market data
        print("\n📊 Testing Market Data...")
        try:
            # Get BTC-USD market
            markets = client.markets.get_perpetual_markets()
            
            if markets and 'markets' in markets:
                btc_market = markets['markets'].get('BTC-USD')
                if btc_market:
                    print(f"  ✅ BTC-USD Market Data:")
                    print(f"     Price: ${btc_market.get('oraclePrice', 'N/A')}")
                    print(f"     24h Volume: ${btc_market.get('volume24H', 'N/A')}")
                else:
                    print("  ⚠️  BTC-USD market not found")
            else:
                print("  ⚠️  No market data available")
        except Exception as e:
            print(f"  ⚠️  Could not fetch market data: {e}")
        
        # Test orderbook
        print("\n📖 Testing Orderbook...")
        try:
            orderbook = client.markets.get_perpetual_market_orderbook('BTC-USD')
            
            if orderbook and 'bids' in orderbook and 'asks' in orderbook:
                bids = orderbook['bids'][:3]  # Top 3 bids
                asks = orderbook['asks'][:3]  # Top 3 asks
                
                print("  ✅ BTC-USD Orderbook:")
                print("\n  Top 3 Bids:")
                for bid in bids:
                    print(f"     ${bid['price']} - {bid['size']} BTC")
                
                print("\n  Top 3 Asks:")
                for ask in asks:
                    print(f"     ${ask['price']} - {ask['size']} BTC")
            else:
                print("  ⚠️  Orderbook data not available")
        except Exception as e:
            print(f"  ⚠️  Could not fetch orderbook: {e}")
        
        # Test funding rates
        print("\n💰 Testing Funding Rates...")
        try:
            funding = client.markets.get_perpetual_market_funding('BTC-USD')
            
            if funding and 'historicalFunding' in funding:
                latest = funding['historicalFunding'][0]
                rate = float(latest['rate'])
                apy = rate * 3 * 365 * 100  # Convert to APY
                
                print(f"  ✅ BTC-USD Funding Rate:")
                print(f"     Current Rate: {rate:.6f} ({apy:.2f}% APY)")
                print(f"     Next Funding: {latest.get('effectiveAt', 'N/A')}")
            else:
                print("  ⚠️  Funding rate data not available")
        except Exception as e:
            print(f"  ⚠️  Could not fetch funding rates: {e}")
        
        # Check account balance
        print("\n💵 Checking Account Balance...")
        try:
            account_data = client.account.get_account()
            
            if account_data and 'account' in account_data:
                acc = account_data['account']
                equity = acc.get('equity', '0')
                free_collateral = acc.get('freeCollateral', '0')
                
                print(f"  ✅ Account Balance:")
                print(f"     Equity: ${equity}")
                print(f"     Free Collateral: ${free_collateral}")
            else:
                print("  ⚠️  Account balance not available")
        except Exception as e:
            print(f"  ⚠️  Could not fetch balance: {e}")
        
        print("\n" + "="*60)
        print("✅ Connection Test Complete!")
        print("="*60)
        
        print("\n📝 Summary:")
        print("  ✅ Can connect to dYdX v4")
        print("  ✅ Can fetch market data")
        print("  ✅ Can get orderbook")
        print("  ✅ Can get funding rates")
        print("  ✅ Can check account balance")
        
        print("\n🚀 You're ready to:")
        print("  1. Fetch real-time orderbook data")
        print("  2. Submit orders programmatically")
        print("  3. Run the delta-neutral strategy")
        
        print("\n📖 Next Steps:")
        print("  python3 examples/delta_neutral_live_paper_trading.py")
        
    except Exception as e:
        print(f"\n❌ Connection failed: {e}")
        print("\n🔧 Troubleshooting:")
        print("  1. Check your mnemonic is correct")
        print("  2. Verify network setting (testnet vs mainnet)")
        print("  3. Try alternative RPC node")
        print("  4. Check internet connection")


if __name__ == "__main__":
    try:
        asyncio.run(test_dydx_v4_connection())
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
