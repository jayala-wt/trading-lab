"""CLI entry point for the trading-lab scheduler."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core.scheduler.runner import run_bot, run_all


def main() -> int:
    parser = argparse.ArgumentParser(description="Trading Lab Bot Runner")
    parser.add_argument(
        "--bot",
        type=str,
        help="Bot ID (e.g., crypto_24_7) or full config path",
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Full path to bot config YAML",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one cycle and exit",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all bots in configs/bots/",
    )
    
    args = parser.parse_args()
    
    if args.all:
        # Run all bots in the configs/bots/ directory
        configs_dir = Path(__file__).parent.parent.parent / "configs" / "bots"
        config_paths = [
            f"configs/bots/{f.name}"
            for f in configs_dir.glob("*.yaml")
            if f.is_file()
        ]
        if not config_paths:
            print("No bot configs found in configs/bots/")
            return 1
        print(f"Running {len(config_paths)} bots: {config_paths}")
        run_all(config_paths, once=args.once)
        return 0
    
    if args.bot:
        # If it's just a bot ID, construct the full path
        if "/" not in args.bot and not args.bot.endswith(".yaml"):
            config_path = f"configs/bots/{args.bot}.yaml"
        else:
            config_path = args.bot
    elif args.config:
        config_path = args.config
    else:
        parser.print_help()
        return 1
    
    # Verify the config exists
    from core.common.paths import repo_root
    full_path = repo_root() / config_path
    if not full_path.exists():
        print(f"Error: Config not found: {full_path}")
        return 1
    
    print(f"Running bot: {config_path} (once={args.once})")
    run_bot(config_path, once=args.once)
    return 0


if __name__ == "__main__":
    sys.exit(main())
