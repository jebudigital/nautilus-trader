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
from nautilus_trader.model.data import QuoteTick, Bar, FundingRateUpdate
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
        
        # Order tracking for blocking behavior
        self.pending_entry_orders = set()  # Track orders we're waiting for
        self.is_entering_position = False  # Flag to block evaluation during entry
        self.entry_start_time = 0  # Track when we started entering
        self.entry_timeout_seconds = 60  # Timeout after 60 seconds
        
    def on_start(self):
        """Called when strategy starts."""
        print("\n" + "="*60)
        print("🚀 STRATEGY ON_START CALLED")
        print("="*60)
        self.log.info("="*60)
        self.log.info(f"🚀 STARTING DELTA NEUTRAL STRATEGY")
        self.log.info("="*60)
        self.log.info(f"Spot: {self.spot_instrument_id}")
        self.log.info(f"Perp: {self.perp_instrument_id}")
        self.log.info(f"Max Position: ${self.config.max_position_size_usd}")
        self.log.info(f"Rebalance Threshold: {self.config.rebalance_threshold_pct}%")
        
        # Check existing positions
        self.log.info("\n📊 Checking existing positions...")
        spot_positions = self.cache.positions_open(venue=self.spot_instrument_id.venue)
        perp_positions = self.cache.positions_open(venue=self.perp_instrument_id.venue)
        
        self.log.info(f"Binance positions: {len(list(spot_positions))}")
        self.log.info(f"dYdX positions: {len(list(perp_positions))}")
        
        for pos in self.cache.positions_open():
            self.log.info(f"  Existing: {pos.side} {pos.quantity} {pos.instrument_id}")
        
        # Subscribe to market data
        self.log.info("\n📡 Subscribing to market data...")
        self.subscribe_quote_ticks(self.spot_instrument_id)
        self.subscribe_quote_ticks(self.perp_instrument_id)
        self.log.info(f"  ✅ Subscribed to {self.spot_instrument_id}")
        self.log.info(f"  ✅ Subscribed to {self.perp_instrument_id}")
        
        # Subscribe to funding rates (proper Nautilus way)
        self.subscribe_funding_rates(self.perp_instrument_id)
        self.log.info(f"Subscribed to funding rates for {self.perp_instrument_id}")
        
        # Subscribe to bars for additional analysis
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
    
    def on_funding_rate(self, funding_rate: FundingRateUpdate):
        """
        Handle funding rate updates.
        
        This is the proper Nautilus handler for FundingRateUpdate.
        Called when subscribed via subscribe_funding_rates().
        
        Args:
            funding_rate: FundingRateUpdate object
        """
        if funding_rate.instrument_id == self.perp_instrument_id:
            self.funding_rate = funding_rate.rate
            
            # Calculate APY for logging (funding paid 3x per day)
            funding_apy = self.funding_rate * Decimal('3') * Decimal('365') * Decimal('100')
            self.log.info(f"Funding rate updated: {self.funding_rate:.6f} ({funding_apy:.2f}% APY)")
    
    def on_data(self, data):
        """
        Handle generic data updates (fallback for custom data types).
        
        Args:
            data: Data object
        """
        # Fallback handler for any custom data types
        # FundingRateUpdate should go to on_funding_rate instead
        self.log.debug(f"Received data: {type(data).__name__}")
    
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
            # Only log every 20th price update
            if not hasattr(self, '_spot_count'):
                self._spot_count = 0
            self._spot_count += 1
            if self._spot_count % 20 == 0:
                print(f"📊 Binance BTC: ${mid_price:.2f}")
        
        elif tick.instrument_id == self.perp_instrument_id:
            self.perp_price = mid_price
            if not hasattr(self, '_perp_count'):
                self._perp_count = 0
            self._perp_count += 1
            if self._perp_count % 20 == 0:
                print(f"📊 dYdX BTC: ${mid_price:.2f}")
        
        # Check if we should take action (sample every 10th quote to reduce spam)
        if self.spot_price and self.perp_price:
            if not hasattr(self, '_eval_count'):
                self._eval_count = 0
            self._eval_count += 1
            
            if self._eval_count % 10 == 0:
                print(f"\n💡 Evaluating (check #{self._eval_count})...")
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
    
    def on_order_accepted(self, event):
        """Handle order accepted event."""
        print(f"  ✅ Order accepted: {event.client_order_id}")
        self.log.info(f"Order accepted: {event}")
        
        # Track this order if it's part of entry
        if event.client_order_id in self.pending_entry_orders:
            print(f"     ⏳ Waiting for fill...")
    
    def on_order_rejected(self, event):
        """Handle order rejected event."""
        print(f"  ❌ Order rejected: {event.client_order_id} - {event.reason}")
        self.log.error(f"Order rejected: {event}")
        
        # Remove from pending and unblock if this was an entry order
        if event.client_order_id in self.pending_entry_orders:
            self.pending_entry_orders.discard(event.client_order_id)
            if not self.pending_entry_orders:
                self.is_entering_position = False
                print(f"     🔓 Entry unblocked (order rejected)")
    
    def on_order_filled(self, event):
        """Handle order filled event."""
        print(f"  💰 Order filled: {event.client_order_id} - {event.last_qty} @ {event.last_px}")
        self.log.info(f"Order filled: {event}")
        
        # Remove from pending orders
        if event.client_order_id in self.pending_entry_orders:
            self.pending_entry_orders.discard(event.client_order_id)
            print(f"     ✅ Entry order filled ({len(self.pending_entry_orders)} remaining)")
            
            # Unblock evaluation when all entry orders are filled
            if not self.pending_entry_orders:
                self.is_entering_position = False
                print(f"     🔓 All entry orders filled - evaluation unblocked!")
    
    def _evaluate_opportunity(self):
        """Evaluate if we should open/close/rebalance positions."""
        # Block evaluation if we're waiting for entry orders to fill
        if self.is_entering_position:
            # Check for timeout
            current_time = self.clock.timestamp_ns()
            elapsed_seconds = (current_time - self.entry_start_time) / 1_000_000_000
            
            if elapsed_seconds > self.entry_timeout_seconds:
                print(f"  ⏰ Entry timeout after {elapsed_seconds:.0f}s - unblocking")
                self.log.warning(f"Entry timeout - {len(self.pending_entry_orders)} orders still pending")
                self.is_entering_position = False
                self.pending_entry_orders.clear()
            else:
                print(f"  🔒 Blocked - waiting for {len(self.pending_entry_orders)} entry orders to fill ({elapsed_seconds:.0f}s elapsed)")
                return
        
        # Get current positions for instruments
        spot_positions = self.cache.positions_open(instrument_id=self.spot_instrument_id)
        perp_positions = self.cache.positions_open(instrument_id=self.perp_instrument_id)
        
        spot_position = spot_positions[0] if spot_positions else None
        perp_position = perp_positions[0] if perp_positions else None
        
        # Calculate current delta
        spot_delta = Decimal('0')
        perp_delta = Decimal('0')
        
        if spot_position and not spot_position.is_closed:
            spot_delta = Decimal(str(spot_position.quantity))
            print(f"  📈 Binance: LONG {spot_delta} BTC")
        
        if perp_position and not perp_position.is_closed:
            # Perp short has negative delta
            perp_delta = -Decimal(str(perp_position.quantity))
            print(f"  📉 dYdX: SHORT {abs(perp_delta)} BTC")
        
        current_delta = spot_delta + perp_delta
        print(f"  ⚖️  Net Delta: {current_delta:.8f} BTC")
        
        # Check if we have positions
        has_positions = (spot_position and not spot_position.is_closed) or \
                       (perp_position and not perp_position.is_closed)
        
        if not has_positions:
            print("  ℹ️  No positions - checking entry signal")
            self._check_entry_signal()
        else:
            print("  ✅ Have positions - checking rebalance")
            self._check_rebalance(current_delta, spot_delta, perp_delta)
            self._check_exit_signal()
    
    def _check_entry_signal(self):
        """Check if we should enter a delta-neutral position."""
        # Check if we have all required data
        if not self.spot_price:
            print(f"  ⚠️  Missing spot price")
            return
        
        if not self.perp_price:
            print(f"  ⚠️  Missing perp price")
            return
            
        if not self.funding_rate:
            print(f"  ⚠️  Missing funding rate (waiting for data...)")
            return
        
        # Convert funding rate to APY (funding paid 3x per day)
        funding_apy = self.funding_rate * Decimal('3') * Decimal('365') * Decimal('100')
        
        # Log entry checks
        print(f"  💰 Funding APY: {funding_apy:.2f}% (need {self.config.min_funding_rate_apy}%)")
        
        # Only enter if funding rate is attractive
        if funding_apy >= Decimal(str(self.config.min_funding_rate_apy)):
            print(f"  🚀 ENTRY SIGNAL! Funding APY {funding_apy:.2f}% >= {self.config.min_funding_rate_apy}%")
            self._open_delta_neutral_position()
        else:
            print(f"  ⏸️  Waiting - funding too low")
    
    def _open_delta_neutral_position(self):
        """Open delta-neutral position (buy spot + short perp)."""
        # Check if we have any open orders (don't submit more if orders are pending)
        open_orders = list(self.cache.orders_open())
        if open_orders:
            print(f"  ⏳ Waiting for {len(open_orders)} pending orders to complete")
            return
        
        # Check if we already have pending orders to avoid spam
        if not hasattr(self, '_last_order_attempt_time'):
            self._last_order_attempt_time = 0
        
        current_time = self.clock.timestamp_ns()
        time_since_last_attempt = (current_time - self._last_order_attempt_time) / 1_000_000_000  # Convert to seconds
        
        if time_since_last_attempt < 30:  # Wait at least 30 seconds between attempts
            return
        
        self._last_order_attempt_time = current_time
        
        if not self.spot_price or not self.perp_price:
            print("  ⚠️  Cannot open position: missing price data")
            self.log.warning("Cannot open position: missing price data")
            return
        
        # Verify we have recent quotes for both instruments
        spot_quote = self.cache.quote_tick(self.spot_instrument_id)
        perp_quote = self.cache.quote_tick(self.perp_instrument_id)
        
        if not spot_quote or not perp_quote:
            print(f"  ⚠️  Cannot open position: missing quotes (spot={spot_quote is not None}, perp={perp_quote is not None})")
            self.log.warning(f"Cannot open position: missing quotes (spot={spot_quote is not None}, perp={perp_quote is not None})")
            return
        
        # Calculate position size
        avg_price = (self.spot_price + self.perp_price) / Decimal('2')
        position_size_usd = Decimal(str(self.config.max_position_size_usd))
        quantity = position_size_usd / avg_price
        
        print(f"  💼 Opening delta-neutral position:")
        print(f"     Size: ${position_size_usd:.2f}")
        print(f"     Quantity: {quantity:.6f} BTC")
        self.log.info(f"Opening delta-neutral position:")
        self.log.info(f"  Size: ${position_size_usd:.2f}")
        self.log.info(f"  Quantity: {quantity:.6f}")
        
        # Get instruments from cache
        spot_instrument = self.cache.instrument(self.spot_instrument_id)
        perp_instrument = self.cache.instrument(self.perp_instrument_id)
        
        if not spot_instrument or not perp_instrument:
            print(f"  ❌ Instruments not found in cache!")
            print(f"     Spot instrument: {spot_instrument}")
            print(f"     Perp instrument: {perp_instrument}")
            print(f"     Available instruments: {list(self.cache.instruments())}")
            self.log.error("Instruments not found in cache")
            return
        
        # Convert to proper Quantity with instrument precision
        spot_quantity = spot_instrument.make_qty(quantity)
        perp_quantity = perp_instrument.make_qty(quantity)
        
        print(f"     Submitting orders...")
        print(f"     Spot: BUY {spot_quantity} {self.spot_instrument_id}")
        print(f"     Perp: SELL {perp_quantity} {self.perp_instrument_id}")
        
        # Set blocking flag BEFORE submitting orders
        self.is_entering_position = True
        self.entry_start_time = self.clock.timestamp_ns()
        print(f"     🔒 Blocking evaluation until orders fill...")
        
        # Submit orders
        # 1. Buy spot
        spot_order = self.order_factory.market(
            instrument_id=self.spot_instrument_id,
            order_side=OrderSide.BUY,
            quantity=spot_quantity,
            time_in_force=TimeInForce.GTC
        )
        self.log.info(f"Submitting spot order: {spot_order}")
        print(f"     🔵 Calling submit_order for spot...")
        self.submit_order(spot_order)
        self.pending_entry_orders.add(spot_order.client_order_id)
        print(f"     ✅ Spot order submitted: {spot_order.client_order_id}")
        print(f"     📊 Order state: {spot_order.status}")
        
        # 2. Short perp
        perp_order = self.order_factory.market(
            instrument_id=self.perp_instrument_id,
            order_side=OrderSide.SELL,
            quantity=perp_quantity,
            time_in_force=TimeInForce.GTC
        )
        self.log.info(f"Submitting perp order: {perp_order}")
        self.submit_order(perp_order)
        self.pending_entry_orders.add(perp_order.client_order_id)
        print(f"     ✅ Perp order submitted: {perp_order.client_order_id}")
        print(f"     ⏳ Waiting for {len(self.pending_entry_orders)} orders to fill before next evaluation...")
    
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
        # Get instrument from cache
        spot_instrument = self.cache.instrument(self.spot_instrument_id)
        if not spot_instrument:
            self.log.error("Spot instrument not found in cache")
            return
        
        # Rebalance by adjusting spot position (simpler than perp)
        rebalance_amount = abs(current_delta) / Decimal('2')
        rebalance_qty = spot_instrument.make_qty(rebalance_amount)
        
        if current_delta > 0:
            # Too much long - sell some spot
            order = self.order_factory.market(
                instrument_id=self.spot_instrument_id,
                order_side=OrderSide.SELL,
                quantity=rebalance_qty,
                time_in_force=TimeInForce.GTC
            )
            self.submit_order(order)
            self.log.info(f"Rebalance: Selling {rebalance_amount:.6f} spot")
        
        elif current_delta < 0:
            # Too much short - buy some spot
            order = self.order_factory.market(
                instrument_id=self.spot_instrument_id,
                order_side=OrderSide.BUY,
                quantity=rebalance_qty,
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