"""
Delta-Neutral Strategy - Proper Nautilus Implementation

This strategy uses Nautilus Trader framework properly:
- Inherits from nautilus_trader.trading.strategy.Strategy
- Uses Nautilus event handlers
- Works in backtest, paper, and live modes automatically
"""

from decimal import Decimal
from typing import Dict, Optional

from nautilus_trader.trading.strategy import Strategy
from nautilus_trader.model.data import QuoteTick, Bar
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.orders import MarketOrder
from nautilus_trader.config import StrategyConfig
from nautilus_trader.core.message import Event


class DeltaNeutralConfig(StrategyConfig):
    """Configuration for delta-neutral strategy."""
    
    # Instruments
    spot_instrument: str = "BTCUSDT.BINANCE"  # Binance spot
    perp_instrument: str = "BTC-USD.DYDX_V4"  # dYdX perpetual
    
    # Position sizing
    max_position_size_usd: float = 5000.0
    max_total_exposure_usd: float = 20000.0
    
    # Delta management
    rebalance_threshold_pct: float = 2.0  # Rebalance at 2% deviation
    rebalance_cooldown_minutes: int = 20
    
    # Funding requirements
    min_funding_rate_apy: float = 6.0  # Minimum 6% APY
    
    # Risk controls
    max_leverage: float = 3.0
    emergency_exit_loss_pct: float = 4.0


class DeltaNeutralStrategy(Strategy):
    """
    Delta-neutral strategy using Nautilus Trader framework.
    
    Maintains market-neutral exposure by:
    1. Buying spot on Binance
    2. Shorting perpetual on dYdX
    3. Collecting funding rate payments
    4. Rebalancing when delta deviates
    """
    
    def __init__(self, config: DeltaNeutralConfig):
        """
        Initialize strategy.
        
        Args:
            config: Strategy configuration
        """
        super().__init__(config)
        
        # Configuration
        self.spot_instrument_id = InstrumentId.from_str(config.spot_instrument)
        self.perp_instrument_id = InstrumentId.from_str(config.perp_instrument)
        
        # State
        self.spot_price: Optional[Decimal] = None
        self.perp_price: Optional[Decimal] = None
        self.funding_rate: Optional[Decimal] = None
        
        # Position tracking
        self.target_delta = Decimal('0')  # Always zero for delta-neutral
        
    def on_start(self):
        """Called when strategy starts."""
        self.log.info(f"Starting {self.__class__.__name__}")
        self.log.info(f"Spot instrument: {self.spot_instrument_id}")
        self.log.info(f"Perp instrument: {self.perp_instrument_id}")
        
        # Subscribe to market data
        self.subscribe_quote_ticks(self.spot_instrument_id)
        self.subscribe_quote_ticks(self.perp_instrument_id)
        
        # Subscribe to bars for funding rate calculation
        from nautilus_trader.model.data import BarType, BarSpecification
        from nautilus_trader.model.enums import BarAggregation, PriceType, AggregationSource
        
        bar_spec = BarSpecification(
            step=1,
            aggregation=BarAggregation.MINUTE,
            price_type=PriceType.LAST
        )
        bar_type = BarType(
            instrument_id=self.perp_instrument_id,
            bar_spec=bar_spec,
            aggregation_source=AggregationSource.EXTERNAL
        )
        self.subscribe_bars(bar_type)
    
    def on_stop(self):
        """Called when strategy stops."""
        self.log.info(f"Stopping {self.__class__.__name__}")
        
        # Close all positions
        self.close_all_positions(self.spot_instrument_id)
        self.close_all_positions(self.perp_instrument_id)
    
    def on_quote_tick(self, tick: QuoteTick):
        """
        Handle quote tick updates.
        
        Args:
            tick: Quote tick with bid/ask prices
        """
        # Update prices
        mid_price = (tick.bid_price.as_decimal() + tick.ask_price.as_decimal()) / Decimal('2')
        
        if tick.instrument_id == self.spot_instrument_id:
            self.spot_price = mid_price
            self.log.debug(f"Spot price updated: ${mid_price}")
        
        elif tick.instrument_id == self.perp_instrument_id:
            self.perp_price = mid_price
            self.log.debug(f"Perp price updated: ${mid_price}")
        
        # Check if we should take action
        if self.spot_price and self.perp_price:
            self._evaluate_opportunity()
    
    def on_bar(self, bar: Bar):
        """
        Handle bar updates (for funding rate calculation).
        
        Args:
            bar: Price bar
        """
        if bar.bar_type.instrument_id == self.perp_instrument_id:
            # In real implementation, would calculate funding rate from bar data
            # For now, we'll get it from the adapter
            self._update_funding_rate()
    
    def on_event(self, event: Event):
        """
        Handle custom events (like funding rate updates).
        
        Args:
            event: Custom event
        """
        # Handle funding rate events from dYdX adapter
        if hasattr(event, 'funding_rate'):
            self.funding_rate = Decimal(str(event.funding_rate))
            self.log.info(f"Funding rate updated: {self.funding_rate}")
    
    def _evaluate_opportunity(self):
        """Evaluate if we should open/close/rebalance positions."""
        # Get current positions
        spot_position = self.portfolio.position(self.spot_instrument_id)
        perp_position = self.portfolio.position(self.perp_instrument_id)
        
        # Calculate current delta
        spot_delta = Decimal('0')
        perp_delta = Decimal('0')
        
        if spot_position and not spot_position.is_flat:
            spot_delta = Decimal(str(spot_position.quantity))
        
        if perp_position and not perp_position.is_flat:
            # Perp short has negative delta
            perp_delta = -Decimal(str(perp_position.quantity))
        
        current_delta = spot_delta + perp_delta
        
        # Check if we have positions
        has_positions = (spot_position and not spot_position.is_flat) or \
                       (perp_position and not perp_position.is_flat)
        
        if not has_positions:
            # No positions - check if we should open
            self._check_entry_signal()
        else:
            # Have positions - check if we should rebalance or exit
            self._check_rebalance(current_delta, spot_delta, perp_delta)
            self._check_exit_signal()
    
    def _check_entry_signal(self):
        """Check if we should enter a delta-neutral position."""
        if not self.funding_rate:
            return
        
        # Convert funding rate to APY (funding paid 3x per day)
        funding_apy = self.funding_rate * Decimal('3') * Decimal('365') * Decimal('100')
        
        # Only enter if funding rate is attractive
        if funding_apy >= Decimal(str(self.config.min_funding_rate_apy)):
            self.log.info(f"Entry signal: Funding APY {funding_apy:.2f}% >= {self.config.min_funding_rate_apy}%")
            self._open_delta_neutral_position()
        else:
            self.log.debug(f"Funding APY {funding_apy:.2f}% below threshold")
    
    def _open_delta_neutral_position(self):
        """Open delta-neutral position (buy spot + short perp)."""
        if not self.spot_price or not self.perp_price:
            return
        
        # Calculate position size
        avg_price = (self.spot_price + self.perp_price) / Decimal('2')
        position_size_usd = Decimal(str(self.config.max_position_size_usd))
        quantity = position_size_usd / avg_price
        
        self.log.info(f"Opening delta-neutral position:")
        self.log.info(f"  Size: ${position_size_usd:.2f}")
        self.log.info(f"  Quantity: {quantity:.6f}")
        
        # Submit orders
        # 1. Buy spot
        spot_order = self.order_factory.market(
            instrument_id=self.spot_instrument_id,
            order_side=OrderSide.BUY,
            quantity=self.instrument_provider.get_quantity(
                self.spot_instrument_id,
                float(quantity)
            ),
            time_in_force=TimeInForce.GTC
        )
        self.submit_order(spot_order)
        
        # 2. Short perp
        perp_order = self.order_factory.market(
            instrument_id=self.perp_instrument_id,
            order_side=OrderSide.SELL,
            quantity=self.instrument_provider.get_quantity(
                self.perp_instrument_id,
                float(quantity)
            ),
            time_in_force=TimeInForce.GTC
        )
        self.submit_order(perp_order)
    
    def _check_rebalance(self, current_delta: Decimal, spot_delta: Decimal, perp_delta: Decimal):
        """Check if we need to rebalance to restore delta neutrality."""
        if current_delta == 0:
            return
        
        # Calculate delta as percentage of position size
        total_size = abs(spot_delta) + abs(perp_delta)
        if total_size == 0:
            return
        
        delta_pct = abs(current_delta) / total_size * Decimal('100')
        
        # Check if deviation exceeds threshold
        if delta_pct >= Decimal(str(self.config.rebalance_threshold_pct)):
            self.log.info(f"Rebalancing: Delta deviation {delta_pct:.2f}%")
            self._rebalance_position(current_delta)
    
    def _rebalance_position(self, current_delta: Decimal):
        """Rebalance position to restore delta neutrality."""
        # Rebalance by adjusting spot position (simpler than perp)
        rebalance_amount = abs(current_delta) / Decimal('2')
        
        if current_delta > 0:
            # Too much long - sell some spot
            order = self.order_factory.market(
                instrument_id=self.spot_instrument_id,
                order_side=OrderSide.SELL,
                quantity=self.instrument_provider.get_quantity(
                    self.spot_instrument_id,
                    float(rebalance_amount)
                ),
                time_in_force=TimeInForce.GTC
            )
            self.submit_order(order)
            self.log.info(f"Rebalance: Selling {rebalance_amount:.6f} spot")
        
        elif current_delta < 0:
            # Too much short - buy some spot
            order = self.order_factory.market(
                instrument_id=self.spot_instrument_id,
                order_side=OrderSide.BUY,
                quantity=self.instrument_provider.get_quantity(
                    self.spot_instrument_id,
                    float(rebalance_amount)
                ),
                time_in_force=TimeInForce.GTC
            )
            self.submit_order(order)
            self.log.info(f"Rebalance: Buying {rebalance_amount:.6f} spot")
    
    def _check_exit_signal(self):
        """Check if we should exit positions."""
        if not self.funding_rate:
            return
        
        # Exit if funding rate becomes unfavorable
        funding_apy = self.funding_rate * Decimal('3') * Decimal('365') * Decimal('100')
        
        if funding_apy < Decimal(str(self.config.min_funding_rate_apy)) / Decimal('2'):
            self.log.info(f"Exit signal: Funding APY {funding_apy:.2f}% too low")
            self._close_all_positions()
    
    def _close_all_positions(self):
        """Close all positions."""
        self.log.info("Closing all positions")
        self.close_all_positions(self.spot_instrument_id)
        self.close_all_positions(self.perp_instrument_id)
    
    def _update_funding_rate(self):
        """Update funding rate from adapter."""
        # This would be called by the adapter when funding rate updates
        # For now, it's a placeholder
        pass
    
    def on_reset(self):
        """Reset strategy state."""
        self.spot_price = None
        self.perp_price = None
        self.funding_rate