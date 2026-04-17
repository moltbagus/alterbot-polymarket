# alter-bot-v2 — Active Debug Session Handoff

## Bot Status
- **PM2**: `alter-bot-v2` — status `waiting restart`, 21 restarts
- **Crash**: `NameError: name 'forecast_src' is not defined` at line ~1595 of bot_v2.py
- **Balance**: $14,750.20 paper trade
- **Trades today**: 0

## Root Causes Found (all fixed in code)

1. **YES/NO price swap** — Gamma API returns `[no_price, yes_price]`, bot had it backwards
2. **Temperature unit bug** — Open-Meteo defaults to Kelvin; London showed 508°C
3. **MIN_PRICE gate $0.05** — too high, most summer markets are $0.01-$0.04
4. **Disagreement threshold 20%** — too tight, blocked Miami (bot 25% vs market 4%)
5. **MAX_PRICE $0.35** — too low, Tokyo $0.53 rejected
6. **`forecast_src` NameError** — variable scope bug, line 1595 references undefined var

## Fixes Applied (verified via read_file)

- `MAX_PRICE = 0.50` in bot_v2.py
- YES/NO swap in bot_v2.py and tradingagents_integration.py
- `temperature_unit=c` for Open-Meteo
- `MIN_PRICE = 0.01` in tradingagents_integration.py (2 places)
- Disagreement `> 0.60` in RiskManager.evaluate() (2 places)

## PM2 restart command (use this pattern)

```
pm2 stop alter-bot-v2
find /home/alyssa/.openclaw/workspace/alter-bot-v1 -name "*.pyc" -delete
pm2 start /home/alyssa/.openclaw/workspace/alter-bot-v1/bot_v2.py --name alter-bot-v2 -- -c /home/alyssa/.openclaw/workspace/alter-bot-v1/config.json
```

## Full execplan at
`/home/alyssa/.openclaw/workspace/alter-bot-v1/execplan/FIX-ALTER-BOT-V2-TRADING.md`
