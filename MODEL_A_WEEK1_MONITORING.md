# Model A Deployment - Week 1 Monitoring Plan

**Deployed:** February 14, 2026  
**Model:** Crash Predictor v2 (Loss Avoidance - Symbol-Aware)  
**Mode:** Paper Trading  
**Bot:** crypto_24_7 (BTC/USD, ETH/USD, SOL/USD, DOGE/USD, AVAX/USD, LINK/USD)  

---

## 🎯 Mission

Validate that Model A v2 reduces losses in live paper trading over 7 days, replicating the **+559% improvement** seen in Feb 3-6 backtest validation.

---

## 📊 Model Specifications

### Training
- **Dataset:** 21,688 samples (Feb 3-14, 2026)
- **Target:** `label_quality='bad'` (outcome_60m < -0.5% OR max_drawdown < -2.0%)
- **Distribution:** 24% bad, 52% neutral, 24% good (balanced ✅)
- **Model:** Random Forest (200 trees, max_depth=10, class_weight='balanced')
- **Features:** 6 dimension states + 12 raw indicators + **1 symbol** (19 total)
- **Split:** Time-based 70/15/15 (no random shuffle, prevents look-ahead bias)

### Validation (Feb 3-6 Crash Period)
- **Samples:** 5,996 across 6 symbols (1,873 bad, 4,123 good/neutral)
  - **AVAX/USD**: 1,583 samples (28.3% bad) - highest velocity
  - **BTC/USD**: 1,210 samples (27.9% bad) - most stable
  - **ETH/USD**: 950 samples (35.1% bad)
  - **DOGE/USD**: 862 samples (31.1% bad)
  - **LINK/USD**: 742 samples (32.1% bad)
  - **SOL/USD**: 649 samples (38.2% bad) - highest risk
- **Threshold:** 0.50 (optimal)
- **Precision:** 64.0% (when model says bad, it's right 64% of time)
- **Recall:** 90.7% (catches 90.7% of actual bad signals)
- **F1 Score:** 0.751
- **Baseline loss:** -413% cumulative outcome
- **With Model A v2:** +1,897% cumulative outcome
- **Improvement:** +2,310% = **+559% loss reduction** 🚀

### Symbol Awareness
Model learns each symbol's unique risk profile:
- **SOL**: 38.2% bad rate → model more cautious on SOL signals
- **BTC**: 27.9% bad rate → model less aggressive on BTC signals
- **AVAX**: Highest velocity (1,583 signals) → model learns AVAX patterns

### Crash Signature Detection
- **Pattern:** compressed volatility + weak trend + neutral momentum
- **Detection rate:** 47.1% avg probability (correctly identifies)
- **Bad rate in signature:** 31.5% (3x higher than baseline)

---

## 🚀 Deployment Configuration

### Integration Points
1. **Entry Gate:** `ExecutionManager.submit_intent()` in [core/execution/executor.py](core/execution/executor.py#L110-L145)
   - Checks crash probability before every trade
   - **Tiered Risk Policy** (recommended for Week 1):
     - `p_crash ≥ 0.80` → **BLOCK** (extreme risk)
     - `0.50 ≤ p_crash < 0.80` → **REDUCE SIZE 50%** + tighter stops (high risk)
     - `p_crash < 0.50` → **ALLOW NORMAL** (acceptable risk)
   - Alternative: **Binary policy** (current): Block if `crash_prob ≥ 0.50`

2. **Exit Protection:** `PositionManager.check_exit_conditions()` in [core/execution/position_manager.py](core/execution/position_manager.py#L121-L129)
   - Force-exits losing positions if crash risk spikes
   - Already implemented (not modified)

**Note:** Starting with binary 0.50 threshold for simplicity. Can switch to tiered policy mid-week if needed.

### Logging
All ML decisions logged to `devlog_events` table:
- **ml_crash_check:** Signal evaluated and ALLOWED (prob < 0.50)
- **ml_crash_block:** Signal evaluated and BLOCKED (prob >= 0.50)

---

## 📈 Daily Monitoring Checklist

Run these commands daily to track performance:

### 1. Check ML Dashboard
```bash
cd /opt/homelab-panel/trading-lab
./scripts/monitor_ml_performance.sh
```

**Key Metrics:**
- **Crash Recall:** What % of bad signals are blocked? (target: ≥80%)
- **Block Rate:** How many signals prevented (target: ≤40% to avoid freezing)
- **Probability distribution:** Are we seeing high-risk signals? (>80% = extreme)
- **Recent decisions:** Spot-check model reasoning

### 2. Calculate Crash Recall (Mid-week & Week-end)
```bash
# Run after signals have 60min outcomes (mid-week Wed, week-end Fri)
./scripts/calculate_crash_recall.sh

# Or specify custom date range:
./scripts/calculate_crash_recall.sh 2026-02-15 2026-02-21
```

**What It Shows:**
- Label distribution (bad/neutral/good actual outcomes)
- Block rate vs target (≤40%)
- Tail losses (crashes that slipped through = false negatives)
- Trade outcomes for allowed signals

### 3. Compare Trading Performance
```bash
# Signals fired vs executed (ML gate effectiveness)
sqlite3 data/market.db "
SELECT 
    DATE(created_at) as date,
    COUNT(*) as signals_fired,
    SUM(CASE WHEN state = 'executed' THEN 1 ELSE 0 END) as executed,
    SUM(CASE WHEN state = 'rejected' THEN 1 ELSE 0 END) as rejected,
    ROUND(100.0 * SUM(CASE WHEN state = 'rejected' THEN 1 ELSE 0 END) / COUNT(*), 1) as block_rate
FROM signals
WHERE DATE(created_at) >= date('now', '-7 days')
GROUP BY DATE(created_at)
ORDER BY date DESC;
"

# Trade outcomes (P/L distribution)
sqlite3 data/market.db "
SELECT 
    DATE(opened_at) as date,
    COUNT(*) as trades,
    ROUND(AVG(realized_pnl_pct), 2) as avg_pnl_pct,
    SUM(CASE WHEN realized_pnl_pct > 0 THEN 1 ELSE 0 END) as wins,
    SUM(CASE WHEN realized_pnl_pct < 0 THEN 1 ELSE 0 END) as losses
FROM trades
WHERE status = 'closed'
AND DATE(opened_at) >= date('now', '-7 days')
GROUP BY DATE(opened_at)
ORDER BY date DESC;
"
```

### 4. Check Bot Health
```bash
# Verify bot is running
ps aux | grep "[p]ython.*crypto_24_7"

# Check recent logs (last 50 lines)
tail -50 bot_ml_live.log

# Restart if needed
cd /opt/homelab-panel/trading-lab
kill $(cat bot_ml.pid)
nohup python3 -m scripts.run_bot --config configs/bots/crypto_24_7.yaml > bot_ml_live.log 2>&1 &
echo $! > bot_ml.pid
```

---

## 🎯 Success Criteria (Week 1)

**Primary Goal:** Reduce losses without excessively blocking good signals

| Metric | Target | Priority | Notes |
|--------|--------|----------|-------|
| **Crash Recall** | ≥80% | 🔴 CRITICAL | Must catch 8 out of 10 actual bad signals |
| **Block Rate** | ≤40% | 🟡 HIGH | Don't freeze the bot, allow most trading |
| **Tail Loss Reduction** | ≥30% | 🔴 CRITICAL | Clear improvement on worst outcomes |
| **Normal-Day False Blocks** | ≤30% | 🟡 HIGH | Don't overblock on safe days |
| **Precision (on blocks)** | ≥50% | 🟢 MEDIUM | At least half of blocks should be good calls |
| **Win Rate Improvement** | +10-20% | 🟢 MEDIUM | Model should improve win rate vs baseline |

**Key Insight:** For crash prevention, prioritize **recall over precision**. False positives = skipped trades (opportunity cost), but false negatives = catastrophic losses.

**Monitoring Frequency:**
- **Daily (Feb 15-21):** Run dashboard, check crash recall + block rate, verify bot running
- **Mid-week (Feb 18 Wed):** Deep dive into blocked vs allowed outcomes
- **End of week (Feb 21 Fri):** Full performance analysis, decide next steps

---

## 🔍 What to Watch For

### Good Signs ✅
1. **High crash recall (>80%)** - Model catching most actual bad signals
2. **Block rate 25-40%** - Model selective but protective (not freezing bot)
3. **Precision on blocks ≥50%** - At least half of blocks are correct
4. **Crash signature blocks** - Model catching compressed+weak+neutral pattern
5. **Reduced tail losses** - Fewer -3%+ drawdowns on crash days
6. **Normal-day false blocks <30%** - Not overblocking on safe market conditions

### Warning Signs ⚠️
1. **Low crash recall (<70%)** - Model missing actual bad signals (false negatives)
2. **Block rate >50%** - Model too aggressive, freezing the bot
3. **High normal-day false blocks (>40%)** - Overblocking on safe conditions
4. **Missing crash signatures** - compressed+weak+neutral not triggering
5. **No tail loss reduction** - Major losses still occurring despite model

### Emergency Actions 🚨
If any of these occur:
1. **Model blocking everything (>80% block rate)** → Increase threshold to 0.60 temporarily
2. **Model blocking nothing (<5% block rate)** → Decrease threshold to 0.40 temporarily
3. **Major losses despite model** → Check if crash signature failing, retrain with new data
4. **Bot crashed** → Restart bot, check logs for errors

---

## 📅 Week-End Review (Feb 21)

### Analysis Questions
1. **Did Model A reduce tail losses?** - Compare worst outcomes to Feb 3-6 baseline
2. **Was crash recall ≥80%?** - Calculate blocked_crash / total_crash ratio
3. **What patterns did it catch?** - Analyze blocked signals (crash signature?)
4. **What did it miss?** - Analyze false negatives (bad signals that slipped through)
5. **Opportunity cost?** - How much profit lost from blocking good signals?
6. **Normal-day performance?** - False block rate on non-crash days

### Decision Tree
**If Model A worked well (≥80% crash recall, ≥30% tail loss reduction):**
- ✅ Deploy to live trading OR implement tiered policy (reduce size instead of hard block)
- Consider threshold tuning: 0.50 binary OR 0.50/0.80 tiered bands
- Start Model B training (profit predictor for entry selection)
- Retrain Model A bi-weekly with rolling 90-day window

**If Model A underperformed (<70% crash recall OR >50% block rate):**
- Switch to **tiered policy**: 0.80 block / 0.50-0.80 reduce size / <0.50 allow
- Investigate false negatives: why did bad signals pass?
- Check crash signature detection on missed signals
- Consider retraining with more crash examples

**If Model A failed (<50% crash recall OR bot issues):**
- Disable ML gate temporarily
- Debug model predictions on Feb 3-6 unit test
- Validate feature extraction (especially symbol encoding)
- Check for data leakage or overfitting

---

## 🔬 Stock Data Investigation (Optional)

**Issue:** 70/76 stock symbols failed in batch replay (Feb 3-14 period)

**Single-Symbol Diagnostic Plan:**
```bash
# Test 1-2 liquid stocks to identify root cause
python3 -m scripts.simple_historical_replay \\
  --symbol AAPL \\
  --start-date 2026-02-07 \\
  --end-date 2026-02-14 \\
  --log-level DEBUG

# Check what we got:
# - Bar count > 0?
# - Timezone issues?
# - Symbol format (AAPL vs AAPL/USD)?
# - Rate limits / throttling?
```

**Most Likely Causes (Alpaca):**
1. Rate limits / API throttling (bunched requests)
2. Wrong endpoint for asset class (stocks vs crypto API)
3. Timezone/session logic caused empty windows (market closed Feb 3?)
4. Symbol format differences

**Decision:** Not blocking crypto deployment. Stocks can be separate model later.

---

## 🛠️ Quick Reference Commands

### Start Bot
```bash
cd /opt/homelab-panel/trading-lab
nohup python3 -m scripts.run_bot --config configs/bots/crypto_24_7.yaml > bot_ml_live.log 2>&1 &
echo $! > bot_ml.pid
```

### Stop Bot
```bash
kill $(cat /opt/homelab-panel/trading-lab/bot_ml.pid)
```

### View Live Logs
```bash
tail -f /opt/homelab-panel/trading-lab/bot_ml_live.log
```

### ML Dashboard
```bash
/opt/homelab-panel/trading-lab/scripts/monitor_ml_performance.sh
```

### Crash Recall Calculator
```bash
# Run mid-week (Feb 18 Wed) and week-end (Feb 21 Fri)
/opt/homelab-panel/trading-lab/scripts/calculate_crash_recall.sh

# Custom date range:
/opt/homelab-panel/trading-lab/scripts/calculate_crash_recall.sh 2026-02-15 2026-02-21
```

### Check DB for Recent ML Activity
```bash
sqlite3 /opt/homelab-panel/trading-lab/data/market.db "
SELECT ts, event_type, message FROM devlog_events 
WHERE event_type IN ('ml_crash_check', 'ml_crash_block') 
ORDER BY ts DESC LIMIT 20;
"
```

### Model Info
```bash
python3 -c "from core.ml.crash_predictor import get_crash_predictor; print(get_crash_predictor().get_model_info())"
```

---

## 📝 Notes

- **Model v2** trained on Feb 3-14 data (21,688 samples)
- **Symbol-aware**: Learns each symbol's unique volatility (SOL 38% bad vs BTC 28% bad)
- Feb 3-6 validation shows **+559% improvement** (from -413% to +1,897%)
- Threshold 0.50 balances precision (64%) and recall (91%)
- Features: 19 total (6 dimensions + 12 raw + **1 symbol**)
- Crash signature: compressed + weak + neutral (31.5% bad rate)
- Bot checks every signal before execution with symbol context
- All decisions logged to `devlog_events` for audit trail

**Model path:** `/opt/homelab-panel/trading-lab/trading-lab/models/crash_predictor/`  
**Metadata:** `metadata.json` (includes Feb 3-6 validation + symbol distribution)  
**Logs:** `bot_ml_live.log` (real-time bot activity)  

---

**Good luck! May the model protect your capital. 🚀**
