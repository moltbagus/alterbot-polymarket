# SKILL.md — Debug Simulation Errors

Debug fill simulation errors, order book issues, and AMM fill rate anomalies in alter-bot-v1.

## When to Use
- Bot reports unexpected fills or missed fills
- `fill_tracker.py` output looks wrong
- AMM simulation behaving unexpectedly

## Debug Flow

### Step 1: Check PM2 logs for errors
```bash
cd ~/.openclaw/workspace/alter-bot-v1
pm2 logs alter-bot-v1 --lines 50 --nostream
```

### Step 2: Check fill tracker state
```bash
python3 -c "from fill_tracker import print_fill_report; print_fill_report()"
```

### Step 3: Check recent market data
```bash
ls -la data/markets/ | tail -10
cat data/markets/<recent_market>.json | python3 -m json.tool | head -80
```

### Step 4: Check self-improvement observations
```bash
ls -la memory/self-improvement/observations/ | tail -5
cat memory/self-improvement/observations/<recent>.json
```

### Step 5: Run a targeted backtest
```bash
python3 proper_backtest.py 2>&1 | tail -30
```

## Common Error Patterns

| Error | Likely Cause | Fix |
|-------|-------------|-----|
| Fill at wrong price | `simulate_fill()` not called | Check `execute_trade()` call path |
| No fills on high-EV trade | Price > $0.50 or volume < 100 | Filter check in code |
| Sigma too tight | City error history outdated | Run `self_improver.py process` |
| Zero-filled bucket | Edge bucket norm_cdf edge case | Check `bucket_prob()` with t_low=-999 or t_high=999 |

## Key Files
- `fill_tracker.py` — AMM simulation logic
- `bot_v2.py` lines 1800-2000 — trade execution path
- `self_improver.py` — error tracking

## Verification
After any fix:
```bash
python3 -m py_compile bot_v2.py
python3 -c "from bot_v2 import *"
pm2 restart alter-bot-v1
pm2 logs alter-bot-v1 --nostream --lines 20
```
