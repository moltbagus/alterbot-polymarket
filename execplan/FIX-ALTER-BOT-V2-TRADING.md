# ExecPlan: Fix alter-bot-v2 — Restore Live Trading

> [⬛ Musk] Going forward, this will require being extremely hardcore. Only exceptional performance constitutes a passing grade.

## Purpose / Big Picture

alter-bot-v2 is a Polymarket weather prediction trading bot running under PM2 at `~/.openclaw/workspace/alter-bot-v1/bot_v2.py`. As of 2026-04-12 ~17:00 MYT, the bot is **online but producing zero trades** — it enters `monitor_positions()` and never attempts a new position. The balance is $14,750.20 (paper). Two separate problems must be diagnosed and fixed:

1. **The crash loop** — bot previously crashed with `NameError: name 'forecast_src' is not defined` and PM2 did NOT auto-recover (0 restarts logged). The bot was manually restarted at 13:14 but the error log still shows the old crash. Root cause needs to be found and fixed in code.
2. **The no-trade symptom** — bot is scanning markets but every city is being SKIPPED. The logs show all cities getting filtered out with "zone=floor_bucket overshoot=0.0°C" and "spread too wide" — meaning the bot has extremely restrictive filters that effectively block all trades.

After this fix, the bot should be: (a) not crashing, (b) actively placing paper trades when conditions are met, (c) logged to Telegram/WhatsApp with trade alerts.

## Progress

- [x] (2026-04-12 17:00 MYT) Diagnose PM2 process state, error log, trade log, and live output
- [ ] (Step 1) Read the full scan_and_update() function — find where forecast_src variable is wrong
- [ ] (Step 2) Find the crash location in scan_and_update() — trace the dict that uses forecast_src
- [ ] (Step 3) Check runner.py / two_bucket_backtest.py for the same bug (same codebase, likely same issue)
- [ ] (Step 4) Fix all occurrences
- [ ] (Step 5) Verify no other similar typos exist (grep for forecast_src vs forecast_snap)
- [ ] (Step 6) Investigate no-trade filters — why are all cities being skipped?
- [ ] (Step 7) Restart the bot via PM2, confirm it survives one full scan cycle
- [ ] (Step 8) Confirm trade signals appear in the output log

## Surprises & Discoveries

- PM2 `restarts: 0` despite bot being online for 3h. This means PM2 did NOT auto-recover from the crash. The bot was manually restarted OR a different supervisor is keeping it alive.
- Error log references line 1595 but current code at line 1595 is `pos["closed_at"]` — file was modified after the crash occurred (current: 2265 lines, backup: 90347 bytes vs 97914 bytes current). The crash happened when the file had the old version.
- All SKIP reasons logged are "floor_bucket overshoot=0.0°C" — this means the signal engine is computing a forecast temperature exactly at the floor of a bucket, triggering an overshoot=0 condition which is classified as "not in sweet spot". This may be a legitimate filter or a bug in the signal calculation.
- Bot is "monitoring positions" every ~10 minutes — meaning it completes scan_and_update() without crashing but returns 0 new positions.

## Decision Log

- Decision: Treat the crash as already fixed (file updated Apr 12 08:50) but verify the bot actually exits the monitoring-only loop. The no-trade symptom is the primary issue now.
- Decision: Focus The Algorithm on the no-trade filter. The crash is secondary — if the bot is surviving scans without crashing, the crash fix is validated by observation.
- Decision: Don't ask the user for input — do the root cause analysis first, then restart and observe. User said "fix it" not "explain it."

## Context and Orientation

Key files:
- `/home/alyssa/.openclaw/workspace/alter-bot-v1/bot_v2.py` — main bot (2265 lines, 97KB, modified Apr 12 08:50)
- `/home/alyssa/.openclaw/workspace/alter-bot-v1/bot_v2.py.bak` — pre-fix backup (90347 bytes)
- `/home/alyssa/.openclaw/workspace/alter-bot-v1/runner.py` — may be a wrapper that calls bot_v2
- `/home/alyssa/.openclaw/workspace/alter-bot-v1/two_bucket_backtest.py` — backtest script, may share code
- `/home/alyssa/.openclaw/workspace/alter-bot-v1/config.json` — trading config (16KB, modified Apr 12 08:28)
- `~/.pm2/logs/alter-bot-v2-error.log` — PM2 error log
- `~/.pm2/logs/alter-bot-v2-out.log` — PM2 stdout

The `scan_and_update()` function (around line 1400-1900) is the core trading loop. It:
1. Fetches weather forecasts for all cities
2. Computes a signal (EV, Kelly criterion)
3. Opens or skips trades based on filters
4. Checks stop-loss / trailing stop on open positions
5. Returns (new_pos, closed, resolved) counts

The `monitor_positions()` function is called when scan_and_update() returns 0 new positions — but it should NOT be called if there are valid signals.

## Plan of Work

### Phase 1: Find the exact crash location (Step 1-2)

Read the full scan_and_update() function from bot_v2.py around line 1400-1950. The error says `forecast_src` at line 1595 — but current code has `pos["closed_at"]` there. This means either:
- (A) The crash path has been removed/rewritten
- (B) The crash is in a different code path that wasn't rewritten

Search ALL occurrences of `forecast_src` (not `forecast_snap`) in the current file. There should be 0 — if there are any, fix them. The error log shows `forecast_src` was used at line 1744 in the best_signal dict, but current code shows it correctly as `best_signal["forecast_src"]` there.

### Phase 2: Check runner.py and two_bucket_backtest.py for same bug (Step 3)

grep both files for `forecast_src`. If found, fix in both.

### Phase 3: Investigate no-trade filters (Step 6)

Read the SKIP reason pattern: "zone=floor_bucket overshoot=0.0°C". This means:
- The signal engine is computing a forecast temperature
- The computed temperature falls in the "floor_bucket" zone
- The overshoot is exactly 0.0°C (forecast temp = floor boundary exactly)

This could be:
- Legitimate: markets are genuinely not worth trading right now
- Bug: temperature computation is producing boundary values that get filtered

Find the code that outputs "zone=floor_bucket overshoot=X.X°C" and trace backwards to understand what triggers a trade vs a skip.

### Phase 4: Fix and restart (Step 4-8)

1. Fix all `forecast_src` typos
2. Patch the filter that causes all-skips if it's a bug
3. PM2 restart alter-bot-v2
4. Wait one scan cycle (~5-10 min)
5. Check output log for [BUY] signals

## Concrete Steps

### Step 1: Read the full scan_and_update() function

```bash
sed -n '1380,1950p' /home/alyssa/.openclaw/workspace/alter-bot-v1/bot_v2.py
```

Look for all occurrences of `forecast_src`, `forecast_snap`, `best_signal`, `best_source`. The crash is at the line that builds a dict with `"forecast_src": best_source` — find where that happens.

### Step 2: Grep the current file for exact crash variable

```bash
grep -n "forecast_src\|forecast_snap\|best_source" /home/alyssa/.openclaw/workspace/alter-bot-v1/bot_v2.py
```

If `forecast_src` appears anywhere other than in a string key, fix it.

### Step 3: Check runner.py and two_bucket_backtest.py

```bash
grep -n "forecast_src\|forecast_snap\|best_source" /home/alyssa/.openclaw/workspace/alter-bot-v1/runner.py
grep -n "forecast_src\|forecast_snap\|best_source" /home/alyssa/.openclaw/workspace/alter-bot-v1/two_bucket_backtest.py
```

### Step 4: Find the SKIP reason generator

```bash
grep -n "floor_bucket\|overshoot\|zone=" /home/alyssa/.openclaw/workspace/alter-bot-v1/bot_v2.py | head -30
```

### Step 5: Fix and PM2 restart

```bash
# After fixes:
pm2 restart alter-bot-v2
# Wait 5 minutes, then:
tail -30 ~/.pm2/logs/alter-bot-v2-out.log
```

## Validation and Acceptance

**Before fix**: Bot monitoring positions, 0 new trades, 0 closed, 0 resolved.
**After fix**: Bot outputs `[BUY]` signals OR `[no signal]` with clear reasoning, and at least attempts to trade within 2 scan cycles.
**Crash test**: After PM2 restart, error log should NOT contain new `NameError` entries.

## Idempotence and Recovery

- All edits are to `.py` files tracked by git in the same directory
- Before any edit: `cp bot_v2.py bot_v2.py.pre-fix-$(date +%Y%m%d%H%M%S)`
- Rollback: `pm2 restart alter-bot-v2` with previous backup if needed
