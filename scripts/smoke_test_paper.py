from __future__ import annotations

import argparse
import os
from pathlib import Path

from core.common.env import load_dotenv
from core.common.jsonlog import get_json_logger
from core.common.paths import repo_root
from core.config.loader import load_bot_with_risk
from core.data.db import Database, apply_migrations, log_dev_event
from core.execution.executor import ExecutionManager
from core.scheduler.runner import build_providers


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, help="Bot config YAML")
    args = parser.parse_args()

    load_dotenv(repo_root() / ".env")
    if os.getenv("TRADING_LAB_SMOKE_TEST", "0") != "1":
        print("TRADING_LAB_SMOKE_TEST not set. Aborting.")
        return

    bot, risk = load_bot_with_risk(args.config)
    if bot.execution.mode != "paper":
        print("Execution mode is not paper. Aborting.")
        return

    db_path = Path(os.getenv("TRADING_LAB_DB_PATH", str(repo_root() / "data" / "market.db")))
    log_path = Path(os.getenv("TRADING_LAB_LOG_PATH", str(repo_root() / "data" / "artifacts" / "reports" / "trading-lab.jsonl")))

    db = Database(db_path)
    apply_migrations(db)
    logger = get_json_logger("trading-lab", log_path)

    providers = build_providers(bot)
    bars_by_symbol = providers.data_provider.get_bars(bot.universe.symbols, bot.bot.timeframe, limit=50)
    symbol = bot.universe.symbols[0]
    bars = bars_by_symbol.get(symbol, [])
    if not bars:
        print("No bars returned. Aborting.")
        return

    last_price = float(bars[-1].get("c") or bars[-1].get("close") or 0.0)
    executor = ExecutionManager(
        db=db,
        bot_id=bot.bot.id,
        mode=bot.execution.mode,
        risk=risk,
        logger=logger,
        trading_provider=providers.trading_provider,
        use_provider=providers.use_trading_provider,
        gated=bot.execution.gated,
    )
    result = executor.submit_intent(symbol=symbol, side="buy", qty=1, price=last_price, order_type="market")

    log_dev_event(
        db,
        "INFO" if result.accepted else "WARN",
        "smoke_test",
        "Paper smoke test executed",
        {"symbol": symbol, "accepted": result.accepted, "reason": result.reason},
    )
    print(f"Smoke test result: {result.accepted} ({result.reason})")


if __name__ == "__main__":
    main()
