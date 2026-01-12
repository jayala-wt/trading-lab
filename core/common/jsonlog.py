from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


class JsonLogHandler(logging.Handler):
    def __init__(self, log_path: Path) -> None:
        super().__init__()
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, record: logging.LogRecord) -> None:
        payload: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            payload.update(record.extra)
        line = json.dumps(payload, ensure_ascii=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def get_json_logger(name: str, log_path: Path, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(level)
    handler = JsonLogHandler(log_path)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def log_with_extra(logger: logging.Logger, level: int, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
    record_extra = {"extra": extra or {}}
    logger.log(level, message, extra=record_extra)
