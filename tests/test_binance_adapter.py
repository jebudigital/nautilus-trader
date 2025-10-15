"""
Unit tests for Binance adapter.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from decimal import Decimal
from datetime import datetime

from nautilus_trader.model.identifiers import Venue, InstrumentId, ClientOrderId, StrategyId
from nautilus_trader.model.enums import OrderSide, OrderType, TimeInForce
from nautilus_trader.model.objects import Money, Price, Quantity, Currency

from src.crypto_trading_engine.adapters.binance_adapter import BinanceAdapter
from src.crypto_trading_engine.models.trading_mode import TradingMode
from src.crypto_trading_engine.models.core import Order, Instrument


class TestBinanceAdapter:
    """Test cases for BinanceAdapter."""
    
    @pytest.fixture
    def config(self):
        """Test configuration."""
        return {
            "api_key": "test_api_key",
            "api_secret": "test_api_secret",
            "testnet": True,
            "base_url": "https://testnet.binance.vision/api",
            "ws_url": "wss://testnet.binance.vision/ws"
        }
    
    @pytest.fixture
    def adapter(self, config):
        """Create test adapter."""
        return BinanceAdapter(config, TradingMode.PAPER)
    
    @pytest.fixture
    def sample_instrument(self):
        """Create sample instrument."""
        return Instrument(
            id=InstrumentId.from_str("BTCUSDT.BINANCE"),
            symbol="BTCUSDT",
            base_currency="BTC",
            quote_currency="USDT",
            price_precision=2,
            size_precision=6,
            min_quantity=Decimal("0.001"),
            max_quantity=Decimal("1000"),
            tick_size=Decimal("0.01"),
            venue=Venue("BINANCE"),
            is_active=True
        )
    
    @pytest.fixture
    def sample_order(self, sample_instrument):
        """Create sample order."""
        return Order(
            id=ClientOrderId("TEST_ORDER_1"),
            instrument=sample_instrument,
            side=OrderSide.BUY,
            quantity=Quantity(Decimal("0.1"), 6),
            price=Price(Decimal("50000"), 2),
            order_type=OrderType.LIMIT,
            time_in_force=TimeInForce.GTC,
            strategy_id=StrategyId("TEST-STRATEGY"),
            trading_mode=TradingMode.PAPER,
            created_time=datetime.now(),
            is_simulated=True
        )
    
    def test_initialization(self, config):
        """Test adapter initialization."""
        adapter = BinanceAdapter(config, TradingMode.LIVE)
        
        assert adapter.venue == Venue("BINANCE")
        assert adapter.trading_mode == TradingMode.LIVE
        assert adapter.api_key == "test_api_key"
        assert adapter.api_secret == "test_api_secret"
        assert adapter.testnet is True
        assert not adapter.is_connected
        assert len(adapter.instruments) == 0
        assert len(adapter.positions) == 0
        assert len(adapter.orders) == 0
    
    def test_initialization_with_defaults(self):
        """Test adapter initialization with minimal config."""
        config = {"api_key": "key", "api_secret": "secret"}
        adapter = BinanceAdapter(config)
        
        assert adapter.trading_mode == TradingMode.BACKTEST
        assert adapter.testnet is True
        assert "testnet.binance.vision" in adapter.base_url
    
    @pytest.mark.asyncio
    async def test_connect_backtest_mode(self, config):
        """Test connection in backtest mode."""
        adapter = BinanceAdapter(config, TradingMode.BACKTEST)
        
        result = await adapter.connect()
        
        assert result is True
        assert adapter.is_connected is True
    
    @pytest.mark.asyncio
    async def test_connect_paper_mode_success(self, config):
        """Test successful connection in paper mode."""
        adapter = BinanceAdapter(config, TradingMode.PAPER)
        
        # Mock the private methods directly
        with patch.object(adapter, '_test_connection', return_value=True) as mock_test:
            with patch.object(adapter, '_load_instruments') as mock_load:
                result = await adapter.connect()
                
                assert result is True
                assert adapter.is_connected is True
                mock_test.assert_called_once()
                mock_load.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_connect_failure(self, config):
        """Test connection failure."""
        adapter = BinanceAdapter(config, TradingMode.PAPER)
        
        # Mock the test connection to fail
        with patch.object(adapter, '_test_connection', return_value=False):
            result = await adapter.connect()
            
            assert result is False
            assert adapter.is_connected is False
    
    @pytest.mark.asyncio
    async def test_disconnect(self, adapter):
        """Test disconnection."""
        # Set up connected state
        adapter.is_connected = True
        adapter.session = AsyncMock()
        adapter.ws_connection = AsyncMock()
        
        # Test without market data task first
        await adapter.disconnect()
        
        assert adapter.is_connected is False
        assert adapter.session is None
        assert adapter.ws_connection is None
    
    @pytest.mark.asyncio
    async def test_submit_order_paper_mode(self, adapter, sample_order):
        """Test order submission in paper mode."""
        adapter.instruments[str(sample_order.instrument.id)] = sample_order.instrument
        adapter.last_prices["BTCUSDT"] = Price(Decimal("50000"), 2)
        
        # Mock callbacks
        fill_callback = Mock()
        adapter.set_callbacks(on_order_filled=fill_callback)
        
        result = await adapter.submit_order(sample_order)
        
        assert result is True
        assert str(sample_order.id) in adapter.orders
        fill_callback.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_submit_order_invalid(self, adapter, sample_order):
        """Test submission of invalid order."""
        # Make order invalid by not adding instrument to adapter
        # This will cause validation to fail
        
        result = await adapter.submit_order(sample_order)
        
        assert result is False
        assert str(sample_order.id) not in adapter.orders
    
    @pytest.mark.asyncio
    async def test_submit_order_backtest_mode(self, config, sample_order):
        """Test order submission in backtest mode."""
        adapter = BinanceAdapter(config, TradingMode.BACKTEST)
        
        result = await adapter.submit_order(sample_order)
        
        assert result is False  # Not supported in backtest mode
    
    @pytest.mark.asyncio
    async def test_cancel_order_paper_mode(self, adapter, sample_order):
        """Test order cancellation in paper mode."""
        # Add order to adapter
        adapter.orders[str(sample_order.id)] = sample_order
        
        result = await adapter.cancel_order(str(sample_order.id))
        
        assert result is True
        assert str(sample_order.id) not in adapter.orders
    
    @pytest.mark.asyncio
    async def test_cancel_order_not_found(self, adapter):
        """Test cancellation of non-existent order."""
        result = await adapter.cancel_order("NON_EXISTENT")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_cancel_order_backtest_mode(self, config):
        """Test order cancellation in backtest mode."""
        adapter = BinanceAdapter(config, TradingMode.BACKTEST)
        
        result = await adapter.cancel_order("TEST_ORDER")
        
        assert result is False  # Not supported in backtest mode
    
    @pytest.mark.asyncio
    async def test_get_order_status_paper_mode(self, adapter, sample_order):
        """Test getting order status in paper mode."""
        adapter.orders[str(sample_order.id)] = sample_order
        
        status = await adapter.get_order_status(str(sample_order.id))
        
        assert status is not None
        assert status["orderId"] == str(sample_order.id)
        assert status["status"] == "FILLED"
    
    @pytest.mark.asyncio
    async def test_get_order_status_not_found(self, adapter):
        """Test getting status of non-existent order."""
        status = await adapter.get_order_status("NON_EXISTENT")
        
        assert status is None
    
    @pytest.mark.asyncio
    async def test_get_positions_paper_mode(self, adapter):
        """Test getting positions in paper mode."""
        # Add a simulated position
        from nautilus_trader.model.identifiers import PositionId
        from nautilus_trader.model.enums import PositionSide
        from src.crypto_trading_engine.models.core import Position
        
        instrument = Instrument(
            id=InstrumentId.from_str("BTCUSDT.BINANCE"),
            symbol="BTCUSDT",
            base_currency="BTC",
            quote_currency="USDT",
            price_precision=2,
            size_precision=6,
            min_quantity=Decimal("0.001"),
            max_quantity=Decimal("1000"),
            tick_size=Decimal("0.01"),
            venue=Venue("BINANCE")
        )
        
        position = Position(
            id=PositionId("TEST_POSITION"),
            instrument=instrument,
            side=PositionSide.LONG,
            quantity=Quantity(Decimal("0.1"), 6),
            avg_price=Price(Decimal("50000"), 2),
            unrealized_pnl=Money(Decimal("100"), Currency.from_str("USDT")),
            venue=Venue("BINANCE"),
            strategy_id=StrategyId("TEST-STRATEGY"),
            opened_time=datetime.now(),
            is_simulated=True
        )
        
        adapter.positions["TEST_POSITION"] = position
        
        positions = await adapter.get_positions()
        
        assert len(positions) == 1
        assert positions[0].is_simulated is True
    
    @pytest.mark.asyncio
    async def test_get_balance_paper_mode(self, adapter):
        """Test getting balance in paper mode."""
        balance = await adapter.get_balance()
        
        assert "USDT" in balance
        assert "BTC" in balance
        assert balance["USDT"].as_decimal() == Decimal("10000")
        assert balance["BTC"].as_decimal() == Decimal("1")
    
    @pytest.mark.asyncio
    async def test_get_balance_backtest_mode(self, config):
        """Test getting balance in backtest mode."""
        adapter = BinanceAdapter(config, TradingMode.BACKTEST)
        
        balance = await adapter.get_balance()
        
        assert "USDT" in balance
        assert "BTC" in balance
        assert balance["USDT"].as_decimal() == Decimal("10000")
    
    @pytest.mark.asyncio
    async def test_get_instruments(self, adapter, sample_instrument):
        """Test getting instruments."""
        adapter.instruments[str(sample_instrument.id)] = sample_instrument
        
        instruments = await adapter.get_instruments()
        
        assert len(instruments) == 1
        assert instruments[0].symbol == "BTCUSDT"
    
    @pytest.mark.asyncio
    async def test_subscribe_market_data_backtest(self, config):
        """Test market data subscription in backtest mode."""
        adapter = BinanceAdapter(config, TradingMode.BACKTEST)
        
        result = await adapter.subscribe_market_data(["BTCUSDT.BINANCE"])
        
        assert result is True  # Always succeeds in backtest mode
    
    @pytest.mark.asyncio
    async def test_subscribe_market_data_paper_mode(self, adapter, sample_instrument):
        """Test market data subscription in paper mode."""
        adapter.instruments[str(sample_instrument.id)] = sample_instrument
        
        with patch.object(adapter, '_connect_websocket', new_callable=AsyncMock) as mock_ws:
            result = await adapter.subscribe_market_data([str(sample_instrument.id)])
            
            assert result is True
            assert "btcusdt@ticker" in adapter.subscribed_symbols
            mock_ws.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_unsubscribe_market_data(self, adapter, sample_instrument):
        """Test market data unsubscription."""
        adapter.instruments[str(sample_instrument.id)] = sample_instrument
        adapter.subscribed_symbols.add("btcusdt@ticker")
        
        result = await adapter.unsubscribe_market_data([str(sample_instrument.id)])
        
        assert result is True
        assert "btcusdt@ticker" not in adapter.subscribed_symbols
    
    def test_validate_order_valid(self, adapter, sample_order):
        """Test order validation with valid order."""
        adapter.instruments[str(sample_order.instrument.id)] = sample_order.instrument
        
        result = adapter.validate_order(sample_order)
        
        assert result is True
    
    def test_validate_order_invalid_instrument(self, adapter, sample_order):
        """Test order validation with invalid instrument."""
        # Don't add instrument to adapter
        
        result = adapter.validate_order(sample_order)
        
        assert result is False
    
    def test_simulate_order_execution(self, adapter, sample_order):
        """Test order execution simulation."""
        market_price = Price(Decimal("50000"), 2)
        
        fill = adapter.simulate_order_execution(sample_order, market_price)
        
        assert fill.order_id == sample_order.id
        assert fill.fill_quantity == sample_order.quantity
        assert fill.slippage >= 0
        assert fill.transaction_cost.as_decimal() > 0
    
    def test_simulate_order_execution_live_mode_error(self, config, sample_order):
        """Test that simulation raises error in live mode."""
        adapter = BinanceAdapter(config, TradingMode.LIVE)
        market_price = Price(Decimal("50000"), 2)
        
        with pytest.raises(RuntimeError, match="Cannot simulate execution in live trading mode"):
            adapter.simulate_order_execution(sample_order, market_price)
    
    def test_set_trading_mode_connected_error(self, adapter):
        """Test that setting trading mode while connected raises error."""
        adapter.is_connected = True
        
        with pytest.raises(RuntimeError, match="Cannot change trading mode while connected"):
            adapter.set_trading_mode(TradingMode.LIVE)
    
    def test_set_trading_mode_success(self, adapter):
        """Test successful trading mode change."""
        adapter.is_connected = False
        old_mode = adapter.trading_mode
        
        adapter.set_trading_mode(TradingMode.LIVE)
        
        assert adapter.trading_mode == TradingMode.LIVE
    
    def test_get_connection_status(self, adapter):
        """Test getting connection status."""
        status = adapter.get_connection_status()
        
        assert status["venue"] == "BINANCE"
        assert status["trading_mode"] == "paper"
        assert status["is_connected"] is False
        assert status["instrument_count"] == 0
        assert status["position_count"] == 0
        assert status["order_count"] == 0
    
    def test_to_dict(self, adapter):
        """Test adapter serialization to dictionary."""
        result = adapter.to_dict()
        
        assert result["venue"] == "BINANCE"
        assert result["trading_mode"] == "paper"
        assert result["is_connected"] is False
        assert "config" in result
        assert "instruments" in result
        assert "positions" in result
        assert "orders" in result
    
    def test_set_callbacks(self, adapter):
        """Test setting event callbacks."""
        market_data_cb = Mock()
        order_filled_cb = Mock()
        position_update_cb = Mock()
        error_cb = Mock()
        
        adapter.set_callbacks(
            on_market_data=market_data_cb,
            on_order_filled=order_filled_cb,
            on_position_update=position_update_cb,
            on_error=error_cb
        )
        
        assert adapter.on_market_data_callback == market_data_cb
        assert adapter.on_order_filled_callback == order_filled_cb
        assert adapter.on_position_update_callback == position_update_cb
        assert adapter.on_error_callback == error_cb
    
    def test_parse_instruments(self, adapter):
        """Test parsing instruments from exchange info."""
        symbols_data = [
            {
                "symbol": "BTCUSDT",
                "status": "TRADING",
                "baseAsset": "BTC",
                "quoteAsset": "USDT",
                "quotePrecision": 2,
                "baseAssetPrecision": 6,
                "filters": [
                    {
                        "filterType": "LOT_SIZE",
                        "minQty": "0.001",
                        "maxQty": "1000.0"
                    },
                    {
                        "filterType": "PRICE_FILTER",
                        "tickSize": "0.01"
                    }
                ]
            },
            {
                "symbol": "ETHUSDT",
                "status": "BREAK",  # Should be ignored
                "baseAsset": "ETH",
                "quoteAsset": "USDT"
            }
        ]
        
        adapter._parse_instruments(symbols_data)
        
        assert len(adapter.instruments) == 1  # Only BTCUSDT should be added
        assert "BTCUSDT.BINANCE" in adapter.instruments
        
        instrument = adapter.instruments["BTCUSDT.BINANCE"]
        assert instrument.symbol == "BTCUSDT"
        assert instrument.base_currency == "BTC"
        assert instrument.quote_currency == "USDT"
        assert instrument.min_quantity == Decimal("0.001")
        assert instrument.tick_size == Decimal("0.01")
    
    def test_parse_balances(self, adapter):
        """Test parsing balances from account data."""
        balances_data = [
            {"asset": "BTC", "free": "1.0", "locked": "0.0"},
            {"asset": "USDT", "free": "9500.0", "locked": "500.0"},
            {"asset": "ETH", "free": "0.0", "locked": "0.0"}  # Should be ignored
        ]
        
        balances = adapter._parse_balances(balances_data)
        
        assert len(balances) == 2  # Only BTC and USDT
        assert "BTC" in balances
        assert "USDT" in balances
        assert balances["BTC"].as_decimal() == Decimal("1.0")
        assert balances["USDT"].as_decimal() == Decimal("10000.0")
    
    def test_parse_positions(self, adapter, sample_instrument):
        """Test parsing positions from account balances."""
        adapter.instruments[str(sample_instrument.id)] = sample_instrument
        
        balances_data = [
            {"asset": "BTC", "free": "1.0", "locked": "0.0"},
            {"asset": "USDT", "free": "10000.0", "locked": "0.0"}
        ]
        
        positions = adapter._parse_positions(balances_data)
        
        assert len(positions) == 1  # Only BTC position (USDT is quote currency)
        position = positions[0]
        assert position.instrument.symbol == "BTCUSDT"
        assert position.quantity.as_decimal() == Decimal("1.0")
    
    @pytest.mark.asyncio
    async def test_process_market_data(self, adapter, sample_instrument):
        """Test processing market data message."""
        adapter.instruments[str(sample_instrument.id)] = sample_instrument
        
        # Mock callback
        market_data_cb = Mock()
        adapter.set_callbacks(on_market_data=market_data_cb)
        
        # Sample ticker data
        ticker_data = {
            "e": "24hrTicker",
            "s": "BTCUSDT",
            "c": "50000.00"  # Close price
        }
        
        await adapter._process_market_data(ticker_data)
        
        assert "BTCUSDT" in adapter.last_prices
        assert adapter.last_prices["BTCUSDT"].as_decimal() == Decimal("50000.00")
        market_data_cb.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__])