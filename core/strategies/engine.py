from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from core.config.models import StrategyConfig
from core.patterns.base import PatternEvent


# Cache for symbol overrides
_symbol_overrides_cache: Optional[Dict] = None
_symbol_overrides_mtime: float = 0


def load_symbol_overrides() -> Dict:
    """Load symbol-specific strategy overrides from YAML config."""
    global _symbol_overrides_cache, _symbol_overrides_mtime
    
    config_path = Path(__file__).parent.parent.parent / "configs" / "symbol_overrides.yaml"
    
    if not config_path.exists():
        return {}
    
    # Check if file was modified (hot reload)
    current_mtime = config_path.stat().st_mtime
    if _symbol_overrides_cache is not None and current_mtime == _symbol_overrides_mtime:
        return _symbol_overrides_cache
    
    try:
        with open(config_path) as f:
            _symbol_overrides_cache = yaml.safe_load(f) or {}
            _symbol_overrides_mtime = current_mtime
            return _symbol_overrides_cache
    except Exception:
        return {}


def check_direction_filter(
    filter_mode: str,
    side: str,
    dimension_snapshot: Optional[Dict],
) -> bool:
    """Check if trade passes the directional filter.
    
    Args:
        filter_mode: none, require_bullish, require_bearish, prefer_bullish, prefer_bearish
        side: buy or sell
        dimension_snapshot: Current market dimension states
        
    Returns:
        True if trade should proceed, False to skip
    """
    if filter_mode == "none" or not dimension_snapshot:
        return True
    
    # Extract dimension states
    states = dimension_snapshot.get("states", {})
    if not states:
        # Try to get from nested structure
        if "symbol" in dimension_snapshot:
            states = dimension_snapshot.get("states", {})
        else:
            return True  # No state data, allow trade
    
    momentum_bias = states.get("momentum_bias", "neutral")
    trend = states.get("trend", "neutral")
    
    # Determine market direction
    is_bullish = momentum_bias in ("bullish",) or trend in ("up_strong", "up_weak")
    is_bearish = momentum_bias in ("bearish",) or trend in ("down_strong", "down_weak")
    
    if filter_mode == "require_bullish":
        # LONG trades require bullish conditions
        if side == "buy":
            return is_bullish
        return True  # Don't filter shorts
        
    elif filter_mode == "require_bearish":
        # SHORT trades require bearish conditions  
        if side == "sell":
            return is_bearish
        return True  # Don't filter longs
        
    elif filter_mode == "prefer_bullish":
        # Soft filter - warn but allow
        if side == "buy" and not is_bullish:
            return True  # Allow but could log warning
        return True
        
    elif filter_mode == "prefer_bearish":
        # Soft filter - warn but allow
        if side == "sell" and not is_bearish:
            return True  # Allow but could log warning
        return True
    
    return True


@dataclass
class TradeIntent:
    strategy_id: str
    action: str
    side: str
    qty: float
    order_type: str
    score: float
    reason: Dict[str, Any]
    dimension_snapshot: Optional[Dict[str, Any]] = None
    signal_id: Optional[int] = None


@dataclass
class IntentResult:
    """Result of building intents - includes rejection reasons for ML data."""
    intents: List[TradeIntent]
    rejection_reason: Optional[str] = None  # Why no intent was created
    matched_patterns: List[str] = None  # Patterns that matched strategy requirements


def build_intents(
    strategy: StrategyConfig,
    events: List[PatternEvent],
    last_price: Optional[float] = None,
    symbol: Optional[str] = None,
) -> IntentResult:
    """Build trade intents from strategy and pattern events.
    
    Args:
        strategy: Strategy configuration
        events: List of pattern events that fired
        last_price: Current price (needed for fixed_usd size mode)
        symbol: Symbol for symbol-specific overrides
    
    Returns:
        IntentResult with intents list and rejection reason if no intent created
    """
    event_map = {event.pattern_id: event for event in events}
    
    # Check if ANY required pattern is present (OR logic for dimension patterns)
    # For dimension patterns, we want to match if at least one fires
    matched_patterns = [pid for pid in strategy.required_patterns if pid in event_map]
    if not matched_patterns:
        return IntentResult(intents=[], rejection_reason="no_pattern_match", matched_patterns=[])

    side = str(strategy.entry.get("side", "buy"))
    order_type = str(strategy.entry.get("order_type", "market"))
    action = str(strategy.entry.get("action", "open"))
    
    # Handle 'signal' side mode - get direction from pattern event
    if side == "signal":
        # Find a matched pattern with direction in tags
        for pid in matched_patterns:
            event = event_map[pid]
            direction = event.tags.get("direction", "")
            if direction in ("buy", "sell"):
                side = direction
                break
        else:
            # No valid direction found, skip neutral patterns
            return IntentResult(intents=[], rejection_reason="neutral_direction", matched_patterns=matched_patterns)
    
    # Filter out neutral direction patterns if side is still not buy/sell
    if side not in ("buy", "sell"):
        return IntentResult(intents=[], rejection_reason="invalid_side", matched_patterns=matched_patterns)
    
    # Calculate quantity based on size_mode
    size_mode = str(strategy.entry.get("size_mode", "fixed_qty"))
    size_value = float(strategy.entry.get("size_value", 1.0))
    
    if size_mode == "fixed_usd" and last_price and last_price > 0:
        # Convert USD amount to quantity
        qty = size_value / last_price
    elif size_mode == "fixed_qty":
        qty = size_value
    else:
        # Fallback to legacy qty field or default to 1
        qty = float(strategy.entry.get("qty", 1))

    scores = [event_map[pid].score for pid in matched_patterns]
    score = float(sum(scores) / len(scores)) if scores else 0.0
    
    # Apply min_confidence filter if present
    filters = strategy.filters or {}
    min_confidence = float(filters.get("min_confidence", 0))
    if min_confidence > 0:
        # Check if any matched pattern meets confidence threshold
        max_confidence = 0
        for pid in matched_patterns:
            event = event_map[pid]
            confidence = event.tags.get("confidence", 0)
            max_confidence = max(max_confidence, confidence)
            if confidence >= min_confidence:
                break
        else:
            return IntentResult(
                intents=[], 
                rejection_reason=f"low_confidence:{max_confidence:.2f}<{min_confidence}", 
                matched_patterns=matched_patterns
            )

    reason = {
        "patterns": matched_patterns,
        "scores": scores,
    }
    
    # Capture dimension snapshot from the first matched pattern (if available)
    dimension_snapshot = None
    for pid in matched_patterns:
        event = event_map[pid]
        if event.snapshot:
            # snapshot contains dimension states - extract the states dict
            if isinstance(event.snapshot, dict):
                dimension_snapshot = event.snapshot
            elif hasattr(event.snapshot, 'to_dict'):
                dimension_snapshot = event.snapshot.to_dict()
            break
    
    # === SYMBOL-SPECIFIC DIRECTION FILTER ===
    # Check if this symbol/strategy combo has a directional filter
    if symbol:
        overrides = load_symbol_overrides()
        symbols_config = overrides.get("symbols", {})
        symbol_config = symbols_config.get(symbol, {})
        strategy_override = symbol_config.get(strategy.id, {})
        
        if strategy_override:
            # Check if strategy is disabled for this symbol
            if not strategy_override.get("enabled", True):
                return IntentResult(
                    intents=[], 
                    rejection_reason=f"strategy_disabled_for_symbol", 
                    matched_patterns=matched_patterns
                )
            
            # Apply direction filter
            direction_filter = strategy_override.get("direction_filter", "none")
            if direction_filter != "none":
                if not check_direction_filter(direction_filter, side, dimension_snapshot):
                    # Direction filter blocked this trade
                    states = dimension_snapshot.get("states", {}) if dimension_snapshot else {}
                    return IntentResult(
                        intents=[], 
                        rejection_reason=f"direction_filter:{direction_filter}|trend={states.get('trend')}|bias={states.get('momentum_bias')}", 
                        matched_patterns=matched_patterns
                    )
                reason["direction_filter"] = direction_filter
                reason["filter_result"] = "passed"
            
            # Apply symbol-specific min_confidence override
            override_confidence = strategy_override.get("min_confidence")
            if override_confidence is not None:
                max_conf = 0
                for pid in matched_patterns:
                    event = event_map[pid]
                    confidence = event.tags.get("confidence", 0)
                    max_conf = max(max_conf, confidence)
                    if confidence >= override_confidence:
                        break
                else:
                    return IntentResult(
                        intents=[], 
                        rejection_reason=f"symbol_confidence:{max_conf:.2f}<{override_confidence}", 
                        matched_patterns=matched_patterns
                    )
            
            # Apply symbol-specific risk overrides (stored in reason for executor to use)
            override_risk = strategy_override.get("risk", {})
            if override_risk:
                reason["risk_override"] = override_risk
    
    return IntentResult(
        intents=[
            TradeIntent(
                strategy_id=strategy.id,
                action=action,
                side=side,
                qty=qty,
                order_type=order_type,
                score=score,
                reason=reason,
                dimension_snapshot=dimension_snapshot,
            )
        ],
        rejection_reason=None,
        matched_patterns=matched_patterns
    )
