"""
Unit tests for core interfaces and base classes.
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any

from nautilus_trader.model.identifiers import StrategyId, Venue, ClientOrderId, PositionId, InstrumentId
from nautilus_trader.model.objects import Money, Price, Quantity, Currency
from nautilus_trader.model.enums import OrderSide, OrderType, TimeInForce, PositionSide
from nautilus_trader.model.data import QuoteTick

from crypto_trading_engine.models import TradingMode, BacktestResults, Instrument, Position, Order
from crypto_trading_engine.core import Strategy, ExchangeAdapter, TradingModeManager, RiskManager
from crypto_trading_engine.core.risk_manager import RiskLevel, RiskAlert, RiskAssessment


# Test implementations of abstract classes

class MockStrategy(Strategy):
    """Test implementation of Strategy."""
    
    def __init__(self, strategy_id: StrategyId, config: Dict[str, Any], trading_mode: TradingMode = TradingMode.BACKTEST):
        super().__init__(strategy_id, config, trading_mode)
        self.started = False
        self.stopped = False
        self.market_data_received = []
        self.orders_filled = []
        self.positions_opened = []
        self.positions_closed = []
    
    def on_start(self) -> None:
        self.started = True
    
    def on_stop(self) -> None:
        self.stopped = True
    
    def on_market_data(self, data: QuoteTick) -> None:
        self.market_data_received.append(data)
    
    def on_order_filled(self, order: Order, fill_price: float, fill_quantity: float) -> None:
        self.orders_filled.append((order, fill_price, fill_quantity))
    
    def on_position_opened(self, position: Position) -> None:
        self.positions_opened.append(position)
    
    def on_position_closed(self, position: Position) -> None:
        self.positions_closed.append(position)


class MockExchangeAdapter(ExchangeAdapter):
    """Test implementation of ExchangeAdapter."""
    
    def __init__(self, venue: Venue, config: Dict[str, Any], trading_mode: TradingMode = TradingMode.BACKTEST):
        super().__init__(venue, config, trading_mode)
        self.connect_called = False
        self.disconnect_called = False
        self.submitted_orders = []
        self.cancelled_orders = []
    
    async def connect(self) -> bool:
        self.connect_called = True
        self.is_connected = True
        return True
    
    async def disconnect(self) -> None:
        self.disconnect_called = True
        self.is_connected = False
    
    async def submit_order(self, order: Order) -> bool:
        self.submitted_orders.append(order)
        return True
    
    async def cancel_order(self, order_id: str) -> bool:
        self.cancelled_orders.append(order_id)
        return True
    
    async def get_order_status(self, order_id: str) -> Dict[str, Any]:
        return {"order_id": order_id, "status": "filled"}
    
    async def get_positions(self) -> list:
        return list(self.positions.values())
    
    async def get_balance(self) -> Dict[str, Money]:
        usd = Currency.from_str('USD')
        return {"USD": Money(10000, usd)}
    
    async def get_instruments(self) -> list:
        return list(self.instruments.values())
    
    async def subscribe_market_data(self, instrument_ids: list) -> bool:
        return True
    
    async def unsubscribe_market_data(self, instrument_ids: list) -> bool:
        return True


class MockRiskManager(RiskManager):
    """Test implementation of RiskManager."""
    
    def __init__(self, config: Dict[str, Any], trading_mode: TradingMode = TradingMode.BACKTEST):
        super().__init__(config, trading_mode)
        self.position_checks = []
        self.order_checks = []
        self.portfolio_checks = []
    
    def check_position_risk(self, position: Position) -> RiskAssessment:
        self.position_checks.append(position)
        return RiskAssessment(True, RiskLevel.LOW, "Position risk acceptable")
    
    def check_order_risk(self, order: Order) -> RiskAssessment:
        self.order_checks.append(order)
        return RiskAssessment(True, RiskLevel.LOW, "Order risk acceptable")
    
    def check_portfolio_risk(self) -> RiskAssessment:
        self.portfolio_checks.append(datetime.now())
        return RiskAssessment(True, RiskLevel.LOW, "Portfolio risk acceptable")
    
    def calculate_var(self, confidence: float = 0.95, horizon_days: int = 1) -> Money:
        usd = Currency.from_str('USD')
        return Money(100, usd)
    
    def calculate_position_size(
        self, 
        instrument: Instrument, 
        risk_amount: Money,
        entry_price: Decimal,
        stop_loss_price: Decimal
    ) -> Decimal:
        return Decimal('1.0')


class TestStrategy:
    """Test Strategy base class."""
    
    def test_strategy_initialization(self):
        """Test strategy initialization."""
        strategy_id = StrategyId("test-strategy")
        config = {"param1": "value1"}
        
        strategy = MockStrategy(strategy_id, config)
        
        assert strategy.strategy_id == strategy_id
        assert strategy.config == config
        assert strategy.trading_mode == TradingMode.BACKTEST
        assert not strategy.is_running
        assert len(strategy.positions) == 0
        assert len(strategy.orders) == 0
        assert len(strategy.instruments) == 0
    
    def test_strategy_lifecycle(self):
        """Test strategy start/stop lifecycle."""
        strategy_id = StrategyId("test-strategy")
        strategy = MockStrategy(strategy_id, {})
        
        # Test start
        strategy.start()
        assert strategy.is_running
        assert strategy.started
        
        # Test stop
        strategy.stop()
        assert not strategy.is_running
        assert strategy.stopped
    
    def test_trading_mode_change(self):
        """Test trading mode changes."""
        strategy_id = StrategyId("test-strategy")
        strategy = MockStrategy(strategy_id, {})
        
        # Change mode when not running
        strategy.set_trading_mode(TradingMode.PAPER)
        assert strategy.trading_mode == TradingMode.PAPER
        
        # Cannot change mode when running
        strategy.start()
        with pytest.raises(RuntimeError, match="Cannot change trading mode while strategy is running"):
            strategy.set_trading_mode(TradingMode.LIVE)
    
    def test_instrument_management(self):
        """Test instrument management."""
        strategy_id = StrategyId("test-strategy")
        strategy = MockStrategy(strategy_id, {})
        
        venue = Venue("BINANCE")
        instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
        
        instrument = Instrument(
            id=instrument_id,
            symbol="BTCUSDT",
            base_currency="BTC",
            quote_currency="USDT",
            price_precision=2,
            size_precision=6,
            min_quantity=Decimal('0.001'),
            max_quantity=Decimal('1000'),
            tick_size=Decimal('0.01'),
            venue=venue
        )
        
        # Add instrument
        strategy.add_instrument(instrument)
        assert len(strategy.instruments) == 1
        assert strategy.get_instrument(str(instrument_id)) == instrument
        
        # Get non-existent instrument
        assert strategy.get_instrument("NONEXISTENT") is None


class TestExchangeAdapter:
    """Test ExchangeAdapter base class."""
    
    def test_adapter_initialization(self):
        """Test adapter initialization."""
        venue = Venue("BINANCE")
        config = {"api_key": "test_key"}
        
        adapter = MockExchangeAdapter(venue, config)
        
        assert adapter.venue == venue
        assert adapter.config == config
        assert adapter.trading_mode == TradingMode.BACKTEST
        assert not adapter.is_connected
    
    @pytest.mark.asyncio
    async def test_adapter_connection(self):
        """Test adapter connection lifecycle."""
        venue = Venue("BINANCE")
        adapter = MockExchangeAdapter(venue, {})
        
        # Test connect
        result = await adapter.connect()
        assert result is True
        assert adapter.is_connected
        assert adapter.connect_called
        
        # Test disconnect
        await adapter.disconnect()
        assert not adapter.is_connected
        assert adapter.disconnect_called
    
    def test_trading_mode_change(self):
        """Test trading mode changes."""
        venue = Venue("BINANCE")
        adapter = MockExchangeAdapter(venue, {})
        
        # Change mode when not connected
        adapter.set_trading_mode(TradingMode.PAPER)
        assert adapter.trading_mode == TradingMode.PAPER
    
    @pytest.mark.asyncio
    async def test_order_operations(self):
        """Test order operations."""
        venue = Venue("BINANCE")
        adapter = MockExchangeAdapter(venue, {})
        
        # Create test order
        instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
        instrument = Instrument(
            id=instrument_id,
            symbol="BTCUSDT",
            base_currency="BTC",
            quote_currency="USDT",
            price_precision=2,
            size_precision=6,
            min_quantity=Decimal('0.001'),
            max_quantity=Decimal('1000'),
            tick_size=Decimal('0.01'),
            venue=venue
        )
        
        order = Order(
            id=ClientOrderId("ORD-001"),
            instrument=instrument,
            side=OrderSide.BUY,
            quantity=Quantity.from_str("0.1"),
            price=Price.from_str("50000.00"),
            order_type=OrderType.LIMIT,
            time_in_force=TimeInForce.GTC,
            strategy_id=StrategyId("test-strategy"),
            trading_mode=TradingMode.BACKTEST,
            created_time=datetime.now()
        )
        
        # Submit order
        result = await adapter.submit_order(order)
        assert result is True
        assert len(adapter.submitted_orders) == 1
        
        # Cancel order
        result = await adapter.cancel_order("ORD-001")
        assert result is True
        assert len(adapter.cancelled_orders) == 1
    
    def test_order_simulation(self):
        """Test order execution simulation."""
        venue = Venue("BINANCE")
        adapter = MockExchangeAdapter(venue, {})
        adapter.set_trading_mode(TradingMode.PAPER)
        
        # Create test order
        instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
        instrument = Instrument(
            id=instrument_id,
            symbol="BTCUSDT",
            base_currency="BTC",
            quote_currency="USDT",
            price_precision=2,
            size_precision=6,
            min_quantity=Decimal('0.001'),
            max_quantity=Decimal('1000'),
            tick_size=Decimal('0.01'),
            venue=venue
        )
        
        order = Order(
            id=ClientOrderId("ORD-001"),
            instrument=instrument,
            side=OrderSide.BUY,
            quantity=Quantity.from_str("0.1"),
            price=Price.from_str("50000.00"),
            order_type=OrderType.LIMIT,
            time_in_force=TimeInForce.GTC,
            strategy_id=StrategyId("test-strategy"),
            trading_mode=TradingMode.PAPER,
            created_time=datetime.now()
        )
        
        market_price = Price.from_str("50000.00")
        
        # Simulate execution
        fill = adapter.simulate_order_execution(order, market_price)
        
        assert fill.order_id == order.id
        assert fill.fill_quantity == order.quantity
        assert fill.slippage >= 0
        assert fill.venue == venue


class TestTradingModeManager:
    """Test TradingModeManager."""
    
    def test_manager_initialization(self):
        """Test manager initialization."""
        manager = TradingModeManager()
        
        assert manager.current_mode == TradingMode.BACKTEST
        assert len(manager.strategies) == 0
        assert len(manager.adapters) == 0
        assert len(manager.mode_history) == 0
    
    def test_mode_transitions(self):
        """Test trading mode transitions."""
        manager = TradingModeManager()
        
        # Valid transition: BACKTEST -> PAPER
        manager.set_trading_mode(TradingMode.PAPER, force=True)
        assert manager.current_mode == TradingMode.PAPER
        assert len(manager.mode_history) == 1
        
        # Valid transition: PAPER -> LIVE
        manager.set_trading_mode(TradingMode.LIVE, force=True)
        assert manager.current_mode == TradingMode.LIVE
        assert len(manager.mode_history) == 2
    
    def test_strategy_registration(self):
        """Test strategy registration."""
        manager = TradingModeManager()
        strategy_id = StrategyId("test-strategy")
        strategy = MockStrategy(strategy_id, {})
        
        # Register strategy
        manager.register_strategy(strategy)
        assert strategy_id in manager.strategies
        assert strategy.trading_mode == manager.current_mode
        
        # Unregister strategy
        manager.unregister_strategy(strategy_id)
        assert strategy_id not in manager.strategies
    
    def test_adapter_registration(self):
        """Test adapter registration."""
        manager = TradingModeManager()
        venue = Venue("BINANCE")
        adapter = MockExchangeAdapter(venue, {})
        
        # Register adapter
        manager.register_adapter(adapter)
        assert str(venue) in manager.adapters
        assert adapter.trading_mode == manager.current_mode
        
        # Unregister adapter
        manager.unregister_adapter(str(venue))
        assert str(venue) not in manager.adapters
    
    def test_strategy_promotion(self):
        """Test strategy promotion workflow."""
        manager = TradingModeManager()
        strategy_id = StrategyId("test-strategy")
        strategy = MockStrategy(strategy_id, {})
        
        manager.register_strategy(strategy)
        
        # Create backtest results
        usd = Currency.from_str('USD')
        backtest_results = BacktestResults(
            strategy_id=strategy_id,
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 12, 31),
            total_return=Decimal('0.20'),
            sharpe_ratio=Decimal('1.5'),
            max_drawdown=Decimal('0.08'),
            win_rate=Decimal('0.65'),
            total_trades=100,
            avg_trade_duration=timedelta(hours=2),
            transaction_costs=Money(100, usd)
        )
        
        # Promote to paper trading
        result = manager.promote_strategy_to_paper(strategy_id, backtest_results)
        assert result.is_valid
        assert strategy.trading_mode == TradingMode.PAPER


class TestRiskManager:
    """Test RiskManager base class."""
    
    def test_risk_manager_initialization(self):
        """Test risk manager initialization."""
        config = {
            "max_portfolio_loss": Decimal("0.05"),
            "max_position_size": Decimal("0.1"),
            "max_leverage": Decimal("3.0"),
            "max_daily_trades": 100
        }
        
        risk_manager = MockRiskManager(config)
        
        assert risk_manager.config == config
        assert risk_manager.trading_mode == TradingMode.BACKTEST
        assert not risk_manager.is_active
        assert len(risk_manager.alerts) == 0
        assert len(risk_manager.positions) == 0
        assert len(risk_manager.orders) == 0
    
    def test_risk_manager_lifecycle(self):
        """Test risk manager start/stop."""
        risk_manager = MockRiskManager({})
        
        # Start
        risk_manager.start()
        assert risk_manager.is_active
        
        # Stop
        risk_manager.stop()
        assert not risk_manager.is_active
    
    def test_position_monitoring(self):
        """Test position risk monitoring."""
        risk_manager = MockRiskManager({})
        
        # Create test position
        venue = Venue("BINANCE")
        instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
        position_id = PositionId("POS-001")
        strategy_id = StrategyId("test-strategy")
        usd = Currency.from_str('USD')
        
        instrument = Instrument(
            id=instrument_id,
            symbol="BTCUSDT",
            base_currency="BTC",
            quote_currency="USDT",
            price_precision=2,
            size_precision=6,
            min_quantity=Decimal('0.001'),
            max_quantity=Decimal('1000'),
            tick_size=Decimal('0.01'),
            venue=venue
        )
        
        position = Position(
            id=position_id,
            instrument=instrument,
            side=PositionSide.LONG,
            quantity=Quantity.from_str("1.0"),
            avg_price=Price.from_str("50000.00"),
            unrealized_pnl=Money(0, usd),
            venue=venue,
            strategy_id=strategy_id,
            opened_time=datetime.now()
        )
        
        # Add position
        risk_manager.add_position(position)
        assert len(risk_manager.positions) == 1
        assert len(risk_manager.position_checks) == 1
        
        # Remove position
        risk_manager.remove_position(str(position_id))
        assert len(risk_manager.positions) == 0
    
    def test_order_risk_checking(self):
        """Test order risk checking."""
        risk_manager = MockRiskManager({})
        
        # Create test order
        venue = Venue("BINANCE")
        instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
        
        instrument = Instrument(
            id=instrument_id,
            symbol="BTCUSDT",
            base_currency="BTC",
            quote_currency="USDT",
            price_precision=2,
            size_precision=6,
            min_quantity=Decimal('0.001'),
            max_quantity=Decimal('1000'),
            tick_size=Decimal('0.01'),
            venue=venue
        )
        
        order = Order(
            id=ClientOrderId("ORD-001"),
            instrument=instrument,
            side=OrderSide.BUY,
            quantity=Quantity.from_str("0.1"),
            price=Price.from_str("50000.00"),
            order_type=OrderType.LIMIT,
            time_in_force=TimeInForce.GTC,
            strategy_id=StrategyId("test-strategy"),
            trading_mode=TradingMode.BACKTEST,
            created_time=datetime.now()
        )
        
        # Check order risk
        assessment = risk_manager.add_order(order)
        assert assessment.is_acceptable
        assert len(risk_manager.orders) == 1
        assert len(risk_manager.order_checks) == 1
    
    def test_risk_alerts(self):
        """Test risk alert system."""
        risk_manager = MockRiskManager({})
        
        # Create alert
        alert = risk_manager._create_alert(
            RiskLevel.MEDIUM,
            "Test alert message"
        )
        
        assert len(risk_manager.alerts) == 1
        assert alert.level == RiskLevel.MEDIUM
        assert alert.message == "Test alert message"
        
        # Get alerts
        alerts = risk_manager.get_alerts(level=RiskLevel.MEDIUM)
        assert len(alerts) == 1
        
        # Clear alerts
        risk_manager.clear_alerts(hours=0)  # Clear all
        assert len(risk_manager.alerts) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])