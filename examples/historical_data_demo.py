#!/usr/bin/env python3
"""
Historical Data Management Demo

This script demonstrates the Parquet-based historical data management system
for the crypto trading engine. It shows how to:

1. Initialize the data storage system
2. Create and run data ingestion jobs
3. Store data in efficient Parquet format
4. Query and retrieve historical data
5. Monitor storage statistics

The system uses a hybrid approach:
- SQLite for fast metadata queries and indexing
- Parquet files for efficient bulk data storage and analytics
"""

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path

from nautilus_trader.model.identifiers import InstrumentId, Venue

import sys
sys.path.append('.')

from src.crypto_trading_engine.data.models import DataType, TimeFrame
from src.crypto_trading_engine.data.store import HistoricalDataStore
from src.crypto_trading_engine.data.ingestion import DataIngestionEngine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Main demo function."""
    logger.info("🚀 Starting Historical Data Management Demo")
    
    # Initialize data storage system
    data_path = "demo_data"
    parquet_path = Path(data_path) / "parquet"
    
    logger.info(f"📁 Initializing data storage at: {data_path}")
    
    # Create data store
    store = HistoricalDataStore(data_path=data_path)
    await store.initialize()
    
    # Create ingestion engine
    engine = DataIngestionEngine(
        data_store=store,
        parquet_path=str(parquet_path),
        max_workers=4
    )
    
    # Demo instruments
    instruments = [
        (InstrumentId.from_str("BTCUSDT.BINANCE"), Venue("BINANCE")),
        (InstrumentId.from_str("ETHUSDT.BINANCE"), Venue("BINANCE")),
        (InstrumentId.from_str("BTCUSD.DYDX"), Venue("DYDX")),
    ]
    
    # Demo timeframes
    timeframes = [TimeFrame.HOUR_1, TimeFrame.DAY_1]
    
    # Create ingestion jobs for different instruments and timeframes
    logger.info("📊 Creating data ingestion jobs...")
    
    job_ids = []
    start_time = datetime(2024, 1, 1)
    end_time = datetime(2024, 1, 7)  # One week of data
    
    for instrument_id, venue in instruments:
        for timeframe in timeframes:
            logger.info(f"Creating job for {instrument_id} on {venue} ({timeframe.value})")
            
            job_id = await engine.create_ingestion_job(
                data_type=DataType.OHLCV,
                instrument_id=instrument_id,
                venue=venue,
                start_time=start_time,
                end_time=end_time,
                timeframe=timeframe
            )
            job_ids.append(job_id)
    
    logger.info(f"✅ Created {len(job_ids)} ingestion jobs")
    
    # Start all jobs
    logger.info("🔄 Starting data ingestion jobs...")
    
    for i, job_id in enumerate(job_ids, 1):
        logger.info(f"Starting job {i}/{len(job_ids)}: {job_id}")
        await engine.start_ingestion_job(job_id)
        
        # Check job status
        job = await engine.get_job_status(job_id)
        logger.info(f"Job {job_id} completed with status: {job.status}")
    
    logger.info("✅ All ingestion jobs completed")
    
    # Demonstrate data querying
    logger.info("🔍 Demonstrating data querying...")
    
    # Query OHLCV data for BTC on Binance
    btc_instrument = InstrumentId.from_str("BTCUSDT.BINANCE")
    btc_venue = Venue("BINANCE")
    
    # Query from Parquet files
    logger.info("📈 Querying BTC hourly data from Parquet...")
    btc_hourly_data = await engine.read_ohlcv_parquet(
        instrument_id=btc_instrument,
        venue=btc_venue,
        timeframe=TimeFrame.HOUR_1,
        start_time=datetime(2024, 1, 2),
        end_time=datetime(2024, 1, 3)
    )
    
    logger.info(f"Retrieved {len(btc_hourly_data)} hourly BTC data points")
    if btc_hourly_data:
        first_point = btc_hourly_data[0]
        logger.info(f"First data point: {first_point.timestamp} - "
                   f"O:{first_point.open_price} H:{first_point.high_price} "
                   f"L:{first_point.low_price} C:{first_point.close_price}")
    
    # Query from SQLite (faster for metadata queries)
    logger.info("📊 Querying BTC daily data from SQLite...")
    btc_daily_data = await store.get_ohlcv_data(
        instrument_id=btc_instrument,
        venue=btc_venue,
        timeframe=TimeFrame.DAY_1,
        start_time=start_time,
        end_time=end_time,
        limit=10
    )
    
    logger.info(f"Retrieved {len(btc_daily_data)} daily BTC data points from SQLite")
    
    # Demonstrate data quality metrics
    logger.info("📋 Calculating data quality metrics...")
    
    quality_metrics = await store.get_data_quality_metrics(
        instrument_id=btc_instrument,
        venue=btc_venue,
        data_type=DataType.OHLCV,
        start_time=start_time,
        end_time=end_time,
        timeframe=TimeFrame.HOUR_1
    )
    
    logger.info(f"Data Quality Metrics for BTC hourly data:")
    logger.info(f"  Total records: {quality_metrics.total_records}")
    logger.info(f"  Missing records: {quality_metrics.missing_records}")
    logger.info(f"  Completeness ratio: {quality_metrics.completeness_ratio:.2%}")
    logger.info(f"  Data gaps: {len(quality_metrics.data_gaps)}")
    
    # Show storage statistics
    logger.info("💾 Storage Statistics:")
    
    # SQLite stats
    sqlite_stats = await store.get_storage_stats()
    logger.info(f"SQLite Database:")
    logger.info(f"  OHLCV records: {sqlite_stats['ohlcv_data_count']}")
    logger.info(f"  Database size: {sqlite_stats['db_file_size_mb']:.2f} MB")
    
    # Parquet stats
    parquet_stats = await engine.get_parquet_storage_stats()
    logger.info(f"Parquet Storage:")
    logger.info(f"  Total files: {parquet_stats['total_files']}")
    logger.info(f"  Total size: {parquet_stats['total_size_mb']:.2f} MB")
    
    for data_type, stats in parquet_stats['data_types'].items():
        logger.info(f"  {data_type}: {stats['files']} files, "
                   f"{stats['size_bytes'] / (1024*1024):.2f} MB")
    
    # Demonstrate job management
    logger.info("📋 Job Management:")
    
    # List all jobs
    all_jobs = await engine.list_active_jobs()
    logger.info(f"Total active jobs: {len(all_jobs)}")
    
    completed_jobs = [job for job in all_jobs if job.status == "completed"]
    logger.info(f"Completed jobs: {len(completed_jobs)}")
    
    # Show ingestion jobs from database
    db_jobs = await store.list_ingestion_jobs(limit=5)
    logger.info(f"Recent jobs from database: {len(db_jobs)}")
    
    for job in db_jobs[:3]:  # Show first 3 jobs
        logger.info(f"  Job {job.job_id[:8]}... - {job.data_type.value} "
                   f"{job.instrument_id} ({job.status})")
    
    # Demonstrate advanced querying
    logger.info("🔍 Advanced Querying Examples:")
    
    # Query multiple instruments
    logger.info("Querying multiple instruments...")
    
    eth_instrument = InstrumentId.from_str("ETHUSDT.BINANCE")
    eth_data = await engine.read_ohlcv_parquet(
        instrument_id=eth_instrument,
        venue=btc_venue,
        timeframe=TimeFrame.HOUR_1,
        start_time=datetime(2024, 1, 1),
        end_time=datetime(2024, 1, 2)
    )
    
    logger.info(f"ETH data points: {len(eth_data)}")
    
    # Time-filtered queries
    logger.info("Time-filtered query example...")
    
    filtered_data = await engine.read_ohlcv_parquet(
        instrument_id=btc_instrument,
        venue=btc_venue,
        timeframe=TimeFrame.HOUR_1,
        start_time=datetime(2024, 1, 1, 12),  # Start at noon
        end_time=datetime(2024, 1, 1, 18)     # End at 6 PM
    )
    
    logger.info(f"Filtered BTC data (noon to 6 PM): {len(filtered_data)} points")
    
    # Performance comparison
    logger.info("⚡ Performance Comparison:")
    
    # Time SQLite query
    import time
    
    start_time_query = time.time()
    sqlite_data = await store.get_ohlcv_data(
        instrument_id=btc_instrument,
        venue=btc_venue,
        timeframe=TimeFrame.HOUR_1,
        start_time=datetime(2024, 1, 1),
        end_time=datetime(2024, 1, 7)
    )
    sqlite_time = time.time() - start_time_query
    
    # Time Parquet query
    start_time_query = time.time()
    parquet_data = await engine.read_ohlcv_parquet(
        instrument_id=btc_instrument,
        venue=btc_venue,
        timeframe=TimeFrame.HOUR_1,
        start_time=datetime(2024, 1, 1),
        end_time=datetime(2024, 1, 7)
    )
    parquet_time = time.time() - start_time_query
    
    logger.info(f"SQLite query: {len(sqlite_data)} records in {sqlite_time:.3f}s")
    logger.info(f"Parquet query: {len(parquet_data)} records in {parquet_time:.3f}s")
    
    # Cleanup demonstration
    logger.info("🧹 Cleanup Operations:")
    
    # Clean up old jobs
    cleaned_jobs = await engine.cleanup_completed_jobs(max_age_hours=0)  # Clean all for demo
    logger.info(f"Cleaned up {cleaned_jobs} completed jobs")
    
    # Clean up old data (demo - normally you'd keep more data)
    cleaned_data = await store.cleanup_old_data(days_to_keep=1)
    logger.info(f"Cleaned up old data: {cleaned_data}")
    
    logger.info("🎉 Historical Data Management Demo completed successfully!")
    logger.info(f"📁 Demo data stored in: {data_path}")
    logger.info("💡 Key features demonstrated:")
    logger.info("   ✓ Parquet-based efficient data storage")
    logger.info("   ✓ SQLite metadata and fast querying")
    logger.info("   ✓ Asynchronous data ingestion jobs")
    logger.info("   ✓ Data quality metrics and validation")
    logger.info("   ✓ Flexible querying with time filters")
    logger.info("   ✓ Storage statistics and monitoring")
    logger.info("   ✓ Job management and cleanup")


if __name__ == "__main__":
    asyncio.run(main())