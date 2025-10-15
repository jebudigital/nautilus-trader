"""
Abstract strategy base class for multi-mode operation.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional, Any

from nautilus_trader.model.identifiers import StrategyId
from nautilus_trader.model.data import QuoteTick

from ..models.trading_mode import TradingMode, BacktestResults
from ..models.core import Position, Order, Instrument


class Strategy(ABC):
    """
    Abstract base class for trading strategies supporting multiple trading modes.
    
    Strategies can operate in three modes:
    - BACKTEST: Historical data simulation
    - PAPER: Live data with simulated execution
    - LIVE: Real trading with actual capital
    """
    
    def __init__(
        self,
        strategy_id: StrategyId,
        config: Dict[str, Any],
        trading_mode: TradingMode = TradingMode.BACKTEST
    ):
        """
        Initialize the strategy.
        
        Args:
            strategy_id: Unique identifier for the strategy
            config: Strategy configuration parameters
            trading_mode: Current trading mode
        """
        self.strategy_id = strategy_id
        self.config = config
        self.trading_mode = trading_mode
        self.is_running = False
        self.positions: Dict[str, Position] = {}
        self.orders: Dict[str, Order] = {}
        self.instruments: Dict[str, Instrument] = {}
        
    @abstractmethod
    def on_start(self) -> None:
        """
        Called when the strategy is started.
        
        Override to implement strategy initialization logic.
        """
        pass
    
    @abstractmethod
    def on_stop(self) -> None:
        """
        Called when the strategy is stopped.
        
        Override to implement strategy cleanup logic.
        """
        pass
    
    @abstractmethod
    def on_market_data(self, data: QuoteTick) -> None:
        """
        Called when market data is received.
        
        Args:
            data: Market data (quotes, trades, order book, etc.)
        """
        pass
    
    @abstractmethod
    def on_order_filled(self, order: Order, fill_price: float, fill_quantity: float) -> None:
        """
        Called when an order is filled.
        
        Args:
            order: The filled order
            fill_price: Price at which the order was filled
            fill_quantity: Quantity that was filled
        """
        pass
    
    @abstractmethod
    def on_position_opened(self, position: Position) -> None:
        """
        Called when a new position is opened.
        
        Args:
            position: The newly opened position
        """
        pass
    
    @abstractmethod
    def on_position_closed(self, position: Position) -> None:
        """
        Called when a position is closed.
        
        Args:
            position: The closed position
        """
        pass
    
    def set_trading_mode(self, mode: TradingMode) -> None:
        """
        Set the trading mode for this strategy.
        
        Args:
            mode: New trading mode
        """
        if self.is_running:
            raise RuntimeError("Cannot change trading mode while strategy is running")
        
        old_mode = self.trading_mode
        self.trading_mode = mode
        self.on_trading_mode_changed(old_mode, mode)
    
    def on_trading_mode_changed(self, old_mode: TradingMode, new_mode: TradingMode) -> None:
        """
        Called when trading mode changes.
        
        Override to implement mode-specific logic.
        
        Args:
            old_mode: Previous trading mode
            new_mode: New trading mode
        """
        pass
    
    def start(self) -> None:
        """Start the strategy."""
        if self.is_running:
            raise RuntimeError("Strategy is already running")
        
        self.is_running = True
        self.on_start()
    
    def stop(self) -> None:
        """Stop the strategy."""
        if not self.is_running:
            raise RuntimeError("Strategy is not running")
        
        self.is_running = False
        self.on_stop()
    
    def add_instrument(self, instrument: Instrument) -> None:
        """
        Add an instrument to the strategy.
        
        Args:
            instrument: Instrument to add
        """
        self.instruments[str(instrument.id)] = instrument
    
    def get_instrument(self, instrument_id: str) -> Optional[Instrument]:
        """
        Get an instrument by ID.
        
        Args:
            instrument_id: Instrument identifier
            
        Returns:
            Instrument if found, None otherwise
        """
        return self.instruments.get(instrument_id)
    
    def get_positions(self) -> List[Position]:
        """
        Get all current positions.
        
        Returns:
            List of current positions
        """
        return list(self.positions.values())
    
    def get_position(self, position_id: str) -> Optional[Position]:
        """
        Get a position by ID.
        
        Args:
            position_id: Position identifier
            
        Returns:
            Position if found, None otherwise
        """
        return self.positions.get(position_id)
    
    def get_orders(self) -> List[Order]:
        """
        Get all orders.
        
        Returns:
            List of all orders
        """
        return list(self.orders.values())
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """
        Get an order by ID.
        
        Args:
            order_id: Order identifier
            
        Returns:
            Order if found, None otherwise
        """
        return self.orders.get(order_id)
    
    def validate_config(self) -> bool:
        """
        Validate strategy configuration.
        
        Returns:
            True if configuration is valid, False otherwise
        """
        # Basic validation - override in subclasses for specific validation
        return isinstance(self.config, dict)
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get current performance metrics.
        
        Returns:
            Dictionary of performance metrics
        """
        # Basic metrics - override in subclasses for detailed metrics
        return {
            "strategy_id": str(self.strategy_id),
            "trading_mode": self.trading_mode.value,
            "is_running": self.is_running,
            "position_count": len(self.positions),
            "order_count": len(self.orders),
            "instrument_count": len(self.instruments)
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert strategy to dictionary representation.
        
        Returns:
            Dictionary representation of the strategy
        """
        return {
            "strategy_id": str(self.strategy_id),
            "config": self.config,
            "trading_mode": self.trading_mode.value,
            "is_running": self.is_running,
            "positions": {k: v.to_dict() for k, v in self.positions.items()},
            "orders": {k: v.to_dict() for k, v in self.orders.items()},
            "instruments": {k: v.to_dict() for k, v in self.instruments.items()}
        }