from __future__ import annotations

from typing import Any, Dict, List

from core.patterns.base import PatternEvent, PatternDetector


class BartSimpsonDetector:
    def detect(self, bars: List[Dict[str, Any]], params: Dict[str, Any]) -> List[PatternEvent]:
        if len(bars) < 15:
            return []
        closes = [float(bar.get("c") or bar.get("close") or 0.0) for bar in bars]
        impulse = params.get("impulse", 5)
        shelf = params.get("shelf", 5)
        reversion = params.get("reversion", 5)
        if len(closes) < impulse + shelf + reversion:
            return []
        segment = closes[-(impulse + shelf + reversion) :]
        impulse_segment = segment[:impulse]
        shelf_segment = segment[impulse : impulse + shelf]
        reversion_segment = segment[-reversion:]

        impulse_move = impulse_segment[-1] - impulse_segment[0]
        shelf_range = max(shelf_segment) - min(shelf_segment)
        reversion_move = reversion_segment[-1] - reversion_segment[0]

        impulse_threshold = params.get("impulse_threshold", 0.8)
        shelf_max_range = params.get("shelf_max_range", 0.3)
        reversion_threshold = params.get("reversion_threshold", -0.5)

        if impulse_move <= impulse_threshold:
            return []
        if shelf_range >= shelf_max_range:
            return []
        if reversion_move >= reversion_threshold:
            return []

        score = float(abs(impulse_move) + abs(reversion_move))
        tags = {
            "impulse_move": impulse_move,
            "shelf_range": shelf_range,
            "reversion_move": reversion_move,
        }
        snapshot = {
            "last_close": closes[-1],
            "impulse": impulse,
            "shelf": shelf,
            "reversion": reversion,
        }
        return [PatternEvent(pattern_id="bart_simpson", score=score, tags=tags, snapshot=snapshot)]


PLUGIN_REGISTRY = {
    "bart_simpson": BartSimpsonDetector(),
}
