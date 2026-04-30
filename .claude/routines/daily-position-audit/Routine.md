# Daily Position Audit

*Schedule: Every day at 09:00 MYT (0100 UTC)*

## Purpose
Quick morning scan of open positions, balance, and portfolio health before market activity.

## What to Check
1. Open positions — any in AVOID/TIER 3 cities?
2. Balance vs yesterday — any unexpected drawdown?
3. Recent fills — any anomalous results?
4. Self-improvement observations — any new city errors?

## Commands
```bash
cd ~/.openclaw/workspace/alter-bot-v1
python3 bot_v2.py status
python3 -c "from fill_tracker import print_fill_report; print_fill_report()"
ls memory/self-improvement/observations/ | tail -3
```

## Output
If any issue found → log to `memory/daily-audit-YYYY-MM-DD.md` and alert via Telegram.

## Thresholds
- Alert if balance drawdown > 10% from peak
- Alert if any position in AVOID list city
- Alert if fill_rate_anomaly detected
