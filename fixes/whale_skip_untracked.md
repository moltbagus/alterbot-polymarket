# Fix Manifest: Whale Skip Reason Not Tracked

## Alert Summary
- **Trigger:** `whale_skip_reason` printed/logged but NOT stored in position dict, not emitted in observation, not captured for analysis
- **Source:** `data/p0_alerts.json` → `whale_skip_untracked`
- **Severity:** P1

## Root Cause

The whale detection code prints/logs the skip reason but:
1. **Not stored in position dict** — the position record has no `whale_reason` field
2. **Not passed to `add_error()`** — whale skips don't update city error history
3. **Not emitted in `emit_observation()`** — ML/self-improvement can't see whale patterns
4. **Not written to fill_log** — backtesting and analysis missing this data

**Current code (approx):**
```python
# In select_city() or whale check:
if is_whale_trade(city):
    log.warning(f"[WHALE] Skipping {city} — whale detected")
    whale_skip_reason = "whale_detected"  # printed but discarded
    continue  # skip this city
```

**Missing:**
```python
# These should happen:
pos["whale_skip_reason"] = whale_skip_reason  # NOT done
add_error(city, error_type="WHALE_SKIP", reason=whale_skip_reason)  # NOT done
emit_observation(..., whale_reason=whale_skip_reason)  # NOT done
```

**Related code path:**
- `bot_v2.py:select_city()` — whale detection + skip
- `bot_v2.py:add_error()` — error tracking
- `bot_v2.py:emit_observation()` — ML observation emission

## Fix Required

### 1. Store whale_reason in position dict
**File:** `bot_v2.py`
**Function:** When whale skip occurs

```python
# In city selection loop:
if is_whale_trade(city):
    whale_reason = classify_whale_reason(city)  # "large_position", "market_irrational", etc.
    
    # Record for analysis even though we skip
    skipped_record = {
        "city": city,
        "timestamp": timestamp,
        "action": "WHALE_SKIP",
        "whale_reason": whale_reason,
        "forecast": forecast,
        "price": current_price,
    }
    
    # Append to pending observations (for emit_observation)
    self._pending_whale_skips.append(skipped_record)
    
    # Also log to fill_log
    log_whale_skip(skipped_record)
    
    continue
```

### 2. Pass whale reason to add_error()
**File:** `bot_v2.py`
**Function:** When whale skip occurs

```python
# Whale skips are informative — track them
add_error(
    city=city,
    error_type="WHALE_SKIP",
    reason=whale_reason,
    details={"forecast": forecast, "price": current_price}
)
```

### 3. Include whale_reason in emit_observation()
**File:** `bot_v2.py`
**Function:** `emit_observation()`

```python
# Add whale skip to observation
obs = {
    ...
    "whale_skipped": whale_skipped,  # list of whale skip dicts since last emit
    "whale_reasons": [s["whale_reason"] for s in whale_skipped],
}
```

### 4. Add to fill_log
**File:** `bot_v2.py`
**Function:** When whale skip occurs

```python
def log_whale_skip(record):
    """Append whale skip to fill_log for backtesting."""
    log_path = Path(DATA_DIR) / "logs" / "whale_skips.jsonl"
    with open(log_path, "a") as f:
        f.write(json.dumps(record) + "\n")
```

## Verify Steps

1. Trigger whale detection on a city (large bet or market conditions)
2. Confirm `whale_skip_reason` appears in `data/logs/whale_skips.jsonl`
3. Confirm `data/city_error_history.json` has the WHALE_SKIP entry
4. Confirm `emit_observation()` payload includes `whale_reasons` field
5. Confirm self_improver.py can read whale patterns from observations

## Test Case

```
Setup: Large whale position detected on Atlanta
Expected in logs: [WHALE] Skipping Atlanta — whale detected: large_order_book_imbalance
Expected in fill_log: {"city": "ATLANTA", "action": "WHALE_SKIP", "whale_reason": "large_order_book_imbalance", ...}
Expected in city_error_history: WHALE_SKIP entry with reason
Expected in next observation emit: whale_reasons = ["large_order_book_imbalance"]
```
