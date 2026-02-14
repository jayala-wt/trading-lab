# Trading Bot Notifications Setup

## Overview

Leverages your existing **msmtp** email setup to send trading alerts. No need for WhatsApp/Telegram - you already have email working!

## Notification Types

### 1. Trade Opened 🟢
Sent when a new trade is executed:
- Symbol, side (buy/sell)
- Entry price & position size  
- Bot & strategy info

### 2. Trade Closed ✅/❌  
Sent when a trade closes:
- P&L in $ and %
- Entry vs exit prices
- Win/loss indicator

### 3. Daily Summary 📊
End-of-day digest:
- Total P&L
- Win rate
- Winner/loser count

### 4. Risk Alerts ⚠️
Sent when limits hit:
- Max trades per day
- Daily loss limit
- Kill switch triggers

## Quick Test

```bash
cd /opt/homelab-panel/trading-lab

# Test all notifications
python3 scripts/test_notifications.py

# Test specific type
python3 scripts/test_notifications.py --test summary
```

Check your inbox at **user@example.com**!

## Integration Examples

### Add to Bot Execution

Edit `/opt/homelab-panel/trading-lab/core/execution/executor.py`:

```python
from core.common.notifications import notify_trade_opened, notify_trade_closed

class Executor:
    def execute_trade(self, intent):
        # ... existing trade execution ...
        
        # Send notification on trade open
        if trade_opened:
            notify_trade_opened({
                'symbol': intent.symbol,
                'side': intent.side,
                'qty': intent.qty,
                'entry_price': fill_price,
                'bot_id': self.bot_id,
                'strategy_id': intent.strategy_id
            })
    
    def close_trade(self, trade):
        # ... existing close logic ...
        
        # Send notification on trade close
        if trade_closed:
            notify_trade_closed({
                'symbol': trade.symbol,
                'side': trade.side,
                'entry_price': trade.entry_price,
                'exit_price': trade.exit_price,
                'realized_pnl': trade.realized_pnl,
                'bot_id': self.bot_id
            })
```

### Add Daily Summary Cron

```bash
# Edit crontab
crontab -e

# Add this line (runs at 5 PM daily)
0 17 * * * cd /opt/homelab-panel/trading-lab && python3 scripts/send_daily_summary.py
```

Create `/opt/homelab-panel/trading-lab/scripts/send_daily_summary.py`:

```python
#!/usr/bin/env python3
import sys
from pathlib import Path
from datetime import datetime
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.common.notifications import notify_daily_summary
from core.data.db import Database

db = Database(Path("data/market.db"))

# Query today's stats
today = datetime.now().strftime('%Y-%m-%d')
stats = db.query("""
    SELECT 
        COUNT(*) as total_trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        SUM(CASE WHEN realized_pnl <= 0 THEN 1 ELSE 0 END) as losses,
        ROUND(SUM(realized_pnl), 2) as total_pnl
    FROM trades
    WHERE DATE(ts_open) = ? AND status = 'closed'
""", (today,))[0]

notify_daily_summary({
    'date': today,
    'total_trades': stats['total_trades'],
    'wins': stats['wins'],
    'losses': stats['losses'],
    'total_pnl': stats['total_pnl']
})
```

### Add Risk Alert Triggers

Edit `/opt/homelab-panel/trading-lab/core/execution/risk_manager.py`:

```python
from core.common.notifications import notify_risk_alert

class RiskManager:
    def check_daily_trade_limit(self):
        if self.trades_today >= self.max_trades_per_day:
            # Send notification
            notify_risk_alert({
                'type': 'MAX_TRADES_PER_DAY',
                'message': f'Daily trade limit reached for {self.bot_id}',
                'current_value': self.trades_today,
                'limit': self.max_trades_per_day
            })
            return False
        return True
```

## Email vs Telegram/WhatsApp

### ✅ Why Email is Perfect for Your Use Case:

1. **Already Set Up** - msmtp working, no additional API keys needed
2. **Rich Formatting** - HTML emails look beautiful with charts/tables
3. **Persistent** - Searchable history in Gmail
4. **Reliable** - No rate limits, no API downtime
5. **Professional** - Looks like a trading platform email

### When to Consider Telegram/WhatsApp:

- Real-time alerts needed (< 5 second latency)
- Mobile push notifications critical
- Want to reply to bot with commands
- Multiple users need alerts

### Quick Telegram Setup (Optional)

If you want instant mobile notifications:

1. Create bot: Talk to @BotFather on Telegram
2. Get chat ID: `/getUpdates` after sending bot a message
3. Add to notifications.py:

```python
import requests

TELEGRAM_BOT_TOKEN = "your_bot_token"
TELEGRAM_CHAT_ID = "your_chat_id"

def notify_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    requests.post(url, data=data)
```

## Configuration

Edit `/opt/homelab-panel/trading-lab/core/common/notifications.py`:

```python
# Change recipient
EMAIL_TO = "your_other_email@gmail.com"

# Filter notifications (only send on big wins/losses)
MIN_PNL_FOR_ALERT = 5.00  # Only notify if P&L > $5

# Quiet hours (no alerts 11 PM - 7 AM)
QUIET_HOURS = (23, 7)
```

## Monitoring

View sent emails:

```bash
# Check msmtp logs
tail -f /var/log/syslog | grep msmtp

# Test email delivery
echo "Test" | msmtp -a default user@example.com
```

## Next Steps

1. **Test notifications** - Run the test script
2. **Integrate with executor** - Add to trade execution flow
3. **Schedule daily summary** - Add cron job
4. **Customize templates** - Edit HTML in notifications.py
5. **(Optional) Add Telegram** - If you need mobile push

---

**Recommendation:** Stick with email for now. It's already working, looks professional, and provides good visibility. Add Telegram later only if you need instant mobile alerts.
