from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from core.common.jsonlog import log_with_extra
from core.config.models import RiskDefaults
from core.data.db import (
    Database,
    insert_trade,
    log_dev_event,
    sum_realized_pnl_today,
    count_trades_today,
)
from core.data.providers import TradingProvider
from core.ml.crash_predictor import get_crash_predictor
from core.ml.buy_entry_classifier import get_buy_entry_classifier


@dataclass
class ExecutionResult:
    accepted: bool
    reason: str
    trade_id: Optional[int] = None


class ExecutionManager:
    def __init__(
        self,
        db: Database,
        bot_id: str,
        mode: str,
        risk: RiskDefaults,
        logger: logging.Logger,
        trading_provider: Optional[TradingProvider] = None,
        use_provider: bool = False,
        gated: bool = True,
    ) -> None:
        self.db = db
        self.bot_id = bot_id
        self.mode = mode
        self.risk = risk
        self.logger = logger
        self.trading_provider = trading_provider
        self.use_provider = use_provider
        self.gated = gated
        self.api_error_count = 0
        self.risk_breach_count = 0
        self.disabled = False

    def _armed(self) -> bool:
        if not self.gated:
            return True
        if not self.risk.arm_required:
            return True
        return str(self._env("TRADING_LAB_ARMED", "0")) in {"1", "true", "TRUE"}

    def _env(self, key: str, default: str) -> str:
        import os

        return os.getenv(key, default)

    def _risk_ok(self, symbol: str, side: str, notional: float, strategy_id: Optional[str] = None) -> Optional[str]:
        if side.lower() == "sell" and not self.risk.allow_short:
            return "shorts_not_allowed"
        # Per-symbol-per-strategy trade limit (most granular for ML data farming)
        if count_trades_today(self.db, self.bot_id, symbol, strategy_id) >= self.risk.max_trades_per_day:
            return "max_trades_per_day"
        daily_pnl = sum_realized_pnl_today(self.db, self.bot_id)
        if daily_pnl <= -abs(self.risk.max_daily_loss_usd):
            return "max_daily_loss"
        if notional > self.risk.max_position_usd:
            return "max_position_usd"
        return None

    def _kill_switch(self) -> bool:
        return self.api_error_count >= self.risk.api_error_kill_switch_threshold or self.risk_breach_count >= self.risk.api_error_kill_switch_threshold

    def submit_intent(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        order_type: str,
        strategy_id: Optional[str] = None,
        intent_id: Optional[int] = None,
        signal_id: Optional[int] = None,
        dimension_snapshot: Optional[Dict[str, Any]] = None,
    ) -> ExecutionResult:
        if self.mode == "off":
            log_dev_event(self.db, "INFO", "execution_skipped", "Execution mode off", {"symbol": symbol})
            return ExecutionResult(False, "mode_off")
        if self.disabled or self._kill_switch():
            self.disabled = True
            log_dev_event(self.db, "ERROR", "execution_disabled", "Kill switch triggered", {"symbol": symbol})
            return ExecutionResult(False, "kill_switch")
        if not self._armed():
            log_dev_event(self.db, "WARN", "execution_blocked", "Execution not armed", {"symbol": symbol})
            return ExecutionResult(False, "not_armed")
        risk_block = self._risk_ok(symbol, side, qty * price, strategy_id)
        if risk_block:
            self.risk_breach_count += 1
            log_dev_event(self.db, "WARN", "execution_blocked", f"Risk blocked: {risk_block}", {"symbol": symbol})
            if self._kill_switch():
                self.disabled = True
                log_dev_event(self.db, "ERROR", "execution_disabled", "Kill switch triggered by risk breaches", {"symbol": symbol})
            return ExecutionResult(False, risk_block)

        # ML Crash Predictor Gate (Model A - Loss Avoidance)
        # Use threshold=0.50 (optimal from Feb 3-6 validation: 65% precision, 89% recall)
        if dimension_snapshot is not None:
            crash_predictor = get_crash_predictor()
            if crash_predictor.is_loaded():
                should_block, crash_prob, ml_reason = crash_predictor.should_block_trade(
                    dimension_snapshot,
                    symbol=symbol,  # Symbol-aware predictions (AVAX more volatile than BTC)
                    threshold=0.50  # Validated optimal threshold
                )
                if should_block:
                    log_dev_event(
                        self.db, "WARN", "ml_crash_block",
                        f"ML model blocked trade: {ml_reason}",
                        {
                            "symbol": symbol,
                            "crash_probability": crash_prob,
                            "threshold": 0.50,
                            "reason": ml_reason,
                            "dimension_states": dimension_snapshot.get("states", {}),
                        }
                    )
                    return ExecutionResult(False, f"ml_crash_risk:{ml_reason}")
                else:
                    # Log predictions for monitoring (even when allowed)
                    log_dev_event(
                        self.db, "DEBUG", "ml_crash_check",
                        f"ML check passed for {symbol}",
                        {
                            "symbol": symbol,
                            "crash_probability": crash_prob,
                            "threshold": 0.50,
                            "decision": "allow",
                        }
                    )

        # ML Buy Entry Classifier Gate (Model B - Entry Timing)
        # Only applies to buy orders. Blocks entries where RSI/BB/Stoch indicate
        # the bot is buying too early before the real reversal bottom.
        if side.lower() == "buy" and dimension_snapshot is not None:
            entry_classifier = get_buy_entry_classifier()
            if entry_classifier.is_loaded():
                allow, good_prob, entry_reason = entry_classifier.should_allow_buy(
                    dimension_snapshot,
                    symbol=symbol,
                )
                if not allow:
                    log_dev_event(
                        self.db, "WARN", "ml_entry_block",
                        f"Buy entry classifier blocked trade: {entry_reason}",
                        {
                            "symbol": symbol,
                            "good_entry_probability": good_prob,
                            "threshold": entry_classifier.optimal_threshold,
                            "reason": entry_reason,
                            "dimension_states": dimension_snapshot.get("states", {}),
                        }
                    )
                    return ExecutionResult(False, f"ml_bad_entry:{entry_reason}")
                else:
                    log_dev_event(
                        self.db, "DEBUG", "ml_entry_check",
                        f"Buy entry classifier passed for {symbol}",
                        {
                            "symbol": symbol,
                            "good_entry_probability": good_prob,
                            "decision": "allow",
                        }
                    )

        if self.use_provider and self.trading_provider:
            try:
                # Crypto uses GTC (good til canceled), stocks use DAY
                is_crypto = "/" in symbol  # BTC/USD, ETH/USD, etc.
                tif = "gtc" if is_crypto else "day"
                
                payload = {
                    "symbol": symbol,
                    "qty": qty,
                    "side": side,
                    "type": order_type,
                    "time_in_force": tif,
                }
                response = self.trading_provider.submit_order(payload)
                trade_id = insert_trade(
                    self.db,
                    bot_id=self.bot_id,
                    symbol=symbol,
                    side=side,
                    qty=qty,
                    entry_price=price,
                    status="open",
                    execution_mode=self.mode,
                    provider_order_id=response.get("id"),
                    strategy_id=strategy_id,
                    intent_id=intent_id,
                    signal_id=signal_id,
                    dimension_snapshot=dimension_snapshot,
                )
                log_with_extra(self.logger, logging.INFO, "order_submitted", {"symbol": symbol, "trade_id": trade_id})
                return ExecutionResult(True, "submitted", trade_id)
            except Exception as exc:
                self.api_error_count += 1
                log_dev_event(self.db, "ERROR", "execution_error", str(exc), {"symbol": symbol})
                return ExecutionResult(False, "provider_error")

        trade_id = insert_trade(
            self.db,
            bot_id=self.bot_id,
            symbol=symbol,
            side=side,
            qty=qty,
            entry_price=price,
            status="open",
            execution_mode=self.mode,
            strategy_id=strategy_id,
            intent_id=intent_id,
            signal_id=signal_id,
            dimension_snapshot=dimension_snapshot,
        )
        log_with_extra(self.logger, logging.INFO, "order_simulated", {"symbol": symbol, "trade_id": trade_id})
        return ExecutionResult(True, "simulated", trade_id)
