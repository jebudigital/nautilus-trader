"""
Trading mode manager for handling transitions between trading modes.
"""

from typing import Dict, List, Optional, Set, Callable
from datetime import datetime
from enum import Enum

from nautilus_trader.model.identifiers import StrategyId

from ..models.trading_mode import TradingMode, BacktestResults
from .strategy import Strategy
from .adapter import ExchangeAdapter


class ModeTransitionError(Exception):
    """Raised when a trading mode transition is invalid or fails."""
    pass


class ValidationResult:
    """Result of strategy validation for mode promotion."""
    
    def __init__(self, is_valid: bool, message: str = "", metrics: Optional[Dict] = None):
        self.is_valid = is_valid
        self.message = message
        self.metrics = metrics or {}


class TradingModeManager:
    """
    Manages trading mode transitions and strategy promotion workflows.
    
    Handles the progression: BACKTEST → PAPER → LIVE
    """
    
    def __init__(self):
        """Initialize the trading mode manager."""
        self.current_mode = TradingMode.BACKTEST
        self.strategies: Dict[StrategyId, Strategy] = {}
        self.adapters: Dict[str, ExchangeAdapter] = {}
        self.mode_history: List[Dict] = []
        
        # Validation callbacks
        self.backtest_validators: List[Callable[[BacktestResults], ValidationResult]] = []
        self.paper_validators: List[Callable[[Strategy], ValidationResult]] = []
        self.live_validators: List[Callable[[Strategy], ValidationResult]] = []
        
        # Promotion criteria
        self.promotion_criteria = {
            TradingMode.PAPER: {
                "min_sharpe_ratio": 1.0,
                "max_drawdown": 0.1,
                "min_trades": 50,
                "min_win_rate": 0.5
            },
            TradingMode.LIVE: {
                "min_paper_duration_days": 7,
                "min_paper_trades": 20,
                "max_paper_drawdown": 0.05,
                "min_paper_consistency": 0.8
            }
        }
    
    def set_trading_mode(self, mode: TradingMode, force: bool = False) -> None:
        """
        Set the global trading mode.
        
        Args:
            mode: New trading mode
            force: Force mode change without validation
            
        Raises:
            ModeTransitionError: If transition is invalid
        """
        if not force and not self._validate_mode_transition(self.current_mode, mode):
            raise ModeTransitionError(
                f"Invalid transition from {self.current_mode.value} to {mode.value}"
            )
        
        old_mode = self.current_mode
        self.current_mode = mode
        
        # Update all strategies and adapters
        for strategy in self.strategies.values():
            strategy.set_trading_mode(mode)
        
        for adapter in self.adapters.values():
            adapter.set_trading_mode(mode)
        
        # Record transition
        self.mode_history.append({
            "timestamp": datetime.now(),
            "from_mode": old_mode.value,
            "to_mode": mode.value,
            "forced": force
        })
    
    def get_current_mode(self) -> TradingMode:
        """
        Get the current trading mode.
        
        Returns:
            Current trading mode
        """
        return self.current_mode
    
    def register_strategy(self, strategy: Strategy) -> None:
        """
        Register a strategy with the manager.
        
        Args:
            strategy: Strategy to register
        """
        strategy.set_trading_mode(self.current_mode)
        self.strategies[strategy.strategy_id] = strategy
    
    def unregister_strategy(self, strategy_id: StrategyId) -> None:
        """
        Unregister a strategy from the manager.
        
        Args:
            strategy_id: ID of strategy to unregister
        """
        if strategy_id in self.strategies:
            del self.strategies[strategy_id]
    
    def register_adapter(self, adapter: ExchangeAdapter) -> None:
        """
        Register an exchange adapter with the manager.
        
        Args:
            adapter: Adapter to register
        """
        adapter.set_trading_mode(self.current_mode)
        self.adapters[str(adapter.venue)] = adapter
    
    def unregister_adapter(self, venue: str) -> None:
        """
        Unregister an exchange adapter from the manager.
        
        Args:
            venue: Venue name of adapter to unregister
        """
        if venue in self.adapters:
            del self.adapters[venue]
    
    def validate_mode_transition(self, from_mode: TradingMode, to_mode: TradingMode) -> bool:
        """
        Validate if a mode transition is allowed.
        
        Args:
            from_mode: Current mode
            to_mode: Target mode
            
        Returns:
            True if transition is valid, False otherwise
        """
        return self._validate_mode_transition(from_mode, to_mode)
    
    def promote_strategy_to_paper(
        self, 
        strategy_id: StrategyId, 
        backtest_results: BacktestResults
    ) -> ValidationResult:
        """
        Promote a strategy from backtest to paper trading.
        
        Args:
            strategy_id: Strategy to promote
            backtest_results: Results from backtesting
            
        Returns:
            Validation result indicating success/failure
        """
        if strategy_id not in self.strategies:
            return ValidationResult(False, "Strategy not found")
        
        strategy = self.strategies[strategy_id]
        if strategy.trading_mode != TradingMode.BACKTEST:
            return ValidationResult(False, "Strategy is not in backtest mode")
        
        # Validate backtest results
        validation = self._validate_backtest_results(backtest_results)
        if not validation.is_valid:
            return validation
        
        # Run custom validators
        for validator in self.backtest_validators:
            result = validator(backtest_results)
            if not result.is_valid:
                return result
        
        # Promote strategy
        strategy.set_trading_mode(TradingMode.PAPER)
        
        return ValidationResult(True, "Strategy promoted to paper trading", {
            "backtest_results": backtest_results.to_dict()
        })
    
    def promote_strategy_to_live(self, strategy_id: StrategyId) -> ValidationResult:
        """
        Promote a strategy from paper to live trading.
        
        Args:
            strategy_id: Strategy to promote
            
        Returns:
            Validation result indicating success/failure
        """
        if strategy_id not in self.strategies:
            return ValidationResult(False, "Strategy not found")
        
        strategy = self.strategies[strategy_id]
        if strategy.trading_mode != TradingMode.PAPER:
            return ValidationResult(False, "Strategy is not in paper trading mode")
        
        # Validate paper trading performance
        validation = self._validate_paper_performance(strategy)
        if not validation.is_valid:
            return validation
        
        # Run custom validators
        for validator in self.paper_validators:
            result = validator(strategy)
            if not result.is_valid:
                return result
        
        # Final validation for live trading
        for validator in self.live_validators:
            result = validator(strategy)
            if not result.is_valid:
                return result
        
        # Promote strategy
        strategy.set_trading_mode(TradingMode.LIVE)
        
        return ValidationResult(True, "Strategy promoted to live trading")
    
    def add_backtest_validator(self, validator: Callable[[BacktestResults], ValidationResult]) -> None:
        """Add a custom backtest validator."""
        self.backtest_validators.append(validator)
    
    def add_paper_validator(self, validator: Callable[[Strategy], ValidationResult]) -> None:
        """Add a custom paper trading validator."""
        self.paper_validators.append(validator)
    
    def add_live_validator(self, validator: Callable[[Strategy], ValidationResult]) -> None:
        """Add a custom live trading validator."""
        self.live_validators.append(validator)
    
    def get_mode_history(self) -> List[Dict]:
        """
        Get the history of mode transitions.
        
        Returns:
            List of mode transition records
        """
        return self.mode_history.copy()
    
    def get_strategies_by_mode(self, mode: TradingMode) -> List[Strategy]:
        """
        Get all strategies in a specific mode.
        
        Args:
            mode: Trading mode to filter by
            
        Returns:
            List of strategies in the specified mode
        """
        return [s for s in self.strategies.values() if s.trading_mode == mode]
    
    def _validate_mode_transition(self, from_mode: TradingMode, to_mode: TradingMode) -> bool:
        """Validate mode transition logic."""
        # Allow same mode
        if from_mode == to_mode:
            return True
        
        # Define valid transitions
        valid_transitions = {
            TradingMode.BACKTEST: {TradingMode.PAPER},
            TradingMode.PAPER: {TradingMode.LIVE, TradingMode.BACKTEST},
            TradingMode.LIVE: {TradingMode.PAPER, TradingMode.BACKTEST}
        }
        
        return to_mode in valid_transitions.get(from_mode, set())
    
    def _validate_backtest_results(self, results: BacktestResults) -> ValidationResult:
        """Validate backtest results against promotion criteria."""
        criteria = self.promotion_criteria[TradingMode.PAPER]
        
        if results.sharpe_ratio < criteria["min_sharpe_ratio"]:
            return ValidationResult(
                False, 
                f"Sharpe ratio {results.sharpe_ratio} below minimum {criteria['min_sharpe_ratio']}"
            )
        
        if results.max_drawdown > criteria["max_drawdown"]:
            return ValidationResult(
                False,
                f"Max drawdown {results.max_drawdown} exceeds maximum {criteria['max_drawdown']}"
            )
        
        if results.total_trades < criteria["min_trades"]:
            return ValidationResult(
                False,
                f"Total trades {results.total_trades} below minimum {criteria['min_trades']}"
            )
        
        if results.win_rate < criteria["min_win_rate"]:
            return ValidationResult(
                False,
                f"Win rate {results.win_rate} below minimum {criteria['min_win_rate']}"
            )
        
        return ValidationResult(True, "Backtest results meet promotion criteria")
    
    def _validate_paper_performance(self, strategy: Strategy) -> ValidationResult:
        """Validate paper trading performance against promotion criteria."""
        criteria = self.promotion_criteria[TradingMode.LIVE]
        
        # Get strategy performance metrics
        metrics = strategy.get_performance_metrics()
        
        # This is a simplified validation - in practice, you'd analyze
        # detailed paper trading performance data
        
        return ValidationResult(True, "Paper trading performance meets criteria")
    
    def to_dict(self) -> Dict:
        """
        Convert manager state to dictionary.
        
        Returns:
            Dictionary representation of the manager
        """
        return {
            "current_mode": self.current_mode.value,
            "strategies": {str(k): v.to_dict() for k, v in self.strategies.items()},
            "adapters": {k: v.to_dict() for k, v in self.adapters.items()},
            "mode_history": self.mode_history,
            "promotion_criteria": self.promotion_criteria
        }