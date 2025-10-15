"""
DeFi-specific data models.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from nautilus_trader.model.identifiers import StrategyId
from nautilus_trader.model.objects import Money


@dataclass
class Token:
    """Token representation for DeFi operations."""
    
    address: str
    symbol: str
    decimals: int
    name: str
    
    def validate(self) -> None:
        """Validate token data."""
        if not self.address:
            raise ValueError("Token address cannot be empty")
        
        if not self.symbol:
            raise ValueError("Token symbol cannot be empty")
        
        if self.decimals < 0 or self.decimals > 18:
            raise ValueError("Token decimals must be between 0 and 18")
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "address": self.address,
            "symbol": self.symbol,
            "decimals": self.decimals,
            "name": self.name
        }


@dataclass
class UniswapPool:
    """Uniswap V3 pool information."""
    
    address: str
    token0: Token
    token1: Token
    fee_tier: int
    liquidity: Decimal
    sqrt_price_x96: int
    tick: int
    apy: float
    tvl: Optional[Money] = None
    volume_24h: Optional[Money] = None
    
    def validate(self) -> None:
        """Validate pool data."""
        if not self.address:
            raise ValueError("Pool address cannot be empty")
        
        if self.fee_tier not in [100, 500, 3000, 10000]:
            raise ValueError("Invalid fee tier, must be 100, 500, 3000, or 10000")
        
        if self.liquidity < 0:
            raise ValueError("Liquidity cannot be negative")
        
        if self.apy < 0:
            raise ValueError("APY cannot be negative")
        
        self.token0.validate()
        self.token1.validate()
    
    def get_fee_percentage(self) -> Decimal:
        """Get fee as percentage (e.g., 0.3% for 3000 fee tier)."""
        return Decimal(self.fee_tier) / Decimal(10000)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "address": self.address,
            "token0": self.token0.to_dict(),
            "token1": self.token1.to_dict(),
            "fee_tier": self.fee_tier,
            "liquidity": str(self.liquidity),
            "sqrt_price_x96": self.sqrt_price_x96,
            "tick": self.tick,
            "apy": self.apy,
            "tvl": {
                "value": str(self.tvl.as_decimal()),
                "currency": str(self.tvl.currency)
            } if self.tvl else None,
            "volume_24h": {
                "value": str(self.volume_24h.as_decimal()),
                "currency": str(self.volume_24h.currency)
            } if self.volume_24h else None
        }


@dataclass
class LiquidityPosition:
    """Uniswap V3 liquidity position."""
    
    pool_address: str
    token0: Token
    token1: Token
    liquidity_amount: Decimal
    tick_lower: int
    tick_upper: int
    fees_earned: Money
    impermanent_loss: Money
    strategy_id: StrategyId
    created_time: datetime
    is_simulated: bool = False
    token_id: Optional[int] = None  # NFT token ID for the position
    
    def validate(self) -> None:
        """Validate liquidity position data."""
        if not self.pool_address:
            raise ValueError("Pool address cannot be empty")
        
        if self.liquidity_amount <= 0:
            raise ValueError("Liquidity amount must be positive")
        
        if self.tick_lower >= self.tick_upper:
            raise ValueError("Lower tick must be less than upper tick")
        
        self.token0.validate()
        self.token1.validate()
    
    def is_in_range(self, current_tick: int) -> bool:
        """Check if position is in range for current price."""
        return self.tick_lower <= current_tick <= self.tick_upper
    
    def calculate_net_pnl(self) -> Money:
        """Calculate net P&L including fees and impermanent loss."""
        net_pnl = self.fees_earned.as_decimal() - self.impermanent_loss.as_decimal()
        return Money(net_pnl, self.fees_earned.currency)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "pool_address": self.pool_address,
            "token0": self.token0.to_dict(),
            "token1": self.token1.to_dict(),
            "liquidity_amount": str(self.liquidity_amount),
            "tick_lower": self.tick_lower,
            "tick_upper": self.tick_upper,
            "fees_earned": {
                "value": str(self.fees_earned.as_decimal()),
                "currency": str(self.fees_earned.currency)
            },
            "impermanent_loss": {
                "value": str(self.impermanent_loss.as_decimal()),
                "currency": str(self.impermanent_loss.currency)
            },
            "strategy_id": str(self.strategy_id),
            "created_time": self.created_time.isoformat(),
            "is_simulated": self.is_simulated,
            "token_id": self.token_id
        }