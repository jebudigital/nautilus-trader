"""
Exchange adapter interface with simulation capabilities.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from decimal import Decimal

from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.model.data import QuoteTick

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
        self.on_market_data_callback: Optional[Callable[[QuoteTick], None]] = None
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
        on_market_data: Optional[Callable[[QuoteTick], None]] = None,
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
        self.on_market_data_callback = on_market_data
        self.on_order_filled_callback = on_order_filled
        self.on_position_update_callback = on_position_update
        self.on_error_callback = on_error
    
    def simulate_order_execution(self, order: Order, market_price: Price) -> SimulatedFill:
        """
        Simulate order execution for paper trading.
        
        Args:
            order: Order to simulate
            market_price: Current market price
            
        Returns:
            Simulated fill result
        """
        if self.trading_mode == TradingMode.LIVE:
            raise RuntimeError("Cannot simulate execution in live trading mode")
        
        # Simple simulation - can be overridden for more sophisticated logic
        fill_price = market_price
        fill_quantity = order.quantity
        slippage = Decimal('0.001')  # 0.1% default slippage
        
        # Apply slippage
        if order.side.name == 'BUY':
            fill_price = Price(fill_price.as_decimal() * (1 + slippage), fill_price.precision)
        else:
            fill_price = Price(fill_price.as_decimal() * (1 - slippage), fill_price.precision)
        
        # Calculate transaction cost (0.1% default fee)
        transaction_cost_rate = Decimal('0.001')
        transaction_cost_value = fill_price.as_decimal() * fill_quantity.as_decimal() * transaction_cost_rate
        # Use USD as default currency for transaction costs
        from nautilus_trader.model.objects import Currency
        usd = Currency.from_str('USD')
        transaction_cost = Money(transaction_cost_value, usd)
        
        return SimulatedFill(
            order_id=order.id,
            fill_price=fill_price,
            fill_quantity=fill_quantity,
            fill_time=datetime.now(),
            slippage=slippage,
            transaction_cost=transaction_cost,
            venue=self.venue
        )
    
    def validate_order(self, order: Order) -> bool:
        """
        Validate an order before submission.
        
        Args:
            order: Order to validate
            
        Returns:
            True if order is valid, False otherwise
        """
        try:
            order.validate()
            
            # Check if instrument is supported
            instrument = self.instruments.get(str(order.instrument.id))
            if not instrument:
                return False
            
            # Additional validation can be added here
            return True
            
        except Exception:
            return False
    
    def get_connection_status(self) -> Dict[str, Any]:
        """
        Get connection status information.
        
        Returns:
            Dictionary with connection status details
        """
        return {
            "venue": str(self.venue),
            "trading_mode": self.trading_mode.value,
            "is_connected": self.is_connected,
            "instrument_count": len(self.instruments),
            "position_count": len(self.positions),
            "order_count": len(self.orders)
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert adapter to dictionary representation.
        
        Returns:
            Dictionary representation of the adapter
        """
        return {
            "venue": str(self.venue),
            "config": self.config,
            "trading_mode": self.trading_mode.value,
            "is_connected": self.is_connected,
            "instruments": {k: v.to_dict() for k, v in self.instruments.items()},
            "positions": {k: v.to_dict() for k, v in self.positions.items()},
            "orders": {k: v.to_dict() for k, v in self.orders.items()}
        }