from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.common.env import load_dotenv
from core.common.jsonlog import get_json_logger, log_with_extra
from core.common.paths import charts_dir, queue_dir, repo_root
from core.config.loader import load_bot_with_risk, load_pattern_config, load_strategy_config
from core.config.models import BotConfig, PatternConfig, RiskDefaults, StrategyConfig
from core.content.queue import write_content_queue
from core.data.db import (
    Database,
    apply_migrations,
    insert_intent,
    insert_signal,
    insert_dimension_signal,
    log_dev_event,
    register_pattern,
    register_strategy,
    update_bot_heartbeat,
    update_bot_last_run,
    upsert_bot,
    update_intent_state,
    update_signal_rejection,
)
from core.data.providers import AlpacaConfig, AlpacaMarketDataProvider, AlpacaTradingProvider, StubMarketDataProvider
from core.execution.executor import ExecutionManager
from core.patterns.engine import detect_pattern
from core.patterns.base import PatternEvent
from core.patterns.dimensions import compute_dimensions, DimensionSnapshot
from core.patterns.dimension_patterns import (
    evaluate_all_patterns as evaluate_dimension_patterns,
    get_best_signal as get_best_dimension_signal,
    DimensionPatternResult,
)
from core.strategies.engine import build_intents
from core.visuals.charts import generate_chart, dated_chart_path
from core.scheduler.outcome_tracker import run_outcome_tracker


@dataclass
class Providers:
    data_provider: object
    trading_provider: Optional[object]
    use_trading_provider: bool


def _env(key: str, default: str) -> str:
    import os

    return os.getenv(key, default)


def _market_open_now(market: str) -> bool:
    if market != "stocks":
        return True
    from datetime import datetime, time as dtime
    try:
        from zoneinfo import ZoneInfo
    except Exception:  # pragma: no cover - fallback
        return True
    now = datetime.now(ZoneInfo("America/New_York"))
    start = dtime(9, 30)
    end = dtime(16, 0)
    return start <= now.time() <= end and now.weekday() < 5


def build_providers(bot: BotConfig) -> Providers:
    api_key = _env("ALPACA_API_KEY", "")
    api_secret = _env("ALPACA_API_SECRET", "") or _env("ALPACA_SECRET_KEY", "")
    data_url = _env("ALPACA_DATA_URL", "https://data.alpaca.markets")
    paper_url = _env("ALPACA_PAPER_TRADING_URL", "https://paper-api.alpaca.markets")
    live_url = _env("ALPACA_LIVE_TRADING_URL", "https://api.alpaca.markets")

    if bot.data.provider != "alpaca" or not api_key or not api_secret:
        return Providers(StubMarketDataProvider(bot.bot.market), None, False)

    trading_base = paper_url if bot.execution.mode == "paper" else live_url
    config = AlpacaConfig(
        api_key=api_key,
        api_secret=api_secret,
        trading_base_url=trading_base,
        data_base_url=data_url,
        market=bot.bot.market,
    )
    data_provider = AlpacaMarketDataProvider(config)
    trading_provider = AlpacaTradingProvider(config) if bot.execution.mode in {"paper", "live"} else None
    use_trading_provider = bot.execution.mode == "paper" and bool(api_key and api_secret)
    if bot.execution.mode == "live":
        use_trading_provider = bool(api_key and api_secret)
    return Providers(data_provider, trading_provider, use_trading_provider)


def _load_patterns(pattern_refs: List[object]) -> List[tuple[PatternConfig, str]]:
    patterns: List[tuple[PatternConfig, str]] = []
    for ref in pattern_refs:
        patterns.append((load_pattern_config(ref.config), ref.config))
    return patterns


def _load_strategies(strategy_refs: List[object]) -> List[tuple[StrategyConfig, str]]:
    strategies: List[tuple[StrategyConfig, str]] = []
    for ref in strategy_refs:
        strategies.append((load_strategy_config(ref.config), ref.config))
    return strategies


def _detect_dimension_patterns(
    bars: List[Dict[str, Any]],
    symbol: str,
    bot_id: str,
    db: Database,
    logger: logging.Logger,
) -> List[PatternEvent]:
    """
    Detect patterns using the new dimension-based system.
    
    Returns PatternEvents for compatibility with the existing strategy engine.
    """
    try:
        # Compute dimension snapshot from bars
        snapshot = compute_dimensions(bars, symbol)
        
        # Evaluate all dimension patterns
        results = evaluate_dimension_patterns(snapshot)
        
        # Get best signal (if any)
        best = get_best_dimension_signal(snapshot)
        
        events: List[PatternEvent] = []
        last_price = float(bars[-1].get("c") or bars[-1].get("close") or 0.0)
        
        for result in results:
            if not result.matched:
                continue
            
            # Convert to PatternEvent for strategy engine compatibility
            direction_score = result.confidence if result.direction == "buy" else -result.confidence
            
            event = PatternEvent(
                pattern_id=result.pattern_id,
                score=direction_score,
                tags={
                    "direction": result.direction,
                    "confidence": result.confidence,
                    "dimension_based": True,
                },
                snapshot={
                    "reason": result.reason,
                    "dimension_states": result.dimension_states,
                },
            )
            events.append(event)
            
            # Insert dimension signal with ML tracking
            insert_dimension_signal(
                db=db,
                bot_id=bot_id,
                symbol=symbol,
                pattern_id=result.pattern_id,
                state="fired",
                score=result.confidence,
                tags={
                    "direction": result.direction,
                    "confidence": result.confidence,
                },
                snapshot={
                    "reason": result.reason,
                    "dimension_states": result.dimension_states,
                },
                dimension_snapshot=snapshot.to_dict(),
                entry_price=last_price,
            )
            
            log_dev_event(
                db, "INFO", "dimension_signal",
                f"Dimension pattern {result.pattern_id} fired for {symbol}",
                {
                    "symbol": symbol,
                    "pattern_id": result.pattern_id,
                    "direction": result.direction,
                    "confidence": result.confidence,
                    "reason": result.reason,
                    "states": result.dimension_states,
                }
            )
        
        # Log the dimension snapshot even if no patterns matched
        if not events:
            log_dev_event(
                db, "DEBUG", "dimension_snapshot",
                f"Dimension analysis for {symbol}: no patterns matched",
                {
                    "symbol": symbol,
                    "states": {
                        "momentum": snapshot.momentum.value,
                        "trend": snapshot.trend.value,
                        "volatility": snapshot.volatility.value,
                        "participation": snapshot.participation.value,
                        "location": snapshot.location.value,
                        "structure": snapshot.structure.value,
                    }
                }
            )
        
        return events
        
    except Exception as exc:
        log_dev_event(
            db, "ERROR", "dimension_error",
            f"Error computing dimensions for {symbol}: {exc}",
            {"symbol": symbol, "error": str(exc)}
        )
        return []


def run_cycle(bot: BotConfig, risk: RiskDefaults, db: Database, logger: logging.Logger) -> None:
    upsert_bot(db, bot.bot.id, "running", None)
    update_bot_heartbeat(db, bot.bot.id)

    providers = build_providers(bot)
    patterns = _load_patterns(bot.pipeline.patterns)
    strategies = _load_strategies(bot.pipeline.strategies)

    # Register YAML-configured patterns
    for pattern, config_path in patterns:
        register_pattern(db, pattern.id, config_path, pattern.implementation, pattern.name, pattern.description)
    for strategy, config_path in strategies:
        register_strategy(db, strategy.id, config_path, strategy.name, strategy.description)
    
    # Register dimension-based patterns
    from core.patterns.dimension_patterns import DIMENSION_PATTERNS
    for dim_pattern in DIMENSION_PATTERNS:
        register_pattern(
            db,
            dim_pattern.pattern_id,
            "core/patterns/dimension_patterns.py",
            "dimension",
            dim_pattern.name,
            dim_pattern.description,
        )

    bars_by_symbol = providers.data_provider.get_bars(
        bot.universe.symbols,
        bot.bot.timeframe,
        limit=bot.data.bars.lookback_bars,
    )

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

    for symbol, bars in bars_by_symbol.items():
        if not bars:
            log_dev_event(db, "WARN", "no_bars", "No bars returned", {"symbol": symbol})
            continue
        symbol_events: List[PatternEvent] = []
        signal_ids_by_pattern: Dict[str, int] = {}  # Track signal IDs for rejection updates
        
        # === NEW: Dimension-based pattern detection ===
        # This runs alongside existing patterns for comparison
        dimension_events = _detect_dimension_patterns(bars, symbol, bot.bot.id, db, logger)
        symbol_events.extend(dimension_events)
        
        # === EXISTING: YAML-configured pattern detection ===
        for pattern, _config_path in patterns:
            events = detect_pattern(pattern, bars)
            for event in events:
                signal_id = insert_signal(
                    db,
                    bot_id=bot.bot.id,
                    symbol=symbol,
                    pattern_id=event.pattern_id,
                    state="fired",
                    score=event.score,
                    tags=event.tags,
                    snapshot=event.snapshot,
                )
                signal_ids_by_pattern[event.pattern_id] = signal_id
                symbol_events.append(event)
                if "signal_fired" in bot.visuals.generate_on:
                    chart_path = dated_chart_path(charts_dir(), bot.bot.id, symbol)
                    generate_chart(bars, chart_path, f"{symbol} {event.pattern_id}")
                    if bot.content.enabled:
                        metadata = {
                            "pattern_id": event.pattern_id,
                            "score": event.score,
                            "tags": event.tags,
                        }
                        write_content_queue(
                            queue_dir(),
                            bot.bot.id,
                            symbol,
                            chart_path,
                            bot.content.caption_templates,
                            metadata,
                        )
        last_price = float(bars[-1].get("c") or bars[-1].get("close") or 0.0)
        
        # Compute dimension snapshot once for ALL strategies to use
        # This ensures every trade has dimension context for ML
        try:
            from core.patterns.dimensions import compute_dimensions
            dim_snapshot = compute_dimensions(bars, symbol)
            current_dimension_snapshot = dim_snapshot.to_dict() if dim_snapshot else None
        except Exception as e:
            current_dimension_snapshot = None
            logger.warning(f"Failed to compute dimension snapshot: {e}")
        
        # === POSITION GUARD: skip all strategies if bot already has an open trade for this symbol ===
        open_positions = db.query(
            "SELECT COUNT(*) AS cnt FROM trades WHERE bot_id=? AND symbol=? AND status='open'",
            (bot.bot.id, symbol),
        )
        if open_positions and open_positions[0]["cnt"] > 0:
            log_dev_event(
                db, "DEBUG", "intent_skipped",
                f"{symbol}: already_open_position ({open_positions[0]['cnt']} open)",
                {"symbol": symbol, "bot_id": bot.bot.id, "open_count": open_positions[0]["cnt"]},
            )
            continue

        for strategy, _config_path in strategies:
            intent_result = build_intents(strategy, symbol_events, last_price=last_price, symbol=symbol)
            
            # === ML DATA: Track rejection reasons for signals that didn't become trades ===
            if intent_result.rejection_reason:
                # Update signals with rejection reason for ML training data when we can
                for pattern_id in intent_result.matched_patterns or []:
                    signal_id = signal_ids_by_pattern.get(pattern_id)
                    if signal_id:
                        # Append strategy rejection info to the signal
                        rejection_info = f"{strategy.id}:{intent_result.rejection_reason}"
                        update_signal_rejection(db, signal_id, rejection_info)

                log_dev_event(
                    db, "DEBUG", "intent_rejected",
                    f"{symbol}/{strategy.id}: {intent_result.rejection_reason}",
                    {
                        "symbol": symbol,
                        "strategy_id": strategy.id,
                        "rejection_reason": intent_result.rejection_reason,
                        "matched_patterns": intent_result.matched_patterns,
                    }
                )
            
            for intent in intent_result.intents:
                # Use the pattern's snapshot if available, otherwise use computed snapshot
                snapshot_to_use = intent.dimension_snapshot or current_dimension_snapshot
                intent_id = insert_intent(
                    db,
                    bot_id=bot.bot.id,
                    symbol=symbol,
                    strategy_id=strategy.id,
                    action=intent.action,
                    qty=intent.qty,
                    side=intent.side,
                    order_type=intent.order_type,
                    state="new",
                    score=intent.score,
                    reason=intent.reason,
                    dimension_snapshot=snapshot_to_use,
                )
                result = executor.submit_intent(
                    symbol=symbol,
                    side=intent.side,
                    qty=intent.qty,
                    price=last_price,
                    order_type=intent.order_type,
                    strategy_id=strategy.id,
                    intent_id=intent_id,
                    dimension_snapshot=snapshot_to_use,
                )
                update_intent_state(db, intent_id, "submitted" if result.accepted else f"rejected:{result.reason}")
                if result.accepted and "trade_open" in bot.visuals.generate_on:
                    chart_path = dated_chart_path(charts_dir(), bot.bot.id, symbol)
                    generate_chart(bars, chart_path, f"{symbol} trade_open")
        update_bot_last_run(db, bot.bot.id)
    
    # === Manage open positions - check stop-loss, take-profit, time stops ===
    try:
        from core.execution.position_manager import manage_positions
        
        # Build prices dict from bars
        prices = {}
        for symbol, bars in bars_by_symbol.items():
            if bars:
                last_price = float(bars[-1].get("c") or bars[-1].get("close") or 0.0)
                if last_price > 0:
                    prices[symbol] = last_price
        
        if prices:
            position_results = manage_positions(
                db=db,
                bot_id=bot.bot.id,
                prices=prices,
                trading_provider=providers.trading_provider if providers.use_trading_provider else None,
                logger=logger,
            )
            closed_count = sum(1 for r in position_results if r.action == "closed")
            if closed_count > 0:
                total_pnl = sum(r.realized_pnl or 0 for r in position_results if r.action == "closed")
                log_dev_event(
                    db, "INFO", "positions_managed",
                    f"Closed {closed_count} positions, P/L: ${total_pnl:.2f}",
                    {"closed": closed_count, "total_pnl": total_pnl}
                )
    except Exception as exc:
        log_dev_event(
            db, "WARN", "position_manager_error",
            f"Position manager error: {exc}",
            {"error": str(exc)}
        )
    
    # === Run outcome tracker to compute returns for mature signals ===
    try:
        outcome_results = run_outcome_tracker(db, providers.data_provider, logger)
        if outcome_results.get("tracked_count", 0) > 0:
            log_dev_event(
                db, "INFO", "outcome_tracker",
                f"Tracked outcomes for {outcome_results['tracked_count']} signals",
                outcome_results
            )
    except Exception as exc:
        log_dev_event(
            db, "WARN", "outcome_tracker_error",
            f"Outcome tracker error: {exc}",
            {"error": str(exc)}
        )


def run_bot(config_path: str, once: bool = False) -> None:
    load_dotenv(repo_root() / ".env")
    db_path = Path(_env("TRADING_LAB_DB_PATH", str(repo_root() / "data" / "market.db")))
    log_path = Path(_env("TRADING_LAB_LOG_PATH", str(repo_root() / "data" / "artifacts" / "reports" / "trading-lab.jsonl")))
    logger = get_json_logger("trading-lab", log_path)

    bot, risk = load_bot_with_risk(config_path)
    db = Database(db_path)
    apply_migrations(db)

    upsert_bot(db, bot.bot.id, "starting", config_path)
    log_dev_event(db, "INFO", "bot_start", f"Bot {bot.bot.id} starting", {"config": config_path})

    interval = bot.data.schedule.interval_seconds
    while True:
        try:
            if not bot.bot.enabled:
                log_dev_event(db, "WARN", "bot_disabled", f"Bot {bot.bot.id} disabled", {})
                return
            if bot.data.schedule.market_hours_only and not _market_open_now(bot.bot.market):
                log_dev_event(db, "INFO", "market_closed", "Market closed; skipping cycle", {"bot": bot.bot.id})
                time.sleep(interval)
                continue
            run_cycle(bot, risk, db, logger)
        except Exception as exc:
            update_bot_last_run(db, bot.bot.id, str(exc))
            log_with_extra(logger, logging.ERROR, "bot_error", {"error": str(exc)})
            log_dev_event(db, "ERROR", "bot_error", str(exc), {"config": config_path})
        if once:
            break
        time.sleep(interval)


def run_all(config_paths: List[str], once: bool = False) -> None:
    if once:
        for config_path in config_paths:
            run_bot(config_path, once=True)
        return
    import threading

    threads: List[threading.Thread] = []
    for config_path in config_paths:
        thread = threading.Thread(target=run_bot, args=(config_path,), kwargs={"once": False}, daemon=True)
        thread.start()
        threads.append(thread)
    for thread in threads:
        thread.join()
