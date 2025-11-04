"""
Backtesting models and data structures.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any
from enum import Enum

from nautilus_trader.model.identifiers import InstrumentId, Venue


class TradingMode(Enum):
    """Trading modes supported by the engine."""
    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"


class OrderSide(Enum):
    """Order side enumeration."""
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    """Order type enumeration."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(Enum):
    """Order status enumeration."""
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class PositionSide(Enum):
    """Position side enumeration."""
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


@dataclass
class Money:
    """Represents a monetary amount with currency."""
    amount: Decimal
    currency: str
    
    def __add__(self, other: 'Money') -> 'Money':
        if self.currency != other.currency:
            raise ValueError(f"Cannot add {self.currency} and {other.currency}")
        return Money(self.amount + other.amount, self.currency)
    
    def __sub__(self, other: 'Money') -> 'Money':
        if self.currency != other.currency:
            raise ValueError(f"Cannot subtract {self.currency} and {other.currency}")
        return Money(self.amount - other.amount, self.currency)
    
    def __mul__(self, scalar: Decimal) -> 'Money':
        return Money(self.amount * scalar, self.currency)
    
    def __str__(self) -> str:
        return f"{self.amount} {self.currency}"


@dataclass
class Order:
    """Represents a trading order."""
    order_id: str
    instrument_id: InstrumentId
    venue: Venue
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    time_in_force: str = "GTC"  # Good Till Cancelled
    strategy_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: Decimal = Decimal('0')
    avg_fill_price: Optional[Decimal] = None
    commission: Optional[Money] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
    
    @property
    def remaining_quantity(self) -> Decimal:
        """Get remaining quantity to be filled."""
        return self.quantity - self.filled_quantity
    
    @property
    def is_complete(self) -> bool:
        """Check if order is completely filled."""
        return self.filled_quantity >= self.quantity
    
    def validate(self) -> None:
        """Validate order parameters."""
        if self.quantity <= 0:
            raise ValueError("Order quantity must be positive")
        
        if self.order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT] and self.price is None:
            raise ValueError(f"{self.order_type.value} order requires a price")
        
        if self.order_type in [OrderType.STOP, OrderType.STOP_LIMIT] and self.stop_price is None:
            raise ValueError(f"{self.order_type.value} order requires a stop price")
        
        if self.filled_quantity < 0:
            raise ValueError("Filled quantity cannot be negative")
        
        if self.filled_quantity > self.quantity:
            raise ValueError("Filled quantity cannot exceed order quantity")


@dataclass
class Fill:
    """Represents an order fill."""
    fill_id: str
    order_id: str
    instrument_id: InstrumentId
    venue: Venue
    side: OrderSide
    quantity: Decimal
    price: Decimal
    timestamp: datetime
    commission: Optional[Money] = None
    liquidity_side: str = "taker"  # taker or maker
    
    def validate(self) -> None:
        """Validate fill parameters."""
        if self.quantity <= 0:
            raise ValueError("Fill quantity must be positive")
        if self.price <= 0:
            raise ValueError("Fill price must be positive")
        if self.liquidity_side not in ["taker", "maker"]:
            raise ValueError("Liquidity side must be 'taker' or 'maker'")


@dataclass
class Position:
    """Represents a trading position."""
    instrument_id: InstrumentId
    venue: Venue
    side: PositionSide
    quantity: Decimal
    avg_price: Decimal
    unrealized_pnl: Money
    realized_pnl: Money
    strategy_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
    
    @property
    def market_value(self) -> Decimal:
        """Calculate market value of position."""
        return self.quantity * self.avg_price
    
    def calculate_pnl(self, current_price: Decimal) -> Money:
        """Calculate unrealized P&L at current price."""
        if self.side == PositionSide.FLAT:
            return Money(Decimal('0'), self.unrealized_pnl.currency)
        
        price_diff = current_price - self.avg_price
        if self.side == PositionSide.SHORT:
            price_diff = -price_diff
        
        pnl_amount = self.quantity * price_diff
        return Money(pnl_amount, self.unrealized_pnl.currency)
    
    def validate(self) -> None:
        """Validate position parameters."""
        if self.side != PositionSide.FLAT and self.quantity <= 0:
            raise ValueError("Position quantity must be positive for non-flat positions")
        if self.side != PositionSide.FLAT and self.avg_price <= 0:
            raise ValueError("Average price must be positive for non-flat positions")


@dataclass
class SimulatedFill:
    """Represents a simulated order fill for backtesting."""
    order_id: str
    fill_price: Decimal
    fill_quantity: Decimal
    fill_time: datetime
    slippage: Decimal
    transaction_cost: Money
    market_impact: Decimal = Decimal('0')
    
    def validate(self) -> None:
        """Validate simulated fill parameters."""
        if self.fill_quantity <= 0:
            raise ValueError("Fill quantity must be positive")
        if self.fill_price <= 0:
            raise ValueError("Fill price must be positive")
        if self.slippage < 0:
            raise ValueError("Slippage cannot be negative")


@dataclass
class MarketState:
    """Represents market state at a point in time."""
    timestamp: datetime
    instrument_id: InstrumentId
    venue: Venue
    bid_price: Decimal
    ask_price: Decimal
    mid_price: Decimal
    volume: Decimal
    volatility: Optional[Decimal] = None
    
    @property
    def spread(self) -> Decimal:
        """Get bid-ask spread."""
        return self.ask_price - self.bid_price
    
    @property
    def spread_bps(self) -> Decimal:
        """Get spread in basis points."""
        return (self.spread / self.mid_price) * Decimal('10000')
    
    def validate(self) -> None:
        """Validate market state."""
        if self.bid_price <= 0:
            raise ValueError("Bid price must be positive")
        if self.ask_price <= 0:
            raise ValueError("Ask price must be positive")
        if self.bid_price >= self.ask_price:
            raise ValueError("Bid price must be less than ask price")
        if self.volume < 0:
            raise ValueError("Volume cannot be negative")


@dataclass
class ExecutionResult:
    """Result of order execution simulation."""
    order_id: str
    executed: bool
    fills: List[SimulatedFill]
    remaining_quantity: Decimal
    avg_fill_price: Optional[Decimal] = None
    total_commission: Optional[Money] = None
    rejection_reason: Optional[str] = None
    
    @property
    def total_filled_quantity(self) -> Decimal:
        """Get total filled quantity across all fills."""
        return sum(fill.fill_quantity for fill in self.fills)
    
    def validate(self) -> None:
        """Validate execution result."""
        if self.remaining_quantity < 0:
            raise ValueError("Remaining quantity cannot be negative")
        
        total_filled = self.total_filled_quantity
        if self.executed and total_filled == 0:
            raise ValueError("Executed order must have at least one fill")


@dataclass
class BacktestConfig:
    """Configuration for backtesting."""
    start_date: datetime
    end_date: datetime
    initial_capital: Money
    commission_rate: Decimal = Decimal('0.001')  # 0.1%
    slippage_rate: Decimal = Decimal('0.0005')   # 0.05%
    market_impact_rate: Decimal = Decimal('0.0001')  # 0.01%
    max_position_size: Optional[Decimal] = None
    max_leverage: Optional[Decimal] = None
    risk_free_rate: Decimal = Decimal('0.02')  # 2% annual
    
    def validate(self) -> None:
        """Validate backtest configuration."""
        if self.start_date >= self.end_date:
            raise ValueError("Start date must be before end date")
        if self.initial_capital.amount <= 0:
            raise ValueError("Initial capital must be positive")
        if self.commission_rate < 0:
            raise ValueError("Commission rate cannot be negative")
        if self.slippage_rate < 0:
            raise ValueError("Slippage rate cannot be negative")
        if self.market_impact_rate < 0:
            raise ValueError("Market impact rate cannot be negative")


@dataclass
class BacktestResults:
    """Results of a backtest run."""
    strategy_id: str
    config: BacktestConfig
    start_date: datetime
    end_date: datetime
    initial_capital: Money
    final_capital: Money
    total_return: Decimal
    annualized_return: Decimal
    volatility: Decimal
    sharpe_ratio: Decimal
    sortino_ratio: Decimal
    max_drawdown: Decimal
    max_drawdown_duration: timedelta
    calmar_ratio: Decimal
    win_rate: Decimal
    profit_factor: Decimal
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_trade_duration: timedelta
    avg_winning_trade: Money
    avg_losing_trade: Money
    largest_winning_trade: Money
    largest_losing_trade: Money
    total_commission: Money
    total_slippage: Money
    positions: List[Position] = field(default_factory=list)
    trades: List[Fill] = field(default_factory=list)
    equity_curve: List[tuple] = field(default_factory=list)  # (timestamp, equity)
    
    @property
    def total_pnl(self) -> Money:
        """Calculate total P&L."""
        return self.final_capital - self.initial_capital
    
    @property
    def return_percentage(self) -> Decimal:
        """Calculate return as percentage."""
        return (self.total_return - Decimal('1')) * Decimal('100')
    
    def validate(self) -> None:
        """Validate backtest results."""
        if self.start_date >= self.end_date:
            raise ValueError("Start date must be before end date")
        if self.total_trades < 0:
            raise ValueError("Total trades cannot be negative")
        if self.winning_trades + self.losing_trades > self.total_trades:
            raise ValueError("Winning + losing trades cannot exceed total trades")
        if not (0 <= self.win_rate <= 1):
            raise ValueError("Win rate must be between 0 and 1")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert results to dictionary for serialization."""
        return {
            "strategy_id": self.strategy_id,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "initial_capital": str(self.initial_capital.amount),
            "final_capital": str(self.final_capital.amount),
            "total_return": str(self.total_return),
            "annualized_return": str(self.annualized_return),
            "volatility": str(self.volatility),
            "sharpe_ratio": str(self.sharpe_ratio),
            "sortino_ratio": str(self.sortino_ratio),
            "max_drawdown": str(self.max_drawdown),
            "max_drawdown_duration_days": self.max_drawdown_duration.days,
            "calmar_ratio": str(self.calmar_ratio),
            "win_rate": str(self.win_rate),
            "profit_factor": str(self.profit_factor),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "avg_trade_duration_hours": self.avg_trade_duration.total_seconds() / 3600,
            "avg_winning_trade": str(self.avg_winning_trade.amount),
            "avg_losing_trade": str(self.avg_losing_trade.amount),
            "largest_winning_trade": str(self.largest_winning_trade.amount),
            "largest_losing_trade": str(self.largest_losing_trade.amount),
            "total_commission": str(self.total_commission.amount),
            "total_slippage": str(self.total_slippage.amount),
            "return_percentage": str(self.return_percentage)
        }


@dataclass
class PerformanceMetrics:
    """Performance metrics for strategy evaluation."""
    total_return: Decimal
    annualized_return: Decimal
    volatility: Decimal
    sharpe_ratio: Decimal
    sortino_ratio: Decimal
    calmar_ratio: Decimal
    max_drawdown: Decimal
    win_rate: Decimal
    profit_factor: Decimal
    var_95: Decimal  # Value at Risk at 95% confidence
    cvar_95: Decimal  # Conditional Value at Risk at 95% confidence
    
    def validate(self) -> None:
        """Validate performance metrics."""
        if not (0 <= self.win_rate <= 1):
            raise ValueError("Win rate must be between 0 and 1")
        if self.max_drawdown < 0:
            raise ValueError("Max drawdown must be non-negative")
        if self.volatility < 0:
            raise ValueError("Volatility must be non-negative")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "total_return": str(self.total_return),
            "annualized_return": str(self.annualized_return),
            "volatility": str(self.volatility),
            "sharpe_ratio": str(self.sharpe_ratio),
            "sortino_ratio": str(self.sortino_ratio),
            "calmar_ratio": str(self.calmar_ratio),
            "max_drawdown": str(self.max_drawdown),
            "win_rate": str(self.win_rate),
            "profit_factor": str(self.profit_factor),
            "var_95": str(self.var_95),
            "cvar_95": str(self.cvar_95)
        }