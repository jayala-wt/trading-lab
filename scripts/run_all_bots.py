#!/usr/bin/env python3
"""
Run ALL trading bots based on their schedules.

Each bot runs in its own thread:
- crypto bots: 24/7
- stocks bots: market hours only (9:30-4:00 ET)

Usage: python scripts/run_all_bots.py
"""
import sys
import time
import threading
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.scheduler.runner import run_bot


# All bot configs to run
BOT_CONFIGS = [
    "configs/bots/crypto_24_7.yaml",
    "configs/bots/crypto_intraday.yaml",
    "configs/bots/stocks_intraday.yaml",
    "configs/bots/momentum_trader.yaml",
    "configs/bots/swing_master.yaml",
]


def run_bot_thread(config_path: str):
    """Run a single bot in a thread."""
    print(f"[{datetime.now().isoformat()}] Starting bot: {config_path}")
    try:
        run_bot(config_path, once=False)
    except Exception as e:
        print(f"[ERROR] Bot {config_path} failed: {e}")


def main():
    print("=" * 60)
    print("🤖 Trading Lab Multi-Bot Scheduler")
    print("=" * 60)
    print(f"Starting {len(BOT_CONFIGS)} bots...")
    print()
    
    threads = []
    
    for config_path in BOT_CONFIGS:
        config_file = Path(config_path)
        if not config_file.exists():
            print(f"[WARN] Config not found: {config_path}")
            continue
        
        thread = threading.Thread(
            target=run_bot_thread,
            args=(config_path,),
            daemon=True,
            name=config_path.split("/")[-1].replace(".yaml", "")
        )
        thread.start()
        threads.append(thread)
        print(f"  ✓ Started: {config_path}")
        time.sleep(2)  # Stagger starts
    
    print()
    print(f"All {len(threads)} bots running. Press Ctrl+C to stop.")
    print("=" * 60)
    
    try:
        while True:
            time.sleep(60)
            # Print heartbeat
            alive = sum(1 for t in threads if t.is_alive())
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Bots alive: {alive}/{len(threads)}")
    except KeyboardInterrupt:
        print("\nShutting down all bots...")


if __name__ == "__main__":
    main()
