#!/bin/bash
set -euo pipefail

# Load environment
set -a
source ~/.hermes/.env 2>/dev/null || true
source /home/alyssa/.openclaw/workspace/alter-bot-v1/.env 2>/dev/null || true
set +a

cd /home/alyssa/.openclaw/workspace/alter-bot-v1

# Validate ALTERBOT_TELEGRAM_TOKEN before use
if [[ -z "${ALTERBOT_TELEGRAM_TOKEN:-}" ]]; then
    echo "ERROR: ALTERBOT_TELEGRAM_TOKEN is not set or empty" >&2
    exit 1
fi

# Today's date for market files
TODAY=$(date +%Y-%m-%d)

# Use python3.12 with timeout wrapper for all data extraction
BALANCE=$(timeout 30 python3.12 -c "import json; print(json.load(open('data/state.json'))['balance'])" 2>/dev/null || echo "?")

OPEN=$(timeout 30 python3.12 -c "
import json, glob, os, signal
signal.alarm(25)
today = '$TODAY'
c = 0
for f in glob.glob('data/markets/*.json'):
    if today not in f: continue
    try:
        if json.load(open(f)).get('position',{}).get('status') == 'open': c += 1
    except: pass
print(c)
" 2>/dev/null)

RECENT=$(timeout 30 python3.12 -c "
import json, glob, signal
signal.alarm(25)
trades = []
today = '$TODAY'
for f in sorted(glob.glob('data/markets/*' + today + '.json')):
    try:
        m = json.load(open(f))
        p = m.get('position',{})
        if p.get('status') == 'closed':
            city = m.get('city_name','')[:6]
            pnl = p.get('pnl', 0)
            trades.append(city + ' ' + str(round(pnl, 2)))
    except: pass
print(' | '.join(trades[:3]) if trades else 'none')
" 2>/dev/null)

MSG="Bot Status | Balance: \$${BALANCE} | Open: ${OPEN} | Recent: ${RECENT}"

# Expand MSG for logging/verification
echo "DEBUG: Sending message: ${MSG}"

curl --max-time 60 -s -X POST "https://api.telegram.org/bot${ALTERBOT_TELEGRAM_TOKEN}/sendMessage" \
    -d "chat_id=392076648" \
    -d "text=${MSG}"
echo ""
echo "DEBUG: curl exit code: $?"
