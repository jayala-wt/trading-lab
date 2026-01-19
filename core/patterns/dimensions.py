"""
Dimension Layer - Groups indicators into meaningful market dimensions.

This reduces bias by:
1. Separating measurement from decision
2. Grouping related indicators into dimensions
3. Using majority vote / gate+confirm instead of weighted averages
4. Outputting STATES not scores

Flow: Bars → Indicators → Dimensions → Patterns → Signals
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import json


# ============================================================================
# DIMENSION STATES (What each dimension can output)
# ============================================================================

class MomentumState(str, Enum):
    """Momentum EXTREME state - measures oversold/overbought extremes."""
    OVERSOLD_STRONG = "oversold_strong"      # 3/3 indicators agree
    OVERSOLD_SOFT = "oversold_soft"          # 2/3 indicators agree
    NEUTRAL = "neutral"
    OVERBOUGHT_SOFT = "overbought_soft"
    OVERBOUGHT_STRONG = "overbought_strong"


class MomentumBias(str, Enum):
    """Momentum BIAS - directional tendency regardless of extreme."""
    BULLISH = "bullish"       # Momentum favoring upside
    NEUTRAL = "neutral"       # Mixed signals
    BEARISH = "bearish"       # Momentum favoring downside


class TrendState(str, Enum):
    UP_STRONG = "up_strong"          # Strong uptrend with alignment
    UP_WEAK = "up_weak"              # Mild uptrend
    FLAT = "flat"                    # No clear trend
    DOWN_WEAK = "down_weak"
    DOWN_STRONG = "down_strong"


class VolatilityState(str, Enum):
    COMPRESSED = "compressed"        # Low volatility, squeeze forming
    NORMAL = "normal"
    EXPANDING = "expanding"          # High volatility
    EXTREME = "extreme"              # Very high volatility


class ParticipationState(str, Enum):
    WEAK = "weak"                    # Below average volume
    NORMAL = "normal"
    STRONG = "strong"                # Above average volume
    CLIMAX = "climax"                # Extreme volume (potential exhaustion)


class LocationState(str, Enum):
    ABOVE_VWAP = "above_vwap"
    AT_VWAP = "at_vwap"
    BELOW_VWAP = "below_vwap"
    AT_SUPPORT = "at_support"
    AT_RESISTANCE = "at_resistance"
    IN_RANGE = "in_range"


class StructureState(str, Enum):
    HIGHER_HIGHS = "higher_highs"    # Bullish structure
    LOWER_LOWS = "lower_lows"        # Bearish structure
    CONSOLIDATING = "consolidating"  # Neither
    BREAKOUT_UP = "breakout_up"      # Breaking above range
    BREAKOUT_DOWN = "breakout_down"  # Breaking below range


# ============================================================================
# DIMENSION SNAPSHOT (The complete state at one moment)
# ============================================================================

@dataclass
class DimensionSnapshot:
    """Complete market state across all dimensions."""
    symbol: str
    timestamp: str
    
    # Core dimensions
    momentum: MomentumState           # Extreme state (oversold/overbought)
    momentum_bias: MomentumBias       # Directional bias (bullish/bearish)
    trend: TrendState
    volatility: VolatilityState
    participation: ParticipationState
    location: LocationState
    structure: StructureState
    
    # Raw values for debugging/ML
    momentum_raw: Dict[str, float]
    trend_raw: Dict[str, float]
    volatility_raw: Dict[str, float]
    participation_raw: Dict[str, float]
    location_raw: Dict[str, float]
    structure_raw: Dict[str, float]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "states": {
                "momentum": self.momentum.value,
                "momentum_bias": self.momentum_bias.value,
                "trend": self.trend.value,
                "volatility": self.volatility.value,
                "participation": self.participation.value,
                "location": self.location.value,
                "structure": self.structure.value,
            },
            "raw": {
                "momentum": self.momentum_raw,
                "trend": self.trend_raw,
                "volatility": self.volatility_raw,
                "participation": self.participation_raw,
                "location": self.location_raw,
                "structure": self.structure_raw,
            }
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict())


# ============================================================================
# DIMENSION COMPUTERS
# ============================================================================

def compute_momentum(
    rsi: float,
    stoch_k: float,
    macd_histogram: float,
) -> Tuple[MomentumState, MomentumBias, Dict[str, float]]:
    """
    Compute momentum dimension using MAJORITY VOTE.
    
    Returns two separate measures (per audit recommendation):
    - MomentumState: EXTREME measure (oversold/overbought)
    - MomentumBias: DIRECTIONAL measure (bullish/bearish)
    
    This separation makes ML easier and reduces state explosion.
    """
    raw = {
        "rsi": rsi,
        "stoch_k": stoch_k,
        "macd_histogram": macd_histogram,
    }
    
    # === EXTREME STATE (oversold/overbought) ===
    oversold_votes = 0
    overbought_votes = 0
    
    # RSI: <30 oversold, >70 overbought
    if rsi < 30:
        oversold_votes += 1
    elif rsi > 70:
        overbought_votes += 1
    
    # Stochastic K: <20 oversold, >80 overbought
    if stoch_k < 20:
        oversold_votes += 1
    elif stoch_k > 80:
        overbought_votes += 1
    
    # MACD histogram extremes
    if macd_histogram < -50:
        oversold_votes += 1
    elif macd_histogram > 50:
        overbought_votes += 1
    
    # Determine extreme state by majority
    if oversold_votes >= 3:
        extreme = MomentumState.OVERSOLD_STRONG
    elif oversold_votes >= 2:
        extreme = MomentumState.OVERSOLD_SOFT
    elif overbought_votes >= 3:
        extreme = MomentumState.OVERBOUGHT_STRONG
    elif overbought_votes >= 2:
        extreme = MomentumState.OVERBOUGHT_SOFT
    else:
        extreme = MomentumState.NEUTRAL
    
    # === BIAS STATE (bullish/bearish direction) ===
    bullish_votes = 0
    bearish_votes = 0
    
    # RSI: >50 bullish, <50 bearish
    if rsi > 55:
        bullish_votes += 1
    elif rsi < 45:
        bearish_votes += 1
    
    # Stochastic K: >50 bullish, <50 bearish
    if stoch_k > 55:
        bullish_votes += 1
    elif stoch_k < 45:
        bearish_votes += 1
    
    # MACD histogram: positive = bullish, negative = bearish
    if macd_histogram > 0:
        bullish_votes += 1
    elif macd_histogram < 0:
        bearish_votes += 1
    
    # Determine bias by majority
    if bullish_votes >= 2:
        bias = MomentumBias.BULLISH
    elif bearish_votes >= 2:
        bias = MomentumBias.BEARISH
    else:
        bias = MomentumBias.NEUTRAL
    
    return extreme, bias, raw


def compute_trend(
    ema_9: float,
    ema_21: float,
    ema_50: float,
    sma_200: float,
    close: float,
    slope_20: float,
) -> Tuple[TrendState, Dict[str, float]]:
    """
    Compute trend dimension using GATE + CONFIRM.
    
    Gate: EMA alignment (9 > 21 > 50 = uptrend)
    Confirm: Slope + price position
    """
    raw = {
        "ema_9": ema_9,
        "ema_21": ema_21,
        "ema_50": ema_50,
        "sma_200": sma_200,
        "close": close,
        "slope_20": slope_20,
    }
    
    # Check EMA alignment
    ema_bullish_aligned = ema_9 > ema_21 > ema_50
    ema_bearish_aligned = ema_9 < ema_21 < ema_50
    
    # Check price vs EMAs
    price_above_fast = close > ema_9
    price_above_slow = close > ema_50
    price_above_200 = close > sma_200
    
    # Check slope
    trending_up = slope_20 > 0.001  # Positive slope
    trending_down = slope_20 < -0.001
    
    # Determine state
    if ema_bullish_aligned and price_above_fast and trending_up:
        state = TrendState.UP_STRONG
    elif (ema_9 > ema_21 or price_above_slow) and trending_up:
        state = TrendState.UP_WEAK
    elif ema_bearish_aligned and not price_above_fast and trending_down:
        state = TrendState.DOWN_STRONG
    elif (ema_9 < ema_21 or not price_above_slow) and trending_down:
        state = TrendState.DOWN_WEAK
    else:
        state = TrendState.FLAT
    
    return state, raw


def compute_volatility(
    atr_pct: float,
    bb_bandwidth: float,
    bb_pct: float,
    atr_percentile: float = 50,  # Where current ATR ranks vs history
) -> Tuple[VolatilityState, Dict[str, float]]:
    """
    Compute volatility dimension using STATE BUCKETS.
    
    Uses ATR% and Bollinger Bandwidth to determine regime.
    """
    raw = {
        "atr_pct": atr_pct,
        "bb_bandwidth": bb_bandwidth,
        "bb_pct": bb_pct,
    }
    
    # Bollinger Bandwidth thresholds (typical values)
    # <0.02 = compressed, >0.05 = expanding, >0.08 = extreme
    
    if bb_bandwidth < 0.02 or atr_pct < 0.01:
        state = VolatilityState.COMPRESSED
    elif bb_bandwidth > 0.08 or atr_pct > 0.04:
        state = VolatilityState.EXTREME
    elif bb_bandwidth > 0.05 or atr_pct > 0.025:
        state = VolatilityState.EXPANDING
    else:
        state = VolatilityState.NORMAL
    
    return state, raw


def compute_participation(
    volume_ratio: float,  # Current volume / average volume
    volume_zscore: float = 0,
) -> Tuple[ParticipationState, Dict[str, float]]:
    """
    Compute participation dimension using THRESHOLD FLAGS.
    """
    raw = {
        "volume_ratio": volume_ratio,
        "volume_zscore": volume_zscore,
    }
    
    if volume_ratio > 3.0 or volume_zscore > 2.5:
        state = ParticipationState.CLIMAX
    elif volume_ratio > 1.5 or volume_zscore > 1.0:
        state = ParticipationState.STRONG
    elif volume_ratio < 0.5 or volume_zscore < -1.0:
        state = ParticipationState.WEAK
    else:
        state = ParticipationState.NORMAL
    
    return state, raw


def compute_location(
    close: float,
    vwap: float,
    support: float,
    resistance: float,
    range_position: float,  # 0-1 where price is in recent range
) -> Tuple[LocationState, Dict[str, float]]:
    """
    Compute location dimension - where is price relative to key levels?
    """
    raw = {
        "close": close,
        "vwap": vwap,
        "support": support,
        "resistance": resistance,
        "range_position": range_position,
    }
    
    vwap_distance_pct = (close - vwap) / vwap if vwap else 0
    support_distance_pct = (close - support) / support if support else 0
    resistance_distance_pct = (resistance - close) / resistance if resistance else 0
    
    # Check if at support/resistance (within 0.5%)
    if support_distance_pct < 0.005 and support_distance_pct > -0.01:
        state = LocationState.AT_SUPPORT
    elif resistance_distance_pct < 0.005 and resistance_distance_pct > -0.01:
        state = LocationState.AT_RESISTANCE
    elif vwap_distance_pct > 0.005:
        state = LocationState.ABOVE_VWAP
    elif vwap_distance_pct < -0.005:
        state = LocationState.BELOW_VWAP
    else:
        state = LocationState.AT_VWAP
    
    return state, raw


def compute_structure(
    recent_high: float,
    prev_high: float,
    recent_low: float,
    prev_low: float,
    close: float,
    resistance: float,
    support: float,
) -> Tuple[StructureState, Dict[str, float]]:
    """
    Compute structure dimension - higher highs/lower lows, breakouts.
    """
    raw = {
        "recent_high": recent_high,
        "prev_high": prev_high,
        "recent_low": recent_low,
        "prev_low": prev_low,
        "close": close,
    }
    
    higher_high = recent_high > prev_high
    higher_low = recent_low > prev_low
    lower_high = recent_high < prev_high
    lower_low = recent_low < prev_low
    
    # Check for breakouts
    if close > resistance * 1.002:  # Breaking above with margin
        state = StructureState.BREAKOUT_UP
    elif close < support * 0.998:
        state = StructureState.BREAKOUT_DOWN
    elif higher_high and higher_low:
        state = StructureState.HIGHER_HIGHS
    elif lower_high and lower_low:
        state = StructureState.LOWER_LOWS
    else:
        state = StructureState.CONSOLIDATING
    
    return state, raw


# ============================================================================
# MAIN DIMENSION COMPUTER
# ============================================================================

def compute_dimensions(bars: List[Any], symbol: str) -> DimensionSnapshot:
    """
    Compute all dimensions from price bars.
    
    This is the main entry point - takes raw bars, returns dimension snapshot.
    """
    from datetime import datetime, timezone
    from core.patterns.primitives_engine import build_context
    
    # Get indicator values from primitives engine
    ctx, funcs = build_context(bars)
    
    # Extract values
    close = ctx.get("close", 0)
    
    # Momentum indicators
    rsi = funcs["rsi"](14)
    stoch_k = funcs["stochastic_k"](14)  # Correct function name
    macd_hist = funcs["macd_histogram"](12, 26, 9)
    
    # Trend indicators
    ema_9 = funcs["ema"](9)
    ema_21 = funcs["ema"](21)
    ema_50 = funcs["ema"](50) if len(bars) >= 50 else ema_21
    sma_200 = funcs["sma"](200) if len(bars) >= 200 else ema_50
    slope_20 = funcs["slope"](20)
    
    # Volatility indicators
    atr = funcs["atr"](14)
    atr_pct = atr / close if close else 0
    bb_bandwidth = funcs["bb_bandwidth"](20, 2)
    bb_pct = funcs["bb_pct"](20, 2)
    
    # Participation
    volume_ratio = funcs["volume_ratio"](20)
    
    # Location
    vwap = funcs["vwap"](None)
    support = funcs["rolling_low"](20)
    resistance = funcs["rolling_high"](20)
    range_size = resistance - support if resistance > support else 1
    range_position = (close - support) / range_size if range_size else 0.5
    
    # Structure
    recent_high = funcs["rolling_high"](10)
    prev_high = funcs["rolling_high"](20)  # Using different window as proxy
    recent_low = funcs["rolling_low"](10)
    prev_low = funcs["rolling_low"](20)
    
    # Compute each dimension
    momentum_state, momentum_bias, momentum_raw = compute_momentum(rsi, stoch_k, macd_hist)
    trend_state, trend_raw = compute_trend(ema_9, ema_21, ema_50, sma_200, close, slope_20)
    vol_state, vol_raw = compute_volatility(atr_pct, bb_bandwidth, bb_pct)
    part_state, part_raw = compute_participation(volume_ratio)
    loc_state, loc_raw = compute_location(close, vwap, support, resistance, range_position)
    struct_state, struct_raw = compute_structure(recent_high, prev_high, recent_low, prev_low, close, resistance, support)
    
    return DimensionSnapshot(
        symbol=symbol,
        timestamp=datetime.now(timezone.utc).isoformat(),
        momentum=momentum_state,
        momentum_bias=momentum_bias,
        trend=trend_state,
        volatility=vol_state,
        participation=part_state,
        location=loc_state,
        structure=struct_state,
        momentum_raw=momentum_raw,
        trend_raw=trend_raw,
        volatility_raw=vol_raw,
        participation_raw=part_raw,
        location_raw=loc_raw,
        structure_raw=struct_raw,
    )


def format_dimension_report(snapshot: DimensionSnapshot) -> str:
    """Human-readable dimension report."""
    lines = [
        f"{'='*50}",
        f"📊 DIMENSION ANALYSIS: {snapshot.symbol}",
        f"{'='*50}",
        f"",
        f"🎯 MOMENTUM:      {snapshot.momentum.value.upper()} (Extreme)",
        f"   BIAS:          {snapshot.momentum_bias.value.upper()} (Direction)",
        f"   RSI: {snapshot.momentum_raw.get('rsi', 0):.1f}, Stoch: {snapshot.momentum_raw.get('stoch_k', 0):.1f}",
        f"",
        f"📈 TREND:         {snapshot.trend.value.upper()}",
        f"   EMA9: {snapshot.trend_raw.get('ema_9', 0):.2f}, EMA21: {snapshot.trend_raw.get('ema_21', 0):.2f}",
        f"",
        f"📊 VOLATILITY:    {snapshot.volatility.value.upper()}",
        f"   ATR%: {snapshot.volatility_raw.get('atr_pct', 0):.4f}, BB Width: {snapshot.volatility_raw.get('bb_bandwidth', 0):.4f}",
        f"",
        f"📢 PARTICIPATION: {snapshot.participation.value.upper()}",
        f"   Volume Ratio: {snapshot.participation_raw.get('volume_ratio', 0):.2f}x",
        f"",
        f"📍 LOCATION:      {snapshot.location.value.upper()}",
        f"   Close: {snapshot.location_raw.get('close', 0):.2f}, VWAP: {snapshot.location_raw.get('vwap', 0):.2f}",
        f"",
        f"🏗️ STRUCTURE:     {snapshot.structure.value.upper()}",
        f"{'='*50}",
    ]
    return "\n".join(lines)
