"""
Position Manager - Monitors and closes open positions based on exit rules.

Checks:
1. Stop-loss: Close if price drops below entry - stop_loss_pct
2. Take-profit: Close if price rises above entry + take_profit_pct  
3. Time stop: Close if position held longer than time_stop_bars
4. ML Crash Protection: Force-exit if ML model detects high crash risk
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from core.data.db import Database, update_trade_close, log_dev_event
from core.ml.crash_predictor import get_crash_predictor


@dataclass
class PositionExitResult:
    """Result of checking/closing a position."""
    trade_id: int
    symbol: str
    action: str  # "closed" or "held"
    reason: str  # "stop_loss", "take_profit", "time_stop", "holding"
    entry_price: float
    exit_price: Optional[float] = None
    realized_pnl: Optional[float] = None


def get_open_trades(db: Database, bot_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get all open trades, optionally filtered by bot_id."""
    if bot_id:
        rows = db.query(
            """SELECT id, ts_open, bot_id, symbol, side, qty, entry_price, 
                      strategy_id, dimension_snapshot_json
               FROM trades WHERE status = 'open' AND bot_id = ?
               ORDER BY ts_open ASC""",
            (bot_id,)
        )
    else:
        rows = db.query(
            """SELECT id, ts_open, bot_id, symbol, side, qty, entry_price,
                      strategy_id, dimension_snapshot_json
               FROM trades WHERE status = 'open'
               ORDER BY ts_open ASC"""
        )
    return [dict(row) for row in rows]


def get_strategy_exit_rules(db: Database, strategy_id: str) -> Dict[str, Any]:
    """Get exit rules for a strategy from registry or defaults."""
    # Default exit rules
    defaults = {
        "stop_loss_pct": 1.5,      # 1.5% stop loss
        "take_profit_pct": 3.0,    # 3% take profit
        "time_stop_minutes": 240,  # 4 hours max hold time
    }
    
    # TODO: Could read from strategy_registry or config
    # For now, use reasonable defaults
    return defaults


def check_position_exit(
    trade: Dict[str, Any],
    current_price: float,
    exit_rules: Dict[str, Any],
    dimension_snapshot: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str, float]:
    """
    Check if a position should be exited.
    
    Args:
        trade: Trade record with entry details
        current_price: Current market price
        exit_rules: Exit rules (stop loss, take profit, etc.)
        dimension_snapshot: Optional current market dimension snapshot for ML crash detection
    
    Returns:
        (should_exit, reason, pnl)
    """
    entry_price = float(trade["entry_price"])
    side = trade["side"]
    qty = float(trade["qty"])
    
    # Calculate P/L based on side
    if side == "buy":
        pnl = (current_price - entry_price) * qty
        pnl_pct = ((current_price - entry_price) / entry_price) * 100
    else:  # sell/short
        pnl = (entry_price - current_price) * qty
        pnl_pct = ((entry_price - current_price) / entry_price) * 100
    
    stop_loss_pct = exit_rules.get("stop_loss_pct", 1.5)
    take_profit_pct = exit_rules.get("take_profit_pct", 3.0)
    time_stop_minutes = exit_rules.get("time_stop_minutes", 240)
    
    # Calculate time in position
    ts_open = trade["ts_open"]
    if isinstance(ts_open, str):
        # Parse ISO format timestamp
        try:
            open_time = datetime.fromisoformat(ts_open.replace("Z", "+00:00"))
        except:
            open_time = datetime.now(timezone.utc) - timedelta(minutes=1)
    else:
        open_time = ts_open
    
    # Make sure open_time is timezone-aware
    if open_time.tzinfo is None:
        open_time = open_time.replace(tzinfo=timezone.utc)
    
    age_minutes = (datetime.now(timezone.utc) - open_time).total_seconds() / 60
    
    # ML CRASH PROTECTION - Check before standard rules
    if dimension_snapshot:
        crash_predictor = get_crash_predictor()
        if crash_predictor.is_loaded():
            should_exit, reason = crash_predictor.should_force_exit(
                dimension_snapshot,
                symbol=trade.get("symbol", "unknown"),  # Symbol-aware crash detection
                time_in_position_minutes=age_minutes,
                unrealized_pnl_pct=pnl_pct,
            )
            if should_exit:
                return True, f"ml_{reason}", pnl
    
    # Check stop-loss
    if pnl_pct <= -stop_loss_pct:
        return True, "stop_loss", pnl
    
    # Check take-profit
    if pnl_pct >= take_profit_pct:
        return True, "take_profit", pnl
    
    # Check time stop
    if age_minutes >= time_stop_minutes:
        return True, "time_stop", pnl
    
    return False, "holding", pnl


def close_position(
    db: Database,
    trade: Dict[str, Any],
    current_price: float,
    reason: str,
    trading_provider: Optional[Any] = None,
    logger: Optional[logging.Logger] = None,
) -> PositionExitResult:
    """Close a position and record the result."""
    trade_id = trade["id"]
    symbol = trade["symbol"]
    side = trade["side"]
    qty = float(trade["qty"])
    entry_price = float(trade["entry_price"])
    
    # Calculate realized P/L
    if side == "buy":
        realized_pnl = (current_price - entry_price) * qty
    else:
        realized_pnl = (entry_price - current_price) * qty
    
    # Submit close order to provider if available
    if trading_provider:
        try:
            close_side = "sell" if side == "buy" else "buy"
            is_crypto = "/" in symbol
            tif = "gtc" if is_crypto else "day"
            
            payload = {
                "symbol": symbol,
                "qty": qty,
                "side": close_side,
                "type": "market",
                "time_in_force": tif,
            }
            trading_provider.submit_order(payload)
        except Exception as e:
            if logger:
                logger.error(f"Failed to submit close order for {symbol}: {e}")
            log_dev_event(
                db, "ERROR", "close_order_failed",
                f"Failed to close position: {e}",
                {"trade_id": trade_id, "symbol": symbol, "error": str(e)}
            )
    
    # Update trade record
    update_trade_close(db, trade_id, current_price, realized_pnl)
    
    log_dev_event(
        db, "INFO", "position_closed",
        f"Closed {side} {symbol} position: {reason}",
        {
            "trade_id": trade_id,
            "symbol": symbol,
            "side": side,
            "reason": reason,
            "entry_price": entry_price,
            "exit_price": current_price,
            "realized_pnl": realized_pnl,
        }
    )
    
    return PositionExitResult(
        trade_id=trade_id,
        symbol=symbol,
        action="closed",
        reason=reason,
        entry_price=entry_price,
        exit_price=current_price,
        realized_pnl=realized_pnl,
    )


def manage_positions(
    db: Database,
    bot_id: str,
    prices: Dict[str, float],
    dimension_snapshots: Optional[Dict[str, Dict[str, Any]]] = None,
    trading_provider: Optional[Any] = None,
    logger: Optional[logging.Logger] = None,
) -> List[PositionExitResult]:
    """
    Check all open positions for a bot and close any that hit exit rules.
    
    Args:
        db: Database connection
        bot_id: Bot ID to check positions for
        prices: Dict of symbol -> current price
        dimension_snapshots: Optional dict of symbol -> current dimension snapshot (for ML crash detection)
        trading_provider: Optional provider for submitting close orders
        logger: Optional logger
    
    Returns:
        List of PositionExitResult for all positions checked
    """
    results: List[PositionExitResult] = []
    open_trades = get_open_trades(db, bot_id)
    
    for trade in open_trades:
        symbol = trade["symbol"]
        
        if symbol not in prices:
            continue
        
        current_price = prices[symbol]
        strategy_id = trade.get("strategy_id") or "default"
        exit_rules = get_strategy_exit_rules(db, strategy_id)
        
        # Get current dimension snapshot for ML crash detection
        dimension_snapshot = None
        if dimension_snapshots and symbol in dimension_snapshots:
            dimension_snapshot = dimension_snapshots[symbol]
        elif trade.get("dimension_snapshot_json"):
            # Fallback to entry snapshot if current not available
            try:
                dimension_snapshot = json.loads(trade["dimension_snapshot_json"])
            except:
                pass
        
        should_exit, reason, pnl = check_position_exit(
            trade, current_price, exit_rules, dimension_snapshot
        )
        
        if should_exit:
            result = close_position(
                db, trade, current_price, reason,
                trading_provider, logger
            )
            results.append(result)
        else:
            results.append(PositionExitResult(
                trade_id=trade["id"],
                symbol=symbol,
                action="held",
                reason=reason,
                entry_price=float(trade["entry_price"]),
            ))
    
    return results


def get_position_summary(db: Database, bot_id: Optional[str] = None) -> Dict[str, Any]:
    """Get summary statistics for open positions."""
    open_trades = get_open_trades(db, bot_id)
    
    by_symbol: Dict[str, Dict] = {}
    total_qty = 0
    total_notional = 0
    
    for trade in open_trades:
        symbol = trade["symbol"]
        qty = float(trade["qty"])
        entry_price = float(trade["entry_price"])
        notional = qty * entry_price
        
        if symbol not in by_symbol:
            by_symbol[symbol] = {"qty": 0, "notional": 0, "count": 0}
        
        by_symbol[symbol]["qty"] += qty
        by_symbol[symbol]["notional"] += notional
        by_symbol[symbol]["count"] += 1
        
        total_qty += qty
        total_notional += notional
    
    return {
        "total_open_trades": len(open_trades),
        "total_notional": total_notional,
        "by_symbol": by_symbol,
    }
