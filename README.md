# Crypto Algorithmic Trading Engine

A sophisticated algorithmic trading engine built on the Nautilus framework for executing trading strategies across centralized exchanges (Binance) and decentralized protocols (Uniswap, dYdX).

## Features

- **Multi-venue Trading**: Execute strategies across Binance, dYdX, and Uniswap
- **Advanced Strategies**: Uniswap lending and delta-neutral strategies
- **Risk Management**: Comprehensive risk controls and portfolio monitoring
- **Real-time Execution**: Low-latency order execution and market data processing
- **Backtesting**: Historical strategy testing and performance analysis

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd crypto-algo-trading-engine
```

2. Install dependencies:
```bash
pip install -e .
```

3. For development:
```bash
pip install -e ".[dev]"
```

## Configuration

1. Copy the example environment file:
```bash
cp .env.example .env
```

2. Edit `.env` with your API keys and configuration:
- Binance API credentials
- dYdX API credentials  
- Web3 provider URL and private key

## Usage

### Development Mode
```bash
trading-engine --environment dev --log-level DEBUG
```

### Production Mode
```bash
trading-engine --environment prod --config config/custom.env
```

## Project Structure

```
src/crypto_trading_engine/
├── __init__.py
├── main.py                 # Main entry point
├── adapters/              # Exchange and protocol adapters
├── config/                # Configuration management
├── core/                  # Core engine components
├── models/                # Data models
└── strategies/            # Trading strategies
```

## Development

### Running Tests
```bash
pytest
```

### Code Formatting
```bash
black src/
isort src/
```

### Type Checking
```bash
mypy src/
```

## License

MIT License - see LICENSE file for details.