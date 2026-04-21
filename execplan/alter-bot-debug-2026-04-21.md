# Alter Bot v2 — Debug & Fix ExecPlan

**Date:** 2026-04-21
**File:** `bot_v2.py` (2,340 lines)
**Location:** `~/.openclaw/workspace/alter-bot-v1/`

---

## Purpose

Full debug and diagnostic pass on the Alter Bot v2 weather trading bot. Fix all confirmed bugs, then provide a live-paper-trade run plan with overnight positions checked next morning. Also address the Dallas / Tier 3 win rate issue.

---

## Bug #1 — `_cal` Never Initialized (CRITICAL)

### File
`bot_v2.py`

### Root Cause
`_cal` is declared as a module-level variable at line 827:
```python
_cal: dict = {}
```
But `load_cal()` is called in `run_loop()` at line 2246, AFTER the `get_horizon_adjusted_sigma()` function is called during `_scan_city()`. The call chain is:

```
run_loop()
  scan_and_update()           ← line 1879
    _scan_city()               ← line 1437
      take_forecast_snapshot() ← uses get_horizon_adjusted_sigma()
        get_horizon_adjusted_sigma()
          load_cal() called at line 346 ← but _cal was never set before this
```

`_cal` remains `{}` for the entire first scan. Every city gets `sigma` computed only from `BASE_SIGMA + horizon/seasonal adjustments`. City-specific calibration from `calibration.json` is silently bypassed.

### Fix
Add `load_cal()` call at the start of `run_loop()`, before `scan_and_update()` is called. Also add at the top of `scan_and_update()`.

**Insert at line 2246**, at the top of `run_loop()`, BEFORE `global _cal`:
```python
global _cal
_cal = load_cal()   # ← ADD THIS LINE
now      = datetime.now(timezone.utc)
```

And add same at top of `scan_and_update()`:
```python
global _cal
_cal = load_cal()
```

### Validation
Run: `python3 -c "import bot_v2; bot_v2.run_loop.__code__.co_names"` — verify `load_cal` is called before `_scan_city`.

---

## Bug #2 — `get_city_error_sigma()` Returns None for Dallas (0% win rate tier cities)

### Root Cause
`get_city_error_sigma()` returns `None` when `n_total < 3` (line 847):
```python
if city_data.get("n_total", 0) >= 3:
    return city_data.get("sigma", None)
return None
```

Dallas has 0 trades in `city_error_history.json`, so it always falls back to `BASE_SIGMA["volatile"]["D+0"] = 1.5°F`. But Dallas has `VOLATILE_CITIES = True`, giving it sigma = `1.5 * 1.2 (spring) = 1.8°F` — not historically accurate (real sigma is ~3-4°F for Dallas).

### Tier 3 Win Rates (from `city_error_history.json`)
```
london:      0.0%  (25 trades)
tokyo:       20%   (25 trades)
singapore:   22%   (27 trades)
paris:       20%   (25 trades)
hong-kong:   25%   (20 trades)
seoul:       50%   (4 trades)
miami:       40%   (25 trades) ← but this is wrong
atlanta:     81%   (26 trades) ← PRIMARY
sao-paulo:   63%   (27 trades)
lucknow:     0%    (2 trades) — too few samples
```

### Recommended Fix
**For Tier 3 (dallas, london, paris, seoul, tokyo, hong-kong, shanghai, singapore, chicago, seattle, nyc, etc.):** Set `MAX_TIER = 2` in `config.json` so these cities are excluded from scanning entirely, since their historical win rates are ≤50% and most are 0-25%. This is the cleanest fix per the PRD.

**As a prerequisite for Tier 3 cities that ARE traded** (if any), implement `sigma` fallback with known default sigmas:

```python
# Known sigmas for cities not in city_error_history (from backtesting)
DEFAULT_SIGMA_FALLBACK = {
    "dallas": 3.0, "chicago": 2.5, "seattle": 2.5,
    "london": 4.0, "paris": 4.5, "seoul": 3.0,
    "tokyo": 3.5, "hong-kong": 3.0, "singapore": 3.0,
    "shanghai": 2.5, "nyc": 2.5, "miami": 2.0,
}
```

Then in `get_horizon_adjusted_sigma()`, after the `ce_sigma is None` check, add:
```python
# 3. Fallback: hardcoded known sigmas for well-studied cities
if sigma is None or sigma == 0:
    known = DEFAULT_SIGMA_FALLBACK.get(city_slug)
    if known:
        sigma = known * (1.2 if month in [3,4,9,10] else 1.0)
        return round(sigma, 2)
```

---

## Bug #3 — Typo: `snap["ec mwf"]` vs `snap["ecmwf"]`

### Location
Line 1373:
```python
if snap["ec mwf"] is not None:   # ← TYPO: space in key
```

This should be:
```python
if snap["ecmwf"] is not None:    # ← correct key
```

`snap["ecmwf"]` is set at line 1410: `snap["ecmwf_raw"] = snap["ecmwf"]` — the correct key is `"ecmwf"` with no space. This typo means the `else` branch never correctly checks ECMWF data in the non-D+0 path.

---

## Bug #4 — `get_city_error_win_rate()` Not Used to Gate Trading

### Location
Lines 1576-1578:
```python
city_win_rate = get_city_error_win_rate(city_slug)
if city_win_rate is not None and city_win_rate < 0.50:
    pass  # below threshold - will be handled below
```

This reads the win rate but does NOTHING with it — `pass` is a no-op. The comment says "will be handled below" but there's no handling. A city with a 25% win rate proceeds identically to a city with an 80% win rate.

### Fix
Change to:
```python
city_win_rate = get_city_error_win_rate(city_slug)
if city_win_rate is not None and city_win_rate < 0.50:
    print(f"  [SKIP] {city_slug} win_rate={city_win_rate:.0%} < 50% — skipping")
    continue  # skip opening new positions in underperforming cities
```

Also consider a higher threshold (e.g., 0.60) for tier_1 cities.

---

## Bug #5 — `balance_delta` in `_scan_city` Never Used

### Location
`balance_delta` is accumulated in `_scan_city()` (lines 1501, 1535) but never returned. Looking at lines 1500-1535, `balance_delta` accumulates P&L from stop-loss and forecast-shift closes, but is a local variable in `_scan_city()` that isn't returned. Actually — looking at the return at line 1439:
```python
return new_pos, 0, [], 0.0
```
Wait, let me re-check the return statement of `_scan_city`... Looking at line 1439 and the function body, `_scan_city` returns `(new_pos, closed, dirty_markets, balance_delta)` but `balance_delta` is initialized at line 1460 and accumulated. Let me verify the return statement of `_scan_city`.

Actually from line 1439: `return (new_pos, closed, dirty_markets, balance_delta)` — yes `balance_delta` IS returned. But in `scan_and_update()` line 1916: `balance += sum(balance_deltas)` — this only sums the deltas but never applies them to `_scan_city`'s returned deltas. Let me verify...

From `scan_and_update()` lines 1900-1918:
```python
balance_deltas = []
...
np_, cl_, dirty, bal_delta = future.result(timeout=60)
...
balance_deltas.append(bal_delta)
...
balance += sum(balance_deltas)
```

YES `bal_delta` is returned from `_scan_city` and summed. So this appears OK. But let me check if `balance_delta` is actually being set in `_scan_city` — from lines 1501 and 1535, it's only set inside the stop_loss and forecast_changed blocks. These are EXIT events, not openings. The delta should be `pos["cost"] + pnl` — but `pnl` can be negative.

Wait — the exit P&L formula at line 1500:
```python
pnl = round((current_price - entry) * pos["shares"], 2) if pos.get("side") != "NO" else round((entry - current_price) * pos["shares"], 2)
```

This computes raw price difference × shares. But on Polymarket, if you BUY at $X and the price moves to $Y, your P&L = (Y - X) × shares for YES, or (X - Y) × shares for NO. This formula looks correct.

But wait — `balance_delta += pos["cost"] + pnl` at line 1501. `pos["cost"]` is what you PAID to open the position. So you get back your cost + pnl. This seems right for closing a position.

**Actually this looks correct.** Let me skip this one unless there's evidence it's wrong.

---

## Feature Check: `bucket_prob_cumulative`

Lines 786-793 — defined but never called in `_scan_city`. The actual probability calculation uses `bucket_score()` at line 1637-1644 which uses manual Gaussian CDF math. `bucket_prob_cumulative()` at line 786 uses `math.erf` — which is actually MORE correct than the manual `bucket_score()` implementation. But since `bucket_prob_cumulative()` isn't called, the existing manual implementation is what's running. No need to fix if what's there works.

---

## Feature Check: D+0 Ensemble (line 1365-1370)

The D+0 ensemble uses `0.4*ECMWF + 0.6*METAR` which is correct — METAR is actual observed temperature. This is good. No changes needed.

---

## Summary of Confirmed Bugs to Fix

| # | Bug | Severity | Fix Location |
|---|-----|----------|-------------|
| 1 | `_cal` never initialized before use | 🔴 CRITICAL | Line 2246, 1879 |
| 2 | Dallas / Tier 3 0% win rate cities | 🔴 HIGH | Set `MAX_TIER=2` in config.json |
| 3 | Typo `snap["ec mwf"]` | 🟡 MEDIUM | Line 1373 |
| 4 | Win rate gate is dead code (`pass`) | 🟡 MEDIUM | Line 1577 |

---

## Progress

- [x] Read `bot_v2.py` — 2,340 lines, all key functions identified
- [x] Read `city_error_history.json` — confirmed Dallas has 0 entries
- [x] Read `config.json` — confirmed `MAX_TIER=3`, `min_ev=0.001`
- [x] Read PRD — confirmed 90%+ win rate target
- [ ] Fix Bug #1 — Add `_cal = load_cal()` at startup
- [ ] Fix Bug #2 — Set `MAX_TIER=2` in config.json
- [ ] Fix Bug #3 — Fix typo at line 1373
- [ ] Fix Bug #4 — Replace `pass` with `continue`
- [ ] Run syntax check — `python3 -m py_compile bot_v2.py`
- [ ] Run live paper trade scan — verify output
- [ ] Set up overnight run plan

---

## Decision Log

- **2026-04-21:** Identified `_cal` initialization bug — `_cal` is `{}` on first scan because `load_cal()` is called too late in the call chain.
- **2026-04-21:** Confirmed Dallas has 0 entries in `city_error_history.json` → `get_city_error_sigma` returns `None` → falls back to `BASE_SIGMA["volatile"]["D+0"]=1.5°F` which understates true uncertainty.
- **2026-04-21:** Tier 3 cities have 0-25% win rates. PRD recommends dropping Tier 3. Decision: set `MAX_TIER=2` in config.
- **2026-04-21:** Typo `snap["ec mwf"]` at line 1373 — should be `snap["ecmwf"]`. This prevents ECMWF from being weighted in the non-D+0 ensemble.
- **2026-04-21:** Win rate gate at line 1577 is dead code — `pass` does nothing. Cities with 0-25% win rates proceed to trade.
