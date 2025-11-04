# Historical Data Management System

## Overview

The crypto trading engine implements a sophisticated historical data management system that combines the efficiency of Parquet files for bulk storage with SQLite for fast metadata queries. This hybrid approach provides optimal performance for both analytical workloads and real-time trading operations.

## Architecture

### Hybrid Storage Design

```
┌─────────────────────────────────────────────────────────────┐
│                    Data Ingestion Engine                    │
├─────────────────────────────────────────────────────────────┤
│  • Fetches data from exchange APIs                         │
│  • Validates and processes data                            │
│  • Manages ingestion jobs                                  │
│  • Handles parallel processing                             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────┐    ┌─────────────────────┐
│   SQLite Database   │    │   Parquet Files     │
├─────────────────────┤    ├─────────────────────┤
│ • Fast metadata     │    │ • Bulk data storage │
│ • Indexing          │    │ • Compression       │
│ • Job tracking      │    │ • Analytics         │
│ • Quality metrics   │    │ • Partitioning      │
└─────────────────────┘    └─────────────────────┘
```

### Data Organization

#### Parquet Structure
```
data/parquet/
├── ohlcv/
│   ├── venue=BINANCE/
│   │   ├── instrument=BTCUSDT/
│   │   │   ├── timeframe=1h/
│   │   │   │   ├── year=2024/
│   │   │   │   │   ├── month=01/
│   │   │   │   │   │   └── data.parquet
│   │   │   │   │   └── month=02/
│   │   │   │   └── year=2025/
│   │   │   └── timeframe=1d/
│   │   └── instrument=ETHUSDT/
│   └── venue=DYDX/
├── orderbook/
├── trades/
└── funding_rates/
```

#### SQLite Schema
- **ohlcv_data**: Fast queries and indexing
- **orderbook_data**: Order book snapshots
- **trade_data**: Individual trades
- **funding_rate_data**: Perpetual contract funding rates
- **ingestion_jobs**: Job tracking and management

## Key Features

### 1. Efficient Data Storage

**Parquet Benefits:**
- **Compression**: 80-90% size reduction compared to CSV
- **Columnar Format**: Optimized for analytical queries
- **Schema Evolution**: Supports adding new fields
- **Cross-Platform**: Compatible with pandas, Apache Spark, etc.

**SQLite Benefits:**
- **Fast Queries**: Sub-millisecond metadata lookups
- **ACID Compliance**: Reliable data integrity
- **Indexing**: Optimized query performance
- **Lightweight**: No separate server required

### 2. Asynchronous Data Ingestion

```python
# Create ingestion job
job_id = await engine.create_ingestion_job(
    data_type=DataType.OHLCV,
    instrument_id=InstrumentId.from_str("BTCUSDT.BINANCE"),
    venue=Venue("BINANCE"),
    start_time=datetime(2024, 1, 1),
    end_time=datetime(2024, 1, 7),
    timeframe=TimeFrame.HOUR_1
)

# Start ingestion
await engine.start_ingestion_job(job_id)
```

### 3. Flexible Querying

**Parquet Queries (Analytics):**
```python
# Read large datasets efficiently
data = await engine.read_ohlcv_parquet(
    instrument_id=instrument_id,
    venue=venue,
    timeframe=TimeFrame.HOUR_1,
    start_time=start_time,
    end_time=end_time
)
```

**SQLite Queries (Fast Lookups):**
```python
# Fast metadata queries
data = await store.get_ohlcv_data(
    instrument_id=instrument_id,
    venue=venue,
    timeframe=TimeFrame.HOUR_1,
    limit=100
)
```

### 4. Data Quality Management

```python
# Calculate quality metrics
metrics = await store.get_data_quality_metrics(
    instrument_id=instrument_id,
    venue=venue,
    data_type=DataType.OHLCV,
    start_time=start_time,
    end_time=end_time,
    timeframe=TimeFrame.HOUR_1
)

print(f"Completeness: {metrics.completeness_ratio:.2%}")
print(f"Missing records: {metrics.missing_records}")
print(f"Data gaps: {len(metrics.data_gaps)}")
```

### 5. Job Management

```python
# List active jobs
jobs = await engine.list_active_jobs()

# Check job status
job = await engine.get_job_status(job_id)
print(f"Status: {job.status}, Progress: {job.progress:.1%}")

# Cancel job if needed
await engine.cancel_job(job_id)
```

## Data Types Supported

### OHLCV Data
- Open, High, Low, Close prices
- Volume and quote volume
- Trade count
- Multiple timeframes (1m, 5m, 1h, 1d, etc.)

### Order Book Snapshots
- Bid/ask levels with prices and quantities
- Timestamp precision
- Market depth analysis

### Trade Data
- Individual trade records
- Price, quantity, side
- Trade IDs and timestamps

### Funding Rates
- Perpetual contract funding rates
- Predicted rates
- Next funding times

## Performance Characteristics

### Storage Efficiency
- **Parquet Compression**: ~90% size reduction
- **Partitioning**: Efficient data pruning
- **Columnar Access**: Read only needed columns

### Query Performance
- **SQLite Indexes**: Sub-millisecond lookups
- **Parquet Filtering**: Efficient time-range queries
- **Parallel Processing**: Multi-threaded operations

### Scalability
- **Horizontal Partitioning**: By date/instrument
- **Async Operations**: Non-blocking I/O
- **Memory Efficient**: Streaming data processing

## Usage Examples

### Basic Setup

```python
from src.crypto_trading_engine.data.store import HistoricalDataStore
from src.crypto_trading_engine.data.ingestion import DataIngestionEngine

# Initialize storage
store = HistoricalDataStore(data_path="data")
await store.initialize()

# Initialize ingestion engine
engine = DataIngestionEngine(
    data_store=store,
    parquet_path="data/parquet"
)
```

### Data Ingestion

```python
# Create and start ingestion job
job_id = await engine.create_ingestion_job(
    data_type=DataType.OHLCV,
    instrument_id=InstrumentId.from_str("BTCUSDT.BINANCE"),
    venue=Venue("BINANCE"),
    start_time=datetime(2024, 1, 1),
    end_time=datetime(2024, 1, 7),
    timeframe=TimeFrame.HOUR_1
)

await engine.start_ingestion_job(job_id)
```

### Data Querying

```python
# Query from Parquet (efficient for large datasets)
data = await engine.read_ohlcv_parquet(
    instrument_id=InstrumentId.from_str("BTCUSDT.BINANCE"),
    venue=Venue("BINANCE"),
    timeframe=TimeFrame.HOUR_1,
    start_time=datetime(2024, 1, 1),
    end_time=datetime(2024, 1, 7)
)

# Query from SQLite (fast for small datasets)
data = await store.get_ohlcv_data(
    instrument_id=InstrumentId.from_str("BTCUSDT.BINANCE"),
    venue=Venue("BINANCE"),
    timeframe=TimeFrame.HOUR_1,
    limit=100
)
```

### Monitoring and Maintenance

```python
# Storage statistics
sqlite_stats = await store.get_storage_stats()
parquet_stats = await engine.get_parquet_storage_stats()

# Data quality metrics
metrics = await store.get_data_quality_metrics(
    instrument_id, venue, DataType.OHLCV,
    start_time, end_time, TimeFrame.HOUR_1
)

# Cleanup old data
await store.cleanup_old_data(days_to_keep=365)
await engine.cleanup_completed_jobs(max_age_hours=24)
```

## Best Practices

### 1. Data Partitioning
- Partition by date for efficient time-range queries
- Use appropriate timeframes for different use cases
- Consider instrument-based partitioning for large datasets

### 2. Query Optimization
- Use SQLite for fast metadata and small result sets
- Use Parquet for analytical queries and large datasets
- Apply time filters to minimize data scanning

### 3. Storage Management
- Regular cleanup of old data and completed jobs
- Monitor storage usage and compression ratios
- Use appropriate retention policies

### 4. Error Handling
- Implement retry logic for failed ingestion jobs
- Validate data quality before storage
- Monitor job status and handle failures gracefully

### 5. Performance Tuning
- Adjust worker thread counts based on system resources
- Use appropriate batch sizes for data processing
- Consider memory usage for large datasets

## Integration with Trading Engine

The historical data management system integrates seamlessly with the trading engine components:

- **Backtesting Engine**: Efficient access to historical data
- **Strategy Development**: Data for research and validation
- **Risk Management**: Historical volatility and correlation analysis
- **Performance Analytics**: Trade analysis and reporting

## Future Enhancements

- **Real-time Data Streaming**: Live data ingestion
- **Data Compression**: Advanced compression algorithms
- **Distributed Storage**: Multi-node data distribution
- **Caching Layer**: In-memory data caching
- **Data Validation**: Enhanced quality checks
- **Metadata Management**: Rich data cataloging