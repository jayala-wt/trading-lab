# Trading Bot Action Items - 2026-02-14

## 🚨 Critical Issues Found

### Issue #1: Dormant Bots Due to Pattern Errors

**crypto_24_7 Bot:**
- Status: Running but failing
- Last Error: `Function not allowed: is_double_bottom`
- Pattern: `double_bottom.yaml`
- Impact: Bot tries to run every 5min but crashes immediately

**stocks_1m_core Bot:**
- Status: Running but failing  
- Last Error: `Function not allowed: gap_fill_pct`
- Pattern: `gap_fill.yaml`
- Impact: Bot tries to run but crashes, 8.23 hours since last successful run

**Root Cause:**
The safe expression engine blocks certain custom functions that are used in pattern detection:
- `is_double_bottom()` - used in double_bottom pattern
- `gap_fill_pct()` - used in gap_fill pattern

**Fix Options:**

**Option 1: Remove problematic patterns from bot configs (Quick Fix)**
```bash
# Edit crypto_24_7.yaml - remove double_bottom pattern and double_bottom_long strategy
# Edit stocks_intraday.yaml - remove gap_fill pattern and gap_trade strategy
```

**Option 2: Whitelist functions in safe expression engine (Proper Fix)**
```python
# In core/patterns/safe_eval.py or similar
ALLOWED_FUNCTIONS = {
    'is_double_bottom': pattern_detectors.is_double_bottom,
    'gap_fill_pct': pattern_detectors.gap_fill_pct,
    # ... other custom functions
}
```

---

## ✅ Immediate Action Plan

### 1. Fix Broken Bots (Priority: HIGH)
```bash
cd /opt/homelab-panel/trading-lab

# Quick fix - disable problematic patterns
# For crypto_24_7
vim configs/bots/crypto_24_7.yaml
# Comment out: - id: double_bottom
# Comment out: - id: double_bottom_long

# For stocks_1m_core  
vim configs/bots/stocks_intraday.yaml
# Comment out: - id: gap_fill
# Comment out: - id: gap_trade

# Restart bots
PYTHONPATH=/opt/homelab-panel/trading-lab python3 scripts/run_bot.py --config configs/bots/crypto_24_7.yaml --once
PYTHONPATH=/opt/homelab-panel/trading-lab python3 scripts/run_bot.py --config configs/bots/stocks_intraday.yaml --once
```

### 2. Investigate Feb 3 Crash (Priority: HIGH)
```bash
cd /opt/homelab-panel/trading-lab

# Check devlog for Feb 3
sqlite3 data/market.db "
SELECT ts, level, event_type, message
FROM devlog_events
WHERE DATE(ts) = '2026-02-03'
ORDER BY ts;"

# Check trades on Feb 3
sqlite3 data/market.db "
SELECT symbol, entry_price, exit_price, realized_pnl, ts_open, ts_close
FROM trades
WHERE DATE(ts_open) = '2026-02-03'
ORDER BY realized_pnl ASC
LIMIT 20;"
```

**Feb 3 Analysis:**
- -$155.54 total loss
- 8.75% win rate (28 wins / 292 losses)
- 320 total trades
- **This looks like a market event or systematic issue**

### 3. Balance Bot Activity (Priority: MEDIUM)

**Current State:**
- crypto_5m_core: 5,413 trades (86%)
- crypto_24_7: 703 trades (11%) - BROKEN
- stocks_1m_core: 201 trades (3%) - BROKEN

**Goal:** Balanced distribution (~33% each)

**Options:**
- Reduce crypto_5m_core interval: 5m → 15m or 30m
- Add more stock symbols to stocks_1m_core (currently only traded 4 symbols)
- Enable momentum_trader and swing_master bots

### 4. ML Data Export (Priority: LOW - data is already good)
```bash
cd /opt/homelab-panel/trading-lab

# Export ML training data
sqlite3 data/market.db << 'EOF'
.mode csv
.output ml_training_data_2026-02-14.csv
SELECT * FROM ml_training_samples;
.quit
EOF

# Export to Python-friendly format
sqlite3 data/market.db << 'EOF'
.mode json
.output ml_training_data_2026-02-14.json
SELECT * FROM ml_training_samples WHERE outcome_5m IS NOT NULL;
.quit
EOF
```

---

## 📊 Performance Insights

### What's Working:
✅ **stocks_1m_core performance** - +$138 profit (86% from AAPL alone)  
✅ **ML data collection** - 20,108 high-quality labeled samples  
✅ **Quality labels** - 79% win rate on "good" signals  
✅ **dim_momentum_reversal_buy** - +12% avg outcome (best pattern)  
✅ **Risk management** - Daily limits prevent catastrophic losses  

### What's Not Working:
❌ **Crypto pairs all negative** - BTC, ETH, SOL, AVAX, DOGE all losing  
❌ **crypto_5m_core dominance** - 86% of trades, drowning out other bots  
❌ **Feb 3 crash** - -$155.54 loss needs investigation  
❌ **Broken bots** - 2 out of 3 active bots have pattern errors  
❌ **dim_volatility_squeeze** - Near 50/50 win rate (coin flip)  

---

## 🎯 Strategic Recommendations

### Short Term (This Week):
1. ✅ Fix broken bot patterns (remove double_bottom and gap_fill)
2. ✅ Restart crypto_24_7 and stocks_1m_core
3. ✅ Investigate Feb 3 crash
4. Monitor daily performance for balance

### Medium Term (This Month):
1. **Focus on stocks** - they're profitable!
   - Expand stocks_1m_core to more symbols (currently has 72 defined, only traded 4)
   - Increase position size for stocks (currently $20 max)
   - Add time-of-day filters (first hour momentum, power hour, etc.)

2. **Reduce crypto noise**
   - Change crypto_5m_core interval: 5m → 15m
   - Add volume filters (require >1.5x avg volume)
   - Only trade high-confidence patterns

3. **Enable dormant bots**
   - momentum_trader (registered, never traded)
   - swing_master (registered, never traded)

### Long Term (Next Quarter):
1. **Train ML model** at 30K+ samples
   - Target: Predict which "neutral" signals should be "good" or "bad"
   - Use features: dimension states + raw indicators
   - Validate with walk-forward testing

2. **Backtest strategy refinements**
   - Test time-of-day filters
   - Test symbol-specific parameters
   - Test combined patterns (require 2+ signals to agree)

3. **Scale up if profitable**
   - Move from $20 → $50 position size
   - Increase daily trade limit: 20 → 50
   - Add more stock symbols

---

## 📁 Files to Review

Key configurations to edit:
- [configs/bots/crypto_24_7.yaml](configs/bots/crypto_24_7.yaml) - Remove double_bottom
- [configs/bots/stocks_intraday.yaml](configs/bots/stocks_intraday.yaml) - Remove gap_fill
- [configs/bots/crypto_intraday.yaml](configs/bots/crypto_intraday.yaml) - Consider 15m timeframe
- [configs/risk/crypto.yaml](configs/risk/crypto.yaml) - Current: 20 trades/day, $75 max loss
- [configs/risk/stocks.yaml](configs/risk/stocks.yaml) - Review limits

Pattern definitions:
- [configs/patterns/double_bottom.yaml](configs/patterns/double_bottom.yaml) - BROKEN
- [configs/patterns/gap_fill.yaml](configs/patterns/gap_fill.yaml) - BROKEN
- [configs/patterns/volatility_squeeze.yaml](configs/patterns/volatility_squeeze.yaml) - Low quality (48% win rate)

---

## 🔧 Commands to Run Now

```bash
# Navigate to trading-lab
cd /opt/homelab-panel/trading-lab

# 1. Check current bot status
PYTHONPATH=/opt/homelab-panel/trading-lab python3 -c "
from core.data.db import Database
from pathlib import Path
import os
os.chdir('/opt/homelab-panel/trading-lab')
db = Database(Path('data/market.db'))
bots = db.query('SELECT bot_id, status, last_error FROM bots')
for bot in bots:
    print(f\"{bot['bot_id']:20} {bot['status']:10} {bot['last_error']}\")
"

# 2. Quick fix - disable broken patterns in crypto_24_7
sed -i 's/^    - id: double_bottom$/    # - id: double_bottom  # DISABLED - function not allowed/' configs/bots/crypto_24_7.yaml
sed -i 's/^    - id: double_bottom_long$/    # - id: double_bottom_long  # DISABLED - depends on double_bottom/' configs/bots/crypto_24_7.yaml

# 3. Quick fix - disable broken patterns in stocks_intraday
sed -i 's/^    - id: gap_fill$/    # - id: gap_fill  # DISABLED - function not allowed/' configs/bots/stocks_intraday.yaml
sed -i 's/^    - id: gap_trade$/    # - id: gap_trade  # DISABLED - depends on gap_fill/' configs/bots/stocks_intraday.yaml

# 4. Test bots (dry run)
PYTHONPATH=/opt/homelab-panel/trading-lab python3 scripts/run_bot.py --config configs/bots/crypto_24_7.yaml --once
PYTHONPATH=/opt/homelab-panel/trading-lab python3 scripts/run_bot.py --config configs/bots/stocks_intraday.yaml --once

# 5. If successful, check status again
PYTHONPATH=/opt/homelab-panel/trading-lab python3 -c "
from core.data.db import Database
from pathlib import Path
import os
os.chdir('/opt/homelab-panel/trading-lab')
db = Database(Path('data/market.db'))
bots = db.query('SELECT bot_id, status, last_run_ts, last_error FROM bots ORDER BY last_run_ts DESC')
for bot in bots:
    print(f\"{bot['bot_id']:20} {bot['status']:10} {bot['last_run_ts']:30} {bot['last_error']}\")
"
```

---

## 📈 Expected Improvements

After fixes:
- ✅ All 3 bots trading successfully
- ✅ More balanced trade distribution
- ✅ stocks_1m_core generating profit again
- ✅ Faster ML data accumulation
- ✅ Better pattern diversity

Target metrics (next 7 days):
- Daily trades: 400-600 (currently 150-500)
- Bot balance: 40% crypto_5m, 30% crypto_24_7, 30% stocks
- Daily P&L: Break even or better
- ML samples: 25K+ (currently 20K)
- Win rate: 50%+ sustained

---

**Next Review:** 2026-02-21 (7 days)  
**Success Criteria:** All bots running, stocks profitable, 25K+ ML samples
