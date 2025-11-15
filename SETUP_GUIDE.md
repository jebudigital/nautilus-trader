# Setup Guide: Hyperliquid + Uniswap Delta Neutral Strategy

Complete guide to set up and run the delta neutral strategy.

## Prerequisites

- Python 3.10 or higher
- Ethereum wallet with private key
- Hyperliquid account (testnet or mainnet)
- Ethereum RPC endpoint (Alchemy, Infura, or self-hosted)

## Step 1: Install Dependencies

```bash
# Clone repository (if not already done)
cd crypto-trading-engine

# Install Python dependencies
pip install -r requirements.txt

# Verify installation
python -c "import nautilus_trader; print(f'NautilusTrader {nautilus_trader.__version__}')"
```

## Step 2: Set Up Hyperliquid

### Testnet (Recommended for Testing)

1. Visit [Hyperliquid Testnet](https://app.hyperliquid-testnet.xyz)
2. Connect your wallet (MetaMask, etc.)
3. Get testnet USDC from faucet
4. Note your wallet address and private key

### Mainnet (Production)

1. Visit [Hyperliquid](https://app.hyperliquid.xyz)
2. Connect your wallet
3. Deposit USDC for margin
4. **Start with small amounts!**

### Get Your Credentials

```python
# Your wallet private key (KEEP SECRET!)
HYPERLIQUID__PRIVATE_KEY=0x1234567890abcdef...

# Your wallet address
HYPERLIQUID__WALLET_ADDRESS=0xYourWalletAddress...

# Testnet or mainnet
HYPERLIQUID__TESTNET=true  # or false for mainnet
```

## Step 3: Set Up Uniswap

### Get Ethereum RPC Endpoint

**Option 1: Alchemy (Recommended)**

1. Sign up at [Alchemy](https://www.alchemy.com/)
2. Create a new app (Ethereum Mainnet)
3. Copy the HTTPS endpoint

**Option 2: Infura**

1. Sign up at [Infura](https://infura.io/)
2. Create a new project
3. Copy the Ethereum endpoint

**Option 3: Self-Hosted Node**

```bash
# Run your own Ethereum node
geth --http --http.api eth,net,web3
```

### Get Your Credentials

```python
# RPC endpoint
UNISWAP__RPC_URL=https://eth-mainnet.g.alchemy.com/v2/your-api-key

# Your wallet private key (KEEP SECRET!)
UNISWAP__PRIVATE_KEY=0x1234567890abcdef...

# Your wallet address
UNISWAP__WALLET_ADDRESS=0xYourWalletAddress...
```

### Fund Your Wallet

You'll need:
- **ETH** for gas fees (~0.1 ETH recommended)
- **WETH or USDC** for trading (depends on pair)

## Step 4: Configure Environment

```bash
# Copy example config
cp .env.example .env

# Edit .env with your credentials
nano .env  # or use your favorite editor
```

Example `.env`:

```bash
# Hyperliquid
HYPERLIQUID__PRIVATE_KEY=0xyour_private_key_here
HYPERLIQUID__WALLET_ADDRESS=0xyour_wallet_address_here
HYPERLIQUID__TESTNET=true

# Uniswap
UNISWAP__RPC_URL=https://eth-mainnet.g.alchemy.com/v2/your-api-key
UNISWAP__PRIVATE_KEY=0xyour_private_key_here
UNISWAP__WALLET_ADDRESS=0xyour_wallet_address_here

# Strategy
STRATEGY__MAX_POSITION_SIZE_USD=1000.0
STRATEGY__MIN_FUNDING_RATE_APY=5.0
STRATEGY__REBALANCE_THRESHOLD_PCT=5.0
```

## Step 5: Test Connection

### Test Hyperliquid

```python
import asyncio
from src.crypto_trading_engine.adapters.hyperliquid_adapter import HyperliquidHttpClient

async def test_hyperliquid():
    client = HyperliquidHttpClient(
        private_key="0x...",
        wallet_address="0x...",
        testnet=True,
    )
    
    # Get account state
    state = await client.get_user_state()
    print("Account State:", state)
    
    # Get instruments
    meta = await client.get_meta()
    print(f"Available instruments: {len(meta['universe'])}")
    
    await client.close()

asyncio.run(test_hyperliquid())
```

### Test Uniswap

```python
from src.crypto_trading_engine.adapters.uniswap_adapter import UniswapHttpClient

client = UniswapHttpClient(
    rpc_url="https://...",
    private_key="0x...",
    wallet_address="0x...",
)

# Check ETH balance
eth_balance = client.get_balance("ETH")
print(f"ETH Balance: {eth_balance:.4f}")

# Check if connected
print(f"Connected: {client.w3.is_connected()}")
print(f"Chain ID: {client.w3.eth.chain_id}")
```

## Step 6: Run Backtest (Optional)

```bash
# Run backtest with historical data
python examples/hyperliquid_uniswap_backtest.py

# Note: You'll need to implement historical data loading first
```

## Step 7: Run Paper Trading (Testnet)

```bash
# Make sure HYPERLIQUID__TESTNET=true in .env
python examples/hyperliquid_uniswap_live.py
```

This will:
1. Connect to Hyperliquid testnet
2. Connect to Uniswap (mainnet or testnet)
3. Start monitoring funding rates
4. Execute trades when conditions are met

## Step 8: Run Live Trading (Mainnet)

**⚠️ WARNING: This uses real money!**

```bash
# Set HYPERLIQUID__TESTNET=false in .env
python examples/hyperliquid_uniswap_live.py

# You'll be prompted to confirm
Type 'START' to proceed: START
```

## Monitoring

### Check Positions

```python
# In Python console
from nautilus_trader.cache.cache import Cache

cache = Cache()
positions = list(cache.positions_open())

for position in positions:
    print(f"{position.instrument_id}: {position.quantity}")
```

### Check Balances

```python
# Hyperliquid
state = await hyperliquid_client.get_user_state()
print(state['marginSummary'])

# Uniswap
eth_balance = uniswap_client.get_balance("ETH")
print(f"ETH: {eth_balance}")
```

### View Logs

```bash
# Real-time logs
tail -f logs/trading_*.log

# Search for errors
grep ERROR logs/trading_*.log
```

## Troubleshooting

### "Connection refused"

- Check your RPC endpoint is correct
- Verify your API key is valid
- Check firewall settings

### "Insufficient balance"

- Ensure you have enough USDC on Hyperliquid
- Ensure you have enough ETH for gas on Ethereum
- Check minimum balance requirements

### "Invalid signature"

- Verify your private key is correct
- Check wallet address matches private key
- Ensure no extra spaces in .env file

### "Gas price too high"

- Wait for lower gas prices
- Use L2 (Arbitrum, Optimism) instead
- Adjust gas price limits

### "Slippage too high"

- Reduce position size
- Use limit orders instead of market orders
- Check pool liquidity

## Best Practices

### Security

1. **Never commit .env file**
   ```bash
   # Verify .env is in .gitignore
   cat .gitignore | grep .env
   ```

2. **Use separate wallets**
   - One for testing (testnet)
   - One for production (mainnet)
   - Never use your main wallet

3. **Start small**
   - Test with $100-$1000 first
   - Gradually increase position size
   - Monitor closely for first week

### Risk Management

1. **Set position limits**
   ```python
   max_position_size_usd=1000.0  # Start small
   ```

2. **Monitor funding rates**
   - Exit if funding turns negative
   - Adjust min_funding_rate_apy threshold

3. **Set stop losses**
   ```python
   emergency_exit_loss_pct=10.0  # Exit at 10% loss
   ```

### Performance

1. **Use WebSocket for real-time data**
   - Faster than polling
   - Lower latency

2. **Optimize gas costs**
   - Batch transactions when possible
   - Use L2s for lower fees

3. **Monitor slippage**
   - Use limit orders for large trades
   - Check pool depth before trading

## Next Steps

1. **Implement historical data loading**
   - Download data from Hyperliquid API
   - Download data from The Graph (Uniswap)
   - Store in Parquet format

2. **Add WebSocket support**
   - Real-time price updates
   - Real-time funding rate updates
   - Order book updates

3. **Implement Uniswap swap execution**
   - Approve token spending
   - Execute swaps via router
   - Handle transaction confirmations

4. **Add multi-pair support**
   - Trade multiple pairs simultaneously
   - Diversify funding rate exposure

5. **Build monitoring dashboard**
   - Web UI for monitoring
   - Real-time P&L tracking
   - Alert system

## Support

- **Documentation:** See README.md
- **Issues:** Open GitHub issue
- **Community:** Join Discord/Telegram

## Resources

- [Hyperliquid Docs](https://hyperliquid.gitbook.io/)
- [Uniswap Docs](https://docs.uniswap.org/)
- [NautilusTrader Docs](https://nautilustrader.io/)
- [Web3.py Docs](https://web3py.readthedocs.io/)

---

**Ready to trade?** Follow the steps above and start with testnet!
