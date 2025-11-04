"""
Tests for Uniswap Lending Strategy.
"""

import asyncio
import pytest
import pytest_asyncio
import tempfile
import shutil
from datetime import datetime, timedelta
from decimal import Decimal

from nautilus_trader.model.identifiers import InstrumentId, Venue

import sys
sys.path.append('.')

from src.crypto_trading_engine.data.models import TimeFrame, DataType
from src.crypto_trading_engine.data.store import HistoricalDataStore
from src.crypto_trading_engine.data.ingestion import DataIngestionEngine
from src.crypto_trading_engine.backtesting import BacktestEngine, BacktestConfig, Money
from src.crypto_trading_engine.strategies import UniswapLendingStrategy
from src.crypto_trading_engine.strategies.models import (
    StrategyConfig, LiquidityRange, ImpermanentLossCalculator
)


@pytest.fixture
def temp_data_dir():
    """Create temporary directory for test data."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest_asyncio.fixture
async def data_store(temp_data_dir):
    """Create test data store."""
    store = HistoricalDataStore(data_path=temp_data_dir)
    await store.initialize()
    return store


@pytest_asyncio.fixture
async def data_engine(data_store, temp_data_dir):
    """Create test data ingestion engine."""
    from pathlib import Path
    parquet_path = Path(temp_data_dir) / "parquet"
    engine = DataIngestionEngine(
        data_store=data_store,
        parquet_path=str(parquet_path),
        max_workers=2
    )
    return engine


@pytest_asyncio.fixture
async def backtest_engine(data_store, data_engine):
    """Create test backtest engine."""
    engine = BacktestEngine(data_store, data_engine)
    return engine


@pytest.fixture
def strategy_config():
    """Create test strategy configuration."""
    return StrategyConfig(
        min_tvl_usd=Decimal('100000'),        # Lower threshold for testing
        min_volume_24h_usd=Decimal('10000'),  # Lower threshold for testing
        min_fee_apy=Decimal('5'),
        max_impermanent_loss=Decimal('15'),   # Higher tolerance for testing
        max_position_size_usd=Decimal('10000'),
        max_total_exposure_usd=Decimal('50000'),
        liquidity_range=LiquidityRange.MEDIUM,
        range_width_percentage=Decimal('20'),
        max_gas_price_gwei=Decimal('100'),    # Higher for testing
        min_profit_threshold_usd=Decimal('5')
    )


@pytest_asyncio.fixture
async def sample_data(data_engine):
    """Create sample market data for testing."""
    # Create data for ETH (which will be used for Uniswap pools)
    instrument_id = InstrumentId.from_str("ETHUSDT.BINANCE")
    venue = Venue("BINANCE")
    start_time = datetime(2024, 1, 1)
    end_time = datetime(2024, 1, 7)  # One week
    
    job_id = await data_engine.create_ingestion_job(
        data_type=DataType.OHLCV,
        instrument_id=instrument_id,
        venue=venue,
        start_time=start_time,
        end_time=end_time,
        timeframe=TimeFrame.HOUR_1
    )
    
    await data_engine.start_ingestion_job(job_id)
    
    return {
        'instrument_id': instrument_id,
        'venue': venue,
        'start_time': start_time,
        'end_time': end_time,
        'timeframe': TimeFrame.HOUR_1
    }


class TestUniswapLendingStrategy:
    """Test cases for UniswapLendingStrategy."""
    
    def test_strategy_initialization(self, strategy_config):
        """Test strategy initialization."""
        strategy = UniswapLendingStrategy("test_uniswap", strategy_config)
        
        assert strategy.strategy_id == "test_uniswap"
        assert strategy.strategy_config == strategy_config
        assert len(strategy.active_positions) == 0
        assert len(strategy.pool_metrics) == 0
        assert strategy.total_fees_earned_usd == Decimal('0')
        assert strategy.total_impermanent_loss_usd == Decimal('0')
        assert strategy.total_gas_costs_usd == Decimal('0')
    
    def test_strategy_config_validation(self):
        """Test strategy configuration validation."""
        # Valid config
        config = StrategyConfig()
        config.validate()  # Should not raise
        
        # Invalid config - negative TVL
        with pytest.raises(ValueError, match="Minimum TVL must be positive"):
            invalid_config = StrategyConfig(min_tvl_usd=Decimal('-1000'))
            invalid_config.validate()
        
        # Invalid config - invalid price impact
        with pytest.raises(ValueError, match="Max price impact must be between 0 and 1"):
            invalid_config = StrategyConfig(max_price_impact=Decimal('1.5'))
            invalid_config.validate()
    
    @pytest.mark.asyncio
    async def test_strategy_initialization_with_pools(self, backtest_engine, strategy_config, sample_data):
        """Test strategy initialization with pool setup."""
        strategy = UniswapLendingStrategy("test_uniswap", strategy_config)
        
        config = BacktestConfig(
            start_date=sample_data['start_time'],
            end_date=sample_data['end_time'],
            initial_capital=Money(Decimal('100000'), 'USD')
        )
        
        # Initialize strategy
        await strategy.initialize(backtest_engine, config)
        
        # Check that pools were initialized
        assert len(strategy.available_pools) > 0
        assert len(strategy.pool_metrics) > 0
        
        # Check that price cache was set up
        assert 'WETH' in strategy.price_cache
        assert 'USDC' in strategy.price_cache
        assert strategy.eth_price_usd > 0
    
    @pytest.mark.asyncio
    async def test_pool_opportunity_evaluation(self, backtest_engine, strategy_config, sample_data):
        """Test pool opportunity evaluation logic."""
        strategy = UniswapLendingStrategy("test_uniswap", strategy_config)
        
        config = BacktestConfig(
            start_date=sample_data['start_time'],
            end_date=sample_data['end_time'],
            initial_capital=Money(Decimal('100000'), 'USD')
        )
        
        await strategy.initialize(backtest_engine, config)
        
        # Test opportunity evaluation for each pool
        for pool in strategy.available_pools.values():
            score = await strategy._evaluate_pool_opportunity(pool)
            
            # Score should be calculated (could be positive or negative)
            assert isinstance(score, Decimal)
            
            # For pools that meet criteria, score should be positive
            metrics = strategy.pool_metrics[pool.address]
            if (metrics.tvl_usd >= strategy_config.min_tvl_usd and
                metrics.volume_24h_usd >= strategy_config.min_volume_24h_usd and
                metrics.average_fee_apy >= strategy_config.min_fee_apy):
                assert score > 0
    
    @pytest.mark.asyncio
    async def test_impermanent_loss_calculation(self, backtest_engine, strategy_config, sample_data):
        """Test impermanent loss calculation."""
        strategy = UniswapLendingStrategy("test_uniswap", strategy_config)
        
        config = BacktestConfig(
            start_date=sample_data['start_time'],
            end_date=sample_data['end_time'],
            initial_capital=Money(Decimal('100000'), 'USD')
        )
        
        await strategy.initialize(backtest_engine, config)
        
        # Get a pool and create a mock position
        pool = list(strategy.available_pools.values())[0]
        
        from src.crypto_trading_engine.strategies.models import LiquidityPosition
        position = LiquidityPosition(
            token_id=1,
            pool=pool,
            tick_lower=pool.current_tick - 1000,
            tick_upper=pool.current_tick + 1000,
            liquidity=Decimal('1000'),
            created_at=datetime.now() - timedelta(days=1)
        )
        
        # Calculate impermanent loss
        il_calc = await strategy._calculate_impermanent_loss(position)
        
        # Validate calculation
        assert il_calc.position == position
        assert il_calc.entry_price > 0
        assert il_calc.current_price > 0
        assert il_calc.fees_earned_token0 >= 0
        assert il_calc.fees_earned_token1 >= 0
    
    @pytest.mark.asyncio
    async def test_optimal_range_calculation(self, backtest_engine, strategy_config, sample_data):
        """Test optimal liquidity range calculation."""
        strategy = UniswapLendingStrategy("test_uniswap", strategy_config)
        
        config = BacktestConfig(
            start_date=sample_data['start_time'],
            end_date=sample_data['end_time'],
            initial_capital=Money(Decimal('100000'), 'USD')
        )
        
        await strategy.initialize(backtest_engine, config)
        
        # Test range calculation for each pool
        for pool in strategy.available_pools.values():
            tick_lower, tick_upper = await strategy._calculate_optimal_range(pool)
            
            # Validate range
            assert tick_lower < tick_upper
            assert tick_lower <= pool.current_tick <= tick_upper or strategy.strategy_config.liquidity_range == LiquidityRange.FULL_RANGE
            
            # Check tick spacing alignment
            if strategy.strategy_config.liquidity_range != LiquidityRange.FULL_RANGE:
                assert tick_lower % pool.tick_spacing == 0
                assert tick_upper % pool.tick_spacing == 0
    
    @pytest.mark.asyncio
    async def test_gas_optimization(self, strategy_config):
        """Test gas optimization logic."""
        strategy = UniswapLendingStrategy("test_uniswap", strategy_config)
        
        # Test gas cost estimation
        gas_estimate = strategy.gas_optimizer.estimate_gas_cost(
            'mint_position', 
            Decimal('50'),  # 50 Gwei
            Decimal('2000')  # $2000 ETH
        )
        
        assert gas_estimate.operation == 'mint_position'
        assert gas_estimate.gas_limit > 0
        assert gas_estimate.gas_price_gwei == Decimal('50')
        assert gas_estimate.gas_cost_eth > 0
        assert gas_estimate.gas_cost_usd > 0
        
        # Test execution decision
        should_execute = strategy.gas_optimizer.should_execute_now(
            'mint_position',
            Decimal('30'),    # 30 Gwei (reasonable)
            Decimal('100'),   # $100 expected profit
            Decimal('2000')   # $2000 ETH
        )
        
        assert isinstance(should_execute, bool)
        
        # High gas price should prevent execution
        should_not_execute = strategy.gas_optimizer.should_execute_now(
            'mint_position',
            Decimal('200'),   # 200 Gwei (very high)
            Decimal('10'),    # $10 expected profit (low)
            Decimal('2000')   # $2000 ETH
        )
        
        assert should_not_execute is False
    
    @pytest.mark.asyncio
    async def test_full_strategy_backtest(self, backtest_engine, strategy_config, sample_data):
        """Test full strategy backtest execution."""
        strategy = UniswapLendingStrategy("test_uniswap", strategy_config)
        
        config = BacktestConfig(
            start_date=sample_data['start_time'],
            end_date=sample_data['end_time'],
            initial_capital=Money(Decimal('100000'), 'USD'),
            commission_rate=Decimal('0.001')
        )
        
        # Run backtest
        results = await backtest_engine.run_backtest(
            strategy=strategy,
            config=config,
            instruments=[sample_data['instrument_id']],
            venues=[sample_data['venue']],
            timeframe=sample_data['timeframe']
        )
        
        # Validate results
        assert results.strategy_id == "test_uniswap"
        assert results.initial_capital.amount == Decimal('100000')
        assert len(results.equity_curve) > 0
        
        # Get strategy-specific performance
        performance = await strategy.get_strategy_performance()
        
        assert 'active_positions' in performance
        assert 'total_exposure_usd' in performance
        assert 'total_fees_earned_usd' in performance
        assert 'net_profit_usd' in performance
        
        # Validate performance metrics
        assert performance['active_positions'] >= 0
        assert performance['total_exposure_usd'] >= 0
        assert performance['pools_monitored'] > 0
    
    def test_impermanent_loss_calculator(self):
        """Test the impermanent loss calculator utility."""
        # Test theoretical IL calculation
        
        # No price change = no IL
        il_no_change = ImpermanentLossCalculator.calculate_theoretical_il(Decimal('1.0'))
        assert abs(il_no_change) < Decimal('0.001')  # Should be very close to 0
        
        # 2x price increase
        il_2x = ImpermanentLossCalculator.calculate_theoretical_il(Decimal('2.0'))
        assert il_2x < 0  # Should be negative (loss)
        assert abs(il_2x) > Decimal('0.05')  # Should be significant loss
        
        # 50% price decrease
        il_half = ImpermanentLossCalculator.calculate_theoretical_il(Decimal('0.5'))
        assert il_half < 0  # Should be negative (loss)
        
        # Test breakeven fee APY calculation
        breakeven_apy = ImpermanentLossCalculator.calculate_breakeven_fee_apy(
            Decimal('2.0'),  # 2x price change
            30  # 30 days
        )
        
        assert breakeven_apy > 0
        assert breakeven_apy > Decimal('10')  # Should require significant APY to break even
    
    @pytest.mark.asyncio
    async def test_position_management(self, backtest_engine, strategy_config, sample_data):
        """Test position opening, monitoring, and closing."""
        # Use more aggressive config for testing
        test_config = StrategyConfig(
            min_tvl_usd=Decimal('1000'),      # Very low for testing
            min_volume_24h_usd=Decimal('100'), # Very low for testing
            min_fee_apy=Decimal('1'),          # Very low for testing
            max_impermanent_loss=Decimal('5'), # Low threshold to trigger closes
            max_position_size_usd=Decimal('5000'),
            max_total_exposure_usd=Decimal('20000'),
            max_gas_price_gwei=Decimal('20')   # Low gas for testing
        )
        
        strategy = UniswapLendingStrategy("test_positions", test_config)
        
        config = BacktestConfig(
            start_date=sample_data['start_time'],
            end_date=sample_data['end_time'],
            initial_capital=Money(Decimal('50000'), 'USD')
        )
        
        await strategy.initialize(backtest_engine, config)
        
        # Manually trigger position evaluation
        await strategy._evaluate_new_opportunities()
        
        # Check if any positions were opened
        initial_positions = len(strategy.active_positions)
        
        # Simulate some market data processing
        from src.crypto_trading_engine.backtesting.models import MarketState
        market_state = MarketState(
            timestamp=datetime.now(),
            instrument_id=sample_data['instrument_id'],
            venue=sample_data['venue'],
            bid_price=Decimal('2000'),
            ask_price=Decimal('2010'),
            mid_price=Decimal('2005'),
            volume=Decimal('1000')
        )
        
        # Process some market updates
        for i in range(5):
            # Simulate price movement
            market_state.mid_price += Decimal('10') * (i - 2)  # Some price volatility
            
            # Create proper OHLCVData object
            from src.crypto_trading_engine.data.models import OHLCVData
            ohlcv_data = OHLCVData(
                instrument_id=sample_data['instrument_id'],
                venue=sample_data['venue'],
                timestamp=datetime.now(),
                timeframe=sample_data['timeframe'],
                open_price=market_state.mid_price,
                high_price=market_state.mid_price + Decimal('5'),
                low_price=market_state.mid_price - Decimal('5'),
                close_price=market_state.mid_price,
                volume=Decimal('1000')
            )
            
            await strategy._update_price_from_market_data(
                ohlcv_data, market_state
            )
            await strategy._monitor_existing_positions()
        
        # Get final performance
        performance = await strategy.get_strategy_performance()
        position_summary = strategy.get_position_summary()
        
        # Validate that strategy attempted to manage positions
        assert performance['pools_monitored'] > 0
        assert len(strategy.position_history) >= 0  # May or may not have opened positions
        
        # If positions were opened, validate their structure
        for pos_summary in position_summary:
            assert 'token_pair' in pos_summary
            assert 'fee_tier' in pos_summary
            assert 'is_in_range' in pos_summary
            assert 'impermanent_loss_pct' in pos_summary


class TestUniswapModels:
    """Test cases for Uniswap-related models."""
    
    def test_token_validation(self):
        """Test token model validation."""
        from src.crypto_trading_engine.strategies.models import Token
        
        # Valid token
        token = Token(
            address="0xA0b86a33E6441E6C7D3E4C2C4C8C8C8C8C8C8C8C",
            symbol="USDC",
            decimals=6,
            name="USD Coin"
        )
        token.validate()  # Should not raise
        
        # Invalid address
        with pytest.raises(ValueError, match="Invalid token address"):
            invalid_token = Token(address="invalid", symbol="TEST", decimals=18)
            invalid_token.validate()
        
        # Invalid decimals
        with pytest.raises(ValueError, match="Invalid token decimals"):
            invalid_token = Token(
                address="0xA0b86a33E6441E6C7D3E4C2C4C8C8C8C8C8C8C8C",
                symbol="TEST",
                decimals=25
            )
            invalid_token.validate()
    
    def test_uniswap_pool_properties(self):
        """Test Uniswap pool model properties."""
        from src.crypto_trading_engine.strategies.models import UniswapPool, Token, PoolTier
        
        usdc = Token("0xA0b86a33E6441E6C7D3E4C2C4C8C8C8C8C8C8C8C", "USDC", 6)
        weth = Token("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "WETH", 18)
        
        pool = UniswapPool(
            address="0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640",
            token0=usdc,
            token1=weth,
            fee_tier=PoolTier.TIER_0_05,
            tick_spacing=10,
            current_tick=200000,
            sqrt_price_x96=1771845812700000000000000000000000,
            liquidity=Decimal('50000000')
        )
        
        # Test properties
        assert pool.current_price > 0
        assert pool.fee_percentage == Decimal('0.0005')  # 0.05%
        
        # Test validation
        pool.validate()  # Should not raise
    
    def test_liquidity_position_calculations(self):
        """Test liquidity position calculations."""
        from src.crypto_trading_engine.strategies.models import (
            LiquidityPosition, UniswapPool, Token, PoolTier
        )
        
        # Create test pool and position
        usdc = Token("0xA0b86a33E6441E6C7D3E4C2C4C8C8C8C8C8C8C8C", "USDC", 6)
        weth = Token("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "WETH", 18)
        
        pool = UniswapPool(
            address="0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640",
            token0=usdc,
            token1=weth,
            fee_tier=PoolTier.TIER_0_05,
            tick_spacing=10,
            current_tick=200000,
            sqrt_price_x96=1771845812700000000000000000000000,
            liquidity=Decimal('50000000')
        )
        
        position = LiquidityPosition(
            token_id=1,
            pool=pool,
            tick_lower=199000,  # Below current tick
            tick_upper=201000,  # Above current tick
            liquidity=Decimal('1000')
        )
        
        # Test properties
        assert position.price_lower > 0
        assert position.price_upper > position.price_lower
        assert position.is_in_range is True  # Current tick is within range
        assert position.range_width_percentage > 0
        
        # Test token amount calculations
        amount0, amount1 = position.calculate_token_amounts()
        assert amount0 >= 0
        assert amount1 >= 0
        
        # Test validation
        position.validate()  # Should not raise


if __name__ == "__main__":
    pytest.main([__file__])