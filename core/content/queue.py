from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def write_content_queue(
    base_dir: Path,
    bot_id: str,
    symbol: str,
    image_path: Path,
    captions: List[str],
    metadata: Dict[str, Any],
    ts: Optional[str] = None,
) -> Path:
    if ts is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    date_folder = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    file_name = f"{symbol}_{ts}.json".replace("/", "-")
    output_path = base_dir / date_folder / bot_id / file_name
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "image_path": str(image_path),
        "captions": captions,
        "metadata": metadata,
        "ts": ts,
    }
    output_path.write_text(json.dumps(payload, indent=2))
    return output_path
