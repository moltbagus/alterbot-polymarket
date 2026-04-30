# Fix Manifest: City Circuit Breaker / Poor Performance

## Alert Summary
- **Trigger:** A city accumulates 4+ DATA_ERRORs or has 0% win rate over 20+ resolved markets
- **Source:** `data/city_error_history.json` → `city_error_count`
- **Severity:** P0

## Root Cause

**Root cause:** `circuit_broken` flag is stored in-memory only. When PM2 restarts (or the bot crashes/restarts), the in-memory flag is wiped and the city is re-traded immediately, causing cascading bad bets.

Additionally:
- Config `blocked_cities` list is NOT updated when circuit breaks
- State file `data/state.json` does NOT persist the broken city list
- `city_error_history.json` tracks errors but nothing reads it to block cities

**Affected cities (from error history):**
- Dallas: 0% win rate, multiple DATA_ERRORs — should be blocked
- London: 0% win rate — should be blocked

**Related code path:**
- `bot_v2.py:select_city()` — checks in-memory `circuit_broken` only
- `bot_v2.py:add_error()` — increments error count but doesn't persist to blocked list
- PM2 restart → all in-memory state lost

## Fix Required

### 1. Persist broken cities to state.json
**File:** `bot_v2.py`
**Function:** `add_error()` or circuit breaker logic

```python
# When circuit breaks (4+ errors):
broken_cities = state.get("circuit_broken_cities", [])
if city not in broken_cities:
    broken_cities.append(city)
state["circuit_broken_cities"] = broken_cities
save_state(state)

# Also update config blocked_cities on disk
config = load_config()
if city not in config.get("blocked_cities", []):
    config["blocked_cities"].append(city)
    save_config(config)
```

### 2. Load broken cities on startup
**File:** `bot_v2.py`
**Function:** `__init__()` or `load_state()`

```python
# After loading state.json:
self.circuit_broken_cities = state.get("circuit_broken_cities", [])
# Merge with config blocked_cities
config_blocked = config.get("blocked_cities", [])
self.blocked_cities = list(set(self.circuit_broken_cities + config_blocked))
```

### 3. Add to city_error_history.json on circuit break
**File:** `bot_v2.py`
**Function:** When circuit breaks

```json
{
  "city": "DALLAS",
  "error_count": 4,
  "first_error": "2026-04-20T...",
  "last_error": "2026-04-27T...",
  "circuit_broken": true,
  "broken_at": "2026-04-27T...",
  "reason": "4 consecutive DATA_ERRORs"
}
```

### 4. Add circuit break event to p0_alerts.json
**File:** `bot_v2.py`
**Function:** When circuit breaks

```python
p0_alert = {
    "type": "CITY_CIRCUIT_BREAKER",
    "city": city,
    "error_count": error_count,
    "broken_at": timestamp,
    "requires_turing_fix": True
}
```

## Verify Steps

1. Trigger 4 DATA_ERRORs for a test city in paper trading
2. Kill the PM2 process (`pm2 kill` or crash simulation)
3. Restart the bot
4. Confirm city is NOT re-traded after restart (check logs)
5. Confirm `data/state.json` contains the city in `circuit_broken_cities`
6. Confirm `data/city_error_history.json` has `circuit_broken: true`

## Test Case

```
Setup: Dallas has 3 DATA_ERRORs
Action: Trigger 1 more DATA_ERROR (4th)
Expected: circuit_broken = True, Dallas in state.json circuit_broken_cities
Action: pm2 restart alter-bot-v2
Expected after restart: Dallas NOT traded (blocked from select_city)
Expected: Dallas in config.json blocked_cities list
```
