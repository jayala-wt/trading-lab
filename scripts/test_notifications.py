#!/usr/bin/env python3
"""
Test Trading Bot Notifications
"""
import sys
from pathlib import Path

# Add trading-lab to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.common.notifications import (
    notify_trade_opened,
    notify_trade_closed,
    notify_daily_summary,
    notify_risk_alert
)

def test_trade_opened():
    """Test trade opened notification"""
    print("📧 Testing trade opened notification...")
    
    trade_data = {
        'symbol': 'BTC/USD',
        'side': 'buy',
        'qty': 0.001,
        'entry_price': 95500.00,
        'bot_id': 'crypto_5m_core',
        'strategy_id': 'dim_momentum_reversal'
    }
    
    success = notify_trade_opened(trade_data)
    print(f"   ✅ Sent!" if success else "   ❌ Failed")
    return success


def test_trade_closed():
    """Test trade closed notification"""
    print("📧 Testing trade closed notification...")
    
    trade_data = {
        'symbol': 'ETH/USD',
        'side': 'buy',
        'entry_price': 3500.00,
        'exit_price': 3587.50,
        'realized_pnl': 2.50,
        'bot_id': 'crypto_5m_core'
    }
    
    success = notify_trade_closed(trade_data)
    print(f"   ✅ Sent!" if success else "   ❌ Failed")
    return success


def test_daily_summary():
    """Test daily summary notification"""
    print("📧 Testing daily summary notification...")
    
    summary_data = {
        'date': '2026-02-14',
        'total_trades': 149,
        'wins': 72,
        'losses': 77,
        'total_pnl': -0.62
    }
    
    success = notify_daily_summary(summary_data)
    print(f"   ✅ Sent!" if success else "   ❌ Failed")
    return success


def test_risk_alert():
    """Test risk alert notification"""
    print("📧 Testing risk alert notification...")
    
    alert_data = {
        'type': 'MAX_TRADES_PER_DAY',
        'message': 'Daily trade limit reached for crypto_5m_core',
        'current_value': 20,
        'limit': 20
    }
    
    success = notify_risk_alert(alert_data)
    print(f"   ✅ Sent!" if success else "   ❌ Failed")
    return success


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Test trading bot notifications')
    parser.add_argument('--test', choices=['open', 'close', 'summary', 'alert', 'all'], 
                       default='all', help='Which notification to test')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("🧪 Trading Bot Notification Tests")
    print("=" * 60)
    print(f"Email: wanatux@gmail.com\n")
    
    tests = {
        'open': test_trade_opened,
        'close': test_trade_closed,
        'summary': test_daily_summary,
        'alert': test_risk_alert
    }
    
    if args.test == 'all':
        results = []
        for name, test_func in tests.items():
            results.append(test_func())
            print()
        
        print("=" * 60)
        print(f"✅ Passed: {sum(results)}/{len(results)}")
        print("=" * 60)
    else:
        tests[args.test]()
    
    print("\n📬 Check your inbox at wanatux@gmail.com")


if __name__ == '__main__':
    main()
