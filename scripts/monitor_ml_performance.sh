#!/bin/bash
# ML Crash Predictor - Weekly Performance Monitor
# Track Model A performance: blocks, precision, outcomes
# Run daily: ./monitor_ml_performance.sh

DB="data/market.db"

echo "═══════════════════════════════════════════════════════════════════════"
echo "ML CRASH PREDICTOR - PERFORMANCE DASHBOARD"
echo "═══════════════════════════════════════════════════════════════════════"
echo ""

# Date range
START_DATE=$(date -d '7 days ago' +%Y-%m-%d)
END_DATE=$(date +%Y-%m-%d)

echo "📅 Date Range: $START_DATE to $END_DATE"
echo ""

# ML Events Summary
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "ML ACTIVITY SUMMARY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
sqlite3 $DB <<SQL
SELECT 
    event_type,
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) as pct
FROM devlog_events
WHERE (event_type LIKE '%ml%' OR event_type LIKE '%crash%')
AND DATE(ts) BETWEEN '$START_DATE' AND '$END_DATE'
GROUP BY event_type
ORDER BY count DESC;
SQL

echo ""

# Blocked signals breakdown
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "ML BLOCKS (High Risk Signals Prevented)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
sqlite3 $DB <<SQL
SELECT 
    DATE(ts) as date,
    COUNT(*) as blocked_count
FROM devlog_events
WHERE event_type = 'ml_crash_block'
AND DATE(ts) BETWEEN '$START_DATE' AND '$END_DATE'
GROUP BY DATE(ts)
ORDER BY date DESC;
SQL

TOTAL_BLOCKS=$(sqlite3 $DB "SELECT COUNT(*) FROM devlog_events WHERE event_type = 'ml_crash_block' AND DATE(ts) BETWEEN '$START_DATE' AND '$END_DATE';")

if [ "$TOTAL_BLOCKS" -eq "0" ]; then
    echo "No signals blocked (all passed threshold)"
fi

echo ""

# Probability distribution
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "CRASH PROBABILITY DISTRIBUTION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
sqlite3 $DB <<SQL
.mode column
.headers on
WITH probabilities AS (
    SELECT 
        json_extract(payload_json, '$.crash_probability') as prob,
        json_extract(payload_json, '$.symbol') as symbol,
        ts
    FROM devlog_events
    WHERE event_type IN ('ml_crash_check', 'ml_crash_block')
    AND DATE(ts) BETWEEN '$START_DATE' AND '$END_DATE'
)
SELECT 
    CASE
        WHEN prob < 0.2 THEN '0-20% (Very Low)'
        WHEN prob < 0.4 THEN '20-40% (Low)'
        WHEN prob < 0.5 THEN '40-50% (Moderate)'
        WHEN prob < 0.6 THEN '50-60% (High) ⚠️'
        WHEN prob < 0.8 THEN '60-80% (Very High) 🚨'
        ELSE '80-100% (Extreme) 🔴'
    END as risk_level,
    COUNT(*) as count,
    ROUND(AVG(prob) * 100, 1) || '%' as avg_prob
FROM probabilities
GROUP BY risk_level
ORDER BY MIN(prob);
SQL

echo ""

# Crash Recall calculation (requires outcome data)
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "CRASH RECALL (Target: ≥80%)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "⚠️  Crash recall requires outcome data (60min window)."
echo "    Check this metric mid-week (Feb 18) and week-end (Feb 21)"
echo "    when enough signals have closed to calculate actual bad rate."
echo ""
echo "Formula: blocked_crash / total_crash (where crash = label_quality='bad')"
echo ""

# Recent ML decisions
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "RECENT ML DECISIONS (Last 10)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
sqlite3 $DB <<SQL
.mode column
.headers on
SELECT 
    SUBSTR(ts, 12, 8) as time,
    json_extract(payload_json, '$.symbol') as symbol,
    ROUND(json_extract(payload_json, '$.crash_probability') * 100, 1) || '%' as crash_prob,
    CASE 
        WHEN event_type = 'ml_crash_block' THEN '🚫 BLOCKED'
        ELSE '✅ ALLOWED'
    END as decision
FROM devlog_events
WHERE event_type IN ('ml_crash_check', 'ml_crash_block')
AND DATE(ts) BETWEEN '$START_DATE' AND '$END_DATE'
ORDER BY ts DESC
LIMIT 10;
SQL

echo ""
echo "═══════════════════════════════════════════════════════════════════════"
echo "Model: crash_predictor v2 (symbol-aware, trained 2026-02-14)"
echo "Threshold: 0.50 (64% precision, 91% recall on Feb 3-6)"
echo "Target: label_quality='bad' (loss avoidance)"
echo "Features: 19 (6 dimensions + 12 raw + symbol)"
echo "═══════════════════════════════════════════════════════════════════════"
