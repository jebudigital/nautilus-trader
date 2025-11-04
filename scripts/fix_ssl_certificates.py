#!/usr/bin/env python3
"""
SSL Certificate Fix Script for macOS

This script fixes common SSL certificate verification issues on macOS
that prevent the trading engine from connecting to external APIs.
"""

import os
import sys
import subprocess
import ssl
import urllib.request
from pathlib import Path


def test_ssl_connection():
    """Test if SSL connections work."""
    test_urls = [
        'https://api.coinbase.com/v2/exchange-rates',
        'https://api.coingecko.com/api/v3/ping',
        'https://api.etherscan.io/api'
    ]
    
    print("🔍 Testing SSL connections...")
    
    for url in test_urls:
        try:
            response = urllib.request.urlopen(url, timeout=5)
            print(f"✅ {url} - OK")
        except Exception as e:
            print(f"❌ {url} - FAILED: {e}")
            return False
    
    return True


def install_certifi():
    """Install/upgrade certifi package."""
    print("📦 Installing/upgrading certifi...")
    
    try:
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--upgrade', 'certifi'], 
                      check=True, capture_output=True)
        print("✅ certifi installed/upgraded successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install certifi: {e}")
        return False


def run_install_certificates():
    """Run the Install Certificates command if available."""
    print("🔧 Looking for Install Certificates command...")
    
    # Find Python installation directories
    python_dirs = []
    
    # Check common locations
    for version in ['3.13', '3.12', '3.11', '3.10', '3.9']:
        cert_path = f"/Applications/Python {version}/Install Certificates.command"
        if os.path.exists(cert_path):
            python_dirs.append(cert_path)
    
    if python_dirs:
        for cert_path in python_dirs:
            print(f"📋 Found: {cert_path}")
            try:
                subprocess.run(['sudo', cert_path], check=True)
                print(f"✅ Executed: {cert_path}")
                return True
            except subprocess.CalledProcessError as e:
                print(f"⚠️  Failed to execute {cert_path}: {e}")
    else:
        print("⚠️  No Install Certificates command found")
    
    return False


def setup_environment_variables():
    """Set up SSL environment variables."""
    print("🌍 Setting up SSL environment variables...")
    
    try:
        import certifi
        cert_path = certifi.where()
        
        # Add to shell profiles
        shell_configs = [
            os.path.expanduser('~/.zshrc'),
            os.path.expanduser('~/.bash_profile'),
            os.path.expanduser('~/.bashrc')
        ]
        
        ssl_exports = f"""
# SSL Certificate Configuration (added by crypto trading engine)
export SSL_CERT_FILE="{cert_path}"
export REQUESTS_CA_BUNDLE="{cert_path}"
export CURL_CA_BUNDLE="{cert_path}"
"""
        
        for config_file in shell_configs:
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    content = f.read()
                
                if 'SSL_CERT_FILE' not in content:
                    with open(config_file, 'a') as f:
                        f.write(ssl_exports)
                    print(f"✅ Updated {config_file}")
                else:
                    print(f"✅ {config_file} already configured")
        
        # Set for current session
        os.environ['SSL_CERT_FILE'] = cert_path
        os.environ['REQUESTS_CA_BUNDLE'] = cert_path
        os.environ['CURL_CA_BUNDLE'] = cert_path
        
        print(f"✅ SSL certificates configured: {cert_path}")
        return True
        
    except ImportError:
        print("❌ certifi not available")
        return False


def update_homebrew_certificates():
    """Update certificates via Homebrew if available."""
    print("🍺 Checking Homebrew certificates...")
    
    try:
        # Check if Homebrew is installed
        subprocess.run(['brew', '--version'], check=True, capture_output=True)
        
        # Update certificates
        subprocess.run(['brew', 'update'], check=True, capture_output=True)
        subprocess.run(['brew', 'install', 'ca-certificates'], check=True, capture_output=True)
        
        print("✅ Homebrew certificates updated")
        return True
        
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("⚠️  Homebrew not available or failed to update certificates")
        return False


def main():
    """Main SSL certificate fix routine."""
    print("🔐 SSL Certificate Fix Script")
    print("=" * 50)
    
    # Test initial state
    if test_ssl_connection():
        print("✅ SSL connections already working!")
        return
    
    print("❌ SSL connections failing - applying fixes...")
    
    # Try multiple fix strategies
    fixes_applied = []
    
    # 1. Install/upgrade certifi
    if install_certifi():
        fixes_applied.append("certifi")
    
    # 2. Set up environment variables
    if setup_environment_variables():
        fixes_applied.append("environment")
    
    # 3. Try Install Certificates command
    if run_install_certificates():
        fixes_applied.append("install_certificates")
    
    # 4. Try Homebrew certificates
    if update_homebrew_certificates():
        fixes_applied.append("homebrew")
    
    print(f"\n🔧 Applied fixes: {', '.join(fixes_applied)}")
    
    # Test again
    print("\n🔍 Testing SSL connections after fixes...")
    if test_ssl_connection():
        print("✅ SSL connections now working!")
        print("\n📋 Next steps:")
        print("1. Restart your terminal")
        print("2. Run: source ~/.zshrc")
        print("3. Test the trading engine again")
    else:
        print("❌ SSL connections still failing")
        print("\n🛠️  Manual steps to try:")
        print("1. Restart your terminal")
        print("2. Run: /Applications/Python\\ 3.x/Install\\ Certificates.command")
        print("3. Run: pip3 install --upgrade certifi")
        print("4. Add to ~/.zshrc:")
        print("   export SSL_CERT_FILE=$(python3 -m certifi)")
        print("   export REQUESTS_CA_BUNDLE=$(python3 -m certifi)")


if __name__ == "__main__":
    main()