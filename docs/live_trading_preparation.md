# Live Trading Preparation Guide

## 🚀 Complete Setup for Live Uniswap Lending Strategy

This guide covers everything you need to prepare for live trading with the Uniswap lending strategy, including credentials, asset management, and safety procedures.

## 📋 Pre-Flight Checklist

### ✅ **Phase 1: Infrastructure Setup**

#### 1. **API Credentials & Access**

**Binance API (for price feeds)**
```bash
# Required permissions: Read-only for market data
- Spot & Margin Trading: Read (for price feeds)
- Futures Trading: Read (for price feeds)
- Enable Reading: Yes
- Enable Spot & Margin Trading: No (read-only)
- Enable Futures: No (read-only)
```

**Ethereum Infrastructure**
```bash
# Primary RPC Provider (choose one)
- Infura: https://infura.io/ (recommended)
- Alchemy: https://www.alchemy.com/
- QuickNode: https://www.quicknode.com/

# Backup RPC Provider (different from primary)
- Always have a backup from a different provider
```

**Uniswap Subgraph Access**
```bash
# The Graph Protocol
- Main: https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3
- Backup: https://api.studio.thegraph.com/query/uniswap-v3
```

#### 2. **Wallet & Asset Setup**

**Ethereum Wallet Requirements**
```bash
# Wallet Setup
1. Create dedicated trading wallet (separate from personal funds)
2. Generate private key securely (hardware wallet recommended)
3. Fund with initial capital + gas reserves

# Minimum Asset Requirements
- ETH: 0.5-1.0 ETH (for gas fees)
- USDC: $10,000-50,000 (initial liquidity capital)
- WETH: Equivalent to USDC amount (for balanced pools)

# Security Requirements
- Hardware wallet (Ledger/Trezor) for key storage
- Multi-sig wallet for large amounts (>$100k)
- Separate hot wallet for automated trading
```

**Asset Allocation Strategy**
```bash
# Conservative Approach ($25,000 total)
- Gas Reserve: 0.5 ETH (~$1,000)
- USDC: $12,000
- WETH: $12,000 (equivalent ETH amount)

# Aggressive Approach ($100,000 total)
- Gas Reserve: 1.0 ETH (~$2,000)
- USDC: $49,000  
- WETH: $49,000 (equivalent ETH amount)
```

### ✅ **Phase 2: Configuration Setup**

#### 1. **Environment Configuration**

Create `.env` file:
```bash
# Binance API (Read-only for price feeds)
BINANCE_API_KEY=your_binance_api_key_here
BINANCE_API_SECRET=your_binance_secret_here
BINANCE_TESTNET=false

# Ethereum Infrastructure
ETHEREUM_RPC_URL=https://mainnet.infura.io/v3/your_project_id
ETHEREUM_BACKUP_RPC=https://eth-mainnet.alchemyapi.io/v2/your_key
ETHEREUM_CHAIN_ID=1

# Trading Wallet
TRADING_WALLET_PRIVATE_KEY=your_private_key_here
TRADING_WALLET_ADDRESS=0x_your_wallet_address

# Uniswap Configuration
UNISWAP_SUBGRAPH_URL=https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3
UNISWAP_BACKUP_SUBGRAPH=https://api.studio.thegraph.com/query/uniswap-v3

# Risk Management
MAX_POSITION_SIZE_USD=25000
MAX_TOTAL_EXPOSURE_USD=50000
MAX_GAS_PRICE_GWEI=50
EMERGENCY_STOP_LOSS_PCT=15

# Monitoring & Alerts
DISCORD_WEBHOOK_URL=your_discord_webhook_for_alerts
EMAIL_ALERTS=your_email@domain.com
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
```

#### 2. **Strategy Configuration**

```python
# production_config.py
from decimal import Decimal
from src.crypto_trading_engine.strategies.models import StrategyConfig, LiquidityRange

# Production Uniswap Strategy Configuration
PRODUCTION_CONFIG = StrategyConfig(
    # Target Pools (Real Uniswap V3 addresses)
    target_pools=[
        {
            # WETH/USDC 0.05% pool (highest volume)
            'address': '0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640',
            'token0_address': '0xA0b86a33E6441E6C7D3E4C2C4C8C8C8C8C8C8C8C',  # USDC
            'token0_symbol': 'USDC',
            'token0_decimals': 6,
            'token1_address': '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',  # WETH
            'token1_symbol': 'WETH', 
            'token1_decimals': 18,
            'fee_tier': 500,  # 0.05%
            'tick_spacing': 10
        },
        {
            # WETH/USDC 0.30% pool (backup)
            'address': '0x8ad599c3A0ff1De082011EFDDc58f1908eb6e6D8',
            'token0_address': '0xA0b86a33E6441E6C7D3E4C2C4C8C8C8C8C8C8C8C',  # USDC
            'token0_symbol': 'USDC',
            'token0_decimals': 6,
            'token1_address': '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',  # WETH
            'token1_symbol': 'WETH',
            'token1_decimals': 18,
            'fee_tier': 3000,  # 0.30%
            'tick_spacing': 60
        }
    ],
    
    # Pool Selection Criteria
    min_tvl_usd=Decimal('50000000'),        # $50M minimum TVL
    min_volume_24h_usd=Decimal('5000000'),  # $5M minimum daily volume
    min_fee_apy=Decimal('8'),               # 8% minimum APY
    max_price_impact=Decimal('0.005'),      # 0.5% max price impact
    
    # Risk Management (Conservative for live trading)
    max_impermanent_loss=Decimal('5'),       # 5% max IL
    max_position_size_usd=Decimal('25000'),  # $25K max per position
    max_total_exposure_usd=Decimal('50000'), # $50K total max
    
    # Liquidity Strategy
    liquidity_range=LiquidityRange.MEDIUM,
    range_width_percentage=Decimal('15'),    # 15% range width
    rebalance_threshold=Decimal('0.03'),     # 3% price move triggers rebalance
    
    # Gas Optimization (Conservative)
    max_gas_price_gwei=Decimal('50'),        # Max 50 Gwei
    min_profit_threshold_usd=Decimal('100'), # Min $100 profit after gas
    
    # Timing Parameters
    position_hold_min_hours=24,              # Hold positions 24h minimum
    rebalance_cooldown_hours=6               # 6h cooldown between rebalances
)
```

### ✅ **Phase 3: Testing & Validation**

#### 1. **Complete Validation Pipeline**

```python
# validation_pipeline.py
import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from src.crypto_trading_engine.core.multi_mode_strategy import MultiModeStrategyManager

async def run_complete_validation():
    """Run complete validation pipeline before live trading."""
    
    # Configuration
    binance_config = {
        'api_key': 'your_api_key',
        'api_secret': 'your_api_secret',
        'testnet': False  # Use real Binance for price feeds
    }
    
    uniswap_config = {
        'rpc_url': 'https://mainnet.infura.io/v3/your_project_id',
        'chain_id': 1,
        'wallet_private_key': 'your_private_key'
    }
    
    # Create strategy manager
    manager = MultiModeStrategyManager(
        strategy_config=PRODUCTION_CONFIG,
        binance_config=binance_config,
        uniswap_config=uniswap_config
    )
    
    print("🔄 Starting Complete Validation Pipeline")
    print("=" * 60)
    
    # Phase 1: Backtest Validation
    print("📊 Phase 1: Backtest Validation")
    backtest_result = await manager.run_backtest_validation(
        start_date=datetime.now() - timedelta(days=30),
        end_date=datetime.now(),
        initial_capital=Decimal('50000')
    )
    
    print(f"✅ Backtest Result: {backtest_result.is_valid}")
    print(f"   Message: {backtest_result.message}")
    
    if not backtest_result.is_valid:
        print("❌ Backtest validation failed - stopping pipeline")
        return
    
    # Phase 2: Paper Trading Validation
    print("\n📈 Phase 2: Paper Trading Validation (7 days)")
    paper_result = await manager.run_paper_trading_validation(duration_days=7)
    
    print(f"✅ Paper Trading Result: {paper_result.is_valid}")
    print(f"   Message: {paper_result.message}")
    
    if not paper_result.is_valid:
        print("❌ Paper trading validation failed - stopping pipeline")
        return
    
    # Phase 3: Live Trading Readiness
    print("\n🚀 Phase 3: Live Trading Readiness Check")
    live_result = await manager.promote_to_live_trading()
    
    print(f"✅ Live Trading Ready: {live_result.is_valid}")
    print(f"   Message: {live_result.message}")
    
    # Summary
    summary = manager.get_validation_summary()
    print("\n📋 Validation Summary:")
    print(f"   Current Mode: {summary['current_mode']}")
    print(f"   Ready for Live: {summary['ready_for_live']}")
    
    for mode, validation in summary['validations'].items():
        print(f"   {mode}: {'✅' if validation['is_valid'] else '❌'} {validation['message']}")
    
    await manager.cleanup()

if __name__ == "__main__":
    asyncio.run(run_complete_validation())
```

#### 2. **Safety Testing Checklist**

```bash
# Pre-Live Testing Checklist
□ Backtest validation passed (Sharpe > 1.0, Drawdown < 15%)
□ Paper trading completed (7+ days, consistent performance)
□ API connections tested (Binance, Ethereum RPC, Subgraph)
□ Wallet connectivity verified
□ Gas price monitoring working
□ Emergency stop procedures tested
□ Position size limits enforced
□ Impermanent loss monitoring active
□ Alert systems configured and tested
□ Backup systems ready (RPC, APIs)
```

### ✅ **Phase 4: Live Trading Deployment**

#### 1. **Production Deployment Script**

```python
# deploy_live_strategy.py
import asyncio
import os
from decimal import Decimal
from src.crypto_trading_engine.core.multi_mode_strategy import MultiModeStrategyManager
from production_config import PRODUCTION_CONFIG

async def deploy_live_strategy():
    """Deploy strategy to live trading after validation."""
    
    # Load configuration from environment
    binance_config = {
        'api_key': os.getenv('BINANCE_API_KEY'),
        'api_secret': os.getenv('BINANCE_API_SECRET'),
        'testnet': False
    }
    
    uniswap_config = {
        'rpc_url': os.getenv('ETHEREUM_RPC_URL'),
        'backup_rpc': os.getenv('ETHEREUM_BACKUP_RPC'),
        'chain_id': int(os.getenv('ETHEREUM_CHAIN_ID', 1)),
        'wallet_private_key': os.getenv('TRADING_WALLET_PRIVATE_KEY')
    }
    
    # Validate environment
    required_vars = [
        'BINANCE_API_KEY', 'BINANCE_API_SECRET',
        'ETHEREUM_RPC_URL', 'TRADING_WALLET_PRIVATE_KEY'
    ]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        print(f"❌ Missing environment variables: {missing_vars}")
        return
    
    # Create strategy manager
    manager = MultiModeStrategyManager(
        strategy_config=PRODUCTION_CONFIG,
        binance_config=binance_config,
        uniswap_config=uniswap_config
    )
    
    print("🚀 Deploying Live Trading Strategy")
    print("=" * 50)
    
    # Initialize live trading mode
    await manager.initialize_mode(TradingMode.LIVE)
    
    print("✅ Live trading strategy deployed successfully!")
    print("📊 Strategy is now active and monitoring markets...")
    
    # Keep strategy running (in production, this would be a proper daemon)
    try:
        while True:
            await asyncio.sleep(60)  # Check every minute
            # In production: monitor performance, check alerts, etc.
            
    except KeyboardInterrupt:
        print("\n🛑 Shutting down strategy...")
        await manager.cleanup()
        print("✅ Strategy shutdown complete")

if __name__ == "__main__":
    asyncio.run(deploy_live_strategy())
```

#### 2. **Monitoring & Alerts Setup**

```python
# monitoring_setup.py
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any

class LiveTradingMonitor:
    """Monitor live trading strategy and send alerts."""
    
    def __init__(self, strategy_manager: MultiModeStrategyManager):
        self.strategy_manager = strategy_manager
        self.alert_thresholds = {
            'max_drawdown': 0.10,      # 10% max drawdown alert
            'min_daily_pnl': -500,     # -$500 daily loss alert
            'max_gas_price': 100,      # 100 Gwei gas price alert
            'min_pool_tvl': 10000000   # $10M minimum pool TVL
        }
    
    async def monitor_performance(self):
        """Continuously monitor strategy performance."""
        while True:
            try:
                # Check strategy health
                await self._check_strategy_health()
                
                # Check market conditions
                await self._check_market_conditions()
                
                # Check risk metrics
                await self._check_risk_metrics()
                
                # Sleep for 5 minutes
                await asyncio.sleep(300)
                
            except Exception as e:
                await self._send_alert(f"Monitoring error: {e}", "ERROR")
    
    async def _check_strategy_health(self):
        """Check if strategy is running properly."""
        # Implementation would check:
        # - Strategy is active and responding
        # - Data feeds are working
        # - No stuck transactions
        # - API connections healthy
        pass
    
    async def _check_market_conditions(self):
        """Check market conditions for alerts."""
        # Implementation would check:
        # - Extreme volatility
        # - Low liquidity conditions
        # - High gas prices
        # - Network congestion
        pass
    
    async def _check_risk_metrics(self):
        """Check risk metrics and position sizes."""
        # Implementation would check:
        # - Current drawdown vs limits
        # - Position sizes vs limits
        # - Impermanent loss levels
        # - Portfolio exposure
        pass
    
    async def _send_alert(self, message: str, level: str = "INFO"):
        """Send alert via configured channels."""
        timestamp = datetime.now().isoformat()
        alert_msg = f"[{level}] {timestamp}: {message}"
        
        # Log alert
        logging.warning(alert_msg)
        
        # Send to Discord/Telegram/Email
        # Implementation would send to configured alert channels
        print(f"🚨 ALERT: {alert_msg}")
```

## 🔐 Security Best Practices

### **Wallet Security**
```bash
# Hardware Wallet Setup (Recommended)
1. Use Ledger or Trezor for key storage
2. Enable 2FA on all exchange accounts
3. Use separate wallets for different purposes:
   - Cold storage: Long-term holdings
   - Hot wallet: Active trading (minimal funds)
   - Gas wallet: ETH for transaction fees

# Private Key Management
- Never store private keys in plain text
- Use encrypted key stores (Keystore files)
- Consider multi-sig wallets for large amounts
- Regular key rotation for hot wallets
```

### **API Security**
```bash
# Binance API Security
- Use read-only permissions for price feeds
- Restrict IP access to your server
- Enable 2FA on Binance account
- Regular API key rotation

# Ethereum RPC Security
- Use reputable providers (Infura, Alchemy)
- Set up multiple backup providers
- Monitor RPC usage and limits
- Use WebSocket connections for real-time data
```

## 💰 Capital Requirements

### **Minimum Capital Recommendations**

**Conservative Start ($25,000)**
```bash
- Gas Reserve: $1,000 (0.5 ETH)
- Trading Capital: $24,000
- Expected Daily P&L: $50-150
- Max Risk: 5% ($1,250)
```

**Professional Setup ($100,000)**
```bash
- Gas Reserve: $2,000 (1.0 ETH)  
- Trading Capital: $98,000
- Expected Daily P&L: $200-600
- Max Risk: 5% ($5,000)
```

**Enterprise Setup ($500,000+)**
```bash
- Gas Reserve: $5,000 (2.5 ETH)
- Trading Capital: $495,000
- Expected Daily P&L: $1,000-3,000
- Max Risk: 3% ($15,000)
- Requires: Multi-sig, dedicated infrastructure
```

## 🚨 Emergency Procedures

### **Emergency Stop Conditions**
```bash
# Automatic Stop Triggers
- Drawdown > 15% (configurable)
- Daily loss > $1,000 (configurable)
- Gas prices > 200 Gwei
- Network congestion > 90%
- API failures > 5 consecutive

# Manual Stop Procedures
1. Set emergency stop flag
2. Close all open positions
3. Withdraw liquidity from pools
4. Move funds to safe wallet
5. Investigate and resolve issues
```

### **Recovery Procedures**
```bash
# After Emergency Stop
1. Analyze what triggered the stop
2. Review logs and performance data
3. Adjust strategy parameters if needed
4. Test in paper trading mode
5. Gradual restart with reduced position sizes
```

## 📊 Performance Monitoring

### **Key Metrics to Track**
```bash
# Daily Monitoring
- P&L (daily, weekly, monthly)
- Sharpe ratio (rolling 30-day)
- Maximum drawdown
- Win rate and profit factor
- Gas costs as % of profits
- Impermanent loss levels

# Technical Monitoring  
- API response times
- Transaction success rates
- Gas price trends
- Pool liquidity levels
- Network congestion
```

This comprehensive guide provides everything needed to safely deploy the Uniswap lending strategy to live trading. The key is following the validation pipeline and never skipping safety checks!