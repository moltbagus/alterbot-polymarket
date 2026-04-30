# Alter-Bot Full Debug & Profitability ExecPlan
**Status: IN PROGRESS | Started: 2026-04-27 23:45 MYT**

## Purpose / Big Picture

Fix every known bug in alter-bot-v1 until it produces profitable or at minimum break-even paper trades. The bot is currently paused at $621.57 (-40.8% drawdown) with 15+ PM2 restarts. We will systematically close each bug, verify the fix, and not stop until the bot is healthy.

---

## Context and Orientation

**Key files:**
- Bot: `/home/alyssa/.openclaw/workspace/alter-bot-v1/bot_v2.py`
- Self-improver: `/home/alyssa/.openclaw/workspace/alter-bot-v1/self_improver.py`
- Config: `/home/alyssa/.openclaw/workspace/alter-bot-v1/config.json`
- State: `/home/alyssa/.openclaw/workspace/alter-bot-v1/data/state.json`
- Checkpoint: `/home/alyssa/.openclaw/workspace/alter-bot-v1/data/.checkpoint`
- City errors: `/home/alyssa/.openclaw/workspace/alter-bot-v1/data/city_error_history.json`
- P0 alerts: `/home/alyssa/.openclaw/workspace/alter-bot-v1/data/p0_alerts.json`
- Fill log: `/home/alyssa/.openclaw/workspace/alter-bot-v1/data/fill_log.json`

**Current known issues (from diagnosis):**
1. Portfolio drawdown 40.8% — checkpoint active, bot paused ✅ (monitor_agent.py checkpoint working)
2. Tokyo/London/Singapore/Paris all <25% win rate over 25+ samples — NOT yet blocked ❌
3. State.json inconsistent: wins(12)+losses(12)=24 ≠ total_trades(7) ❌
4. Shanghai systematic underforecast: -8.7°C bias, current bias only +2.0°C ❌
5. PM2 SIGKILL on p0_router — OOM or timeout when spawning hermes ❌
6. whale_skip_reason tracking — partially fixed, verify end-to-end ⚠️
7. US city unit mismatch — ALREADY FIXED in resolve_market (lines ~2227-2252) ✅
8. Circuit breaker persistence — ALREADY FIXED (state.json circuit_broken list) ✅
9. EV formula — ALREADY CORRECT in code ✅

---

## Verified True State (as of 23:45 MYT Apr 27)

### Already Fixed (Do NOT re-fix)
- US city unit mismatch: resolve_market() at lines ~2227 converts °F→°C for US cities ✅
- whale_skip_reason: best_signal["whale_reason"] set at line 2084, passed to add_error() ✅
- Circuit breaker persistence: state circuit_broken list written to state.json ✅
- Checkpoint: monitor_agent.py now tracks consecutive losses + drawdown and pauses bot ✅

### Still Broken / Needs Fixing
1. **City blocklist** — Tokyo/London/Singapore/Paris at <25% WR need to be in avoid list
2. **State.json reset** — wins/losses counters don't match total_trades; need a paper-reset function
3. **PM2 restarts (18+)** — p0_router SIGKILL when spawning hermes; needs investigation
4. **Shanghai bias** — +2.0°C is far too small; 8.7°C underforecast needs ~+8.0°C bias
5. **Station mismatch** — HK resolves on HKO downtown but forecast uses airport coordinates

---

## Progress

- [x] (2026-04-27 23:45) Deep diagnosis — read all relevant source files
- [ ] (2026-04-27) Fix 1: Add poor-performing cities to avoid list
- [ ] (2026-04-27) Fix 2: Reset state.json counters after paper reset
- [ ] (2026-04-27) Fix 3: Increase Shanghai bias from +2.0 to +8.0
- [ ] (2026-04-27) Fix 4: Investigate and fix PM2 SIGKILL / hermes spawn issue
- [ ] (2026-04-27) Fix 5: Verify whale_skip_reason end-to-end tracking
- [ ] (2026-04-27) Fix 6: Verify US city unit fix on next US city trade
- [ ] (2026-04-27) Verify: Run monitor_agent.py — no checkpoint triggered
- [ ] (2026-04-27) Verify: Paper trade cycle completes without errors

---

## Surprises & Discoveries

- calc_ev() in bot_v2.py IS already correct — HEARTBEAT was wrong to flag it as broken
- forecast_changed early-close is ALREADY disabled in paper_trade mode (line ~1691: `if not _cfg.get("paper_trade", False)"`)
- state.json "wins" and "losses" are NOT the source of truth — market files are (line 2374)
- whale_skip_reason is correctly forwarded through best_signal → pos → add_error()
- resolve_market() already has the US city unit fix applied (lines ~2227-2252)

---

## Decision Log

- Decision: US city unit fix already in resolve_market(), do not re-apply
- Decision: EV formula already correct, do not change
- Decision: forecast_changed early-close already disabled in paper mode
- Decision: Shanghai bias needs largest correction (+2.0 → +8.0) due to 8.7°C systematic cold bias

---

## Plan of Work

### Fix 1: City Blocklist (Poor Performers)
**What:** Add Tokyo, London, Singapore, Paris to config.json `avoid_cities` list.
**Why:** All have <25% win rate over 25+ samples. Each trade is expected value negative.
**File:** `config.json`
**Change:** Add to `avoid_cities` array: `"tokyo", "london", "singapore", "paris"`
**Verification:** After fix, run `python3 bot_v2.py --dry-run` (or check scan output) — these cities should not appear in scan output.

### Fix 2: State.json Paper Reset
**What:** Reset wins/losses/total_trades to sane values after paper reset.
**Why:** Wins=12, losses=12 but total_trades=7 is internally inconsistent. After a paper reset, all counters should reflect the new session.
**File:** `data/state.json`
**Action:** Set `"wins": 0, "losses": 0, "total_trades": 0, "last_reset": "2026-04-27 PAPER RESET (counters cleaned)"`
**Verification:** Read state.json — counters should be 0/0/0.

### Fix 3: Shanghai Bias Correction
**What:** Increase Shanghai bias from +2.0°C to +8.0°C in BIAS_CORRECTION dict and config.json.
**Why:** 8.7°C systematic cold bias means model is forecasting too cold. Need large positive correction.
**File:** `bot_v2.py` (BIAS_CORRECTION dict) + `config.json` (city_biases section)
**Change:** `"shanghai": +8.0` (up from +2.0)
**Also update:** config.json `city_biases.shanghai` from +2.0 to +8.0
**Verification:** After fix, scan Shanghai — bias should show +8.0°C in forecast output.

### Fix 4: PM2 SIGKILL Investigation
**What:** p0_router.py gets SIGKILL when running `python3 p0_router.py` without dry-run.
**Why:** Likely hermes subprocess taking too long or OOM. Need to investigate.
**File:** `p0_router.py` spawn_turing() function
**Action:** 
1. Check if hermes is available: `/home/alyssa/.local/bin/hermes --version`
2. Check if timeout is the issue — currently 300s hard timeout
3. Consider adding memory limit or using `nohup` for hermes spawn
**Verification:** `python3 p0_router.py --dry-run` should complete without SIGKILL.

### Fix 5: Whale Skip Reason Verification
**What:** Verify whale_skip_reason flows from apply_whale_filters → best_signal → pos → add_error() → city_error_history.json.
**Why:** Self-improvement reflection said this was fixed, but need end-to-end verification.
**Action:** 
1. Read bot_v2.py lines ~2080-2086 (whale_reason set in best_signal)
2. Read bot_v2.py lines ~2300-2310 (pos.get("whale_reason") passed to add_error)
3. Check city_error_history.json for any entries with whale_skip_reason != null
**Verification:** Look for whale_skip_reason field in city_error_history.json entries.

### Fix 6: US City Unit Fix Verification
**What:** The fix in resolve_market() at lines ~2227-2252 should be working. Verify by checking if US city errors are now in normal range (not -45°C to -59°C).
**Action:** After next US city (NYC/Miami/Atlanta) trade resolves, check city_error_history.json for that city's avg_error. Should be <5°C for Atlanta (our best city).
**Verification:** When Atlanta next resolves, error should be <5°C (not the previous -45°C garbage).

---

## Concrete Steps

### Fix 1: City Blocklist
```bash
cd ~/.openclaw/workspace/alter-bot-v1
# Read current avoid_cities
python3 -c "import json; cfg=json.load(open('config.json')); print('avoid:', cfg.get('avoid_cities',[])); print('blocked:', cfg.get('blocked_cities',[]))"
```
Then edit config.json to add: `"tokyo", "london", "singapore", "paris"` to avoid_cities.

### Fix 2: State.json Reset
```bash
cd ~/.openclaw/workspace/alter-bot-v1/data
python3 -c "
import json
s=json.load(open('state.json'))
s['wins']=0
s['losses']=0
s['total_trades']=0
s['last_reset']='2026-04-27 PAPER RESET (counters cleaned)'
json.dump(s,open('state.json','w'),indent=2)
print('Reset:',s)
"
```

### Fix 3: Shanghai Bias
```bash
cd ~/.openclaw/workspace/alter-bot-v1
# In bot_v2.py: change BIAS_CORRECTION["shanghai"] from +2.0 to +8.0
# In config.json: change city_biases.shanghai from +2.0 to +8.0
```

### Fix 4: PM2 SIGKILL
```bash
/home/alyssa/.local/bin/hermes --version
# Test hermes spawn manually:
timeout 30 /home/alyssa/.local/bin/hermes chat -q "echo test" --provider minimax 2>&1 | head -5
```

### After all fixes:
```bash
cd ~/.openclaw/workspace/alter-bot-v1
# 1. Run monitor_agent.py to verify checkpoint still ok but no new issues
python3 monitoring/monitor_agent.py

# 2. Clear the checkpoint so bot can resume (after Colbert confirms)
/* Colbert must say YES to resume */

# 3. Run a paper scan
python3 bot_v2.py 2>&1 | head -50
```

---

## Acceptance Criteria

1. ✅ Tokyo, London, Singapore, Paris are in `avoid_cities` in config.json
2. ✅ State.json shows wins=0, losses=0, total_trades=0 after reset
3. ✅ Shanghai bias is +8.0 in both bot_v2.py and config.json
4. ✅ PM2 restarts < 5 in next 24h (bot stable)
5. ✅ whale_skip_reason appears in city_error_history.json when whale skips occur
6. ✅ US city (Atlanta) resolves with error < 5°C (not -45°C garbage)
7. ✅ Bot produces profitable OR break-even trades over 10 resolution cycles
8. ✅ monitor_agent.py returns 0 (all clear) with no checkpoint triggered

---

## Interfaces and Dependencies

- `bot_v2.py`: Main trading bot — Kelly-based weather prediction trading
- `self_improver.py`: CityErrorTracker class — tracks per-city forecast errors
- `config.json`: City tier settings, biases, weights, thresholds
- `monitor_agent.py`: Cron job — checks bot health every 30 min
- `p0_router.py`: Routes P0 issues to Turing (hermes) for auto-fixing
