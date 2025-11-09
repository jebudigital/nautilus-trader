# Live Trading Setup Guide

## Current Status

✅ **Complete:**
- Strategy logic (delta-neutral)
- Backtesting framework
- Data loading and processing
- Risk management
- dYdX V4 adapter skeleton (REST API)

⚠️ **Needs Implementation:**
- dYdX V4 order signing
- Live trading node configuration
- Position monitoring
- Real-time alerts

## Prerequisites

### 1. Exchange Accounts

**Binance:**
- Account with KYC completed
- API key with spot trading permissions
- IP whitelist enabled
- Minimum $50 USDT funded

**dYdX V4:**
- Account created at https://trade.dydx.exchange
- Wallet connected (MetaMask, etc.)
- API credentials generated
- Minimum $50 USDC funded

### 2. API Credentials

Create a `.env` file in project root:

```bash
# dYdX V4
DYDX__NETWORK=testnet  # or 'mainnet' for live
DYDX__API_KEY=your_api_key_here
DYDX__API_SECRET=your_api_secret_here
DYDX__API_PASSPHRASE=your_passphrase_here
DYDX__ACCOUNT_NUMBER=0

# Binance
BINANCE__API_KEY=your_api_key_here
BINANCE__API_SECRET=your_secret_here
BINANCE__SANDBOX=true  # false for mainnet
```

## Implementation Steps

### Step 1: dYdX Order Signing (CRITICAL)

dYdX V4 requires wallet signatures for all orders. You need to implement:

**Option A: Use Private Key Directly**
```python
from eth_account import Account
from eth_account.messages import encode_defunct

# In DydxV4ExecutionClient.__init__
self.private_key = os.getenv('DYDX__PRIVATE_KEY')
self.account = Account.from_key(self.private_key)

def sign_order(self, order_params):
    # Create order message
    message = self._create_order_message(order_params)
    
    # Sign with wallet
    message_hash = encode_defunct(text=message)
    signed = self.account.sign_message(message_hash)
    
    return signed.signature.hex()
```

**Option B: Use Mnemonic**
```python
from eth_account import Account
from mnemonic import Mnemonic

# Derive private key from mnemonic
mnemo = Mnemonic("english")
seed = mnemo.to_seed(mnemonic, passphrase="")
private_key = Account.from_mnemonic(mnemonic).key
```

### Step 2: Order Submission Flow

```python
async def _submit_order(self, order):
    """Submit order to dYdX V4."""
    
    # 1. Prepare order parameters
    order_params = {
        "market": order.instrument_id.symbol.value,
        "side": "BUY" if order.side == OrderSide.BUY else "SELL",
        "type": "MARKET",
        "size": str(float(order.quantity)),
        "clientId": str(order.client_order_id),
        "timeInForce": "IOC",  # Immediate or Cancel
        "postOnly": False,
    }
    
    # 2. Sign order
    signature = self.sign_order(order_params)
    
    # 3. Submit via REST API
    url = f"{self.api_base}/v4/orders"
    headers = {
        "DYDX-SIGNATURE": signature,
        "DYDX-API-KEY": self.api_key,
        "DYDX-TIMESTAMP": str(int(time.time())),
        "DYDX-PASSPHRASE": self.api_passphrase,
    }
    
    async with self._client.post(
        url,
        json=order_params,
        headers=headers
    ) as response:
        if response.status == 201:
            data = await response.json()
            self._handle_order_accepted(order, data)
        else:
            error = await response.text()
            self._handle_order_rejected(order, error)
```

### Step 3: Position Monitoring

```python
async def _monitor_positions(self):
    """Monitor open positions."""
    while True:
        try:
            # Fetch positions from dYdX
            url = f"{self.api_base}/v4/accounts/{self.account_number}/positions"
            async with self._client.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    self._update_positions(data)
            
            await asyncio.sleep(5)  # Poll every 5 seconds
            
        except Exception as e:
            self._log.error(f"Error monitoring positions: {e}")
            await asyncio.sleep(10)
```

### Step 4: Funding Rate Monitoring

Already implemented in adapter - polls every hour:

```python
async def _poll_funding_rates(self, instrument_id):
    """Poll for funding rate updates."""
    while True:
        funding_rate = await self.get_funding_rate(market)
        if funding_rate:
            update = FundingRateUpdate(
                instrument_id=instrument_id,
                rate=funding_rate,
                ts_event=self._clock.timestamp_ns(),
                ts_init=self._clock.timestamp_ns(),
            )
            self._handle_data(update)
        
        await asyncio.sleep(3600)  # Every hour
```

## Testing Strategy

### Phase 1: Paper Trading (1-2 days)
- Run with no API keys
- Verify strategy logic
- Check order generation
- Monitor logs

### Phase 2: Testnet (3-5 days)
- Use testnet for both exchanges
- Submit real orders (fake money)
- Verify fills and positions
- Test error handling

### Phase 3: Small Live (1 week)
- Start with $100 capital
- Position size: $25-50
- Monitor 24/7
- Keep detailed logs

### Phase 4: Scale Up
- Increase capital gradually
- Monitor performance
- Adjust parameters

## Risk Management

### Position Limits
```python
# For $100 capital
max_position_size_usd = 50.0  # $50 per position
max_total_exposure_usd = 100.0  # Total $100
max_leverage = 2.0  # Conservative
```

### Stop Loss
```python
emergency_exit_loss_pct = 5.0  # Exit if loss > 5%
```

### Monitoring
- Check positions every hour
- Set up alerts for:
  - Large losses (>$5)
  - Failed orders
  - API errors
  - Funding rate changes

## Common Issues

### 1. Order Rejected
**Cause:** Invalid signature, insufficient balance, or market closed
**Solution:** Check API credentials, verify balance, check market hours

### 2. Position Not Opening
**Cause:** No market data, funding rate too low, or insufficient capital
**Solution:** Check data subscriptions, lower funding threshold, increase capital

### 3. Rebalancing Too Frequent
**Cause:** Threshold too low, volatile market
**Solution:** Increase rebalance_threshold_pct to 3-5%

### 4. Funding Payments Not Received
**Cause:** Position not held during funding time (every 8 hours)
**Solution:** Hold positions longer, check funding schedule

## Monitoring Dashboard

Create a simple monitoring script:

```python
# scripts/monitor_live.py
import asyncio
from src.crypto_trading_engine.adapters.dydx_v4_nautilus_adapter import create_dydx_v4_clients

async def monitor():
    # Connect to exchanges
    # Fetch positions
    # Calculate P&L
    # Display status
    
    while True:
        print("\n" + "="*60)
        print("📊 Live Trading Status")
        print("="*60)
        print(f"Binance Balance: ${binance_balance:.2f}")
        print(f"dYdX Balance: ${dydx_balance:.2f}")
        print(f"Open Positions: {num_positions}")
        print(f"Total P&L: ${total_pnl:+.2f}")
        print(f"Current Funding APY: {funding_apy:.2f}%")
        
        await asyncio.sleep(60)  # Update every minute

if __name__ == "__main__":
    asyncio.run(monitor())
```

## Emergency Procedures

### Stop Trading
1. Stop the trading script (Ctrl+C)
2. Manually close all positions on exchanges
3. Withdraw funds to safe wallet

### Handle Errors
1. Check logs in `logs/` directory
2. Verify API connectivity
3. Check exchange status pages
4. Contact exchange support if needed

## Next Steps

1. **Implement order signing** in `dydx_v4_nautilus_adapter.py`
2. **Test on testnet** with fake money
3. **Create monitoring dashboard**
4. **Set up alerts** (email/SMS)
5. **Start with $100** on mainnet
6. **Monitor and adjust** parameters

## Support

- dYdX Discord: https://discord.gg/dydx
- Binance Support: https://www.binance.com/en/support
- Nautilus Docs: https://nautilustrader.io/docs/

## Disclaimer

⚠️ **Trading cryptocurrencies involves significant risk. Only trade with money you can afford to lose. This software is provided as-is with no guarantees. Always test thoroughly on testnet before going live.**
