"""
Exchange adapter interface with simulation capabilities.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from decimal import Decimal

from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.model.data import Data

from ..models.trading_mode import TradingMode
from ..models.core import Order, Position, Instrument, SimulatedFill


class ExchangeAdapter(ABC):
    """
    Abstract base class for exchange adapters supporting multiple trading modes.
    
    Adapters handle communication with exchanges and can operate in:
    - BACKTEST: No real connections, uses historical data
    - PAPER: Live connections for data, simulated execution
    - LIVE: Full live trading with real execution
    """
    
    def __init__(
        self,
        venue: Venue,
        config: Dict[str, Any],
        trading_mode: TradingMode = TradingMode.BACKTEST
    ):
        """
        Initialize the exchange adapter.
        
        Args:
            venue: Exchange venue identifier
            config: Adapter configuration
            trading_mode: Current trading mode
        """
        self.venue = venue
        self.config = config
        self.trading_mode = trading_mode
        self.is_connected = False
        self.instruments: Dict[str, Instrument] = {}
        self.positions: Dict[str, Position] = {}
        self.orders: Dict[str, Order] = {}
        
        # Callbacks for events
        self.on_market_data_callback: Optional[Callable[[Data], None]] = None
        self.on_order_filled_callback: Optional[Callable[[Order, SimulatedFill], None]] = None
        self.on_position_update_callback: Optional[Callable[[Position], None]] = None
        self.on_error_callback: Optional[Callable[[Exception], None]] = None
    
    @abstractmethod
    async def connect(self) -> bool:
        """
        Connect to the exchange.
        
        Returns:
            True if connection successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the exchange."""
        pass
    
    @abstractmethod
    async def submit_order(self, order: Order) -> bool:
        """
        Submit an order to the exchange.
        
        Args:
            order: Order to submit
            
        Returns:
            True if order submitted successfully, False otherwise
        """
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.
        
        Args:
            order_id: ID of order to cancel
            
        Returns:
            True if order cancelled successfully, False otherwise
        """
        pass
    
    @abstractmethod
    async def get_order_status(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        Get order status.
        
        Args:
            order_id: Order ID to check
            
        Returns:
            Order status information or None if not found
        """
        pass
    
    @abstractmethod
    async def get_positions(self) -> List[Position]:
        """
        Get current positions.
        
        Returns:
            List of current positions
        """
        pass
    
    @abstractmethod
    async def get_balance(self) -> Dict[str, Money]:
        """
        Get account balance.
        
        Returns:
            Dictionary of currency balances
        """
        pass
    
    @abstractmethod
    async def get_instruments(self) -> List[Instrument]:
        """
        Get available instruments.
        
        Returns:
            List of available instruments
        """
        pass
    
    @abstractmethod
    async def subscribe_market_data(self, instrument_ids: List[str]) -> bool:
        """
        Subscribe to market data for instruments.
        
        Args:
            instrument_ids: List of instrument IDs to subscribe to
            
        Returns:
            True if subscription successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def unsubscribe_market_data(self, instrument_ids: List[str]) -> bool:
        """
        Unsubscribe from market data for instruments.
        
        Args:
            instrument_ids: List of instrument IDs to unsubscribe from
            
        Returns:
            True if unsubscription successful, False otherwise
        """
        pass
    
    def set_trading_mode(self, mode: TradingMode) -> None:
        """
        Set the trading mode for this adapter.
        
        Args:
            mode: New trading mode
        """
        if self.is_connected:
            raise RuntimeError("Cannot change trading mode while connected")
        
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
    
    def set_callbacks(
        self,
        on_market_data: Optional[Callable[[Data], None]] = None,
        on_order_filled: Optional[Callable[[Order, SimulatedFill], None]] = None,
        on_position_update: Optional[Callable[[Position], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None
    ) -> None:
        """
        Set event callbacks.
        
        Args:
            on_market_data: Market data callback
            on_order_filled: Order fill callback
            on_position_update: Position update callback
            on_error: Error callback
        """
        self.on_market_da