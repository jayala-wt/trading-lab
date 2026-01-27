#!/bin/bash
# Calculate Crash Recall for Model A
# Run mid-week (Feb 18) and week-end (Feb 21)
# 
# Crash recall = blocked_crash / total_crash
# where crash = label_quality='bad' (outcome_60m < -0.5% OR max_drawdown < -2.0%)

DB="data/market.db"

echo "═══════════════════════════════════════════════════════════════════════"
echo "CRASH RECALL CALCULATOR"
echo "═══════════════════════════════════════════════════════════════════════"
echo ""

# Date range (default: current week, override with args)
START_DATE=${1:-$(date -d 'last monday' +%Y-%m-%d)}
END_DATE=${2:-$(date +%Y-%m-%d)}

echo "📅 Analysis Period: $START_DATE to $END_DATE"
echo ""

# Step 1: How many signals have outcomes yet?
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "SAMPLE AVAILABILITY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
sqlite3 $DB <<SQL
SELECT 
    COUNT(*) as total_samples,
    SUM(CASE WHEN outcome_60m IS NOT NULL THEN 1 ELSE 0 END) as with_outcomes,
    SUM(CASE WHEN label_quality IS NOT NULL THEN 1 ELSE 0 END) as with_labels
FROM ml_training_samples
WHERE DATE(created_at) BETWEEN '$START_DATE' AND '$END_DATE';
SQL

echo ""

# Step 2: Label distribution
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "LABEL QUALITY DISTRIBUTION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
sqlite3 $DB <<SQL
.mode column
.headers on
SELECT 
    label_quality,
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) || '%' as pct,
    ROUND(AVG(outcome_60m), 2) || '%' as avg_outcome_60m,
    ROUND(AVG(max_drawdown), 2) || '%' as avg_drawdown
FROM ml_training_samples
WHERE DATE(created_at) BETWEEN '$START_DATE' AND '$END_DATE'
AND outcome_60m IS NOT NULL
GROUP BY label_quality
ORDER BY count DESC;
SQL

echo ""

# Step 3: ML decisions breakdown by actual label
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "ML DECISIONS BY ACTUAL OUTCOME"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Get ML decisions from devlog_events
# Join with ml_training_samples to get actual label_quality
# This requires matching on symbol + timestamp (approximate)

echo ""
echo "⚠️  LIMITATION: Direct join between ML events and outcome labels"
echo "    requires timestamp alignment. For precise crash recall:"
echo ""
echo "    1. Wait until signals have 60min outcomes (approx 1 hour after signal)"
echo "    2. Run this script mid-week (Feb 18) for 3-day sample size"
echo "    3. Run again week-end (Feb 21) for full week validation"
echo ""

# Approximate calculation using signals table
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "ESTIMATED CRASH RECALL (via executed trades)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Count blocked vs allowed signals
TOTAL_CHECKS=$(sqlite3 $DB "SELECT COUNT(*) FROM devlog_events WHERE event_type IN ('ml_crash_check', 'ml_crash_block') AND DATE(ts) BETWEEN '$START_DATE' AND '$END_DATE';")
BLOCKED=$(sqlite3 $DB "SELECT COUNT(*) FROM devlog_events WHERE event_type = 'ml_crash_block' AND DATE(ts) BETWEEN '$START_DATE' AND '$END_DATE';")
ALLOWED=$(sqlite3 $DB "SELECT COUNT(*) FROM devlog_events WHERE event_type = 'ml_crash_check' AND DATE(ts) BETWEEN '$START_DATE' AND '$END_DATE';")

if [ "$TOTAL_CHECKS" -gt "0" ]; then
    BLOCK_RATE=$(echo "scale=1; $BLOCKED * 100 / $TOTAL_CHECKS" | bc)
    echo "Total ML checks:    $TOTAL_CHECKS"
    echo "Blocked (high risk): $BLOCKED ($BLOCK_RATE%)"
    echo "Allowed (safe):      $ALLOWED"
    echo ""
    
    # Check if block rate is in target range
    if (( $(echo "$BLOCK_RATE < 40" | bc -l) )); then
        echo "✅ Block rate within target (≤40%)"
    else
        echo "⚠️  Block rate above target (>40%) - may be too aggressive"
    fi
else
    echo "No ML activity in this period"
fi

echo ""

# Step 4: Trade outcomes for allowed signals
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "ALLOWED SIGNAL OUTCOMES (Check for false negatives)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
sqlite3 $DB <<SQL
.mode column
.headers on
SELECT 
    COUNT(*) as closed_trades,
    SUM(CASE WHEN realized_pnl_pct < -0.5 THEN 1 ELSE 0 END) as losses,
    ROUND(100.0 * SUM(CASE WHEN realized_pnl_pct < -0.5 THEN 1 ELSE 0 END) / COUNT(*), 1) || '%' as loss_rate,
    ROUND(AVG(realized_pnl_pct), 2) || '%' as avg_pnl,
    ROUND(MIN(realized_pnl_pct), 2) || '%' as worst_loss
FROM trades
WHERE status = 'closed'
AND DATE(opened_at) BETWEEN '$START_DATE' AND '$END_DATE';
SQL

echo ""

# Tail losses (crashes that slipped through)
TAIL_LOSSES=$(sqlite3 $DB "SELECT COUNT(*) FROM trades WHERE status = 'closed' AND DATE(opened_at) BETWEEN '$START_DATE' AND '$END_DATE' AND realized_pnl_pct < -2.0;")

if [ "$TAIL_LOSSES" -gt "0" ]; then
    echo "⚠️  Tail losses detected: $TAIL_LOSSES trades with <-2.0% loss"
    echo "    These are potential false negatives (crashes model missed)"
    echo ""
    
    echo "Worst 5 losses (potential model misses):"
    sqlite3 $DB <<SQL
.mode column
.headers on
SELECT 
    symbol,
    SUBSTR(opened_at, 12, 8) as time,
    ROUND(realized_pnl_pct, 2) || '%' as loss,
    side,
    ROUND(qty * entry_price, 2) as notional
FROM trades
WHERE status = 'closed'
AND DATE(opened_at) BETWEEN '$START_DATE' AND '$END_DATE'
AND realized_pnl_pct < -2.0
ORDER BY realized_pnl_pct ASC
LIMIT 5;
SQL
else
    echo "✅ No tail losses (<-2.0%) - model preventing catastrophic trades"
fi

echo ""
echo "═══════════════════════════════════════════════════════════════════════"
echo "🎯 KEY METRICS (Target: ≥80% crash recall, ≤40% block rate)"
echo "═══════════════════════════════════════════════════════════════════════"
echo ""
echo "For precise crash recall, wait 60+ minutes after signals fire,"
echo "then check ml_training_samples for label_quality distribution."
echo ""
echo "Manual calculation:"
echo "  1. Count signals with label_quality='bad' in period"
echo "  2. Count how many of those were blocked (ml_crash_block events)"
echo "  3. Crash recall = blocked_bad / total_bad"
echo ""
echo "Run mid-week (Feb 18) and week-end (Feb 21) for full analysis."
echo "═══════════════════════════════════════════════════════════════════════"

