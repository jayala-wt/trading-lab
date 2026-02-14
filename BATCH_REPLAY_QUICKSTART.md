# Batch Historical Replay - Quickstart Guide

Generate training data for **ALL 93 trading symbols** (6 crypto + 87 stocks) in one automated run.

---

## 🎯 Quick Start (Recommended)

### Run Complete 90-Day Replay for All Symbols

```bash
cd /opt/homelab-panel/trading-lab

# Full batch (93 symbols × 90 days = ~750,000+ samples)
python3 scripts/batch_historical_replay.py

# Estimated time: ~2.5 hours
# Rate limit safe: 10 second delays between symbols
```

**What this does:**
- ✅ Processes 6 crypto symbols (BTC, ETH, SOL, DOGE, AVAX, LINK)
- ✅ Processes 87 stock symbols (SPY, AAPL, NVDA, TSLA, etc.)
- ✅ Downloads 90 days of historical bars per symbol
- ✅ Runs dimension classifier + pattern detector on each bar
- ✅ Labels outcomes (5min, 15min, 60min profit/loss)
- ✅ Saves to `ml_training_samples` table
- ✅ Respects Alpaca API rate limits (10s delay between symbols)
- ✅ Tracks progress (can resume if interrupted)

---

## 📊 Dataset Expectations

### Per Symbol (90 days):

| Market | Trading Hours | Bars/Day | Total Bars (90d) | Samples Created |
|--------|---------------|----------|------------------|-----------------|
| Crypto | 24/7 | ~288 | ~26,000 | ~8,000-12,000 |
| Stocks | 6.5h/day, 5 days/week | ~78 | ~5,460 | ~2,000-3,000 |

### Total Dataset (All 93 Symbols):

```
Crypto (6 symbols):   ~50,000 samples
Stocks (87 symbols):  ~200,000 samples
──────────────────────────────────────
TOTAL:                ~250,000 samples
```

**Quality Distribution:**
- Excellent: ~30% (strong patterns, clean outcomes)
- Good: ~40% (valid patterns, typical outcomes)
- Marginal: ~20% (weak patterns, noisy outcomes)
- Poor: ~10% (edge cases, anomalies)

---

## 🚀 Usage Options

### 1. Full Batch (All Symbols)

```bash
# Default: 90 days, all symbols
python3 scripts/batch_historical_replay.py

# Custom days
python3 scripts/batch_historical_replay.py --days 30
python3 scripts/batch_historical_replay.py --days 180
```

### 2. Crypto Only

```bash
# Only 6 crypto symbols (faster, ~30 minutes)
python3 scripts/batch_historical_replay.py --crypto-only

# Expected: ~50,000 samples
```

### 3. Stocks Only

```bash
# Only 87 stock symbols (~2 hours)
python3 scripts/batch_historical_replay.py --stocks-only

# Expected: ~200,000 samples
```

### 4. Test Run (Dry Run)

```bash
# Test without saving to database
python3 scripts/batch_historical_replay.py --dry-run --days 7

# Quick validation (completes in ~15 minutes)
```

### 5. Resume Interrupted Run

```bash
# If process was interrupted, resume from where it stopped
python3 scripts/batch_historical_replay.py --resume

# Skips already-completed symbols (tracked in data/batch_replay_progress.json)
```

---

## ⚙️ Advanced Options

```bash
# Adjust rate limit delay (default: 10s)
python3 scripts/batch_historical_replay.py --rate-limit-delay 5

# Crypto only, 30 days, faster delays
python3 scripts/batch_historical_replay.py --crypto-only --days 30 --rate-limit-delay 5
```

---

## 📈 Progress Tracking

The script shows real-time progress:

```
[12/93] Processing AAPL...
  ✅ Success: 2,847 samples created in 82.3s
  📊 Total samples for AAPL: 2,847
  📈 Progress: 12.9% | ETA: 118.2m | Samples: 34,521
  ⏸️  Rate limit delay: 10s...
```

**Progress saved to:** `data/batch_replay_progress.json`

If interrupted, the script can resume using `--resume` flag.

---

## 🛡️ Rate Limiting Strategy

**Alpaca Free Tier Limits:**
- 200 requests per minute
- Each symbol requires ~10-15 requests (for 90 days of bars)
- Processing time: ~60-90 seconds per symbol

**Built-in Safety:**
- 10 second delay between symbols (default)
- Progress tracking (resume on failure)
- 10 minute timeout per symbol
- Error handling (continues on failures)

**Total time estimate:**
- **Crypto only:** ~30 minutes (6 symbols)
- **Stocks only:** ~2 hours (87 symbols)
- **Full batch:** ~2.5 hours (93 symbols)

---

## 📊 After Completion

### 1. Verify Dataset

```bash
# Check total samples created
sqlite3 data/market.db "SELECT COUNT(*) FROM ml_training_samples"

# Check samples per symbol
sqlite3 data/market.db << 'SQL'
SELECT symbol, COUNT(*) as samples 
FROM ml_training_samples 
GROUP BY symbol 
ORDER BY samples DESC 
LIMIT 20;
SQL

# Check quality distribution
sqlite3 data/market.db << 'SQL'
SELECT label_quality, COUNT(*) as count 
FROM ml_training_samples 
GROUP BY label_quality;
SQL
```

### 2. Train ML Model

```bash
# Train crash predictor on full dataset
python3 -m core.ml.crash_predictor_trainer --train

# Expected: 80%+ accuracy with 250,000 samples
```

### 3. Evaluate Performance

```bash
# Run tests
python3 tests/test_crash_predictor.py

# Benchmark inference speed
python3 tests/benchmark_crash_predictor.py
```

### 4. Create Quarterly Snapshot

```bash
# Save immutable snapshot for cold storage
python3 scripts/create_quarterly_snapshot.py

# Output: snapshots/2026_Q1/
```

---

## 🔧 Troubleshooting

### Error: "No bars returned for SYMBOL"

**Cause:** Symbol not available on Alpaca or date range issue

**Fix:** Script continues to next symbol automatically

---

### Error: "Rate limit exceeded"

**Cause:** Too many requests to Alpaca API

**Fix:** Increase `--rate-limit-delay`:
```bash
python3 scripts/batch_historical_replay.py --rate-limit-delay 15
```

---

### Process Interrupted

**Fix:** Resume from progress file:
```bash
python3 scripts/batch_historical_replay.py --resume
```

Progress is saved after each successful symbol in `data/batch_replay_progress.json`.

---

### Timeout on Symbol

**Cause:** Symbol taking >10 minutes (very rare)

**Fix:** Script skips and continues. Check errors in output.

---

## 📋 Symbol List

### Crypto (6 symbols)
```
BTC/USD, ETH/USD, SOL/USD, DOGE/USD, AVAX/USD, LINK/USD
```

### Stocks (87 symbols)

**ETFs (9 symbols):**
```
SPY, QQQ, IWM, DIA, XLF, XLE, XLV, ARKK, VTI
```

**Mega Tech (10):**
```
AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA, ORCL, CRM, ADBE
```

**Semiconductors (8):**
```
AMD, INTC, MU, AVGO, QCOM, TSM, MRVL, ARM
```

**Finance (7):**
```
JPM, GS, V, MA, BAC, WFC, SCHW
```

**Defense/Military (6):**
```
LMT, RTX, NOC, GD, BA, LHX
```

**Pharma/Healthcare (8):**
```
PFE, JNJ, MRK, ABBV, LLY, UNH, BMY, MRNA
```

**Consumer/Entertainment (8):**
```
NFLX, DIS, NKE, SBUX, MCD, WMT, TGT, COST
```

**Fintech/Crypto (4):**
```
COIN, SQ, PYPL, HOOD
```

**Tech Growth/Niche (7):**
```
PLTR, UBER, ABNB, SNOW, NET, DDOG, CNXC
```

**Energy (3):**
```
XOM, CVX, OXY
```

---

## 🎯 Recommended Workflow

### Option A: Full Dataset (Best ML Performance)

```bash
# Step 1: Run full 90-day batch (~2.5 hours)
python3 scripts/batch_historical_replay.py

# Step 2: Train model
python3 -m core.ml.crash_predictor_trainer --train

# Step 3: Create snapshot
python3 scripts/create_quarterly_snapshot.py
```

**Expected outcome:** 250,000+ samples, 85%+ model accuracy

---

### Option B: Quick Start (Faster Testing)

```bash
# Step 1: Run crypto-only 30 days (~15 minutes)
python3 scripts/batch_historical_replay.py --crypto-only --days 30

# Step 2: Train initial model
python3 -m core.ml.crash_predictor_trainer --train

# Step 3: Expand to stocks later
python3 scripts/batch_historical_replay.py --stocks-only --days 30 --resume
```

**Expected outcome:** 15,000+ samples (crypto), then 60,000+ (stocks), good for testing

---

### Option C: High-Value Symbols (Balanced)

Edit `batch_historical_replay.py` to use subset:

```python
# Top crypto + top stocks only (reduces to ~20 symbols)
CRYPTO_SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD"]
STOCK_SYMBOLS = ["SPY", "QQQ", "AAPL", "NVDA", "TSLA", "AMZN", "MSFT"]
```

```bash
# Run focused batch (~30 minutes for 10 symbols)
python3 scripts/batch_historical_replay.py --days 90
```

**Expected outcome:** ~80,000 samples, covers most important symbols

---

## 💡 Next Steps After Batch Replay

1. **Train multiple ML models:**
   ```bash
   # Crash predictor (implemented)
   python3 -m core.ml.crash_predictor_trainer --train
   
   # Profit predictor (coming soon)
   # python3 -m core.ml.profit_predictor_trainer --train
   
   # Regime classifier (coming soon)
   # python3 -m core.ml.regime_classifier_trainer --train
   ```

2. **Set up weekly automation:**
   ```bash
   crontab -e
   
   # Add: Run batch replay weekly to accumulate more data
   0 2 * * 0 cd /opt/homelab-panel/trading-lab && python3 scripts/batch_historical_replay.py --days 7 --resume
   ```

3. **Integrate ML into live bot:**
   - Already integrated: `core/execution/position_manager.py` uses crash predictor
   - Add more: Profit prediction, regime classification, return regression

4. **Monitor performance:**
   ```bash
   # Check ML accuracy over time
   python3 tests/test_crash_predictor.py
   
   # Compare bot performance with/without ML
   # Check trading.db for P&L comparison
   ```

---

## 🚀 Start Now

```bash
cd /opt/homelab-panel/trading-lab

# Recommended: Full 90-day batch for all symbols
python3 scripts/batch_historical_replay.py

# Grab coffee ☕ - this will take ~2.5 hours
# When done, you'll have 250,000+ labeled samples for ML training!
```

**Expected Outcome:**
- ✅ ~250,000 training samples across 93 symbols
- ✅ Ready for ML training (9,000+ sample target exceeded by 28×)
- ✅ Multiple quality tiers (excellent, good, marginal, poor)
- ✅ Foundation for crash prediction, profit prediction, regime classification
- ✅ Historical data from last 90 days (recent market conditions)
