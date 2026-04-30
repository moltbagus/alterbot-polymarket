# Wire Self-Improver Routing Chain

This ExecPlan closes the loop between whale_skip detection and Turing spawning. After this, when a whale skip fires, the reason gets persisted → p0_alert_detector sees it → p0_router spawns Turing → fix lands.

## Context and Orientation

The alter-bot self-improvement loop has 4 separate systems that were never fully connected:

| File | Role | Status |
|------|------|--------|
| `bot_v2.py` | Trading logic + whale skip | whale_reason NOT persisted |
| `p0_alert_detector.py` | Writes p0_alerts.json | No whale detection logic |
| `p0_router.py` | Reads p0_alerts.json, spawns Turing | Not cron-scheduled; hermes times out at 300s |
| `monitor_agent.py` | Health monitor | Alerts human only, doesn't route to Turing |

Key data files:
- `alter-bot-v1/data/state.json` — circuit breakers, balance, positions
- `alter-bot-v1/data/logs/fill_log.jsonl` — trade history
- `alter-bot-v1/data/city_error_history.json` — per-city win rates
- `alter-bot-v1/data/p0_alerts.json` — P0 alert queue (currently empty [])
- `alter-bot-v1/data/logs/whale_skips.jsonl` — whale skip log (doesn't exist yet)
- `alter-bot-v1/memory/self-improvement/observations/` — daily observation markdown

## Purpose / Big Picture

After this plan, the closed loop works like this:

```
whale skip fires in bot_v2.py
  → whale_reason persisted to whale_skips.jsonl
  → p0_alert_detector reads whale_skips.jsonl, writes to p0_alerts.json
  → p0_router (30-min cron) reads p0_alerts.json
  → spawns Turing with timeout=900s (not 300s)
  → Turing reads fix manifest + executes fix
  → loop closes
```

## Progress

- [ ] (2026-04-29 14:xx MYT) Milestone 1: bot_v2.py — persist whale_reason before early return
- [ ] (2026-04-29 14:xx MYT) Milestone 2: p0_alert_detector.py — add whale skip detection
- [ ] (2026-04-29 14:xx MYT) Milestone 3: p0_router.py — fix 'str' object bug, increase timeout to 900s
- [ ] (2026-04-29 14:xx MYT) Milestone 4: Cron — schedule p0_router every 30 min
- [ ] (2026-04-29 14:xx MYT) Milestone 5: Validate end-to-end

## Milestone 1: Persist whale_reason in bot_v2.py

**File:** `alter-bot-v1/bot_v2.py`

**Problem:** At line ~2120, when whale skip fires, the function returns early BEFORE the position dict is created. whale_reason is printed but never stored.

**Fix:** Before `return new_pos, closed, dirty_markets, balance_delta`, write to `data/logs/whale_skips.jsonl`.

Add near the whale skip block (~line 2120):

```python
if not whale_can_trade:
    whale_entry = {
        "timestamp": datetime.now().isoformat(),
        "city": city_slug,
        "date": date,
        "whale_reason": whale_reason,
        "forecast": forecast_temp,
        "price": best_signal.get("entry_price") if best_signal else None,
        "confidence": confidence,
    }
    whale_log = DATA_DIR / "logs" / "whale_skips.jsonl"
    with open(whale_log, "a") as f:
        f.write(json.dumps(whale_entry) + "\n")
    print(f"  [WHALE SKIP PERSISTED] {loc['name']} {date} - {whale_reason}")
    return new_pos, closed, dirty_markets, balance_delta
```

Also add `json` and `datetime` imports at top if not already present.

**Validation:** After edit, PM2 restart bot, trigger a whale skip (or wait for next occurrence), confirm entry appears in `data/logs/whale_skips.jsonl`.

## Milestone 2: Add whale skip detection to p0_alert_detector.py

**File:** `alter-bot-v1/p0_alert_detector.py`

**Problem:** p0_alert_detector.py has no whale skip check function. p0_alerts.json stays empty.

**Fix:** Add a `check_whale_skip_tracking()` function that reads `whale_skips.jsonl` and writes whale entries to `p0_alerts.json`.

```python
def check_whale_skip_tracking():
    """Check if whale skips are being captured and routed properly."""
    whale_log = DATA_DIR / "logs" / "whale_skips.jsonl"
    if not whale_log.exists():
        return []
    
    alerts = []
    # Read last 7 days of whale skip entries
    try:
        entries = []
        if whale_log.exists():
            with open(whale_log) as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        entries.append(entry)
                    except json.JSONDecodeError:
                        continue
        
        # If we have whale skip entries but no corresponding p0_alert,
        # generate an alert
        for entry in entries[-10:]:  # last 10 entries
            alerts.append({
                "type": "WHALE_SKIP_CAPTURED",
                "city": entry.get("city"),
                "whale_reason": entry.get("whale_reason"),
                "timestamp": entry.get("timestamp"),
                "forecast": entry.get("forecast"),
                "severity": "P2",  # informational - fix manifest exists
            })
    except Exception as e:
        print(f"  [ERROR] check_whale_skip_tracking: {e}")
    
    return alerts
```

Add this to the main detection loop in `detect_all()` alongside the other check functions.

**Validation:** Run `python3 p0_alert_detector.py` and confirm it reads whale_skips.jsonl (or creates empty list if none exist).

## Milestone 3: Fix p0_router.py bugs + increase timeout

**File:** `alter-bot-v1/p0_router.py`

**Problem 1:** `check_circuit_breaker_candidates()` has `'str' object has no attribute 'get'` bug — corrupted city_error_history.json entries crash the check.

**Problem 2:** hermes timeout is 300s but consistently times out. Increase to 900s.

**Problem 3:** WHALE_SKIP_NOT_CAPTURED plugin needs updating to match the new whale skip data source.

**Fix 1 — Guard in check function:**
```python
for city, info in cities_data.items():
    if not isinstance(info, dict):  # ADD THIS GUARD
        continue
    if info.get("win_rate", 1.0) < 0.35 and info.get("n", 0) >= 5:
```

**Fix 2 — Timeout in spawn_turing():**
```python
result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)  # was 300
```

**Fix 3 — Update WHALE_SKIP_NOT_CAPTURED plugin:**
The plugin currently reads p0_alerts.json for whale entries. Update to also check whale_skips.jsonl directly as fallback:

```python
def check_whale_skip_tracking():
    """Check if whale skips are being persisted properly."""
    whale_log = DATA_DIR / "logs" / "whale_skips.jsonl"
    if not whale_log.exists():
        return [alert_template("WHALE_SKIP_NOT_CAPTURED", "No whale skip log exists")]
    
    entries = []
    with open(whale_log) as f:
        for line in f:
            try:
                entries.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                continue
    
    if len(entries) == 0:
        return [alert_template("WHALE_SKIP_NOT_CAPTURED", "Log exists but no entries")]
    
    return []  # whale skips are being captured — no alert needed
```

**Validation:** Run `python3 p0_router.py` in dry-run mode, confirm no errors and all 5 plugins execute without crashing.

## Milestone 4: Schedule p0_router on cron (every 30 min)

**Problem:** p0_router.py is NOT on any cron. The loop dies at the routing step.

**Fix:** Create a cron job that runs p0_router.py every 30 minutes using the OpenClaw cron tool.

Cron job spec:
- Name: `alter-bot-p0-router`
- Schedule: `0,30 * * * *` (every hour at :00 and :30)
- Session target: `isolated`
- Payload: `agentTurn` with message instructing sub-agent to run `python3 p0_router.py` in alter-bot-v1 directory
- Delivery: `announce` to channel telegram, to 392076648

```python
cron(action="add", job={
    "name": "alter-bot-p0-router",
    "schedule": {"kind": "cron", "expr": "0,30 * * * *", "tz": "Asia/Kuala_Lumpur"},
    "sessionTarget": "isolated",
    "payload": {
        "kind": "agentTurn",
        "message": "Run: cd /home/alyssa/.openclaw/workspace/alter-bot-v1 && python3 p0_router.py >> data/logs/p0_router_cron.log 2>&1\nWorking directory: /home/alyssa/.openclaw/workspace/alter-bot-v1\nTimeout: 600s\nON COMPLETION: Send Telegram to 392076648 if p0 alerts were routed.",
    },
    "delivery": {"mode": "announce", "channel": "telegram", "to": "392076648"},
    "enabled": True,
})
```

**Validation:** `cron(action="list")` shows the new job. Trigger a test run immediately to confirm it fires.

## Milestone 5: End-to-End Validation

After all 4 milestones, validate the full chain:

1. Trigger a whale skip (wait for natural occurrence or force one)
2. Check `data/logs/whale_skips.jsonl` has the entry
3. Run `python3 p0_alert_detector.py` — confirm whale entry in p0_alerts.json
4. Run `python3 p0_router.py` — confirm Turing was spawned
5. Confirm p0_router.log shows the routing with 900s timeout

## Surprises & Discoveries

- whale_skip_reason has been "N/A" in ALL 50+ observation entries — zero captures ever, despite the reason being printed to logs. The code path simply returns before the position dict is created.
- p0_router.py and p0_autoroute.py are two independent implementations that were never consolidated or cron-scheduled.
- hermes consistently timing out at 300s suggests the task context is too large, not that the fix is complex. Need to scope the prompt better (read fix manifest + execute, not full audit).

## Decision Log

- Decision: Use p0_router.py (plugin architecture) as the canonical router, deprecate p0_autoroute.py.
  Rationale: Plugin architecture is more extensible for future P0 checks.
  Date: 2026-04-29

- Decision: Increase hermes timeout from 300s to 900s.
  Rationale: 6 consecutive timeouts at 300s. 900s gives breathing room for context loading.
  Date: 2026-04-29

- Decision: Route p0_router via isolated cron session, not heartbeat.
  Rationale: heartbeat is already overloaded. Isolated sessions are designed for autonomous background work.
  Date: 2026-04-29
