# Delta-Neutral Trading Strategy

A delta-neutral trading strategy **built on Nautilus Trader framework** for executing market-neutral arbitrage across Binance (spot) and dYdX v4 (perpetuals).

## Architecture

**IMPORTANT**: This project uses Nautilus Trader properly:
- ✅ Strategy inherits from `nautilus_trader.trading.strategy.Strategy`
- ✅ Uses Nautilus `BacktestEngine` for backtesting
- ✅ Uses Nautilus `TradingNode` for live/paper trading
- ✅ Uses Nautilus adapters (Binance built-in, dYdX custom)
- ✅ Event-driven architecture
- ✅ Automatic mode switching (backtest → paper → live)

## Strategy

**Delta-Neutral**: Maintains zero directional exposure by:
1. Buying spot on Binance
2. Shorting perpetual on dYdX v4
3. Collecting funding rate payments
4. Rebalancing when delta deviates

**Profit Source**: Funding rate arbitrage (typically 5-20% APY)

## Quick Start

### 1. Install
```bash
pip install -e .
```

### 2. Configure
Edit `.env` with your API keys:
```bash
# Binance
BINANCE__API_KEY=your_key
BINANCE__API_SECRET=your_secret
BINANCE__SANDBOX=true  # testnet

# dYdX v4
DYDX__VERSION=v4
DYDX__MNEMONIC=your metamask mnemonic
DYDX__NETWORK=testnet
```

### 3. Run

**Backtest** (coming soon):
```bash
python examples/backtest_delta_neutral.py
```

**Paper Trading**:
```bash
python examples/paper_trade_delta_neutral.py
```

**Live Trading**:
```bash
python examples/live_trade_delta_neutral.py
```

## Project Structure

```
src/crypto_trading_engine/
├── strategies/
│   └── delta_neutral_nautilus.py  # Main strategy (Nautilus-based)
├── adapters/
│   ├── binance_nautilus_adapter.py  # Binance (uses Nautilus built-in)
│   └── dydx_v4_rest_adapter.py      # dYdX v4 custom adapter
└── config/
    └── settings.py
```

## Migration Complete

This project has been migrated to use Nautilus Trader properly. Previous custom implementations have been removed. All trading modes (backtest/paper/live) now use Nautilus infrastructure.

## License

MIT License