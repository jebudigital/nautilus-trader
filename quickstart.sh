#!/bin/bash

echo "🚀 Hyperliquid + Uniswap Delta Neutral Strategy - Quick Start"
echo "=============================================================="
echo ""

# Check Python version
echo "Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "✅ Python $python_version"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found"
    echo "Creating from template..."
    cp .env.example .env
    echo "✅ Created .env file"
    echo ""
    echo "📝 Please edit .env with your credentials:"
    echo "   nano .env"
    echo ""
    exit 1
fi

# Check if dependencies are installed
echo "Checking dependencies..."
if python3 -c "import nautilus_trader" 2>/dev/null; then
    echo "✅ NautilusTrader installed"
else
    echo "⚠️  NautilusTrader not found"
    echo "Installing dependencies..."
    pip install -r requirements.txt
    echo "✅ Dependencies installed"
fi
echo ""

# Check if web3 is installed
if python3 -c "import web3" 2>/dev/null; then
    echo "✅ Web3.py installed"
else
    echo "⚠️  Web3.py not found"
    echo "Installing..."
    pip install web3 eth-account
    echo "✅ Web3.py installed"
fi
echo ""

# Menu
echo "What would you like to do?"
echo ""
echo "1. Test Hyperliquid connection"
echo "2. Test Uniswap connection"
echo "3. Run backtest"
echo "4. Run paper trading (testnet)"
echo "5. Run live trading (mainnet)"
echo "6. Clean up old files"
echo "7. View documentation"
echo "8. Exit"
echo ""
read -p "Enter choice [1-8]: " choice

case $choice in
    1)
        echo ""
        echo "Testing Hyperliquid connection..."
        python3 -c "
import asyncio
import os
from dotenv import load_dotenv
from src.crypto_trading_engine.adapters.hyperliquid_adapter import HyperliquidHttpClient

load_dotenv()

async def test():
    client = HyperliquidHttpClient(
        private_key=os.getenv('HYPERLIQUID__PRIVATE_KEY', ''),
        wallet_address=os.getenv('HYPERLIQUID__WALLET_ADDRESS', ''),
        testnet=os.getenv('HYPERLIQUID__TESTNET', 'true').lower() == 'true',
    )
    try:
        meta = await client.get_meta()
        print(f'✅ Connected to Hyperliquid!')
        print(f'   Available instruments: {len(meta[\"universe\"])}')
        
        state = await client.get_user_state()
        margin = state.get('marginSummary', {})
        print(f'   Account value: \${float(margin.get(\"accountValue\", 0)):.2f}')
    except Exception as e:
        print(f'❌ Error: {e}')
    finally:
        await client.close()

asyncio.run(test())
"
        ;;
    2)
        echo ""
        echo "Testing Uniswap connection..."
        python3 -c "
import os
from dotenv import load_dotenv
from src.crypto_trading_engine.adapters.uniswap_adapter import UniswapHttpClient

load_dotenv()

client = UniswapHttpClient(
    rpc_url=os.getenv('UNISWAP__RPC_URL', ''),
    private_key=os.getenv('UNISWAP__PRIVATE_KEY', ''),
    wallet_address=os.getenv('UNISWAP__WALLET_ADDRESS', ''),
)

try:
    if client.w3.is_connected():
        print('✅ Connected to Ethereum!')
        print(f'   Chain ID: {client.w3.eth.chain_id}')
        
        eth_balance = client.get_balance('ETH')
        print(f'   ETH balance: {eth_balance:.4f}')
    else:
        print('❌ Not connected')
except Exception as e:
    print(f'❌ Error: {e}')
"
        ;;
    3)
        echo ""
        echo "Running backtest..."
        python3 examples/hyperliquid_uniswap_backtest.py
        ;;
    4)
        echo ""
        echo "⚠️  Make sure HYPERLIQUID__TESTNET=true in .env"
        read -p "Press Enter to continue..."
        python3 examples/hyperliquid_uniswap_live.py
        ;;
    5)
        echo ""
        echo "⚠️  WARNING: This will use REAL MONEY!"
        echo "⚠️  Make sure HYPERLIQUID__TESTNET=false in .env"
        read -p "Type 'START' to continue: " confirm
        if [ "$confirm" = "START" ]; then
            python3 examples/hyperliquid_uniswap_live.py
        else
            echo "Cancelled"
        fi
        ;;
    6)
        echo ""
        echo "This will remove old exchange files (Binance, dYdX, Bybit)"
        read -p "Continue? [y/N]: " confirm
        if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
            ./cleanup_old_exchanges.sh
        else
            echo "Cancelled"
        fi
        ;;
    7)
        echo ""
        echo "Documentation:"
        echo "  - README.md - Main documentation"
        echo "  - SETUP_GUIDE.md - Setup instructions"
        echo "  - MIGRATION_SUMMARY.md - Migration guide"
        echo ""
        read -p "Open README.md? [y/N]: " confirm
        if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
            if command -v less &> /dev/null; then
                less README_HYPERLIQUID_UNISWAP.md
            else
                cat README_HYPERLIQUID_UNISWAP.md
            fi
        fi
        ;;
    8)
        echo "Goodbye!"
        exit 0
        ;;
    *)
        echo "Invalid choice"
        exit 1
        ;;
esac

echo ""
echo "Done!"
