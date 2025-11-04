"""
Simple tests for data ingestion system.
"""

import asyncio
import tempfile
import shutil
import logging
from datetime import datetime
from pathlib import Path

from nautilus_trader.model.identifiers import InstrumentId, Venue

import sys
sys.path.append('.')

# Enable logging
logging.basicConfig(level=logging.INFO)

from src.crypto_trading_engine.data.models import DataType, TimeFrame
from src.crypto_trading_engine.data.store import HistoricalDataStore
from src.crypto_trading_engine.data.ingestion import DataIngestionEngine


async def test_basic_ingestion():
    """Test basic data ingestion functionality."""
    # Create temporary directory
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Initialize data store
        store = HistoricalDataStore(data_path=temp_dir)
        await store.initialize()
        
        # Initialize ingestion engine
        parquet_path = Path(temp_dir) / "parquet"
        engine = DataIngestionEngine(
            data_store=store,
            parquet_path=str(parquet_path),
            max_workers=2
        )
        
        # Create ingestion job
        instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
        venue = Venue("BINANCE")
        start_time = datetime(2024, 1, 1)
        end_time = datetime(2024, 1, 1, 2)  # 2 hours
        
        job_id = await engine.create_ingestion_job(
            data_type=DataType.OHLCV,
            instrument_id=instrument_id,
            venue=venue,
            start_time=start_time,
            end_time=end_time,
            timeframe=TimeFrame.HOUR_1
        )
        
        print(f"Created job: {job_id}")
        
        # Check job status
        job = await engine.get_job_status(job_id)
        assert job is not None
        assert job.status == "pending"
        print(f"Job status: {job.status}")
        
        # Start the job
        await engine.start_ingestion_job(job_id)
        
        # Check completion
        job = await engine.get_job_status(job_id)
        assert job.status == "completed"
        print(f"Job completed with status: {job.status}")
        
        # Check Parquet files were created
        parquet_dir = (
            parquet_path / "ohlcv" / 
            f"venue={venue}" / 
            f"instrument={instrument_id}" /
            f"timeframe={TimeFrame.HOUR_1.value}"
        )
        assert parquet_dir.exists()
        print(f"Parquet directory created: {parquet_dir}")
        
        # Read data back
        data = await engine.read_ohlcv_parquet(
            instrument_id=instrument_id,
            venue=venue,
            timeframe=TimeFrame.HOUR_1,
            start_time=start_time,
            end_time=end_time
        )
        
        assert len(data) > 0
        print(f"Read {len(data)} data points from Parquet")
        
        # Get storage stats
        stats = await engine.get_parquet_storage_stats()
        print(f"Storage stats: {stats}")
        
        print("✅ All tests passed!")
        
    finally:
        # Cleanup
        shutil.rmtree(temp_dir)


if __name__ == "__main__":
    asyncio.run(test_basic_ingestion())