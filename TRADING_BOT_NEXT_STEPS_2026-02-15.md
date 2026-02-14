# Trading Bot System - Next Steps & Action Plan

**Generated:** February 15, 2026, 23:15 UTC  
**Priority:** 🔴 **CRITICAL** - 4 of 5 bots offline  
**Estimated Time:** 2-3 hours  
**Dependencies:** None (can start immediately)

---

## 🚨 IMMEDIATE ACTIONS (Tonight - Next 30 Minutes)

### Action #1: Trigger Knowledge Reindex NOW ⚡
**Why:** 17 trading-lab docs from Feb 14 not indexed, AI has no context  
**Impact:** HIGH - AI can't find documented state

```bash
# Check current indexing status
mcp_homelab_knowledge_status

# Trigger manual reindex
mcp_homelab_knowledge_reindex

# Verify trading docs are now found
mcp_homelab_knowledge_search --query "ML crash predictor" --limit 5
```

**Expected Result:** Should find MODEL_A_WEEK1_MONITORING.md and related docs

---

### Action #2: Investigate Bot Startup Failures 🔍
**Why:** 4 bots stuck in "starting" since Feb 14 06:07  
**Impact:** HIGH - Missing 80% of trading capacity

```bash
cd /opt/homelab-panel/trading-lab

# Check if there are any bot logs
ls -lht *.log | head -20

# Check database for bot errors
sqlite3 data/market.db "SELECT bot_id, status, last_error FROM bots"

# Check for pattern errors (from ACTION_ITEMS_2026-02-14.md)
sqlite3 data/market.db "
SELECT ts, level, event_type, message 
FROM devlog_events 
WHERE message LIKE '%Function not allowed%' 
   OR message LIKE '%double_bottom%'
   OR message LIKE '%gap_fill%'
ORDER BY ts DESC 
LIMIT 20"

# Check system logs around Feb 14 06:07
journalctl --since "2026-02-14 06:00" --until "2026-02-14 06:15" | grep -i trading
```

**Known Issues (from Feb 14 docs):**
- `double_bottom` pattern → "Function not allowed: is_double_bottom"
- `gap_fill` pattern → "Function not allowed: gap_fill_pct"

**Expected Finding:** Bots tried to start but crashed due to forbidden pattern functions

---

### Action #3: Fix Bot Configurations 🔧

Based on ACTION_ITEMS_2026-02-14.md, these patterns are DISABLED:

**crypto_24_7.yaml:**
- ✅ Already disabled: `# - id: double_bottom` (line 39)
- ✅ Already disabled: `# - id: double_bottom_long` (line 71)

**stocks_intraday.yaml:**
- ✅ Already disabled: `# - id: gap_fill` (line 148)
- ✅ Already disabled: `# - id: gap_trade` (line 172)

**Verify other bots don't use these patterns:**
```bash
cd /opt/homelab-panel/trading-lab

# Check if other bots reference forbidden patterns
grep -n "double_bottom\|gap_fill" configs/bots/*.yaml
```

If found, comment them out like crypto_24_7 and stocks_intraday.

---

### Action #4: Clean Stale Bot State & Restart All 🔄

```bash
cd /opt/homelab-panel/trading-lab

# Clear stale bot status in database
sqlite3 data/market.db "
UPDATE bots 
SET status = 'stopped', 
    heartbeat_ts = NULL, 
    last_error = 'Manually reset - restarting all bots'
WHERE bot_id IN ('crypto_5m_core', 'stocks_1m_core', 'momentum_trader', 'swing_master')
"

# Kill any zombie processes
ps aux | grep "run_bot" | grep -v grep | awk '{print $2}' | xargs -r kill

# Create bot startup script
cat > start_all_bots.sh << 'EOF'
#!/bin/bash
cd /opt/homelab-panel/trading-lab

# Start each bot in background
for config in configs/bots/*.yaml; do
    bot_name=$(basename "$config" .yaml)
    echo "Starting $bot_name..."
    
    nohup python3 -m scripts.run_bot --config "$config" \
        >> "logs/${bot_name}.log" 2>&1 &
    
    pid=$!
    echo "$pid" > "pids/${bot_name}.pid"
    echo "  PID: $pid"
    sleep 2
done

echo ""
echo "All bots started. Check status:"
ps aux | grep "run_bot" | grep -v grep
EOF

chmod +x start_all_bots.sh

# Create necessary directories
mkdir -p logs pids

# Run it!
./start_all_bots.sh
```

**Expected Result:** 5 bot processes running, all with unique PIDs

---

### Action #5: Monitor Bot Startup (30 seconds per bot)

```bash
cd /opt/homelab-panel/trading-lab

# Watch bot logs for errors
tail -f logs/*.log

# Check bot status in database
watch -n 5 'sqlite3 data/market.db "SELECT bot_id, status, datetime(last_run_ts) as last_run FROM bots"'

# Check for ML decisions (crypto_24_7 only has ML)
watch -n 10 'sqlite3 data/market.db "
SELECT event_type, COUNT(*) as count 
FROM devlog_events 
WHERE ts >= datetime(\"now\", \"-10 minutes\")
  AND event_type LIKE \"ml_%\"
GROUP BY event_type
"'
```

**Success Criteria:**
- All 5 bots show "running" status
- Last_run_ts updates every 1-5 minutes
- No error messages in logs
- ML decisions appearing in devlog_events

---

## 📊 VALIDATION CHECKS (After 15 Minutes)

### Check #1: Bot Trading Activity

```bash
cd /opt/homelab-panel/trading-lab

# Check trades per bot in last 15 minutes
sqlite3 -header -column data/market.db "
SELECT bot_id, COUNT(*) as trades, 
       ROUND(SUM(realized_pnl), 2) as total_pnl
FROM trades 
WHERE ts_open >= datetime('now', '-15 minutes')
GROUP BY bot_id
ORDER BY trades DESC
"
```

**Expected:**
- crypto_5m_core: 30-60 trades (runs every 5min, 6 symbols)
- crypto_24_7: 10-30 trades (runs every 5min, 6 symbols)
- stocks_1m_core: 0-10 trades (market closed after hours)
- momentum_trader: 0-5 trades (market closed)
- swing_master: 0-5 trades (market closed)

---

### Check #2: ML Crash Predictor Performance

```bash
cd /opt/homelab-panel/trading-lab

# Check ML decisions for crypto_24_7
python3 << 'EOF'
import sqlite3, json
from datetime import datetime, timedelta

conn = sqlite3.connect('data/market.db')
conn.row_factory = sqlite3.Row

since = (datetime.now() - timedelta(minutes=15)).isoformat()
rows = conn.execute('''
    SELECT event_type, payload_json
    FROM devlog_events 
    WHERE ts >= ? 
      AND event_type IN ('ml_crash_check', 'ml_crash_block')
    ORDER BY ts DESC
''', (since,)).fetchall()

blocks = sum(1 for r in rows if r['event_type'] == 'ml_crash_block')
allows = sum(1 for r in rows if r['event_type'] == 'ml_crash_check')
total = len(rows)

if total > 0:
    print(f"ML Crash Predictor Decisions (last 15 min):")
    print(f"  Total decisions: {total}")
    print(f"  ✓ Allowed: {allows} ({allows/total*100:.1f}%)")
    print(f"  ✗ Blocked: {blocks} ({blocks/total*100:.1f}%)")
    print(f"\nBlock rate: {blocks/total*100:.1f}%")
    
    if blocks/total > 0.6:
        print("⚠️  WARNING: Blocking >60% of trades - threshold may be too low")
    elif blocks/total < 0.1:
        print("⚠️  WARNING: Blocking <10% of trades - threshold may be too high")
    else:
        print("✅ Block rate looks healthy (10-60%)")
        
    print("\nRecent decisions:")
    for r in rows[:10]:
        payload = json.loads(r['payload_json'])
        prob = payload.get('crash_probability', 0)
        symbol = payload.get('symbol', '?')
        decision = 'BLOCK' if r['event_type'] == 'ml_crash_block' else 'ALLOW'
        print(f"  [{decision:5}] {symbol:8} p(crash)={prob:.3f}")
else:
    print("No ML decisions yet - waiting for signals...")

conn.close()
EOF
```

**Expected:**  
Block rate: 20-40% (based on 24.9% crash rate in training data)

---

### Check #3: Pattern Error Check

```bash
cd /opt/homelab-panel/trading-lab

# Look for forbidden function errors
sqlite3 data/market.db "
SELECT bot_id, ts, message 
FROM devlog_events 
WHERE ts >= datetime('now', '-30 minutes')
  AND (message LIKE '%Function not allowed%'
    OR message LIKE '%double_bottom%'
    OR message LIKE '%gap_fill%')
ORDER BY ts DESC
"
```

**Expected:** No results (all forbidden patterns disabled)

---

## 🔄 TOMORROW (February 16, 2026)

### Morning Check (10:00 UTC)

1. **Bot Uptime Verification**
   ```bash
   cd /opt/homelab-panel/trading-lab
   ps aux | grep "run_bot" | grep -v grep | wc -l  # Should be 5
   ```

2. **Overnight Performance**
   ```bash
   sqlite3 -header -column data/market.db "
   SELECT bot_id, 
          COUNT(*) as trades,
          ROUND(SUM(realized_pnl), 2) as pnl,
          ROUND(AVG(realized_pnl), 4) as avg_pnl,
          COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) as wins,
          COUNT(CASE WHEN realized_pnl < 0 THEN 1 END) as losses
   FROM trades
   WHERE ts_open >= datetime('now', '-12 hours')
   GROUP BY bot_id
   ORDER BY trades DESC
   "
   ```

3. **ML Effectiveness Check**
   ```bash
   # Compare blocked vs allowed trade outcomes
   # (This requires waiting 60min for outcomes to populate)
   ./scripts/calculate_crash_recall.sh
   ```

---

### Afternoon Tasks (16:00 UTC)

1. **Balance Bot Activity**
   - Review trade distribution across bots
   - Adjust intervals if one bot dominates (like crypto_5m_core did before)
   - Consider reducing crypto_5m_core from 5min → 15min

2. **Enable Additional Symbols**
   - stocks_intraday has 72 symbols defined but only traded 4
   - Consider enabling top 10-20 high-volume stocks

3. **Review Risk Limits**
   - Check if daily limits too restrictive
   - Review max_position_usd ($20 might be too small for stocks)

---

## 📅 THIS WEEK (Feb 17-21, 2026)

### Wednesday (Feb 19): Mid-Week ML Check

**Goal:** Validate ML crash predictor is improving outcomes

```bash
cd /opt/homelab-panel/trading-lab

# Run crash recall analysis
python3 << 'EOF'
import sqlite3, json
from datetime import datetime, timedelta

conn = sqlite3.connect('data/market.db')

# Get ML blocks from Mon-Wed
blocks = conn.execute('''
    SELECT payload_json
    FROM devlog_events
    WHERE ts >= datetime('now', '-3 days')
      AND event_type = 'ml_crash_block'
''').fetchall()

# Get ML allows from Mon-Wed
allows = conn.execute('''
    SELECT payload_json
    FROM devlog_events
    WHERE ts >= datetime('now', '-3 days')
      AND event_type = 'ml_crash_check'
''').fetchall()

print(f"ML Decisions (Mon-Wed):")
print(f"  Blocked: {len(blocks)}")
print(f"  Allowed: {len(allows)}")
print(f"  Block rate: {len(blocks)/(len(blocks)+len(allows))*100:.1f}%")

# TODO: Calculate crash recall (need to join with ml_training_samples)
# For each block, check if it would have been a crash (outcome_60m < -0.5%)
# For each allow, check if it was actually safe

conn.close()
EOF
```

**Success Criteria:**
- Crash recall ≥80% (catches 80%+ of bad trades)
- Block rate 20-40% (not blocking too many trades)

---

### Friday (Feb 21): Week 1 ML Report

Create comprehensive report:
- ML model performance
- Bot P&L comparison (with vs without ML)
- Crash signatures detected
- False positives analysis
- Recommendations for threshold tuning

**Template:** `/opt/homelab-panel/trading-lab/ML_WEEK1_REPORT_TEMPLATE.md`

---

## 🔧 NEXT SPRINT (Feb 22-28, 2026)

### Fix #1: Knowledge Ingestion Interval
**Current:** 24 hours (too slow)  
**Target:** 6 hours OR file-system triggered

**Implementation:**
```bash
# Option A: Reduce cron interval
crontab -e
# Change from: 0 3 * * * /opt/homelab-panel/scripts/automation/...
# To:         0 */6 * * * /opt/homelab-panel/scripts/automation/...

# Option B: File watcher (inotifywait)
# Monitor /opt/homelab-panel/trading-lab/*.md for changes
# Trigger reindex on create/modify
```

---

### Fix #2: Bot Health Monitoring
**Goal:** Auto-restart stuck bots, alert on crashes

**Create:** `scripts/monitor_bot_health.sh`
```bash
#!/bin/bash
# Check every 5 minutes:
# - Are all enabled bots running?
# - Are heartbeats updating?
# - Are there zombie processes?
# - Restart if needed
```

Add to cron: `*/5 * * * *`

---

### Fix #3: ML Model Retraining Schedule
**Current:** Manual  
**Target:** Automated bi-weekly

```bash
# Add to cron (every 2 weeks on Sunday 2am)
0 2 */14 * 0 cd /opt/homelab-panel/trading-lab && python3 scripts/retrain_crash_predictor.py

# Also trigger after batch historical replay (new data)
```

---

## 📋 CHECKLIST (Print & Track)

### Tonight (Feb 15, 2026):
- [ ] Trigger knowledge reindex
- [ ] Investigate bot startup logs
- [ ] Clean database bot state
- [ ] Start all 5 bots
- [ ] Monitor for 30 minutes
- [ ] Verify ML decisions appearing
- [ ] Check for pattern errors
- [ ] Document any issues found

### Tomorrow Morning (Feb 16):
- [ ] Verify all 5 bots still running
- [ ] Check overnight P&L
- [ ] Review ML block rate
- [ ] Balance bot activity if needed

### This Week:
- [ ] Wed: Calculate ML crash recall
- [ ] Fri: Generate Week 1 ML report
- [ ] Fix knowledge ingestion interval
- [ ] Implement bot health monitoring

### Next Week:
- [ ] Automate ML retraining
- [ ] Review ML threshold (0.50)
- [ ] Consider tiered risk policy
- [ ] Add more stock symbols

---

## 🚀 LONG-TERM ROADMAP (March 2026)

1. **Train Model B:** Exit optimizer (improve stop-loss timing)
2. **Scale up:** Increase position size if profitable ($20 → $50)
3. **Add symbols:** Expand to top 50 stocks (high volume)
4. **Backtest:** Validate ML on Q1 2026 data
5. **Deploy to production:** Move from paper → live (if ≥60% win rate)

---

**Status:** 🔴 **Action Required**  
**Owner:** User + AI Assistant  
**Next Review:** Feb 16, 2026, 10:00 UTC  
**Related Docs:**
- [TRADING_BOT_ML_TRAINING_2026-02-15.md](./TRADING_BOT_ML_TRAINING_2026-02-15.md)
- [MODEL_A_WEEK1_MONITORING.md](/opt/homelab-panel/trading-lab/MODEL_A_WEEK1_MONITORING.md)
- [ACTION_ITEMS_2026-02-14.md](/opt/homelab-panel/trading-lab/ACTION_ITEMS_2026-02-14.md)
