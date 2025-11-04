"""
Unit tests for Uniswap adapter.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from decimal import Decimal
from datetime import datetime

from nautilus_trader.model.identifiers import Venue, InstrumentId, ClientOrderId, StrategyId
from nautilus_trader.model.enums import OrderSide, OrderType, TimeInForce
from nautilus_trader.model.objects import Money, Price, Quantity, Currency

from src.crypto_trading_engine.adapters.uniswap_adapter import UniswapAdapter
from src.crypto_trading_engine.models.trading_mode import TradingMode
from src.crypto_trading_engine.models.core import Order, Instrument
from src.crypto_trading_engine.models.defi import Token, UniswapPool, LiquidityPosition


class TestUniswapAdapter:
    """Test cases for UniswapAdapter."""
    
    @pytest.fixture
    def config(self):
        """Test configuration."""
        return {
            "web3_provider_url": "https://mainnet.infura.io/v3/test",
            "private_key": "0x" + "0" * 64,  # Dummy private key
            "network": "mainnet",
            "factory_address": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
            "router_address": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
            "position_manager_address": "0xC36442b4a4522E871399CD717aBDD847Ab11FE88"
        }
    
    @pytest.fixture
    def adapter(self, config):
        """Create test adapter."""
        return UniswapAdapter(config, TradingMode.PAPER)
    
    @pytest.fixture
    def sample_token0(self):
        """Create sample token0."""
        return Token(
            address="0xA0b86a33E6441E6C8A0E0C37c2E0C2F0E6C4F2A8",
            symbol="USDC",
            decimals=6,
            name="USD Coin"
        )
    
    @pytest.fixture
    def sample_token1(self):
        """Create sample token1."""
        return Token(
            address="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
            symbol="WETH",
            decimals=18,
            name="Wrapped Ether"
        )
    
    @pytest.fixture
    def sample_pool(self, sample_token0, sample_token1):
        """Create sample pool."""
        return UniswapPool(
            address="0x8ad599c3A0ff1De082011EFDDc58f1908eb6e6D8",
            token0=sample_token0,
            token1=sample_token1,
            fee_tier=3000,
            liquidity=Decimal("1000000"),
            sqrt_price_x96=2**96,
            tick=0,
            apy=0.15
        )
    
    @pytest.fixture
    def sample_instrument(self):
        """Create sample instrument."""
        return Instrument(
            id=InstrumentId.from_str("POOL_8ad599c3.UNISWAP"),
            symbol="POOL_8ad599c3",
            base_currency="LP",
            quote_currency="ETH",
            price_precision=8,
            size_precision=8,
            min_quantity=Decimal("0.001"),
            max_quantity=None,
            tick_size=Decimal("0.000001"),
            venue=Venue("UNISWAP"),
            is_active=True
        )
    
    @pytest.fixture
    def sample_order(self, sample_instrument):
        """Create sample order."""
        return Order(
            id=ClientOrderId("TEST_ORDER_1"),
            instrument=sample_instrument,
            side=OrderSide.BUY,
            quantity=Quantity(Decimal("1000"), 8),
            price=Price(Decimal("1"), 8),
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.GTC,
            strategy_id=StrategyId("TEST-STRATEGY"),
            trading_mode=TradingMode.PAPER,
            created_time=datetime.now(),
            is_simulated=True
        )
    
    def test_initialization(self, config):
        """Test adapter initialization."""
        adapter = UniswapAdapter(config, TradingMode.LIVE)
        
        assert adapter.venue == Venue("UNISWAP")
        assert adapter.trading_mode == TradingMode.LIVE
        assert adapter.web3_provider_url == "https://mainnet.infura.io/v3/test"
        assert adapter.network == "mainnet"
        assert not adapter.is_connected
        assert len(adapter.instruments) == 0
        assert len(adapter.pools) == 0
        assert len(adapter.liquidity_positions) == 0
    
    def test_initialization_with_defaults(self):
        """Test adapter initialization with minimal config."""
        config = {"web3_provider_url": "https://mainnet.infura.io/v3/test"}
        adapter = UniswapAdapter(config)
        
        assert adapter.trading_mode == TradingMode.BACKTEST
        assert adapter.network == "mainnet"
        assert "1F98431c8aD98523631AE4a59f267346ea31F984" in adapter.factory_address
    
    @pytest.mark.asyncio
    async def test_connect_backtest_mode(self, config):
        """Test connection in backtest mode."""
        adapter = UniswapAdapter(config, TradingMode.BACKTEST)
        
        result = await adapter.connect()
        
        assert result is True
        assert adapter.is_connected is True
    
    @pytest.mark.asyncio
    async def test_connect_paper_mode_success(self, config):
        """Test successful connection in paper mode."""
        adapter = UniswapAdapter(config, TradingMode.PAPER)
        
        # Mock the private methods directly
        with patch.object(adapter, '_initialize_web3', return_value=True) as mock_web3:
            with patch.object(adapter, '_load_pools') as mock_load_pools:
                with patch.object(adapter, '_start_gas_monitoring') as mock_gas:
                    result = await adapter.connect()
                    
                    assert result is True
                    assert adapter.is_connected is True
                    mock_web3.assert_called_once()
                    mock_load_pools.assert_called_once()
                    mock_gas.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_connect_failure(self, config):
        """Test connection failure."""
        adapter = UniswapAdapter(config, TradingMode.PAPER)
        
        # Mock the web3 initialization to fail
        with patch.object(adapter, '_initialize_web3', return_value=False):
            result = await adapter.connect()
            
            assert result is False
            assert adapter.is_connected is False
    
    @pytest.mark.asyncio
    async def test_disconnect(self, adapter):
        """Test disconnection."""
        # Set up connected state
        adapter.is_connected = True
        adapter.w3 = Mock()
        adapter.account_address = "0x123"
        
        await adapter.disconnect()
        
        assert adapter.is_connected is False
        assert adapter.w3 is None
        assert adapter.account_address is None
    
    @pytest.mark.asyncio
    async def test_submit_order_paper_mode(self, adapter, sample_order, sample_pool):
        """Test order submission in paper mode."""
        # Update the instrument symbol to match the pool address pattern
        sample_order.instrument.symbol = f"POOL_{sample_pool.address[:8]}"
        adapter.instruments[str(sample_order.instrument.id)] = sample_order.instrument
        adapter.pools[sample_pool.address] = sample_pool
        
        # Mock callbacks
        fill_callback = Mock()
        adapter.set_callbacks(on_order_filled=fill_callback)
        
        result = await adapter.submit_order(sample_order)
        
        assert result is True
        assert str(sample_order.id) in adapter.liquidity_positions
        fill_callback.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_submit_order_invalid(self, adapter, sample_order):
        """Test submission of invalid order."""
        # Make order invalid by not adding instrument to adapter
        
        result = await adapter.submit_order(sample_order)
        
        assert result is False
        assert str(sample_order.id) not in adapter.liquidity_positions
    
    @pytest.mark.asyncio
    async def test_submit_order_backtest_mode(self, config, sample_order):
        """Test order submission in backtest mode."""
        adapter = UniswapAdapter(config, TradingMode.BACKTEST)
        
        result = await adapter.submit_order(sample_order)
        
        assert result is False  # Not supported in backtest mode
    
    @pytest.mark.asyncio
    async def test_cancel_order_paper_mode(self, adapter, sample_order, sample_pool):
        """Test order cancellation (liquidity removal) in paper mode."""
        # Add liquidity position to adapter
        position = LiquidityPosition(
            pool_address=sample_pool.address,
            token0=sample_pool.token0,
            token1=sample_pool.token1,
            liquidity_amount=Decimal("1000"),
            tick_lower=-60000,
            tick_upper=60000,
            fees_earned=Money(Decimal("0"), Currency.from_str("ETH")),
            impermanent_loss=Money(Decimal("0"), Currency.from_str("ETH")),
            strategy_id=StrategyId("TEST-STRATEGY"),
            created_time=datetime.now(),
            is_simulated=True
        )
        adapter.liquidity_positions[str(sample_order.id)] = position
        
        result = await adapter.cancel_order(str(sample_order.id))
        
        assert result is True
        assert str(sample_order.id) not in adapter.liquidity_positions
    
    @pytest.mark.asyncio
    async def test_cancel_order_not_found(self, adapter):
        """Test cancellation of non-existent position."""
        result = await adapter.cancel_order("NON_EXISTENT")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_cancel_order_backtest_mode(self, config):
        """Test order cancellation in backtest mode."""
        adapter = UniswapAdapter(config, TradingMode.BACKTEST)
        
        result = await adapter.cancel_order("TEST_ORDER")
        
        assert result is False  # Not supported in backtest mode
    
    @pytest.mark.asyncio
    async def test_get_order_status_with_position(self, adapter, sample_pool):
        """Test getting order status with existing position."""
        position = LiquidityPosition(
            pool_address=sample_pool.address,
            token0=sample_pool.token0,
            token1=sample_pool.token1,
            liquidity_amount=Decimal("1000"),
            tick_lower=-60000,
            tick_upper=60000,
            fees_earned=Money(Decimal("10"), Currency.from_str("ETH")),
            impermanent_loss=Money(Decimal("0"), Currency.from_str("ETH")),
            strategy_id=StrategyId("TEST-STRATEGY"),
            created_time=datetime.now(),
            is_simulated=True
        )
        adapter.liquidity_positions["TEST_POSITION"] = position
        
        status = await adapter.get_order_status("TEST_POSITION")
        
        assert status is not None
        assert status["id"] == "TEST_POSITION"
        assert status["status"] == "ACTIVE"
        assert status["liquidity"] == "1000"
    
    @pytest.mark.asyncio
    async def test_get_order_status_not_found(self, adapter):
        """Test getting status of non-existent position."""
        status = await adapter.get_order_status("NON_EXISTENT")
        
        assert status is None
    
    @pytest.mark.asyncio
    async def test_get_positions(self, adapter, sample_pool, sample_instrument):
        """Test getting positions."""
        adapter.instruments[str(sample_instrument.id)] = sample_instrument
        
        # Add a liquidity position
        position = LiquidityPosition(
            pool_address=sample_pool.address,
            token0=sample_pool.token0,
            token1=sample_pool.token1,
            liquidity_amount=Decimal("1000"),
            tick_lower=-60000,
            tick_upper=60000,
            fees_earned=Money(Decimal("10"), Currency.from_str("ETH")),
            impermanent_loss=Money(Decimal("0"), Currency.from_str("ETH")),
            strategy_id=StrategyId("TEST-STRATEGY"),
            created_time=datetime.now(),
            is_simulated=True
        )
        adapter.liquidity_positions["TEST_POSITION"] = position
        
        # Mock the _get_pool_instrument method
        with patch.object(adapter, '_get_pool_instrument', return_value=sample_instrument):
            positions = await adapter.get_positions()
            
            assert len(positions) == 1
            assert positions[0].is_simulated is True
    
    @pytest.mark.asyncio
    async def test_get_balance_paper_mode(self, adapter):
        """Test getting balance in paper mode."""
        balance = await adapter.get_balance()
        
        assert "ETH" in balance
        assert "USDC" in balance
        assert balance["ETH"].as_decimal() == Decimal("10")
        assert balance["USDC"].as_decimal() == Decimal("10000")
    
    @pytest.mark.asyncio
    async def test_get_balance_backtest_mode(self, config):
        """Test getting balance in backtest mode."""
        adapter = UniswapAdapter(config, TradingMode.BACKTEST)
        
        balance = await adapter.get_balance()
        
        assert "ETH" in balance
        assert "USDC" in balance
        assert balance["ETH"].as_decimal() == Decimal("10")
    
    @pytest.mark.asyncio
    async def test_get_instruments(self, adapter, sample_instrument):
        """Test getting instruments."""
        adapter.instruments[str(sample_instrument.id)] = sample_instrument
        
        instruments = await adapter.get_instruments()
        
        assert len(instruments) == 1
        assert instruments[0].symbol == "POOL_8ad599c3"
    
    @pytest.mark.asyncio
    async def test_subscribe_market_data_backtest(self, config):
        """Test market data subscription in backtest mode."""
        adapter = UniswapAdapter(config, TradingMode.BACKTEST)
        
        result = await adapter.subscribe_market_data(["POOL_8ad599c3.UNISWAP"])
        
        assert result is True  # Always succeeds in backtest mode
    
    @pytest.mark.asyncio
    async def test_subscribe_market_data_paper_mode(self, adapter, sample_instrument):
        """Test market data subscription in paper mode."""
        adapter.instruments[str(sample_instrument.id)] = sample_instrument
        
        result = await adapter.subscribe_market_data([str(sample_instrument.id)])
        
        assert result is True
        # Should start the pool monitoring task
        assert adapter.pool_update_task is not None
    
    @pytest.mark.asyncio
    async def test_unsubscribe_market_data(self, adapter, sample_instrument):
        """Test market data unsubscription."""
        result = await adapter.unsubscribe_market_data([str(sample_instrument.id)])
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_get_pool_info(self, adapter, sample_pool):
        """Test getting pool information."""
        adapter.pools[sample_pool.address] = sample_pool
        
        pool_info = await adapter.get_pool_info(sample_pool.address)
        
        assert pool_info is not None
        assert pool_info.address == sample_pool.address
        assert pool_info.fee_tier == 3000
    
    @pytest.mark.asyncio
    async def test_get_pool_info_not_found(self, adapter):
        """Test getting info for non-existent pool."""
        pool_info = await adapter.get_pool_info("0x123")
        
        assert pool_info is None
    
    @pytest.mark.asyncio
    async def test_calculate_optimal_liquidity(self, adapter, sample_pool):
        """Test calculating optimal liquidity."""
        adapter.pools[sample_pool.address] = sample_pool
        
        result = await adapter.calculate_optimal_liquidity(
            sample_pool.address,
            Decimal("1000"),  # token0_amount
            Decimal("1"),     # token1_amount
            -60000,           # tick_lower
            60000             # tick_upper
        )
        
        assert "liquidity_amount" in result
        assert "token0_required" in result
        assert "token1_required" in result
        assert "current_price" in result
        assert "estimated_fees_apy" in result
    
    @pytest.mark.asyncio
    async def test_calculate_optimal_liquidity_pool_not_found(self, adapter):
        """Test calculating liquidity for non-existent pool."""
        result = await adapter.calculate_optimal_liquidity(
            "0x123", Decimal("1000"), Decimal("1"), -60000, 60000
        )
        
        assert result == {}
    
    @pytest.mark.asyncio
    async def test_estimate_gas_cost_non_live_mode(self, adapter):
        """Test gas cost estimation in non-live mode."""
        result = await adapter.estimate_gas_cost("add_liquidity")
        
        assert "gas_limit" in result
        assert "gas_price" in result
        assert "total_cost_wei" in result
        assert "total_cost_eth" in result
        assert result["total_cost_eth"] == Decimal("0.004")
    
    @pytest.mark.asyncio
    async def test_estimate_gas_cost_live_mode(self, config):
        """Test gas cost estimation in live mode."""
        adapter = UniswapAdapter(config, TradingMode.LIVE)
        
        # Mock Web3 instance
        mock_w3 = Mock()
        mock_w3.eth.gas_price = 20000000000  # 20 gwei
        adapter.w3 = mock_w3
        
        result = await adapter.estimate_gas_cost("remove_liquidity")
        
        assert "gas_limit" in result
        assert "gas_price" in result
        assert result["gas_price"] == 20000000000
        assert result["gas_limit"] == 200000  # remove_liquidity gas limit
    
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
    
    def test_get_connection_status(self, adapter):
        """Test getting connection status."""
        status = adapter.get_connection_status()
        
        assert status["venue"] == "UNISWAP"
        assert status["trading_mode"] == "paper"
        assert status["is_connected"] is False
        assert status["instrument_count"] == 0
        assert status["position_count"] == 0
        assert status["order_count"] == 0
    
    def test_to_dict(self, adapter):
        """Test adapter serialization to dictionary."""
        result = adapter.to_dict()
        
        assert result["venue"] == "UNISWAP"
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
    
    @pytest.mark.asyncio
    async def test_initialize_web3_success(self, adapter):
        """Test successful Web3 initialization."""
        # Mock WEB3_AVAILABLE to be True
        with patch('src.crypto_trading_engine.adapters.uniswap_adapter.WEB3_AVAILABLE', True):
            with patch('src.crypto_trading_engine.adapters.uniswap_adapter.Web3') as mock_web3_class:
                mock_w3 = Mock()
                mock_w3.is_connected.return_value = True
                mock_web3_class.return_value = mock_w3
                
                # Mock account creation
                mock_account = Mock()
                mock_account.address = "0x123456789"
                mock_w3.eth.account.from_key.return_value = mock_account
                
                result = await adapter._initialize_web3()
                
                assert result is True
                assert adapter.w3 == mock_w3
                assert adapter.account_address == "0x123456789"
    
    @pytest.mark.asyncio
    async def test_initialize_web3_no_provider_url(self, config):
        """Test Web3 initialization without provider URL."""
        config["web3_provider_url"] = ""
        adapter = UniswapAdapter(config, TradingMode.PAPER)
        
        result = await adapter._initialize_web3()
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_initialize_web3_connection_failed(self, adapter):
        """Test Web3 initialization with connection failure."""
        # Mock WEB3_AVAILABLE to be True
        with patch('src.crypto_trading_engine.adapters.uniswap_adapter.WEB3_AVAILABLE', True):
            with patch('src.crypto_trading_engine.adapters.uniswap_adapter.Web3') as mock_web3_class:
                mock_w3 = Mock()
                mock_w3.is_connected.return_value = False
                mock_web3_class.return_value = mock_w3
                
                result = await adapter._initialize_web3()
                
                assert result is False
    
    @pytest.mark.asyncio
    async def test_load_pools(self, adapter):
        """Test loading pools."""
        await adapter._load_pools()
        
        # Should load at least one pool
        assert len(adapter.pools) >= 1
        assert len(adapter.instruments) >= 1
        
        # Check that the pool was created correctly
        pool_address = "0x8ad599c3A0ff1De082011EFDDc58f1908eb6e6D8"
        assert pool_address in adapter.pools
        
        pool = adapter.pools[pool_address]
        assert pool.fee_tier == 3000
        assert pool.token0.symbol == "USDC"
        assert pool.token1.symbol == "WETH"
    
    @pytest.mark.asyncio
    async def test_start_gas_monitoring_live_mode(self, config):
        """Test starting gas monitoring in live mode."""
        adapter = UniswapAdapter(config, TradingMode.LIVE)
        
        # Mock Web3 instance
        mock_w3 = Mock()
        mock_w3.eth.gas_price = 25000000000  # 25 gwei
        adapter.w3 = mock_w3
        
        await adapter._start_gas_monitoring()
        
        assert adapter.current_gas_price == 25000000000
    
    @pytest.mark.asyncio
    async def test_start_gas_monitoring_non_live_mode(self, adapter):
        """Test starting gas monitoring in non-live mode."""
        await adapter._start_gas_monitoring()
        
        # Should not set gas price in non-live mode
        assert adapter.current_gas_price is None
    
    def test_get_pool_instrument_found(self, adapter, sample_instrument, sample_pool):
        """Test getting pool instrument when it exists."""
        # Update the instrument symbol to contain the pool address
        sample_instrument.symbol = f"POOL_{sample_pool.address[:8]}"
        adapter.instruments[str(sample_instrument.id)] = sample_instrument
        
        result = adapter._get_pool_instrument(sample_pool.address)
        
        assert result == sample_instrument
    
    def test_get_pool_instrument_not_found(self, adapter):
        """Test getting pool instrument when it doesn't exist."""
        result = adapter._get_pool_instrument("0x123")
        
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__])