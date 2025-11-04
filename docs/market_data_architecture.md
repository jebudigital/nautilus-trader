# Market Data Architecture

## Overview

The crypto trading engine uses a sophisticated market data architecture that seamlessly supports backtesting, paper trading, and live trading modes. The system provides unified interfaces with automatic failover, data validation, and multi-source aggregation.

## Architecture Components

### 🏗️ **Core Components**

```
┌─────────────────────────────────────────────────────────────┐
│                    Strategy Layer                           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │         UniswapLendingStrategy                      │   │
│  │    (Uses MarketDataAggregator interface)           │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                MarketDataAggregator                         │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐ │
│  │  Data Sources   │  │   Validation    │  │  Failover   │ │
│  │   Management    │  │   & Quality     │  │  & Caching  │ │
│  └─────────────────┘  └─────────────────┘  └─────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Data Sources                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐ │
│  │ BacktestData    │  │  LivePriceData  │  │ LivePoolData│ │
│  │    Source       │  │     Source      │  │   Source    │ │
│  └─────────────────┘  └─────────────────┘  └─────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                Exchange Adapters & APIs                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐ │
│  │    Binance      │  │    Uniswap      │  │  External   │ │
│  │    Adapter      │  │    Adapter      │  │    APIs     │ │
│  └─────────────────┘  └─────────────────┘  └─────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 📊 **Data Flow by Trading Mode**

#### Backtesting Mode
```
Historical Data Store → BacktestDataSource → MarketDataAggregator → Strategy
```
- Uses stored OHLCV data from Parquet/SQLite
- Simulated price updates and gas costs
- Deterministic and reproducible

#### Paper Trading Mode
```
Live APIs → LiveDataSources → MarketDataAggregator → Strategy
```
- Real-time price feeds from exchanges
- Live gas price monitoring
- Simulated order execution

#### Live Trading Mode
```
Live APIs → LiveDataSources → MarketDataAggregator → Strategy → Real Orders
```
- Real-time market data
- Actual order execution
- Production monitoring and alerting

## Data Sources

### 🔄 **BacktestDataSource**
Used for backtesting with historical data:
- **Price Data**: Manual price updates for simulation
- **Gas Data**: Configurable gas price simulation
- **Pool Data**: Static pool configurations
- **Caching**: In-memory cache for fast access

```python
# Example usage
backtest_source = BacktestDataSource()
backtest_source.update_token_price('WETH', Decimal('2000'))
backtest_source.update_gas_price(Decimal('20'))
```

### 🌐 **LivePriceDataSource**
Real-time price data from multiple sources:
- **Primary**: Binance WebSocket streams
- **Backup**: CoinGecko, Coinbase APIs
- **Gas Prices**: Etherscan, MetaMask APIs
- **Validation**: Price range checks and anomaly detection
- **Caching**: 30-second TTL for prices, 1-minute for gas

```python
# Example usage
live_source = LivePriceDataSource(binance_adapter)
await live_source.connect()
price = await live_source.get_token_price_usd('WETH')
```

### 🏊 **LivePoolDataSource**
Real-time Uniswap pool data:
- **Pool State**: On-chain contract calls via Web3
- **Pool Metrics**: Uniswap subgraph queries
- **Caching**: 5-minute TTL for pool data
- **Fallback**: Multiple subgraph endpoints

```python
# Example usage
pool_source = LivePoolDataSource(uniswap_adapter)
await pool_source.connect()
metrics = await pool_source.get_pool_metrics(pool_address)
```

## Market Data Aggregator

### 🎯 **Key Features**

1. **Unified Interface**: Single API for all data needs
2. **Automatic Failover**: Seamless switching between sources
3. **Data Validation**: Price range checks and anomaly detection
4. **Mode Switching**: Runtime switching between trading modes
5. **Performance Tracking**: Success/failure metrics for each source

### 🔧 **Configuration**

```python
# Basic setup
aggregator = MarketDataAggregator(
    trading_mode=TradingMode.LIVE,
    binance_adapter=binance_adapter,
    uniswap_adapter=uniswap_adapter
)

# Connect to live sources
await aggregator.connect()

# Use in strategy
strategy = UniswapLendingStrategy(
    "live_strategy",
    config,
    market_data_aggregator=aggregator
)
```

### 📈 **Data Validation**

The aggregator includes built-in validation:

```python
# Price range validation
price_ranges = {
    'WETH': (100, 10000),    # $100 - $10,000
    'WBTC': (10000, 200000), # $10K - $200K
    'USDC': (0.95, 1.05),    # $0.95 - $1.05
}

# Gas price validation
valid_gas_range = (1, 1000)  # 1-1000 Gwei
```

## Integration Examples

### 🧪 **Backtesting Integration**

```python
# Create aggregator for backtesting
aggregator = MarketDataAggregator(trading_mode=TradingMode.BACKTEST)

# Update prices for simulation
backtest_source = aggregator.get_backtest_source()
backtest_source.update_token_price('WETH', Decimal('2000'))
backtest_source.update_token_price('USDC', Decimal('1'))

# Create strategy
strategy = UniswapLendingStrategy(
    "backtest_strategy",
    config,
    market_data_aggregator=aggregator
)

# Run backtest
results = await backtest_engine.run_backtest(strategy, config, ...)
```

### 📊 **Paper Trading Integration**

```python
# Set up live adapters
binance_adapter = BinanceAdapter(binance_config, TradingMode.PAPER)
uniswap_adapter = UniswapAdapter(uniswap_config, TradingMode.PAPER)

# Create aggregator with live data
aggregator = MarketDataAggregator(
    trading_mode=TradingMode.PAPER,
    binance_adapter=binance_adapter,
    uniswap_adapter=uniswap_adapter
)

await aggregator.connect()

# Strategy gets live data but simulates orders
strategy = UniswapLendingStrategy(
    "paper_strategy",
    config,
    market_data_aggregator=aggregator
)
```

### 🚀 **Live Trading Integration**

```python
# Production configuration
production_config = {
    'binance': {
        'api_key': 'prod_key',
        'api_secret': 'prod_secret',
        'testnet': False
    },
    'ethereum': {
        'rpc_url': 'https://mainnet.infura.io/v3/prod_id',
        'backup_rpc': 'https://eth-mainnet.alchemyapi.io/v2/prod_key'
    }
}

# Create production adapters
binance_adapter = BinanceAdapter(production_config['binance'], TradingMode.LIVE)
uniswap_adapter = UniswapAdapter(production_config['ethereum'], TradingMode.LIVE)

# Create aggregator
aggregator = MarketDataAggregator(
    trading_mode=TradingMode.LIVE,
    binance_adapter=binance_adapter,
    uniswap_adapter=uniswap_adapter
)

await aggregator.connect()

# Strategy executes real orders
strategy = UniswapLendingStrategy(
    "live_strategy",
    config,
    market_data_aggregator=aggregator
)
```

## Error Handling & Resilience

### 🛡️ **Failover Strategy**

1. **Primary Source Failure**: Automatically switch to backup APIs
2. **Data Validation Failure**: Reject invalid data, use cached values
3. **Network Issues**: Use cached data with staleness warnings
4. **Complete Failure**: Graceful degradation with safe defaults

### 📊 **Monitoring & Alerting**

```python
# Get performance metrics
performance = aggregator.get_source_performance()
# Returns: {'LivePriceDataSource': {'success': 150, 'failure': 2}}

# Check source health
if performance['LivePriceDataSource']['failure'] > 10:
    # Alert: High failure rate detected
    pass
```

### 🔄 **Circuit Breakers**

- **Price Validation**: Reject prices outside reasonable ranges
- **Rate Limiting**: Respect API rate limits
- **Timeout Handling**: Fail fast on slow responses
- **Retry Logic**: Exponential backoff for transient failures

## Production Deployment

### 📋 **Checklist**

- [ ] **API Credentials**: Configure production API keys
- [ ] **RPC Endpoints**: Set up primary and backup Ethereum RPC
- [ ] **Monitoring**: Implement health checks and alerting
- [ ] **Logging**: Configure structured logging for debugging
- [ ] **Rate Limits**: Respect exchange API rate limits
- [ ] **Circuit Breakers**: Implement failure detection and recovery
- [ ] **Data Validation**: Configure price range validators
- [ ] **Backup Sources**: Set up multiple data source endpoints

### 🔧 **Configuration Management**

```python
# Environment-specific configuration
config = {
    'development': {
        'binance': {'testnet': True},
        'ethereum': {'rpc_url': 'https://goerli.infura.io/...'}
    },
    'production': {
        'binance': {'testnet': False},
        'ethereum': {'rpc_url': 'https://mainnet.infura.io/...'}
    }
}
```

## Performance Considerations

### ⚡ **Optimization Strategies**

1. **Caching**: Aggressive caching with appropriate TTLs
2. **Connection Pooling**: Reuse HTTP connections
3. **Batch Requests**: Group multiple API calls when possible
4. **Async Operations**: Non-blocking I/O for all network calls
5. **Data Compression**: Use compressed responses when available

### 📈 **Scalability**

- **Horizontal Scaling**: Multiple aggregator instances
- **Load Balancing**: Distribute API calls across endpoints
- **Regional Deployment**: Deploy close to exchange servers
- **CDN Integration**: Cache static data (token metadata, etc.)

This architecture provides a robust, scalable foundation for professional cryptocurrency trading across all modes while maintaining clean separation of concerns and easy testability.