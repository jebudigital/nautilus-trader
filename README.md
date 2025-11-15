# Hyperliquid + 0x Delta Neutral Trading Bot

**Automated delta neutral trading on Arbitrum L2 using NautilusTrader**

## Overview

This bot implements a delta neutral strategy that earns funding rates while maintaining zero directional exposure:

- **Long spot** via 0x Protocol (aggregates Uniswap, SushiSwap, Curve, etc.)
- **Short perpetuals** on Hyperliquid
- **Network:** Arbitrum L2 (100x cheaper gas than Ethereum)
- **Returns:** 5-15% APY from funding rates

## Why This Stack?

### Arbitrum L2
- **100x cheaper gas:** $0.10 vs $10 on Ethereum
- **Fast finality:** 2 seconds
- **Full EVM compatibility**

### 0x Protocol
- **DEX aggregator:** Best prices across Uniswap, SushiSwap, Curve, Balancer
- **No protocol fees:** Only gas costs
- **Optimized routing:** Automatic best execution

### Hyperliquid
- **Decentralized perpetuals** on Arbitrum
- **No API keys:** Wallet-based authentication
- **Maker rebates:** -0.002% (you get paid to make orders!)
- **Up to 50x leverage**

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
nano .env
```

Add your configuration:
```bash
# Free Arbitrum RPC
ARBITRUM__RPC_URL=https://arb1.arbitrum.io/rpc

# Your wallet (same for both Hyperliquid and 0x)
ARBITRUM__PRIVATE_KEY=0x...
ARBITRUM__WALLET_ADDRESS=0x...

# Hyperliquid settings
HYPERLIQUID__PRIVATE_KEY=0x...  # Same as above
HYPERLIQUID__WALLET_ADDRESS=0x...  # Same as above
HYPERLIQUID__TESTNET=true  # Start with testnet!

# Strategy parameters
STRATEGY__MAX_POSITION_SIZE_USD=1000.0
STRATEGY__MIN_FUNDING_RATE_APY=5.0
STRATEGY__REBALANCE_THRESHOLD_PCT=5.0
```

### 3. Get Free Arbitrum RPC

**Option 1: Public RPC (Free)**
```
https://arb1.arbitrum.io/rpc
```

**Option 2: Alchemy (Recommended - 300M compute units/month free)**
1. Sign up at https://www.alchemy.com/
2. Create app: Arbitrum One
3. Copy HTTPS endpoint

### 4. Fund Your Wallet

You need USDC on Arbitrum:

**Option A: Bridge from Ethereum**
- Use https://bridge.arbitrum.io/

**Option B: Buy on CEX and withdraw**
- Buy USDT/USDC on Binance/Coinbase
- Withdraw to Arbitrum network
- Swap USDT → USDC if needed (via 0x)

**Option C: Buy directly on Arbitrum**
- Use on-ramp services that support Arbitrum

### 5. Run

```bash
# Test connections
./quickstart.sh

# Run on testnet (recommended first!)
python examples/hyperliquid_zerox_live.py
```

## How It Works

### Strategy

1. **Monitor funding rates** on Hyperliquid
2. **When funding > 5% APY:**
   - Buy ETH on 0x (spot)
   - Short ETH on Hyperliquid (perp)
3. **Maintain delta neutral** (net exposure = 0)
4. **Earn funding rate** (5-15% APY)
5. **Rebalance** when delta drifts > 5%

### Example Trade

```
Entry:
  0x (Arbitrum):  BUY 1 ETH @ $2,000 (spot)
  Hyperliquid:    SELL 1 ETH @ $2,000 (perp)
  Net Delta:      0 ETH (neutral)
  Gas Cost:       ~$0.10

Market moves to $2,200:
  Spot P&L:       +$200 (long profit)
  Perp P&L:       -$200 (short loss)
  Net P&L:        $0 (neutral)

Funding Rate: +0.01% every 8 hours
  = ~11% APY (passive income!)
```

## Costs

| Item | Cost |
|------|------|
| Gas (0x swap) | $0.10 |
| Gas (Hyperliquid order) | $0.05 |
| 0x Protocol fee | $0 |
| Hyperliquid maker fee | -0.002% (rebate!) |
| **Total per cycle** | **~$0.15** |

**Compare to Ethereum:** $10-50 per cycle (100x more expensive!)

## Project Structure

```
crypto-trading-engine/
├── src/crypto_trading_engine/
│   ├── adapters/
│   │   ├── hyperliquid_adapter.py    # Hyperliquid (WebSocket)
│   │   └── zerox_adapter.py          # 0x Protocol (Arbitrum)
│   └── strategies/
│       └── hyperliquid_zerox_delta_neutral.py
├── examples/
│   ├── hyperliquid_zerox_live.py     # Live trading
│   └── hyperliquid_zerox_backtest.py # Backtesting
├── .env.example                       # Config template
├── requirements.txt                   # Dependencies
└── README.md                          # This file
```

## Features

### ✅ Implemented

- [x] Hyperliquid adapter with WebSocket (real-time data)
- [x] 0x Protocol adapter (DEX aggregation)
- [x] Delta neutral strategy
- [x] Real-time price updates
- [x] Order execution
- [x] Position management

### 🚧 TODO

- [ ] Historical data loading (for backtesting)
- [ ] Order event handling (fill/cancel events)
- [ ] Account state management
- [ ] Performance analytics
- [ ] Multi-pair support

## Configuration

### Strategy Parameters

Edit in `examples/hyperliquid_zerox_live.py`:

```python
strategy_config = HyperliquidZeroXConfig(
    spot_instrument="WETHUSDC.ZEROX",
    perp_instrument="ETH-PERP.HYPERLIQUID",
    max_position_size_usd=1000.0,      # Position size
    rebalance_threshold_pct=5.0,       # Rebalance at 5% drift
    min_funding_rate_apy=5.0,          # Min 5% APY to enter
    max_leverage=3.0,                  # Max 3x leverage
    emergency_exit_loss_pct=10.0,      # Stop loss at 10%
)
```

## Safety

1. **Start with testnet** (`HYPERLIQUID__TESTNET=true`)
2. **Small amounts first** ($100-500)
3. **Monitor closely** (first 24 hours)
4. **Set stop losses** (10% max loss)
5. **Keep private keys secure**
6. **Use separate wallet** for trading

## Performance Expectations

### Funding Rates
- **Typical:** 5-15% APY
- **Good:** 15-30% APY
- **Excellent:** 30%+ APY

### Costs
- **Gas:** ~$0.15 per cycle
- **Net profit:** Funding rate - gas costs

### Capital Requirements
- **Minimum:** $500
- **Recommended:** $5,000+
- **Optimal:** $50,000+ (better diversification)

## Risks

- ⚠️ Funding rates can turn negative
- ⚠️ Liquidation risk on Hyperliquid
- ⚠️ Smart contract risk (0x, Hyperliquid)
- ⚠️ Slippage on large trades
- ⚠️ Market volatility during rebalancing

## Troubleshooting

### "Connection refused"
- Check Arbitrum RPC URL is correct
- Try public RPC: `https://arb1.arbitrum.io/rpc`
- Verify firewall settings

### "Insufficient balance"
- Ensure you have USDC on Arbitrum
- Check minimum balance requirements
- Verify wallet address is correct

### "Invalid signature"
- Verify private key is correct
- Check wallet address matches private key
- Ensure no extra spaces in .env file

### "Gas price too high"
- Wait for lower gas prices
- Arbitrum gas is usually very low (~$0.10)
- Check network congestion

## Resources

### Documentation
- [Hyperliquid Docs](https://hyperliquid.gitbook.io/)
- [0x Docs](https://0x.org/docs)
- [Arbitrum Docs](https://docs.arbitrum.io/)
- [NautilusTrader Docs](https://nautilustrader.io/)

### APIs
- [Hyperliquid API](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api)
- [0x API](https://0x.org/docs/api)
- [Alchemy RPC](https://www.alchemy.com/)

## License

MIT License

## Disclaimer

This software is for educational purposes. Trading cryptocurrencies involves risk. Only trade with money you can afford to lose. The authors are not responsible for any financial losses.

---

**Ready to trade?** Run `./quickstart.sh` and get started!

**Questions?** Open an issue or check the docs.

**Note:** All old files (Binance, dYdX, WazirX, etc.) have been removed. This is a clean, focused implementation of Hyperliquid + 0x on Arbitrum L2.
