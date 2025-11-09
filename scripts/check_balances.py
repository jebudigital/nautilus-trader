"""
Check Testnet Balances

Quick script to check if testnet funds have arrived.
"""

import asyncio
import aiohttp
import os
from pathlib import Path
import sys
from dotenv import load_dotenv

# Add project root
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from eth_account import Account


async def check_balances():
    """Check balances on both exchanges."""
    
    load_dotenv()
    
    network = os.getenv('DYDX__NETWORK', 'testnet')
    private_key = os.getenv('DYDX__PRIVATE_KEY', '')
    binance_key = os.getenv('BINANCE__API_KEY', '')
    binance_secret = os.getenv('BINANCE__API_SECRET', '')
    binance_testnet = os.getenv('BINANCE__SANDBOX', 'true').lower() == 'true'
    
    print("\n" + "="*60)
    print("💰 Testnet Balance Check")
    print("="*60)
    
    # Check dYdX
    if private_key:
        print("\n📊 dYdX Testnet:")
        try:
            if private_key.startswith('0x'):
                private_key = private_key[2:]
            account = Account.from_key(private_key)
            
            if network == "testnet":
                api_base = "https://indexer.v4testnet.dydx.exchange"
            else:
                api_base = "https://indexer.dydx.trade"
            
            async with aiohttp.ClientSession() as client:
                async with client.get(
                    f"{api_base}/v4/addresses/{account.address}",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        subaccounts = data.get('subaccounts', [])
                        
                        if subaccounts:
                            for i, sub in enumerate(subaccounts):
                                equity = float(sub.get('equity', '0'))
                                free = float(sub.get('freeCollateral', '0'))
                                print(f"   Subaccount {i}:")
                                print(f"   💵 Total: ${equity:,.2f}")
                                print(f"   💵 Free:  ${free:,.2f}")
                                
                                if equity > 0:
                                    print(f"   ✅ Funded!")
                                else:
                                    print(f"   ⚠️  No funds yet")
                        else:
                            print(f"   ⚠️  No account found")
                            print(f"   Go to: https://v4.testnet.dydx.exchange")
                            print(f"   Connect wallet: {account.address}")
                    else:
                        print(f"   ⚠️  Account not found (status: {response.status})")
                        print(f"   Connect wallet to dYdX testnet first")
                        
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    # Check Binance
    if binance_key and binance_secret:
        print("\n📊 Binance Testnet:")
        try:
            import hmac
            import hashlib
            import time
            
            if binance_testnet:
                base_url = "https://testnet.binance.vision"
            else:
                base_url = "https://api.binance.com"
            
            timestamp = int(time.time() * 1000)
            query_string = f"timestamp={timestamp}"
            signature = hmac.new(
                binance_secret.encode('utf-8'),
                query_string.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            url = f"{base_url}/api/v3/account?{query_string}&signature={signature}"
            headers = {"X-MBX-APIKEY": binance_key}
            
            async with aiohttp.ClientSession() as client:
                async with client.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        balances = data.get('balances', [])
                        
                        # Show non-zero balances
                        has_funds = False
                        for bal in balances:
                            free = float(bal.get('free', 0))
                            locked = float(bal.get('locked', 0))
                            total = free + locked
                            
                            if total > 0:
                                asset = bal.get('asset')
                                print(f"   💵 {asset}: {total:.8f} (free: {free:.8f})")
                                has_funds = True
                        
                        if has_funds:
                            print(f"   ✅ Funded!")
                        else:
                            print(f"   ⚠️  No funds yet")
                            print(f"   Go to: https://testnet.binance.vision")
                            print(f"   Request testnet BTC and USDT")
                    else:
                        error_text = await response.text()
                        print(f"   ❌ Error: {response.status}")
                        print(f"   {error_text}")
                        
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    print("\n" + "="*60)
    print("\n💡 TIP: Run this script again after requesting funds")
    print("   python3 scripts/check_balances.py")
    print("\n" + "="*60)


if __name__ == "__main__":
    asyncio.run(check_balances())
