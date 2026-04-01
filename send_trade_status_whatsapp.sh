#!/bin/bash
# Send paper trade status to WhatsApp every hour
cd /home/alyssa/.openclaw/workspace/alter-bot-v1

# Get balance and trade info
BALANCE=$(python3.12 -c "import json; print(json.load(open('data/state.json'))['balance'])" 2>/dev/null)

# Get open positions count
OPEN=$(python3.12 -c "
import json, glob
count = 0
for f in glob.glob('data/markets/*.json'):
    m = json.load(open(f))
    if m.get('position',{}).get('status') == 'open':
        count += 1
print(count)
" 2>/dev/null)

# Get recent closed trades
RECENT=$(python3.12 -c "
import json, glob
trades = []
for f in sorted(glob.glob('data/markets/*.json'))[-10:]:
    m = json.load(open(f))
    p = m.get('position',{})
    if p.get('status') == 'closed':
        trades.append(f\"{m.get('city_name','')[:10]} +\${p.get('pnl',0):+.2f}\")
print(' | '.join(trades[:3]))
" 2>/dev/null)

MSG="📊 Paper Trading Update

Balance: \$$BALANCE
Open: $OPEN
Recent: $RECENT"

# Send via WhatsApp
wacli send text --to "+601117762080" --message "$MSG" 2>/dev/null

echo "WhatsApp sent: $(date)"