"""
Check if a Binance order was actually executed.
"""

import asyncio
import os
import hmac
import hashlib
import time
from dotenv import load_dotenv
import aiohttp

load_dotenv()


async def check_recent_orders():
    """Check recent orders on Binance."""
    
    api_key = os.getenv('BINANCE__API_KEY', '')
    api_secret = os.getenv('BINANCE__API_SECRET', '')
    base_url = "https://api.binance.com"
    
    print("\n🔍 Checking Recent Binance Orders")
    print("="*60)
    
    async with aiohttp.ClientSession() as session:
        # Get recent trades
        timestamp = int(time.time() * 1000)
        query_string = f"symbol=BTCUSDT&timestamp={timestamp}"
        
        signature = hmac.new(
            api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        headers = {'X-MBX-APIKEY': api_key}
        url = f"{base_url}/api/v3/myTrades?{query_string}&signature={signature}"
        
        print("\n1. Recent trades:")
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                trades = await response.json()
                if trades:
                    print(f"   Found {len(trades)} recent trades")
                    for trade in trades[-5:]:  # Last 5
                        print(f"\n   Trade ID: {trade['id']}")
                        print(f"   Time: {trade['time']}")
                        print(f"   Side: {'BUY' if trade['isBuyer'] else 'SELL'}")
                        print(f"   Quantity: {trade['qty']} BTC")
                        print(f"   Price: ${float(trade['price']):,.2f}")
                        print(f"   Total: ${float(trade['quoteQty']):,.2f}")
                else:
                    print("   No recent trades found")
            else:
                print(f"   ❌ Failed: {response.status}")
                print(await response.text())
        
        # Get all open orders
        print("\n2. Open orders:")
        query_string = f"symbol=BTCUSDT&timestamp={timestamp}"
        signature = hmac.new(
            api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        url = f"{base_url}/api/v3/openOrders?{query_string}&signature={signature}"
        
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                orders = await response.json()
                if orders:
                    print(f"   Found {len(orders)} open orders")
                    for order in orders:
                        print(f"\n   Order ID: {order['orderId']}")
                        print(f"   Client Order ID: {order['clientOrderId']}")
                        print(f"   Side: {order['side']}")
                        print(f"   Quantity: {order['origQty']}")
                        print(f"   Status: {order['status']}")
                else:
                    print("   No open orders")
            else:
                print(f"   ❌ Failed: {response.status}")
    
    print("\n" + "="*60)


if __name__ == "__main__":
    asyncio.run(check_recent_orders())
