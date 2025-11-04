"""
Base strategy interface for backtesting and live trading.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime
from decimal import Decimal

from ..data.models import OHLCVData
from .models import BacktestConfig, MarketState, Order


class Strategy(ABC):
    """
    Abstract base class for trading strategies.
    
    All trading strategies must inherit from this class and implement
    the required methods for backtesting and live trading.
    """
    
    def __init__(self, strategy_id: str, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the strategy.
        
        Args:
            strategy_id: Unique identifier for the strategy
            config: Strategy-specific configuration parameters
        """
        self.strategy_id = strategy_id
        self.config = config or {}
        self.is_initialized = False
        self.backtest_engine: Optional['BacktestEngine'] = None
        
    async def initialize(self, backtest_engine: 'BacktestEngine', backtest_config: BacktestConfig) -> None:
        """
        Initialize the strategy with the backtesting engine.
        
        Args:
            backtest_engine: The backtesting engine instance
            backtest_config: Backtest configuration
        """
        self.backtest_engine = backtest_engine
        self.is_initialized = True
        await self.on_initialize(backtest_config)
    
    @abstractmethod
    async def on_initialize(self, config: BacktestConfig) -> None:
        """
        Called when the strategy is initialized.
        
        Override this method to perform strategy-specific initialization,
        such as setting up indicators, loading parameters, etc.
        
        Args:
            config: Backtest configuration
        """
        pass
    
    @abstractmethod
    async def on_market_data(self, data: OHLCVData, market_state: MarketState) -> None:
        """
        Called when new market data is received.
        
        This is the main strategy logic where trading decisions are made.
        
        Args:
            data: OHLCV market data
            market_state: Current market state with bid/ask prices
        """
        pass
    
    async def on_order_filled(self, order: Order) -> None:
        """
        Called when an order is filled.
        
        Override this method to handle order fill events,
        such as updating position tracking or risk management.
        
        Args:
            order: The filled order
        """
        pass
    
    async def on_order_rejected(self, order: Order, reason: str) -> None:
        """
        Called when an order is rejected.
        
        Override this method to handle order rejection events.
        
        Args:
            order: The rejected order
            reason: Rejection reason
        """
        pass
    
    async def submit_market_order(
        self,
        instrument_id: str,
        venue: str,
        side: str,
        quantity: float,
        strategy_id: Optional[str] = None
    ) -> str:
        """
        Submit a market order.
        
        Args:
            instrument_id: Instrument to trade
            venue: Trading venue
            side: Order side ('buy' or 'sell')
            quantity: Order quantity
            strategy_id: Optional strategy identifier
            
        Returns:
            Order ID
        """
        if not self.backtest_engine:
            raise RuntimeError("Strategy not initialized with backtest engine")
        
        from nautilus_trader.model.identifiers import InstrumentId, Venue
        from .models import Order, OrderSide, OrderType
        from decimal import Decimal
        import uuid
        
        order = Order(
            order_id=str(uuid.uuid4()),
            instrument_id=InstrumentId.from_str(instrument_id),
            venue=Venue(venue),
            side=OrderSide.BUY if side.lower() == 'buy' else OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=Decimal(str(quantity)),
            strategy_id=strategy_id or self.strategy_id
        )
        
        return await self.backtest_engine.submit_order(order)
    
    async def submit_limit_order(
        self,
        instrument_id: str,
        venue: str,
        side: str,
        quantity: float,
        price: float,
        strategy_id: Optional[str] = None
    ) -> str:
        """
        Submit a limit order.
        
        Args:
            instrument_id: Instrument to trade
            venue: Trading venue
            side: Order side ('buy' or 'sell')
            quantity: Order quantity
            price: Limit price
            strategy_id: Optional strategy identifier
            
        Returns:
            Order ID
        """
        if not self.backtest_engine:
            raise RuntimeError("Strategy not initialized with backtest engine")
        
        from nautilus_trader.model.identifiers import InstrumentId, Venue
        from .models import Order, OrderSide, OrderType
        from decimal import Decimal
        import uuid
        
        order = Order(
            order_id=str(uuid.uuid4()),
            instrument_id=InstrumentId.from_str(instrument_id),
            venue=Venue(venue),
            side=OrderSide.BUY if side.lower() == 'buy' else OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=Decimal(str(quantity)),
            price=Decimal(str(price)),
            strategy_id=strategy_id or self.strategy_id
        )
        
        return await self.backtest_engine.submit_order(order)
    
    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.
        
        Args:
            order_id: ID of order to cancel
            
        Returns:
            True if order was cancelled, False otherwise
        """
        if not self.backtest_engine:
            raise RuntimeError("Strategy not initialized with backtest engine")
        
        return await self.backtest_engine.cancel_order(order_id)
    
    def get_position(self, instrument_id: str):
        """
        Get current position for an instrument.
        
        Args:
            instrument_id: Instrument identifier
            
        Returns:
            Position object or None
        """
        if not self.backtest_engine:
            raise RuntimeError("Strategy not initialized with backtest engine")
        
        from nautilus_trader.model.identifiers import InstrumentId
        return self.backtest_engine.get_position(InstrumentId.from_str(instrument_id))
    
    def get_portfolio_value(self):
        """Get current portfolio value."""
        if not self.backtest_engine:
            raise RuntimeError("Strategy not initialized with backtest engine")
        
        return self.backtest_engine.get_portfolio_value()
    
    def get_cash_balance(self):
        """Get current cash balance."""
        if not self.backtest_engine:
            raise RuntimeError("Strategy not initialized with backtest engine")
        
        return self.backtest_engine.get_cash_balance()
    
    def log_info(self, message: str) -> None:
        """Log an info message."""
        import logging
        logger = logging.getLogger(f"strategy.{self.strategy_id}")
        logger.info(message)
    
    def log_warning(self, message: str) -> None:
        """Log a warning message."""
        import logging
        logger = logging.getLogger(f"strategy.{self.strategy_id}")
        logger.warning(message)
    
    def log_error(self, message: str) -> None:
        """Log an error message."""
        import logging
        logger = logging.getLogger(f"strategy.{self.strategy_id}")
        logger.error(message)


class SimpleMovingAverageStrategy(Strategy):
    """
    Example strategy implementing a simple moving average crossover.
    
    This strategy buys when the short MA crosses above the long MA
    and sells when the short MA crosses below the long MA.
    """
    
    def __init__(self, strategy_id: str = "sma_crossover", config: Optional[Dict[str, Any]] = None):
        default_config = {
            "short_window": 10,
            "long_window": 30,
            "position_size": 0.1  # 10% of portfolio per trade
        }
        
        if config:
            default_config.update(config)
        
        super().__init__(strategy_id, default_config)
        
        # Strategy state
        self.prices = []
        self.short_ma = None
        self.long_ma = None
        self.last_signal = None
        self.position_instrument = None
    
    async def on_initialize(self, config: BacktestConfig) -> None:
        """Initialize the strategy."""
        self.log_info(f"Initializing SMA strategy with windows: {self.config['short_window']}, {self.config['long_window']}")
        self.prices = []
        self.short_ma = None
        self.long_ma = None
        self.last_signal = None
    
    async def on_market_data(self, data: OHLCVData, market_state: MarketState) -> None:
        """Process new market data and make trading decisions."""
        # Store price
        self.prices.append(float(data.close_price))
        
        # Keep only the data we need
        max_window = max(self.config['short_window'], self.config['long_window'])
        if len(self.prices) > max_window * 2:
            self.prices = self.prices[-max_window * 2:]
        
        # Calculate moving averages
        if len(self.prices) >= self.config['long_window']:
            self.short_ma = sum(self.prices[-self.config['short_window']:]) / self.config['short_window']
            self.long_ma = sum(self.prices[-self.config['long_window']:]) / self.config['long_window']
            
            # Generate signals
            current_signal = None
            if self.short_ma > self.long_ma:
                current_signal = 'buy'
            elif self.short_ma < self.long_ma:
                current_signal = 'sell'
            
            # Execute trades on signal changes
            if current_signal != self.last_signal and current_signal is not None:
                await self._execute_signal(current_signal, data, market_state)
                self.last_signal = current_signal
    
    async def _execute_signal(self, signal: str, data: OHLCVData, market_state: MarketState) -> None:
        """Execute trading signal."""
        instrument_str = str(data.instrument_id)
        venue_str = str(data.venue)
        
        # Get current position
        position = self.get_position(instrument_str)
        portfolio_value = self.get_portfolio_value()
        
        # Calculate position size
        position_value = portfolio_value.amount * Decimal(str(self.config['position_size']))
        quantity = position_value / market_state.mid_price
        
        if signal == 'buy':
            # Close short position if any, then go long
            if position and position.side.value == 'short':
                await self.submit_market_order(
                    instrument_str, venue_str, 'buy', float(position.quantity)
                )
                self.log_info(f"Closed short position: {position.quantity}")
            
            # Open long position
            await self.submit_market_order(
                instrument_str, venue_str, 'buy', float(quantity)
            )
            self.log_info(f"Opened long position: {quantity} at {market_state.mid_price}")
            
        elif signal == 'sell':
            # Close long position if any, then go short
            if position and position.side.value == 'long':
                await self.submit_market_order(
                    instrument_str, venue_str, 'sell', float(position.quantity)
                )
                self.log_info(f"Closed long position: {position.quantity}")
            
            # Open short position (simplified - in reality would need margin)
            await self.submit_market_order(
                instrument_str, venue_str, 'sell', float(quantity)
            )
            self.log_info(f"Opened short position: {quantity} at {market_state.mid_price}")


class BuyAndHoldStrategy(Strategy):
    """
    Simple buy and hold strategy for benchmarking.
    
    Buys the instrument at the start and holds until the end.
    """
    
    def __init__(self, strategy_id: str = "buy_and_hold", config: Optional[Dict[str, Any]] = None):
        default_config = {
            "allocation": 0.95  # 95% of portfolio
        }
        
        if config:
            default_config.update(config)
        
        super().__init__(strategy_id, default_config)
        self.has_bought = False
    
    async def on_initialize(self, config: BacktestConfig) -> None:
        """Initialize the strategy."""
        self.log_info("Initializing Buy and Hold strategy")
        self.has_bought = False
    
    async def on_market_data(self, data: OHLCVData, market_state: MarketState) -> None:
        """Buy once at the beginning."""
        self.log_info(f"BuyAndHold received market data: {data.timestamp} price={market_state.mid_price}")
        
        if not self.has_bought:
            instrument_str = str(data.instrument_id)
            venue_str = str(data.venue)
            
            # Calculate quantity to buy
            portfolio_value = self.get_portfolio_value()
            allocation_value = portfolio_value.amount * Decimal(str(self.config['allocation']))
            quantity = allocation_value / market_state.mid_price
            
            self.log_info(f"Submitting buy order: {quantity} {instrument_str} at {market_state.mid_price}")
            
            # Submit buy order
            order_id = await self.submit_market_order(
                instrument_str, venue_str, 'buy', float(quantity)
            )
            
            self.log_info(f"Bought {quantity} {instrument_str} at {market_state.mid_price}, order_id: {order_id}")
            self.has_bought = True