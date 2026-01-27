#!/usr/bin/env python3
"""
Dataset Snapshot - Create immutable backup before training.

Creates a timestamped SQLite backup of ml_training_samples table for:
- Reproducibility (can retrain exact model later)
- Version control (track dataset evolution)
- Rollback capability (if training goes wrong)

Usage:
    python3 scripts/snapshot_dataset.py
    python3 scripts/snapshot_dataset.py --name "pre_modelA_training"
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import shutil
import argparse
from datetime import datetime

from core.common.env import load_dotenv
from core.common.paths import repo_root
from core.data.db import Database


def snapshot_dataset(db_path: Path, snapshot_name: str = None) -> Path:
    """Create a snapshot of the training dataset."""
    
    # Create snapshots directory
    snapshots_dir = repo_root() / "trading-lab" / "data" / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate snapshot filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if snapshot_name:
        filename = f"{snapshot_name}_{timestamp}.sqlite"
    else:
        filename = f"dataset_snapshot_{timestamp}.sqlite"
    
    snapshot_path = snapshots_dir / filename
    
    # Create backup using SQLite's backup API
    print(f"📸 Creating dataset snapshot...")
    print(f"   Source: {db_path}")
    print(f"   Destination: {snapshot_path}")
    
    shutil.copy2(db_path, snapshot_path)
    
    # Get snapshot stats
    db = Database(snapshot_path)
    query = "SELECT COUNT(*) as count FROM ml_training_samples"
    row = db.query(query)[0]
    sample_count = row['count']
    
    query2 = "SELECT MIN(created_at) as first, MAX(created_at) as last FROM ml_training_samples"
    row2 = db.query(query2)[0]
    
    file_size_mb = snapshot_path.stat().st_size / (1024 * 1024)
    
    print(f"\n✅ Snapshot created successfully!")
    print(f"   Samples: {sample_count:,}")
    print(f"   Date range: {row2['first']} to {row2['last']}")
    print(f"   File size: {file_size_mb:.2f} MB")
    print(f"   Location: {snapshot_path}")
    
    # Create metadata file
    metadata_path = snapshot_path.with_suffix('.metadata.txt')
    with open(metadata_path, 'w') as f:
        f.write(f"Dataset Snapshot Metadata\n")
        f.write(f"========================\n\n")
        f.write(f"Created: {datetime.now().isoformat()}\n")
        f.write(f"Source: {db_path}\n")
        f.write(f"Snapshot: {snapshot_path}\n")
        f.write(f"Name: {snapshot_name or 'default'}\n\n")
        f.write(f"Dataset Stats:\n")
        f.write(f"  Total samples: {sample_count:,}\n")
        f.write(f"  Date range: {row2['first']} to {row2['last']}\n")
        f.write(f"  File size: {file_size_mb:.2f} MB\n\n")
        f.write(f"Purpose:\n")
        f.write(f"  This snapshot captures the exact dataset state before model training.\n")
        f.write(f"  Use it to reproduce model training results or roll back if needed.\n\n")
        f.write(f"To restore:\n")
        f.write(f"  cp {snapshot_path} {db_path}\n")
    
    print(f"\n📝 Metadata saved: {metadata_path}")
    
    return snapshot_path


def list_snapshots():
    """List all existing snapshots."""
    snapshots_dir = repo_root() / "trading-lab" / "data" / "snapshots"
    
    if not snapshots_dir.exists():
        print("No snapshots directory found")
        return
    
    snapshots = sorted(snapshots_dir.glob("*.sqlite"), reverse=True)
    
    if not snapshots:
        print("No snapshots found")
        return
    
    print(f"\n📋 Existing Snapshots ({len(snapshots)}):")
    print("=" * 70)
    
    for snapshot in snapshots:
        # Get metadata if exists
        metadata_path = snapshot.with_suffix('.sqlite.metadata.txt')
        
        size_mb = snapshot.stat().st_size / (1024 * 1024)
        created = datetime.fromtimestamp(snapshot.stat().st_mtime)
        
        print(f"\n{snapshot.name}")
        print(f"  Created: {created.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Size: {size_mb:.2f} MB")
        
        if metadata_path.exists():
            # Extract sample count from metadata
            with open(metadata_path) as f:
                for line in f:
                    if 'Total samples:' in line:
                        print(f"  {line.strip()}")
                        break


def main():
    parser = argparse.ArgumentParser(description='Create dataset snapshot')
    parser.add_argument(
        '--name',
        help='Optional name for snapshot (e.g., "pre_modelA_training")'
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='List existing snapshots'
    )
    
    args = parser.parse_args()
    
    load_dotenv(repo_root() / ".env")
    
    if args.list:
        list_snapshots()
        return
    
    db_path = Path(os.getenv("TRADING_LAB_DB_PATH", str(repo_root() / "data" / "market.db")))
    
    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        return
    
    snapshot_path = snapshot_dataset(db_path, args.name)
    
    print(f"\n💡 Recommended: Reference this snapshot in model_card.md")
    print(f"   Dataset version: {snapshot_path.stem}")


if __name__ == "__main__":
    main()
