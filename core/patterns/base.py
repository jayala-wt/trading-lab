from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Protocol


@dataclass
class PatternEvent:
    pattern_id: str
    score: float
    tags: Dict[str, Any]
    snapshot: Dict[str, Any]


class PatternDetector(Protocol):
    def detect(self, bars: List[Dict[str, Any]], params: Dict[str, Any]) -> List[PatternEvent]:
        ...
