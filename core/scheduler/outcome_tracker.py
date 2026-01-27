"""
Outcome Tracker - Computes outcomes for signals to enable ML training.

This runs periodically (e.g., every 15 minutes) to:
1. Find signals that are at least 60 minutes old
2. Fetch price data from signal time to now
3. Compute outcomes: ret_5m, ret_15m, ret_60m, max_drawdown, max_favorable
4. Update the signal record with outcomes

These outcomes become the LABELS for ML training:
- Input: dimension snapshot (features)
- Output: outcome_60m, max_drawdown (labels)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.common.env import load_dotenv
from core.common.paths import repo_root
from core.data.db import (
    Database,
    apply_migrations,
    get_signals_pending_outcome,
    update_signal_outcomes,
    log_dev_event,
)
from core.data.providers import AlpacaConfig, AlpacaMarketDataProvider


def _env(key: str, default: str) -> str:
    import os
    return os.getenv(key, default)


@dataclass
class OutcomeResult:
    """Computed outcomes for a signal."""
    signal_id: int
    outcome_5m: Optional[float]
    outcome_15m: Optional[float]
    outcome_60m: Optional[float]
    max_drawdown: Optional[float]
    max_favorable: Optional[float]
    success: bool
    error: Optional[str] = None


def compute_outcome_from_bars(
    entry_price: float,
    bars: List[Dict[str, Any]],
    direction: str = "buy",
) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float], Optional[float]]:
    """
    Compute outcomes from price bars after signal.
    
    Returns: (ret_5m, ret_15m, ret_60m, max_drawdown, max_favorable)
    
    For BUY signals:
    - Positive return = price went up (good)
    - Drawdown = max price drop from entry
    - Favorable = max price rise from entry
    
    For SELL signals:
    - Positive return = price went down (good for short)
    - Drawdown = max price rise from entry
    - Favorable = max price drop from entry
    """
    if not bars or entry_price <= 0:
        return None, None, None, None, None
    
    # Extract close prices
    closes = [float(bar.get("c") or bar.get("close") or 0) for bar in bars]
    highs = [float(bar.get("h") or bar.get("high") or 0) for bar in bars]
    lows = [float(bar.get("l") or bar.get("low") or 0) for bar in bars]
    
    if not closes or all(c == 0 for c in closes):
        return None, None, None, None, None
    
    # Compute returns at different horizons
    def pct_return(price: float) -> float:
        return ((price - entry_price) / entry_price) * 100
    
    # 5m = 1 bar (if 5m timeframe)
    ret_5m = pct_return(closes[0]) if len(closes) >= 1 else None
    
    # 15m = 3 bars
    ret_15m = pct_return(closes[2]) if len(closes) >= 3 else None
    
    # 60m = 12 bars
    ret_60m = pct_return(closes[11]) if len(closes) >= 12 else pct_return(closes[-1])
    
    # Max adverse and favorable moves
    if direction == "buy":
        # For long: drawdown is how much price dropped, favorable is how much it rose
        max_drawdown = min(pct_return(l) for l in lows) if lows else 0
        max_favorable = max(pct_return(h) for h in highs) if highs else 0
    else:
        # For short: drawdown is how much price rose (bad), favorable is how much it dropped (good)
        max_drawdown = max(pct_return(h) for h in highs) if highs else 0
        max_favorable = min(pct_return(l) for l in lows) if lows else 0
    
    return ret_5m, ret_15m, ret_60m, max_drawdown, max_favorable


def track_signal_outcome(
    signal: Any,
    data_provider: AlpacaMarketDataProvider,
) -> OutcomeResult:
    """
    Track outcome for a single signal.
    
    Fetches bars from signal time + 5min to signal time + 65min.
    Direction-aware: outcomes are computed relative to signal direction.
    """
    import json
    
    signal_id = signal["id"]
    symbol = signal["symbol"]
    entry_price = signal["entry_price"]
    signal_ts = signal["ts"]
    
    # Extract direction from tags (critical for symmetric ML labels)
    # Use bracket notation - sqlite3.Row doesn't support .get()
    tags_json = signal["tags_json"] if signal["tags_json"] else "{}"
    try:
        tags = json.loads(tags_json) if isinstance(tags_json, str) else (tags_json or {})
    except:
        tags = {}
    
    # Get direction: buy/sell/neutral. Treat neutral as buy for outcome math
    direction = tags.get("direction", "buy")
    if direction == "neutral":
        direction = "buy"  # Default to buy-side math for neutral signals
    
    try:
        # Parse signal timestamp
        signal_time = datetime.fromisoformat(signal_ts.replace("Z", "+00:00"))
        
        # Fetch bars for 65 minutes after signal
        start_time = signal_time + timedelta(minutes=5)
        end_time = signal_time + timedelta(minutes=70)
        
        bars_dict = data_provider.get_bars(
            symbols=[symbol],
            timeframe="5m",
            start=start_time.isoformat(),
            end=end_time.isoformat(),
            limit=15,
        )
        
        bars = bars_dict.get(symbol, [])
        
        if not bars:
            return OutcomeResult(
                signal_id=signal_id,
                outcome_5m=None,
                outcome_15m=None,
                outcome_60m=None,
                max_drawdown=None,
                max_favorable=None,
                success=False,
                error="No bars fetched for outcome period",
            )
        
        # Use direction from signal tags (direction-aware outcomes per audit)
        ret_5m, ret_15m, ret_60m, max_dd, max_fav = compute_outcome_from_bars(
            entry_price, bars, direction
        )
        
        return OutcomeResult(
            signal_id=signal_id,
            outcome_5m=ret_5m,
            outcome_15m=ret_15m,
            outcome_60m=ret_60m,
            max_drawdown=max_dd,
            max_favorable=max_fav,
            success=True,
        )
        
    except Exception as exc:
        return OutcomeResult(
            signal_id=signal_id,
            outcome_5m=None,
            outcome_15m=None,
            outcome_60m=None,
            max_drawdown=None,
            max_favorable=None,
            success=False,
            error=str(exc),
        )


def run_outcome_tracker(db: Database, data_provider: AlpacaMarketDataProvider, logger: logging.Logger) -> Dict[str, Any]:
    """
    Main entry point: track outcomes for all pending signals.
    
    Returns summary of tracking run.
    """
    from core.data.db import sync_signals_to_ml_table
    
    pending = get_signals_pending_outcome(db, max_age_minutes=180)
    
    results = {
        "total_pending": len(pending),
        "tracked_ok": 0,
        "tracked_failed": 0,
        "ml_synced": 0,
        "errors": [],
    }
    
    for signal in pending:
        outcome = track_signal_outcome(signal, data_provider)
        
        if outcome.success:
            update_signal_outcomes(
                db=db,
                signal_id=outcome.signal_id,
                outcome_5m=outcome.outcome_5m,
                outcome_15m=outcome.outcome_15m,
                outcome_60m=outcome.outcome_60m,
                max_drawdown=outcome.max_drawdown,
                max_favorable=outcome.max_favorable,
            )
            results["tracked_ok"] += 1
            
            log_dev_event(
                db, "INFO", "outcome_tracked",
                f"Tracked outcome for signal {outcome.signal_id}",
                {
                    "signal_id": outcome.signal_id,
                    "ret_5m": outcome.outcome_5m,
                    "ret_15m": outcome.outcome_15m,
                    "ret_60m": outcome.outcome_60m,
                    "max_dd": outcome.max_drawdown,
                    "max_fav": outcome.max_favorable,
                }
            )
        else:
            results["tracked_failed"] += 1
            results["errors"].append({
                "signal_id": outcome.signal_id,
                "error": outcome.error,
            })
            
            # Mark as tracked anyway to avoid retrying forever
            update_signal_outcomes(
                db=db,
                signal_id=outcome.signal_id,
                outcome_5m=None,
                outcome_15m=None,
                outcome_60m=None,
                max_drawdown=None,
                max_favorable=None,
            )
    
    # Sync all tracked signals to ML training table
    try:
        ml_synced = sync_signals_to_ml_table(db)
        results["ml_synced"] = ml_synced
        if ml_synced > 0:
            log_dev_event(
                db, "INFO", "ml_sync",
                f"Synced {ml_synced} signals to ML training table",
                {"count": ml_synced}
            )
    except Exception as e:
        log_dev_event(db, "ERROR", "ml_sync_error", str(e), {})
    
    return results


def main():
    """Run outcome tracker as standalone script."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Track outcomes for ML training")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--interval", type=int, default=900, help="Interval in seconds (default 15min)")
    args = parser.parse_args()
    
    load_dotenv(repo_root() / ".env")
    
    db_path = Path(_env("TRADING_LAB_DB_PATH", str(repo_root() / "data" / "market.db")))
    db = Database(db_path)
    apply_migrations(db)
    
    api_key = _env("ALPACA_API_KEY", "")
    api_secret = _env("ALPACA_API_SECRET", "") or _env("ALPACA_SECRET_KEY", "")
    data_url = _env("ALPACA_DATA_URL", "https://data.alpaca.markets")
    
    config = AlpacaConfig(
        api_key=api_key,
        api_secret=api_secret,
        trading_base_url="https://paper-api.alpaca.markets",
        data_base_url=data_url,
        market="crypto",
    )
    data_provider = AlpacaMarketDataProvider(config)
    
    # Simple logger
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
    logger = logging.getLogger("outcome-tracker")
    
    import time
    
    while True:
        logger.info("Running outcome tracker...")
        results = run_outcome_tracker(db, data_provider, logger)
        logger.info(f"Tracked {results['tracked_ok']}/{results['total_pending']} signals")
        
        if results["errors"]:
            logger.warning(f"Errors: {results['errors'][:5]}")  # Show first 5 errors
        
        if args.once:
            break
        
        logger.info(f"Sleeping for {args.interval} seconds...")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
