"""
Core trading data models.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from nautilus_trader.model.enums import OrderSide, OrderType, TimeInForce, PositionSide
from nautilus_trader.model.identifiers import (
    InstrumentId, 
    ClientOrderId, 
    PositionId, 
    StrategyId, 
    Venue
)
from nautilus_trader.model.instruments import Instrument as NautilusInstrument
from nautilus_trader.model.objects import Money, Price, Quantity

from .trading_mode import TradingMode


@dataclass
class Instrument:
    """Extended instrument model with simulation support."""
    
    id: InstrumentId
    symbol: str
    base_currency: str
    quote_currency: str
    price_precision: int
    size_precision: int
    min_quantity: Decimal
    max_quantity: Optional[Decimal]
    tick_size: Decimal
    venue: Venue
    is_active: bool = True
    
    def validate(self) -> None:
        """Validate instrument data."""
        if self.price_precision < 0:
            raise ValueError("Price precision cannot be negative")
        
        if self.size_precision < 0:
            raise ValueError("Size precision cannot be negative")
        
        if self.min_quantity <= 0:
            raise ValueError("Minimum quantity must be positive")
        
        if self.max_quantity is not None and self.max_quantity <= self.min_quantity:
            raise ValueError("Maximum quantity must be greater than minimum quantity")
        
        if self.tick_size <= 0:
            raise ValueError("Tick size must be positive")
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "id": str(self.id),
            "symbol": self.symbol,
            "base_currency": self.base_currency,
            "quote_currency": self.quote_currency,
            "price_precision": self.price_precision,
            "size_precision": self.size_precision,
            "min_quantity": str(self.min_quantity),
            "max_quantity": str(self.max_quantity) if self.max_quantity else None,
            "tick_size": str(self.tick_size),
            "venue": str(self.venue),
            "is_active": self.is_active
        }


@dataclass
class Position:
    """Trading position with simulation support."""
    
    id: PositionId
    instrument: Instrument
    side: PositionSide
    quantity: Quantity
    avg_price: Price
    unrealized_pnl: Money
    venue: Venue
    strategy_id: StrategyId
    opened_time: datetime
    is_simulated: bool = False
    
    def validate(self) -> None:
        """Validate position data."""
        if self.quantity.as_decimal() <= 0:
            raise ValueError("Position quantity must be positive")
        
        if self.avg_price.as_decimal() <= 0:
            raise ValueError("Average price must be positive")
    
    def calculate_market_value(self, current_price: Price) -> Money:
        """Calculate current market value of position."""
        market_value = self.quantity.as_decimal() * current_price.as_decimal()
        return Money(market_value, self.unrealized_pnl.currency)
    
    def calculate_pnl(self, current_price: Price) -> Money:
        """Calculate current P&L of position."""
        if self.side == PositionSide.LONG:
            pnl = (current_price.as_decimal() - self.avg_price.as_decimal()) * self.quantity.as_decimal()
        else:
            pnl = (self.avg_price.as_decimal() - current_price.as_decimal()) * self.quantity.as_decimal()
        
        return Money(pnl, self.unrealized_pnl.currency)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "id": str(self.id),
            "instrument": self.instrument.to_dict(),
            "side": str(self.side),
            "quantity": str(self.quantity),
            "avg_price": str(self.avg_price),
            "unrealized_pnl": {
                "value": str(self.unrealized_pnl.as_decimal()),
                "currency": str(self.unrealized_pnl.currency)
            },
            "venue": str(self.venue),
            "strategy_id": str(self.strategy_id),
            "opened_time": self.opened_time.isoformat(),
            "is_simulated": self.is_simulated
        }


@dataclass
class Order:
    """Trading order with simulation support."""
    
    id: ClientOrderId
    instrument: Instrument
    side: OrderSide
    quantity: Quantity
    price: Optional[Price]
    order_type: OrderType
    time_in_force: TimeInForce
    strategy_id: StrategyId
    trading_mode: TradingMode
    created_time: datetime
    is_simulated: bool = False
    
    def validate(self) -> None:
        """Validate order data."""
        if self.quantity.as_decimal() <= 0:
            raise ValueError("Order quantity must be positive")
        
        if self.quantity.as_decimal() < self.instrument.min_quantity:
            raise ValueError(f"Order quantity below minimum: {self.instrument.min_quantity}")
        
        if (self.instrument.max_quantity is not None and 
            self.quantity.as_decimal() > self.instrument.max_quantity):
            raise ValueError(f"Order quantity above maximum: {self.instrument.max_quantity}")
        
        if self.price is not None and self.price.as_decimal() <= 0:
            raise ValueError("Order price must be positive")
    
    def is_market_order(self) -> bool:
        """Check if this is a market order."""
        return self.order_type == OrderType.MARKET
    
    def is_limit_order(self) -> bool:
        """Check if this is a limit order."""
        return self.order_type == OrderType.LIMIT
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "id": str(self.id),
            "instrument": self.instrument.to_dict(),
            "side": str(self.side),
            "quantity": str(self.quantity),
            "price": str(self.price) if self.price else None,
            "order_type": str(self.order_type),
            "time_in_force": str(self.time_in_force),
            "strategy_id": str(self.strategy_id),
            "trading_mode": str(self.trading_mode.value),
            "created_time": self.created_time.isoformat(),
            "is_simulated": self.is_simulated
        }


@dataclass
class SimulatedFill:
    """Simulated order fill for paper trading."""
    
    order_id: ClientOrderId
    fill_price: Price
    fill_quantity: Quantity
    fill_time: datetime
    slippage: Decimal
    transaction_cost: Money
    venue: Venue
    
    def validate(self) -> None:
        """Validate simulated fill data."""
        if self.fill_quantity.as_decimal() <= 0:
            raise ValueError("Fill quantity must be positive")
        
        if self.fill_price.as_decimal() <= 0:
            raise ValueError("Fill price must be positive")
        
        if self.slippage < 0:
            raise ValueError("Slippage cannot be negative")
    
    def calculate_total_cost(self) -> Money:
        """Calculate total cost including transaction costs."""
        execution_value = self.fill_price.as_decimal() * self.fill_quantity.as_decimal()
        total_cost = execution_value + self.transaction_cost.as_decimal()
        return Money(total_cost, self.transaction_cost.currency)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "order_id": str(self.order_id),
            "fill_price": str(self.fill_price),
            "fill_quantity": str(self.fill_quantity),
            "fill_time": self.fill_time.isoformat(),
            "slippage": str(self.slippage),
            "transaction_cost": {
                "value": str(self.transaction_cost.as_decimal()),
                "currency": str(self.transaction_cost.currency)
            },
            "venue": str(self.venue)
        }