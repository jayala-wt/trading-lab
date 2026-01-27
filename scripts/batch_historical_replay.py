#!/usr/bin/env python3
"""
Batch Historical Replay - Run replay for ALL trading symbols with rate limiting

This script:
- Reads symbols from bot config files
- Runs 90-day historical replay for each symbol
- Respects Alpaca API rate limits (200 requests/minute)
- Shows progress and can be resumed if interrupted
- Saves progress to avoid re-processing completed symbols

Usage:
    python3 scripts/batch_historical_replay.py
    python3 scripts/batch_historical_replay.py --days 30
    python3 scripts/batch_historical_replay.py --crypto-only
    python3 scripts/batch_historical_replay.py --stocks-only
    python3 scripts/batch_historical_replay.py --dry-run
"""

import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import time
import json
import argparse
from datetime import datetime
from typing import List, Dict, Set

from core.common.env import load_dotenv
from core.common.paths import repo_root
from core.data.db import Database


# All symbols from bot configs
CRYPTO_SYMBOLS = [
    "BTC/USD", "ETH/USD", "SOL/USD", "DOGE/USD", "AVAX/USD", "LINK/USD"
]

STOCK_SYMBOLS = [
    # ETFs (9)
    "SPY", "QQQ", "IWM", "DIA", "XLF", "XLE", "XLV", "ARKK", "VTI",
    
    # Mega Tech (10)
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "ORCL", "CRM", "ADBE",
    
    # Semiconductors (8)
    "AMD", "INTC", "MU", "AVGO", "QCOM", "TSM", "MRVL", "ARM",
    
    # Finance (7)
    "JPM", "GS", "V", "MA", "BAC", "WFC", "SCHW",
    
    # Defense/Military (6)
    "LMT", "RTX", "NOC", "GD", "BA", "LHX",
    
    # Pharma/Healthcare (8)
    "PFE", "JNJ", "MRK", "ABBV", "LLY", "UNH", "BMY", "MRNA",
    
    # Consumer/Entertainment (8)
    "NFLX", "DIS", "NKE", "SBUX", "MCD", "WMT", "TGT", "COST",
    
    # Fintech/Crypto (4)
    "COIN", "SQ", "PYPL", "HOOD",
    
    # Tech Growth/Niche (7)
    "PLTR", "UBER", "ABNB", "SNOW", "NET", "DDOG", "CNXC",
    
    # Energy (3)
    "XOM", "CVX", "OXY",
]


def get_progress_file() -> Path:
    """Get path to progress tracking file."""
    return Path(__file__).parent.parent / "data" / "batch_replay_progress.json"


def load_progress() -> Dict[str, str]:
    """Load completed symbols from progress file.
    
    Returns:
        Dict mapping symbol to completion timestamp
    """
    progress_file = get_progress_file()
    if not progress_file.exists():
        return {}
    
    try:
        with open(progress_file, 'r') as f:
            return json.load(f)
    except Exception:
        return {}


def save_progress(symbol: str, timestamp: str) -> None:
    """Save symbol completion to progress file."""
    progress_file = get_progress_file()
    progress_file.parent.mkdir(parents=True, exist_ok=True)
    
    progress = load_progress()
    progress[symbol] = timestamp
    
    with open(progress_file, 'w') as f:
        json.dump(progress, f, indent=2)


def get_symbol_sample_count(db: Database, symbol: str) -> int:
    """Get count of training samples for a symbol."""
    query = "SELECT COUNT(*) as count FROM ml_training_samples WHERE symbol = ?"
    rows = db.query(query, (symbol,))
    return rows[0]['count'] if rows else 0


def run_historical_replay(symbol: str, days: int, dry_run: bool = False) -> Dict[str, any]:
    """Run historical replay for a single symbol.
    
    Returns:
        Dict with status, samples_created, errors
    """
    import subprocess
    
    # Detect market type
    market = "crypto" if "/" in symbol else "stocks"
    
    # Run script as subprocess
    cmd = [
        sys.executable,
        str(Path(__file__).parent / "historical_replay_simple.py"),
        symbol,
        str(days),
        f"--market={market}"
    ]
    
    if dry_run:
        cmd.append("--dry-run")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout per symbol
        )
        
        # Parse output for sample count
        samples_created = 0
        for line in result.stdout.split('\n'):
            if 'Created' in line and 'training samples' in line:
                try:
                    samples_created = int(line.split()[1])
                except:
                    pass
        
        return {
            'status': 'success' if result.returncode == 0 else 'error',
            'samples_created': samples_created,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'returncode': result.returncode
        }
    
    except subprocess.TimeoutExpired:
        return {
            'status': 'timeout',
            'samples_created': 0,
            'error': 'Timed out after 10 minutes'
        }
    except Exception as e:
        return {
            'status': 'error',
            'samples_created': 0,
            'error': str(e)
        }


def estimate_time(total_symbols: int, days: int) -> str:
    """Estimate total processing time.
    
    Alpaca free tier: 200 requests/minute
    For 90 days: ~10,000 bars per symbol
    Download time: ~3-5 seconds per symbol
    Processing time: ~130 bars/second = ~77 seconds per symbol
    Rate limit safety: 10 second delay between symbols
    
    Total per symbol: ~90 seconds (1.5 minutes)
    """
    seconds_per_symbol = 90
    total_seconds = total_symbols * seconds_per_symbol
    
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    
    if hours > 0:
        return f"{hours}h {minutes}m"
    else:
        return f"{minutes}m"


def main():
    parser = argparse.ArgumentParser(description='Batch Historical Replay for All Symbols')
    parser.add_argument('--days', type=int, default=90, help='Days to replay (default: 90)')
    parser.add_argument('--crypto-only', action='store_true', help='Only process crypto symbols')
    parser.add_argument('--stocks-only', action='store_true', help='Only process stock symbols')
    parser.add_argument('--dry-run', action='store_true', help='Dry run mode')
    parser.add_argument('--resume', action='store_true', help='Skip already completed symbols')
    parser.add_argument('--rate-limit-delay', type=int, default=10, help='Seconds between symbols (default: 10)')
    
    args = parser.parse_args()
    
    # Load environment variables
    load_dotenv(repo_root() / ".env")
    
    # Build symbol list
    symbols = []
    if args.crypto_only:
        symbols = CRYPTO_SYMBOLS
    elif args.stocks_only:
        symbols = STOCK_SYMBOLS
    else:
        symbols = CRYPTO_SYMBOLS + STOCK_SYMBOLS
    
    # Load progress
    progress = load_progress()
    if args.resume:
        completed = set(progress.keys())
        symbols = [s for s in symbols if s not in completed]
        print(f"📋 Resuming: {len(completed)} already completed, {len(symbols)} remaining")
    else:
        print(f"📋 Starting fresh batch replay for {len(symbols)} symbols")
    
    if not symbols:
        print("✅ All symbols already completed!")
        return
    
    # Show estimate
    estimated_time = estimate_time(len(symbols), args.days)
    print(f"⏱️  Estimated time: {estimated_time}")
    print(f"📅 Replay window: {args.days} days")
    print(f"⏸️  Rate limit delay: {args.rate_limit_delay} seconds between symbols")
    
    if args.dry_run:
        print("⚠️  DRY RUN MODE - no data will be saved")
    
    print("\n" + "="*80)
    
    # Initialize database
    db_path = Path(os.getenv("TRADING_LAB_DB_PATH", str(repo_root() / "data" / "market.db")))
    db = Database(db_path)
    
    # Track stats
    stats = {
        'total': len(symbols),
        'success': 0,
        'errors': 0,
        'timeouts': 0,
        'total_samples': 0,
        'start_time': time.time()
    }
    
    # Process each symbol
    for idx, symbol in enumerate(symbols, 1):
        print(f"\n[{idx}/{len(symbols)}] Processing {symbol}...")
        
        # Get current sample count (before replay)
        samples_before = get_symbol_sample_count(db, symbol)
        
        # Run replay
        start = time.time()
        result = run_historical_replay(symbol, args.days, args.dry_run)
        elapsed = time.time() - start
        
        # Get new sample count (after replay)
        samples_after = get_symbol_sample_count(db, symbol)
        samples_created = samples_after - samples_before
        
        # Update stats
        if result['status'] == 'success':
            stats['success'] += 1
            stats['total_samples'] += samples_created
            
            # Save progress
            if not args.dry_run:
                save_progress(symbol, datetime.now().isoformat())
            
            print(f"  ✅ Success: {samples_created} samples created in {elapsed:.1f}s")
            print(f"  📊 Total samples for {symbol}: {samples_after}")
        
        elif result['status'] == 'timeout':
            stats['timeouts'] += 1
            print(f"  ⏱️  Timeout: {result.get('error', 'Unknown timeout')}")
        
        else:
            stats['errors'] += 1
            print(f"  ❌ Error: {result.get('error', 'Unknown error')}")
            if result.get('stderr'):
                print(f"  stderr: {result['stderr'][:200]}")
        
        # Show progress
        progress_pct = (idx / len(symbols)) * 100
        elapsed_total = time.time() - stats['start_time']
        remaining = len(symbols) - idx
        eta_seconds = (elapsed_total / idx) * remaining if idx > 0 else 0
        eta_minutes = eta_seconds / 60
        
        print(f"  📈 Progress: {progress_pct:.1f}% | ETA: {eta_minutes:.1f}m | Samples: {stats['total_samples']}")
        
        # Rate limiting delay (except after last symbol)
        if idx < len(symbols):
            print(f"  ⏸️  Rate limit delay: {args.rate_limit_delay}s...")
            time.sleep(args.rate_limit_delay)
    
    # Final summary
    print("\n" + "="*80)
    print("📊 BATCH REPLAY COMPLETE\n")
    print(f"Total symbols:      {stats['total']}")
    print(f"✅ Successful:      {stats['success']}")
    print(f"❌ Errors:          {stats['errors']}")
    print(f"⏱️  Timeouts:        {stats['timeouts']}")
    print(f"📦 Total samples:   {stats['total_samples']}")
    
    elapsed_total = time.time() - stats['start_time']
    print(f"⏰ Total time:      {elapsed_total/60:.1f} minutes")
    
    if stats['total_samples'] > 0:
        avg_per_symbol = stats['total_samples'] / stats['success'] if stats['success'] > 0 else 0
        print(f"📊 Avg per symbol:  {avg_per_symbol:.0f} samples")
    
    # Show sample quality distribution
    if not args.dry_run and stats['total_samples'] > 0:
        print("\n📊 Sample Quality Breakdown:")
        quality_query = """
            SELECT label_quality, COUNT(*) as count 
            FROM ml_training_samples 
            GROUP BY label_quality 
            ORDER BY count DESC
        """
        quality_rows = db.query(quality_query)
        for row in quality_rows:
            print(f"  {row['label_quality']:>10}: {row['count']:>6} samples")
    
    print("\n💡 Next Steps:")
    print("1. Train crash predictor: python3 -m core.ml.crash_predictor_trainer --train")
    print("2. Evaluate model: python3 tests/test_crash_predictor.py")
    print("3. Create quarterly snapshot: python3 scripts/create_quarterly_snapshot.py")


if __name__ == "__main__":
    main()
