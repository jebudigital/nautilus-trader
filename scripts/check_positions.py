"""Check current positions on both exchanges"""
import os
import sys
from pathlib import Path
import asyncio
import aiohttp
import hmac
import hashlib
import time

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

load_dotenv()

async def check_binance_positions():
    """Check Binance spot holdings"""
    api_key = os.getenv('BINANCE__API_KEY', '')
    api_secret = os.getenv('BINANCE__API_SECRET', '')
    base_url = "https://api.binance.com"
    
    print("\n📊 Binance Spot Holdings:")
    
    try:
        timestamp = int(time.time() * 1000)
        query_string = f"timestamp={timestamp}"
        signature = hmac.new(
            api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        url = f"{base_url}/api/v3/account?{query_string}&signature={signature}"
        headers = {'X-MBX-APIKEY': api_key}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    balances = [b for b in data['balances'] if float(b['free']) > 0 or float(b['locked']) > 0]
                    
                    # Get BTC price for USD value
                    async with session.get(f"{base_url}/api/v3/ticker/price?symbol=BTCUSDT") as price_resp:
                        price_data = await price_resp.json()
                        btc_price = float(price_data['price'])
                    
                    total_usd = 0
                    for balance in balances:
                        asset = balance['asset']
                        free = float(balance['free'])
                        locked = float(balance['locked'])
                        total = free + locked
                        
                        # Calculate USD value
                        if asset == 'BTC':
                            usd_value = total * btc_price
                            print(f"   💰 {asset}: {total:.8f} (${usd_value:.2f})")
                            total_usd += usd_value
                        elif asset in ['USDT', 'USDC', 'BUSD']:
                            print(f"   💵 {asset}: {total:.2f}")
                            total_usd += total
                        elif total > 0:
                            print(f"   💎 {asset}: {total:.8f}")
                    
                    print(f"\n   📈 Total Value: ~${total_usd:.2f}")
                else:
                    print(f"   ❌ Error: {response.status}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

async def check_dydx_positions():
    """Check dYdX perpetual positions"""
    network = os.getenv('DYDX__NETWORK', 'testnet')
    wallet_address = os.getenv('DYDX__WALLET_ADDRESS', '')
    
    if network == 'mainnet':
        base_url = "https://indexer.dydx.trade"
    else:
        base_url = "https://indexer.v4testnet.dydx.exchange"
    
    print("\n📊 dYdX Perpetual Positions:")
    
    try:
        async with aiohttp.ClientSession() as session:
            # Get account info
            async with session.get(f"{base_url}/v4/addresses/{wallet_address}") as response:
                if response.status == 200:
                    data = await response.json()
                    subaccounts = data.get('subaccounts', [])
                    
                    if not subaccounts:
                        print("   ⚠️  No positions found")
                        return
                    
                    for sub in subaccounts:
                        subaccount_num = sub.get('subaccountNumber', 0)
                        equity = float(sub.get('equity', 0))
                        free_collateral = float(sub.get('freeCollateral', 0))
                        
                        print(f"\n   💼 Subaccount {subaccount_num}:")
                        print(f"      Equity: ${equity:.2f}")
                        print(f"      Free Collateral: ${free_collateral:.2f}")
                        
                        # Get open positions
                        open_positions = sub.get('openPerpetualPositions', {})
                        
                        if open_positions:
                            print(f"\n      📈 Open Positions:")
                            for market, position in open_positions.items():
                                side = position.get('side', 'UNKNOWN')
                                size = float(position.get('size', 0))
                                entry_price = float(position.get('entryPrice', 0))
                                unrealized_pnl = float(position.get('unrealizedPnl', 0))
                                
                                notional = abs(size * entry_price)
                                
                                side_emoji = "🟢" if side == "LONG" else "🔴"
                                pnl_emoji = "📈" if unrealized_pnl >= 0 else "📉"
                                
                                print(f"         {side_emoji} {market}: {side}")
                                print(f"            Size: {size}")
                                print(f"            Entry: ${entry_price:.2f}")
                                print(f"            Notional: ${notional:.2f}")
                                print(f"            {pnl_emoji} PnL: ${unrealized_pnl:.2f}")
                        else:
                            print(f"      ⚠️  No open positions")
                        
                elif response.status == 404:
                    print("   ⚠️  Account not found")
                else:
                    print(f"   ❌ Error: {response.status}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

async def calculate_delta():
    """Calculate net delta exposure"""
    print("\n" + "="*60)
    print("📊 DELTA ANALYSIS")
    print("="*60)
    
    # This is a simplified calculation
    # In reality, you'd need to fetch actual positions and calculate
    
    print("\n💡 Delta Neutral Check:")
    print("   - Long BTC spot on Binance")
    print("   - Short BTC perp on dYdX")
    print("   - Net delta should be close to 0")
    print("\n   If positions are balanced, you're earning funding rates!")

async def main():
    print("\n" + "="*60)
    print("📊 POSITION CHECK")
    print("="*60)
    
    await check_binance_positions()
    await check_dydx_positions()
    await calculate_delta()
    
    print("\n" + "="*60)

if __name__ == "__main__":
    asyncio.run(main())
