"""
Test live market data integration.

This test verifies that the live data sources can successfully connect to
external APIs and retrieve real market data.
"""

import asyncio
import pytest
import sys
sys.path.append('.')

from decimal import Decimal
from src.crypto_trading_engine.data.live_sources import LivePriceDataSource, LivePoolDataSource
from src.crypto_trading_engine.data.aggregator import MarketDataAggregator
from src.crypto_trading_engine.models.trading_mode import TradingMode


class TestLiveMarketData:
    """Test live market data functionality."""
    
    @pytest.mark.asyncio
    async def test_live_price_data_source(self):
        """Test live price data source without adapters."""
        # Create live price source without Binance adapter (uses backup APIs)
        price_source = LivePriceDataSource()
        
        try:
            await price_source.connect()
            
            # Test major token prices
            tokens_to_test = ['WETH', 'BTC', 'USDC']
            
            for token in tokens_to_test:
                price = await price_source.get_token_price_usd(token)
                print(f"✅ {token} price: ${price}")
                
                # Validate price is reasonable
                assert price > 0, f"{token} price should be positive"
                
                if token in ['WETH', 'ETH']:
                    assert 100 <= price <= 10000, f"ETH price ${price} seems unreasonable"
                elif token in ['BTC', 'WBTC']:
                    assert 10000 <= price <= 200000, f"BTC price ${price} seems unreasonable"
                elif token in ['USDC', 'USDT']:
                    assert 0.95 <= price <= 1.05, f"Stablecoin price ${price} seems unreasonable"
            
            # Test gas price
            gas_price = await price_source.get_gas_price_gwei()
            print(f"✅ Gas price: {gas_price} Gwei")
            assert 1 <= gas_price <= 1000, f"Gas price {gas_price} Gwei seems unreasonable"
            
        finally:
            await price_source.disconnect()
    
    @pytest.mark.asyncio
    async def test_market_data_aggregator_live_mode(self):
        """Test market data aggregator in live mode."""
        # Create aggregator without adapters (uses backup APIs)
        aggregator = MarketDataAggregator(trading_mode=TradingMode.LIVE)
        
        try:
            await aggregator.connect()
            
            # Test price retrieval through aggregator
            eth_price = await aggregator.get_token_price_usd('WETH')
            usdc_price = await aggregator.get_token_price_usd('USDC')
            gas_price = await aggregator.get_gas_price_gwei()
            
            print(f"✅ Aggregator ETH price: ${eth_price}")
            print(f"✅ Aggregator USDC price: ${usdc_price}")
            print(f"✅ Aggregator gas price: {gas_price} Gwei")
            
            # Validate prices
            assert eth_price > 0, "ETH price should be positive"
            assert usdc_price > 0, "USDC price should be positive"
            assert gas_price > 0, "Gas price should be positive"
            
            # Test performance tracking
            performance = aggregator.get_source_performance()
            print(f"✅ Source performance: {performance}")
            
        finally:
            await aggregator.disconnect()
    
    @pytest.mark.asyncio
    async def test_price_validation(self):
        """Test price validation and failover."""
        aggregator = MarketDataAggregator(trading_mode=TradingMode.LIVE)
        
        try:
            await aggregator.connect()
            
            # Test with valid token
            valid_price = await aggregator.get_token_price_usd('WETH')
            assert valid_price > 0, "Should get valid price for WETH"
            
            # Test with invalid/unknown token
            invalid_price = await aggregator.get_token_price_usd('INVALID_TOKEN')
            # Should return 0 for unknown tokens
            assert invalid_price == 0, "Should return 0 for invalid tokens"
            
        finally:
            await aggregator.disconnect()
    
    @pytest.mark.asyncio
    async def test_caching_behavior(self):
        """Test price caching behavior."""
        price_source = LivePriceDataSource()
        
        try:
            await price_source.connect()
            
            # Get price twice quickly - second should be cached
            import time
            
            start_time = time.time()
            price1 = await price_source.get_token_price_usd('WETH')
            first_call_time = time.time() - start_time
            
            start_time = time.time()
            price2 = await price_source.get_token_price_usd('WETH')
            second_call_time = time.time() - start_time
            
            print(f"✅ First call: {first_call_time:.3f}s, Second call: {second_call_time:.3f}s")
            print(f"✅ Price1: ${price1}, Price2: ${price2}")
            
            # Prices should be the same (cached)
            assert price1 == price2, "Cached prices should be identical"
            
            # Second call should be faster (cached)
            assert second_call_time < first_call_time, "Cached call should be faster"
            
        finally:
            await price_source.disconnect()


async def run_live_data_demo():
    """Run a comprehensive live data demonstration."""
    print("🌐 Live Market Data Integration Test")
    print("=" * 60)
    
    # Test 1: Basic price retrieval
    print("\n📊 Test 1: Basic Price Retrieval")
    print("-" * 40)
    
    price_source = LivePriceDataSource()
    await price_source.connect()
    
    tokens = ['WETH', 'BTC', 'USDC']
    prices = {}
    
    for token in tokens:
        try:
            price = await price_source.get_token_price_usd(token)
            prices[token] = price
            print(f"✅ {token}: ${price:,.2f}")
        except Exception as e:
            print(f"❌ {token}: Failed - {e}")
    
    # Test gas price
    try:
        gas_price = await price_source.get_gas_price_gwei()
        print(f"✅ Gas Price: {gas_price} Gwei")
    except Exception as e:
        print(f"❌ Gas Price: Failed - {e}")
    
    await price_source.disconnect()
    
    # Test 2: Market Data Aggregator
    print("\n🔄 Test 2: Market Data Aggregator")
    print("-" * 40)
    
    aggregator = MarketDataAggregator(trading_mode=TradingMode.LIVE)
    await aggregator.connect()
    
    try:
        # Test aggregated price retrieval
        for token in tokens:
            price = await aggregator.get_token_price_usd(token)
            cached_price = prices.get(token, 0)
            diff = abs(price - cached_price) if cached_price > 0 else 0
            print(f"✅ {token}: ${price:,.2f} (diff: ${diff:.2f})")
        
        # Test performance metrics
        performance = aggregator.get_source_performance()
        print(f"✅ Performance: {performance}")
        
    finally:
        await aggregator.disconnect()
    
    # Test 3: Error Handling
    print("\n🛡️  Test 3: Error Handling & Validation")
    print("-" * 40)
    
    aggregator = MarketDataAggregator(trading_mode=TradingMode.LIVE)
    await aggregator.connect()
    
    try:
        # Test invalid token
        invalid_price = await aggregator.get_token_price_usd('INVALID_TOKEN_XYZ')
        print(f"✅ Invalid token handling: ${invalid_price}")
        
        # Test mode switching
        print(f"✅ Current mode: {aggregator.trading_mode}")
        aggregator.switch_trading_mode(TradingMode.BACKTEST)
        print(f"✅ Switched to: {aggregator.trading_mode}")
        
        # Test backtest mode price (should use cached/default values)
        backtest_price = await aggregator.get_token_price_usd('WETH')
        print(f"✅ Backtest mode price: ${backtest_price}")
        
    finally:
        await aggregator.disconnect()
    
    print("\n🎉 Live Market Data Integration Test Complete!")
    print("=" * 60)


if __name__ == "__main__":
    # Run the demo
    asyncio.run(run_live_data_demo())