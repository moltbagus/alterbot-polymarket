# Alter-Bot Proactive Monitoring System

This ExecPlan establishes always-on proactive monitoring for the alter-bot trading system. The goal: detect anomalies, track performance, and alert BEFORE problems compound — not after.

## Purpose / Big Picture

Colbert wants a "super proactive agentic system" for his alter-bot. This means:
- Bot health checked automatically every 30 minutes
- Performance anomalies detected and flagged immediately
- Known bugs (US city unit mismatch) tracked and warned about
- No manual intervention required — autonomous alerting

After this plan: a persistent monitoring session runs every 30 minutes, ingesting bot state + logs, and sends Telegram summaries. Alerts fire automatically on degradation.

---

## Progress

- [x] (2026-04-27 07:30 MYT) ExecPlan written
- [ ] Create monitoring prompt for the 30-min cron agent
- [ ] Set up the cron job (30-min interval, isolated session)
- [ ] Validate: confirm first run fires and delivers report
- [ ] Document the system in MEMORY.md

---

## Surprises & Discoveries

- Bot is running at $592.12 paper balance (started $1000, down ~41%)
- PM2 reports 15 restarts — bot crashing repeatedly
- US city bucket unit mismatch confirmed UNFIXED (°F buckets vs °C forecasts)
- 4+ separate bot instances detected (balance fragmentation)
- Self-Improver daily reflection timing out (timeout 600s→900s, still failing)

---

## Decision Log

- Decision: Use a persistent isolated session for the monitor (not one-shot cron jobs)
  Rationale: Allows the monitor to build context over time, compare with previous runs, and make smarter triage decisions
  Date: 2026-04-27

- Decision: Monitor every 30 minutes during active hours (7AM MYT - 11PM MYT)
  Rationale: Bot trades based on weather markets — overnight hours have low activity but still worth watching
  Date: 2026-04-27

---

## Context and Orientation

**Bot location:** `/home/alyssa/.openclaw/workspace/alter-bot-v1/`
**PM2 process:** `alter-bot-v2` (PID 1043990, uptime 46min, 15 restarts)
**State file:** `data/state.json` — balance, wins/losses, circuit breakers
**Fill log:** `data/fill_log.json` — all order fill records
**PM2 logs:** `~/.pm2/logs/alter-bot-v2-out-0.log` (current)
**Dashboard script:** `scripts/alterbot_dashboard.py` (already exists)

**Key files to read for monitoring:**
- `alter-bot-v1/bot_v2.py` — main trading logic
- `alter-bot-v1/config.json` — city tiers, avoid list, conviction thresholds
- `alter-bot-v1/data/state.json` — current balance and positions
- `alter-bot-v1/data/fill_log.json` — recent fills (last 10)

---

## Known Issues to Monitor

1. **US City Unit Mismatch (P0 — UNFIXED)**
   - US city buckets from Polymarket are in °F but forecast/actual stored in °C
   - Error calculations are garbage for: nyc, miami, atlanta, chicago, seattle, dallas, houston
   - These cities show impossible errors (-45°C to -59°C)
   - **Monitor action:** If these cities appear in scan results, flag as "⚠️ US CITY UNIT MISMATCH — avoid"

2. **Balance Fragmentation (P0 — NEW)**
   - At least 4 separate bot instances running with different balances: $992.5, $653.29, $997.5, $603.79
   - PM2 only shows one process (PID 1043990)
   - Likely cause: PM2 forked multiple processes, or state.json is shared but instances are not
   - **Monitor action:** Check for multiple state.json files or PM2 process count mismatch

3. **PM2 Restarts (P1)**
   - 15 restarts in < 1 hour = unstable
   - **Monitor action:** If restarts > 10, alert "🚨 BOT UNSTABLE — PM2 restarts exceeded 10"

4. **All Recent Trades LOSS (P1)**
   - 6 trades Apr 27: all LOSS
   - Atlanta (normally 83% WR) showing model warm bias in summer transition
   - **Monitor action:** If win rate < 40% over last 10 trades, flag degradation

5. **Circuit Breaker Persistence (FIXED)**
   - Circuit breaker was in-memory only, reset on PM2 restart
   - Apr 26 fix: persistence to state.json + reload at startup
   - **Monitor action:** Verify circuit_broken list survives PM2 restart

6. **Self-Improver Reflection Timeout (P2)**
   - Daily reflection job timing out despite timeout increase to 900s
   - **Monitor action:** Log job state, alert if consecutive errors > 2

---

## Plan of Work

### Step 1: Create the Monitoring Prompt

Write a detailed monitoring prompt that will be used by the cron-triggered agent. This prompt must:
- Check bot health (PID + log freshness)
- Parse state.json for balance, wins/losses
- Parse fill_log.json for recent performance
- Check PM2 restart count
- Scan for known issue signatures
- Compose a concise Telegram report
- Decide: alert or silent OK

### Step 2: Set Up Cron Job

Create a cron job running every 30 minutes (7AM MYT - 11PM MYT):
- Session target: isolated
- Payload: agentTurn with the monitoring prompt
- Delivery: announce to Telegram 392076648
- Timeout: 300 seconds

### Step 3: Validate

Trigger the job manually, confirm it fires, check Telegram delivery.

### Step 4: Document in MEMORY.md

Update MEMORY.md with the new monitoring system.

---

## Concrete Steps

### Step 1: Write the monitoring prompt to a file

Create: `~/.openclaw/workspace/alter-bot-v1/monitoring/prompt_agent.md`

This file contains the system prompt for the monitoring agent. The agent should:
1. Read bot state: `~/.openclaw/workspace/alter-bot-v1/data/state.json`
2. Read recent fills: `~/.openclaw/workspace/alter-bot-v1/data/fill_log.json`
3. Check PM2 status: `pm2 status alter-bot-v2`
4. Check PM2 logs for errors/restarts: `pm2 logs alter-bot-v2 --lines 50 --nostream`
5. Check circuit breaker state in state.json
6. Analyze for the 6 known issues above
7. Compose a Telegram message (max 500 chars):
   - Balance + session P&L
   - Win rate last 10 trades
   - Any active issues
   - Decision: "✅ OK" or "⚠️ ISSUE + recommended action"
8. If issues found: send to Telegram
9. If all clear: respond with just "HEARTBEAT_OK" (no Telegram noise)

### Step 2: Create the cron job

```python
# Cron schedule: every 30 min, 7AM-11PM MYT
# 7AM = 23:00 UTC previous day, 11PM = 15:00 UTC
# cron expr: "0,30 23,0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15 * * *"
# Simplified: "*/30 0-23 * * *" (run every 30 min, every hour)
```

The cron job payload should read the prompt from the file and execute it.

### Step 3: Manual trigger test

```bash
# Trigger immediately to test
openclaw cron run <job_id>
```

### Step 4: Observe

Check Telegram for the report. Confirm it arrives within 60 seconds of triggering.

---

## Validation and Acceptance

**Acceptance criteria:**
1. Monitoring cron job created and enabled
2. Manual trigger produces a Telegram message within 60 seconds
3. Report contains: balance, win rate, issue count
4. Silent OK produces no Telegram message
5. US city unit mismatch is detected and flagged if active
6. PM2 restart count > 10 triggers alert

---

## Idempotence and Recovery

- If cron job fails: the next run will attempt again (no manual reset needed)
- If Telegram delivery fails: cron job delivery has `bestEffort: true` — won't block
- If monitoring produces false positives: refine the alert thresholds in the prompt
- If bot is dead (PID gone): watchdog script (separate cron) handles this and alerts

---

## Artifacts and Notes

**Existing monitoring infrastructure to leverage:**
- `alterbot_dashboard.py` — already parses logs and generates reports (reuse logic)
- `alter_bot_watchdog.sh` — checks for dead PID (keep separate, this is for alive-but-degraded bots)
- `data/state.json` — primary state source
- `data/fill_log.json` — fill performance data

**Session target decision:** `isolated` — each monitoring run is independent, no cross-run contamination. The monitor doesn't need to maintain state between runs — each run reads fresh data from disk.
