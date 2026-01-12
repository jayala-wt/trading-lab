"""
Trading Bot Notification System
Sends email alerts for important trading events using msmtp
"""
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

MSMTP_BIN = "/usr/bin/msmtp"
EMAIL_TO = "wanatux@gmail.com"


def send_email(subject: str, html_body: str) -> bool:
    """Send HTML email via msmtp"""
    try:
        email_message = f"""Subject: {subject}
From: Trading Lab <{EMAIL_TO}>
To: {EMAIL_TO}
Content-Type: text/html; charset=utf-8

{html_body}"""
        
        result = subprocess.run(
            [MSMTP_BIN, '-a', 'default', EMAIL_TO],
            input=email_message.encode('utf-8'),
            capture_output=True,
            timeout=30
        )
        
        return result.returncode == 0
            
    except Exception as e:
        print(f"❌ Failed to send notification: {e}")
        return False


def notify_trade_opened(trade_data: Dict[str, Any]) -> bool:
    """Send notification when trade is opened"""
    symbol = trade_data.get('symbol', 'UNKNOWN')
    side = trade_data.get('side', 'BUY')
    qty = trade_data.get('qty', 0)
    entry_price = trade_data.get('entry_price', 0)
    bot_id = trade_data.get('bot_id', 'unknown')
    strategy = trade_data.get('strategy_id', 'unknown')
    
    cost = qty * entry_price
    
    emoji = "🟢" if side == "buy" else "🔴"
    
    subject = f"🤖 Trading Alert: {side.upper()} {symbol}"
    
    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #1f2937; color: #fff; padding: 20px; border-radius: 8px; }}
        .trade-info {{ background: #f3f4f6; padding: 20px; margin: 20px 0; border-radius: 8px; }}
        .metric {{ display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #e5e7eb; }}
        .label {{ color: #6b7280; font-weight: bold; }}
        .value {{ color: #111827; }}
        .footer {{ color: #6b7280; font-size: 12px; margin-top: 30px; text-align: center; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{emoji} Trade Opened</h1>
        <p style="margin: 0; opacity: 0.8;">{datetime.now().strftime('%b %d, %Y at %I:%M %p')}</p>
    </div>
    
    <div class="trade-info">
        <h2 style="margin-top: 0;">Trade Details</h2>
        <div class="metric">
            <span class="label">Symbol:</span>
            <span class="value">{symbol}</span>
        </div>
        <div class="metric">
            <span class="label">Side:</span>
            <span class="value" style="color: {'#10b981' if side == 'buy' else '#ef4444'};">{side.upper()}</span>
        </div>
        <div class="metric">
            <span class="label">Quantity:</span>
            <span class="value">{qty}</span>
        </div>
        <div class="metric">
            <span class="label">Entry Price:</span>
            <span class="value">${entry_price:.2f}</span>
        </div>
        <div class="metric">
            <span class="label">Position Size:</span>
            <span class="value">${cost:.2f}</span>
        </div>
        <div class="metric">
            <span class="label">Bot:</span>
            <span class="value">{bot_id}</span>
        </div>
        <div class="metric">
            <span class="label">Strategy:</span>
            <span class="value">{strategy}</span>
        </div>
    </div>
    
    <div class="footer">
        <p>Trading Lab Paper Trading System<br>
        This is a paper trade - no real money involved</p>
    </div>
</body>
</html>
"""
    
    return send_email(subject, html_body)


def notify_trade_closed(trade_data: Dict[str, Any]) -> bool:
    """Send notification when trade is closed"""
    symbol = trade_data.get('symbol', 'UNKNOWN')
    side = trade_data.get('side', 'BUY')
    entry_price = trade_data.get('entry_price', 0)
    exit_price = trade_data.get('exit_price', 0)
    pnl = trade_data.get('realized_pnl', 0)
    bot_id = trade_data.get('bot_id', 'unknown')
    
    pnl_pct = ((exit_price - entry_price) / entry_price * 100) if entry_price else 0
    if side == "sell":
        pnl_pct = -pnl_pct
    
    emoji = "✅" if pnl > 0 else "❌"
    color = "#10b981" if pnl > 0 else "#ef4444"
    
    subject = f"🤖 Trade Closed: {symbol} ({'+' if pnl > 0 else ''}${pnl:.2f})"
    
    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #1f2937; color: #fff; padding: 20px; border-radius: 8px; }}
        .trade-info {{ background: #f3f4f6; padding: 20px; margin: 20px 0; border-radius: 8px; }}
        .metric {{ display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #e5e7eb; }}
        .label {{ color: #6b7280; font-weight: bold; }}
        .value {{ color: #111827; }}
        .pnl-box {{ background: {color}; color: white; padding: 20px; border-radius: 8px; text-align: center; margin: 20px 0; }}
        .footer {{ color: #6b7280; font-size: 12px; margin-top: 30px; text-align: center; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{emoji} Trade Closed</h1>
        <p style="margin: 0; opacity: 0.8;">{datetime.now().strftime('%b %d, %Y at %I:%M %p')}</p>
    </div>
    
    <div class="pnl-box">
        <h2 style="margin: 0; font-size: 48px;">{'+ ' if pnl > 0 else ''}${pnl:.2f}</h2>
        <p style="margin: 10px 0 0; font-size: 24px;">{'+ ' if pnl_pct > 0 else ''}{pnl_pct:.2f}%</p>
    </div>
    
    <div class="trade-info">
        <h2 style="margin-top: 0;">Trade Summary</h2>
        <div class="metric">
            <span class="label">Symbol:</span>
            <span class="value">{symbol}</span>
        </div>
        <div class="metric">
            <span class="label">Entry:</span>
            <span class="value">${entry_price:.2f}</span>
        </div>
        <div class="metric">
            <span class="label">Exit:</span>
            <span class="value">${exit_price:.2f}</span>
        </div>
        <div class="metric">
            <span class="label">Bot:</span>
            <span class="value">{bot_id}</span>
        </div>
    </div>
    
    <div class="footer">
        <p>Trading Lab Paper Trading System<br>
        This is a paper trade - no real money involved</p>
    </div>
</body>
</html>
"""
    
    return send_email(subject, html_body)


def notify_daily_summary(summary_data: Dict[str, Any]) -> bool:
    """Send daily trading summary"""
    date = summary_data.get('date', datetime.now().strftime('%Y-%m-%d'))
    total_trades = summary_data.get('total_trades', 0)
    wins = summary_data.get('wins', 0)
    losses = summary_data.get('losses', 0)
    total_pnl = summary_data.get('total_pnl', 0)
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    
    emoji = "🎉" if total_pnl > 0 else "📊" if total_pnl == 0 else "⚠️"
    
    subject = f"📊 Trading Summary: {date} ({'+' if total_pnl > 0 else ''}${total_pnl:.2f})"
    
    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #1f2937; color: #fff; padding: 20px; border-radius: 8px; }}
        .summary-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin: 20px 0; }}
        .stat-card {{ background: #f3f4f6; padding: 20px; border-radius: 8px; text-align: center; }}
        .stat-value {{ font-size: 32px; font-weight: bold; color: #111827; margin: 10px 0; }}
        .stat-label {{ color: #6b7280; font-size: 14px; }}
        .footer {{ color: #6b7280; font-size: 12px; margin-top: 30px; text-align: center; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{emoji} Daily Trading Summary</h1>
        <p style="margin: 0; opacity: 0.8;">{date}</p>
    </div>
    
    <div class="summary-grid">
        <div class="stat-card">
            <div class="stat-label">Total P&L</div>
            <div class="stat-value" style="color: {'#10b981' if total_pnl > 0 else '#ef4444' if total_pnl < 0 else '#6b7280'};">
                {'+ ' if total_pnl > 0 else ''}${total_pnl:.2f}
            </div>
        </div>
        
        <div class="stat-card">
            <div class="stat-label">Win Rate</div>
            <div class="stat-value">{win_rate:.1f}%</div>
        </div>
        
        <div class="stat-card">
            <div class="stat-label">Winners</div>
            <div class="stat-value" style="color: #10b981;">{wins}</div>
        </div>
        
        <div class="stat-card">
            <div class="stat-label">Losers</div>
            <div class="stat-value" style="color: #ef4444;">{losses}</div>
        </div>
    </div>
    
    <div class="footer">
        <p>Trading Lab Paper Trading System<br>
        <a href="http://localhost:5050/trading-lab/overview">View Dashboard</a></p>
    </div>
</body>
</html>
"""
    
    return send_email(subject, html_body)


def notify_risk_alert(alert_data: Dict[str, Any]) -> bool:
    """Send risk management alert"""
    alert_type = alert_data.get('type', 'UNKNOWN')
    message = alert_data.get('message', 'Risk limit reached')
    current_value = alert_data.get('current_value', 0)
    limit = alert_data.get('limit', 0)
    
    subject = f"⚠️ Trading Risk Alert: {alert_type}"
    
    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #dc2626; color: #fff; padding: 20px; border-radius: 8px; }}
        .alert-box {{ background: #fef2f2; border-left: 4px solid #dc2626; padding: 20px; margin: 20px 0; }}
        .footer {{ color: #6b7280; font-size: 12px; margin-top: 30px; text-align: center; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>⚠️ Risk Alert</h1>
        <p style="margin: 0; opacity: 0.8;">{datetime.now().strftime('%b %d, %Y at %I:%M %p')}</p>
    </div>
    
    <div class="alert-box">
        <h2 style="margin-top: 0; color: #dc2626;">{alert_type}</h2>
        <p style="font-size: 16px; margin: 15px 0;">{message}</p>
        <p style="color: #6b7280;">
            Current: <strong>{current_value}</strong> | Limit: <strong>{limit}</strong>
        </p>
    </div>
    
    <div class="footer">
        <p>Trading Lab Risk Management System<br>
        Review your settings and adjust if needed</p>
    </div>
</body>
</html>
"""
    
    return send_email(subject, html_body)
