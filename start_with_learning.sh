#!/bin/bash
# Alter Bot V2 - Start with Self-Learning

echo "=== Starting Alter Bot V2 with Self-Learning ==="

CONFIG_FILE="$HOME/.openclaw/workspace/alter-bot-v1/config.json"

# Check if self-learning is enabled
if grep -q '"enabled": false' "$CONFIG_FILE" 2>/dev/null; then
    echo "⚠️ Self-Learning disabled! Enabling..."
    python3.12 << 'PY'
import json
with open('/home/alyssa/.openclaw/workspace/alter-bot-v1/config.json') as f:
    config = json.load(f)

config['self_learning'] = {
    "enabled": True,
    "calibration_mode": "auto",
    "min_trades_for_calibration": 5,
    "auto_reload_biases": True,
    "update_interval_hours": 1
}
config['enable_self_improvement'] = True
config['learn_from_resolved'] = True

with open('/home/alyssa/.openclaw/workspace/alter-bot-v1/config.json', 'w') as f:
    json.dump(config, f, indent=2)
print("✅ Self-Learning ENABLED!")
PY
else
    echo "✅ Self-Learning already enabled"
fi

# Start the bot
pm2 restart alter-bot-v2
echo "=== Bot started with Self-Learning ==="
