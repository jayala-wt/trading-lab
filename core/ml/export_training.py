"""
ML Training Data Export - Export signals with outcomes for model training.

Usage:
    python -m core.ml.export_training --format csv --output training_data.csv
    python -m core.ml.export_training --format json --output training_data.json
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List

from core.common.env import load_dotenv
from core.common.paths import repo_root
from core.data.db import Database, export_ml_training_data, get_pattern_performance


def flatten_dimensions(data: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten dimension snapshot into individual features."""
    flattened = {}
    
    # Add states as categorical features
    states = data.get("dimensions", {}).get("states", {})
    for dim_name, state_value in states.items():
        flattened[f"dim_{dim_name}"] = state_value
    
    # Add raw values as numeric features
    raw = data.get("dimensions", {}).get("raw", {})
    for dim_name, raw_values in raw.items():
        if isinstance(raw_values, dict):
            for key, value in raw_values.items():
                flattened[f"raw_{dim_name}_{key}"] = value
    
    return flattened


def export_to_csv(data: List[Dict[str, Any]], output_path: Path) -> None:
    """Export training data to CSV format."""
    if not data:
        print("No data to export")
        return
    
    # Flatten first record to get columns
    sample = data[0].copy()
    flat_sample = flatten_dimensions(sample)
    sample.update(flat_sample)
    del sample["dimensions"]  # Remove nested dict
    
    fieldnames = list(sample.keys())
    
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for record in data:
            flat = flatten_dimensions(record)
            record_copy = record.copy()
            record_copy.update(flat)
            del record_copy["dimensions"]
            writer.writerow(record_copy)
    
    print(f"Exported {len(data)} records to {output_path}")


def export_to_json(data: List[Dict[str, Any]], output_path: Path) -> None:
    """Export training data to JSON format."""
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    
    print(f"Exported {len(data)} records to {output_path}")


def print_summary(data: List[Dict[str, Any]]) -> None:
    """Print summary statistics of training data."""
    if not data:
        print("No training data available yet")
        return
    
    print(f"\n{'='*60}")
    print("ML TRAINING DATA SUMMARY")
    print(f"{'='*60}")
    print(f"Total samples: {len(data)}")
    
    # Count by pattern
    pattern_counts: Dict[str, int] = {}
    for record in data:
        pid = record.get("pattern_id", "unknown")
        pattern_counts[pid] = pattern_counts.get(pid, 0) + 1
    
    print(f"\nSamples by pattern:")
    for pid, count in sorted(pattern_counts.items(), key=lambda x: -x[1]):
        print(f"  {pid}: {count}")
    
    # Outcome statistics
    outcomes_60m = [r["outcome_60m"] for r in data if r.get("outcome_60m") is not None]
    if outcomes_60m:
        avg = sum(outcomes_60m) / len(outcomes_60m)
        wins = len([o for o in outcomes_60m if o > 0])
        win_rate = wins / len(outcomes_60m) * 100
        print(f"\nOutcome statistics (60m):")
        print(f"  Average return: {avg:.2f}%")
        print(f"  Win rate: {win_rate:.1f}%")
        print(f"  Min: {min(outcomes_60m):.2f}%")
        print(f"  Max: {max(outcomes_60m):.2f}%")
    
    print(f"{'='*60}\n")


def print_pattern_performance(db: Database) -> None:
    """Print aggregated pattern performance."""
    perf = get_pattern_performance(db)
    
    if not perf:
        print("No pattern performance data available yet")
        return
    
    print(f"\n{'='*60}")
    print("PATTERN PERFORMANCE (by 60m returns)")
    print(f"{'='*60}")
    print(f"{'Pattern':<30} {'Count':>6} {'Avg 60m':>8} {'Win%':>6} {'Avg DD':>8}")
    print("-" * 60)
    
    for p in perf:
        print(f"{p['pattern_id']:<30} {p['signal_count']:>6} {p['avg_ret_60m']:>7.2f}% {p['win_rate']*100:>5.1f}% {p['avg_drawdown']:>7.2f}%")
    
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Export ML training data")
    parser.add_argument("--format", choices=["csv", "json"], default="json", help="Output format")
    parser.add_argument("--output", type=str, help="Output file path")
    parser.add_argument("--summary", action="store_true", help="Print summary only")
    parser.add_argument("--performance", action="store_true", help="Print pattern performance")
    args = parser.parse_args()
    
    load_dotenv(repo_root() / ".env")
    
    db_path = repo_root() / "data" / "market.db"
    db = Database(db_path)
    
    if args.performance:
        print_pattern_performance(db)
        return
    
    data = export_ml_training_data(db)
    print_summary(data)
    
    if args.summary:
        return
    
    if args.output:
        output_path = Path(args.output)
        if args.format == "csv":
            export_to_csv(data, output_path)
        else:
            export_to_json(data, output_path)
    else:
        # Print to stdout
        print(json.dumps(data, indent=2, default=str))


if __name__ == "__main__":
    main()
