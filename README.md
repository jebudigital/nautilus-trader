# Crypto Trading Engine with NautilusTrader

Professional algorithmic trading system for cryptocurrency markets using NautilusTrader framework.

## Features

- ✅ **Delta Neutral Strategy** - Earn funding rates while staying market neutral
- ✅ **Backtesting** - Test strategies on historical data
- ✅ **Paper Trading** - Practice with testnet funds
- ✅ **Live Trading** - Trade on mainnet with real money
- ✅ **Multi-Exchange** - Binance (spot) + dYdX V4 (perpetuals)
- ✅ **Real-time Dashboard** - Monitor positions, P&L, and orders

## Quick Start

### 1. Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env
```

### 2. Configure Credentials

Edit `.env`:

```bash
# Binance
BINANCE__API_KEY=your_api_key
BINANCE__API_SECRET=your_api_secret
BINANCE__SANDBOX=false  # false for mainnet, true for testnet

# dYdX V4 (only needs private key, no API keys!)
DYDX__NETWORK=mainnet  # or testnet
DYDX__PRIVATE_KEY=0xyour_private_key
DYDX__WALLET_ADDRESS=dydx1your_address
```

### 3. Run

**Backtesting:**
```bash
python3 examples/backtest_delta_neutral.py
```

**Live Trading:**
```bash
python3 examples/live_trading_final.py
```

## Project Structure

```
crypto-trading-engine/
├── src/crypto_trading_engine/
│   ├── strategies/
│   │   └── delta_neutral_nautilus.py    # Delta neutral strategy
│   └── adapters/
│       ├── dydx_v4_nautilus_adapter.py  # dYdX V4 adapter
│       └── binance_adapter.py           # Binance adapter
├── examples/
│   ├── backtest_delta_neutral.py        # Backtesting script
│   └── live_trading_final.py            # Live trading script
├── scripts/
│   ├── check_positions.py               # Check open positions
│   ├── check_balances.py                # Check account balances
│   └── test_dydx_connection.py          # Test dYdX connection
├── docs/
│   └── live_trading_setup.md            # Detailed setup guide
├── .env                                  # Configuration (create from .env.example)
└── README.md                             # This file
```

## Strategy: Delta Neutral

The delta neutral strategy:

1. **Long BTC spot** on Binance
2. **Short BTC perpetual** on dYdX
3. **Net delta ≈ 0** (market neutral)
4. **Earn funding rates** on the short position

### How It Works

```
Market goes UP:
  Spot: +$100 profit
  Perp: -$100 loss
  Net: $0 (neutral)
  
Market goes DOWN:
  Spot: -$100 loss
  Perp: +$100 profit
  Net: $0 (neutral)
  
Funding Rate: +0.01% every 8 hours
  = ~11% APY (passive income!)
```

### Configuration

Edit strategy parameters in `examples/live_trading_final.py`:

```python
strategy_config = DeltaNeutralConfig(
    spot_instrument="BTCUSDT.BINANCE",
    perp_instrument="BTC-USD.DYDX_V4",
    max_position_size_usd=30.0,        # Position size
    max_total_exposure_usd=120.0,      # Total capital
    rebalance_threshold_pct=5.0,       # Rebalance at 5% drift
    min_funding_rate_apy=5.0,          # Min 5% APY to enter
    max_leverage=2.0,                  # Max 2x leverage
    emergency_exit_loss_pct=10.0,      # Stop loss at 10%
)
```

## Monitoring

The live trading script includes a real-time dashboard showing:

- ⏱️ Runtime and start time
- 💰 Portfolio balance and equity
- 📊 Open positions with P&L
- 📝 Recent orders
- ⚖️ Delta exposure status

Updates every 5 seconds automatically.

## Safety Features

1. **Position Limits** - Maximum position sizes enforced
2. **Stop Loss** - Automatic exit on large losses
3. **Rebalancing** - Maintains delta neutral exposure
4. **Funding Rate Check** - Only enters when profitable
5. **Paper Trading** - Test on testnet first

## Getting Help

### Check Balances
```bash
python3 scripts/check_balances.py
```

### Check Positions
```bash
python3 scripts/check_positions.py
```

### Test Connection
```bash
python3 scripts/test_dydx_connection.py
```

## Important Notes

### dYdX V4 Authentication

dYdX V4 is **fully decentralized** and uses **wallet signatures only**:

- ✅ Only need: Private key
- ❌ Don't need: API key, API secret, passphrase

This is different from dYdX V3 and other centralized exchanges.

### Security

- 🔒 Never share your private keys
- 🔒 Use separate wallets for trading
- 🔒 Start with small amounts
- 🔒 Test on testnet first
- 🔒 Keep `.env` in `.gitignore`

### Risks

- ⚠️ You can lose money
- ⚠️ Market volatility can cause losses
- ⚠️ Funding rates can turn negative
- ⚠️ Technical issues can occur
- ⚠️ Always monitor your positions

## Troubleshooting

### "Invalid API Key" (Binance)
- Verify API key is for mainnet, not testnet
- Check IP restrictions in Binance settings
- Ensure trading permissions are enabled

### "Account not found" (dYdX)
- Deposit funds to activate account
- Verify you're on correct network (mainnet/testnet)
- Check wallet address is correct

### "Insufficient Balance"
- Check balances on both exchanges
- Ensure you have enough for fees
- Reduce position sizes

## Performance

Typical performance (varies by market conditions):

- **Funding Rate APY:** 5-15%
- **Risk:** Low (market neutral)
- **Capital Required:** $100+ recommended
- **Time Commitment:** Automated (check daily)

## Roadmap

- [ ] Web UI dashboard
- [ ] Multiple trading pairs
- [ ] Advanced risk management
- [ ] Performance analytics
- [ ] Telegram notifications
- [ ] Cloud deployment guide

## License

MIT License - See LICENSE file

## Disclaimer

This software is for educational purposes. Trading cryptocurrencies involves risk. Only trade with money you can afford to lose. The authors are not responsible for any financial losses.

---

**Ready to start?** Run `python3 examples/live_trading_final.py`

**Questions?** Check `docs/live_trading_setup.md` for detailed setup instructions.
