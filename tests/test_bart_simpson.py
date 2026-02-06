from __future__ import annotations

from core.patterns.plugins import BartSimpsonDetector


def test_bart_simpson_detector_stub() -> None:
    detector = BartSimpsonDetector()
    bars = []
    price = 100.0
    for idx in range(20):
        if idx < 5:
            price += 0.5
        elif idx < 11:
            price += 0.0
        else:
            price -= 0.4
        bars.append({"c": price, "o": price - 0.1, "h": price + 0.2, "l": price - 0.2, "v": 1000})
    events = detector.detect(bars, {"impulse_threshold": 0.5, "shelf_max_range": 0.6, "reversion_threshold": -0.2})
    assert isinstance(events, list)
