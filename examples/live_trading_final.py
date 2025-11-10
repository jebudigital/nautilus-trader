"""
Complete NautilusTrader Live Trading with Status Dashboard

Features:
- Real-time position monitoring
- P&L tracking
- Order status
- Console dashboard
"""

import asyncio
import os
from pathlib import Path
import sys
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
import aiohttp

from nautilus_trader.common.component import LiveClock, MessageBus, Logger
from nautilus_trader.cache.cache import Cache
from nautilus_trader.model.identifiers import TraderId
from nautilus_trader.portfolio.portfolio import Portfolio
from nautilus_trader.risk.engine import RiskEngine
from nautilus_trader.execution.engine import ExecutionEngine
from nautilus_trader.data.engine import DataEngine
from nautilus_trader.common.enums import LogLevel
from nautilus_trader.common import Environment
from nautilus_trader.trading.trader import Trader
from nautilus_trader.core.uuid import UUID4
import logging

from nautilus_trader.adapters.binance.factories import (
    BinanceLiveDataClientFactory,
    BinanceLiveExecClientFactory,
)
from nautilus_trader.adapters.binance.config import BinanceDataClientConfig, BinanceExecClientConfig

from src.crypto_trading_engine.adapters.dydx_v4_nautilus_adapter import create_dydx_v4_clients
from src.crypto_trading_engine.strategies.delta_neutral_nautilus import (
    DeltaNeutralStrategy,
    DeltaNeutralConfig,
)

load_dotenv()


class TradingDashboard:
    """Real-time trading dashboard"""
    
    def __init__(self, portfolio, cache):
        self.portfolio = portfolio
        self.cache = cache
        self.start_time = datetime.now()
    
    def display(self):
        """Display current status"""
        os.system('clear' if os.name == 'posix' else 'cls')
        
        print("="*80)
        print("🤖 NAUTILUS TRADER - LIVE DELTA NEUTRAL STRATEGY")
        print("="*80)
        
        # Runtime
        runtime = datetime.now() - self.start_time
        print(f"\n⏱️  Runtime: {runtime}")
        print(f"📅 Started: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Portfolio
        print(f"\n💰 Portfolio:")
        accounts = list(self.cache.accounts())
        if accounts:
            for account in accounts:
                print(f"   {account.id}:")
                try:
                    # Get balances for each currency
                    balances = account.balances()
                    if balances:
                        for currency, balance in balances.items():
                            if balance.total.as_double() > 0:
                                print(f"      {currency}: {balance.total.as_double():.8f}")
                except Exception as e:
                    print(f"      (Balance info unavailable)")
        else:
            print("   No accounts loaded yet")
        
        # Positions
        print(f"\n📊 Open Positions:")
        positions = list(self.cache.positions_open())
        if positions:
            for position in positions:
                side = "🟢 LONG" if position.is_long else "🔴 SHORT"
                print(f"   {side} {position.instrument_id}")
                print(f"      Size: {position.quantity}")
                print(f"      Entry: ${position.avg_px_open}")
                if position.unrealized_pnl():
                    pnl = position.unrealized_pnl().as_double()
                    pnl_emoji = "📈" if pnl >= 0 else "📉"
                    print(f"      {pnl_emoji} PnL: ${pnl:.2f}")
        else:
            print("   No open positions")
        
        # Orders
        print(f"\n📝 Recent Orders:")
        orders = list(self.cache.orders())[-5:]  # Last 5 orders
        if orders:
            for order in orders:
                status_emoji = {
                    'FILLED': '✅',
                    'ACCEPTED': '⏳',
                    'REJECTED': '❌',
                    'CANCELED': '🚫',
                }.get(str(order.status), '❓')
                print(f"   {status_emoji} {order.side} {order.quantity} @ {order.instrument_id}")
                print(f"      Status: {order.status}")
        else:
            print("   No orders yet")
        
        # Delta
        print(f"\n⚖️  Delta Exposure:")
        total_delta = 0.0
        for position in self.cache.positions_open():
            delta = position.quantity.as_double()
            if position.is_short:
                delta = -delta
            total_delta += delta
        
        delta_status = "✅ NEUTRAL" if abs(total_delta) < 0.01 else "⚠️  IMBALANCED"
        print(f"   Net Delta: {total_delta:.4f} BTC {delta_status}")
        
        print("\n" + "="*80)
        print("⏸️  Press Ctrl+C to stop")
        print("="*80)


class LiveTradingSystem:
    """Complete live trading system"""
    
    def __init__(self):
        self.loop = asyncio.get_event_loop()
        self.clock = LiveClock()
        self.trader_id = TraderId("TRADER-001")
        
        self.msgbus = None
        self.cache = None
        self.portfolio = None
        self.data_engine = None
        self.risk_engine = None
        self.exec_engine = None
        self.trader = None  # The Trader instance that wires everything together
        
        self.dydx_data_client = None
        self.dydx_exec_client = None
        self.binance_data_client = None
        self.binance_exec_client = None
        self.http_client = None
        
        self.strategy = None
        self.dashboard = None
        
        self.running = False
    
    async def initialize(self):
        """Initialize all components"""
        print("\n🚀 Initializing NautilusTrader...")
        
        # Setup proper logging with unbuffered file output
        from pathlib import Path
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / f"trading_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
        # Configure root logger
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        
        # File handler with detailed format (line buffered for real-time updates)
        # Open file in line-buffered mode
        log_file_handle = open(log_file, 'a', buffering=1)  # Line buffered
        file_handler = logging.StreamHandler(log_file_handle)
        file_handler.setLevel(logging.INFO)
        file_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        
        # Console handler with simpler format
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(asctime)s | %(message)s', datefmt='%H:%M:%S')
        console_handler.setFormatter(console_formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        # Redirect print to also log to file (with immediate flush)
        import sys
        class TeeOutput:
            def __init__(self, log_file_handle):
                self.terminal = sys.stdout
                self.log = log_file_handle
            def write(self, message):
                self.terminal.write(message)
                self.terminal.flush()
                self.log.write(message)
                self.log.flush()
            def flush(self):
                self.terminal.flush()
                self.log.flush()
        
        sys.stdout = TeeOutput(log_file_handle)
        
        # Set all loggers to INFO
        logging.getLogger().setLevel(logging.INFO)
        for name in ['nautilus_trader', 'DeltaNeutralStrategy', 'Strategy', 'Actor']:
            logging.getLogger(name).setLevel(logging.INFO)
        
        print(f"📝 Logging to {log_file}")
        
        # Load config
        dydx_network = os.getenv('DYDX__NETWORK', 'testnet')
        dydx_private_key = os.getenv('DYDX__PRIVATE_KEY', '')
        dydx_wallet_address = os.getenv('DYDX__WALLET_ADDRESS', '')
        dydx_account_number = os.getenv('DYDX__ACCOUNT_NUMBER', '0')
        
        binance_api_key = os.getenv('BINANCE__API_KEY', '')
        binance_api_secret = os.getenv('BINANCE__API_SECRET', '')
        binance_testnet = os.getenv('BINANCE__SANDBOX', 'false').lower() == 'true'
        
        # Safety check
        if dydx_network == 'mainnet' and not binance_testnet:
            print("\n⚠️  MAINNET MODE - REAL MONEY!")
            response = input("Type 'START' to proceed: ")
            if response != 'START':
                return False
        
        # Create components
        self.msgbus = MessageBus(trader_id=self.trader_id, clock=self.clock)
        self.cache = Cache(database=None)
        self.portfolio = Portfolio(msgbus=self.msgbus, cache=self.cache, clock=self.clock)
        self.data_engine = DataEngine(msgbus=self.msgbus, cache=self.cache, clock=self.clock)
        self.risk_engine = RiskEngine(portfolio=self.portfolio, msgbus=self.msgbus, cache=self.cache, clock=self.clock)
        self.exec_engine = ExecutionEngine(msgbus=self.msgbus, cache=self.cache, clock=self.clock)
        
        # Create HTTP client
        self.http_client = aiohttp.ClientSession()
        
        # Create Binance adapters
        print("   Creating Binance adapters...")
        binance_data_config = BinanceDataClientConfig(
            api_key=binance_api_key,
            api_secret=binance_api_secret,
            testnet=binance_testnet,
        )
        binance_exec_config = BinanceExecClientConfig(
            api_key=binance_api_key,
            api_secret=binance_api_secret,
            testnet=binance_testnet,
        )
        
        self.binance_data_client = BinanceLiveDataClientFactory.create(
            loop=self.loop,
            name="BINANCE",
            msgbus=self.msgbus,
            cache=self.cache,
            clock=self.clock,
            config=binance_data_config,
        )
        
        self.binance_exec_client = BinanceLiveExecClientFactory.create(
            loop=self.loop,
            name="BINANCE",
            msgbus=self.msgbus,
            cache=self.cache,
            clock=self.clock,
            config=binance_exec_config,
        )
        
        # Create dYdX adapters
        print("   Creating dYdX adapters...")
        self.dydx_data_client, self.dydx_exec_client = create_dydx_v4_clients(
            loop=self.loop,
            msgbus=self.msgbus,
            cache=self.cache,
            clock=self.clock,
            network=dydx_network,
            private_key=dydx_private_key,
            wallet_address=dydx_wallet_address,
            account_number=dydx_account_number,
        )
        
        # Register adapters
        print("   Registering data clients...")
        self.data_engine.register_client(self.binance_data_client)
        self.data_engine.register_client(self.dydx_data_client)
        print("   Registering execution clients...")
        self.exec_engine.register_client(self.binance_exec_client)
        print(f"     ✅ Registered Binance exec client: {self.binance_exec_client.id}")
        self.exec_engine.register_client(self.dydx_exec_client)
        print(f"     ✅ Registered dYdX exec client: {self.dydx_exec_client.id}")
        
        # Verify registration
        print(f"   Execution engine has {len(list(self.exec_engine.registered_clients))} clients")
        
        # Connect to exchanges
        print("   Connecting to Binance...")
        await self.binance_data_client._connect()
        await self.binance_exec_client._connect()
        
        print("   Connecting to dYdX...")
        await self.dydx_data_client._connect()
        await self.dydx_exec_client._connect()
        
        # Check if accounts are loaded
        print("   Checking accounts...")
        accounts = list(self.cache.accounts())
        print(f"   Loaded {len(accounts)} accounts")
        for account in accounts:
            print(f"     - {account.id}")
        
        # Load instruments explicitly
        print("   Loading instruments...")
        from nautilus_trader.model.identifiers import InstrumentId
        
        # Request dYdX perp instrument using internal method
        perp_id = InstrumentId.from_str("BTC-USD.DYDX_V4")
        await self.dydx_data_client._request_instrument(perp_id)
        
        # Binance instruments are loaded automatically when subscribing
        # We'll verify after subscription in the strategy
        
        # Wait a moment for instruments to load
        await asyncio.sleep(1)
        
        # Verify dYdX instrument loaded
        perp_instrument = self.cache.instrument(perp_id)
        
        print(f"   dYdX instrument loaded: {perp_instrument is not None}")
        
        if not perp_instrument:
            print("   ⚠️  Warning: dYdX instrument failed to load")
            print("   Available instruments:", list(self.cache.instruments()))
        
        # For Binance, we'll create a simple spot instrument if needed
        spot_id = InstrumentId.from_str("BTCUSDT.BINANCE")
        spot_instrument = self.cache.instrument(spot_id)
        
        if not spot_instrument:
            print("   Creating Binance spot instrument...")
            from nautilus_trader.model.instruments import CurrencyPair
            from nautilus_trader.model.identifiers import Symbol
            from nautilus_trader.model.objects import Price, Quantity, Currency
            from decimal import Decimal
            
            # Create a simple BTC/USDT spot instrument as CurrencyPair
            spot_instrument = CurrencyPair(
                instrument_id=spot_id,
                raw_symbol=Symbol("BTCUSDT"),
                base_currency=Currency.from_str("BTC"),
                quote_currency=Currency.from_str("USDT"),
                price_precision=2,
                size_precision=5,
                price_increment=Price.from_str("0.01"),
                size_increment=Quantity.from_str("0.00001"),
                max_quantity=Quantity.from_str("9000"),
                min_quantity=Quantity.from_str("0.00001"),
                max_price=Price.from_str("1000000"),
                min_price=Price.from_str("0.01"),
                margin_init=Decimal("1.0"),
                margin_maint=Decimal("1.0"),
                maker_fee=Decimal("0.001"),
                taker_fee=Decimal("0.001"),
                ts_event=self.clock.timestamp_ns(),
                ts_init=self.clock.timestamp_ns(),
            )
            self.cache.add_instrument(spot_instrument)
            print("   ✅ Binance spot instrument created")
        else:
            print(f"   Binance instrument loaded: {spot_instrument is not None}")
        
        # Accounts will be loaded automatically by adapters
        
        # Create strategy
        strategy_config = DeltaNeutralConfig(
            spot_instrument="BTCUSDT.BINANCE",
            perp_instrument="BTC-USD.DYDX_V4",
            max_position_size_usd=30.0,
            max_total_exposure_usd=120.0,
            rebalance_threshold_pct=5.0,
            min_funding_rate_apy=1.0,  # Lowered to 0.1% APY to trade now
            max_leverage=2.0,
            emergency_exit_loss_pct=10.0,
        )
        
        # Create Trader instance to wire everything together
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
        self.strategy = DeltaNeutralStrategy(config=strategy_config)
        
        # Force strategy to use Python logging
        import sys
        strategy_logger = logging.getLogger('DeltaNeutralStrategy')
        strategy_logger.setLevel(logging.INFO)
        
        # Add strategy to trader (this properly wires it to exec engine)
        self.trader.add_strategy(self.strategy)
        
        logging.info(f"Strategy added to trader: {self.strategy}")
        
        # Create dashboard
        self.dashboard = TradingDashboard(self.portfolio, self.cache)
        
        print("✅ System initialized\n")
        return True
    
    async def start(self):
        """Start trading"""
        logging.info("Starting engines...")
        self.data_engine.start()
        logging.info("  Data engine started")
        self.risk_engine.start()
        logging.info("  Risk engine started")
        self.exec_engine.start()
        logging.info("  Exec engine started")
        
        logging.info("Starting strategy...")
        self.strategy.start()
        logging.info("  Strategy started")
        
        self.running = True
        logging.info("System is now running")
    
    async def run(self):
        """Main loop"""
        print("\n✅ LIVE TRADING ACTIVE - Monitoring...")
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
        
        if self.binance_data_client:
            await self.binance_data_client._disconnect()
        if self.binance_exec_client:
            await self.binance_exec_client._disconnect()
        if self.dydx_data_client:
            await self.dydx_data_client._disconnect()
        if self.dydx_exec_client:
            await self.dydx_exec_client._disconnect()
        if self.http_client:
            await self.http_client.close()
        
        print("\n✅ Shutdown complete")
        
        # Restore stdout and close log file
        import sys
        if hasattr(sys.stdout, 'log'):
            sys.stdout.log.close()


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
