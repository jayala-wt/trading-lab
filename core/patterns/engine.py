from __future__ import annotations

from typing import Any, Dict, List

from core.config.models import PatternConfig
from core.patterns.base import PatternEvent
from core.patterns.plugins import PLUGIN_REGISTRY
from core.patterns.primitives_engine import evaluate_pattern


def detect_pattern(pattern: PatternConfig, bars: List[Dict[str, Any]]) -> List[PatternEvent]:
    if pattern.implementation == "plugin":
        plugin_key = pattern.plugin_class or pattern.id
        detector = PLUGIN_REGISTRY.get(plugin_key)
        if not detector:
            return []
        return detector.detect(bars, pattern.params)
    return evaluate_pattern(pattern.id, bars, pattern.logic, pattern.params)
