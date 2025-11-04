"""
Simple script to run your crypto trading engine with live data.

Just update your .env file with real credentials and run this script.
"""

import asyncio
import os
import sys
sys.path.append('.')

from src.crypto_trading_engine.config.settings import load_config
from src.crypto_trading_engine.adapters.binance_adapter import BinanceAdapter
from src.crypto_trading_engine.adapters.uniswap_adapter import UniswapAdapter
from src.crypto_trading_engine.models.trading_mode import TradingMode


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
    except Exception as e:
        print(f"❌ Error loading .env: {e}")


async def main():
    """Run live trading with your existing engine."""
    import logging
    import os
    
    # Load environment variables from .env file
    load_env_file()
    
    # Setup logging to see what's happening
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),  # Console output
            logging.FileHandler('trading_engine.log')  # File output
        ]
    )
    
    logger = logging.getLogger(__name__)
    
    print("🚀 Starting Crypto Trading Engine - Live Mode")
    print("=" * 60)
    
    # Load configuration from .env file
    config = load_config(environment="dev")  # Using dev since that's what your .env shows
    
    print(f"📊 Environment: {config.environment}")
    print(f"👤 Trader ID: {config.trader_id}")
    print(f"📝 Logs will be written to: trading_engine.log")
    
    # Check if credentials are loaded
    binance_key = os.getenv('BINANCE__API_KEY')
    infura_url = os.getenv('WEB3__PROVIDER_URL')
    
    print(f"\n🔑 Credentials Check:")
    print(f"   Binance API Key: {'✅ Found' if binance_key else '❌ Missing'}")
    print(f"   Infura URL: {'✅ Found' if infura_url else '❌ Missing'}")
    
    # Initialize adapters with live credentials
    try:
        adapters = []
        
        # Binance adapter
        if binance_key:
            print("\n💰 Initializing Binance...")
            logger.info("Connecting to Binance...")
            
            binance_adapter = BinanceAdapter(
                config={
                    'api_key': binance_key,
                    'api_secret': os.getenv('BINANCE__API_SECRET'),
                    'testnet': os.getenv('BINANCE__SANDBOX', 'true').lower() == 'true'
                },
                trading_mode=TradingMode.LIVE
            )
            
            await binance_adapter.connect()
            adapters.append(binance_adapter)
            print("✅ Binance connected")
            logger.info("Binance adapter connected successfully")
        else:
            print("⚠️  Skipping Binance - no API key found")
        
        # Uniswap adapter  
        if infura_url:
            print("\n⛓️  Initializing Uniswap...")
            logger.info("Connecting to Uniswap via Infura...")
            
            uniswap_adapter = UniswapAdapter(
                config={
                    'web3_provider_url': infura_url,
                    'private_key': os.getenv('WEB3__PRIVATE_KEY'),
                    'gas_limit': int(os.getenv('WEB3__GAS_LIMIT', '500000'))
                },
                trading_mode=TradingMode.LIVE
            )
            
            await uniswap_adapter.connect()
            adapters.append(uniswap_adapter)
            print("✅ Uniswap connected")
            logger.info("Uniswap adapter connected successfully")
        else:
            print("⚠️  Skipping Uniswap - no Infura URL found")
        
        if adapters:
            print(f"\n🎯 {len(adapters)} adapter(s) connected - Ready for live trading!")
            print("\n📋 Monitor activity:")
            print("   • Console: Real-time status updates")
            print("   • File: tail -f trading_engine.log")
            print("   • Detailed logs: Check trading_engine.log")
            
            # Simulate some activity to show logging
            logger.info("Trading engine started successfully")
            logger.info(f"Active adapters: {[type(a).__name__ for a in adapters]}")
            
            # Keep running and log periodic status
            print("\n⏸️  Press Ctrl+C to stop...")
            try:
                counter = 0
                while True:
                    await asyncio.sleep(10)  # Log every 10 seconds
                    counter += 1
                    logger.info(f"System running - heartbeat #{counter}")
                    print(f"💓 Heartbeat #{counter} - Check trading_engine.log for details")
            except KeyboardInterrupt:
                print("\n⏹️  Shutting down...")
                logger.info("Trading engine shutdown requested")
        else:
            print("\n❌ No adapters connected - check your .env configuration")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        logger.error(f"Trading engine error: {e}", exc_info=True)
        print("\n🔧 Check your .env file configuration:")
        print("   • BINANCE__API_KEY and BINANCE__API_SECRET")
        print("   • WEB3__PROVIDER_URL (your Infura URL)")
        print("   • WEB3__PRIVATE_KEY (for transactions)")


if __name__ == "__main__":
    asyncio.run(main())