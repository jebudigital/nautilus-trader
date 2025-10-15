"""
Main entry point for the crypto trading engine.
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

import click

from crypto_trading_engine.config.settings import load_config

# Nautilus imports will be added when dependencies are installed
try:
    from nautilus_trader.config import TradingNodeConfig
    from nautilus_trader.live.node import TradingNode
    NAUTILUS_AVAILABLE = True
except ImportError:
    NAUTILUS_AVAILABLE = False
    TradingNodeConfig = None
    TradingNode = None


logger = logging.getLogger(__name__)


@click.command()
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True, path_type=Path),
    help="Path to configuration file",
)
@click.option(
    "--environment",
    "-e",
    type=click.Choice(["dev", "test", "prod"]),
    default="dev",
    help="Environment to run in",
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]),
    default="INFO",
    help="Logging level",
)
def main(
    config: Optional[Path] = None,
    environment: str = "dev",
    log_level: str = "INFO",
) -> None:
    """
    Start the crypto algorithmic trading engine.
    """
    # Set up logging
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    logger.info(f"Starting crypto trading engine in {environment} environment")
    
    if not NAUTILUS_AVAILABLE:
        logger.error("Nautilus trader not installed. Please install dependencies: pip install -e .")
        sys.exit(1)
    
    try:
        # Load configuration
        engine_config = load_config(environment, config)
        
        # Create Nautilus trading node configuration
        node_config = TradingNodeConfig(
            trader_id=engine_config.trader_id,
            log_level=log_level,
            # Additional Nautilus configuration will be added here
        )
        
        # Run the trading engine
        asyncio.run(run_engine(node_config))
        
    except Exception as e:
        logger.error(f"Failed to start trading engine: {e}")
        sys.exit(1)


async def run_engine(config: TradingNodeConfig) -> None:
    """
    Run the trading engine with the given configuration.
    """
    logger.info("Initializing trading node...")
    
    # Create and configure the trading node
    node = TradingNode(config=config)
    
    try:
        # Build and start the node
        node.build()
        await node.start_async()
        
        logger.info("Trading engine started successfully")
        
        # Keep the engine running
        await node.get_event_loop().run_forever()
        
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error(f"Trading engine error: {e}")
        raise
    finally:
        logger.info("Shutting down trading engine...")
        await node.stop_async()
        node.dispose()


if __name__ == "__main__":
    main()