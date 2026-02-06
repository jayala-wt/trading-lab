"""
Signal Quality Report - Statistical analysis of pattern performance.

Per audit recommendation: Before ML, analyze patterns statistically:
- Win rate
- Average return
- Average drawdown
- Performance by dimension state

This helps identify which patterns are noise vs regime-dependent.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from core.data.db import Database


@dataclass
class PatternStats:
    """Statistical performance metrics for a pattern."""
    pattern_id: str
    total_signals: int
    signals_with_outcome: int
    
    # Win rate (positive outcome_60m)
    win_count: int
    loss_count: int
    win_rate: float  # 0.0 - 1.0
    
    # Returns
    avg_return_5m: float
    avg_return_15m: float
    avg_return_60m: float
    
    # Risk metrics
    avg_drawdown: float
    avg_favorable: float
    max_drawdown: float
    
    # Expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
    expectancy: float
    
    # Performance by dimension state (optional breakdown)
    by_momentum: Dict[str, Dict[str, float]] = None
    by_trend: Dict[str, Dict[str, float]] = None
    by_volatility: Dict[str, Dict[str, float]] = None


def get_pattern_stats(db: Database, pattern_id: str) -> Optional[PatternStats]:
    """
    Compute statistical performance for a single pattern.
    """
    # Get all signals with outcomes for this pattern
    rows = db.query(
        """
        SELECT 
            outcome_5m, outcome_15m, outcome_60m,
            max_drawdown, max_favorable,
            snapshot_json, tags_json
        FROM signals 
        WHERE pattern_id = ? 
          AND outcome_60m IS NOT NULL
        """,
        (pattern_id,),
    )
    
    total = db.query(
        "SELECT COUNT(*) as cnt FROM signals WHERE pattern_id = ?",
        (pattern_id,),
    )[0]["cnt"]
    
    if not rows:
        return PatternStats(
            pattern_id=pattern_id,
            total_signals=total,
            signals_with_outcome=0,
            win_count=0,
            loss_count=0,
            win_rate=0.0,
            avg_return_5m=0.0,
            avg_return_15m=0.0,
            avg_return_60m=0.0,
            avg_drawdown=0.0,
            avg_favorable=0.0,
            max_drawdown=0.0,
            expectancy=0.0,
        )
    
    n = len(rows)
    
    # Calculate metrics
    returns_5m = [r["outcome_5m"] for r in rows if r["outcome_5m"] is not None]
    returns_15m = [r["outcome_15m"] for r in rows if r["outcome_15m"] is not None]
    returns_60m = [r["outcome_60m"] for r in rows if r["outcome_60m"] is not None]
    drawdowns = [r["max_drawdown"] for r in rows if r["max_drawdown"] is not None]
    favorables = [r["max_favorable"] for r in rows if r["max_favorable"] is not None]
    
    wins = [r for r in returns_60m if r > 0]
    losses = [r for r in returns_60m if r <= 0]
    
    win_rate = len(wins) / len(returns_60m) if returns_60m else 0.0
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0
    
    # Expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
    expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
    
    return PatternStats(
        pattern_id=pattern_id,
        total_signals=total,
        signals_with_outcome=n,
        win_count=len(wins),
        loss_count=len(losses),
        win_rate=win_rate,
        avg_return_5m=sum(returns_5m) / len(returns_5m) if returns_5m else 0.0,
        avg_return_15m=sum(returns_15m) / len(returns_15m) if returns_15m else 0.0,
        avg_return_60m=sum(returns_60m) / len(returns_60m) if returns_60m else 0.0,
        avg_drawdown=sum(drawdowns) / len(drawdowns) if drawdowns else 0.0,
        avg_favorable=sum(favorables) / len(favorables) if favorables else 0.0,
        max_drawdown=min(drawdowns) if drawdowns else 0.0,
        expectancy=expectancy,
    )


def get_pattern_stats_by_dimension(
    db: Database, 
    pattern_id: str, 
    dimension: str
) -> Dict[str, Dict[str, float]]:
    """
    Break down pattern performance by dimension state.
    
    Example: How does `dim_momentum_reversal_buy` perform when volatility is COMPRESSED vs EXPANDING?
    """
    rows = db.query(
        """
        SELECT outcome_60m, max_drawdown, snapshot_json
        FROM signals 
        WHERE pattern_id = ? 
          AND outcome_60m IS NOT NULL
          AND snapshot_json IS NOT NULL
        """,
        (pattern_id,),
    )
    
    # Group by dimension state
    by_state: Dict[str, List[Dict[str, float]]] = {}
    
    for row in rows:
        try:
            snapshot = json.loads(row["snapshot_json"])
            dim_states = snapshot.get("dimension_states", {})
            state = dim_states.get(dimension, "unknown")
            
            if state not in by_state:
                by_state[state] = []
            
            by_state[state].append({
                "return": row["outcome_60m"],
                "drawdown": row["max_drawdown"] or 0,
            })
        except:
            continue
    
    # Compute stats per state
    result = {}
    for state, entries in by_state.items():
        returns = [e["return"] for e in entries]
        drawdowns = [e["drawdown"] for e in entries]
        wins = [r for r in returns if r > 0]
        
        result[state] = {
            "count": len(entries),
            "win_rate": len(wins) / len(returns) if returns else 0,
            "avg_return": sum(returns) / len(returns) if returns else 0,
            "avg_drawdown": sum(drawdowns) / len(drawdowns) if drawdowns else 0,
        }
    
    return result


def generate_quality_report(db: Database) -> Dict[str, Any]:
    """
    Generate a comprehensive signal quality report for all patterns.
    """
    # Get all patterns
    patterns = db.query("SELECT DISTINCT pattern_id FROM signals")
    
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "patterns": {},
        "summary": {
            "total_patterns": 0,
            "patterns_with_data": 0,
            "best_pattern": None,
            "worst_pattern": None,
            "avg_expectancy": 0.0,
        }
    }
    
    all_expectancies = []
    
    for p in patterns:
        pid = p["pattern_id"]
        stats = get_pattern_stats(db, pid)
        
        if stats and stats.signals_with_outcome > 0:
            report["patterns"][pid] = {
                "total_signals": stats.total_signals,
                "with_outcome": stats.signals_with_outcome,
                "win_rate": round(stats.win_rate * 100, 1),
                "avg_return_60m": round(stats.avg_return_60m, 3),
                "avg_drawdown": round(stats.avg_drawdown, 3),
                "expectancy": round(stats.expectancy, 3),
                "max_drawdown": round(stats.max_drawdown, 3),
            }
            all_expectancies.append((pid, stats.expectancy))
    
    report["summary"]["total_patterns"] = len(patterns)
    report["summary"]["patterns_with_data"] = len(report["patterns"])
    
    if all_expectancies:
        all_expectancies.sort(key=lambda x: x[1], reverse=True)
        report["summary"]["best_pattern"] = all_expectancies[0][0]
        report["summary"]["worst_pattern"] = all_expectancies[-1][0]
        report["summary"]["avg_expectancy"] = round(
            sum(e[1] for e in all_expectancies) / len(all_expectancies), 3
        )
    
    return report


def format_quality_report(report: Dict[str, Any]) -> str:
    """Format quality report as human-readable text."""
    lines = [
        "=" * 60,
        "📊 SIGNAL QUALITY REPORT",
        f"Generated: {report['generated_at']}",
        "=" * 60,
        "",
        f"Total Patterns: {report['summary']['total_patterns']}",
        f"Patterns with Data: {report['summary']['patterns_with_data']}",
        f"Best Pattern: {report['summary']['best_pattern']}",
        f"Worst Pattern: {report['summary']['worst_pattern']}",
        f"Avg Expectancy: {report['summary']['avg_expectancy']}%",
        "",
        "-" * 60,
        "PATTERN BREAKDOWN",
        "-" * 60,
    ]
    
    # Sort by expectancy
    sorted_patterns = sorted(
        report["patterns"].items(),
        key=lambda x: x[1].get("expectancy", 0),
        reverse=True
    )
    
    for pid, stats in sorted_patterns:
        grade = "🟢" if stats["expectancy"] > 0.1 else "🟡" if stats["expectancy"] > 0 else "🔴"
        lines.append(f"\n{grade} {pid}")
        lines.append(f"   Signals: {stats['with_outcome']}/{stats['total_signals']}")
        lines.append(f"   Win Rate: {stats['win_rate']}%")
        lines.append(f"   Avg Return (60m): {stats['avg_return_60m']}%")
        lines.append(f"   Expectancy: {stats['expectancy']}%")
        lines.append(f"   Max Drawdown: {stats['max_drawdown']}%")
    
    lines.append("")
    lines.append("=" * 60)
    
    return "\n".join(lines)


# CLI entry point
if __name__ == "__main__":
    from pathlib import Path
    from core.data.db import Database
    
    db_path = Path(__file__).parent.parent.parent / "data" / "market.db"
    db = Database(db_path)
    
    report = generate_quality_report(db)
    print(format_quality_report(report))
