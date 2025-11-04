# How to Run a Backtest

This guide shows you how to run backtests using the crypto trading engine, from simple examples to advanced configurations.

## Quick Start

### 1. Run the Simple Test

The easiest way to see backtesting in action:

```bash
python3 tests/test_backtesting_simple.py
```

This runs a basic Buy and Hold strategy test with sample data.

### 2. Run the Comprehensive Demo

For a full demonstration with multiple strategies:

```bash
python3 examples/backtesting_demo.py
```

This runs 3 different strategies and compares their performance.

## Step-by-Step Guide

### Step 1: Set Up Your Environment

```python
import asyncio
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from nautilus_trader.model.identifiers import InstrumentId, Venue

# Import the trading engine components
from src.crypto_trading_engine.data.models import DataType, TimeFrame
from src.crypto_trading_engine.data.store import HistoricalDataStore
from src.crypto_trading_engine.data.ingestion import DataIngestionEngine
from src.crypto_trading_engine.backtesting import (
    BacktestEngine, BacktestConfig, Money, BuyAndHoldStrategy
)
```

### Step 2: Initialize the Data Infrastructure

```python
async def setup_backtesting():
    # Create data storage
    data_path = "my_backtest_data"
    store = HistoricalDataStore(data_path=data_path)
    await store.initialize()
    
    # Create data ingestion engine
    parquet_path = Path(data_path) / "parquet"
    data_engine = DataIngestionEngine(
        data_store=store,
        parquet_path=str(parquet_path)
    )
    
    # Create backtesting engine
    backtest_engine = BacktestEngine(store, data_engine)
    
    return backtest_engine, data_engine
```

### Step 3: Create Sample Data

```python
async def create_sample_data(data_engine):
    # Define what to backtest
    instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
    venue = Venue("BINANCE")
    start_time = datetime(2024, 1, 1)
    end_time = datetime(2024, 1, 7)  # One week
    
    # Create data ingestion job
    job_id = await data_engine.create_ingestion_job(
        data_type=DataType.OHLCV,
        instrument_id=instrument_id,
        venue=venue,
        start_time=start_time,
        end_time=end_time,
        timeframe=TimeFrame.HOUR_1
    )
    
    # Run the ingestion
    await data_engine.start_ingestion_job(job_id)
    
    return instrument_id, venue, start_time, end_time
```

### Step 4: Configure Your Backtest

```python
def create_backtest_config(start_time, end_time):
    return BacktestConfig(
        start_date=start_time,
        end_date=end_time,
        initial_capital=Money(Decimal('100000'), 'USD'),  # $100,000
        commission_rate=Decimal('0.001'),    # 0.1% commission
        slippage_rate=Decimal('0.0005'),     # 0.05% slippage
        market_impact_rate=Decimal('0.0001') # 0.01% market impact
    )
```

### Step 5: Choose or Create a Strategy

```python
# Use a built-in strategy
strategy = BuyAndHoldStrategy("my_bnh_test", {"allocation": 0.95})

# Or create your own (see Custom Strategy section below)
```

### Step 6: Run the Backtest

```python
async def run_my_backtest():
    # Set up everything
    backtest_engine, data_engine = await setup_backtesting()
    instrument_id, venue, start_time, end_time = await create_sample_data(data_engine)
    config = create_backtest_config(start_time, end_time)
    strategy = BuyAndHoldStrategy("my_test")
    
    # Run the backtest
    results = await backtest_engine.run_backtest(
        strategy=strategy,
        config=config,
        instruments=[instrument_id],
        venues=[venue],
        timeframe=TimeFrame.HOUR_1
    )
    
    # Print results
    print(f"Strategy: {results.strategy_id}")
    print(f"Total Return: {results.return_percentage:.2f}%")
    print(f"Sharpe Ratio: {results.sharpe_ratio:.2f}")
    print(f"Max Drawdown: {results.max_drawdown * 100:.2f}%")
    print(f"Total Trades: {results.total_trades}")
    
    return results

# Run it
if __name__ == "__main__":
    asyncio.run(run_my_backtest())
```

## Complete Example Script

Create a file called `my_backtest.py`:

```python
#!/usr/bin/env python3
import asyncio
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from nautilus_trader.model.identifiers import InstrumentId, Venue

import sys
sys.path.append('.')

from src.crypto_trading_engine.data.models import DataType, TimeFrame
from src.crypto_trading_engine.data.store import HistoricalDataStore
from src.crypto_trading_engine.data.ingestion import DataIngestionEngine
from src.crypto_trading_engine.backtesting import (
    BacktestEngine, BacktestConfig, Money, BuyAndHoldStrategy
)

async def main():
    print("🚀 Starting My Backtest")
    
    # 1. Set up data infrastructure
    data_path = "my_backtest_data"
    store = HistoricalDataStore(data_path=data_path)
    await store.initialize()
    
    parquet_path = Path(data_path) / "parquet"
    data_engine = DataIngestionEngine(
        data_store=store,
        parquet_path=str(parquet_path)
    )
    
    backtest_engine = BacktestEngine(store, data_engine)
    
    # 2. Create sample data
    instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
    venue = Venue("BINANCE")
    start_time = datetime(2024, 1, 1)
    end_time = datetime(2024, 1, 7)
    
    job_id = await data_engine.create_ingestion_job(
        data_type=DataType.OHLCV,
        instrument_id=instrument_id,
        venue=venue,
        start_time=start_time,
        end_time=end_time,
        timeframe=TimeFrame.HOUR_1
    )
    await data_engine.start_ingestion_job(job_id)
    print("✅ Sample data created")
    
    # 3. Configure backtest
    config = BacktestConfig(
        start_date=start_time,
        end_date=end_time,
        initial_capital=Money(Decimal('100000'), 'USD'),
        commission_rate=Decimal('0.001')
    )
    
    # 4. Create strategy
    strategy = BuyAndHoldStrategy("my_test")
    
    # 5. Run backtest
    print("🔄 Running backtest...")
    results = await backtest_engine.run_backtest(
        strategy=strategy,
        config=config,
        instruments=[instrument_id],
        venues=[venue],
        timeframe=TimeFrame.HOUR_1
    )
    
    # 6. Display results
    print(f"\n📊 RESULTS:")
    print(f"Strategy: {results.strategy_id}")
    print(f"Initial Capital: ${results.initial_capital.amount:,.2f}")
    print(f"Final Capital: ${results.final_capital.amount:,.2f}")
    print(f"Total Return: {results.return_percentage:.2f}%")
    print(f"Sharpe Ratio: {results.sharpe_ratio:.2f}")
    print(f"Max Drawdown: {results.max_drawdown * 100:.2f}%")
    print(f"Win Rate: {results.win_rate * 100:.1f}%")
    
    print("✅ Backtest completed!")

if __name__ == "__main__":
    asyncio.run(main())
```

Then run it:

```bash
python3 my_backtest.py
```

## Creating Custom Strategies

### Simple Custom Strategy

```python
from src.crypto_trading_engine.backtesting import Strategy
from decimal import Decimal

class MySimpleStrategy(Strategy):
    def __init__(self, strategy_id="my_strategy"):
        super().__init__(strategy_id, {"threshold": 0.02})  # 2% threshold
        self.last_price = None
    
    async def on_initialize(self, config):
        self.log_info("Initializing My Simple Strategy")
        self.last_price = None
    
    async def on_market_data(self, data, market_state):
        current_price = float(data.close_price)
        
        if self.last_price is None:
            self.last_price = current_price
            return
        
        # Calculate price change
        price_change = (current_price - self.last_price) / self.last_price
        
        # Simple logic: buy if price dropped more than threshold
        if price_change < -self.config["threshold"]:
            portfolio_value = self.get_portfolio_value()
            quantity = (portfolio_value.amount * Decimal('0.1')) / Decimal(str(current_price))
            
            await self.submit_market_order(
                str(data.instrument_id), str(data.venue), 'buy', float(quantity)
            )
            self.log_info(f"Bought {quantity} at {current_price} (dropped {price_change:.2%})")
        
        self.last_price = current_price
```

### Advanced Custom Strategy

```python
class MovingAverageStrategy(Strategy):
    def __init__(self, strategy_id="ma_strategy"):
        super().__init__(strategy_id, {
            "short_window": 10,
            "long_window": 20,
            "position_size": 0.5
        })
        self.prices = []
        self.position = None
    
    async def on_initialize(self, config):
        self.log_info(f"MA Strategy: {self.config['short_window']}/{self.config['long_window']}")
        self.prices = []
        self.position = None
    
    async def on_market_data(self, data, market_state):
        price = float(data.close_price)
        self.prices.append(price)
        
        # Keep only what we need
        max_window = max(self.config['short_window'], self.config['long_window'])
        if len(self.prices) > max_window * 2:
            self.prices = self.prices[-max_window * 2:]
        
        # Need enough data
        if len(self.prices) < self.config['long_window']:
            return
        
        # Calculate moving averages
        short_ma = sum(self.prices[-self.config['short_window']:]) / self.config['short_window']
        long_ma = sum(self.prices[-self.config['long_window']:]) / self.config['long_window']
        
        instrument_str = str(data.instrument_id)
        venue_str = str(data.venue)
        
        # Trading logic
        if short_ma > long_ma and not self.position:
            # Go long
            portfolio_value = self.get_portfolio_value()
            position_value = portfolio_value.amount * Decimal(str(self.config['position_size']))
            quantity = position_value / Decimal(str(price))
            
            await self.submit_market_order(instrument_str, venue_str, 'buy', float(quantity))
            self.position = 'long'
            self.log_info(f"Opened long position: {quantity} at {price}")
            
        elif short_ma < long_ma and self.position == 'long':
            # Close long
            current_position = self.get_position(instrument_str)
            if current_position:
                await self.submit_market_order(
                    instrument_str, venue_str, 'sell', float(current_position.quantity)
                )
                self.position = None
                self.log_info(f"Closed long position at {price}")
```

## Configuration Options

### BacktestConfig Parameters

```python
config = BacktestConfig(
    start_date=datetime(2024, 1, 1),
    end_date=datetime(2024, 1, 31),
    initial_capital=Money(Decimal('100000'), 'USD'),
    
    # Trading costs
    commission_rate=Decimal('0.001'),      # 0.1% per trade
    slippage_rate=Decimal('0.0005'),       # 0.05% slippage
    market_impact_rate=Decimal('0.0001'),  # 0.01% market impact
    
    # Risk management
    max_position_size=Decimal('0.2'),      # Max 20% per position
    max_leverage=Decimal('2.0'),           # Max 2x leverage
    
    # Performance calculation
    risk_free_rate=Decimal('0.02')         # 2% annual risk-free rate
)
```

### Multiple Instruments

```python
# Test with multiple cryptocurrencies
instruments = [
    InstrumentId.from_str("BTCUSDT.BINANCE"),
    InstrumentId.from_str("ETHUSDT.BINANCE"),
    InstrumentId.from_str("ADAUSDT.BINANCE")
]

venues = [Venue("BINANCE")] * len(instruments)

results = await backtest_engine.run_backtest(
    strategy=strategy,
    config=config,
    instruments=instruments,
    venues=venues,
    timeframe=TimeFrame.HOUR_1
)
```

### Different Timeframes

```python
# Test with different data granularity
timeframes = [
    TimeFrame.MINUTE_15,  # 15-minute bars
    TimeFrame.HOUR_1,     # 1-hour bars  
    TimeFrame.HOUR_4,     # 4-hour bars
    TimeFrame.DAY_1       # Daily bars
]

for tf in timeframes:
    results = await backtest_engine.run_backtest(
        strategy=strategy,
        config=config,
        instruments=[instrument_id],
        venues=[venue],
        timeframe=tf
    )
    print(f"{tf.value}: {results.return_percentage:.2f}% return")
```

## Performance Analysis

### Key Metrics Explained

- **Total Return**: Overall percentage gain/loss
- **Annualized Return**: Return scaled to annual basis
- **Sharpe Ratio**: Risk-adjusted return (higher is better)
- **Sortino Ratio**: Downside risk-adjusted return
- **Max Drawdown**: Largest peak-to-trough decline
- **Calmar Ratio**: Annual return / max drawdown
- **Win Rate**: Percentage of profitable trades
- **Profit Factor**: Gross profit / gross loss

### Accessing Detailed Results

```python
# Get detailed trade information
for trade in results.trades:
    print(f"{trade.timestamp}: {trade.side.value} {trade.quantity} @ ${trade.price}")

# Get equity curve for plotting
equity_curve = results.equity_curve
timestamps = [point[0] for point in equity_curve]
values = [point[1] for point in equity_curve]

# Get final positions
for position in results.positions:
    if position.side.value != 'flat':
        print(f"Final position: {position.instrument_id} - {position.side.value} {position.quantity}")
```

## Tips and Best Practices

### 1. Start Simple
- Begin with Buy and Hold strategy
- Use short time periods for testing
- Gradually add complexity

### 2. Validate Your Strategy
- Test on different time periods
- Check performance across market conditions
- Compare against benchmarks

### 3. Consider Transaction Costs
- Include realistic commission rates
- Account for slippage on larger orders
- Model market impact appropriately

### 4. Risk Management
- Set appropriate position size limits
- Monitor drawdown levels
- Use stop-losses in strategies

### 5. Performance Analysis
- Focus on risk-adjusted returns (Sharpe ratio)
- Analyze drawdown periods
- Check trade distribution

## Troubleshooting

### Common Issues

1. **No data available**: Make sure data ingestion completed successfully
2. **Strategy not trading**: Check strategy logic and thresholds
3. **Poor performance**: Review transaction costs and strategy parameters
4. **Memory issues**: Use shorter time periods or fewer instruments

### Debug Mode

Add logging to see what's happening:

```python
import logging
logging.basicConfig(level=logging.INFO)

# Your strategy will now log its decisions
```

### Validation

Always validate your results:

```python
# Check if results make sense
assert results.initial_capital.amount > 0
assert len(results.equity_curve) > 0
assert results.total_trades >= 0
assert 0 <= results.win_rate <= 1
```

This guide should get you started with backtesting! The system is designed to be flexible and extensible, so you can build sophisticated trading strategies and analyze their performance comprehensively.