"""
Cloud ML Export - Export training data to Namecheap Stellar DB.

This module handles exporting ML training data to cloud storage
for backup and sharing across systems. The data grows over time,
creating a comprehensive crash pattern database.

Usage:
    python -m core.ml.cloud_export --export full
    python -m core.ml.cloud_export --export incremental
    python -m core.ml.cloud_export --list-exports
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.common.env import load_dotenv
from core.common.paths import repo_root
from core.data.db import Database


def export_training_data(
    db: Database,
    output_path: Path,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    compress: bool = True,
) -> Dict[str, Any]:
    """
    Export ML training data to CSV.
    
    Args:
        db: Database connection
        output_path: Output file path
        start_date: Optional start date filter (YYYY-MM-DD)
        end_date: Optional end date filter (YYYY-MM-DD)
        compress: Whether to gzip compress the output
    
    Returns:
        Export statistics
    """
    # Build query
    where_clauses = []
    params = []
    
    if start_date:
        where_clauses.append("DATE(created_at) >= ?")
        params.append(start_date)
    
    if end_date:
        where_clauses.append("DATE(created_at) <= ?")
        params.append(end_date)
    
    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
    
    query = f"""
    SELECT 
        id, created_at, signal_id, symbol, pattern_id,
        dim_momentum, dim_trend, dim_volatility, dim_participation, dim_location, dim_structure,
        raw_rsi, raw_stoch_k, raw_macd_histogram, raw_ema_9, raw_ema_21, raw_ema_50,
        raw_slope_20, raw_atr_pct, raw_bb_bandwidth, raw_bb_pct, raw_volume_ratio, raw_vwap_distance_pct,
        entry_price, entry_ts,
        outcome_5m, outcome_15m, outcome_60m, max_drawdown, max_favorable,
        label_profitable_5m, label_profitable_15m, label_profitable_60m, label_quality,
        direction, confidence, led_to_trade
    FROM ml_training_samples
    WHERE {where_sql}
    ORDER BY created_at ASC
    """
    
    rows = db.query(query, tuple(params))
    
    if not rows:
        print("No data to export")
        return {"count": 0, "size_bytes": 0}
    
    # Determine output file
    if compress and not str(output_path).endswith(".gz"):
        output_path = Path(str(output_path) + ".gz")
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write CSV
    keys = rows[0].keys()
    
    if compress:
        with gzip.open(output_path, "wt", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))
    else:
        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))
    
    size_bytes = output_path.stat().st_size
    
    stats = {
        "count": len(rows),
        "size_bytes": size_bytes,
        "size_kb": size_bytes / 1024,
        "size_mb": size_bytes / (1024 * 1024),
        "output_path": str(output_path),
        "start_date": start_date,
        "end_date": end_date,
        "compressed": compress,
    }
    
    return stats


def list_exports(export_dir: Path) -> List[Dict[str, Any]]:
    """List all export files in the export directory."""
    if not export_dir.exists():
        return []
    
    exports = []
    
    for file in sorted(export_dir.glob("*.csv*"), reverse=True):
        size_bytes = file.stat().st_size
        mtime = datetime.fromtimestamp(file.stat().st_mtime)
        
        exports.append({
            "filename": file.name,
            "path": str(file),
            "size_mb": size_bytes / (1024 * 1024),
            "modified": mtime.isoformat(),
            "compressed": file.suffix == ".gz",
        })
    
    return exports


def generate_upload_instructions(export_path: Path) -> str:
    """Generate instructions for uploading to Namecheap Stellar DB."""
    
    instructions = f"""
╔════════════════════════════════════════════════════════════════╗
║  NAMECHEAP STELLAR DB UPLOAD INSTRUCTIONS                      ║
╚════════════════════════════════════════════════════════════════╝

📁 File ready for upload: {export_path.name}
💾 Size: {export_path.stat().st_size / (1024*1024):.2f} MB

🌐 UPLOAD OPTIONS:

Option 1: Web Dashboard Upload
  1. Visit: https://www.namecheap.com/hosting/stellar-db/
  2. Log in to your account
  3. Navigate to "Databases" → "Your Database"
  4. Click "Upload Data"
  5. Select file: {export_path}

Option 2: CLI Upload (if Stellar DB CLI is installed)
  $ stellar-db upload {export_path} --database trading-ml

Option 3: API Upload (using curl)
  $ curl -X POST \\
      -H "Authorization: Bearer YOUR_API_KEY" \\
      -F "file=@{export_path}" \\
      https://api.stellar.namecheap.com/v1/upload

Option 4: S3-Compatible Upload (if configured)
  $ aws s3 cp {export_path} \\
      s3://your-stellar-bucket/ml-training/

💡 TIPS:
  • Store API key in environment: export STELLAR_DB_API_KEY=...
  • Set up automated uploads with cron
  • Keep versioned backups with timestamps
  • Compress large files with gzip to save storage

📊 RECOMMENDED NAMING CONVENTION:
  crash_training_YYYYMMDD_samples.csv.gz
  
  Example: crash_training_20260214_1523_samples.csv.gz

🔗 USEFUL LINKS:
  • Stellar DB Docs: https://docs.stellar.namecheap.com/
  • API Reference: https://api-docs.stellar.namecheap.com/
  • Pricing: https://www.namecheap.com/hosting/stellar-db/pricing/
"""
    
    return instructions


def main():
    parser = argparse.ArgumentParser(description="Export ML training data to cloud")
    parser.add_argument(
        "--export",
        choices=["full", "incremental", "custom"],
        help="Type of export to perform",
    )
    parser.add_argument(
        "--start-date",
        help="Start date for custom export (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        help="End date for custom export (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--list-exports",
        action="store_true",
        help="List all existing exports",
    )
    parser.add_argument(
        "--no-compress",
        action="store_true",
        help="Don't compress output (default: compress with gzip)",
    )
    parser.add_argument(
        "--output",
        help="Custom output path (default: auto-generated in data/ml_exports/)",
    )
    
    args = parser.parse_args()
    
    load_dotenv()
    db = Database()
    export_dir = repo_root() / "trading-lab" / "data" / "ml_exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    
    if args.list_exports:
        print("\n📋 ML TRAINING DATA EXPORTS")
        print("=" * 80)
        
        exports = list_exports(export_dir)
        
        if not exports:
            print("No exports found")
            return
        
        for exp in exports:
            print(f"\n📁 {exp['filename']}")
            print(f"   Size: {exp['size_mb']:.2f} MB")
            print(f"   Modified: {exp['modified']}")
            print(f"   Compressed: {exp['compressed']}")
            print(f"   Path: {exp['path']}")
        
        print(f"\n📊 Total exports: {len(exports)}")
        total_mb = sum(e['size_mb'] for e in exports)
        print(f"💾 Total size: {total_mb:.2f} MB")
        print()
        return
    
    if not args.export:
        parser.print_help()
        return
    
    # Determine date range
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if args.export == "full":
        start_date = None
        end_date = None
        filename = f"crash_training_full_{timestamp}.csv"
        print("\n📦 Exporting FULL dataset...")
    
    elif args.export == "incremental":
        # Last 30 days
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        end_date = datetime.now().strftime("%Y-%m-%d")
        filename = f"crash_training_incremental_{timestamp}.csv"
        print(f"\n📦 Exporting INCREMENTAL dataset (last 30 days)...")
    
    else:  # custom
        start_date = args.start_date
        end_date = args.end_date
        filename = f"crash_training_custom_{timestamp}.csv"
        print(f"\n📦 Exporting CUSTOM dataset...")
        if start_date:
            print(f"   Start: {start_date}")
        if end_date:
            print(f"   End: {end_date}")
    
    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = export_dir / filename
    
    # Export
    print()
    stats = export_training_data(
        db,
        output_path,
        start_date,
        end_date,
        compress=not args.no_compress,
    )
    
    if stats["count"] == 0:
        return
    
    # Print results
    print("\n✅ EXPORT COMPLETE!")
    print("=" * 80)
    print(f"📁 File: {stats['output_path']}")
    print(f"📊 Samples: {stats['count']:,}")
    print(f"💾 Size: {stats['size_mb']:.2f} MB")
    if stats.get("compressed"):
        print(f"🗜️  Compressed: Yes (gzip)")
    
    # Print upload instructions
    print(generate_upload_instructions(Path(stats["output_path"])))


if __name__ == "__main__":
    main()
