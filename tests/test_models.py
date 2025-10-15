"""
Unit tests for trading models.
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal

from nautilus_trader.model.enums import OrderSide, OrderType, TimeInForce, PositionSide
from nautilus_trader.model.identifiers import (
    InstrumentId, ClientOrderId, PositionId, StrategyId, Venue
)
from nautilus_trader.model.objects import Money, Price, Quantity, Currency

from crypto_trading_engine.models import (
    TradingMode, BacktestResults, Instrument, Position, Order, SimulatedFill,
    Token, UniswapPool, LiquidityPosition, FundingRate, PerpetualPosition
)


class TestTradingMode:
    """Test TradingMode enum and BacktestResults."""
    
    def test_trading_mode_values(self):
        """Test TradingMode enum values."""
        assert TradingMode.BACKTEST.value == "backtest"
        assert TradingMode.PAPER.value == "paper"
        assert TradingMode.LIVE.value == "live"
    
    def test_backtest_results_validation(self):
        """Test BacktestResults validation."""
        strategy_id = StrategyId("test-strategy")
        start_date = datetime(2023, 1, 1)
        end_date = datetime(2023, 12, 31)
        usd = Currency.from_str('USD')
        
        # Valid results
        results = BacktestResults(
            strategy_id=strategy_id,
            start_date=start_date,
            end_date=end_date,
            total_return=Decimal('0.15'),
            sharpe_ratio=Decimal('1.2'),
            max_drawdown=Decimal('0.05'),
            win_rate=Decimal('0.6'),
            total_trades=100,
            avg_trade_duration=timedelta(hours=2),
            transaction_costs=Money(100, usd)
        )
        results.validate()  # Should not raise
        
        # Invalid date range
        with pytest.raises(ValueError, match="Start date must be before end date"):
            invalid_results = BacktestResults(
                strategy_id=strategy_id,
                start_date=end_date,
                end_date=start_date,
                total_return=Decimal('0.15'),
                sharpe_ratio=Decimal('1.2'),
                max_drawdown=Decimal('0.05'),
                win_rate=Decimal('0.6'),
                total_trades=100,
                avg_trade_duration=timedelta(hours=2),
                transaction_costs=Money(100, usd)
            )
            invalid_results.validate()


class TestCoreModels:
    """Test core trading models."""
    
    def test_instrument_validation(self):
        """Test Instrument validation."""
        venue = Venue("BINANCE")
        instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
        
        # Valid instrument
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
        instrument.validate()  # Should not raise
        
        # Invalid price precision
        with pytest.raises(ValueError, match="Price precision cannot be negative"):
            invalid_instrument = Instrument(
                id=instrument_id,
                symbol="BTCUSDT",
                base_currency="BTC",
                quote_currency="USDT",
                price_precision=-1,
                size_precision=6,
                min_quantity=Decimal('0.001'),
                max_quantity=Decimal('1000'),
                tick_size=Decimal('0.01'),
                venue=venue
            )
            invalid_instrument.validate()
    
    def test_position_pnl_calculation(self):
        """Test Position P&L calculation."""
        venue = Venue("BINANCE")
        instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
        position_id = PositionId("POS-001")
        strategy_id = StrategyId("test-strategy")
        
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
        
        usd = Currency.from_str('USD')
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
        
        # Test long position P&L
        current_price = Price.from_str("55000.00")
        pnl = position.calculate_pnl(current_price)
        assert pnl.as_decimal() == Decimal('5000.00')
        
        # Test market value
        market_value = position.calculate_market_value(current_price)
        assert market_value.as_decimal() == Decimal('55000.00')
    
    def test_order_validation(self):
        """Test Order validation."""
        venue = Venue("BINANCE")
        instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
        order_id = ClientOrderId("ORD-001")
        strategy_id = StrategyId("test-strategy")
        
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
        
        # Valid order
        order = Order(
            id=ClientOrderId("ORD-001"),
            instrument=instrument,
            side=OrderSide.BUY,
            quantity=Quantity.from_str("0.1"),
            price=Price.from_str("50000.00"),
            order_type=OrderType.LIMIT,
            time_in_force=TimeInForce.GTC,
            strategy_id=strategy_id,
            trading_mode=TradingMode.LIVE,
            created_time=datetime.now()
        )
        order.validate()  # Should not raise
        
        # Test order type checks
        assert not order.is_market_order()
        assert order.is_limit_order()


class TestDeFiModels:
    """Test DeFi-specific models."""
    
    def test_token_validation(self):
        """Test Token validation."""
        # Valid token
        token = Token(
            address="0x1234567890123456789012345678901234567890",
            symbol="USDC",
            decimals=6,
            name="USD Coin"
        )
        token.validate()  # Should not raise
        
        # Invalid decimals
        with pytest.raises(ValueError, match="Token decimals must be between 0 and 18"):
            invalid_token = Token(
                address="0x1234567890123456789012345678901234567890",
                symbol="USDC",
                decimals=25,
                name="USD Coin"
            )
            invalid_token.validate()
    
    def test_uniswap_pool_validation(self):
        """Test UniswapPool validation."""
        token0 = Token("0x1234", "USDC", 6, "USD Coin")
        token1 = Token("0x5678", "WETH", 18, "Wrapped Ether")
        
        # Valid pool
        pool = UniswapPool(
            address="0xabcd",
            token0=token0,
            token1=token1,
            fee_tier=3000,
            liquidity=Decimal('1000000'),
            sqrt_price_x96=1000000,
            tick=100,
            apy=0.15
        )
        pool.validate()  # Should not raise
        
        # Test fee percentage calculation
        assert pool.get_fee_percentage() == Decimal('0.3')
        
        # Invalid fee tier
        with pytest.raises(ValueError, match="Invalid fee tier"):
            invalid_pool = UniswapPool(
                address="0xabcd",
                token0=token0,
                token1=token1,
                fee_tier=1000,  # Invalid
                liquidity=Decimal('1000000'),
                sqrt_price_x96=1000000,
                tick=100,
                apy=0.15
            )
            invalid_pool.validate()
    
    def test_liquidity_position(self):
        """Test LiquidityPosition model."""
        token0 = Token("0x1234", "USDC", 6, "USD Coin")
        token1 = Token("0x5678", "WETH", 18, "Wrapped Ether")
        strategy_id = StrategyId("uniswap-strategy")
        
        position = LiquidityPosition(
            pool_address="0xabcd",
            token0=token0,
            token1=token1,
            liquidity_amount=Decimal('100000'),
            tick_lower=-1000,
            tick_upper=1000,
            fees_earned=Money(100, Currency.from_str('USD')),
            impermanent_loss=Money(20, Currency.from_str('USD')),
            strategy_id=strategy_id,
            created_time=datetime.now()
        )
        
        # Test range check
        assert position.is_in_range(0)
        assert not position.is_in_range(2000)
        
        # Test net P&L calculation
        net_pnl = position.calculate_net_pnl()
        assert net_pnl.as_decimal() == Decimal('80')


class TestPerpetualModels:
    """Test perpetual contract models."""
    
    def test_funding_rate_validation(self):
        """Test FundingRate validation."""
        venue = Venue("DYDX")
        instrument_id = InstrumentId.from_str("BTCUSD-PERP.DYDX")
        
        instrument = Instrument(
            id=instrument_id,
            symbol="BTCUSD-PERP",
            base_currency="BTC",
            quote_currency="USD",
            price_precision=2,
            size_precision=6,
            min_quantity=Decimal('0.001'),
            max_quantity=Decimal('1000'),
            tick_size=Decimal('0.01'),
            venue=venue
        )
        
        now = datetime.now()
        funding_rate = FundingRate(
            instrument=instrument,
            rate=Decimal('0.0001'),  # 0.01%
            timestamp=now,
            venue=venue,
            next_funding_time=now + timedelta(hours=8)
        )
        funding_rate.validate()  # Should not raise
        
        # Test funding payment calculation
        long_payment = funding_rate.calculate_funding_payment(Decimal('1000'), 'long')
        short_payment = funding_rate.calculate_funding_payment(Decimal('1000'), 'short')
        
        assert long_payment == Decimal('-0.1')  # Long pays
        assert short_payment == Decimal('0.1')   # Short receives
        
        # Test annual rate conversion
        annual_rate = funding_rate.get_annual_rate()
        assert annual_rate == Decimal('0.1095')  # 0.0001 * 1095
    
    def test_perpetual_position(self):
        """Test PerpetualPosition model."""
        venue = Venue("DYDX")
        instrument_id = InstrumentId.from_str("BTCUSD-PERP.DYDX")
        
        instrument = Instrument(
            id=instrument_id,
            symbol="BTCUSD-PERP",
            base_currency="BTC",
            quote_currency="USD",
            price_precision=2,
            size_precision=6,
            min_quantity=Decimal('0.001'),
            max_quantity=Decimal('1000'),
            tick_size=Decimal('0.01'),
            venue=venue
        )
        
        position = PerpetualPosition(
            instrument=instrument,
            side='long',
            size=Decimal('1.0'),
            entry_price=Decimal('50000'),
            mark_price=Decimal('55000'),
            margin=Decimal('10000'),
            leverage=Decimal('5'),
            unrealized_pnl=Decimal('5000'),
            funding_payments=Decimal('-50'),
            venue=venue,
            timestamp=datetime.now()
        )
        
        # Test P&L calculation
        pnl = position.calculate_pnl()
        assert pnl == Decimal('5000')
        
        # Test margin ratio
        margin_ratio = position.calculate_margin_ratio()
        expected_ratio = Decimal('10000') / Decimal('55000')
        assert abs(margin_ratio - expected_ratio) < Decimal('0.0001')
        
        # Test liquidation price
        liq_price = position.calculate_liquidation_price(Decimal('0.05'))
        expected_liq = Decimal('50000') * (1 - Decimal('0.05') / Decimal('5'))
        assert abs(liq_price - expected_liq) < Decimal('0.01')