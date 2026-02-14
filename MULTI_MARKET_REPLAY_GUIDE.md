# Multi-Market Historical Replay - Stocks + Crypto

## 🎯 One Script, Multiple Markets

The historical replay script now works for **both crypto AND stocks** - same logic, different symbols!

---

## 🪙 Crypto Examples

### BTC/USD (Bitcoin)
```bash
# 7 days of BTC
python3 scripts/historical_replay_simple.py BTC/USD 7

# Expected: ~630 samples (crypto trades 24/7)
```

### ETH/USD (Ethereum)
```bash
# 30 days of ETH
python3 scripts/historical_replay_simple.py ETH/USD 30

# Expected: ~1,900 samples
```

### Multiple Crypto
```bash
# BTC + ETH + SOL
python3 scripts/historical_replay_simple.py BTC/USD 7
python3 scripts/historical_replay_simple.py ETH/USD 7
python3 scripts/historical_replay_simple.py SOL/USD 7

# Expected: ~1,890 combined samples (3 × 630)
```

---

## 📈 Stock Examples

### AAPL (Apple)
```bash
# 7 days of AAPL
python3 scripts/historical_replay_simple.py AAPL 7 --market=stocks

# Expected: ~195 samples (stocks only trade 6.5h/day, 5 days/week)
```

### TSLA (Tesla)
```bash
# 30 days of TSLA
python3 scripts/historical_replay_simple.py TSLA 30 --market=stocks

# Expected: ~590 samples (21 trading days × ~28 bars/day)
```

### SPY (S&P 500 ETF)
```bash
# 7 days of SPY
python3 scripts/historical_replay_simple.py SPY 7 --market=stocks
```

### Multiple Stocks
```bash
# Tech stocks
python3 scripts/historical_replay_simple.py AAPL 7 --market=stocks
python3 scripts/historical_replay_simple.py TSLA 7 --market=stocks
python3 scripts/historical_replay_simple.py NVDA 7 --market=stocks
python3 scripts/historical_replay_simple.py MSFT 7 --market=stocks

# Expected: ~780 combined samples (4 × 195)
```

---

## 🔄 Auto-Detection

Script auto-detects market type from symbol format:

**Crypto format** (has slash):
```bash
python3 scripts/historical_replay_simple.py BTC/USD 7
# Auto-detects: market=crypto
```

**Stock format** (no slash):
```bash
python3 scripts/historical_replay_simple.py AAPL 7
# Auto-detects: market=stocks
```

**Manual override**:
```bash
python3 scripts/historical_replay_simple.py AAPL 7 --market=stocks
# Explicit: market=stocks
```

---

## 📊 Data Volume Comparison

### Crypto (24/7 Trading)

| Period | Bars | Expected Signals | Expected Samples |
|--------|------|------------------|------------------|
| 1 day | 1,440 | ~13 | ~13 |
| 7 days | 10,080 | ~90 | ~90 |
| 30 days | 43,200 | ~380 | ~380 |

### Stocks (6.5h/day, 5 days/week)

| Period | Trading Days | Bars | Expected Signals | Expected Samples |
|--------|--------------|------|------------------|------------------|
| 1 day | 1 | ~390 | ~4 | ~4 |
| 7 days | 5 | 1,950 | ~28 | ~28 |
| 30 days | 21 | 8,190 | ~117 | ~117 |

**Key insight**: Crypto generates ~3.5X more samples per calendar day!

---

## 🚀 Massive Multi-Market Dataset

### Strategy: Build Combined Dataset

**Goal**: Train ML model on BOTH crypto and stocks

```bash
cd /opt/homelab-panel/trading-lab
export ALPACA_API_KEY="..."
export ALPACA_API_SECRET="..."

# === CRYPTO (30 days) ===
python3 scripts/historical_replay_simple.py BTC/USD 30
# ~1,140 samples

python3 scripts/historical_replay_simple.py ETH/USD 30
# ~1,140 samples

python3 scripts/historical_replay_simple.py SOL/USD 30
# ~1,140 samples

# === STOCKS (30 days) ===
python3 scripts/historical_replay_simple.py AAPL 30 --market=stocks
# ~351 samples

python3 scripts/historical_replay_simple.py TSLA 30 --market=stocks
# ~351 samples

python3 scripts/historical_replay_simple.py NVDA 30 --market=stocks
# ~351 samples

python3 scripts/historical_replay_simple.py SPY 30 --market=stocks
# ~351 samples

# === TOTAL ===
# Crypto: 3,420 samples
# Stocks: 1,404 samples
# Combined: 4,824 samples!
# Plus your 660 crash samples = 5,484 total!
```

**Processing time**: ~10-15 minutes for all symbols

---

## 🎯 Market-Specific ML Models

### Option 1: Universal Model (Recommended)

Train ONE model on all markets:

```python
# ML model trained on crypto + stocks
# Learns universal patterns:
# - compressed + weak_trend + neutral = crash (works for both!)
# - oversold + strong_trend + expanding = profitable (universal!)

# Same dimension logic, same crash signatures
```

**Benefit**: More training data, learns universal market behavior

### Option 2: Market-Specific Models

Train separate models per market:

```bash
# Train crypto-only model
python3 -m core.ml.crash_predictor_trainer --train --market=crypto

# Train stocks-only model
python3 -m core.ml.crash_predictor_trainer --train --market=stocks

# Deploy appropriate model at runtime
```

**Benefit**: Market-specific nuances (stock gaps vs 24/7 crypto)

---

## 💾 Storage Impact

### 30-Day Backfill (7 symbols)

```
Dataset size:
- Raw samples: 5,484
- Engineered features: 18 per sample
- Storage: ~2.3 MB (parquet compressed)

Quarterly snapshot:
- Dataset + models: ~8 MB compressed
- Well within Namecheap free tier (10 GB)
```

---

## 📅 Automated Weekly Backfill (Cron)

### Crypto + Stocks Combined

```bash
crontab -e

# Add these lines:

# Crypto replay (Sunday 2am)
0 2 * * 0 cd /opt/homelab-panel/trading-lab && python3 scripts/historical_replay_simple.py BTC/USD 7 >> logs/weekly_replay_crypto.log 2>&1
5 2 * * 0 cd /opt/homelab-panel/trading-lab && python3 scripts/historical_replay_simple.py ETH/USD 7 >> logs/weekly_replay_crypto.log 2>&1

# Stock replay (Sunday 2:10am)
10 2 * * 0 cd /opt/homelab-panel/trading-lab && python3 scripts/historical_replay_simple.py AAPL 7 --market=stocks >> logs/weekly_replay_stocks.log 2>&1
15 2 * * 0 cd /opt/homelab-panel/trading-lab && python3 scripts/historical_replay_simple.py TSLA 7 --market=stocks >> logs/weekly_replay_stocks.log 2>&1
20 2 * * 0 cd /opt/homelab-panel/trading-lab && python3 scripts/historical_replay_simple.py SPY 7 --market=stocks >> logs/weekly_replay_stocks.log 2>&1
```

**Weekly additions**: ~300 samples (crypto) + ~100 samples (stocks) = ~400 samples/week automatically!

---

## 🔍 Verify Multi-Market Dataset

```bash
sqlite3 /opt/homelab-panel/trading-lab/data/market.db << 'EOF'
SELECT 
    symbol,
    data_source,
    COUNT(*) as samples,
    MIN(DATE(created_at)) as earliest,
    MAX(DATE(created_at)) as latest
FROM ml_training_samples
GROUP BY symbol, data_source
ORDER BY symbol;
EOF
```

**Expected output:**
```
AAPL|historical_replay|351|2026-01-15|2026-02-14
BTC/USD|historical_replay|1140|2026-01-15|2026-02-14
BTC/USD|live|660|2026-02-03|2026-02-06
ETH/USD|historical_replay|1140|2026-01-15|2026-02-14
NVDA|historical_replay|351|2026-01-15|2026-02-14
SOL/USD|historical_replay|1140|2026-01-15|2026-02-14
SPY|historical_replay|351|2026-01-15|2026-02-14
TSLA|historical_replay|351|2026-01-15|2026-02-14
```

---

## 🎯 Recommended Setup

### Phase 1: Initial Backfill (One-Time)

```bash
# Crypto (30 days)
for symbol in BTC/USD ETH/USD SOL/USD; do
    python3 scripts/historical_replay_simple.py $symbol 30 &
done
wait

# Stocks (30 days)
for symbol in AAPL TSLA NVDA SPY; do
    python3 scripts/historical_replay_simple.py $symbol 30 --market=stocks &
done
wait

# ~10 minutes total (parallel execution)
```

### Phase 2: Train Universal Model

```bash
# Train on combined dataset
python3 -m core.ml.crash_predictor_trainer --train

# Model learns from 5,484+ samples (crypto + stocks)
```

### Phase 3: Weekly Automation

```bash
# Set up cron (see above)
# Adds ~400 samples/week automatically
```

### Phase 4: Quarterly Snapshot

```bash
# Every 3 months: preserve combined dataset
python3 scripts/create_quarterly_snapshot.py --auto --encrypt

# Upload to Namecheap Stellar DB
```

---

## 🚨 Key Differences: Crypto vs Stocks

### Trading Hours

**Crypto**:
- 24/7/365
- No gaps
- Continuous data

**Stocks**:
- 9:30am - 4:00pm ET
- Monday - Friday
- Overnight gaps
- Weekend gaps

### Implication for ML

Dimension states work the same, but stocks have additional considerations:

**Gap handling**:
```python
# Stock opening gap example
Friday close: $150
Monday open: $155 (+3.3% gap!)

# Dimension snapshot at Monday 9:31am:
# - Shows "gap up" in structure dimension
# - Volatility might spike at open
# - First 30min often unreliable
```

Your dimension classifier already handles this - it classifies whatever state exists!

---

## 🎯 Bottom Line

✅ **Same script works for crypto AND stocks**  
✅ **Auto-detects market from symbol format**  
✅ **Build combined dataset: 5,000+ samples in 15 minutes**  
✅ **Same crash signatures apply to both markets**  
✅ **Train universal model or market-specific models**  
✅ **Automate weekly with cron**

**Just download more data for more symbols** - the intellectual work (dimension classification, pattern detection, outcome labeling) is automated! 🚀

```bash
# Get started now:
cd /opt/homelab-panel/trading-lab
python3 scripts/historical_replay_simple.py AAPL 7 --market=stocks
python3 scripts/historical_replay_simple.py BTC/USD 7
```
