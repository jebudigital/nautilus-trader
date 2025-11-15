"""
Live Trading: Hyperliquid + 0x Delta Neutral Strategy (Arbitrum L2)

This script runs the delta neutral strategy live using:
- 0x Protocol for spot trading (Arbitrum)
- Hyperliquid for perpetuals
"""

import asyncio
import os
from pathlib import Path
import sys
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
import logging

from nautilus_trader.common.component import LiveClock
from nautilus_trader.cache.cache import Cache
from nautilus_trader.model.identifiers import TraderId, AccountId
from nautilus_trader.portfolio.portfolio import Portfolio
from nautilus_trader.risk.engine import RiskEngine
from nautilus_trader.execution.engine import ExecutionEngine
from nautilus_trader.data.engine import DataEngine
from nautilus_trader.common import Environment
from nautilus_trader.trading.trader import Trader
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.msgbus.bus import MessageBus

from src.crypto_trading_engine.adapters.hyperliquid_adapter import (
    HyperliquidHttpClient,
    HyperliquidDataClient,
    HyperliquidExecutionClient,
    VENUE as HYPERLIQUID_VENUE,
)
from src.crypto_trading_engine.adapters.zerox_adapter import (
    ZeroXHttpClient,
    ZeroXDataClient,
    ZeroXExecutionClient,
    VENUE as ZEROX_VENUE,
)
from src.crypto_trading_engine.strategies.hyperliquid_zerox_delta_neutral import (
    HyperliquidZeroXStrategy,
    HyperliquidZeroXConfig,
)

load_dotenv()


class LiveTradingSystem:
    """Live trading system for Hyperliquid + 0x on Arbitrum"""
    
    def __init__(self):
        self.loop = asyncio.get_event_loop()
        self.clock = LiveClock()
        self.trader_id = TraderId("TRADER-001")
        
        # Core components
        self.msgbus = None
        self.cache = None
        self.portfolio = None
        self.data_engine = None
        self.risk_engine = None
        self.exec_engine = None
        self.trader = None
        
        # Adapters
        self.hyperliquid_http = None
        self.hyperliquid_data = None
        self.hyperliquid_exec = None
        
        self.zerox_http = None
        self.zerox_data = None
        self.zerox_exec = None
        
        # Strategy
        self.strategy = None
        
        self.running = False
    
    async def initialize(self):
        """Initialize all components"""
        print("\n🚀 Initializing Hyperliquid + 0x Trading System (Arbitrum L2)...")
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Load config
        arbitrum_rpc = os.getenv('ARBITRUM__RPC_URL', 'https://arb1.arbitrum.io/rpc')
        arbitrum_private_key = os.getenv('ARBITRUM__PRIVATE_KEY', '')
        arbitrum_wallet = os.getenv('ARBITRUM__WALLET_ADDRESS', '')
        
        hyperliquid_testnet = os.getenv('HYPERLIQUID__TESTNET', 'true').lower() == 'true'
        
        # Safety check
        if not hyperliquid_testnet:
            print("\n⚠️  MAINNET MODE - REAL MONEY!")
            response = input("Type 'START' to proceed: ")
            if response != 'START':
                return False
        
        # Create core components
        self.msgbus = MessageBus(trader_id=self.trader_id, clock=self.clock)
        self.cache = Cache(database=None)
        self.portfolio = Portfolio(msgbus=self.msgbus, cache=self.cache, clock=self.clock)
        self.data_engine = DataEngine(msgbus=self.msgbus, cache=self.cache, clock=self.clock)
        self.risk_engine = RiskEngine(portfolio=self.portfolio, msgbus=self.msgbus, cache=self.cache, clock=self.clock)
        self.exec_engine = ExecutionEngine(msgbus=self.msgbus, cache=self.cache, clock=self.clock)
        
        # Create Hyperliquid adapters
        print("   Creating Hyperliquid adapters...")
        self.hyperliquid_http = HyperliquidHttpClient(
            private_key=arbitrum_private_key,
            wallet_address=arbitrum_wallet,
            testnet=hyperliquid_testnet,
        )
        
        from nautilus_trader.common.component import Logger
        logger = Logger(clock=self.clock)
        
        self.hyperliquid_data = HyperliquidDataClient(
            loop=self.loop,
            client=self.hyperliquid_http,
            msgbus=self.msgbus,
            cache=self.cache,
            clock=self.clock,
            logger=logger,
        )
        
        self.hyperliquid_exec = HyperliquidExecutionClient(
            loop=self.loop,
            client=self.hyperliquid_http,
            msgbus=self.msgbus,
            cache=self.cache,
            clock=self.clock,
            logger=logger,
            account_id=AccountId(f"{HYPERLIQUID_VENUE}-001"),
        )
        
        # Create 0x adapters
        print("   Creating 0x adapters (Arbitrum)...")
        self.zerox_http = ZeroXHttpClient(
            rpc_url=arbitrum_rpc,
            private_key=arbitrum_private_key,
            wallet_address=arbitrum_wallet,
        )
        
        self.zerox_data = ZeroXDataClient(
            loop=self.loop,
            client=self.zerox_http,
            msgbus=self.msgbus,
            cache=self.cache,
            clock=self.clock,
            logger=logger,
        )
        
        self.zerox_exec = ZeroXExecutionClient(
            loop=self.loop,
            client=self.zerox_http,
            msgbus=self.msgbus,
            cache=self.cache,
            clock=self.clock,
            logger=logger,
            account_id=AccountId(f"{ZEROX_VENUE}-001"),
        )
        
        # Register adapters
        print("   Registering adapters...")
        self.data_engine.register_client(self.hyperliquid_data)
        self.data_engine.register_client(self.zerox_data)
        self.exec_engine.register_client(self.hyperliquid_exec)
        self.exec_engine.register_client(self.zerox_exec)
        
        # Connect to exchanges
        print("   Connecting to Hyperliquid...")
        await self.hyperliquid_data._connect()
        await self.hyperliquid_exec._connect()
        
        print("   Connecting to 0x (Arbitrum)...")
        await self.zerox_data._connect()
        await self.zerox_exec._connect()
        
        # Create Trader
        print("   Creating Trader...")
        self.trader = Trader(
            trader_id=self.trader_id,
            instance_id=UUID4(),
            msgbus=self.msgbus,
            cache=self.cache,
            portfolio=self.portfolio,
            data_engine=self.data_engine,
            risk_engine=self.risk_engine,
            exec_engine=self.exec_engine,
            clock=self.clock,
            environment=Environment.LIVE,
            loop=self.loop,
        )
        
        # Create strategy
        print("   Creating strategy...")
        strategy_config = HyperliquidZeroXConfig(
            spot_instrument="WETHUSDC.ZEROX",
            perp_instrument="ETH-PERP.HYPERLIQUID",
            max_position_size_usd=1000.0,
            rebalance_threshold_pct=5.0,
            min_funding_rate_apy=5.0,
        )
        
        self.strategy = HyperliquidZeroXStrategy(config=strategy_config)
        self.trader.add_strategy(self.strategy)
        
        print("✅ System initialized\n")
        return True
    
    async def start(self):
        """Start trading"""
        logging.info("Starting engines...")
        self.data_engine.start()
        self.risk_engine.start()
        self.exec_engine.start()
        
        logging.info("Starting strategy...")
        self.strategy.start()
        
        self.running = True
        logging.info("System is now running")
    
    async def run(self):
        """Main loop"""
        print("\n✅ LIVE TRADING ACTIVE (Arbitrum L2)")
        print("⏸️  Press Ctrl+C to stop\n")
        
        try:
            while self.running:
                await asyncio.sleep(60)
        except KeyboardInterrupt:
            print("\n\n⏹️  Stopping...")
            await self.stop()
    
    async def stop(self):
        """Stop system"""
        self.running = False
        
        if self.strategy:
            self.strategy.stop()
        if self.exec_engine:
            self.exec_engine.stop()
        if self.risk_engine:
            self.risk_engine.stop()
        if self.data_engine:
            self.data_engine.stop()
        
        if self.hyperliquid_data:
            await self.hyperliquid_data._disconnect()
        if self.hyperliquid_exec:
            await self.hyperliquid_exec._disconnect()
        if self.zerox_data:
            await self.zerox_data._disconnect()
        if self.zerox_exec:
            await self.zerox_exec._disconnect()
        
        print("\n✅ Shutdown complete")


async def main():
    system = LiveTradingSystem()
    
    try:
        if await system.initialize():
            await system.start()
            await system.run()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await system.stop()


if __name__ == "__main__":
    asyncio.run(main())
