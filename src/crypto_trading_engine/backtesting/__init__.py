"""
Backtesting module for crypto trading engine.

This module provides comprehensive backtesting capabilities including:
- Realistic order execution simulation
- Transaction cost modeling
- Performance metrics calculation
- Strategy base classes
"""

from .engine import BacktestEngine
from .models import (
    BacktestConfig, BacktestResults, PerformanceMetrics,
    Order, Fill, Position, SimulatedFill, MarketState, ExecutionResult,
    Money, TradingMode, OrderSide, OrderType, OrderStatus, PositionSide
)
from .strategy import Strategy, SimpleMovingAverageStrategy, BuyAndHoldStrategy

__all__ = [
    'BacktestEngine',
    'BacktestConfig',
    'BacktestResults', 
    'PerformanceMetrics',
    'Order',
    'Fill',
    'Position',
    'SimulatedFill',
    'MarketState',
    'ExecutionResult',
    'Money',
    'TradingMode',
    'OrderSide',
    'OrderType', 
    'OrderStatus',
    'PositionSide',
    'Strategy',
    'SimpleMovingAverageStrategy',
    'BuyAndHoldStrategy'
]