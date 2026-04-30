# Fix Manifest: Portfolio Drawdown >30%

## Alert Summary
- **Trigger:** Portfolio drawdown exceeds 30% from peak value
- **Source:** `data/p0_alerts.json` → `portfolio_drawdown`
- **Severity:** P0

## Root Cause

1. **Kelly criterion bypassed by conviction override** — when `conviction > 0.7`, bet size is multiplied by 2x regardless of Kelly sizing, causing oversized bets during drawdown
2. **Stop-loss not working** — `close_position()` is called but `stop_loss_triggered` flag may not be set correctly, and stop-loss price comparison uses raw `price` instead of `actual_temp`
3. **Forecast `changed` closes at loss** — when `forecast_changed=True`, positions are closed even if it means realizing a loss, without checking if the new forecast justifies it

**Related code paths:**
- `bot_v2.py:conviction_bet_size()` — conviction multiplier bypasses Kelly
- `bot_v2.py:close_position()` — stop-loss tracking incomplete
- `bot_v2.py:resolve_market()` — `changed` flag triggers close without P&L check

## Fix Required

### 1. Remove conviction override (HIGH PRIORITY)
**File:** `bot_v2.py`
**Function:** `conviction_bet_size()` or where bet size is computed

Remove or disable the conviction multiplier that bypasses Kelly. During drawdown, aggressive conviction bets accelerate losses.

```python
# BEFORE (problematic):
if conviction > 0.7:
    size *= 2  # DO NOT DO THIS in drawdown

# AFTER:
# Kelly sizing only. No conviction override during drawdown.
```

### 2. Verify stop-loss fires correctly
**File:** `bot_v2.py`
**Function:** `close_position()` / `resolve_market()`

- Ensure `stop_loss_triggered` is set BEFORE calling `close_position()`
- Compare against `actual_temp_for_record` (°C), not raw `temp` (°F for US cities)
- Add logging: `log.info(f"[STOP_LOSS] triggered for {city}: actual={actual}, stop={stop_loss_price})"`

### 3. Fix close-on-forecast-change logic
**File:** `bot_v2.py`
**Function:** `resolve_market()`

Do NOT close a position just because `forecast_changed=True`. Check if the new forecast would have prevented the original bet. If no improvement, keep the position.

```python
# BEFORE (problematic):
if forecast_changed:
    close_position(...)

# AFTER:
if forecast_changed:
    # Only close if new forecast would have prevented entry
    # OR if current position is at a loss and new forecast is worse
    should_close = evaluate_close_decision(pos, new_forecast, actual)
    if should_close:
        close_position(...)
```

## Verify Steps

1. Run paper trading with drawdown > 20%
2. Confirm no 2x conviction bets are placed
3. Confirm stop-loss fires at correct °C threshold
4. Confirm positions aren't closed simply because forecast changed
5. Check `data/logs/alter_bot_{date}.log` for stop-loss events

## Test Case

```
Portfolio peak: $100
Current value: $65 (35% drawdown)
City: Atlanta
Conviction: 0.8 (2x override would fire)

Expected: Bet size from Kelly ONLY, no 2x multiplier
Expected: Stop-loss at configured threshold fires if temp breach occurs
Expected: Forecast change from warm→warm does NOT close position
```
