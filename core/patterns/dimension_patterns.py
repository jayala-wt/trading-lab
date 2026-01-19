"""
Dimension-Based Patterns - Patterns that consume dimension states.

Instead of:  RSI < 30 AND ATR > 0.02
We write:    momentum == oversold AND volatility == compressed

This is cleaner, more readable, and decouples pattern logic from raw indicators.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple
from enum import Enum

from core.patterns.dimensions import (
    DimensionSnapshot,
    MomentumState, TrendState, VolatilityState,
    ParticipationState, LocationState, StructureState,
)


@dataclass
class DimensionPatternResult:
    """Result of evaluating a dimension-based pattern."""
    pattern_id: str
    name: str
    matched: bool
    direction: str  # "buy" or "sell"
    confidence: float  # 0.0 to 1.0
    dimension_states: Dict[str, str]  # Snapshot of states when matched
    reason: str  # Human-readable explanation


# ============================================================================
# PATTERN DEFINITIONS (Dimension-Based)
# ============================================================================

class DimensionPattern:
    """Base class for dimension patterns."""
    
    def __init__(
        self,
        pattern_id: str,
        name: str,
        direction: str,
        description: str,
    ):
        self.pattern_id = pattern_id
        self.name = name
        self.direction = direction
        self.description = description
    
    def evaluate(self, snapshot: DimensionSnapshot) -> DimensionPatternResult:
        """Evaluate pattern against dimension snapshot. Override in subclasses."""
        raise NotImplementedError


class MomentumReversalBuy(DimensionPattern):
    """
    Buy when momentum is oversold and structure/location support reversal.
    
    Conditions:
    - Momentum: oversold (soft or strong)
    - Location: at_support OR below_vwap
    - Volatility: NOT extreme (we want calmer conditions for reversal)
    """
    
    def __init__(self):
        super().__init__(
            pattern_id="dim_momentum_reversal_buy",
            name="Momentum Reversal (Buy)",
            direction="buy",
            description="Oversold momentum with supportive location",
        )
    
    def evaluate(self, snapshot: DimensionSnapshot) -> DimensionPatternResult:
        states = {
            "momentum": snapshot.momentum.value,
            "trend": snapshot.trend.value,
            "volatility": snapshot.volatility.value,
            "location": snapshot.location.value,
            "structure": snapshot.structure.value,
        }
        
        # Check conditions
        momentum_ok = snapshot.momentum in [MomentumState.OVERSOLD_SOFT, MomentumState.OVERSOLD_STRONG]
        location_ok = snapshot.location in [LocationState.AT_SUPPORT, LocationState.BELOW_VWAP]
        volatility_ok = snapshot.volatility != VolatilityState.EXTREME
        
        matched = momentum_ok and location_ok and volatility_ok
        
        # Calculate confidence based on how many states align
        confidence = 0.0
        reasons = []
        
        if snapshot.momentum == MomentumState.OVERSOLD_STRONG:
            confidence += 0.4
            reasons.append("strongly oversold")
        elif snapshot.momentum == MomentumState.OVERSOLD_SOFT:
            confidence += 0.25
            reasons.append("moderately oversold")
        
        if snapshot.location == LocationState.AT_SUPPORT:
            confidence += 0.3
            reasons.append("at support")
        elif snapshot.location == LocationState.BELOW_VWAP:
            confidence += 0.15
            reasons.append("below VWAP")
        
        if snapshot.volatility == VolatilityState.COMPRESSED:
            confidence += 0.2
            reasons.append("volatility compressed (squeeze forming)")
        elif snapshot.volatility == VolatilityState.NORMAL:
            confidence += 0.1
            reasons.append("normal volatility")
        
        if snapshot.structure == StructureState.HIGHER_HIGHS:
            confidence += 0.1
            reasons.append("bullish structure")
        
        reason = "Momentum reversal BUY: " + ", ".join(reasons) if reasons else "Conditions not met"
        
        return DimensionPatternResult(
            pattern_id=self.pattern_id,
            name=self.name,
            matched=matched,
            direction=self.direction,
            confidence=min(confidence, 1.0),
            dimension_states=states,
            reason=reason,
        )


class MomentumReversalSell(DimensionPattern):
    """
    Sell when momentum is overbought and structure/location support reversal.
    """
    
    def __init__(self):
        super().__init__(
            pattern_id="dim_momentum_reversal_sell",
            name="Momentum Reversal (Sell)",
            direction="sell",
            description="Overbought momentum with resistance location",
        )
    
    def evaluate(self, snapshot: DimensionSnapshot) -> DimensionPatternResult:
        states = {
            "momentum": snapshot.momentum.value,
            "trend": snapshot.trend.value,
            "volatility": snapshot.volatility.value,
            "location": snapshot.location.value,
            "structure": snapshot.structure.value,
        }
        
        momentum_ok = snapshot.momentum in [MomentumState.OVERBOUGHT_SOFT, MomentumState.OVERBOUGHT_STRONG]
        location_ok = snapshot.location in [LocationState.AT_RESISTANCE, LocationState.ABOVE_VWAP]
        volatility_ok = snapshot.volatility != VolatilityState.EXTREME
        
        matched = momentum_ok and location_ok and volatility_ok
        
        confidence = 0.0
        reasons = []
        
        if snapshot.momentum == MomentumState.OVERBOUGHT_STRONG:
            confidence += 0.4
            reasons.append("strongly overbought")
        elif snapshot.momentum == MomentumState.OVERBOUGHT_SOFT:
            confidence += 0.25
            reasons.append("moderately overbought")
        
        if snapshot.location == LocationState.AT_RESISTANCE:
            confidence += 0.3
            reasons.append("at resistance")
        elif snapshot.location == LocationState.ABOVE_VWAP:
            confidence += 0.15
            reasons.append("above VWAP")
        
        if snapshot.volatility == VolatilityState.COMPRESSED:
            confidence += 0.2
            reasons.append("volatility compressed")
        elif snapshot.volatility == VolatilityState.NORMAL:
            confidence += 0.1
            reasons.append("normal volatility")
        
        if snapshot.structure == StructureState.LOWER_LOWS:
            confidence += 0.1
            reasons.append("bearish structure")
        
        reason = "Momentum reversal SELL: " + ", ".join(reasons) if reasons else "Conditions not met"
        
        return DimensionPatternResult(
            pattern_id=self.pattern_id,
            name=self.name,
            matched=matched,
            direction=self.direction,
            confidence=min(confidence, 1.0),
            dimension_states=states,
            reason=reason,
        )


class TrendContinuationBuy(DimensionPattern):
    """
    Buy continuation in uptrend with pullback.
    
    Conditions:
    - Trend: up_strong or up_weak
    - Momentum: neutral or oversold_soft (pullback)
    - Participation: normal or strong
    """
    
    def __init__(self):
        super().__init__(
            pattern_id="dim_trend_continuation_buy",
            name="Trend Continuation (Buy)",
            direction="buy",
            description="Uptrend pullback buy",
        )
    
    def evaluate(self, snapshot: DimensionSnapshot) -> DimensionPatternResult:
        states = {
            "momentum": snapshot.momentum.value,
            "trend": snapshot.trend.value,
            "volatility": snapshot.volatility.value,
            "participation": snapshot.participation.value,
        }
        
        trend_ok = snapshot.trend in [TrendState.UP_STRONG, TrendState.UP_WEAK]
        momentum_ok = snapshot.momentum in [MomentumState.NEUTRAL, MomentumState.OVERSOLD_SOFT]
        participation_ok = snapshot.participation in [ParticipationState.NORMAL, ParticipationState.STRONG]
        volatility_ok = snapshot.volatility != VolatilityState.EXTREME
        
        matched = trend_ok and momentum_ok and participation_ok and volatility_ok
        
        confidence = 0.0
        reasons = []
        
        if snapshot.trend == TrendState.UP_STRONG:
            confidence += 0.35
            reasons.append("strong uptrend")
        elif snapshot.trend == TrendState.UP_WEAK:
            confidence += 0.2
            reasons.append("mild uptrend")
        
        if snapshot.momentum == MomentumState.OVERSOLD_SOFT:
            confidence += 0.25
            reasons.append("pullback detected (oversold soft)")
        elif snapshot.momentum == MomentumState.NEUTRAL:
            confidence += 0.15
            reasons.append("momentum neutral")
        
        if snapshot.participation == ParticipationState.STRONG:
            confidence += 0.2
            reasons.append("strong volume")
        
        if snapshot.volatility == VolatilityState.NORMAL:
            confidence += 0.1
            reasons.append("healthy volatility")
        
        reason = "Trend continuation BUY: " + ", ".join(reasons) if reasons else "Conditions not met"
        
        return DimensionPatternResult(
            pattern_id=self.pattern_id,
            name=self.name,
            matched=matched,
            direction=self.direction,
            confidence=min(confidence, 1.0),
            dimension_states=states,
            reason=reason,
        )


class TrendContinuationSell(DimensionPattern):
    """
    Sell continuation in downtrend with bounce.
    """
    
    def __init__(self):
        super().__init__(
            pattern_id="dim_trend_continuation_sell",
            name="Trend Continuation (Sell)",
            direction="sell",
            description="Downtrend bounce sell",
        )
    
    def evaluate(self, snapshot: DimensionSnapshot) -> DimensionPatternResult:
        states = {
            "momentum": snapshot.momentum.value,
            "trend": snapshot.trend.value,
            "volatility": snapshot.volatility.value,
            "participation": snapshot.participation.value,
        }
        
        trend_ok = snapshot.trend in [TrendState.DOWN_STRONG, TrendState.DOWN_WEAK]
        momentum_ok = snapshot.momentum in [MomentumState.NEUTRAL, MomentumState.OVERBOUGHT_SOFT]
        participation_ok = snapshot.participation in [ParticipationState.NORMAL, ParticipationState.STRONG]
        volatility_ok = snapshot.volatility != VolatilityState.EXTREME
        
        matched = trend_ok and momentum_ok and participation_ok and volatility_ok
        
        confidence = 0.0
        reasons = []
        
        if snapshot.trend == TrendState.DOWN_STRONG:
            confidence += 0.35
            reasons.append("strong downtrend")
        elif snapshot.trend == TrendState.DOWN_WEAK:
            confidence += 0.2
            reasons.append("mild downtrend")
        
        if snapshot.momentum == MomentumState.OVERBOUGHT_SOFT:
            confidence += 0.25
            reasons.append("bounce detected (overbought soft)")
        elif snapshot.momentum == MomentumState.NEUTRAL:
            confidence += 0.15
            reasons.append("momentum neutral")
        
        if snapshot.participation == ParticipationState.STRONG:
            confidence += 0.2
            reasons.append("strong volume")
        
        reason = "Trend continuation SELL: " + ", ".join(reasons) if reasons else "Conditions not met"
        
        return DimensionPatternResult(
            pattern_id=self.pattern_id,
            name=self.name,
            matched=matched,
            direction=self.direction,
            confidence=min(confidence, 1.0),
            dimension_states=states,
            reason=reason,
        )


class BreakoutBuy(DimensionPattern):
    """
    Buy breakout from compression.
    
    Conditions:
    - Structure: breakout_up
    - Volatility: expanding from compressed
    - Participation: strong or climax
    """
    
    def __init__(self):
        super().__init__(
            pattern_id="dim_breakout_buy",
            name="Breakout (Buy)",
            direction="buy",
            description="Compression breakout with volume",
        )
    
    def evaluate(self, snapshot: DimensionSnapshot) -> DimensionPatternResult:
        states = {
            "structure": snapshot.structure.value,
            "volatility": snapshot.volatility.value,
            "participation": snapshot.participation.value,
            "momentum": snapshot.momentum.value,
        }
        
        structure_ok = snapshot.structure == StructureState.BREAKOUT_UP
        participation_ok = snapshot.participation in [ParticipationState.STRONG, ParticipationState.CLIMAX]
        
        matched = structure_ok and participation_ok
        
        confidence = 0.0
        reasons = []
        
        if snapshot.structure == StructureState.BREAKOUT_UP:
            confidence += 0.4
            reasons.append("breaking out upward")
        
        if snapshot.participation == ParticipationState.CLIMAX:
            confidence += 0.3
            reasons.append("climax volume (caution: exhaustion possible)")
        elif snapshot.participation == ParticipationState.STRONG:
            confidence += 0.25
            reasons.append("strong volume confirmation")
        
        if snapshot.volatility == VolatilityState.EXPANDING:
            confidence += 0.2
            reasons.append("volatility expanding")
        
        if snapshot.momentum in [MomentumState.NEUTRAL, MomentumState.OVERBOUGHT_SOFT]:
            confidence += 0.1
            reasons.append("momentum building")
        
        reason = "Breakout BUY: " + ", ".join(reasons) if reasons else "Conditions not met"
        
        return DimensionPatternResult(
            pattern_id=self.pattern_id,
            name=self.name,
            matched=matched,
            direction=self.direction,
            confidence=min(confidence, 1.0),
            dimension_states=states,
            reason=reason,
        )


class BreakoutSell(DimensionPattern):
    """
    Sell (or short) on breakdown from compression.
    """
    
    def __init__(self):
        super().__init__(
            pattern_id="dim_breakout_sell",
            name="Breakdown (Sell)",
            direction="sell",
            description="Breakdown with volume confirmation",
        )
    
    def evaluate(self, snapshot: DimensionSnapshot) -> DimensionPatternResult:
        states = {
            "structure": snapshot.structure.value,
            "volatility": snapshot.volatility.value,
            "participation": snapshot.participation.value,
        }
        
        structure_ok = snapshot.structure == StructureState.BREAKOUT_DOWN
        participation_ok = snapshot.participation in [ParticipationState.STRONG, ParticipationState.CLIMAX]
        
        matched = structure_ok and participation_ok
        
        confidence = 0.0
        reasons = []
        
        if snapshot.structure == StructureState.BREAKOUT_DOWN:
            confidence += 0.4
            reasons.append("breaking down")
        
        if snapshot.participation == ParticipationState.CLIMAX:
            confidence += 0.3
            reasons.append("climax volume")
        elif snapshot.participation == ParticipationState.STRONG:
            confidence += 0.25
            reasons.append("strong volume")
        
        if snapshot.volatility == VolatilityState.EXPANDING:
            confidence += 0.2
            reasons.append("volatility expanding")
        
        reason = "Breakdown SELL: " + ", ".join(reasons) if reasons else "Conditions not met"
        
        return DimensionPatternResult(
            pattern_id=self.pattern_id,
            name=self.name,
            matched=matched,
            direction=self.direction,
            confidence=min(confidence, 1.0),
            dimension_states=states,
            reason=reason,
        )


class VolatilitySqueezeSetup(DimensionPattern):
    """
    Detect volatility squeeze - potential for big move incoming.
    
    This is a SETUP pattern, not a directional signal.
    Direction determined by subsequent breakout.
    """
    
    def __init__(self):
        super().__init__(
            pattern_id="dim_volatility_squeeze",
            name="Volatility Squeeze",
            direction="neutral",  # Setup, not directional
            description="Low volatility compression, big move pending",
        )
    
    def evaluate(self, snapshot: DimensionSnapshot) -> DimensionPatternResult:
        states = {
            "volatility": snapshot.volatility.value,
            "participation": snapshot.participation.value,
            "structure": snapshot.structure.value,
        }
        
        volatility_ok = snapshot.volatility == VolatilityState.COMPRESSED
        structure_ok = snapshot.structure == StructureState.CONSOLIDATING
        
        matched = volatility_ok and structure_ok
        
        confidence = 0.0
        reasons = []
        
        if snapshot.volatility == VolatilityState.COMPRESSED:
            confidence += 0.5
            reasons.append("volatility compressed")
        
        if snapshot.structure == StructureState.CONSOLIDATING:
            confidence += 0.3
            reasons.append("price consolidating")
        
        if snapshot.participation == ParticipationState.WEAK:
            confidence += 0.2
            reasons.append("volume drying up (calm before storm)")
        
        reason = "Volatility SQUEEZE setup: " + ", ".join(reasons) if reasons else "No squeeze detected"
        
        return DimensionPatternResult(
            pattern_id=self.pattern_id,
            name=self.name,
            matched=matched,
            direction=self.direction,
            confidence=min(confidence, 1.0),
            dimension_states=states,
            reason=reason,
        )


# ============================================================================
# PATTERN REGISTRY
# ============================================================================

# All available dimension patterns
DIMENSION_PATTERNS: List[DimensionPattern] = [
    MomentumReversalBuy(),
    MomentumReversalSell(),
    TrendContinuationBuy(),
    TrendContinuationSell(),
    BreakoutBuy(),
    BreakoutSell(),
    VolatilitySqueezeSetup(),
]


def evaluate_all_patterns(snapshot: DimensionSnapshot) -> List[DimensionPatternResult]:
    """Evaluate all dimension patterns against a snapshot."""
    results = []
    for pattern in DIMENSION_PATTERNS:
        result = pattern.evaluate(snapshot)
        results.append(result)
    return results


def get_matched_patterns(snapshot: DimensionSnapshot) -> List[DimensionPatternResult]:
    """Return only patterns that matched."""
    return [r for r in evaluate_all_patterns(snapshot) if r.matched]


def get_best_signal(snapshot: DimensionSnapshot) -> Optional[DimensionPatternResult]:
    """Return the highest-confidence matched pattern (excluding neutral setups)."""
    matched = [r for r in get_matched_patterns(snapshot) if r.direction != "neutral"]
    if not matched:
        return None
    return max(matched, key=lambda r: r.confidence)


def format_pattern_results(results: List[DimensionPatternResult]) -> str:
    """Human-readable pattern evaluation report."""
    lines = [
        "=" * 60,
        "📋 DIMENSION PATTERN EVALUATION",
        "=" * 60,
    ]
    
    matched = [r for r in results if r.matched]
    unmatched = [r for r in results if not r.matched]
    
    if matched:
        lines.append("\n✅ MATCHED PATTERNS:")
        for r in sorted(matched, key=lambda x: x.confidence, reverse=True):
            direction_emoji = "🔼" if r.direction == "buy" else "🔽" if r.direction == "sell" else "⏸️"
            lines.append(f"  {direction_emoji} {r.name} ({r.confidence*100:.0f}% confidence)")
            lines.append(f"     → {r.reason}")
    else:
        lines.append("\n⚪ No patterns matched current market state")
    
    lines.append("\n❌ UNMATCHED PATTERNS:")
    for r in unmatched:
        lines.append(f"  • {r.name}")
    
    lines.append("=" * 60)
    return "\n".join(lines)
