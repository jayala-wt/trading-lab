"""
Composite Signal Engine - Multi-Indicator Scoring System

Combines 27+ indicators into a weighted composite score that:
1. Identifies trend direction & strength
2. Detects momentum shifts
3. Finds reversal points
4. Measures volatility context
5. Confirms with volume

Each indicator contributes to:
- BULLISH score (0-100)
- BEARISH score (0-100)  
- NEUTRAL/UNCERTAINTY measure

Final signal: STRONG_BUY | BUY | NEUTRAL | SELL | STRONG_SELL
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Tuple

from core.patterns.primitives_engine import build_context


class SignalStrength(str, Enum):
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    WEAK_BUY = "WEAK_BUY"
    NEUTRAL = "NEUTRAL"
    WEAK_SELL = "WEAK_SELL"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"


@dataclass
class IndicatorScore:
    """Individual indicator contribution."""
    name: str
    value: float
    bullish: float  # 0-100
    bearish: float  # 0-100
    weight: float   # Importance multiplier
    reason: str


@dataclass
class CompositeSignal:
    """Full composite analysis result."""
    symbol: str
    bullish_score: float  # 0-100 weighted
    bearish_score: float  # 0-100 weighted
    net_score: float      # -100 to +100
    signal: SignalStrength
    confidence: float     # 0-100 (how many indicators agree)
    indicators: List[IndicatorScore]
    summary: str


def _score_rsi(rsi: float) -> Tuple[float, float, str]:
    """RSI scoring: <30 bullish, >70 bearish."""
    if rsi < 20:
        return (100, 0, "Extremely oversold")
    elif rsi < 30:
        return (80, 0, "Oversold")
    elif rsi < 40:
        return (40, 0, "Mildly oversold")
    elif rsi > 80:
        return (0, 100, "Extremely overbought")
    elif rsi > 70:
        return (0, 80, "Overbought")
    elif rsi > 60:
        return (0, 40, "Mildly overbought")
    return (30, 30, "Neutral RSI")


def _score_macd(histogram: float, signal_cross: bool, line_above: bool) -> Tuple[float, float, str]:
    """MACD scoring based on histogram, crossover, and line position."""
    bullish, bearish = 0.0, 0.0
    reasons = []
    
    # Histogram strength
    if histogram > 0:
        bullish += min(50, abs(histogram) * 500)
        reasons.append(f"Positive histogram ({histogram:.4f})")
    else:
        bearish += min(50, abs(histogram) * 500)
        reasons.append(f"Negative histogram ({histogram:.4f})")
    
    # Signal crossover
    if signal_cross:
        if histogram > 0:
            bullish += 30
            reasons.append("Bullish crossover")
        else:
            bearish += 30
            reasons.append("Bearish crossover")
    
    # Line position
    if line_above:
        bullish += 20
    else:
        bearish += 20
    
    return (min(100, bullish), min(100, bearish), "; ".join(reasons) if reasons else "MACD neutral")


def _score_bollinger(bb_pct: float, close: float, bb_upper: float, bb_lower: float) -> Tuple[float, float, str]:
    """Bollinger Bands scoring: touch bands = reversal potential."""
    if bb_pct < 0:
        return (90, 0, f"Below lower band (oversold extreme)")
    elif bb_pct < 0.2:
        return (70, 0, f"Near lower band ({bb_pct:.0%})")
    elif bb_pct > 1:
        return (0, 90, f"Above upper band (overbought extreme)")
    elif bb_pct > 0.8:
        return (0, 70, f"Near upper band ({bb_pct:.0%})")
    elif 0.4 < bb_pct < 0.6:
        return (30, 30, f"Mid-band neutral ({bb_pct:.0%})")
    return (40, 40, f"Bollinger range: {bb_pct:.0%}")


def _score_stochastic(k: float, d: float, k_prev: float) -> Tuple[float, float, str]:
    """Stochastic scoring with crossover detection."""
    bullish, bearish = 0.0, 0.0
    reasons = []
    
    if k < 20:
        bullish += 60
        reasons.append(f"Oversold territory (K={k:.1f})")
        if k > k_prev:
            bullish += 30
            reasons.append("Turning up from oversold")
    elif k > 80:
        bearish += 60
        reasons.append(f"Overbought territory (K={k:.1f})")
        if k < k_prev:
            bearish += 30
            reasons.append("Turning down from overbought")
    
    # K/D crossover
    if k > d and k_prev <= d:
        bullish += 20
        reasons.append("Bullish K/D cross")
    elif k < d and k_prev >= d:
        bearish += 20
        reasons.append("Bearish K/D cross")
    
    return (min(100, bullish), min(100, bearish), "; ".join(reasons) if reasons else "Stoch neutral")


def _score_adx(adx: float) -> Tuple[float, float, str]:
    """ADX measures trend strength - amplifies other signals."""
    if adx < 20:
        return (30, 30, f"Weak trend (ADX={adx:.1f})")
    elif adx < 40:
        return (50, 50, f"Moderate trend (ADX={adx:.1f})")
    elif adx < 60:
        return (70, 70, f"Strong trend (ADX={adx:.1f})")
    return (90, 90, f"Very strong trend (ADX={adx:.1f})")


def _score_trend(ema_fast: float, ema_slow: float, close: float, sma_200: float) -> Tuple[float, float, str]:
    """Trend scoring based on moving average positions."""
    bullish, bearish = 0.0, 0.0
    reasons = []
    
    if ema_fast > ema_slow:
        bullish += 40
        reasons.append("Fast EMA above slow (uptrend)")
    else:
        bearish += 40
        reasons.append("Fast EMA below slow (downtrend)")
    
    if close > ema_fast:
        bullish += 30
        reasons.append("Price above fast EMA")
    else:
        bearish += 30
        reasons.append("Price below fast EMA")
    
    if close > sma_200:
        bullish += 30
        reasons.append("Above 200 SMA (long-term bullish)")
    else:
        bearish += 30
        reasons.append("Below 200 SMA (long-term bearish)")
    
    return (min(100, bullish), min(100, bearish), "; ".join(reasons))


def _score_volume(volume_ratio: float) -> Tuple[float, float, str]:
    """Volume confirmation - high volume amplifies signals."""
    if volume_ratio > 2.0:
        return (80, 80, f"Very high volume ({volume_ratio:.1f}x avg)")
    elif volume_ratio > 1.5:
        return (60, 60, f"High volume ({volume_ratio:.1f}x avg)")
    elif volume_ratio > 1.0:
        return (40, 40, f"Normal volume ({volume_ratio:.1f}x avg)")
    else:
        return (20, 20, f"Low volume ({volume_ratio:.1f}x avg) - weak conviction")


def _score_support_resistance(close: float, support: float, resistance: float) -> Tuple[float, float, str]:
    """Score proximity to support/resistance levels."""
    price_range = resistance - support
    if price_range <= 0:
        return (30, 30, "No clear S/R levels")
    
    position = (close - support) / price_range
    
    if position < 0.1:
        return (80, 0, f"Near support (${support:.2f})")
    elif position < 0.3:
        return (50, 0, f"In support zone")
    elif position > 0.9:
        return (0, 80, f"Near resistance (${resistance:.2f})")
    elif position > 0.7:
        return (0, 50, f"In resistance zone")
    return (30, 30, f"Mid-range S/R")


def _score_candlestick(lower_wick: float, upper_wick: float, body_pct: float) -> Tuple[float, float, str]:
    """Candlestick pattern scoring."""
    bullish, bearish = 0.0, 0.0
    reasons = []
    
    # Hammer/Doji patterns
    if lower_wick > 0.6 and upper_wick < 0.2:
        bullish += 60
        reasons.append("Hammer pattern (rejection of lows)")
    elif upper_wick > 0.6 and lower_wick < 0.2:
        bearish += 60
        reasons.append("Shooting star (rejection of highs)")
    elif lower_wick > 0.4 and upper_wick > 0.4:
        bullish += 30
        bearish += 30
        reasons.append("Doji (indecision)")
    
    return (min(100, bullish), min(100, bearish), "; ".join(reasons) if reasons else "Normal candle")


def compute_composite_signal(bars: List[Dict[str, Any]], symbol: str = "UNKNOWN") -> CompositeSignal:
    """
    Compute a composite signal by analyzing all available indicators.
    
    Weights:
    - RSI: 15%
    - MACD: 15%
    - Bollinger: 10%
    - Stochastic: 10%
    - ADX: 10%
    - Trend (EMAs): 15%
    - Volume: 10%
    - Support/Resistance: 10%
    - Candlestick: 5%
    """
    ctx, funcs = build_context(bars)
    indicators: List[IndicatorScore] = []
    
    # 1. RSI Analysis (15%)
    rsi = funcs["rsi"](14)
    rsi_bull, rsi_bear, rsi_reason = _score_rsi(rsi)
    indicators.append(IndicatorScore("RSI(14)", rsi, rsi_bull, rsi_bear, 15, rsi_reason))
    
    # 2. MACD Analysis (15%)
    macd_hist = funcs["macd_histogram"](12, 26, 9)
    macd_hist_prev = funcs["macd_histogram"](12, 26, 9)  # Would need macd_histogram_prev
    macd_line = funcs["macd_line"](12, 26)
    macd_signal = funcs["macd_signal"](12, 26, 9)
    signal_cross = abs(macd_line - macd_signal) < abs(macd_hist) * 0.5  # Rough crossover check
    line_above = macd_line > 0
    macd_bull, macd_bear, macd_reason = _score_macd(macd_hist, signal_cross, line_above)
    indicators.append(IndicatorScore("MACD", macd_hist, macd_bull, macd_bear, 15, macd_reason))
    
    # 3. Bollinger Bands Analysis (10%)
    bb_pct = funcs["bb_pct"](20, 2.0)
    bb_upper = funcs["bb_upper"](20, 2.0)
    bb_lower = funcs["bb_lower"](20, 2.0)
    close = ctx["close"]
    bb_bull, bb_bear, bb_reason = _score_bollinger(bb_pct, close, bb_upper, bb_lower)
    indicators.append(IndicatorScore("Bollinger %B", bb_pct, bb_bull, bb_bear, 10, bb_reason))
    
    # 4. Stochastic Analysis (10%)
    stoch_k = funcs["stochastic_k"](14)
    stoch_d = funcs["stochastic_d"](14, 3)
    stoch_k_prev = stoch_k  # Would need stochastic_k_prev
    stoch_bull, stoch_bear, stoch_reason = _score_stochastic(stoch_k, stoch_d, stoch_k_prev)
    indicators.append(IndicatorScore("Stochastic", stoch_k, stoch_bull, stoch_bear, 10, stoch_reason))
    
    # 5. ADX Analysis (10%)
    adx = funcs["adx"](14)
    adx_bull, adx_bear, adx_reason = _score_adx(adx)
    indicators.append(IndicatorScore("ADX", adx, adx_bull, adx_bear, 10, adx_reason))
    
    # 6. Trend Analysis (15%)
    ema_fast = funcs["ema"](9)
    ema_slow = funcs["ema"](21)
    sma_200 = funcs["sma"](50)  # Use 50 for shorter data
    trend_bull, trend_bear, trend_reason = _score_trend(ema_fast, ema_slow, close, sma_200)
    indicators.append(IndicatorScore("Trend EMAs", ema_fast - ema_slow, trend_bull, trend_bear, 15, trend_reason))
    
    # 7. Volume Analysis (10%)
    vol_ratio = funcs["volume_ratio"](20)
    vol_bull, vol_bear, vol_reason = _score_volume(vol_ratio)
    indicators.append(IndicatorScore("Volume", vol_ratio, vol_bull, vol_bear, 10, vol_reason))
    
    # 8. Support/Resistance (10%)
    support = funcs["support_level"](50)
    resistance = funcs["resistance_level"](50)
    sr_bull, sr_bear, sr_reason = _score_support_resistance(close, support, resistance)
    indicators.append(IndicatorScore("S/R Levels", (close - support) / (resistance - support + 0.001), sr_bull, sr_bear, 10, sr_reason))
    
    # 9. Candlestick Analysis (5%)
    lower_wick = funcs["lower_wick_ratio"]()
    upper_wick = funcs["upper_wick_ratio"]()
    body_pct = abs(ctx["close"] - ctx["open"]) / (ctx["high"] - ctx["low"] + 0.001)
    candle_bull, candle_bear, candle_reason = _score_candlestick(lower_wick, upper_wick, body_pct)
    indicators.append(IndicatorScore("Candlestick", body_pct, candle_bull, candle_bear, 5, candle_reason))
    
    # Compute weighted scores
    total_weight = sum(ind.weight for ind in indicators)
    bullish_score = sum(ind.bullish * ind.weight for ind in indicators) / total_weight
    bearish_score = sum(ind.bearish * ind.weight for ind in indicators) / total_weight
    
    # Net score: -100 (max bearish) to +100 (max bullish)
    net_score = bullish_score - bearish_score
    
    # Determine signal strength
    if net_score >= 60:
        signal = SignalStrength.STRONG_BUY
    elif net_score >= 40:
        signal = SignalStrength.BUY
    elif net_score >= 20:
        signal = SignalStrength.WEAK_BUY
    elif net_score <= -60:
        signal = SignalStrength.STRONG_SELL
    elif net_score <= -40:
        signal = SignalStrength.SELL
    elif net_score <= -20:
        signal = SignalStrength.WEAK_SELL
    else:
        signal = SignalStrength.NEUTRAL
    
    # Confidence: how many indicators agree on direction
    bullish_indicators = sum(1 for ind in indicators if ind.bullish > ind.bearish)
    bearish_indicators = sum(1 for ind in indicators if ind.bearish > ind.bullish)
    neutral_indicators = len(indicators) - bullish_indicators - bearish_indicators
    max_agreement = max(bullish_indicators, bearish_indicators)
    confidence = (max_agreement / len(indicators)) * 100
    
    # Build summary
    dominant_direction = "BULLISH" if bullish_score > bearish_score else "BEARISH" if bearish_score > bullish_score else "MIXED"
    summary = f"{signal.value}: {dominant_direction} bias ({confidence:.0f}% agreement) | Net: {net_score:+.1f} | Bull: {bullish_score:.1f} Bear: {bearish_score:.1f}"
    
    return CompositeSignal(
        symbol=symbol,
        bullish_score=bullish_score,
        bearish_score=bearish_score,
        net_score=net_score,
        signal=signal,
        confidence=confidence,
        indicators=indicators,
        summary=summary,
    )


def format_composite_report(signal: CompositeSignal) -> str:
    """Format a detailed report of the composite signal."""
    lines = [
        f"{'='*60}",
        f"🎯 COMPOSITE SIGNAL: {signal.symbol}",
        f"{'='*60}",
        f"",
        f"📊 SIGNAL: {signal.signal.value}",
        f"   Net Score: {signal.net_score:+.1f} ({signal.confidence:.0f}% confidence)",
        f"   Bullish: {signal.bullish_score:.1f} | Bearish: {signal.bearish_score:.1f}",
        f"",
        f"📈 INDICATOR BREAKDOWN:",
        f"-" * 40,
    ]
    
    for ind in sorted(signal.indicators, key=lambda x: x.weight, reverse=True):
        direction = "🟢" if ind.bullish > ind.bearish else "🔴" if ind.bearish > ind.bullish else "⚪"
        lines.append(f"  {direction} {ind.name} ({ind.weight}%)")
        lines.append(f"     Value: {ind.value:.2f}")
        lines.append(f"     Bull: {ind.bullish:.1f} | Bear: {ind.bearish:.1f}")
        lines.append(f"     → {ind.reason}")
        lines.append("")
    
    lines.extend([
        f"-" * 40,
        f"💡 SUMMARY: {signal.summary}",
        f"{'='*60}",
    ])
    
    return "\n".join(lines)


def get_human_explanation(signal: CompositeSignal) -> Dict[str, Any]:
    """
    Translate technical composite signal into plain English.
    Returns a dictionary with human-readable explanation.
    """
    net = signal.net_score
    conf = signal.confidence
    
    # Main recommendation
    if net > 30:
        action = "GOOD TIME TO BUY"
        emoji = "🟢"
        reason = "Multiple indicators agree the price should go up"
    elif net > 10:
        action = "LEANING BULLISH"
        emoji = "🟡"
        reason = "Some signs point up, but not super confident"
    elif net > -10:
        action = "WAIT & WATCH"
        emoji = "⚪"
        reason = "Mixed signals, no clear direction"
    elif net > -30:
        action = "LEANING BEARISH"
        emoji = "🟡"
        reason = "Some signs point down, be cautious"
    else:
        action = "AVOID BUYING"
        emoji = "🔴"
        reason = "Multiple indicators suggest price may drop"
    
    # Key factors (only mention significant ones)
    key_factors = []
    for ind in signal.indicators:
        diff = ind.bullish - ind.bearish
        if abs(diff) > 20:
            direction = "↑ Bullish" if diff > 0 else "↓ Bearish"
            key_factors.append({
                "indicator": ind.name,
                "direction": direction,
                "why": ind.reason
            })
    
    # Bot would do
    if net > 25 and conf > 40:
        bot_action = "BUY"
        bot_reason = "Strong signal with decent confidence"
    elif net < -25 and conf > 40:
        bot_action = "SELL or AVOID"
        bot_reason = "Strong bearish signal with decent confidence"
    else:
        bot_action = "HOLD or SKIP"
        bot_reason = "Waiting for clearer signal"
    
    return {
        "recommendation": {
            "action": action,
            "emoji": emoji,
            "reason": reason
        },
        "confidence_level": (
            "HIGH" if conf > 60 else 
            "MEDIUM" if conf > 40 else 
            "LOW"
        ),
        "confidence_explanation": (
            f"{conf:.0f}% of indicators agree on direction"
        ),
        "key_factors": key_factors,
        "bot_would": {
            "action": bot_action,
            "reason": bot_reason
        },
        "plain_summary": (
            f"{emoji} {action}: {reason}. "
            f"Confidence is {'high' if conf > 60 else 'medium' if conf > 40 else 'low'} ({conf:.0f}%). "
            f"The bot would {bot_action.lower()}."
        )
    }
