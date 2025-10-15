"""
Perpetual contract-specific data models.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from nautilus_trader.model.identifiers import InstrumentId, Venue

from .core import Instrument


@dataclass
class FundingRate:
    """Funding rate information for perpetual contracts."""
    
    instrument: Instrument
    rate: Decimal
    timestamp: datetime
    venue: Venue
    next_funding_time: datetime
    predicted_rate: Decimal = Decimal('0')
    
    def validate(self) -> None:
        """Validate funding rate data."""
        if self.timestamp >= self.next_funding_time:
            raise ValueError("Next funding time must be after current timestamp")
        
        # Funding rates typically range from -0.75% to +0.75% per 8 hours
        if abs(self.rate) > Decimal('0.0075'):
            raise ValueError("Funding rate seems unusually high")
        
        if abs(self.predicted_rate) > Decimal('0.0075'):
            raise ValueError("Predicted funding rate seems unusually high")
    
    def is_positive(self) -> bool:
        """Check if funding rate is positive (longs pay shorts)."""
        return self.rate > 0
    
    def is_negative(self) -> bool:
        """Check if funding rate is negative (shorts pay longs)."""
        return self.rate < 0
    
    def get_annual_rate(self) -> Decimal:
        """Convert 8-hour funding rate to annualized rate."""
        # Assuming 8-hour funding periods (3 per day, 1095 per year)
        return self.rate * Decimal('1095')
    
    def calculate_funding_payment(self, position_size: Decimal, position_side: str) -> Decimal:
        """
        Calculate funding payment for a position.
        
        Args:
            position_size: Size of the position (positive value)
            position_side: 'long' or 'short'
            
        Returns:
            Funding payment (positive = receive, negative = pay)
        """
        if position_side.lower() == 'long':
            # Longs pay when rate is positive, receive when negative
            return -self.rate * position_size
        elif position_side.lower() == 'short':
            # Shorts receive when rate is positive, pay when negative
            return self.rate * position_size
        else:
            raise ValueError("Position side must be 'long' or 'short'")
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "instrument": self.instrument.to_dict(),
            "rate": str(self.rate),
            "timestamp": self.timestamp.isoformat(),
            "venue": str(self.venue),
            "next_funding_time": self.next_funding_time.isoformat(),
            "predicted_rate": str(self.predicted_rate)
        }


@dataclass
class PerpetualPosition:
    """Extended position model for perpetual contracts."""
    
    instrument: Instrument
    side: str  # 'long' or 'short'
    size: Decimal
    entry_price: Decimal
    mark_price: Decimal
    margin: Decimal
    leverage: Decimal
    unrealized_pnl: Decimal
    funding_payments: Decimal
    venue: Venue
    timestamp: datetime
    
    def validate(self) -> None:
        """Validate perpetual position data."""
        if self.size <= 0:
            raise ValueError("Position size must be positive")
        
        if self.entry_price <= 0:
            raise ValueError("Entry price must be positive")
        
        if self.mark_price <= 0:
            raise ValueError("Mark price must be positive")
        
        if self.margin <= 0:
            raise ValueError("Margin must be positive")
        
        if self.leverage <= 0:
            raise ValueError("Leverage must be positive")
        
        if self.side.lower() not in ['long', 'short']:
            raise ValueError("Side must be 'long' or 'short'")
    
    def calculate_pnl(self) -> Decimal:
        """Calculate current unrealized P&L."""
        if self.side.lower() == 'long':
            return (self.mark_price - self.entry_price) * self.size
        else:
            return (self.entry_price - self.mark_price) * self.size
    
    def calculate_margin_ratio(self) -> Decimal:
        """Calculate current margin ratio."""
        position_value = self.mark_price * self.size
        return self.margin / position_value
    
    def calculate_liquidation_price(self, maintenance_margin_rate: Decimal) -> Decimal:
        """Calculate liquidation price based on maintenance margin rate."""
        if self.side.lower() == 'long':
            return self.entry_price * (1 - maintenance_margin_rate / self.leverage)
        else:
            return self.entry_price * (1 + maintenance_margin_rate / self.leverage)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "instrument": self.instrument.to_dict(),
            "side": self.side,
            "size": str(self.size),
            "entry_price": str(self.entry_price),
            "mark_price": str(self.mark_price),
            "margin": str(self.margin),
            "leverage": str(self.leverage),
            "unrealized_pnl": str(self.unrealized_pnl),
            "funding_payments": str(self.funding_payments),
            "venue": str(self.venue),
            "timestamp": self.timestamp.isoformat()
        }