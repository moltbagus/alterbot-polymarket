# Fix Manifest: US City Unit Mismatch

## Alert Summary
- **Trigger:** US cities (Dallas, Houston, NYC, Chicago, Miami, Atlanta, etc.) returning 20-45°C errors in resolve_market()
- **Source:** `data/p0_alerts.json` → `us_unit_mismatch`
- **Severity:** P0

## Root Cause

**Root cause:** US city actual temperatures arrive in °F, but forecasts are stored in °C. The comparison in `resolve_market()` uses one of two paths:

1. **Path A (new_records path):** Uses `actual_temp_for_record` which IS converted to °C — but the lookup key may use wrong unit
2. **Path B (existing_positions path):** Uses `temp` directly without conversion — °F compared to °C thresholds

This causes:
- Dallas: `actual=50°F` compared as `50°C` → error of ~45°C
- NYC: `actual=32°F` compared as `32°C` → error of ~27°C
- Atlanta: `actual=83°F` compared as `83°C` → error of ~22°C

**Affected cities:** All US cities in the trading system.

**Related code path:**
- `bot_v2.py:resolve_market()` — two branches with inconsistent unit handling
- `bot_v2.py:fetch_weather()` — returns raw API temp (°F for US cities)
- `bot_v2.py:fetch_historical()` — returns °C for US cities (NOAA converted)

## Fix Required

### 1. Audit actual_temp_for_record conversion in resolve_market()
**File:** `bot_v2.py`
**Function:** `resolve_market()`

Verify BOTH branches handle unit conversion consistently:

```python
# Path A (new record / no position):
actual_temp = record.get("actual_temp_for_record")
if actual_temp is not None and city in US_CITIES:
    actual_temp = fahrenheit_to_celsius(actual_temp)  # Ensure conversion

# Path B (existing position):
if pos.get("actual_temp") is not None and city in US_CITIES:
    pos["actual_temp"] = fahrenheit_to_celsius(pos["actual_temp"])

# The key fix: ensure the "actual" value stored in position dict
# AND used in comparison are both in °C for US cities
```

### 2. Add unit tag to position dict
**File:** `bot_v2.py`
**Function:** When creating/updating position dict

```python
pos = {
    ...
    "temp_unit": "F" if city in US_CITIES else "C",
    "actual_temp": fahrenheit_to_celsius(actual_raw),  # Always store °C internally
}
```

### 3. Add unit assertion in resolve_market()
**File:** `bot_v2.py`
**Function:** `resolve_market()`

Add debug assertion at the start:
```python
assert actual_temp > -90 and actual_temp < 70, f"Actual temp {actual_temp} out of range for {city} — unit error?"
```

## Verify Steps

1. Check Dallas forecast: `curl` the market → note forecast °C
2. Run `fetch_weather()` for Dallas → note returned temp in °F
3. Confirm `resolve_market()` converts to °C before comparison
4. Run a test trade on Dallas → verify error < 3°C (not 45°C)
5. Check `data/logs/alter_bot_{date}.log` for `[UNIT_CONVERT]` entries

## Test Case

```
City: Dallas
Forecast high: 26°C (78°F)
Actual: 78°F (25.5°C actual)

Expected: resolve_market() sees actual=25.5°C vs forecast=26°C → error=0.5°C
Expected: NOT actual=78°C vs forecast=26°C → error=52°C
```

## US Cities List (from config.json)
Atlanta, Dallas, Houston, Chicago, Miami, NYC, Philadelphia, Phoenix, San Antonio, San Diego, Los Angeles (verify full list in config)
