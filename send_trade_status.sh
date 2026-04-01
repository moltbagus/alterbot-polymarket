#!/bin/bash
cd /home/alyssa/.openclaw/workspace/alter-bot-v1

BALANCE=$(cat data/state.json | python3.12 -c "import json,sys; print(json.load(sys.stdin)['balance'])" 2>/dev/null)

OPEN=$(python3.12 -c "
import json, glob
c=0
for f in glob.glob('data/markets/*.json'):
    try:
        if json.load(open(f)).get('position',{}).get('status')=='open': c+=1
    except: pass
print(c)
" 2>/dev/null)

RECENT=$(python3.12 -c "
import json, glob
trades = []
for f in sorted(glob.glob('data/markets/*.json'))[-10:]:
    try:
        m = json.load(open(f))
        p = m.get('position',{})
        if p.get('status')=='closed':
            city = m.get('city_name','')[:6]
            pnl = p.get('pnl',0)
            trades.append(city + ' ' + str(round(pnl,2)))
    except: pass
print(' | '.join(trades[:3]) if trades else 'none')
" 2>/dev/null)

MSG="Balance: \$BALANCE | Open: \$OPEN | Recent: \$RECENT"

curl -s -X POST "https://api.telegram.org/bot8397077340:AAG6mYJc-Y3I2GKKgAdkhhvJtZlc2iwsEAY/sendMessage" \
    -d "chat_id=392076648" \
    -d "text=$MSG"