"""
Delta-Neutral Cross-Venue Strategy

This strategy maintains market-neutral exposure by simultaneously holding:
- Long positions on spot markets (Binance)
- Short positions on perpetual markets (dYdX)

The strategy profits from:
1. Funding rate arbitrage (collecting funding payments)
2. Volatility trading (maintaining neutral delta)
3. Cross-venue price discrepancies

Key Features:
- Real-time delta monitoring and rebalancing
- Funding rate optimization
- Multi-venue position synchronization
- Risk-adjusted position sizing
"""

import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Set, Any

from ..backtesting.strategy import Strategy
from ..backtesting.models import BacktestConfig, MarketState
from ..data.models import OHLCVData
from ..models.core import Order, Position, Instrument
from ..models.perpetuals import FundingRate
from nautilus_trader.model.enums import OrderSide, OrderType, TimeInForce, PositionSide
from nautilus_trader.model.objects import Price, Quantity, Money
from nautilus_trader.model.identifiers import InstrumentId

logger = logging.getLogger(__name__)


class DeltaNeutralConfig:
    """Configuration for delta-neutral strategy."""
    
    def __init__(
        self,
        target_instruments: List[str] = None,
        max_position_size_usd: Decimal = Decimal('10000'),
        max_total_exposure_usd: Decimal = Decimal('50000'),
        rebalance_threshold_pct: Decimal = Decimal('2'),  # 2% delta deviation triggers rebalance
        min_funding_rate_apy: Decimal = Decimal('5'),  # Minimum 5% APY from funding
        max_leverage: Decimal = Decimal('3'),
        spot_venue: str = "BINANCE",
        perp_venue: str = "DYDX",
        rebalance_cooldown_minutes: int = 15,
        emergency_exit_loss_pct: Decimal = Decimal('5'),  # Exit if loss exceeds 5%
    ):
        """
        Initialize delta-neutral strategy configuration.
        
        Args:
            target_instruments: List of instruments to trade (e.g., ['BTC', 'ETH'])
            max_position_size_usd: Maximum position size per instrument
            max_total_exposure_usd: Maximum total exposure across all positions
            rebalance_threshold_pct: Delta deviation percentage that triggers rebalance
            min_funding_rate_apy: Minimum funding rate APY to enter position
            max_leverage: Maximum leverage allowed
            spot_venue: Venue for spot trading
            perp_venue: Venue for perpetual trading
            rebalance_cooldown_minutes: Minimum time between rebalances
            emergency_exit_loss_pct: Loss percentage that triggers emergency exit
        """
        self.target_instruments = target_instruments or ['BTC', 'ETH']
        self.max_position_size_usd = max_position_size_usd
        self.max_total_exposure_usd = max_total_exposure_usd
        self.rebalance_threshold_pct = rebalance_threshold_pct
        self.min_funding_rate_apy = min_funding_rate_apy
        self.max_leverage = max_leverage
        self.spot_venue = spot_venue
        self.perp_venue = perp_venue
        self.rebalance_cooldown_minutes = rebalance_cooldown_minutes
        self.emergency_exit_loss_pct = emergency_exit_loss_pct
    
    def validate(self) -> None:
        """Validate configuration parameters."""
        if self.max_position_size_usd <= 0:
            raise ValueError("Max position size must be positive")
        if self.max_total_exposure_usd <= 0:
            raise ValueError("Max total exposure must be positive")
        if not (0 < self.rebalance_threshold_pct < 100):
            raise ValueError("Rebalance threshold must be between 0 and 100")
        if self.max_leverage <= 0:
            raise ValueError("Max leverage must be positive")


class DeltaNeutralStrategy(Strategy):
    """
    Delta-neutral strategy that maintains market-neutral exposure across venues.
    
    The strategy:
    1. Monitors funding rates on perpetual markets
    2. Opens positions when funding rates are attractive
    3. Maintains delta-neutral exposure by balancing spot and perp positions
    4. Rebalances when delta deviates beyond threshold
    5. Exits positions when funding rates become unfavorable
    """
    
    def __init__(
        self,
        strategy_id: str = "delta_neutral",
        config: Optional[DeltaNeutralConfig] = None
    ):
        """
        Initialize delta-neutral strategy.
        
        Args:
            strategy_id: Unique identifier for the strategy
            config: Strategy configuration
        """
        self.strategy_config = config or DeltaNeutralConfig()
        self.strategy_config.validate()
        
        super().__init__(strategy_id, self.strategy_config.__dict__)
        
        # Position tracking
        self.spot_positions: Dict[str, Position] = {}  # instrument -> spot position
        self.perp_positions: Dict[str, Position] = {}  # instrument -> perp position
        
        # Market data
        self.spot_prices: Dict[str, Decimal] = {}  # instrument -> current spot price
        self.perp_prices: Dict[str, Decimal] = {}  # instrument -> current perp price
        self.funding_rates: Dict[str, FundingRate] = {}  # instrument -> funding rate
        
        # Performance tracking
        self.total_funding_earned_usd = Decimal('0')
        self.total_rebalance_costs_usd = Decimal('0')
        self.position_history: List[Dict] = []
        self.last_rebalance_time: Dict[str, datetime] = {}
        
        # Delta tracking
        self.current_delta: Dict[str, Decimal] = {}  # instrument -> current delta
        self.target_delta: Dict[str, Decimal] = {}  # instrument -> target delta (should be 0)
        
        # Order tracking
        self.pending_orders: Dict[str, Dict] = {}  # order_id -> order info
        
        logger.info(f"Initialized DeltaNeutralStrategy with config: {self.strategy_config.__dict__}")
    
    async def on_initialize(self, backtest_config: BacktestConfig) -> None:
        """Initialize the strategy for backtesting."""
        self.log_info("Initializing Delta-Neutral Strategy")
        
        # Initialize target delta to zero for all instruments
        for instrument in self.strategy_config.target_instruments:
            self.target_delta[instrument] = Decimal('0')
            self.current_delta[instrument] = Decimal('0')
        
        self.log_info(f"Strategy initialized for instruments: {self.strategy_config.target_instruments}")
    
    async def on_market_data(self, data: OHLCVData, market_state: MarketState) -> None:
        """
        Process market data and make trading decisions.
        
        Args:
            data: OHLCV market data
            market_state: Current market state
        """
        # Update price cache
        await self._update_prices(data, market_state)
        
        # Update funding rates
        await self._update_funding_rates()
        
        # Calculate current portfolio delta
        await self._calculate_portfolio_delta()
        
        # Check for new opportunities
        await self._evaluate_new_opportunities()
        
        # Monitor existing positions
        await self._monitor_existing_positions()
        
        # Rebalance if needed
        await self._check_and_rebalance()
    
    async def _update_prices(self, data: OHLCVData, market_state: MarketState) -> None:
        """Update price cache from market data."""
        instrument_str = str(data.instrument_id)
        price = market_state.mid_price
        
        # Determine if this is spot or perp data
        if self.strategy_config.spot_venue in instrument_str.upper():
            # Extract instrument symbol
            for symbol in self.strategy_config.target_instruments:
                if symbol in instrument_str.upper():
                    self.spot_prices[symbol] = price
                    self.log_info(f"Updated {symbol} spot price: ${price}")
                    break
        
        elif self.strategy_config.perp_venue in instrument_str.upper():
            # Extract instrument symbol
            for symbol in self.strategy_config.target_instruments:
                if symbol in instrument_str.upper():
                    self.perp_prices[symbol] = price
                    self.log_info(f"Updated {symbol} perp price: ${price}")
                    break
    
    async def _update_funding_rates(self) -> None:
        """Update funding rates for perpetual markets."""
        # In a real implementation, this would fetch from dYdX adapter
        # For backtesting, we'll simulate funding rates
        for instrument in self.strategy_config.target_instruments:
            # Simulate funding rate (in real implementation, fetch from exchange)
            # Typical funding rates range from -0.1% to 0.1% per 8 hours
            simulated_rate = Decimal('0.0001')  # 0.01% per 8 hours = ~10% APY
            
            self.funding_rates[instrument] = FundingRate(
                instrument=None,  # Would be actual instrument object
                rate=simulated_rate,
                timestamp=datetime.now(),
                venue=self.strategy_config.perp_venue,
                next_funding_time=datetime.now() + timedelta(hours=8)
            )
    
    async def _calculate_portfolio_delta(self) -> None:
        """Calculate current portfolio delta for each instrument."""
        for instrument in self.strategy_config.target_instruments:
            spot_position = self.spot_positions.get(instrument)
            perp_position = self.perp_positions.get(instrument)
            
            spot_delta = Decimal('0')
            perp_delta = Decimal('0')
            
            if spot_position:
                # Spot long position has positive delta
                spot_delta = spot_position.quantity.as_decimal()
            
            if perp_position:
                # Perp short position has negative delta
                if perp_position.side == PositionSide.SHORT:
                    perp_delta = -perp_position.quantity.as_decimal()
                else:
                    perp_delta = perp_position.quantity.as_decimal()
            
            # Total delta = spot delta + perp delta
            self.current_delta[instrument] = spot_delta + perp_delta
            
            # Calculate delta as percentage of position size
            total_position_size = abs(spot_delta) + abs(perp_delta)
            if total_position_size > 0:
                delta_pct = abs(self.current_delta[instrument]) / total_position_size * Decimal('100')
                self.log_info(f"{instrument} delta: {self.current_delta[instrument]:.4f} ({delta_pct:.2f}%)")
    
    async def _evaluate_new_opportunities(self) -> None:
        """Evaluate new delta-neutral opportunities based on funding rates."""
        for instrument in self.strategy_config.target_instruments:
            # Skip if we already have a position
            if instrument in self.spot_positions or instrument in self.perp_positions:
                continue
            
            # Check if funding rate is attractive
            funding_rate = self.funding_rates.get(instrument)
            if not funding_rate:
                continue
            
            # Convert funding rate to annualized APY
            # Funding typically paid every 8 hours, so 3 times per day
            funding_apy = funding_rate.rate * Decimal('3') * Decimal('365') * Decimal('100')
            
            if funding_apy >= self.strategy_config.min_funding_rate_apy:
                self.log_info(f"Attractive funding rate for {instrument}: {funding_apy:.2f}% APY")
                await self._open_delta_neutral_position(instrument, funding_apy)
    
    async def _open_delta_neutral_position(self, instrument: str, funding_apy: Decimal) -> None:
        """
        Open a delta-neutral position for an instrument.
        
        Args:
            instrument: Instrument symbol
            funding_apy: Expected funding rate APY
        """
        # Calculate position size
        spot_price = self.spot_prices.get(instrument)
        perp_price = self.perp_prices.get(instrument)
        
        if not spot_price or not perp_price:
            self.log_warning(f"Missing price data for {instrument}")
            return
        
        # Use average price for position sizing
        avg_price = (spot_price + perp_price) / Decimal('2')
        
        # Calculate quantity based on max position size
        position_size_usd = min(
            self.strategy_config.max_position_size_usd,
            self.get_portfolio_value().amount * Decimal('0.2')  # Max 20% per position
        )
        
        quantity = position_size_usd / avg_price
        
        self.log_info(f"Opening delta-neutral position for {instrument}:")
        self.log_info(f"  Position size: ${position_size_usd:.2f}")
        self.log_info(f"  Quantity: {quantity:.6f}")
        self.log_info(f"  Expected funding APY: {funding_apy:.2f}%")
        
        try:
            # Submit orders to both venues simultaneously
            # 1. Buy spot on Binance
            spot_instrument_id = f"{instrument}USDT.{self.strategy_config.spot_venue}"
            spot_order_id = await self.submit_market_order(
                instrument_id=spot_instrument_id,
                venue=self.strategy_config.spot_venue,
                side='buy',
                quantity=float(quantity)
            )
            self.log_info(f"Submitted spot buy order: {spot_order_id}")
            
            # 2. Short perpetual on dYdX
            perp_instrument_id = f"{instrument}-USD.{self.strategy_config.perp_venue}"
            perp_order_id = await self.submit_market_order(
                instrument_id=perp_instrument_id,
                venue=self.strategy_config.perp_venue,
                side='sell',
                quantity=float(quantity)
            )
            self.log_info(f"Submitted perp short order: {perp_order_id}")
            
            # Track positions (will be updated by on_order_filled callback)
            # Store order IDs for tracking
            if not hasattr(self, 'pending_orders'):
                self.pending_orders = {}
            
            self.pending_orders[spot_order_id] = {
                'instrument': instrument,
                'type': 'spot',
                'side': 'buy',
                'quantity': quantity
            }
            self.pending_orders[perp_order_id] = {
                'instrument': instrument,
                'type': 'perp',
                'side': 'sell',
                'quantity': quantity
            }
            
            # Record in history
            self.position_history.append({
                'action': 'open',
                'instrument': instrument,
                'quantity': float(quantity),
                'spot_price': float(spot_price),
                'perp_price': float(perp_price),
                'funding_apy': float(funding_apy),
                'spot_order_id': spot_order_id,
                'perp_order_id': perp_order_id,
                'timestamp': datetime.now().isoformat()
            })
            
        except Exception as e:
            self.log_error(f"Failed to open delta-neutral position for {instrument}: {e}")
            # TODO: Implement rollback logic if one order succeeds but the other fails
    
    async def on_order_filled(self, order) -> None:
        """
        Called when an order is filled.
        
        Updates position tracking based on filled orders.
        
        Args:
            order: The filled order
        """
        # Check if this is one of our pending orders
        if not hasattr(self, 'pending_orders'):
            return
        
        order_id = str(order.order_id)
        if order_id not in self.pending_orders:
            return
        
        order_info = self.pending_orders[order_id]
        instrument = order_info['instrument']
        order_type = order_info['type']
        
        self.log_info(f"Order filled: {order_type} {order_info['side']} {order_info['quantity']} {instrument}")
        
        # Get the actual position from the backtest engine
        instrument_id_str = str(order.instrument_id)
        position = self.get_position(instrument_id_str)
        
        if position:
            if order_type == 'spot':
                self.spot_positions[instrument] = position
                self.log_info(f"Updated spot position for {instrument}: {position.quantity}")
            elif order_type == 'perp':
                self.perp_positions[instrument] = position
                self.log_info(f"Updated perp position for {instrument}: {position.quantity}")
        
        # Remove from pending orders
        del self.pending_orders[order_id]
        
        # Recalculate delta after position update
        await self._calculate_portfolio_delta()
    
    async def _monitor_existing_positions(self) -> None:
        """Monitor existing positions for exit signals."""
        for instrument in list(self.spot_positions.keys()):
            # Check funding rate
            funding_rate = self.funding_rates.get(instrument)
            if not funding_rate:
                continue
            
            funding_apy = funding_rate.rate * Decimal('3') * Decimal('365') * Decimal('100')
            
            # Exit if funding rate becomes unfavorable
            if funding_apy < self.strategy_config.min_funding_rate_apy / Decimal('2'):
                self.log_info(f"Funding rate for {instrument} no longer attractive: {funding_apy:.2f}% APY")
                await self._close_delta_neutral_position(instrument)
            
            # Check for emergency exit conditions
            await self._check_emergency_exit(instrument)
    
    async def _check_emergency_exit(self, instrument: str) -> None:
        """Check if emergency exit is needed for a position."""
        # Calculate current P&L
        spot_position = self.spot_positions.get(instrument)
        perp_position = self.perp_positions.get(instrument)
        
        if not spot_position or not perp_position:
            return
        
        # Get current prices
        spot_price = self.spot_prices.get(instrument, Decimal('0'))
        perp_price = self.perp_prices.get(instrument, Decimal('0'))
        
        if spot_price == 0 or perp_price == 0:
            return
        
        # Calculate unrealized P&L
        spot_pnl = (spot_price - spot_position.avg_price.as_decimal()) * spot_position.quantity.as_decimal()
        perp_pnl = (perp_position.avg_price.as_decimal() - perp_price) * perp_position.quantity.as_decimal()
        
        total_pnl = spot_pnl + perp_pnl
        position_value = spot_position.avg_price.as_decimal() * spot_position.quantity.as_decimal()
        
        if position_value > 0:
            pnl_pct = (total_pnl / position_value) * Decimal('100')
            
            if pnl_pct < -self.strategy_config.emergency_exit_loss_pct:
                self.log_warning(f"Emergency exit triggered for {instrument}: Loss {pnl_pct:.2f}%")
                await self._close_delta_neutral_position(instrument)
    
    async def _check_and_rebalance(self) -> None:
        """Check if rebalancing is needed and execute if necessary."""
        for instrument in self.strategy_config.target_instruments:
            # Skip if no position
            if instrument not in self.spot_positions and instrument not in self.perp_positions:
                continue
            
            # Check cooldown period
            last_rebalance = self.last_rebalance_time.get(instrument)
            if last_rebalance:
                time_since_rebalance = datetime.now() - last_rebalance
                if time_since_rebalance < timedelta(minutes=self.strategy_config.rebalance_cooldown_minutes):
                    continue
            
            # Calculate delta deviation
            current_delta = self.current_delta.get(instrument, Decimal('0'))
            target_delta = self.target_delta.get(instrument, Decimal('0'))
            
            # Get total position size
            spot_position = self.spot_positions.get(instrument)
            perp_position = self.perp_positions.get(instrument)
            
            if not spot_position or not perp_position:
                continue
            
            total_size = spot_position.quantity.as_decimal() + perp_position.quantity.as_decimal()
            
            if total_size > 0:
                delta_deviation_pct = abs(current_delta - target_delta) / total_size * Decimal('100')
                
                if delta_deviation_pct >= self.strategy_config.rebalance_threshold_pct:
                    self.log_info(f"Rebalancing {instrument}: Delta deviation {delta_deviation_pct:.2f}%")
                    await self._rebalance_position(instrument)
    
    async def _rebalance_position(self, instrument: str) -> None:
        """
        Rebalance a position to restore delta neutrality.
        
        Args:
            instrument: Instrument to rebalance
        """
        current_delta = self.current_delta.get(instrument, Decimal('0'))
        
        if current_delta == 0:
            return
        
        # Calculate rebalance amount (half the delta deviation)
        rebalance_amount = abs(current_delta) / Decimal('2')
        
        self.log_info(f"Rebalancing {instrument}:")
        self.log_info(f"  Current delta: {current_delta:.6f}")
        self.log_info(f"  Rebalance amount: {rebalance_amount:.6f}")
        
        try:
            if current_delta > 0:
                # Too much long exposure - need to reduce
                # Option 1: Sell some spot (preferred for lower cost)
                spot_instrument_id = f"{instrument}USDT.{self.strategy_config.spot_venue}"
                order_id = await self.submit_market_order(
                    instrument_id=spot_instrument_id,
                    venue=self.strategy_config.spot_venue,
                    side='sell',
                    quantity=float(rebalance_amount)
                )
                self.log_info(f"Rebalance: Sold {rebalance_amount} spot, order: {order_id}")
                
            elif current_delta < 0:
                # Too much short exposure - need to increase long
                # Option 1: Buy some spot (preferred for lower cost)
                spot_instrument_id = f"{instrument}USDT.{self.strategy_config.spot_venue}"
                order_id = await self.submit_market_order(
                    instrument_id=spot_instrument_id,
                    venue=self.strategy_config.spot_venue,
                    side='buy',
                    quantity=float(rebalance_amount)
                )
                self.log_info(f"Rebalance: Bought {rebalance_amount} spot, order: {order_id}")
            
            # Update last rebalance time
            self.last_rebalance_time[instrument] = datetime.now()
            
            # Estimate rebalance cost
            spot_price = self.spot_prices.get(instrument, Decimal('0'))
            rebalance_cost = rebalance_amount * spot_price * Decimal('0.001')  # 0.1% cost estimate
            self.total_rebalance_costs_usd += rebalance_cost
            
            # Record in history
            self.position_history.append({
                'action': 'rebalance',
                'instrument': instrument,
                'delta_before': float(current_delta),
                'rebalance_amount': float(rebalance_amount),
                'rebalance_cost': float(rebalance_cost),
                'timestamp': datetime.now().isoformat()
            })
            
        except Exception as e:
            self.log_error(f"Failed to rebalance position for {instrument}: {e}")
    

    
    async def _close_delta_neutral_position(self, instrument: str) -> None:
        """
        Close a delta-neutral position.
        
        Args:
            instrument: Instrument to close
        """
        self.log_info(f"Closing delta-neutral position for {instrument}")
        
        spot_position = self.spot_positions.get(instrument)
        perp_position = self.perp_positions.get(instrument)
        
        if not spot_position and not perp_position:
            self.log_warning(f"No positions found for {instrument}")
            return
        
        try:
            # Close spot position (sell on Binance)
            if spot_position:
                spot_instrument_id = str(spot_position.instrument.id)
                spot_order_id = await self.submit_market_order(
                    instrument_id=spot_instrument_id,
                    venue=self.strategy_config.spot_venue,
                    side='sell',
                    quantity=float(spot_position.quantity.as_decimal())
                )
                self.log_info(f"Closed spot position: {spot_order_id}")
            
            # Close perp position (cover short on dYdX)
            if perp_position:
                perp_instrument_id = str(perp_position.instrument.id)
                # To close a short, we buy
                perp_order_id = await self.submit_market_order(
                    instrument_id=perp_instrument_id,
                    venue=self.strategy_config.perp_venue,
                    side='buy',
                    quantity=float(perp_position.quantity.as_decimal())
                )
                self.log_info(f"Closed perp position: {perp_order_id}")
            
            # Calculate final P&L
            spot_pnl = Decimal('0')
            perp_pnl = Decimal('0')
            
            if spot_position:
                spot_price = self.spot_prices.get(instrument, Decimal('0'))
                spot_pnl = (spot_price - spot_position.avg_price.as_decimal()) * spot_position.quantity.as_decimal()
            
            if perp_position:
                perp_price = self.perp_prices.get(instrument, Decimal('0'))
                # For short position, profit when price goes down
                perp_pnl = (perp_position.avg_price.as_decimal() - perp_price) * perp_position.quantity.as_decimal()
            
            total_pnl = spot_pnl + perp_pnl
            
            # Estimate funding earned
            funding_rate = self.funding_rates.get(instrument)
            estimated_funding = Decimal('0')
            if funding_rate and spot_position:
                # Simplified: assume position held for some time
                position_value = spot_position.avg_price.as_decimal() * spot_position.quantity.as_decimal()
                estimated_funding = position_value * funding_rate.rate * Decimal('10')  # Rough estimate
                self.total_funding_earned_usd += estimated_funding
            
            self.log_info(f"Position closed - Spot P&L: ${spot_pnl:.2f}, Perp P&L: ${perp_pnl:.2f}, Funding: ${estimated_funding:.2f}")
            
            # Remove from active positions
            self.spot_positions.pop(instrument, None)
            self.perp_positions.pop(instrument, None)
            self.current_delta.pop(instrument, None)
            
            # Record in history
            self.position_history.append({
                'action': 'close',
                'instrument': instrument,
                'spot_pnl': float(spot_pnl),
                'perp_pnl': float(perp_pnl),
                'total_pnl': float(total_pnl),
                'funding_earned': float(estimated_funding),
                'timestamp': datetime.now().isoformat()
            })
            
        except Exception as e:
            self.log_error(f"Failed to close delta-neutral position for {instrument}: {e}")
    

    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get strategy performance summary."""
        return {
            'total_funding_earned_usd': float(self.total_funding_earned_usd),
            'total_rebalance_costs_usd': float(self.total_rebalance_costs_usd),
            'net_profit_usd': float(self.total_funding_earned_usd - self.total_rebalance_costs_usd),
            'active_positions': len(self.spot_positions),
            'total_trades': len(self.position_history),
            'current_delta': {k: float(v) for k, v in self.current_delta.items()}
        }
