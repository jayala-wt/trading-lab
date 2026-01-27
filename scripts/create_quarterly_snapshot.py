#!/usr/bin/env python3
"""
Quarterly Snapshot Creator - Create immutable ML dataset + model bundles.

This creates versioned, compressed, encrypted snapshots of your valuable ML work:
- Engineered training datasets
- Trained models
- Backtest results
- Configuration

Philosophy: Cold archives, not live sync. Monthly/quarterly snapshots.

Usage:
    # Create Q1 2026 snapshot
    python scripts/create_quarterly_snapshot.py --quarter 2026_Q1
    
    # Auto-detect current quarter
    python scripts/create_quarterly_snapshot.py --auto
    
    # Add encryption with password
    python scripts/create_quarterly_snapshot.py --auto --encrypt
"""
from __future__ import annotations

import argparse
import json
import shutil
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from core.common.env import load_dotenv
from core.common.paths import repo_root
from core.data.db import Database


def get_current_quarter() -> str:
    """Get current quarter identifier (YYYY_QX)."""
    now = datetime.now()
    quarter = (now.month - 1) // 3 + 1
    return f"{now.year}_Q{quarter}"


def create_snapshot_directory(quarter: str) -> Path:
    """Create snapshot directory structure."""
    snapshot_root = repo_root() / "trading-lab" / "snapshots"
    snapshot_dir = snapshot_root / quarter
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    return snapshot_dir


def export_training_dataset(db: Database, snapshot_dir: Path, quarter: str) -> Dict:
    """Export ML training samples to parquet."""
    import pandas as pd
    
    print(f"\n📊 Exporting training dataset...")
    
    # Get all samples with outcomes
    rows = db.query(
        """
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
        WHERE outcome_5m IS NOT NULL
        ORDER BY created_at ASC
        """
    )
    
    if not rows:
        print("⚠️  No training data to export")
        return {"count": 0}
    
    df = pd.DataFrame([dict(row) for row in rows])
    
    # Save as parquet (efficient compression + preserves types)
    dataset_path = snapshot_dir / "ml_training_dataset.parquet"
    df.to_parquet(dataset_path, compression="gzip", index=False)
    
    size_mb = dataset_path.stat().st_size / (1024 * 1024)
    
    print(f"✅ Exported {len(df)} samples to {dataset_path.name}")
    print(f"   Size: {size_mb:.2f} MB")
    
    # Also save crash window specifically (high-value subset)
    crash_window = df[
        (df["created_at"] >= "2026-02-03") & 
        (df["created_at"] <= "2026-02-06")
    ]
    
    if len(crash_window) > 0:
        crash_path = snapshot_dir / "crash_window_feb3-6.parquet"
        crash_window.to_parquet(crash_path, compression="gzip", index=False)
        print(f"✅ Exported {len(crash_window)} crash samples to {crash_path.name}")
    
    return {
        "count": len(df),
        "size_mb": size_mb,
        "date_range": f"{df['created_at'].min()} to {df['created_at'].max()}",
        "crash_samples": len(crash_window),
    }


def copy_model_artifacts(snapshot_dir: Path) -> Dict:
    """Copy trained model files."""
    print(f"\n🤖 Copying model artifacts...")
    
    model_dir = repo_root() / "trading-lab" / "models" / "crash_predictor"
    
    if not model_dir.exists():
        print("⚠️  No trained model found")
        return {"exists": False}
    
    # Copy model files
    artifacts = ["crash_predictor.joblib", "encoders.joblib", "metadata.json"]
    
    for artifact in artifacts:
        src = model_dir / artifact
        if src.exists():
            dst = snapshot_dir / artifact
            shutil.copy2(src, dst)
            print(f"✅ Copied {artifact}")
    
    # Load metadata for summary
    metadata_path = snapshot_dir / "metadata.json"
    if metadata_path.exists():
        with open(metadata_path) as f:
            metadata = json.load(f)
        
        return {
            "exists": True,
            "trained_at": metadata.get("trained_at"),
            "roc_auc": metadata.get("metrics", {}).get("roc_auc", 0),
            "precision": metadata.get("metrics", {}).get("precision", 0),
        }
    
    return {"exists": True}


def save_snapshot_config(snapshot_dir: Path, quarter: str, stats: Dict) -> None:
    """Save snapshot metadata and configuration."""
    print(f"\n📝 Creating snapshot configuration...")
    
    # Load current config (if exists)
    config_src = repo_root() / "trading-lab" / "configs"
    
    config = {
        "quarter": quarter,
        "created_at": datetime.now().isoformat(),
        "dataset_stats": stats.get("dataset", {}),
        "model_stats": stats.get("model", {}),
        "description": f"Trading Lab ML snapshot for {quarter}",
        "reproducibility": {
            "python_version": "3.10+",
            "key_dependencies": [
                "scikit-learn>=1.3.0",
                "pandas>=2.0.0",
                "numpy>=1.24.0",
            ],
        },
    }
    
    config_path = snapshot_dir / "snapshot_config.yaml"
    
    import yaml
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)
    
    print(f"✅ Saved snapshot config to {config_path.name}")
    
    # Create README
    readme_path = snapshot_dir / "README.md"
    with open(readme_path, "w") as f:
        f.write(f"""# Trading Lab Snapshot - {quarter}

Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Contents

- `ml_training_dataset.parquet` - Engineered ML training samples ({stats['dataset'].get('count', 0)} samples)
- `crash_window_feb3-6.parquet` - High-value crash period data
- `crash_predictor.joblib` - Trained Random Forest model
- `encoders.joblib` - Feature encoders
- `metadata.json` - Model training metrics
- `snapshot_config.yaml` - Reproducibility config

## Dataset Statistics

- Total samples: {stats['dataset'].get('count', 0)}
- Date range: {stats['dataset'].get('date_range', 'N/A')}
- Crash samples: {stats['dataset'].get('crash_samples', 0)}
- Size: {stats['dataset'].get('size_mb', 0):.2f} MB

## Model Performance

- Trained: {stats['model'].get('trained_at', 'N/A')}
- ROC AUC: {stats['model'].get('roc_auc', 0):.3f}
- Precision: {stats['model'].get('precision', 0):.3f}

## Restore Instructions

```bash
# Extract snapshot
tar -xzf tradinglab_{quarter}.tar.gz

# Restore to trading-lab
cp {quarter}/*.parquet /opt/homelab-panel/trading-lab/data/restored/
cp {quarter}/*.joblib /opt/homelab-panel/trading-lab/models/crash_predictor/
cp {quarter}/metadata.json /opt/homelab-panel/trading-lab/models/crash_predictor/
```

## Cloud Upload

Upload this bundle to Namecheap Stellar DB or S3:

```bash
# Namecheap Stellar DB
curl -X POST -H "Authorization: Bearer $STELLAR_API_KEY" \\
  -F "file=@tradinglab_{quarter}.tar.gz" \\
  https://api.stellar.namecheap.com/v1/upload

# Or S3-compatible
aws s3 cp tradinglab_{quarter}.tar.gz s3://your-bucket/trading-backups/
```
""")
    
    print(f"✅ Created {readme_path.name}")


def create_compressed_bundle(snapshot_dir: Path, quarter: str) -> Path:
    """Create compressed tar.gz bundle."""
    print(f"\n📦 Creating compressed bundle...")
    
    bundle_name = f"tradinglab_{quarter}.tar.gz"
    bundle_path = snapshot_dir.parent / bundle_name
    
    with tarfile.open(bundle_path, "w:gz") as tar:
        tar.add(snapshot_dir, arcname=quarter)
    
    size_mb = bundle_path.stat().st_size / (1024 * 1024)
    
    print(f"✅ Created {bundle_name}")
    print(f"   Size: {size_mb:.2f} MB")
    print(f"   Path: {bundle_path}")
    
    return bundle_path


def encrypt_bundle(bundle_path: Path, password: str = None) -> Path:
    """Encrypt bundle with age encryption (optional)."""
    print(f"\n🔐 Encrypting bundle...")
    
    try:
        import subprocess
        
        # Check if age is installed
        result = subprocess.run(["which", "age"], capture_output=True)
        if result.returncode != 0:
            print("⚠️  'age' encryption tool not installed")
            print("   Install: https://github.com/FiloSottile/age")
            print("   Or: brew install age / apt install age")
            print("   Skipping encryption...")
            return bundle_path
        
        encrypted_path = Path(str(bundle_path) + ".age")
        
        if password:
            # Symmetric encryption with password
            cmd = ["age", "-p", "-o", str(encrypted_path), str(bundle_path)]
            subprocess.run(cmd, input=f"{password}\n{password}\n".encode(), check=True)
        else:
            # Prompt for password
            cmd = ["age", "-p", "-o", str(encrypted_path), str(bundle_path)]
            subprocess.run(cmd, check=True)
        
        size_mb = encrypted_path.stat().st_size / (1024 * 1024)
        
        print(f"✅ Encrypted to {encrypted_path.name}")
        print(f"   Size: {size_mb:.2f} MB")
        
        return encrypted_path
        
    except Exception as e:
        print(f"⚠️  Encryption failed: {e}")
        return bundle_path


def main():
    parser = argparse.ArgumentParser(
        description="Create quarterly ML snapshot bundle"
    )
    parser.add_argument(
        "--quarter",
        help="Quarter identifier (e.g., 2026_Q1)",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Auto-detect current quarter",
    )
    parser.add_argument(
        "--encrypt",
        action="store_true",
        help="Encrypt bundle with password (requires 'age' tool)",
    )
    parser.add_argument(
        "--password",
        help="Password for encryption (optional, will prompt if not provided)",
    )
    
    args = parser.parse_args()
    
    # Determine quarter
    if args.auto:
        quarter = get_current_quarter()
    elif args.quarter:
        quarter = args.quarter
    else:
        print("Error: Specify --quarter or --auto")
        parser.print_help()
        return
    
    print("="*80)
    print(f"📸 CREATING QUARTERLY SNAPSHOT: {quarter}")
    print("="*80)
    
    load_dotenv()
    db = Database()
    
    # Create snapshot directory
    snapshot_dir = create_snapshot_directory(quarter)
    print(f"\n📁 Snapshot directory: {snapshot_dir}")
    
    # Export dataset
    dataset_stats = export_training_dataset(db, snapshot_dir, quarter)
    
    # Copy model artifacts
    model_stats = copy_model_artifacts(snapshot_dir)
    
    # Save configuration
    save_snapshot_config(snapshot_dir, quarter, {
        "dataset": dataset_stats,
        "model": model_stats,
    })
    
    # Create compressed bundle
    bundle_path = create_compressed_bundle(snapshot_dir, quarter)
    
    # Encrypt if requested
    if args.encrypt:
        bundle_path = encrypt_bundle(bundle_path, args.password)
    
    # Summary
    print("\n" + "="*80)
    print("✅ SNAPSHOT COMPLETE")
    print("="*80)
    print(f"\n📦 Bundle: {bundle_path.name}")
    print(f"📁 Location: {bundle_path}")
    print(f"💾 Size: {bundle_path.stat().st_size / (1024*1024):.2f} MB")
    
    print(f"\n📊 Contents:")
    print(f"   - ML training samples: {dataset_stats.get('count', 0)}")
    print(f"   - Crash window samples: {dataset_stats.get('crash_samples', 0)}")
    print(f"   - Trained model: {'Yes' if model_stats.get('exists') else 'No'}")
    
    print(f"\n☁️  Next Steps:")
    print(f"\n1. Upload to Namecheap Stellar DB:")
    print(f"   curl -X POST -H 'Authorization: Bearer $STELLAR_API_KEY' \\")
    print(f"     -F 'file=@{bundle_path}' \\")
    print(f"     https://api.stellar.namecheap.com/v1/upload")
    
    print(f"\n2. Or upload to S3:")
    print(f"   aws s3 cp {bundle_path} s3://your-bucket/trading-backups/")
    
    print(f"\n3. Or keep local offsite backup:")
    print(f"   cp {bundle_path} /path/to/external/drive/")
    
    if args.encrypt:
        print(f"\n🔐 Encrypted bundle can be safely uploaded to cloud storage")
        print(f"   Decrypt with: age -d {bundle_path.name} > tradinglab_{quarter}.tar.gz")
    
    print("\n" + "="*80)


if __name__ == "__main__":
    main()
