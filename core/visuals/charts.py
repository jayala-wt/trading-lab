from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def generate_chart(
    bars: List[Dict[str, Any]],
    output_path: Path,
    title: Optional[str] = None,
) -> Path:
    closes = [float(bar.get("c") or bar.get("close") or 0.0) for bar in bars]
    if not closes:
        closes = [0.0]
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(closes, color="#7fb069", linewidth=1.6)
    ax.set_facecolor("#0f1419")
    fig.patch.set_facecolor("#0f1419")
    ax.tick_params(colors="#9aa5b1")
    for spine in ax.spines.values():
        spine.set_color("#334155")
    if title:
        ax.set_title(title, color="#e2e8f0")
    ax.grid(True, color="#1f2937", alpha=0.4)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=120)
    plt.close(fig)
    return output_path


def dated_chart_path(base_dir: Path, bot_id: str, symbol: str, ts: Optional[str] = None) -> Path:
    if ts is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    date_folder = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    file_name = f"{symbol}_{ts}.png".replace("/", "-")
    return base_dir / date_folder / bot_id / file_name
