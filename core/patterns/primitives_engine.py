from __future__ import annotations

import ast
import math
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Tuple

from core.patterns.base import PatternEvent


@dataclass
class Series:
    values: List[float]

    def last(self) -> float:
        return self.values[-1] if self.values else 0.0

    def window(self, length: int) -> List[float]:
        if length <= 0:
            return self.values
        return self.values[-length:]


class SafeEvaluator:
    def __init__(self, context: Dict[str, Any], functions: Dict[str, Callable[..., Any]]) -> None:
        self.context = context
        self.functions = functions

    def eval(self, expression: str) -> Any:
        node = ast.parse(expression, mode="eval")
        return self._eval_node(node.body)

    def _eval_node(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Num):
            return node.n
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in self.context:
                return self.context[node.id]
            if node.id in self.functions:
                return self.functions[node.id]
            raise ValueError(f"Unknown name: {node.id}")
        if isinstance(node, ast.BinOp):
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.Mod):
                return left % right
            if isinstance(node.op, ast.Pow):
                return left ** right
            raise ValueError("Unsupported binary operator")
        if isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand)
            if isinstance(node.op, ast.USub):
                return -operand
            if isinstance(node.op, ast.UAdd):
                return +operand
            if isinstance(node.op, ast.Not):
                return not operand
            raise ValueError("Unsupported unary operator")
        if isinstance(node, ast.BoolOp):
            values = [self._eval_node(v) for v in node.values]
            if isinstance(node.op, ast.And):
                return all(values)
            if isinstance(node.op, ast.Or):
                return any(values)
            raise ValueError("Unsupported boolean operator")
        if isinstance(node, ast.Compare):
            left = self._eval_node(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                right = self._eval_node(comparator)
                if isinstance(op, ast.Gt) and not left > right:
                    return False
                if isinstance(op, ast.GtE) and not left >= right:
                    return False
                if isinstance(op, ast.Lt) and not left < right:
                    return False
                if isinstance(op, ast.LtE) and not left <= right:
                    return False
                if isinstance(op, ast.Eq) and not left == right:
                    return False
                if isinstance(op, ast.NotEq) and not left != right:
                    return False
                left = right
            return True
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Unsupported function call")
            func_name = node.func.id
            if func_name not in self.functions:
                raise ValueError(f"Function not allowed: {func_name}")
            func = self.functions[func_name]
            args = [self._eval_node(arg) for arg in node.args]
            return func(*args)
        raise ValueError(f"Unsupported expression: {ast.dump(node)}")


def _series_from_bars(bars: List[Dict[str, Any]]) -> Dict[str, Series]:
    def to_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    closes = [to_float(bar.get("c") or bar.get("close")) for bar in bars]
    opens = [to_float(bar.get("o") or bar.get("open")) for bar in bars]
    highs = [to_float(bar.get("h") or bar.get("high")) for bar in bars]
    lows = [to_float(bar.get("l") or bar.get("low")) for bar in bars]
    volumes = [to_float(bar.get("v") or bar.get("volume")) for bar in bars]
    return {
        "close": Series(closes),
        "open": Series(opens),
        "high": Series(highs),
        "low": Series(lows),
        "volume": Series(volumes),
    }


def _pct_move(series: Series, window: int) -> float:
    if len(series.values) <= window or window <= 0:
        return 0.0
    prev = series.values[-window - 1]
    if prev == 0:
        return 0.0
    return ((series.last() - prev) / prev) * 100.0


def _range_pct(high: Series, low: Series, window: int) -> float:
    highs = high.window(window)
    lows = low.window(window)
    if not highs or not lows:
        return 0.0
    last_close = high.last() or 1.0
    return ((max(highs) - min(lows)) / last_close) * 100.0


def _atr(high: Series, low: Series, close: Series, period: int) -> float:
    if len(close.values) < 2:
        return 0.0
    true_ranges: List[float] = []
    for idx in range(1, len(close.values)):
        tr = max(
            high.values[idx] - low.values[idx],
            abs(high.values[idx] - close.values[idx - 1]),
            abs(low.values[idx] - close.values[idx - 1]),
        )
        true_ranges.append(tr)
    window = true_ranges[-period:] if period > 0 else true_ranges
    if not window:
        return 0.0
    return sum(window) / len(window)


def _ema(series: Series, period: int) -> float:
    values = series.values
    if not values:
        return 0.0
    if period <= 1:
        return values[-1]
    k = 2 / (period + 1)
    ema_val = values[0]
    for value in values[1:]:
        ema_val = value * k + ema_val * (1 - k)
    return ema_val


def _vwap(close: Series, volume: Series, session: Any) -> float:
    length = len(close.values)
    if isinstance(session, int) and session > 0:
        length = min(length, session)
    closes = close.window(length)
    vols = volume.window(length)
    if not closes or not vols:
        return 0.0
    weighted = sum(c * v for c, v in zip(closes, vols))
    total = sum(vols)
    return weighted / total if total else 0.0


def _zscore(series: Series, period: int) -> float:
    window = series.window(period)
    if not window:
        return 0.0
    mean = sum(window) / len(window)
    variance = sum((x - mean) ** 2 for x in window) / len(window)
    std = math.sqrt(variance)
    if std == 0:
        return 0.0
    return (series.last() - mean) / std


def _slope(series: Series, period: int) -> float:
    window = series.window(period)
    n = len(window)
    if n < 2:
        return 0.0
    x_vals = list(range(n))
    x_mean = sum(x_vals) / n
    y_mean = sum(window) / n
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_vals, window))
    den = sum((x - x_mean) ** 2 for x in x_vals)
    if den == 0:
        return 0.0
    return num / den


def _rolling_high(series: Series, period: int) -> float:
    window = series.window(period)
    return max(window) if window else 0.0


def _rolling_low(series: Series, period: int) -> float:
    window = series.window(period)
    return min(window) if window else 0.0


def _cross(a: Any, b: Any) -> bool:
    def to_list(val: Any) -> List[float]:
        if isinstance(val, Series):
            return val.values
        if isinstance(val, list):
            return [float(x) for x in val]
        return [float(val)]

    a_list = to_list(a)
    b_list = to_list(b)
    if len(a_list) < 2 or len(b_list) < 2:
        return False
    return a_list[-2] <= b_list[-2] and a_list[-1] > b_list[-1]


# ============ NEW INDICATORS ============

def _rsi(series: Series, period: int) -> float:
    """Relative Strength Index."""
    values = series.values
    if len(values) < period + 1:
        return 50.0  # neutral
    
    gains: List[float] = []
    losses: List[float] = []
    
    for i in range(1, len(values)):
        change = values[i] - values[i - 1]
        if change > 0:
            gains.append(change)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(change))
    
    # Use EMA-style smoothing for RSI
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    
    if avg_loss == 0:
        return 100.0
    
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _rsi_prev(series: Series, period: int, bars_back: int) -> float:
    """RSI value N bars ago."""
    if bars_back <= 0 or len(series.values) <= bars_back:
        return _rsi(series, period)
    # Create a truncated series
    truncated = Series(series.values[:-bars_back])
    return _rsi(truncated, period)


def _ema_series(values: List[float], period: int) -> List[float]:
    """Calculate full EMA series."""
    if not values or period <= 0:
        return values
    k = 2 / (period + 1)
    ema_vals = [values[0]]
    for i in range(1, len(values)):
        ema_vals.append(values[i] * k + ema_vals[-1] * (1 - k))
    return ema_vals


def _macd_line(series: Series, fast: int, slow: int) -> float:
    """MACD line = fast EMA - slow EMA."""
    fast_ema = _ema(series, fast)
    slow_ema = _ema(series, slow)
    return fast_ema - slow_ema


def _macd_signal(series: Series, fast: int, slow: int, signal: int) -> float:
    """MACD signal line = EMA of MACD line."""
    values = series.values
    if len(values) < slow:
        return 0.0
    
    # Calculate MACD line for each point
    fast_ema_series = _ema_series(values, fast)
    slow_ema_series = _ema_series(values, slow)
    macd_series = [f - s for f, s in zip(fast_ema_series, slow_ema_series)]
    
    # Signal is EMA of MACD
    signal_series = _ema_series(macd_series, signal)
    return signal_series[-1] if signal_series else 0.0


def _macd_histogram(series: Series, fast: int, slow: int, signal: int) -> float:
    """MACD histogram = MACD line - signal line."""
    return _macd_line(series, fast, slow) - _macd_signal(series, fast, slow, signal)


def _macd_line_prev(series: Series, fast: int, slow: int, bars_back: int) -> float:
    """MACD line N bars ago."""
    if bars_back <= 0 or len(series.values) <= bars_back:
        return _macd_line(series, fast, slow)
    truncated = Series(series.values[:-bars_back])
    return _macd_line(truncated, fast, slow)


def _macd_signal_prev(series: Series, fast: int, slow: int, signal: int, bars_back: int) -> float:
    """MACD signal N bars ago."""
    if bars_back <= 0 or len(series.values) <= bars_back:
        return _macd_signal(series, fast, slow, signal)
    truncated = Series(series.values[:-bars_back])
    return _macd_signal(truncated, fast, slow, signal)


def _bb_middle(series: Series, period: int) -> float:
    """Bollinger Band middle (SMA)."""
    window = series.window(period)
    return sum(window) / len(window) if window else 0.0


def _bb_std(series: Series, period: int) -> float:
    """Standard deviation for Bollinger Bands."""
    window = series.window(period)
    if not window:
        return 0.0
    mean = sum(window) / len(window)
    variance = sum((x - mean) ** 2 for x in window) / len(window)
    return math.sqrt(variance)


def _bb_upper(series: Series, period: int, std_mult: float) -> float:
    """Bollinger Band upper."""
    return _bb_middle(series, period) + std_mult * _bb_std(series, period)


def _bb_lower(series: Series, period: int, std_mult: float) -> float:
    """Bollinger Band lower."""
    return _bb_middle(series, period) - std_mult * _bb_std(series, period)


def _bb_bandwidth(series: Series, period: int, std_mult: float) -> float:
    """Bollinger Band bandwidth = (upper - lower) / middle."""
    middle = _bb_middle(series, period)
    if middle == 0:
        return 0.0
    upper = _bb_upper(series, period, std_mult)
    lower = _bb_lower(series, period, std_mult)
    return (upper - lower) / middle


def _bb_pct(series: Series, period: int, std_mult: float) -> float:
    """Bollinger Band %B = (price - lower) / (upper - lower)."""
    upper = _bb_upper(series, period, std_mult)
    lower = _bb_lower(series, period, std_mult)
    if upper == lower:
        return 0.5
    return (series.last() - lower) / (upper - lower)


def _sma(series: Series, period: int) -> float:
    """Simple Moving Average."""
    window = series.window(period)
    return sum(window) / len(window) if window else 0.0


def _ema_prev(series: Series, period: int, bars_back: int) -> float:
    """EMA value N bars ago."""
    if bars_back <= 0 or len(series.values) <= bars_back:
        return _ema(series, period)
    truncated = Series(series.values[:-bars_back])
    return _ema(truncated, period)


def _sma_prev(series: Series, period: int, bars_back: int) -> float:
    """SMA value N bars ago."""
    if bars_back <= 0 or len(series.values) <= bars_back:
        return _sma(series, period)
    truncated = Series(series.values[:-bars_back])
    return _sma(truncated, period)


def _volume_ratio(volume: Series, period: int) -> float:
    """Current volume vs average volume."""
    window = volume.window(period)
    if not window:
        return 1.0
    avg = sum(window) / len(window)
    if avg == 0:
        return 1.0
    return volume.last() / avg


def _stochastic_k(high: Series, low: Series, close: Series, period: int) -> float:
    """Stochastic %K."""
    highs = high.window(period)
    lows = low.window(period)
    if not highs or not lows:
        return 50.0
    highest = max(highs)
    lowest = min(lows)
    if highest == lowest:
        return 50.0
    return ((close.last() - lowest) / (highest - lowest)) * 100


def _stochastic_d(high: Series, low: Series, close: Series, k_period: int, d_period: int) -> float:
    """Stochastic %D (smoothed %K)."""
    # Calculate K for recent bars and average
    k_values: List[float] = []
    for i in range(d_period):
        if len(close.values) > i:
            truncated_high = Series(high.values[:len(high.values) - i] if i > 0 else high.values)
            truncated_low = Series(low.values[:len(low.values) - i] if i > 0 else low.values)
            truncated_close = Series(close.values[:len(close.values) - i] if i > 0 else close.values)
            k_values.append(_stochastic_k(truncated_high, truncated_low, truncated_close, k_period))
    return sum(k_values) / len(k_values) if k_values else 50.0


def _adx(high: Series, low: Series, close: Series, period: int) -> float:
    """Average Directional Index (simplified)."""
    if len(close.values) < period + 1:
        return 25.0  # neutral
    
    plus_dm: List[float] = []
    minus_dm: List[float] = []
    tr_list: List[float] = []
    
    for i in range(1, len(close.values)):
        high_diff = high.values[i] - high.values[i - 1]
        low_diff = low.values[i - 1] - low.values[i]
        
        plus_dm.append(high_diff if high_diff > low_diff and high_diff > 0 else 0)
        minus_dm.append(low_diff if low_diff > high_diff and low_diff > 0 else 0)
        
        tr = max(
            high.values[i] - low.values[i],
            abs(high.values[i] - close.values[i - 1]),
            abs(low.values[i] - close.values[i - 1])
        )
        tr_list.append(tr)
    
    # Smooth with EMA
    plus_dm_ema = _ema_series(plus_dm, period)[-1]
    minus_dm_ema = _ema_series(minus_dm, period)[-1]
    tr_ema = _ema_series(tr_list, period)[-1]
    
    if tr_ema == 0:
        return 25.0
    
    plus_di = (plus_dm_ema / tr_ema) * 100
    minus_di = (minus_dm_ema / tr_ema) * 100
    
    if plus_di + minus_di == 0:
        return 25.0
    
    dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100
    return dx


def _min_close(series: Series, period: int) -> float:
    """Minimum close in window."""
    window = series.window(period)
    return min(window) if window else series.last()


def _max_close(series: Series, period: int) -> float:
    """Maximum close in window."""
    window = series.window(period)
    return max(window) if window else series.last()


def _lower_wick_ratio(open_s: Series, high: Series, low: Series, close: Series) -> float:
    """Lower wick to body ratio (for hammer detection)."""
    o = open_s.last()
    h = high.last()
    l = low.last()
    c = close.last()
    
    body = abs(c - o)
    lower_wick = min(o, c) - l
    
    if body == 0:
        return lower_wick * 10 if lower_wick > 0 else 0
    return lower_wick / body


def _upper_wick_ratio(open_s: Series, high: Series, low: Series, close: Series) -> float:
    """Upper wick to body ratio."""
    o = open_s.last()
    h = high.last()
    c = close.last()
    
    body = abs(c - o)
    upper_wick = h - max(o, c)
    
    if body == 0:
        return upper_wick * 10 if upper_wick > 0 else 0
    return upper_wick / body


def _support_level(low: Series, period: int) -> float:
    """Find support level (recent low)."""
    window = low.window(period)
    return min(window) if window else low.last()


def _resistance_level(high: Series, period: int) -> float:
    """Find resistance level (recent high)."""
    window = high.window(period)
    return max(window) if window else high.last()


def _overnight_gap_pct(open_s: Series, close: Series) -> float:
    """Overnight gap percentage."""
    if len(close.values) < 2:
        return 0.0
    prev_close = close.values[-2]
    curr_open = open_s.last()
    if prev_close == 0:
        return 0.0
    return ((curr_open - prev_close) / prev_close) * 100


def _min_rsi(series: Series, rsi_period: int, lookback: int) -> float:
    """Minimum RSI in lookback window."""
    if len(series.values) <= lookback:
        return _rsi(series, rsi_period)
    
    min_rsi = 100.0
    for i in range(lookback):
        if len(series.values) > i:
            truncated = Series(series.values[:len(series.values) - i])
            rsi_val = _rsi(truncated, rsi_period)
            min_rsi = min(min_rsi, rsi_val)
    return min_rsi


def build_context(bars: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], Dict[str, Callable[..., Any]]]:
    series = _series_from_bars(bars)
    # 'close', 'open', 'high', 'low' in patterns refer to the CURRENT (last) bar values
    # Use 'close_arr', etc. if you need the full array
    context: Dict[str, Any] = {
        "close": series["close"].last(),
        "open": series["open"].last(),
        "high": series["high"].last(),
        "low": series["low"].last(),
        "volume": series["volume"].last(),
        "close_arr": series["close"].values,
        "open_arr": series["open"].values,
        "high_arr": series["high"].values,
        "low_arr": series["low"].values,
        "volume_arr": series["volume"].values,
        "last_close": series["close"].last(),
        "last_open": series["open"].last(),
        "last_high": series["high"].last(),
        "last_low": series["low"].last(),
    }

    def pct_move(window: int) -> float:
        return _pct_move(series["close"], window)

    def range_pct(window: int) -> float:
        return _range_pct(series["high"], series["low"], window)

    def atr(period: int) -> float:
        return _atr(series["high"], series["low"], series["close"], period)

    def ema(period: int) -> float:
        return _ema(series["close"], period)

    def vwap(session: Any) -> float:
        return _vwap(series["close"], series["volume"], session)

    def zscore(period: int) -> float:
        return _zscore(series["close"], period)

    def slope(period: int) -> float:
        return _slope(series["close"], period)

    def cross(a: Any, b: Any) -> bool:
        return _cross(a, b)

    def rolling_high(period: int) -> float:
        return _rolling_high(series["high"], period)

    def rolling_low(period: int) -> float:
        return _rolling_low(series["low"], period)

    # === NEW INDICATOR FUNCTIONS ===
    
    def rsi(period: int) -> float:
        return _rsi(series["close"], period)
    
    def rsi_prev(period: int, bars_back: int) -> float:
        return _rsi_prev(series["close"], period, bars_back)
    
    def macd_line(fast: int = 12, slow: int = 26) -> float:
        return _macd_line(series["close"], fast, slow)
    
    def macd_signal(fast: int = 12, slow: int = 26, signal: int = 9) -> float:
        return _macd_signal(series["close"], fast, slow, signal)
    
    def macd_histogram(fast: int = 12, slow: int = 26, signal: int = 9) -> float:
        return _macd_histogram(series["close"], fast, slow, signal)
    
    def macd_line_prev(fast: int, slow: int, bars_back: int) -> float:
        return _macd_line_prev(series["close"], fast, slow, bars_back)
    
    def macd_signal_prev(fast: int, slow: int, signal: int, bars_back: int) -> float:
        return _macd_signal_prev(series["close"], fast, slow, signal, bars_back)
    
    def bb_upper(period: int = 20, std_mult: float = 2.0) -> float:
        return _bb_upper(series["close"], period, std_mult)
    
    def bb_lower(period: int = 20, std_mult: float = 2.0) -> float:
        return _bb_lower(series["close"], period, std_mult)
    
    def bb_middle(period: int = 20) -> float:
        return _bb_middle(series["close"], period)
    
    def bb_bandwidth(period: int = 20, std_mult: float = 2.0) -> float:
        return _bb_bandwidth(series["close"], period, std_mult)
    
    def bb_pct(period: int = 20, std_mult: float = 2.0) -> float:
        return _bb_pct(series["close"], period, std_mult)
    
    def sma(period: int) -> float:
        return _sma(series["close"], period)
    
    def ema_prev(period: int, bars_back: int) -> float:
        return _ema_prev(series["close"], period, bars_back)
    
    def sma_prev(period: int, bars_back: int) -> float:
        return _sma_prev(series["close"], period, bars_back)
    
    def volume_ratio(period: int = 20) -> float:
        return _volume_ratio(series["volume"], period)
    
    def stochastic_k(period: int = 14) -> float:
        return _stochastic_k(series["high"], series["low"], series["close"], period)
    
    def stochastic_d(k_period: int = 14, d_period: int = 3) -> float:
        return _stochastic_d(series["high"], series["low"], series["close"], k_period, d_period)
    
    def adx(period: int = 14) -> float:
        return _adx(series["high"], series["low"], series["close"], period)
    
    def min_close(period: int) -> float:
        return _min_close(series["close"], period)
    
    def max_close(period: int) -> float:
        return _max_close(series["close"], period)
    
    def lower_wick_ratio() -> float:
        return _lower_wick_ratio(series["open"], series["high"], series["low"], series["close"])
    
    def upper_wick_ratio() -> float:
        return _upper_wick_ratio(series["open"], series["high"], series["low"], series["close"])
    
    def support_level(period: int = 50) -> float:
        return _support_level(series["low"], period)
    
    def resistance_level(period: int = 50) -> float:
        return _resistance_level(series["high"], period)
    
    def overnight_gap_pct() -> float:
        return _overnight_gap_pct(series["open"], series["close"])
    
    def min_rsi(rsi_period: int, lookback: int) -> float:
        return _min_rsi(series["close"], rsi_period, lookback)

    functions: Dict[str, Callable[..., Any]] = {
        # Original functions
        "pct_move": pct_move,
        "range_pct": range_pct,
        "atr": atr,
        "ema": ema,
        "vwap": vwap,
        "zscore": zscore,
        "slope": slope,
        "cross": cross,
        "rolling_high": rolling_high,
        "rolling_low": rolling_low,
        # RSI
        "rsi": rsi,
        "rsi_prev": rsi_prev,
        "min_rsi": min_rsi,
        # MACD
        "macd_line": macd_line,
        "macd_signal": macd_signal,
        "macd_histogram": macd_histogram,
        "macd_line_prev": macd_line_prev,
        "macd_signal_prev": macd_signal_prev,
        # Bollinger Bands
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "bb_middle": bb_middle,
        "bb_bandwidth": bb_bandwidth,
        "bb_pct": bb_pct,
        # Moving Averages
        "sma": sma,
        "ema_prev": ema_prev,
        "sma_prev": sma_prev,
        # Volume
        "volume_ratio": volume_ratio,
        # Stochastic
        "stochastic_k": stochastic_k,
        "stochastic_d": stochastic_d,
        # ADX
        "adx": adx,
        # Support/Resistance
        "min_close": min_close,
        "max_close": max_close,
        "support_level": support_level,
        "resistance_level": resistance_level,
        # Candlestick
        "lower_wick_ratio": lower_wick_ratio,
        "upper_wick_ratio": upper_wick_ratio,
        # Gap
        "overnight_gap_pct": overnight_gap_pct,
        # Built-in math functions
        "abs": abs,
        "min": min,
        "max": max,
        "round": round,
        "sqrt": lambda x: x ** 0.5,
        "pow": pow,
    }

    return context, functions


def evaluate_pattern(pattern_id: str, bars: List[Dict[str, Any]], logic: Dict[str, Any], params: Dict[str, Any]) -> List[PatternEvent]:
    context, functions = build_context(bars)
    context.update(params)
    evaluator = SafeEvaluator(context, functions)

    signal_expr = logic.get("signal")
    if not signal_expr:
        return []
    signal = bool(evaluator.eval(signal_expr))
    if not signal:
        return []

    score_expr = logic.get("score", "0")
    score = float(evaluator.eval(score_expr))

    tags: Dict[str, Any] = {}
    tags_expr = logic.get("tags", {})
    if isinstance(tags_expr, dict):
        for key, expr in tags_expr.items():
            tags[key] = evaluator.eval(str(expr))

    snapshot = {
        "last_close": context["last_close"],
        "last_open": context["last_open"],
        "last_high": context["last_high"],
        "last_low": context["last_low"],
    }

    return [PatternEvent(pattern_id=pattern_id, score=score, tags=tags, snapshot=snapshot)]
