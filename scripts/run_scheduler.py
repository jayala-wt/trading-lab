#!/usr/bin/env python3
"""
Run the trading bot scheduler continuously.
Usage: python scripts/run_scheduler.py [--interval SECONDS] [--config PATH]
"""
import argparse
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.scheduler.runner import run_bot


def main():
    parser = argparse.ArgumentParser(description="Run trading bot scheduler")
    parser.add_argument("--config", default="configs/bots/crypto_24_7.yaml", help="Bot config path")
    parser.add_argument("--interval", type=int, default=300, help="Check interval in seconds (default: 300 = 5 min)")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    args = parser.parse_args()
    
    print(f"Starting scheduler with config: {args.config}")
    print(f"Interval: {args.interval}s, Once: {args.once}")
    
    if args.once:
        run_bot(args.config, once=True)
    else:
        # Run continuously
        while True:
            try:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Running bot cycle...")
                run_bot(args.config, once=True)
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Cycle complete. Sleeping {args.interval}s...")
                time.sleep(args.interval)
            except KeyboardInterrupt:
                print("\nShutting down...")
                break
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(60)  # Wait a bit before retrying


if __name__ == "__main__":
    main()
