from __future__ import annotations

import argparse
import glob

from core.scheduler.runner import run_all


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--configs", nargs="+", required=True, help="Glob or list of bot configs")
    parser.add_argument("--once", action="store_true", help="Run a single cycle")
    args = parser.parse_args()

    paths = []
    for item in args.configs:
        paths.extend(glob.glob(item))
    run_all(paths, once=args.once)


if __name__ == "__main__":
    main()
