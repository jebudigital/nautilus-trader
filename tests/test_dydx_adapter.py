"""
Unit tests for dYdX adapter.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from decimal import Decimal
from datetime import datetime, timedelta

from nautilus_trader.model.identifiers import Venue, InstrumentId, ClientOrderId, StrategyId
from nautilus_trader.model.enums import OrderSide, OrderType, TimeInForce
from nautilus_trader.model.objects import Money, Price, Quantity, Currency

from src.crypto_trading_engine.adapters.dydx_adapter import DydxAdapter
from src.crypto_trading_engine.models.trading_mode import TradingMode
from src.crypto_trading_engine.models.core import Order, Instrument


class TestDydxAdapter:
    """Test cases for DydxAdapter."""
    
    @pytest.fixture
    def config(self):
        """Test configuration."""
        return {
            "api_key": "test_api_key",
            "api_secret": "test_api_secret",
            "passphrase": "test_passphrase",
            "testnet": True,
            "base_url": "https://api.stage.dydx.exchange",
            "ws_url": "wss://api.stage.dydx.exchange/v3/ws"
        }
    
    @pytest.fixture
    def adapter(self, config):
        """Create test adapter."""
        return DydxAdapter(config, TradingMode.PAPER)
    
    @pytest.fixture
    def sample_instrument(self):
        """Create sample instrument."""
        return Instrument(
            id=InstrumentId.from_str("BTC-USD.DYDX"),
            symbol="BTC-USD",
            base_currency="BTC",
            quote_currency="USD",
            price_precision=2,
            size_precision=6,
            min_quantity=Decimal("0.001"),
            max_quantity=None,
            tick_size=Decimal("0.01"),
            venue=Venue("DYDX"),
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
        adapter = DydxAdapter(config, TradingMode.LIVE)
        
        assert adapter.venue == Venue("DYDX")
        assert adapter.trading_mode == TradingMode.LIVE
        assert adapter.api_key == "test_api_key"
        assert adapter.api_secret == "test_api_secret"
        assert adapter.passphrase == "test_passphrase"
        assert adapter.testnet is True
        assert not adapter.is_connected
        assert len(adapter.instruments) == 0
        assert len(adapter.positions) == 0
        assert len(adapter.orders) == 0
    
    def test_initialization_with_defaults(self):
        """Test adapter initialization with minimal config."""
        config = {"api_key": "key", "api_secret": "secret", "passphrase": "pass"}
        adapter = DydxAdapter(config)
        
        assert adapter.trading_mode == TradingMode.BACKTEST
        assert adapter.testnet is True
        assert "api.stage.dydx.exchange" in adapter.base_url
    
    @pytest.mark.asyncio
    async def test_connect_backtest_mode(self, config):
        """Test connection in backtest mode."""
        adapter = DydxAdapter(config, TradingMode.BACKTEST)
        
        result = await adapter.connect()
        
        assert result is True
        assert adapter.is_connected is True
    
    @pytest.mark.asyncio
    async def test_connect_paper_mode_success(self, config):
        """Test successful connection in paper mode."""
        adapter = DydxAdapter(config, TradingMode.PAPER)
        
        # Mock the private methods directly
        with patch.object(adapter, '_test_connection', return_value=True) as mock_test:
            with patch.object(adapter, '_load_markets') as mock_load:
                result = await adapter.connect()
                
                assert result is True
                assert adapter.is_connected is True
                mock_test.assert_called_once()
                mock_load.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_connect_failure(self, config):
        """Test connection failure."""
        adapter = DydxAdapter(config, TradingMode.PAPER)
        
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
        adapter.ws_connection.closed = False
        
        await adapter.disconnect()
        
        assert adapter.is_connected is False
        assert adapter.session is None
        assert adapter.ws_connection is None
    
    @pytest.mark.asyncio
    async def test_submit_order_paper_mode(self, adapter, sample_order):
        """Test order submission in paper mode."""
        adapter.instruments[str(sample_order.instrument.id)] = sample_order.instrument
        adapter.last_prices["BTC-USD"] = Price(Decimal("50000"), 2)
        
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
        
        result = await adapter.submit_order(sample_order)
        
        assert result is False
        assert str(sample_order.id) not in adapter.orders
    
    @pytest.mark.asyncio
    async def test_submit_order_backtest_mode(self, config, sample_order):
        """Test order submission in backtest mode."""
        adapter = DydxAdapter(config, TradingMode.BACKTEST)
        
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
        adapter = DydxAdapter(config, TradingMode.BACKTEST)
        
        result = await adapter.cancel_order("TEST_ORDER")
        
        assert result is False  # Not supported in backtest mode
    
    @pytest.mark.asyncio
    async def test_get_order_status_paper_mode(self, adapter, sample_order):
        """Test getting order status in paper mode."""
        adapter.orders[str(sample_order.id)] = sample_order
        
        status = await adapter.get_order_status(str(sample_order.id))
        
        assert status is not None
        assert status["id"] == str(sample_order.id)
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
            id=InstrumentId.from_str("BTC-USD.DYDX"),
            symbol="BTC-USD",
            base_currency="BTC",
            quote_currency="USD",
            price_precision=2,
            size_precision=6,
            min_quantity=Decimal("0.001"),
            max_quantity=None,
            tick_size=Decimal("0.01"),
            venue=Venue("DYDX")
        )
        
        position = Position(
            id=PositionId("TEST_POSITION"),
            instrument=instrument,
            side=PositionSide.LONG,
            quantity=Quantity(Decimal("0.1"), 6),
            avg_price=Price(Decimal("50000"), 2),
            unrealized_pnl=Money(Decimal("100"), Currency.from_str("USDC")),
            venue=Venue("DYDX"),
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
        
        assert "USDC" in balance
        assert balance["USDC"].as_decimal() == Decimal("10000")
    
    @pytest.mark.asyncio
    async def test_get_balance_backtest_mode(self, config):
        """Test getting balance in backtest mode."""
        adapter = DydxAdapter(config, TradingMode.BACKTEST)
        
        balance = await adapter.get_balance()
        
        assert "USDC" in balance
        assert balance["USDC"].as_decimal() == Decimal("10000")
    
    @pytest.mark.asyncio
    async def test_get_instruments(self, adapter, sample_instrument):
        """Test getting instruments."""
        adapter.instruments[str(sample_instrument.id)] = sample_instrument
        
        instruments = await adapter.get_instruments()
        
        assert len(instruments) == 1
        assert instruments[0].symbol == "BTC-USD"
    
    @pytest.mark.asyncio
    async def test_subscribe_market_data_backtest(self, config):
        """Test market data subscription in backtest mode."""
        adapter = DydxAdapter(config, TradingMode.BACKTEST)
        
        result = await adapter.subscribe_market_data(["BTC-USD.DYDX"])
        
        assert result is True  # Always succeeds in backtest mode
    
    @pytest.mark.asyncio
    async def test_subscribe_market_data_paper_mode(self, adapter, sample_instrument):
        """Test market data subscription in paper mode."""
        adapter.instruments[str(sample_instrument.id)] = sample_instrument
        
        with patch.object(adapter, '_connect_websocket', new_callable=AsyncMock) as mock_ws:
            with patch.object(adapter, '_subscribe_to_market', new_callable=AsyncMock) as mock_sub:
                result = await adapter.subscribe_market_data([str(sample_instrument.id)])
                
                assert result is True
                assert "BTC-USD" in adapter.subscribed_markets
                mock_ws.assert_called_once()
                mock_sub.assert_called_once_with("BTC-USD")
    
    @pytest.mark.asyncio
    async def test_unsubscribe_market_data(self, adapter, sample_instrument):
        """Test market data unsubscription."""
        adapter.instruments[str(sample_instrument.id)] = sample_instrument
        adapter.subscribed_markets.add("BTC-USD")
        
        result = await adapter.unsubscribe_market_data([str(sample_instrument.id)])
        
        assert result is True
        assert "BTC-USD" not in adapter.subscribed_markets
    
    @pytest.mark.asyncio
    async def test_get_funding_rates_backtest(self, config):
        """Test getting funding rates in backtest mode."""
        adapter = DydxAdapter(config, TradingMode.BACKTEST)
        
        # Add a sample instrument
        instrument = Instrument(
            id=InstrumentId.from_str("BTC-USD.DYDX"),
            symbol="BTC-USD",
            base_currency="BTC",
            quote_currency="USD",
            price_precision=2,
            size_precision=6,
            min_quantity=Decimal("0.001"),
            max_quantity=None,
            tick_size=Decimal("0.01"),
            venue=Venue("DYDX")
        )
        adapter.instruments[str(instrument.id)] = instrument
        
        funding_rates = await adapter.get_funding_rates("BTC-USD")
        
        assert len(funding_rates) == 1
        assert funding_rates[0].rate == Decimal("0.0001")
    
    @pytest.mark.asyncio
    async def test_calculate_margin_requirements(self, adapter, sample_instrument):
        """Test margin requirements calculation."""
        adapter.instruments[str(sample_instrument.id)] = sample_instrument
        adapter.last_prices["BTC-USD"] = Price(Decimal("50000"), 2)
        
        margin_req = await adapter.calculate_margin_requirements(Decimal("1.0"), "BTC-USD")
        
        assert "initial_margin" in margin_req
        assert "maintenance_margin" in margin_req
        assert "notional_value" in margin_req
        assert "leverage" in margin_req
        assert margin_req["leverage"] == Decimal("10")
    
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
    
    def test_get_connection_status(self, adapter):
        """Test getting connection status."""
        status = adapter.get_connection_status()
        
        assert status["venue"] == "DYDX"
        assert status["trading_mode"] == "paper"
        assert status["is_connected"] is False
        assert status["instrument_count"] == 0
        assert status["position_count"] == 0
        assert status["order_count"] == 0
    
    def test_to_dict(self, adapter):
        """Test adapter serialization to dictionary."""
        result = adapter.to_dict()
        
        assert result["venue"] == "DYDX"
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
    
    def test_parse_markets(self, adapter):
        """Test parsing markets from API response."""
        markets_data = {
            "BTC-USD": {
                "status": "ONLINE",
                "baseAsset": "BTC",
                "quoteAsset": "USD",
                "tickSize": "0.1",
                "stepSize": "0.001",
                "minOrderSize": "0.001"
            },
            "ETH-USD": {
                "status": "OFFLINE",  # Should be ignored
                "baseAsset": "ETH",
                "quoteAsset": "USD"
            }
        }
        
        adapter._parse_markets(markets_data)
        
        assert len(adapter.instruments) == 1  # Only BTC-USD should be added
        assert "BTC-USD.DYDX" in adapter.instruments
        
        instrument = adapter.instruments["BTC-USD.DYDX"]
        assert instrument.symbol == "BTC-USD"
        assert instrument.base_currency == "BTC"
        assert instrument.quote_currency == "USD"
        assert instrument.min_quantity == Decimal("0.001")
        assert instrument.tick_size == Decimal("0.1")
    
    def test_parse_balance(self, adapter):
        """Test parsing balance from account data."""
        account_data = {
            "equity": "15000.50"
        }
        
        balances = adapter._parse_balance(account_data)
        
        assert len(balances) == 1
        assert "USDC" in balances
        assert balances["USDC"].as_decimal() == Decimal("15000.50")
    
    def test_parse_positions(self, adapter, sample_instrument):
        """Test parsing positions from API response."""
        adapter.instruments[str(sample_instrument.id)] = sample_instrument
        
        positions_data = [
            {
                "market": "BTC-USD",
                "size": "1.5",
                "entryPrice": "50000.0",
                "unrealizedPnl": "1500.0"
            },
            {
                "market": "ETH-USD",
                "size": "0.0"  # Should be ignored
            }
        ]
        
        positions = adapter._parse_positions(positions_data)
        
        assert len(positions) == 1  # Only BTC-USD position
        position = positions[0]
        assert position.instrument.symbol == "BTC-USD"
        assert position.quantity.as_decimal() == Decimal("1.5")
        assert position.avg_price.as_decimal() == Decimal("50000.0")
    
    def test_parse_funding_rates(self, adapter, sample_instrument):
        """Test parsing funding rates from API response."""
        adapter.instruments[str(sample_instrument.id)] = sample_instrument
        
        funding_data = [
            {
                "rate": "0.0001",
                "effectiveAt": "2023-01-01T00:00:00.000Z"
            },
            {
                "rate": "-0.0002",
                "effectiveAt": "2023-01-01T08:00:00.000Z"
            }
        ]
        
        funding_rates = adapter._parse_funding_rates("BTC-USD", funding_data)
        
        assert len(funding_rates) == 2
        assert funding_rates[0].rate == Decimal("0.0001")
        assert funding_rates[1].rate == Decimal("-0.0002")
        assert funding_rates[0].instrument.symbol == "BTC-USD"
    
    @pytest.mark.asyncio
    async def test_process_market_data(self, adapter, sample_instrument):
        """Test processing market data message."""
        adapter.instruments[str(sample_instrument.id)] = sample_instrument
        
        # Mock callback
        market_data_cb = Mock()
        adapter.set_callbacks(on_market_data=market_data_cb)
        
        # Sample orderbook data
        orderbook_data = {
            "type": "channel_data",
            "channel": "v3_orderbook",
            "id": "BTC-USD",
            "contents": {
                "bids": [["49900.0", "1.5"]],
                "asks": [["50100.0", "2.0"]]
            }
        }
        
        await adapter._process_market_data(orderbook_data)
        
        assert "BTC-USD" in adapter.last_prices
        # Mid price should be (49900 + 50100) / 2 = 50000
        assert adapter.last_prices["BTC-USD"].as_decimal() == Decimal("50000")
        market_data_cb.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__])