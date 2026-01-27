#!/bin/bash
cd /opt/homelab-panel/trading-lab

echo "🤖 Starting all trading bots..."
echo "================================"

# Create necessary directories
mkdir -p logs pids

# Get list of enabled bots
for config in configs/bots/*.yaml; do
    bot_name=$(basename "$config" .yaml)
    bot_id=$(grep "^  id:" "$config" | head -1 | awk '{print $2}')
    enabled=$(grep "^  enabled:" "$config" | head -1 | awk '{print $2}')
    
    if [ "$enabled" != "true" ]; then
        echo "⏭️  Skipping $bot_name (not enabled)"
        continue
    fi
    
    echo "🚀 Starting $bot_id ($bot_name)..."
    
    # Start bot in background
    nohup python3 -m scripts.run_bot --config "$config" \
        >> "logs/${bot_id}.log" 2>&1 &
    
    pid=$!
    echo "$pid" > "pids/${bot_id}.pid"
    echo "   PID: $pid → logs/${bot_id}.log"
    sleep 3  # Give bot time to initialize
done

echo ""
echo "✅ Startup complete. Running bots:"
ps aux | grep "run_bot" | grep -v grep | awk '{print "   PID " $2 ": " $NF}'

echo ""
echo "📊 Database status:"
sqlite3 data/market.db "SELECT bot_id, status, datetime(last_run_ts,'localtime') as last_run FROM bots"
