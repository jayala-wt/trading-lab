from __future__ import annotations

import argparse

from core.scheduler.runner import run_bot


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, help="Path to bot config YAML")
    parser.add_argument("--once", action="store_true", help="Run a single cycle")
    args = parser.parse_args()
    run_bot(args.config, once=args.once)


if __name__ == "__main__":
    main()
