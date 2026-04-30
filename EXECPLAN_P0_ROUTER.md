# EXECPLAN: Alter-Bot Auto-Route Closed-Loop System

**Date:** 2026-04-27
**Owner:** TIGER001 → Turing
**Status:** Built

---

## Problem Statement

The Alter-Bot self-improver identifies bugs but has no way to automatically route them to a fixer. The loop is broken:

```
Self-Improver: "Dallas has 0% WR, circuit breaker should fire"
   ↓
   (nothing happens — no routing)
   ↓
   ❌ Same bugs persist across PM2 restarts
```

## Solution Architecture

```
p0_alerts.json + city_error_history.json
         ↓
     p0_router.py (cron agent, every 30 min via heartbeat)
         ↓
    P0_PLUGINS[] (plugin registry — extensible)
         ↓
    check_fn() per plugin → list of alert dicts
         ↓
    Dedup via content hash (.p0_processed.json)
         ↓
    spawn_turing(alert) → hermes chat with fix manifest context
         ↓
    Turing fixes bot_v2.py
         ↓
    Next run verifies fix applied
```

---

## Components

### 1. `p0_router.py` — The Cron Agent

**Purpose:** Poll data sources, deduplicate, route to Turing.

**Key features:**
- **Plugin architecture** — each P0 type is a dict in `P0_PLUGINS[]`
- **Dedup** — content hash in `.p0_processed.json`, 200-entry rolling window
- **Spawn Turing** — writes full context to `data/logs/p0_task_{timestamp}.txt`, calls hermes
- **Index generation** — `fixes/INDEX.md` lists all active P0s + plugin registry
- **Logging** — `data/logs/p0_router.log` with full trace

**Adding a new P0 type:**
```python
# 1. Write fixes/<name>.md (the fix manifest)
# 2. Add check_fn to P0_PLUGINS:
{
    "id": "NEW_P0_TYPE",
    "name": "Human readable name",
    "severity": "P0",
    "check_fn": check_new_p0_type,
    "manifest": "new_p0_type.md",
    "enabled": True,  # or False to disable without removing
},
# 3. Add the check function (returns list of alert dicts)
# No other code changes required.
```

**Execution:** `python3 p0_router.py` — runs one cycle, callable by heartbeat cron.

---

### 2. `fixes/` — Fix Manifests

Each manifest is **self-contained markdown** with:
- Alert summary + severity
- Root cause analysis
- Exact file:function references + code changes
- Verify steps
- Test case

**Files:**

| File | Severity | Root Cause |
|------|----------|------------|
| `portfolio_drawdown.md` | P0 | Kelly bypassed, stop-loss broken, forecast_changed closes at loss |
| `us_unit_fix.md` | P0 | US cities °F actual vs °C forecast causing 20-45°C errors |
| `city_circuit_breaker.md` | P0 | circuit_broken in-memory only, PM2 wipes it |
| `ev_formula_fix.md` | P1 | `calc_ev` uses `p - price` instead of Kelly formula |
| `whale_skip_untracked.md` | P1 | whale_reason printed but not stored/emitted |

**Index:** `fixes/INDEX.md` auto-generated on each run.

---

### 3. Dedup Mechanism

**File:** `data/.p0_processed.json`

```json
[
  {
    "hash": "a3f2b8c1d4e5...",
    "alert": { "type": "CITY_CIRCUIT_BROKEN", "city": "DALLAS", ... },
    "processed_at": "2026-04-27T15:00:00Z"
  }
]
```

- Hash = SHA256 of canonical JSON (sorted keys)
- Rolling 200-entry window (oldest evicted)
- Same alert content = never routed twice

---

## Data Sources

| File | Purpose | Format |
|------|---------|--------|
| `data/p0_alerts.json` | Portfolio-level P0 alerts | JSON array |
| `data/city_error_history.json` | Per-city error tracking | JSON dict, city → stats |
| `data/state.json` | Bot state (broken cities, balance) | JSON dict |
| `data/.p0_processed.json` | Dedup hash log | JSON array |
| `data/logs/p0_router.log` | Router execution log | Text log |
| `data/logs/p0_task_*.txt` | Turing task context files | Text |

---

## Cron Integration

**Heartbeat cron ID:** `09c92199` (Alter-Bot Monitor — every 30 min)

Add to heartbeat:
```python
# In Alter-Bot heartbeat check:
import subprocess
result = subprocess.run(
    ["python3", f"{BOT_DIR}/p0_router.py"],
    capture_output=True, text=True, timeout=120
)
if "No new P0 alerts" not in result.stdout:
    # Alert via Telegram: P0 routed to Turing
    send_telegram_alert(f"🚨 P0 routed: {result.stdout}")
```

---

## Turing Spawn Details

**Command:** `/home/alyssa/.local/bin/hermes chat -q "Fix this P0 alert. Read {task_file} for full context." --provider minimax --yolo`

**Context file contains:**
- Alert metadata (plugin ID, severity, timestamp, city)
- Full alert dump (JSON)
- Fix manifest content (markdown)
- Bot file paths
- Your task instructions

**Timeout:** 300s per alert

---

## Known Limitations

1. **PM2 restart races** — router and bot both read/write state.json; add file locking if needed
2. **Concurrent Turing spawns** — multiple P0s in same cycle spawn multiple hermes sessions; confirm acceptable
3. **Fix verification** — router verifies no new alerts appear, not that fix is correct; manual review needed for P1s
4. **Hermes --yolo** — bypasses permission model; ensure context files are clean (no secrets)

---

## Verify After Fix

1. Run `python3 p0_router.py` — should say "No new P0 alerts"
2. Check `data/logs/p0_router.log` for confirmation
3. Paper trade 1 cycle — confirm bug behavior gone
4. Check `data/state.json` circuit_broken_cities updated correctly
