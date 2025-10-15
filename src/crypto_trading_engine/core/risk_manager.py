"""
Risk manager interface for portfolio monitoring and risk control.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum

from nautilus_trader.model.objects import Money
from nautilus_trader.model.identifiers import StrategyId

from ..models.core import Position, Order, Instrument
from ..models.trading_mode import TradingMode


class RiskLevel(Enum):
    """Risk level enumeration."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskAlert:
    """Risk alert information."""
    
    def __init__(
        self,
        level: RiskLevel,
        message: str,
        strategy_id: Optional[StrategyId] = None,
        position_id: Optional[str] = None,
        timestamp: Optional[datetime] = None
    ):
        self.level = level
        self.message = message
        self.strategy_id = strategy_id
        self.position_id = position_id
        self.timestamp = timestamp or datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "level": self.level.value,
            "message": self.message,
            "strategy_id": str(self.strategy_id) if self.strategy_id else None,
            "position_id": self.position_id,
            "timestamp": self.timestamp.isoformat()
        }


class RiskAssessment:
    """Risk assessment result."""
    
    def __init__(
        self,
        is_acceptable: bool,
        risk_level: RiskLevel,
        message: str = "",
        metrics: Optional[Dict[str, Any]] = None
    ):
        self.is_acceptable = is_acceptable
        self.risk_level = risk_level
        self.message = message
        self.metrics = metrics or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "is_acceptable": self.is_acceptable,
            "risk_level": self.risk_level.value,
            "message": self.message,
            "metrics": self.metrics
        }


class RiskManager(ABC):
    """
    Abstract base class for risk management with portfolio monitoring.
    
    Provides risk controls and monitoring for all trading modes.
    """
    
    def __init__(
        self,
        config: Dict[str, Any],
        trading_mode: TradingMode = TradingMode.BACKTEST
    ):
        """
        Initialize the risk manager.
        
        Args:
            config: Risk management configuration
            trading_mode: Current trading mode
        """
        self.config = config
        self.trading_mode = trading_mode
        self.is_active = False
        self.alerts: List[RiskAlert] = []
        self.positions: Dict[str, Position] = {}
        self.orders: Dict[str, Order] = {}
        
        # Risk limits
        self.max_portfolio_loss = config.get("max_portfolio_loss", Decimal("0.05"))  # 5%
        self.max_position_size = config.get("max_position_size", Decimal("0.1"))     # 10%
        self.max_leverage = config.get("max_leverage", Decimal("3.0"))               # 3x
        self.max_daily_trades = config.get("max_daily_trades", 100)
        
        # Callbacks
        self.on_risk_alert_callback: Optional[Callable[[RiskAlert], None]] = None
        self.on_emergency_shutdown_callback: Optional[Callable[[], None]] = None
    
    @abstractmethod
    def check_position_risk(self, position: Position) -> RiskAssessment:
        """
        Check risk for a specific position.
        
        Args:
            position: Position to assess
            
        Returns:
            Risk assessment result
        """
        pass
    
    @abstractmethod
    def check_order_risk(self, order: Order) -> RiskAssessment:
        """
        Check risk for a pending order.
        
        Args:
            order: Order to assess
            
        Returns:
            Risk assessment result
        """
        pass
    
    @abstractmethod
    def check_portfolio_risk(self) -> RiskAssessment:
        """
        Check overall portfolio risk.
        
        Returns:
            Portfolio risk assessment
        """
        pass
    
    @abstractmethod
    def calculate_var(self, confidence: float = 0.95, horizon_days: int = 1) -> Money:
        """
        Calculate Value at Risk.
        
        Args:
            confidence: Confidence level (e.g., 0.95 for 95%)
            horizon_days: Time horizon in days
            
        Returns:
            VaR amount
        """
        pass
    
    @abstractmethod
    def calculate_position_size(
        self, 
        instrument: Instrument, 
        risk_amount: Money,
        entry_price: Decimal,
        stop_loss_price: Decimal
    ) -> Decimal:
        """
        Calculate optimal position size based on risk.
        
        Args:
            instrument: Trading instrument
            risk_amount: Maximum risk amount
            entry_price: Planned entry price
            stop_loss_price: Stop loss price
            
        Returns:
            Recommended position size
        """
        pass
    
    def start(self) -> None:
        """Start risk monitoring."""
        if self.is_active:
            raise RuntimeError("Risk manager is already active")
        
        self.is_active = True
        self.on_start()
    
    def stop(self) -> None:
        """Stop risk monitoring."""
        if not self.is_active:
            raise RuntimeError("Risk manager is not active")
        
        self.is_active = False
        self.on_stop()
    
    def on_start(self) -> None:
        """Called when risk manager starts. Override in subclasses."""
        pass
    
    def on_stop(self) -> None:
        """Called when risk manager stops. Override in subclasses."""
        pass
    
    def set_trading_mode(self, mode: TradingMode) -> None:
        """
        Set trading mode.
        
        Args:
            mode: New trading mode
        """
        self.trading_mode = mode
        self.on_trading_mode_changed(mode)
    
    def on_trading_mode_changed(self, mode: TradingMode) -> None:
        """
        Called when trading mode changes.
        
        Args:
            mode: New trading mode
        """
        pass
    
    def add_position(self, position: Position) -> None:
        """
        Add a position for monitoring.
        
        Args:
            position: Position to monitor
        """
        self.positions[str(position.id)] = position
        
        # Check risk immediately
        assessment = self.check_position_risk(position)
        if not assessment.is_acceptable:
            self._create_alert(
                assessment.risk_level,
                f"Position risk violation: {assessment.message}",
                position_id=str(position.id)
            )
    
    def remove_position(self, position_id: str) -> None:
        """
        Remove a position from monitoring.
        
        Args:
            position_id: Position ID to remove
        """
        if position_id in self.positions:
            del self.positions[position_id]
    
    def add_order(self, order: Order) -> RiskAssessment:
        """
        Add an order for risk checking.
        
        Args:
            order: Order to check
            
        Returns:
            Risk assessment result
        """
        assessment = self.check_order_risk(order)
        
        if assessment.is_acceptable:
            self.orders[str(order.id)] = order
        else:
            self._create_alert(
                assessment.risk_level,
                f"Order risk violation: {assessment.message}",
                order_id=str(order.id)
            )
        
        return assessment
    
    def remove_order(self, order_id: str) -> None:
        """
        Remove an order from monitoring.
        
        Args:
            order_id: Order ID to remove
        """
        if order_id in self.orders:
            del self.orders[order_id]
    
    def enforce_portfolio_limits(self) -> List[RiskAlert]:
        """
        Enforce portfolio-level risk limits.
        
        Returns:
            List of risk alerts generated
        """
        alerts = []
        
        # Check portfolio risk
        portfolio_assessment = self.check_portfolio_risk()
        if not portfolio_assessment.is_acceptable:
            alert = self._create_alert(
                portfolio_assessment.risk_level,
                f"Portfolio risk limit exceeded: {portfolio_assessment.message}"
            )
            alerts.append(alert)
            
            # Emergency shutdown if critical
            if portfolio_assessment.risk_level == RiskLevel.CRITICAL:
                self.emergency_shutdown()
        
        return alerts
    
    def emergency_shutdown(self) -> None:
        """
        Emergency shutdown procedure.
        
        Triggers immediate position closure and strategy suspension.
        """
        alert = self._create_alert(
            RiskLevel.CRITICAL,
            "Emergency shutdown triggered - closing all positions"
        )
        
        if self.on_emergency_shutdown_callback:
            self.on_emergency_shutdown_callback()
    
    def get_risk_metrics(self) -> Dict[str, Any]:
        """
        Get current risk metrics.
        
        Returns:
            Dictionary of risk metrics
        """
        portfolio_assessment = self.check_portfolio_risk()
        
        return {
            "trading_mode": self.trading_mode.value,
            "is_active": self.is_active,
            "portfolio_risk_level": portfolio_assessment.risk_level.value,
            "portfolio_risk_acceptable": portfolio_assessment.is_acceptable,
            "position_count": len(self.positions),
            "order_count": len(self.orders),
            "alert_count": len(self.alerts),
            "recent_alerts": [a.to_dict() for a in self.alerts[-10:]],  # Last 10 alerts
            "risk_limits": {
                "max_portfolio_loss": str(self.max_portfolio_loss),
                "max_position_size": str(self.max_position_size),
                "max_leverage": str(self.max_leverage),
                "max_daily_trades": self.max_daily_trades
            }
        }
    
    def get_alerts(self, level: Optional[RiskLevel] = None, hours: int = 24) -> List[RiskAlert]:
        """
        Get risk alerts.
        
        Args:
            level: Filter by risk level
            hours: Hours to look back
            
        Returns:
            List of matching alerts
        """
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        alerts = [a for a in self.alerts if a.timestamp >= cutoff_time]
        
        if level:
            alerts = [a for a in alerts if a.level == level]
        
        return alerts
    
    def clear_alerts(self, hours: int = 24) -> None:
        """
        Clear old alerts.
        
        Args:
            hours: Clear alerts older than this many hours
        """
        cutoff_time = datetime.now() - timedelta(hours=hours)
        self.alerts = [a for a in self.alerts if a.timestamp >= cutoff_time]
    
    def set_callbacks(
        self,
        on_risk_alert: Optional[Callable[[RiskAlert], None]] = None,
        on_emergency_shutdown: Optional[Callable[[], None]] = None
    ) -> None:
        """
        Set risk event callbacks.
        
        Args:
            on_risk_alert: Risk alert callback
            on_emergency_shutdown: Emergency shutdown callback
        """
        self.on_risk_alert_callback = on_risk_alert
        self.on_emergency_shutdown_callback = on_emergency_shutdown
    
    def _create_alert(
        self,
        level: RiskLevel,
        message: str,
        strategy_id: Optional[StrategyId] = None,
        position_id: Optional[str] = None,
        order_id: Optional[str] = None
    ) -> RiskAlert:
        """Create and store a risk alert."""
        alert = RiskAlert(
            level=level,
            message=message,
            strategy_id=strategy_id,
            position_id=position_id
        )
        
        self.alerts.append(alert)
        
        if self.on_risk_alert_callback:
            self.on_risk_alert_callback(alert)
        
        return alert
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert risk manager to dictionary.
        
        Returns:
            Dictionary representation
        """
        return {
            "config": self.config,
            "trading_mode": self.trading_mode.value,
            "is_active": self.is_active,
            "positions": {k: v.to_dict() for k, v in self.positions.items()},
            "orders": {k: v.to_dict() for k, v in self.orders.items()},
            "alerts": [a.to_dict() for a in self.alerts],
            "risk_metrics": self.get_risk_metrics()
        }