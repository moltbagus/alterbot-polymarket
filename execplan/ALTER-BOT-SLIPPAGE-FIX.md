# alter-bot-v2 Debug & Fix ExecPlan

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

Reference: `~/.openclaw/skills/execplan/references/PLANS.md`

## Purpose / Big Picture

Fix alter-bot-v2 which is bleeding money due to: (1) excessive slippage on fills averaging 8.11%, (2) 17 PM2 restarts in 49 minutes suggesting crash loops, (3) Dallas feeding completely broken temperature data (0% WR, 22°C avg error), (4) circuit breaker not persisting across restarts, and (5) an incomplete or unenforced avoid list letting broken cities through.

After this change: PM2 restarts should be 0-2 per session, average slippage should drop below 4%, Dallas should be force-blocked, circuit breaker should survive PM2 restarts, and fill_log should capture proper EV values.

## Progress

- [ ] (2026-04-27 20:20Z) Write this ExecPlan
- [ ] (2026-04-27 20:XXZ) Claude Code: Diagnose root cause of crash loops and high restarts
- [ ] (2026-04-27 20:XXZ) Claude Code: Fix Dallas avoid list enforcement
- [ ] (2026-04-27 20:XXZ) Claude Code: Fix circuit breaker persistence
- [ ] (2026-04-27 20:XXZ) Claude Code: Investigate and reduce slippage
- [ ] (2026-04-27 20:XXZ) Claude Code: Verify all fixes with tests/logs

## Surprises & Discoveries

- Dallas avg_error of 22.22°C suggests the temperature data source is returning Fahrenheit data interpreted as Celsius, or a station is completely wrong
- Circuit breaker shows `[]` in state.json even though it was fixed on Apr 26 — either fix didn't persist or bot is writing stale state
- 17 restarts in 49 min with `pm2 logs` showing "balance: $619.07 | new: 0 | closed: 0 | resolved: 0" suggests bot is not actually crashing but being killed and restarted by something else

## Decision Log

- Decision: Use Claude Code (not hermes) for this task because the ExecPlan skill requires a coding agent that can follow structured plans
- Rationale: hermes-agent times out on complex multi-step debugging tasks; Claude Code has better context window and tool access
- Date/Author: 2026-04-27 / TIGER001

## Context and Orientation

Repository: `/home/alyssa/.openclaw/workspace/alter-bot-v1/`

Key files:
- `bot_v2.py` — main bot logic (signal generation + execution + self-improvement)
- `config.json` — trading configuration (city tiers, bet sizes, conviction thresholds)
- `data/state.json` — persistent state (balance, positions, circuit breaker flags)
- `data/fill_log.json` — log of all fill events with slippage and EV data
- `data/city_error_history.json` — per-city win rate and avg error tracking
- `data/slippage_log.json` — slippage tracking

City tiers from config.json:
- Tier 1: `['atlanta', 'sao-paulo']`
- Tier 2: `['miami', 'dallas']` — Dallas is BROKEN
- Tier 3: `['london', 'paris', 'munich', 'ankara', 'seoul', 'tokyo', 'shanghai', 'singapore', 'lucknow', 'tel-aviv', 'toronto', 'buenos-aires', 'wellington', 'hong-kong']`

Avoid list from config.json: `['sao-paulo', 'dallas', 'london', 'lucknow', 'tokyo', 'paris', 'hong-kong', 'seoul', 'singapore']`

Known broken: Dallas (22°C error), Sao Paulo (DATA_ERROR in circuit breaker, but still tier 1 — contradiction)

## Plan of Work

### Milestone 1: Diagnose Crash Loops (17 restarts)

1. Read `bot_v2.py` to understand the main loop and where crashes occur
2. Check PM2 logs for the actual error that triggers restarts: `pm2 logs alter-bot-v2 --nostream --lines 200`
3. Look for `KeyError`, `TypeError`, `JSONDecodeError` patterns in crash logs
4. Check `data/calibration.json` and the calibration logic for schema mismatches
5. Verify the circuit breaker persistence logic — does `_circuit_broken` survive restarts?

### Milestone 2: Force-Block Dallas

1. Confirm Dallas is in `avoid_cities` in config.json
2. If not, add it
3. Find where avoid list is checked in bot_v2.py — is it enforced before signal generation or only at display?
4. If not enforced, add a hard block: if city in avoid_cities, skip signal entirely

### Milestone 3: Fix Circuit Breaker Persistence

1. Find where `_circuit_broken` is written to state.json in bot_v2.py
2. Confirm it's written on every update, not just in-memory
3. Confirm state.json is reloaded at startup
4. Add a startup check: if `_circuit_broken` exists in state.json, restore it before first scan

### Milestone 4: Investigate and Reduce Slippage

1. Find where order placement happens (Polymarket CLOB API calls)
2. Check order sizing — is the bot using market orders or limit orders?
3. Check if `max_slippage` config is actually enforced at order time
4. Slippage of 8-14% on $2-5 orders suggests market orders on low-liquidity markets
5. Consider: reduce order size, add price guard (don't fill if price moved > X%), or use limit orders

### Milestone 5: Verify Fixes

1. After each fix, run `pm2 restart alter-bot-v2` and monitor for 5 minutes
2. Check `pm2 logs` for crash indicators
3. Confirm `_circuit_broken` survives a restart
4. Confirm Dallas generates no signals
5. Confirm slippage on test fills is < 5%

## Concrete Steps

Run at `/home/alyssa/.openclaw/workspace/alter-bot-v1/`:

```bash
# Step 1: Get full crash logs
pm2 logs alter-bot-v2 --nostream --lines 300 2>&1 | grep -E "(Error|error|CRASH|Exception|Kill)" | tail -50

# Step 2: Read bot_v2.py to find crash points
cat bot_v2.py | head -100

# Step 3: Check circuit breaker and state persistence
grep -n "_circuit_broken\|circuit_broken\|state.json" bot_v2.py | head -30

# Step 4: Check avoid list enforcement
grep -n "avoid\|blocked\|skip" bot_v2.py | head -30

# Step 5: Check slippage handling
grep -n "slippage\|max_slippage\|fill" bot_v2.py | head -30
```

## Validation and Acceptance

- After fixes, PM2 should show 0 restarts over a 30-minute session
- `_circuit_broken` should be a non-empty list after a DATA_ERROR triggers, and should survive `pm2 restart alter-bot-v2`
- Dallas should never appear in fill_log
- Average slippage should be < 5% on new fills
- Bot should report balance, wins, losses without crashing

## Idempotence and Recovery

- Always backup config.json before editing: `cp config.json config.json.bak.$(date +%Y%m%d%H%M%S)`
- If bot crashes completely, `pm2 restart alter-bot-v2` brings it back
- State.json can be reset by deleting `_circuit_broken` key if needed
