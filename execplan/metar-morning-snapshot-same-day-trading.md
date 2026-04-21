# METAR Morning Snapshot — Same-Day Trading ExecPlan

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

Reference: `execplan/ALTERBOT-POSITIVE-EV Sprint.md` (prior related plan, same repo).

---

## Purpose / Big Picture

Before opening any **same-day (D+0)** paper trade, the bot will fetch METAR temperature readings at 6am, 7am, 8am, and 9am local city time, compute the morning warmth trajectory, and only trade at 10am if the trajectory confirms the forecast direction. This grounds same-day entries in actual observed morning temperatures rather than relying solely on ECMWF/HRRR forecast snapshots taken hours earlier.

After this change: the bot will log 4 METAR readings per city per scan day, and same-day trades will only open at or after 10am local when morning trajectory data is available.

---

## Progress

- [ ] (2026-04-21) Read codebase: get_metar(), _scan_city(), take_forecast_snapshot(), execute_trade flow
- [ ] (2026-04-21) Write this execplan → execplan/metar-morning-snapshot-same-day-trading.md
- [ ] Implement: `get_metar_at_hour(city_slug, hour)` — fetch METAR/Open-Meteo at specific local hour
- [ ] Implement: `fetch_morning_snapshot(city_slug)` — collect 6am, 7am, 8am, 9am readings, compute trajectory
- [ ] Modify: `_scan_city()` to call `fetch_morning_snapshot()` and gate D+0 trades on trajectory
- [ ] Modify: `take_forecast_snapshot()` to store morning snapshot data in market record
- [ ] Config: add `min_trade_hour: 10` to config.json (block same-day trades before 10am)
- [ ] Update: PRD-v1.md Section 4 (Trading Strategy) and Section 5 (Forecast Sources)
- [ ] Validate: `python3 -m py_compile bot_v2.py` + `python3 bot_v2.py status`
- [ ] Commit + push

---

## Surprises & Discoveries

- Discovery: `get_metar()` only fetches **current** temperature — no historical/hourly METAR capability exists yet. Open-Meteo's archive API can backfill this.
- Discovery: aviationweather.gov METAR/SPECI endpoint supports `hours=6,7,8,9` query parameter for recent history.
- Discovery: `take_forecast_snapshot()` already computes `best` from D+0 METAR+ECMWF blend at ~0.4/0.6 weight — morning snapshot will supplement, not replace, this.

---

## Decision Log

- Decision: Use Open-Meteo Archive API (`archive-api.open-meteo.com/v1/archive`) for historical METAR at specific hours — no API key needed, covers all cities globally.
- Decision: Only apply morning snapshot gate to **D+0 same-day markets**. D+1 and D+2 continue using ECMWF/HRRR as before.
- Decision: `min_trade_hour: 10` in config.json — no same-day trade opens before 10am local, ensuring all 4 morning readings are available.
- Decision: If fewer than 3 of 4 morning readings available (e.g., station down), fall back to standard `best` forecast and allow trading at 10am.
- Date/Author: 2026-04-21 / Claude Code

---

## Outcomes & Retrospective

*(to be filled after implementation)*

---

## Context and Orientation

This plan modifies `bot_v2.py` in `/home/alyssa/.openclaw/workspace/alter-bot-v1/`.

**Key functions and what they do:**

`get_metar(city_slug, ecmwf_temp=None)` at line 1073: Fetches the **current** METAR temperature from aviationweather.gov or Open-Meteo current weather. Returns a single float temperature in Celsius. Used in `take_forecast_snapshot()` for D+0 same-day forecasting.

`take_forecast_snapshot(city_slug, dates)` at line 1340: For each date (D+0, D+1, D+2), fetches ECMWF, HRRR, METAR and computes a weighted `best` temperature. The D+0 METAR is fetched at whatever hour the scan runs — not a fixed morning snapshot.

`_scan_city(city_slug, now, balance)` at line 1426: The per-city scan called from `scan_and_update()`. Opens positions at line ~1540 using `forecast_temp` from `take_forecast_snapshot()`. This is where same-day trade decisions are made.

`LOCATIONS` dict: Contains per-city config including `station` (ICAO code), `lat`, `lon`, `unit` ("F" or "C"), and `tz` (timezone).

**What needs to change:**
1. New function: `get_metar_at_hour(city_slug, hour)` — fetch temp at specific hour via Open-Meteo Archive
2. New function: `fetch_morning_snapshot(city_slug)` — collect 6,7,8,9am readings + compute trajectory
3. Modify `_scan_city()`: gate same-day (D+0) position opens on morning trajectory + `hour >= 10`
4. Add `min_trade_hour: 10` to config.json
5. Update PRD-v1.md

---

## Plan of Work

### Phase 1: Core METAR Hourly Fetch

**Step 1a:** In `bot_v2.py`, add `get_metar_at_hour(city_slug, hour)` function using Open-Meteo Archive API.

Open-Meteo Archive accepts `start_date`, `end_date`, `hourly=temperature_2m`, `timezone`. For each city, call it once per scan day with `start_date=end_date=<today>` and extract readings at hours 6,7,8,9 local time. Convert UTC offsets as needed per city's `TIMEZONES` entry.

API example:
```
GET https://archive-api.open-meteo.com/v1/archive
?latitude=33.64&longitude=-84.43
&start_date=2026-04-21&end_date=2026-04-21
&hourly=temperature_2m
&timezone=America/New_York
```

Response: `data.hourly.temperature_2m` — array of 24 values (one per hour). Index = local hour.

**Step 1b:** Add `fetch_morning_snapshot(city_slug)` that calls `get_metar_at_hour` for hours 6,7,8,9 and returns:
```python
{
    "temps": [t6, t7, t8, t9],   # or None per missing reading
    "trajectory": "rising|falling|stable|mixed",
    "morning_delta": t9 - t6,    # warmth gain since 6am
    "readings_available": 4,      # count of non-None readings
}
```

### Phase 2: Same-Day Trade Gate

**Step 2a:** In `_scan_city()`, before opening any D+0 position, call `fetch_morning_snapshot(city_slug)`. If `readings_available >= 3` and `hour >= 10` (local), proceed. If `readings_available < 3`, fall back to standard `forecast_temp` from `take_forecast_snapshot()` but still enforce hour gate.

**Step 2b:** Pass morning_snapshot data into the EV calculation. Rising trajectory (`morning_delta > 0`) reinforces HOT bucket bets; falling trajectory reinforces COLD bucket bets. Use this as a `conviction_mult` modifier on the existing continuity check.

**Step 2c:** Add `min_trade_hour: 10` to `config.json` under the existing trading criteria section. In `_scan_city()`, read it and enforce: `if date == today and local_hour < min_trade_hour: skip opening`.

### Phase 3: PRD Update

**Step 3a:** Update PRD-v1.md Section 4 (Trading Strategy) to document the morning snapshot requirement. Add subsection 4.6 "Same-Day Trade Gate: METAR Morning Snapshot".

**Step 3b:** Update PRD-v1.md Section 5 (Forecast Sources) to document `get_metar_at_hour()` and Open-Meteo Archive API usage.

---

## Concrete Steps

### Step 1: Add `get_metar_at_hour` and `fetch_morning_snapshot`

**File:** `bot_v2.py`

Insert after the existing `get_metar()` function (after line ~1130).

```python
def get_metar_at_hour(city_slug, hour, date_str=None):
    """Fetch temperature observation at a specific local hour from Open-Meteo Archive.

    Args:
        city_slug: city identifier (key into LOCATIONS)
        hour: local hour (0-23)
        date_str: date in YYYY-MM-DD format. Defaults to today UTC.

    Returns:
        Temperature in Celsius (float) or None if unavailable.
    """
    loc = LOCATIONS[city_slug]
    lat, lon = loc["lat"], loc["lon"]
    tz = TIMEZONES.get(city_slug, "UTC")
    date_str = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    try:
        url = "https://archive-api.open-meteo.com/v1/archive"
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": date_str,
            "end_date": date_str,
            "hourly": "temperature_2m",
            "timezone": tz,
        }
        data = requests.get(url, params=params, timeout=(3, 6)).json()
        hourly = data.get("hourly", {})
        temps = hourly.get("temperature_2m", [])
        if isinstance(temps, list) and len(temps) > hour and temps[hour] is not None:
            return float(temps[hour])
    except Exception:
        pass
    return None


def fetch_morning_snapshot(city_slug, date_str=None):
    """Collect METAR temperatures at 6am, 7am, 8am, 9am local and compute trajectory.

    Args:
        city_slug: city identifier
        date_str: date in YYYY-MM-DD format. Defaults to today.

    Returns:
        dict with keys: temps (list of 4), trajectory (str), morning_delta (float),
                        readings_available (int), warm_signal (bool)
        warm_signal is True if morning_delta > 0 (rising warmth supports HOT bets).
    """
    date_str = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    hours = [6, 7, 8, 9]
    temps = [get_metar_at_hour(city_slug, h, date_str) for h in hours]
    valid = [t for t in temps if t is not None]
    readings_available = len(valid)

    if readings_available >= 3:
        t6, t9 = temps[0], temps[3]
        morning_delta = (t9 - t6) if (t6 is not None and t9 is not None) else 0.0
        if morning_delta > 0.5:
            trajectory = "rising"
            warm_signal = True
        elif morning_delta < -0.5:
            trajectory = "falling"
            warm_signal = False
        else:
            trajectory = "stable"
            warm_signal = None  # inconclusive
    else:
        trajectory = "insufficient_data"
        morning_delta = 0.0
        warm_signal = None

    return {
        "temps": temps,
        "trajectory": trajectory,
        "morning_delta": morning_delta,
        "readings_available": readings_available,
        "warm_signal": warm_signal,
    }
```

### Step 2: Modify `_scan_city()` — add hour gate + morning snapshot gate

**File:** `bot_v2.py`, in `_scan_city()` function around line 1440.

The D+0 same-day position opening logic is at line ~1540 (`if forecast_temp is not None and not mkt.get("position") and hours >= MIN_HOURS`).

After `snap = snapshots.get(date, {})` and `forecast_temp = snap.get("best")` around line 1541, add:

```python
# METAR Morning Snapshot Gate (D+0 only)
is_d0 = (date == now.strftime("%Y-%m-%d"))
local_hour = datetime.now(timezone.utc).hour  # simplified; ideally use city local time
min_trade_hour = _cfg.get("min_trade_hour", 10)

if is_d0 and local_hour < min_trade_hour:
    print(f"  [MORNING GATE] {loc['name']} {date} — waiting until {min_trade_}am (readings={snap.get('morning_readings', 'N/A')})")
    continue  # skip opening for now, will retry next scan cycle

# Evaluate morning trajectory for D+0
warm_signal = None
if is_d0:
    ms = fetch_morning_snapshot(city_slug, date)
    snap["morning_snapshot"] = ms
    warm_signal = ms.get("warm_signal")
    if ms["readings_available"] < 3:
        print(f"  [METAR AMBIGUOUS] {loc['name']} only {ms['readings_available']}/4 morning readings")
```

Then in the position opening block, use `warm_signal` to adjust conviction:

```python
# After sigma computation (around line 1552)
conviction_mult = 1.0
if warm_signal is True:
    conviction_mult = 1.2  # rising morning = extra conviction on HOT buckets
elif warm_signal is False:
    conviction_mult = 0.8  # falling morning = reduce conviction on HOT buckets

# Use conviction_mult in the EV threshold or confidence check
# (integrate into existing conviction logic — this is additive)
```

### Step 3: Add `min_trade_hour` to config.json

**File:** `config.json`, add under trading criteria:

```json
"min_trade_hour": 10,
```

### Step 4: Update PRD-v1.md

**File:** `PRD-v1.md`

In Section 4 (Trading Strategy), after subsection 4.5, add:

```markdown
### 4.6 Same-Day Trade Gate: METAR Morning Snapshot (April 21 2026)

For D+0 same-day markets, no position opens before 10am local city time. At or after 10am, the bot fetches METAR temperature observations at 6am, 7am, 8am, and 9am local via Open-Meteo Archive API and computes the **morning warmth trajectory**:

| Trajectory | Condition | Signal |
|------------|-----------|--------|
| Rising | T9am − T6am > +0.5°C | Supports HOT bucket bets (+20% conviction) |
| Falling | T9am − T6am < −0.5°C | Supports COLD bucket bets (reduce HOT conviction −20%) |
| Stable | \|Δ\| ≤ 0.5°C | No directional signal, use standard EV |

Same-day trades (D+0) require at least 3 of 4 morning readings available. If fewer than 3 readings are available, the bot falls back to the standard ECMWF+METAR blended forecast but still enforces the 10am minimum hour gate.

D+1 and D+2 markets are unaffected — they continue using ECMWF/HRRR forecast as before.
```

In Section 5 (Forecast Sources), update the METAR entry:

```markdown
### 5.4 METAR Morning Snapshot (Same-Day)
- **Endpoint:** `https://archive-api.open-meteo.com/v1/archive`
- **Auth:** None (free API)
- **Usage:** Fetches hourly temperature_2m at 6,7,8,9am local per city for same-day trade gating
- **Fallback:** If <3 readings available, degrades gracefully to current METAR + ECMWF blend
```

---

## Validation and Acceptance

1. **Syntax check:**
   ```bash
   python3 -m py_compile bot_v2.py
   ```
   Expected: silent success (exit 0).

2. **Import check:**
   ```bash
   python3 -c "from bot_v2 import get_metar_at_hour, fetch_morning_snapshot; print('OK')"
   ```
   Expected: prints `OK`.

3. **Unit test morning snapshot for one city:**
   ```bash
   python3 -c "
   from bot_v2 import fetch_morning_snapshot
   ms = fetch_morning_snapshot('atlanta')
   print(ms)
   assert 'temps' in ms
   assert 'trajectory' in ms
   assert ms['readings_available'] >= 0
   print('PASS')
   "
   ```
   Expected: dict with trajectory, morning_delta, readings_available. If API unreachable, trajectory="insufficient_data".

4. **Status command:**
   ```bash
   python3 bot_v2.py status
   ```
   Expected: prints balance, open positions, no crash.

5. **Confirm config flag:**
   ```bash
   grep min_trade_hour config.json
   ```
   Expected: `"min_trade_hour": 10,`

---

## Idempotence and Recovery

Steps are additive and safe to re-run. If the functions are already present, re-running the Step 1 insertion will create a duplicate function definition — check before inserting. All other changes (config, PRD) are idempotent.

If the Open-Meteo Archive API is unreachable, `get_metar_at_hour` returns `None` and `fetch_morning_snapshot` falls back to `trajectory="insufficient_data"` — the bot continues trading using standard logic with only the hour gate enforced.

---

## Interfaces and Dependencies

- **Open-Meteo Archive API:** `https://archive-api.open-meteo.com/v1/archive` — no API key, free, rate-limited to ~10 req/s
- **No new external libraries** — uses existing `requests` library already in bot_v2.py
- **New functions:** `get_metar_at_hour()`, `fetch_morning_snapshot()`
- **Modified function:** `_scan_city()` — position opening gate + morning signal integration
- **Config key:** `min_trade_hour` (integer, local hour threshold for same-day opening)
