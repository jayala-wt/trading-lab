# Quarterly Snapshot Strategy - Cold Archives, Not Live Sync

## 🧠 Philosophy

**Principle: Backup is for catastrophic loss, not daily workflow.**

You're NOT building:
- Live cloud database
- Continuous replication
- Real-time sync
- Multi-region architecture

You're building:
- **Immutable snapshots**
- **Version history**
- **Disaster recovery**
- **MLOps lineage**

---

## 🎯 What to Back Up (and Why)

### ✅ Back Up (High Value, Can't Recreate)

1. **Engineered ML Training Dataset**
   - Crash labels (took days to identify)
   - Feature engineering (your IP)
   - Cleaned/curated samples
   - **Why**: Recreating would require re-running all trades through crash detection logic

2. **Trained Models**
   - crash_predictor.joblib (2 weeks of learning)
   - encoders.joblib
   - metadata.json
   - **Why**: Training takes time, represents accumulated knowledge

3. **Backtest Results**
   - Performance analysis
   - Strategy evaluations
   - Research findings
   - **Why**: Your intellectual work, insights, decisions

4. **Configuration + Hyperparameters**
   - Model settings
   - Risk parameters
   - Pattern definitions
   - **Why**: Reproducibility - "how did we get here?"

### ❌ Don't Back Up (Can Recreate)

1. **Raw Alpaca Market Data**
   - OHLCV bars
   - Trade ticks
   - **Why**: Can re-download from Alpaca API

2. **Live Trading Database**
   - Current positions
   - Pending orders
   - **Why**: This is working state, not historical value

---

## 📅 Recommended Schedule

### Monthly Snapshots (Light)

**First Saturday of each month:**

```bash
# Quick dataset export
python -m core.ml.cloud_export --export incremental
```

- Last 30 days of new samples
- ~5-10 MB compressed
- Upload to Namecheap

### Quarterly Snapshots (Full)

**End of each quarter (Q1: Mar 31, Q2: Jun 30, etc.):**

```bash
# Full immutable bundle
python scripts/create_quarterly_snapshot.py --auto --encrypt
```

Creates versioned bundle:
```
tradinglab_2026_Q1.tar.gz.age
├── ml_training_dataset.parquet (all engineered samples)
├── crash_window_feb3-6.parquet (high-value crash data)
├── crash_predictor.joblib (trained model)
├── encoders.joblib
├── metadata.json (metrics, hyperparameters)
├── snapshot_config.yaml (reproducibility)
└── README.md (restore instructions)
```

- Full dataset history
- Model version
- Config snapshot
- ~10-50 MB compressed + encrypted
- Upload to offsite storage

---

## 🔐 Security: Encryption with `age`

### Why Encrypt?

Once you upload to Namecheap/cloud, you don't control physical security.

Encrypt BEFORE upload:
- Protects your trading strategies (IP)
- Protects API keys in configs
- Protects against cloud provider breaches

### Install `age`

```bash
# macOS
brew install age

# Ubuntu/Debian
apt install age

# Or download binary
wget https://github.com/FiloSottile/age/releases/download/v1.1.1/age-v1.1.1-linux-amd64.tar.gz
```

### Encrypt Bundle

```bash
# Encrypt with password (symmetric)
age -p -o tradinglab_2026_Q1.tar.gz.age tradinglab_2026_Q1.tar.gz
# Enter password (keep in password manager!)

# Upload encrypted file
aws s3 cp tradinglab_2026_Q1.tar.gz.age s3://your-bucket/
```

### Decrypt (When Restoring)

```bash
# Decrypt
age -d tradinglab_2026_Q1.tar.gz.age > tradinglab_2026_Q1.tar.gz
# Enter password

# Extract
tar -xzf tradinglab_2026_Q1.tar.gz
```

---

## ☁️ Upload Options (Namecheap Stellar)

### Option 1: Stellar DB Dashboard (Easy)

1. Go to Namecheap Stellar DB dashboard
2. Upload → Select file
3. Choose `tradinglab_2026_Q1.tar.gz.age`
4. Done!

### Option 2: Stellar DB API (Automated)

```bash
# Set API key once
export STELLAR_API_KEY="your_key_here"

# Upload
curl -X POST \
  -H "Authorization: Bearer $STELLAR_API_KEY" \
  -F "file=@tradinglab_2026_Q1.tar.gz.age" \
  https://api.stellar.namecheap.com/v1/upload
```

### Option 3: S3-Compatible (If Stellar Supports)

```bash
# Configure once
aws configure --profile stellar
# Enter Stellar S3 credentials

# Upload
aws s3 cp tradinglab_2026_Q1.tar.gz.age \
  s3://your-stellar-bucket/trading-backups/ \
  --profile stellar
```

---

## 📂 Recommended Folder Structure

### Local (Homelab)

```
/opt/homelab-panel/trading-lab/
├── data/
│   ├── market.db (live working database)
│   └── ml_exports/ (temp exports)
├── models/
│   └── crash_predictor/ (current model)
└── snapshots/
    ├── 2026_Q1/
    │   ├── ml_training_dataset.parquet
    │   ├── crash_predictor.joblib
    │   └── README.md
    ├── 2026_Q2/ (next quarter)
    └── tradinglab_2026_Q1.tar.gz.age (compressed bundle)
```

### Cloud (Namecheap Stellar DB)

```
/trading-backups/
├── tradinglab_2026_Q1.tar.gz.age
├── tradinglab_2026_Q2.tar.gz.age
├── tradinglab_2026_Q3.tar.gz.age
└── tradinglab_2026_Q4.tar.gz.age
```

Simple, clean, no complexity.

---

## 🔄 Workflow: Create Quarterly Snapshot

### Step 1: Create Snapshot

```bash
cd /opt/homelab-panel/trading-lab

# Auto-detect current quarter + encrypt
python scripts/create_quarterly_snapshot.py --auto --encrypt

# Enter password when prompted (save in 1Password/Bitwarden)
```

Output:
```
📸 CREATING QUARTERLY SNAPSHOT: 2026_Q1
📊 Exporting training dataset...
✅ Exported 1,523 samples to ml_training_dataset.parquet
🤖 Copying model artifacts...
✅ Copied crash_predictor.joblib
📦 Creating compressed bundle...
✅ Created tradinglab_2026_Q1.tar.gz (15.23 MB)
🔐 Encrypting bundle...
✅ Encrypted to tradinglab_2026_Q1.tar.gz.age (15.25 MB)
```

### Step 2: Upload to Cloud

```bash
# Option A: Namecheap Stellar DB API
curl -X POST \
  -H "Authorization: Bearer $STELLAR_API_KEY" \
  -F "file=@snapshots/tradinglab_2026_Q1.tar.gz.age" \
  https://api.stellar.namecheap.com/v1/upload

# Option B: Copy to external drive
cp snapshots/tradinglab_2026_Q1.tar.gz.age /Volumes/External/backups/

# Option C: Upload to S3
aws s3 cp snapshots/tradinglab_2026_Q1.tar.gz.age \
  s3://your-bucket/trading-backups/
```

### Step 3: Verify

```bash
# Verify upload succeeded
curl -H "Authorization: Bearer $STELLAR_API_KEY" \
  https://api.stellar.namecheap.com/v1/files

# Verify size matches
ls -lh snapshots/tradinglab_2026_Q1.tar.gz.age
```

### Step 4: Document (Optional)

Create `snapshots/manifest.md`:

```markdown
# Snapshot Manifest

## 2026_Q1 (Created: 2026-03-31)
- File: tradinglab_2026_Q1.tar.gz.age
- Size: 15.25 MB
- Samples: 1,523 (660 crash + 863 normal)
- Model: crash_predictor v3 (ROC AUC: 0.892)
- Uploaded: Namecheap Stellar DB + External HDD
- Password: In 1Password vault "Trading"
```

---

## 🚨 Disaster Recovery: Restore from Snapshot

### Scenario: Homelab SSD dies

```bash
# 1. Download from cloud
curl -H "Authorization: Bearer $STELLAR_API_KEY" \
  https://api.stellar.namecheap.com/v1/files/tradinglab_2026_Q1.tar.gz.age \
  -o tradinglab_2026_Q1.tar.gz.age

# 2. Decrypt
age -d tradinglab_2026_Q1.tar.gz.age > tradinglab_2026_Q1.tar.gz
# Enter password

# 3. Extract
tar -xzf tradinglab_2026_Q1.tar.gz

# 4. Restore files
cp 2026_Q1/*.parquet /opt/homelab-panel/trading-lab/data/restored/
cp 2026_Q1/*.joblib /opt/homelab-panel/trading-lab/models/crash_predictor/
cp 2026_Q1/metadata.json /opt/homelab-panel/trading-lab/models/crash_predictor/

# 5. Verify model loads
python -c "from core.ml.crash_predictor import get_crash_predictor; p = get_crash_predictor(); print(p.get_model_info())"

# 6. Resume trading
python scripts/run_bot.py
```

Recovery time: ~10 minutes

Without backup: Days/weeks to recreate

---

## 💾 Storage Math

### Quarterly Growth Estimate

```
Q1: 660 samples  → 15 MB compressed
Q2: 1,200 samples → 20 MB compressed
Q3: 2,500 samples → 30 MB compressed
Q4: 4,000 samples → 40 MB compressed

Year 1 total: ~100 MB
Year 2 total: ~200 MB
Year 3 total: ~350 MB
```

Even after 3 years: **<500 MB**

Namecheap Stellar DB free tier: **10 GB**

You're fine for 50+ years! 📈

---

## 🧠 MLOps Best Practices

This snapshot approach gives you:

### 1. Reproducibility

```bash
# Can reproduce any model version
tar -xzf tradinglab_2026_Q1.tar.gz
cd 2026_Q1
cat snapshot_config.yaml
# See exact hyperparameters, data range, dependencies
```

### 2. Model Lineage

```
2026_Q1: crash_predictor_v1 (660 samples, ROC AUC: 0.85)
2026_Q2: crash_predictor_v2 (1,200 samples, ROC AUC: 0.88)
2026_Q3: crash_predictor_v3 (2,500 samples, ROC AUC: 0.91)
```

Track performance improvement over time!

### 3. Regression Testing

```bash
# Test new model vs Q1 snapshot
python scripts/compare_models.py \
  --baseline snapshots/2026_Q1/crash_predictor.joblib \
  --current models/crash_predictor/crash_predictor.joblib
```

### 4. Audit Trail

"Why did we block that trade on March 15?"

```bash
# Load Q1 snapshot
# Review exact model state at that time
# Explain decision with reproducible artifacts
```

---

## 🎯 Summary: Your Workflow

### Monthly (5 minutes)

```bash
# Export incremental dataset
python -m core.ml.cloud_export --export incremental

# Upload to cloud
# Done!
```

### Quarterly (15 minutes)

```bash
# Create full snapshot
python scripts/create_quarterly_snapshot.py --auto --encrypt

# Upload to Namecheap + external drive
# Update manifest
# Done!
```

### Annually (1 hour)

```bash
# Review all snapshots
# Verify restorability (test one restore)
# Clean up old monthlies (keep quarterlies)
# Update backup strategy
```

---

## 🔥 Why This Works

✅ **Simple**: Monthly incremental, quarterly full
✅ **Secure**: Encrypted before upload
✅ **Cheap**: <500 MB total, well within free tier
✅ **Fast**: 5-15 minutes per snapshot
✅ **Reproducible**: Can restore exact model state
✅ **Scalable**: Grows linearly, not exponentially
✅ **Offsite**: Protected against local disasters
✅ **Versioned**: Model lineage + auditability

❌ **NOT**:
- Complex real-time sync
- Live cloud database
- Costly infrastructure
- Over-engineered
- Fragile dependencies

---

## 💡 Bottom Line

You're backing up **intellectual work**, not raw data.

Quarterly snapshots are:
- **Immutable archives** (freeze moment in time)
- **Version controlled** (model evolution)
- **Disaster insurance** (offsite redundancy)
- **MLOps compliance** (reproducibility)

All for ~15 minutes/quarter and <100 MB/year.

That's **disciplined ML operations** without complexity creep.

Perfect. 🎯
