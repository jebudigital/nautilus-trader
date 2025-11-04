"""
Simple test to verify your credentials are working.
No extra dependencies needed.
"""

import os
import sys
sys.path.append('.')


def load_env_file():
    """Manually load .env file."""
    try:
        with open('.env', 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value
        print("✅ .env file loaded")
    except FileNotFoundError:
        print("❌ .env file not found")
    except Exception as e:
        print(f"❌ Error loading .env: {e}")


def main():
    """Test credential loading."""
    print("🔧 Testing Credential Loading")
    print("=" * 40)
    
    # Load .env file manually
    load_env_file()
    
    # Check credentials
    print("\n🔑 Checking Credentials:")
    
    # Binance
    binance_key = os.getenv('BINANCE__API_KEY')
    binance_secret = os.getenv('BINANCE__API_SECRET')
    binance_testnet = os.getenv('BINANCE__SANDBOX')
    
    print(f"   Binance API Key: {'✅ Found' if binance_key else '❌ Missing'}")
    if binance_key:
        print(f"      Key: {binance_key[:8]}...{binance_key[-8:]}")
    print(f"   Binance Secret: {'✅ Found' if binance_secret else '❌ Missing'}")
    print(f"   Binance Testnet: {binance_testnet}")
    
    # Infura
    infura_url = os.getenv('WEB3__PROVIDER_URL')
    private_key = os.getenv('WEB3__PRIVATE_KEY')
    
    print(f"   Infura URL: {'✅ Found' if infura_url else '❌ Missing'}")
    if infura_url:
        print(f"      URL: {infura_url}")
    print(f"   Private Key: {'✅ Found' if private_key else '❌ Missing (OK for read-only)'}")
    
    # Test connections
    print("\n🌐 Testing Connections:")
    
    # Test Binance
    if binance_key and binance_secret:
        try:
            import requests
            
            # Simple Binance API test
            url = "https://testnet.binance.vision/api/v3/ping" if binance_testnet == 'true' else "https://api.binance.com/api/v3/ping"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                print("   ✅ Binance API reachable")
            else:
                print(f"   ❌ Binance API error: {response.status_code}")
                
        except Exception as e:
            print(f"   ⚠️  Binance test failed: {e}")
    
    # Test Infura
    if infura_url:
        try:
            import requests
            
            # Simple Infura test
            payload = {
                "jsonrpc": "2.0",
                "method": "eth_blockNumber",
                "params": [],
                "id": 1
            }
            
            response = requests.post(infura_url, json=payload, timeout=5)
            
            if response.status_code == 200:
                result = response.json()
                if 'result' in result:
                    block_number = int(result['result'], 16)
                    print(f"   ✅ Infura connected - Latest block: {block_number:,}")
                else:
                    print(f"   ❌ Infura error: {result}")
            else:
                print(f"   ❌ Infura HTTP error: {response.status_code}")
                
        except Exception as e:
            print(f"   ⚠️  Infura test failed: {e}")
    
    print("\n🎯 Summary:")
    if binance_key and infura_url:
        print("   ✅ Ready for live trading!")
        print("   📝 Run: python3 examples/run_live_trading.py")
    else:
        print("   ⚠️  Missing credentials - update your .env file")
        print("   📋 Need:")
        if not binance_key:
            print("      • BINANCE__API_KEY")
            print("      • BINANCE__API_SECRET")
        if not infura_url:
            print("      • WEB3__PROVIDER_URL")


if __name__ == "__main__":
    main()