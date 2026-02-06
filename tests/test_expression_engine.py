from __future__ import annotations

from core.patterns.primitives_engine import evaluate_pattern


def test_primitives_expression_engine_basic() -> None:
    bars = [
        {"c": 100, "o": 99, "h": 101, "l": 98, "v": 1000},
        {"c": 102, "o": 101, "h": 103, "l": 100, "v": 1100},
    ]
    logic = {
        "signal": "pct_move(1) > 0",
        "score": "pct_move(1)",
    }
    events = evaluate_pattern("test", bars, logic, {})
    assert len(events) == 1
    assert events[0].score > 0
