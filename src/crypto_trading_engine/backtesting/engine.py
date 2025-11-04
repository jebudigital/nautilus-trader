"""
Backtesting engine for strategy simulation and performance evaluation.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Optional, Any, Callable
import numpy as np
import pandas as pd
from collections import defaultdict

from nautilus_trader.model.identifiers import InstrumentId, Venue

from ..data.models import OHLCVData, TimeFrame
from ..data.store import HistoricalDataStore
from ..data.ingestion import DataIngestionEngine
from .models import (
    Order, Fill, Position, SimulatedFill, MarketState, ExecutionResult,
    BacktestConfig, BacktestResults, PerformanceMetrics, Money,
    OrderSide, OrderType, OrderStatus, PositionSide, TradingMode
)


logger = logging.getLogger(__name__)


class BacktestEngine:
    """
    Backtesting engine for strategy simulation with realistic market conditions.
    
    Features:
    - Realistic order execution simulation with slippage and market impact
    - Transaction cost modeling for different venues
    - Portfolio tracking and risk management
    - Comprehensive performance metrics calculation
    - Support for multiple instruments and venues
    """
    
    def __init__(
        self,
        data_store: HistoricalDataStore,
        data_engine: DataIngestionEngine
    ):
        """
        Initialize the backtesting engine.
        
        Args:
            data_store: Historical data store for market data
            data_engine: Data ingestion engine for Parquet data
        """
        self.data_store = data_store
        self.data_engine = data_engine
        
        # Simulation state
        self.current_time: Optional[datetime] = None
        self.portfolio_value: Money = Money(Decimal('0'), 'USD')
        self.cash_balance: Money = Money(Decimal('0'), 'USD')
        self.positions: Dict[str, Position] = {}  # instrument_id -> Position
        self.orders: Dict[str, Order] = {}  # order_id -> Order
        self.fills: List[Fill] = []
        self.market_states: Dict[str, MarketState] = {}  # instrument_id -> MarketState
        
        # Performance tracking
        self.equity_curve: List[tuple] = []  # (timestamp, equity)
        self.drawdown_series: List[tuple] = []  # (timestamp, drawdown)
        self.trade_history: List[Dict[str, Any]] = []
        
        # Configuration
        self.config: Optional[BacktestConfig] = None
        
        logger.info("Initialized BacktestEngine")
    
    async def run_backtest(
        self,
        strategy: 'Strategy',
        config: BacktestConfig,
        instruments: List[InstrumentId],
        venues: List[Venue],
        timeframe: TimeFrame = TimeFrame.HOUR_1
    ) -> BacktestResults:
        """
        Run a complete backtest for a strategy.
        
        Args:
            strategy: Trading strategy to test
            config: Backtest configuration
            instruments: List of instruments to trade
            venues: List of venues to use
            timeframe: Data timeframe for simulation
            
        Returns:
            Backtest results with performance metrics
        """
        logger.info(f"Starting backtest for strategy {strategy.strategy_id}")
        logger.info(f"Period: {config.start_date} to {config.end_date}")
        logger.info(f"Initial capital: {config.initial_capital}")
        
        # Validate configuration
        config.validate()
        self.config = config
        
        # Initialize portfolio
        self._initialize_portfolio(config.initial_capital)
        
        # Load historical data for all instruments
        market_data = await self._load_market_data(
            instruments, venues, timeframe, config.start_date, config.end_date
        )
        
        if not market_data:
            raise ValueError("No market data available for backtest period")
        
        logger.info(f"Loaded {len(market_data)} data points")
        
        # Initialize strategy
        await strategy.initialize(self, config)
        
        # Run simulation
        await self._run_simulation(strategy, market_data)
        
        # Calculate final results
        results = await self._calculate_results(strategy, config)
        
        logger.info(f"Backtest completed. Total return: {results.return_percentage:.2f}%")
        logger.info(f"Sharpe ratio: {results.sharpe_ratio:.2f}")
        logger.info(f"Max drawdown: {results.max_drawdown:.2f}%")
        
        return results
    
    def _initialize_portfolio(self, initial_capital: Money) -> None:
        """Initialize portfolio with starting capital."""
        self.cash_balance = initial_capital
        self.portfolio_value = initial_capital
        self.positions.clear()
        self.orders.clear()
        self.fills.clear()
        self.equity_curve.clear()
        self.drawdown_series.clear()
        self.trade_history.clear()
        
        logger.info(f"Initialized portfolio with {initial_capital}")
    
    async def _load_market_data(
        self,
        instruments: List[InstrumentId],
        venues: List[Venue],
        timeframe: TimeFrame,
        start_date: datetime,
        end_date: datetime
    ) -> List[OHLCVData]:
        """Load and combine market data for all instruments."""
        all_data = []
        
        for instrument in instruments:
            for venue in venues:
                try:
                    # Try Parquet first for efficiency
                    data = await self.data_engine.read_ohlcv_parquet(
                        instrument_id=instrument,
                        venue=venue,
                        timeframe=timeframe,
                        start_time=start_date,
                        end_time=end_date
                    )
                    
                    if not data:
                        # Fallback to SQLite
                        data = await self.data_store.get_ohlcv_data(
                            instrument_id=instrument,
                            venue=venue,
                            timeframe=timeframe,
                            start_time=start_date,
                            end_time=end_date
                        )
                    
                    all_data.extend(data)
                    logger.info(f"Loaded {len(data)} data points for {instrument} on {venue}")
                    
                except Exception as e:
                    logger.warning(f"Failed to load data for {instrument} on {venue}: {e}")
        
        # Sort by timestamp
        all_data.sort(key=lambda x: x.timestamp)
        return all_data
    
    async def _run_simulation(self, strategy: 'Strategy', market_data: List[OHLCVData]) -> None:
        """Run the main simulation loop."""
        logger.info("Starting simulation loop")
        
        for i, data_point in enumerate(market_data):
            self.current_time = data_point.timestamp
            
            # Update market state
            self._update_market_state(data_point)
            
            # Update portfolio valuation
            self._update_portfolio_value()
            
            # Record equity curve
            self.equity_curve.append((self.current_time, self.portfolio_value.amount))
            
            # Process pending orders
            await self._process_orders()
            
            # Call strategy with new market data
            await strategy.on_market_data(data_point, self.market_states[str(data_point.instrument_id)])
            
            # Log progress periodically
            if i % 1000 == 0:
                logger.debug(f"Processed {i}/{len(market_data)} data points")
        
        logger.info("Simulation loop completed")
    
    def _update_market_state(self, data: OHLCVData) -> None:
        """Update market state with new OHLCV data."""
        instrument_key = str(data.instrument_id)
        
        # Create market state from OHLCV data
        # Use close price as both bid and ask with a small spread
        spread_bps = Decimal('5')  # 5 basis points spread
        mid_price = data.close_price
        spread = mid_price * spread_bps / Decimal('10000')
        
        market_state = MarketState(
            timestamp=data.timestamp,
            instrument_id=data.instrument_id,
            venue=data.venue,
            bid_price=mid_price - spread / 2,
            ask_price=mid_price + spread / 2,
            mid_price=mid_price,
            volume=data.volume
        )
        
        self.market_states[instrument_key] = market_state
    
    def _update_portfolio_value(self) -> None:
        """Update total portfolio value based on current positions."""
        total_value = self.cash_balance.amount
        
        for position in self.positions.values():
            if position.side != PositionSide.FLAT:
                instrument_key = str(position.instrument_id)
                if instrument_key in self.market_states:
                    current_price = self.market_states[instrument_key].mid_price
                    position_value = position.quantity * current_price
                    total_value += position_value
        
        self.portfolio_value = Money(total_value, self.cash_balance.currency)
    
    async def _process_orders(self) -> None:
        """Process all pending orders."""
        orders_to_process = [
            order for order in self.orders.values()
            if order.status in [OrderStatus.PENDING, OrderStatus.SUBMITTED]
        ]
        
        for order in orders_to_process:
            await self._execute_order(order)
    
    async def _execute_order(self, order: Order) -> ExecutionResult:
        """
        Execute an order with realistic simulation.
        
        Args:
            order: Order to execute
            
        Returns:
            Execution result with fills and costs
        """
        logger.info(f"Executing order {order.order_id}: {order.side.value} {order.quantity} {order.instrument_id}")
        
        instrument_key = str(order.instrument_id)
        
        if instrument_key not in self.market_states:
            # No market data available, reject order
            logger.warning(f"No market data for {instrument_key}, rejecting order")
            order.status = OrderStatus.REJECTED
            return ExecutionResult(
                order_id=order.order_id,
                executed=False,
                fills=[],
                remaining_quantity=order.quantity,
                rejection_reason="No market data available"
            )
        
        market_state = self.market_states[instrument_key]
        
        # Determine execution price based on order type
        execution_price = self._calculate_execution_price(order, market_state)
        
        if execution_price is None:
            # Order conditions not met (e.g., limit price not reached)
            return ExecutionResult(
                order_id=order.order_id,
                executed=False,
                fills=[],
                remaining_quantity=order.remaining_quantity
            )
        
        # Calculate slippage and market impact
        slippage = self._calculate_slippage(order, market_state)
        market_impact = self._calculate_market_impact(order, market_state)
        
        # Adjust execution price for slippage and market impact
        if order.side == OrderSide.BUY:
            final_price = execution_price + slippage + market_impact
        else:
            final_price = execution_price - slippage - market_impact
        
        # Calculate commission
        commission = self._calculate_commission(order, final_price)
        
        # Check if we have sufficient funds/position
        if not self._check_order_feasibility(order, final_price, commission):
            logger.warning(f"Order {order.order_id} rejected: insufficient funds. Required: {order.quantity * final_price + commission.amount}, Available: {self.cash_balance.amount}")
            order.status = OrderStatus.REJECTED
            return ExecutionResult(
                order_id=order.order_id,
                executed=False,
                fills=[],
                remaining_quantity=order.remaining_quantity,
                rejection_reason="Insufficient funds or position"
            )
        
        # Execute the order
        fill_quantity = order.remaining_quantity  # Full fill for simplicity
        
        fill = Fill(
            fill_id=str(uuid.uuid4()),
            order_id=order.order_id,
            instrument_id=order.instrument_id,
            venue=order.venue,
            side=order.side,
            quantity=fill_quantity,
            price=final_price,
            timestamp=self.current_time,
            commission=commission
        )
        
        # Update order
        order.filled_quantity += fill_quantity
        order.avg_fill_price = final_price
        order.commission = commission
        order.status = OrderStatus.FILLED if order.is_complete else OrderStatus.PARTIALLY_FILLED
        
        # Update portfolio
        self._update_position(fill)
        self._update_cash_balance(fill)
        
        # Record fill
        self.fills.append(fill)
        
        logger.info(f"Order {order.order_id} executed: {fill_quantity} @ {final_price}, commission: {commission.amount}")
        
        # Create simulated fill for result
        simulated_fill = SimulatedFill(
            order_id=order.order_id,
            fill_price=final_price,
            fill_quantity=fill_quantity,
            fill_time=self.current_time,
            slippage=slippage,
            transaction_cost=commission,
            market_impact=market_impact
        )
        
        return ExecutionResult(
            order_id=order.order_id,
            executed=True,
            fills=[simulated_fill],
            remaining_quantity=order.remaining_quantity,
            avg_fill_price=final_price,
            total_commission=commission
        )
    
    def _calculate_execution_price(self, order: Order, market_state: MarketState) -> Optional[Decimal]:
        """Calculate execution price based on order type and market conditions."""
        if order.order_type == OrderType.MARKET:
            # Market orders execute at current market price
            return market_state.ask_price if order.side == OrderSide.BUY else market_state.bid_price
        
        elif order.order_type == OrderType.LIMIT:
            # Limit orders execute only if price is favorable
            if order.side == OrderSide.BUY:
                if market_state.ask_price <= order.price:
                    return min(order.price, market_state.ask_price)
            else:  # SELL
                if market_state.bid_price >= order.price:
                    return max(order.price, market_state.bid_price)
            return None
        
        # For simplicity, other order types not implemented
        return None
    
    def _calculate_slippage(self, order: Order, market_state: MarketState) -> Decimal:
        """Calculate slippage based on order size and market conditions."""
        if not self.config:
            return Decimal('0')
        
        base_slippage = market_state.mid_price * self.config.slippage_rate
        
        # Increase slippage for larger orders
        size_factor = min(order.quantity / Decimal('1000'), Decimal('2'))  # Cap at 2x
        
        return base_slippage * (Decimal('1') + size_factor)
    
    def _calculate_market_impact(self, order: Order, market_state: MarketState) -> Decimal:
        """Calculate market impact based on order size and liquidity."""
        if not self.config:
            return Decimal('0')
        
        # Simple market impact model
        impact_rate = self.config.market_impact_rate
        
        # Scale by order size relative to average volume
        volume_ratio = order.quantity / max(market_state.volume, Decimal('1'))
        impact_factor = volume_ratio ** Decimal('0.5')  # Square root impact
        
        return market_state.mid_price * impact_rate * impact_factor
    
    def _calculate_commission(self, order: Order, price: Decimal) -> Money:
        """Calculate commission for the order."""
        if not self.config:
            return Money(Decimal('0'), 'USD')
        
        notional_value = order.quantity * price
        commission_amount = notional_value * self.config.commission_rate
        
        return Money(commission_amount, self.cash_balance.currency)
    
    def _check_order_feasibility(self, order: Order, price: Decimal, commission: Money) -> bool:
        """Check if order can be executed given current portfolio state."""
        if order.side == OrderSide.BUY:
            # Check if we have enough cash
            required_cash = (order.quantity * price) + commission.amount
            return self.cash_balance.amount >= required_cash
        else:  # SELL
            # Check if we have enough position
            instrument_key = str(order.instrument_id)
            if instrument_key in self.positions:
                position = self.positions[instrument_key]
                if position.side == PositionSide.LONG:
                    return position.quantity >= order.quantity
            return False
    
    def _update_position(self, fill: Fill) -> None:
        """Update position based on fill."""
        instrument_key = str(fill.instrument_id)
        
        if instrument_key not in self.positions:
            # Create new position
            side = PositionSide.LONG if fill.side == OrderSide.BUY else PositionSide.SHORT
            self.positions[instrument_key] = Position(
                instrument_id=fill.instrument_id,
                venue=fill.venue,
                side=side,
                quantity=fill.quantity,
                avg_price=fill.price,
                unrealized_pnl=Money(Decimal('0'), self.cash_balance.currency),
                realized_pnl=Money(Decimal('0'), self.cash_balance.currency),
                timestamp=fill.timestamp
            )
        else:
            # Update existing position
            position = self.positions[instrument_key]
            
            if fill.side == OrderSide.BUY:
                if position.side == PositionSide.LONG or position.side == PositionSide.FLAT:
                    # Increase long position
                    total_cost = (position.quantity * position.avg_price) + (fill.quantity * fill.price)
                    total_quantity = position.quantity + fill.quantity
                    position.avg_price = total_cost / total_quantity
                    position.quantity = total_quantity
                    position.side = PositionSide.LONG
                else:  # SHORT position
                    # Reduce short position
                    if fill.quantity >= position.quantity:
                        # Close short and potentially open long
                        remaining = fill.quantity - position.quantity
                        if remaining > 0:
                            position.side = PositionSide.LONG
                            position.quantity = remaining
                            position.avg_price = fill.price
                        else:
                            position.side = PositionSide.FLAT
                            position.quantity = Decimal('0')
                    else:
                        position.quantity -= fill.quantity
            
            else:  # SELL
                if position.side == PositionSide.SHORT or position.side == PositionSide.FLAT:
                    # Increase short position
                    total_cost = (position.quantity * position.avg_price) + (fill.quantity * fill.price)
                    total_quantity = position.quantity + fill.quantity
                    position.avg_price = total_cost / total_quantity
                    position.quantity = total_quantity
                    position.side = PositionSide.SHORT
                else:  # LONG position
                    # Reduce long position
                    if fill.quantity >= position.quantity:
                        # Close long and potentially open short
                        remaining = fill.quantity - position.quantity
                        if remaining > 0:
                            position.side = PositionSide.SHORT
                            position.quantity = remaining
                            position.avg_price = fill.price
                        else:
                            position.side = PositionSide.FLAT
                            position.quantity = Decimal('0')
                    else:
                        position.quantity -= fill.quantity
    
    def _update_cash_balance(self, fill: Fill) -> None:
        """Update cash balance based on fill."""
        if fill.side == OrderSide.BUY:
            # Reduce cash for purchase
            cost = (fill.quantity * fill.price) + (fill.commission.amount if fill.commission else Decimal('0'))
            self.cash_balance = Money(self.cash_balance.amount - cost, self.cash_balance.currency)
        else:  # SELL
            # Increase cash from sale
            proceeds = (fill.quantity * fill.price) - (fill.commission.amount if fill.commission else Decimal('0'))
            self.cash_balance = Money(self.cash_balance.amount + proceeds, self.cash_balance.currency)
    
    async def submit_order(self, order: Order) -> str:
        """
        Submit an order for execution.
        
        Args:
            order: Order to submit
            
        Returns:
            Order ID
        """
        order.validate()
        order.status = OrderStatus.SUBMITTED
        self.orders[order.order_id] = order
        
        logger.debug(f"Submitted order {order.order_id}: {order.side.value} {order.quantity} {order.instrument_id}")
        
        return order.order_id
    
    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel a pending order.
        
        Args:
            order_id: ID of order to cancel
            
        Returns:
            True if order was cancelled, False otherwise
        """
        if order_id in self.orders:
            order = self.orders[order_id]
            if order.status in [OrderStatus.PENDING, OrderStatus.SUBMITTED]:
                order.status = OrderStatus.CANCELLED
                logger.debug(f"Cancelled order {order_id}")
                return True
        
        return False
    
    def get_position(self, instrument_id: InstrumentId) -> Optional[Position]:
        """Get current position for an instrument."""
        return self.positions.get(str(instrument_id))
    
    def get_portfolio_value(self) -> Money:
        """Get current portfolio value."""
        return self.portfolio_value
    
    def get_cash_balance(self) -> Money:
        """Get current cash balance."""
        return self.cash_balance
    
    async def _calculate_results(self, strategy: 'Strategy', config: BacktestConfig) -> BacktestResults:
        """Calculate comprehensive backtest results."""
        if not self.equity_curve:
            raise ValueError("No equity curve data available")
        
        # Convert equity curve to pandas for analysis
        df = pd.DataFrame(self.equity_curve, columns=['timestamp', 'equity'])
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)
        
        # Convert Decimal to float for pandas operations
        df['equity'] = df['equity'].astype(float)
        
        # Calculate returns
        df['returns'] = df['equity'].pct_change().fillna(0)
        df['cumulative_returns'] = (1 + df['returns']).cumprod()
        
        # Calculate drawdown
        df['peak'] = df['equity'].expanding().max()
        df['drawdown'] = (df['equity'] - df['peak']) / df['peak']
        
        # Basic metrics
        initial_capital = float(config.initial_capital.amount)
        final_capital = df['equity'].iloc[-1]
        total_return = final_capital / initial_capital
        
        # Time-based calculations
        total_days = (config.end_date - config.start_date).days
        years = total_days / 365.25
        
        # Annualized return
        annualized_return = (total_return ** (1 / years)) - 1 if years > 0 else 0
        
        # Volatility (annualized)
        daily_vol = df['returns'].std()
        annualized_vol = daily_vol * np.sqrt(252)  # 252 trading days per year
        
        # Sharpe ratio
        risk_free_daily = float(config.risk_free_rate) / 252
        excess_returns = df['returns'] - risk_free_daily
        sharpe_ratio = excess_returns.mean() / excess_returns.std() * np.sqrt(252) if excess_returns.std() > 0 else 0
        
        # Sortino ratio (downside deviation)
        downside_returns = excess_returns[excess_returns < 0]
        downside_std = downside_returns.std() if len(downside_returns) > 0 else excess_returns.std()
        sortino_ratio = excess_returns.mean() / downside_std * np.sqrt(252) if downside_std > 0 else 0
        
        # Drawdown metrics
        max_drawdown = abs(df['drawdown'].min())
        max_dd_duration = self._calculate_max_drawdown_duration(df)
        
        # Calmar ratio
        calmar_ratio = float(annualized_return) / float(max_drawdown) if max_drawdown > 0 else 0
        
        # Trade statistics
        trade_stats = self._calculate_trade_statistics()
        
        return BacktestResults(
            strategy_id=strategy.strategy_id,
            config=config,
            start_date=config.start_date,
            end_date=config.end_date,
            initial_capital=config.initial_capital,
            final_capital=Money(Decimal(str(final_capital)), config.initial_capital.currency),
            total_return=Decimal(str(total_return)),
            annualized_return=Decimal(str(annualized_return)),
            volatility=Decimal(str(annualized_vol)),
            sharpe_ratio=Decimal(str(sharpe_ratio)),
            sortino_ratio=Decimal(str(sortino_ratio)),
            max_drawdown=Decimal(str(max_drawdown)),
            max_drawdown_duration=max_dd_duration,
            calmar_ratio=Decimal(str(calmar_ratio)),
            win_rate=trade_stats['win_rate'],
            profit_factor=trade_stats['profit_factor'],
            total_trades=trade_stats['total_trades'],
            winning_trades=trade_stats['winning_trades'],
            losing_trades=trade_stats['losing_trades'],
            avg_trade_duration=trade_stats['avg_duration'],
            avg_winning_trade=trade_stats['avg_winning_trade'],
            avg_losing_trade=trade_stats['avg_losing_trade'],
            largest_winning_trade=trade_stats['largest_winning_trade'],
            largest_losing_trade=trade_stats['largest_losing_trade'],
            total_commission=trade_stats['total_commission'],
            total_slippage=trade_stats['total_slippage'],
            positions=list(self.positions.values()),
            trades=self.fills,
            equity_curve=self.equity_curve
        )
    
    def _calculate_max_drawdown_duration(self, df: pd.DataFrame) -> timedelta:
        """Calculate maximum drawdown duration."""
        in_drawdown = df['drawdown'] < 0
        drawdown_periods = []
        
        start = None
        for i, is_dd in enumerate(in_drawdown):
            if is_dd and start is None:
                start = i
            elif not is_dd and start is not None:
                drawdown_periods.append(i - start)
                start = None
        
        if start is not None:  # Still in drawdown at end
            drawdown_periods.append(len(df) - start)
        
        max_duration_periods = max(drawdown_periods) if drawdown_periods else 0
        
        # Convert periods to timedelta (assuming daily data)
        return timedelta(days=max_duration_periods)
    
    def _calculate_trade_statistics(self) -> Dict[str, Any]:
        """Calculate detailed trade statistics."""
        if not self.fills:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': Decimal('0'),
                'profit_factor': Decimal('0'),
                'avg_duration': timedelta(0),
                'avg_winning_trade': Money(Decimal('0'), 'USD'),
                'avg_losing_trade': Money(Decimal('0'), 'USD'),
                'largest_winning_trade': Money(Decimal('0'), 'USD'),
                'largest_losing_trade': Money(Decimal('0'), 'USD'),
                'total_commission': Money(Decimal('0'), 'USD'),
                'total_slippage': Money(Decimal('0'), 'USD')
            }
        
        # Group fills by instrument to calculate P&L per trade
        trades_pnl = []
        total_commission = Decimal('0')
        
        for fill in self.fills:
            if fill.commission:
                total_commission += fill.commission.amount
        
        # For simplicity, treat each fill as a separate trade
        # In a real implementation, you'd match buy/sell pairs
        winning_trades = 0
        losing_trades = 0
        winning_amounts = []
        losing_amounts = []
        
        # This is a simplified calculation
        # Real implementation would track round-trip trades
        for i in range(1, len(self.fills)):
            prev_fill = self.fills[i-1]
            curr_fill = self.fills[i]
            
            if prev_fill.side != curr_fill.side:  # Opposite sides = trade completion
                if prev_fill.side == OrderSide.BUY:
                    pnl = (curr_fill.price - prev_fill.price) * min(prev_fill.quantity, curr_fill.quantity)
                else:
                    pnl = (prev_fill.price - curr_fill.price) * min(prev_fill.quantity, curr_fill.quantity)
                
                if pnl > 0:
                    winning_trades += 1
                    winning_amounts.append(pnl)
                else:
                    losing_trades += 1
                    losing_amounts.append(abs(pnl))
        
        total_trades = winning_trades + losing_trades
        win_rate = Decimal(str(winning_trades / total_trades)) if total_trades > 0 else Decimal('0')
        
        avg_winning = sum(winning_amounts) / len(winning_amounts) if winning_amounts else 0
        avg_losing = sum(losing_amounts) / len(losing_amounts) if losing_amounts else 0
        
        profit_factor = Decimal(str(avg_winning / avg_losing)) if avg_losing > 0 else Decimal('0')
        
        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'avg_duration': timedelta(hours=1),  # Simplified
            'avg_winning_trade': Money(Decimal(str(avg_winning)), 'USD'),
            'avg_losing_trade': Money(Decimal(str(avg_losing)), 'USD'),
            'largest_winning_trade': Money(Decimal(str(max(winning_amounts) if winning_amounts else 0)), 'USD'),
            'largest_losing_trade': Money(Decimal(str(max(losing_amounts) if losing_amounts else 0)), 'USD'),
            'total_commission': Money(total_commission, 'USD'),
            'total_slippage': Money(Decimal('0'), 'USD')  # Would need to track separately
        }