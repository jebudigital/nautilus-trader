"""
Tests for data ingestion system with Parquet storage.
"""

import asyncio
import pytest
import tempfile
import shutil
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from nautilus_trader.model.identifiers import InstrumentId, Venue

from src.crypto_trading_engine.data.models import (
    DataType, TimeFrame, OHLCVData
)
from src.crypto_trading_engine.data.store import HistoricalDataStore
from src.crypto_trading_engine.data.ingestion import DataIngestionEngine


@pytest.fixture
def temp_data_dir():
    """Create temporary directory for test data."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
async def data_store(temp_data_dir):
    """Create test data store."""
    store = HistoricalDataStore(data_path=temp_data_dir)
    await store.initialize()
    return store


@pytest.fixture
async def ingestion_engine(data_store, temp_data_dir):
    """Create test ingestion engine."""
    parquet_path = Path(temp_data_dir) / "parquet"
    engine = DataIngestionEngine(
        data_store=data_store,
        parquet_path=str(parquet_path),
        max_workers=2
    )
    return engine


class TestDataIngestionEngine:
    """Test cases for DataIngestionEngine."""
    
    @pytest.mark.asyncio
    async def test_create_ingestion_job(self, ingestion_engine):
        """Test creating an ingestion job."""
        instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
        venue = Venue("BINANCE")
        start_time = datetime(2024, 1, 1)
        end_time = datetime(2024, 1, 2)
        
        job_id = await ingestion_engine.create_ingestion_job(
            data_type=DataType.OHLCV,
            instrument_id=instrument_id,
            venue=venue,
            start_time=start_time,
            end_time=end_time,
            timeframe=TimeFrame.HOUR_1
        )
        
        assert job_id is not None
        assert len(job_id) > 0
        
        # Check job was stored
        job = await ingestion_engine.get_job_status(job_id)
        assert job is not None
        assert job.data_type == DataType.OHLCV
        assert job.instrument_id == instrument_id
        assert job.venue == venue
        assert job.status == "pending"
    
    @pytest.mark.asyncio
    async def test_start_ohlcv_ingestion_job(self, ingestion_engine):
        """Test starting an OHLCV ingestion job."""
        instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
        venue = Venue("BINANCE")
        start_time = datetime(2024, 1, 1)
        end_time = datetime(2024, 1, 1, 2)  # 2 hours of data
        
        job_id = await ingestion_engine.create_ingestion_job(
            data_type=DataType.OHLCV,
            instrument_id=instrument_id,
            venue=venue,
            start_time=start_time,
            end_time=end_time,
            timeframe=TimeFrame.HOUR_1
        )
        
        # Start the job
        await ingestion_engine.start_ingestion_job(job_id)
        
        # Check job completed
        job = await ingestion_engine.get_job_status(job_id)
        assert job.status == "completed"
        assert job.progress == 1.0
        
        # Check Parquet files were created
        parquet_dir = (
            ingestion_engine.parquet_path / "ohlcv" / 
            f"venue={venue}" / 
            f"instrument={instrument_id}" /
            f"timeframe={TimeFrame.HOUR_1.value}"
        )
        assert parquet_dir.exists()
        
        # Check we can read the data back
        data = await ingestion_engine.read_ohlcv_parquet(
            instrument_id=instrument_id,
            venue=venue,
            timeframe=TimeFrame.HOUR_1,
            start_time=start_time,
            end_time=end_time
        )
        assert len(data) > 0
        assert all(isinstance(d, OHLCVData) for d in data)
    
    @pytest.mark.asyncio
    async def test_read_ohlcv_parquet_with_filters(self, ingestion_engine):
        """Test reading OHLCV data with time filters."""
        instrument_id = InstrumentId.from_str("ETHUSDT.BINANCE")
        venue = Venue("BINANCE")
        start_time = datetime(2024, 1, 1)
        end_time = datetime(2024, 1, 1, 6)  # 6 hours of data
        
        # Create and run ingestion job
        job_id = await ingestion_engine.create_ingestion_job(
            data_type=DataType.OHLCV,
            instrument_id=instrument_id,
            venue=venue,
            start_time=start_time,
            end_time=end_time,
            timeframe=TimeFrame.HOUR_1
        )
        await ingestion_engine.start_ingestion_job(job_id)
        
        # Read with time filter
        filter_start = datetime(2024, 1, 1, 2)
        filter_end = datetime(2024, 1, 1, 4)
        
        filtered_data = await ingestion_engine.read_ohlcv_parquet(
            instrument_id=instrument_id,
            venue=venue,
            timeframe=TimeFrame.HOUR_1,
            start_time=filter_start,
            end_time=filter_end
        )
        
        # Check all data is within the filter range
        for data_point in filtered_data:
            assert filter_start <= data_point.timestamp <= filter_end
    
    @pytest.mark.asyncio
    async def test_job_status_tracking(self, ingestion_engine):
        """Test job status tracking."""
        instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
        venue = Venue("BINANCE")
        start_time = datetime(2024, 1, 1)
        end_time = datetime(2024, 1, 2)
        
        job_id = await ingestion_engine.create_ingestion_job(
            data_type=DataType.OHLCV,
            instrument_id=instrument_id,
            venue=venue,
            start_time=start_time,
            end_time=end_time,
            timeframe=TimeFrame.HOUR_1
        )
        
        # Check initial status
        job = await ingestion_engine.get_job_status(job_id)
        assert job.status == "pending"
        assert job.progress == 0.0
        
        # Start job
        await ingestion_engine.start_ingestion_job(job_id)
        
        # Check final status
        job = await ingestion_engine.get_job_status(job_id)
        assert job.status == "completed"
        assert job.progress == 1.0
    
    @pytest.mark.asyncio
    async def test_list_active_jobs(self, ingestion_engine):
        """Test listing active jobs."""
        # Initially no jobs
        jobs = await ingestion_engine.list_active_jobs()
        assert len(jobs) == 0
        
        # Create a job
        instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
        venue = Venue("BINANCE")
        start_time = datetime(2024, 1, 1)
        end_time = datetime(2024, 1, 2)
        
        job_id = await ingestion_engine.create_ingestion_job(
            data_type=DataType.OHLCV,
            instrument_id=instrument_id,
            venue=venue,
            start_time=start_time,
            end_time=end_time,
            timeframe=TimeFrame.HOUR_1
        )
        
        # Check job appears in list
        jobs = await ingestion_engine.list_active_jobs()
        assert len(jobs) == 1
        assert jobs[0].job_id == job_id
    
    @pytest.mark.asyncio
    async def test_cancel_job(self, ingestion_engine):
        """Test cancelling a job."""
        instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
        venue = Venue("BINANCE")
        start_time = datetime(2024, 1, 1)
        end_time = datetime(2024, 1, 2)
        
        job_id = await ingestion_engine.create_ingestion_job(
            data_type=DataType.OHLCV,
            instrument_id=instrument_id,
            venue=venue,
            start_time=start_time,
            end_time=end_time,
            timeframe=TimeFrame.HOUR_1
        )
        
        # Cancel the job
        cancelled = await ingestion_engine.cancel_job(job_id)
        assert cancelled is True
        
        # Check job status
        job = await ingestion_engine.get_job_status(job_id)
        assert job.status == "failed"
        assert "cancelled" in job.error_message.lower()
        
        # Try to cancel non-existent job
        cancelled = await ingestion_engine.cancel_job("non-existent")
        assert cancelled is False
    
    @pytest.mark.asyncio
    async def test_parquet_storage_stats(self, ingestion_engine):
        """Test getting Parquet storage statistics."""
        # Initially no files
        stats = await ingestion_engine.get_parquet_storage_stats()
        assert stats["total_files"] == 0
        assert stats["total_size_bytes"] == 0
        
        # Create some data
        instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
        venue = Venue("BINANCE")
        start_time = datetime(2024, 1, 1)
        end_time = datetime(2024, 1, 1, 2)
        
        job_id = await ingestion_engine.create_ingestion_job(
            data_type=DataType.OHLCV,
            instrument_id=instrument_id,
            venue=venue,
            start_time=start_time,
            end_time=end_time,
            timeframe=TimeFrame.HOUR_1
        )
        await ingestion_engine.start_ingestion_job(job_id)
        
        # Check stats updated
        stats = await ingestion_engine.get_parquet_storage_stats()
        assert stats["total_files"] > 0
        assert stats["total_size_bytes"] > 0
        assert "ohlcv" in stats["data_types"]
    
    @pytest.mark.asyncio
    async def test_invalid_job_operations(self, ingestion_engine):
        """Test invalid job operations."""
        # Try to start non-existent job
        with pytest.raises(ValueError, match="Job .* not found"):
            await ingestion_engine.start_ingestion_job("non-existent")
        
        # Create job and try to start it twice
        instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
        venue = Venue("BINANCE")
        start_time = datetime(2024, 1, 1)
        end_time = datetime(2024, 1, 2)
        
        job_id = await ingestion_engine.create_ingestion_job(
            data_type=DataType.OHLCV,
            instrument_id=instrument_id,
            venue=venue,
            start_time=start_time,
            end_time=end_time,
            timeframe=TimeFrame.HOUR_1
        )
        
        await ingestion_engine.start_ingestion_job(job_id)
        
        # Try to start completed job
        with pytest.raises(ValueError, match="not in pending status"):
            await ingestion_engine.start_ingestion_job(job_id)
    
    @pytest.mark.asyncio
    async def test_ohlcv_data_validation_in_ingestion(self, ingestion_engine):
        """Test that ingested OHLCV data is properly validated."""
        instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
        venue = Venue("BINANCE")
        start_time = datetime(2024, 1, 1)
        end_time = datetime(2024, 1, 1, 1)  # 1 hour
        
        job_id = await ingestion_engine.create_ingestion_job(
            data_type=DataType.OHLCV,
            instrument_id=instrument_id,
            venue=venue,
            start_time=start_time,
            end_time=end_time,
            timeframe=TimeFrame.HOUR_1
        )
        
        await ingestion_engine.start_ingestion_job(job_id)
        
        # Read back the data and validate
        data = await ingestion_engine.read_ohlcv_parquet(
            instrument_id=instrument_id,
            venue=venue,
            timeframe=TimeFrame.HOUR_1,
            start_time=start_time,
            end_time=end_time
        )
        
        # Validate each data point
        for ohlcv in data:
            ohlcv.validate()  # Should not raise any exceptions
            assert ohlcv.open_price > 0
            assert ohlcv.high_price > 0
            assert ohlcv.low_price > 0
            assert ohlcv.close_price > 0
            assert ohlcv.volume >= 0
    
    @pytest.mark.asyncio
    async def test_cleanup_completed_jobs(self, ingestion_engine):
        """Test cleanup of completed jobs."""
        instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
        venue = Venue("BINANCE")
        start_time = datetime(2024, 1, 1)
        end_time = datetime(2024, 1, 1, 1)
        
        # Create and complete a job
        job_id = await ingestion_engine.create_ingestion_job(
            data_type=DataType.OHLCV,
            instrument_id=instrument_id,
            venue=venue,
            start_time=start_time,
            end_time=end_time,
            timeframe=TimeFrame.HOUR_1
        )
        await ingestion_engine.start_ingestion_job(job_id)
        
        # Manually set end_time to past for testing cleanup
        job = await ingestion_engine.get_job_status(job_id)
        job.end_time = datetime.now() - timedelta(hours=25)  # 25 hours ago
        
        # Cleanup jobs older than 24 hours
        cleaned_count = await ingestion_engine.cleanup_completed_jobs(max_age_hours=24)
        assert cleaned_count == 1
        
        # Job should be gone
        job = await ingestion_engine.get_job_status(job_id)
        assert job is None


if __name__ == "__main__":
    pytest.main([__file__])