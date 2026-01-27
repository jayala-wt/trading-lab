#!/usr/bin/env python3
"""
Historical Replay - Simple version that works with existing infrastructure

Concept: Download historical bars, run them through compute_dimensions + 
evaluate_all_patterns, label outcomes, save to ml_training_samples.

Usage:
    python3 scripts/historical_replay_simple.py BTC/USD 7
"""
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import time
from datetime import datetime, timedelta
from typing import Dict, List, Any
import json

# Existing infrastructure
from core.common.env import load_dotenv
from core.common.paths import repo_root
from core.data.providers import AlpacaConfig, AlpacaMarketDataProvider
from core.data.db import Database
from core.patterns.dimensions import compute_dimensions
from core.patterns.dimension_patterns import evaluate_all_patterns


def get_alpaca_provider(market: str = "crypto"):
    """Get Alpaca data provider from environment variables.
    
    Args:
        market: "crypto" or "stocks"
    """
    # Load environment variables
    load_dotenv(repo_root() / ".env")
    
    api_key = os.getenv("ALPACA_API_KEY", "")
    api_secret = os.getenv("ALPACA_API_SECRET", "")
    
    if not api_key or not api_secret:
        print("❌ Set ALPACA_API_KEY and ALPACA_API_SECRET environment variables")
        sys.exit(1)
    
    config = AlpacaConfig(
        api_key=api_key,
        api_secret=api_secret,
        trading_base_url="https://paper-api.alpaca.markets",
        data_base_url=os.getenv("ALPACA_DATA_URL", "https://data.alpaca.markets"),
        market=market,
    )
    
    return AlpacaMarketDataProvider(config)


def download_bars(provider, symbol: str, days: int) -> Dict[str, List[Dict]]:
    """Download historical bars for symbol."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    print(f"📥 Downloading {days} days of {symbol} bars...")
   
    start_str = start_date.isoformat() + "Z"
    end_str = end_date.isoformat() + "Z"
    
    result = provider.get_bars(
        symbols=[symbol],
        timeframe="1Min",
        start=start_str,
        end=end_str,
        limit=None,
    )
    
    return result


def label_outcome(bars: List[Dict], current_idx: int) -> Dict[str, float]:
    """Label outcomes 5m, 15m, 60m after this bar."""
    if current_idx >= len(bars):
        return {}
    
    entry_price = float(bars[current_idx].get("c") or bars[current_idx]["close"])
    
    outcomes = {"entry_price": entry_price}
    
    # 5 min = 5 bars ahead
    if current_idx + 5 < len(bars):
        price_5m = float(bars[current_idx + 5].get("c") or bars[current_idx + 5]["close"])
        outcomes["outcome_5m"] = ((price_5m - entry_price) / entry_price) * 100
    
    # 15 min = 15 bars ahead
    if current_idx + 15 < len(bars):
        price_15m = float(bars[current_idx + 15].get("c") or bars[current_idx + 15]["close"])
        outcomes["outcome_15m"] = ((price_15m - entry_price) / entry_price) * 100
    
    # 60 min = 60 bars ahead
    if current_idx + 60 < len(bars):
        price_60m = float(bars[current_idx + 60].get("c") or bars[current_idx + 60]["close"])
        outcomes["outcome_60m"] = ((price_60m - entry_price) / entry_price) * 100
    
    # Max drawdown/favorable in next 60 bars
    future_window = bars[current_idx:current_idx + 61]
    lows = [float(b.get("l") or b.get("low", entry_price)) for b in future_window]
    highs = [float(b.get("h") or b.get("high", entry_price)) for b in future_window]
    
    if lows:
        min_price = min(lows)
        outcomes["max_drawdown"] = ((min_price - entry_price) / entry_price) * 100
    
    if highs:
        max_price = max(highs)
        outcomes["max_favorable"] = ((max_price - entry_price) / entry_price) * 100
    
    return outcomes


def classify_quality(outcomes: Dict[str, float]) -> str:
    """Classify trade quality: crash, profitable, losing, normal."""
    outcome_5m = outcomes.get("outcome_5m")
    max_dd = outcomes.get("max_drawdown")
    
    if outcome_5m is None:
        return "unknown"
    
    # Crash: fast drop or big drawdown
    if outcome_5m <= -3.0 or (max_dd and max_dd <= -5.0):
        return "crash"
    
    # Profitable: gain with small drawdown
    if outcome_5m >= 2.0 and (not max_dd or max_dd >= -1.0):
        return "profitable"
    
    # Losing
    if outcome_5m <= -1.0 or (max_dd and max_dd <= -3.0):
        return "losing"
    
    return "normal"


def save_training_sample(db: Database, symbol: str, snapshot: Dict[str, Any], 
                         pattern_result: Any, outcomes: Dict[str, float], dry_run: bool = False):
    """Save training sample to ml_training_samples table."""
    
    quality = classify_quality(outcomes)
    
    if dry_run:
        print(f"  [DRY RUN] {symbol} {pattern_result.pattern_id} {pattern_result.direction} → " +
              f"{outcomes.get('outcome_5m', 0):.2f}% (quality: {quality})")
        return
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    # Extract dimension states
    dim_states = snapshot.get("dimension_states", {})
    
    cursor.execute("""
        INSERT INTO ml_training_samples (
            symbol, created_at, pattern_id, direction, confidence,
            dimension_snapshot,
            dim_momentum, dim_trend, dim_volatility,
            raw_rsi, raw_stoch_k, raw_macd_histogram,
            raw_ema_9, raw_ema_21, raw_ema_50, raw_slope_20,
            raw_atr_pct, raw_bb_bandwidth, raw_bb_pct,
            raw_volume_ratio, raw_vwap_distance_pct,
            entry_price, outcome_5m, outcome_15m, outcome_60m,
            max_drawdown, max_favorable,
            label_profitable_5m, label_profitable_15m, label_quality,
            data_source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        symbol,
        snapshot.get("timestamp", datetime.now().isoformat()),
        pattern_result.pattern_id,
        pattern_result.direction,
        pattern_result.confidence,
        json.dumps(dim_states),
        dim_states.get("momentum", "unknown"),
        dim_states.get("trend", "unknown"),
        dim_states.get("volatility", "unknown"),
        snapshot.get("raw_rsi", 50),
        snapshot.get("raw_stoch_k", 50),
        snapshot.get("raw_macd_histogram", 0),
        snapshot.get("raw_ema_9", 0),
        snapshot.get("raw_ema_21", 0),
        snapshot.get("raw_ema_50", 0),
        snapshot.get("raw_slope_20", 0),
        snapshot.get("raw_atr_pct", 0),
        snapshot.get("raw_bb_bandwidth", 0),
        snapshot.get("raw_bb_pct", 50),
        snapshot.get("raw_volume_ratio", 1.0),
        snapshot.get("raw_vwap_distance_pct", 0),
        outcomes.get("entry_price", 0),
        outcomes.get("outcome_5m"),
        outcomes.get("outcome_15m"),
        outcomes.get("outcome_60m"),
        outcomes.get("max_drawdown"),
        outcomes.get("max_favorable"),
        1 if (outcomes.get("outcome_5m", 0) > 0) else 0,
        1 if (outcomes.get("outcome_15m", 0) > 0) else 0,
        quality,
        "historical_replay",
    ))
    
    conn.commit()


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 scripts/historical_replay_simple.py SYMBOL DAYS [--dry-run] [--market=crypto|stocks]")
        print("Examples:")
        print("  python3 scripts/historical_replay_simple.py BTC/USD 7")
        print("  python3 scripts/historical_replay_simple.py AAPL 7 --market=stocks")
        sys.exit(1)
    
    symbol = sys.argv[1]
    days = int(sys.argv[2])
    dry_run = "--dry-run" in sys.argv
    
    # Detect market type from arguments or symbol format
    market = "crypto"  # default
    for arg in sys.argv:
        if arg.startswith("--market="):
            market = arg.split("=")[1]
    
    # Auto-detect market from symbol format if not specified
    if "/" in symbol:
        market = "crypto"  # BTC/USD, ETH/USD format
    elif "--market=" not in " ".join(sys.argv):
        market = "stocks"  # AAPL, TSLA format (assume stocks if no slash)
    
    print(f"🔄 HISTORICAL REPLAY: {symbol} for {days} days (market: {market})")
    if dry_run:
        print("⚠️  DRY RUN MODE\n")
    
    # Get provider
    provider = get_alpaca_provider(market)
    db_path = Path(os.getenv("TRADING_LAB_DB_PATH", str(repo_root() / "data" / "market.db")))
    db = Database(db_path)
    
    # Download bars
    start_time = time.time()
    bars_dict = download_bars(provider, symbol, days)
    
    if symbol not in bars_dict or not bars_dict[symbol]:
        print(f"❌ No bars returned for {symbol}")
        sys.exit(1)
    
    bars = bars_dict[symbol]
    print(f"✅ Downloaded {len(bars)} bars\n")
    
    # Process each bar (need windows of bars for compute_dimensions)
    samples_created = 0
    signals_detected = 0
    
    # Use 100-bar rolling window for indicator calculation
    window_size = 100
    
    print(f"🔍 Processing bars with dimension classifier...")
    
    for i in range(window_size, len(bars) - 61):  # Need 61 bars ahead for outcome labeling
        # Get window for this bar
        window = bars[i - window_size:i + 1]
        
        try:
            # Run through dimension classifier (uses existing infrastructure!)
            snapshot = compute_dimensions( window, symbol)
            
            # Run pattern detection (uses existing infrastructure!)
            patterns = evaluate_all_patterns(snapshot)
            
            # Filter to matched patterns only
            matched_patterns = [p for p in patterns if p.matched]
            
            if not matched_patterns:
                continue
            
            signals_detected += len(matched_patterns)
            
            # Label outcomes
            outcomes = label_outcome(bars, i)
            
            if not outcomes.get("outcome_5m"):
                continue  # Not enough future data
            
            # Convert snapshot to dict for storage
            snapshot_dict = snapshot.to_dict() if hasattr(snapshot, 'to_dict') else {}
            
            # Save each matched pattern as training sample
            for pattern in matched_patterns:
                save_training_sample(db, symbol, snapshot_dict, pattern, outcomes, dry_run)
                samples_created += 1
        
        except Exception as e:
            print(f"⚠️  Error processing bar {i}: {e}")
            continue
        
        # Progress every 1000 bars
        if i % 1000 == 0:
            print(f"  Progress: {i}/{len(bars)} bars | {signals_detected} signals | {samples_created} samples")
    
    elapsed = time.time() - start_time
    
    print(f"\n{'='*60}")
    print(f"📊 REPLAY COMPLETE")
    print(f"{'='*60}")
    print(f"Bars processed:   {len(bars):,}")
    print(f"Signals detected: {signals_detected}")
    print(f"Samples created:  {samples_created}")
    print(f"Elapsed time:     {elapsed:.1f}s")
    print(f"{'='*60}\n")
    
    if not dry_run and samples_created > 0:
        print(f"✅ Created {samples_created} new training samples!")
        print(f"\n🤖 Retrain model:")
        print(f"   python3 -m core.ml.crash_predictor_trainer --train\n")


if __name__ == "__main__":
    main()
