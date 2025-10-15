"""
Trading mode enums and related data classes.
"""

from enum import Enum
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from nautilus_trader.model.identifiers import StrategyId
from nautilus_trader.model.objects import Money


class TradingMode(Enum):
    """Enumeration of trading modes."""
    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"


@dataclass
class BacktestResults:
    """Results from a strategy backtest."""
    
    strategy_id: StrategyId
    start_date: datetime
    end_date: datetime
    total_return: Decimal
    sharpe_ratio: Decimal
    max_drawdown: Decimal
    win_rate: Decimal
    total_trades: int
    avg_trade_duration: timedelta
    transaction_costs: Money
    
    def validate(self) -> None:
        """Validate backtest results data."""
        if self.start_date >= self.end_date:
            raise ValueError("Start date must be before end date")
        
        if self.total_trades < 0:
            raise ValueError("Total trades cannot be negative")
        
        if not (0 <= self.win_rate <= 1):
            raise ValueError("Win rate must be between 0 and 1")
        
        if self.max_drawdown < 0:
            raise ValueError("Max drawdown cannot be negative")
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "strategy_id": str(self.strategy_id),
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "total_return": str(self.total_return),
            "sharpe_ratio": str(self.sharpe_ratio),
            "max_drawdown": str(self.max_drawdown),
            "win_rate": str(self.win_rate),
            "total_trades": self.total_trades,
            "avg_trade_duration": str(self.avg_trade_duration.total_seconds()),
            "transaction_costs": {
                "value": str(self.transaction_costs.as_decimal()),
                "currency": str(self.transaction_costs.currency)
            }
        }