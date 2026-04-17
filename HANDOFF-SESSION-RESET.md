# ALTER-BOT-V2 — SESSION RESET HANDOFF
# Written: Session reset during active debugging

## Current State (as of session reset)

**PM2 Status**: `alter-bot-v2` is in `waiting restart` state (21 restarts). The process keeps crashing.

**Immediate crash**: `NameError: name 'forecast_src' is not defined` at line ~1595 in `bot_v2.py`. This was confirmed as the active error.

**The mystery**: pm2 shows `script path: bot_v2.py` but the error log shows crashes from `weatherbet.py`. There may be TWO processes running — the actual `alter-bot-v2` (bot_v2.py) and a separate `weatherbet.py` process. Need to verify with `ps aux | grep bot` and `pm2 list`.

## Files involved

- `/home/alyssa/.openclaw/workspace/alter-bot-v1/bot_v2.py` (2265 lines)
- `/home/alyssa/.openclaw/workspace/alter-bot-v1/tradingagents_integration.py`
- `/home/alyssa/.openclaw/workspace/alter-bot-v1/config.json`

## All fixes applied (confirmed via read_file)

1. `MAX_PRICE = 0.50` in bot_v2.py line ~1766 (was 0.35)
2. YES/NO swap at lines ~1479-1483 (prices[0]=no, prices[1]=yes)
3. Temperature unit `temperature_unit=c` passed to Open-Meteo
4. `MIN_PRICE = 0.01` in tradingagents_integration.py (was 0.05) — TWO places
5. Disagreement threshold `> 0.60` (was `> 0.20`) — TWO places in RiskManager.evaluate()
6. Tokyo skip logic changed to `> MAX_PRICE` (was `>=`)

## Next steps after reset

1. Run execplan: `hermes execplan FIX-ALTER-BOT-V2-TRADING.md`
2. OR load skill `debug-production-polymarket-bot` and follow it
3. Fix the `forecast_src` NameError FIRST
4. Then do clean restart:
   ```
   pm2 stop alter-bot-v2
   find /home/alyssa/.openclaw/workspace/alter-bot-v1 -name "*.pyc" -delete
   pm2 start /home/alyssa/.openclaw/workspace/alter-bot-v1/bot_v2.py --name alter-bot-v2 -- \
     -c /home/alyssa/.openclaw/workspace/alter-bot-v1/config.json
   ```
5. Verify with `tail -30 ~/.pm2/logs/alter-bot-v2-out.log`
6. If still crashing, use `python3 -c "exec(open('bot_v2.py').read())"` to get full traceback

## Full context and history

See the large assistant message (above this handoff) for the full story — 39 cities, cascading failure chain, all code changes, key decisions about YES/NO price format, temperature units, disagreement threshold, etc.
