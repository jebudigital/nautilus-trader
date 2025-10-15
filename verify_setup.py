#!/usr/bin/env python3
"""
Verification script for the crypto trading engine setup.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def verify_imports():
    """Verify that all core modules can be imported."""
    try:
        from crypto_trading_engine import __version__
        print(f"✓ Core package imported successfully (version: {__version__})")
        
        from crypto_trading_engine.config.settings import load_config
        print("✓ Configuration module imported successfully")
        
        from crypto_trading_engine.main import main
        print("✓ Main module imported successfully")
        
        # Test configuration loading
        config = load_config("test")
        print(f"✓ Configuration loaded successfully (trader_id: {config.trader_id})")
        
        return True
        
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False

def verify_structure():
    """Verify that the project structure is correct."""
    required_dirs = [
        "src/crypto_trading_engine",
        "src/crypto_trading_engine/adapters",
        "src/crypto_trading_engine/config", 
        "src/crypto_trading_engine/core",
        "src/crypto_trading_engine/models",
        "src/crypto_trading_engine/strategies",
        "config",
        "tests",
    ]
    
    required_files = [
        "pyproject.toml",
        "requirements.txt",
        "README.md",
        ".gitignore",
        "config/dev.env",
        "config/test.env", 
        "config/prod.env",
    ]
    
    all_good = True
    
    for dir_path in required_dirs:
        if Path(dir_path).exists():
            print(f"✓ Directory exists: {dir_path}")
        else:
            print(f"✗ Missing directory: {dir_path}")
            all_good = False
    
    for file_path in required_files:
        if Path(file_path).exists():
            print(f"✓ File exists: {file_path}")
        else:
            print(f"✗ Missing file: {file_path}")
            all_good = False
    
    return all_good

def main():
    """Run all verification checks."""
    print("Verifying crypto trading engine setup...\n")
    
    print("1. Checking project structure:")
    structure_ok = verify_structure()
    
    print("\n2. Checking imports:")
    imports_ok = verify_imports()
    
    print("\n" + "="*50)
    if structure_ok and imports_ok:
        print("✓ All checks passed! Setup is complete.")
        print("\nNext steps:")
        print("1. Install dependencies: pip install -e .")
        print("2. Copy .env.example to .env and configure")
        print("3. Run: trading-engine --environment dev")
        return 0
    else:
        print("✗ Some checks failed. Please review the output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())