"""
Hyperliquid + 0x Delta Neutral Strategy (Arbitrum L2)

Strategy:
- Long spot on 0x (Arbitrum DEX aggregator)
- Short perpetual on Hyperliquid
- Maintain delta neutral exposure
- Earn funding rates on Hyperliquid shorts
"""

from decimal import Decimal
from typing import Optional

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.trading.strategy import Strategy


class HyperliquidZeroXConfig(StrategyConfig):
    """Configuration for Hyperliquid + 0x delta neutral strategy"""
    
    spot_instrument: str  # e.g., "WETHUSDC.ZEROX"
    perp_instrument: str  # e.g., "ETH-PERP.HYPERLIQUID"
    max_position_size_usd: float = 1000.0
    rebalance_threshold_pct: float = 5.0
    min_funding_rate_apy: float = 5.0
    max_leverage: float = 3.0
    emergency_exit_loss_pct: float = 10.0


class HyperliquidZeroXStrategy(Strategy):
    """
    Delta neutral strategy using Hyperliquid perpetuals and 0x spot on Arbitrum.
    
    The strategy:
    1. Monitors funding rates on Hyperliquid
    2. When funding is positive (longs pay shorts):
       - Buy spot on 0x (Arbitrum)
       - Short perp on Hyperliquid
    3. Maintains delta neutral position
    4. Rebalances when delta drifts beyond threshold
    5. Exits on emergency conditions
    """
    
    def __init__(self, config: HyperliquidZeroXConfig):
        super().__init__(config)
        
        # Configuration
        self.spot_instrument_id = InstrumentId.from_str(config.spot_instrument)
        self.perp_instrument_id = InstrumentId.from_str(config.perp_instrument)
        self.max_position_size_usd = config.max_position_size_usd
        self.rebalance_threshold_pct = config.rebalance_threshold_pct
        self.min_funding_rate_apy = config.min_funding_rate_apy
        self.max_leverage = config.max_leverage
        self.emergency_exit_loss_pct = config.emergency_exit_loss_pct
        
        # State
        self.spot_instrument: Optional[Instrument] = None
        self.perp_instrument: Optional[Instrument] = None
        self.current_funding_rate: float = 0.0
        self.entry_price: Optional[float] = None
    
    def on_start(self):
        """Called when strategy starts"""
        self.log.info(f"Starting {self.__class__.__name__}")
        self.log.info(f"Spot: {self.spot_instrument_id}")
        self.log.info(f"Perp: {self.perp_instrument_id}")
        
        # Load instruments
        self.spot_instrument = self.cache.instrument(self.spot_instrument_id)
        self.perp_instrument = self.cache.instrument(self.perp_instrument_id)
        
        if not self.spot_instrument:
            self.log.error(f"Spot instrument not found: {self.spot_instrument_id}")
            return
        
        if not self.perp_instrument:
            self.log.error(f"Perp instrument not found: {self.perp_instrument_id}")
            return
        
        # Subscribe to data
        self.subscribe_quote_ticks(self.spot_instrument_id)
        self.subscribe_quote_ticks(self.perp_instrument_id)
        
        self.log.info("Strategy started")
    
    def on_stop(self):
        """Called when strategy stops"""
        self.log.info("Stopping strategy")
        
        # Close all positions
        self._close_all_positions()
        
        self.log.info("Strategy stopped")
    
    def on_quote_tick(self, tick: QuoteTick):
        """Handle quote tick"""
        # Check if we should enter position
        if not self._has_position():
            self._check_entry_signal()
        else:
            # Check if we should rebalance
            self._check_rebalance()
            
            # Check emergency exit
            self._check_emergency_exit()
    
    def _has_position(self) -> bool:
        """Check if we have open positions"""
        spot_position = self.cache.position_for_order(self.spot_instrument_id)
        perp_position = self.cache.position_for_order(self.perp_instrument_id)
        
        return (spot_position is not None and spot_position.is_open) or \
               (perp_position is not None and perp_position.is_open)
    
    def _check_entry_signal(self):
        """Check if we should enter position"""
        # TODO: Get funding rate from Hyperliquid
        # For now, use placeholder
        funding_rate_apy = self.current_funding_rate * 365 * 3  # 8h rate * 3 * 365
        
        if funding_rate_apy < self.min_funding_rate_apy:
            return
        
        # Get current prices
        spot_tick = self.cache.quote_tick(self.spot_instrument_id)
        perp_tick = self.cache.quote_tick(self.perp_instrument_id)
        
        if not spot_tick or not perp_tick:
            return
        
        spot_price = float(spot_tick.ask_price)
        perp_price = float(perp_tick.bid_price)
        
        # Calculate position size
        position_size_usd = min(
            self.max_position_size_usd,
            self._get_available_capital() * 0.5,  # Use 50% of capital
        )
        
        spot_quantity = position_size_usd / spot_price
        perp_quantity = position_size_usd / perp_price
        
        self.log.info(f"Entering position:")
        self.log.info(f"  Funding APY: {funding_rate_apy:.2f}%")
        self.log.info(f"  Spot: BUY {spot_quantity:.4f} @ ${spot_price:.2f}")
        self.log.info(f"  Perp: SELL {perp_quantity:.4f} @ ${perp_price:.2f}")
        
        # Place orders
        self._place_spot_order(OrderSide.BUY, spot_quantity)
        self._place_perp_order(OrderSide.SELL, perp_quantity)
        
        self.entry_price = (spot_price + perp_price) / 2
    
    def _check_rebalance(self):
        """Check if we need to rebalance"""
        spot_position = self.cache.position_for_order(self.spot_instrument_id)
        perp_position = self.cache.position_for_order(self.perp_instrument_id)
        
        if not spot_position or not perp_position:
            return
        
        # Calculate delta
        spot_delta = float(spot_position.quantity) if spot_position.is_long else -float(spot_position.quantity)
        perp_delta = float(perp_position.quantity) if perp_position.is_long else -float(perp_position.quantity)
        
        net_delta = spot_delta + perp_delta
        total_position = abs(spot_delta) + abs(perp_delta)
        
        if total_position == 0:
            return
        
        delta_pct = abs(net_delta / total_position) * 100
        
        if delta_pct > self.rebalance_threshold_pct:
            self.log.info(f"Rebalancing: delta {delta_pct:.2f}% > {self.rebalance_threshold_pct}%")
            self._rebalance_positions()
    
    def _check_emergency_exit(self):
        """Check if we should emergency exit"""
        if not self.entry_price:
            return
        
        # Get current prices
        spot_tick = self.cache.quote_tick(self.spot_instrument_id)
        perp_tick = self.cache.quote_tick(self.perp_instrument_id)
        
        if not spot_tick or not perp_tick:
            return
        
        current_price = (float(spot_tick.bid_price) + float(perp_tick.ask_price)) / 2
        
        # Calculate P&L
        pnl_pct = ((current_price - self.entry_price) / self.entry_price) * 100
        
        if abs(pnl_pct) > self.emergency_exit_loss_pct:
            self.log.warning(f"Emergency exit: P&L {pnl_pct:.2f}% > {self.emergency_exit_loss_pct}%")
            self._close_all_positions()
    
    def _place_spot_order(self, side: OrderSide, quantity: float):
        """Place spot order on 0x"""
        order = self.order_factory.market(
            instrument_id=self.spot_instrument_id,
            order_side=side,
            quantity=self.spot_instrument.make_qty(quantity),
        )
        
        self.submit_order(order)
    
    def _place_perp_order(self, side: OrderSide, quantity: float):
        """Place perp order on Hyperliquid"""
        order = self.order_factory.market(
            instrument_id=self.perp_instrument_id,
            order_side=side,
            quantity=self.perp_instrument.make_qty(quantity),
        )
        
        self.submit_order(order)
    
    def _rebalance_positions(self):
        """Rebalance positions to maintain delta neutral"""
        # TODO: Implement rebalancing logic
        self.log.info("Rebalancing positions...")
    
    def _close_all_positions(self):
        """Close all open positions"""
        self.log.info("Closing all positions...")
        
        # Close spot position
        spot_position = self.cache.position_for_order(self.spot_instrument_id)
        if spot_position and spot_position.is_open:
            self.close_position(spot_position)
        
        # Close perp position
        perp_position = self.cache.position_for_order(self.perp_instrument_id)
        if perp_position and perp_position.is_open:
            self.close_position(perp_position)
        
        self.entry_price = None
    
    def _get_available_capital(self) -> float:
        """Get available capital"""
        # TODO: Get actual account balance
        return 10000.0  # Placeholder
