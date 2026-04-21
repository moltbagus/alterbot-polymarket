# Alter Bot v2 — Product Requirements Document (PRD)

**Version:** 1.0
**Date:** 2026-04-20
**Status:** Active Development
**Owner:** Colbert Low / TIGER001

---

## 1. Concept & Vision

Alter Bot is an autonomous weather-forecasting trading agent that exploits mispriced Polymarket markets. It ingests temperature forecasts from multiple sources (ECMWF, HRRR, GFS, METAR, Open-Meteo), compares them against Polymarket bucket pricing, and executes trades when the implied probability diverges from the forecast probability — targeting positive EV entries with Kelly criterion position sizing.

The core thesis: Polymarket buckets are often mispriced relative to meteorological consensus because most traders bet on narrative rather than raw forecast data. Alter Bot fills that gap.

Paper trading as of 2026-04-19 (balance: $1,000). Production-ready architecture, live execution pending validation.

---

## 2. Product Overview

### What It Does

1. **Scans** Polymarket for active temperature markets across 20+ global cities
2. **Fetches** multi-source weather forecasts (Open-Meteo primary, NOAA/NOAA-RAP fallback)
3. **Compares** forecast distribution against Polymarket bucket pricing
4. **Calculates** Expected Value (EV) for each outcome (YES/NO)
5. **Triggers** paper trades via Polymarket CLOB API when EV > threshold with sufficient confidence
6. **Tracks** all resolved trades and feeds results into a self-improvement system
7. **Self-calibrates** city-specific error models (sigma, bias) from resolved outcomes

### How It Works (High-Level Flow)

```
Market Scan → City Filter (tier/avoid list) → Forecast Fetch → Bucket Selection →
EV Calculation → Conviction Filter → Position Sizing (Kelly) → Trade Execution →
Resolution Tracking → Self-Improvement Update
```

---

## 3. Core Components

### 3.1 bot_v2.py (Main Trading Engine)
- **Lines:** ~2,400
- **Responsibility:** Market scanning, forecast ingestion, EV calculation, trade execution, PM2 lifecycle
- **Key imports:** `fill_tracker`, `self_improver.CityErrorTracker`, `tradingagents_integration.WeatherTradingAgents`
- **Runtime:** Managed by PM2, restart-on-failure with `--no-autorestart` fix applied

### 3.2 config.json (Central Configuration)
- **All configuration** lives here — no hardcoded magic numbers
- **City tiers:** tier_1 (atlanta, sao-paulo), tier_2 (miami), tier_3 (18 cities), avoid (cleared Apr 20)
- **Sigma overrides:** Per-city forecast error sigmas derived from historical accuracy data
- **Source preferences:** Region-based forecast source priority (US→HRRR, EU→ECMWF, etc.)
- **Self-learning:** Enabled with auto-calibration mode

### 3.3 tradingagents_integration.py
- **WeatherTradingAgents class:** Multi-agent debate system (bull case, bear case, judge)
- **Purpose:** Aggregate multiple perspectives before trading decision
- **Logging:** Full debate transcripts saved to `data/tradingagents_logs/`

### 3.4 self_improver.py
- **CityErrorTracker:** Tracks forecast errors per city, updates sigma and bias dynamically
- **Observation emitter:** Writes structured observations to `memory/self-improvement/observations/`
- **Resolution source validation:** Filters calibration data by matching forecast source to Polymarket resolution station

### 3.5 fill_tracker.py
- **Simulates Polymarket AMM fill rates**
- **Records:** fill result, fill price vs market price, realized P&L
- **Report generation:** `print_fill_report()` for trade analysis

### 3.6 weatherbet_v3.py
- **Legacy engine** (v3 architecture, superceded by bot_v2.py)
- **Still referenced:** Accuracy tracking, METAR integration patterns

### 3.7 data/ Directory
- `city_error_history.json` — Historical forecast errors per city
- `calibration.json` — City-specific calibration parameters
- `predictions.json` — Forecast snapshots per market
- `accuracy.json` — Rolling accuracy statistics
- `state.json` — Bot persistent state (last scan time, open positions)
- `tradingagents_logs/` — Debate transcripts (~77MB+)

---

## 4. Trading Strategy

### 4.1 Entry Criteria (All Must Pass)
1. **City in scan range:** tier_1_strong (atlanta only) with current tier config
2. **EV > min_ev:** 0.001 (April 19 recalibrated from 0.10)
3. **Confidence > min_confidence:** tier-dependent (tier1: 0.5, tier2: 0.75)
4. **Price ≤ max_price:** $0.50
5. **Volume ≥ min_volume:** 100
6. **Hours to expiry:** Between 1h and 48h
7. **No opposing open position** in same market

### 4.2 Position Sizing
- **Kelly criterion:** `f* = (p - q/r) / r` where p = win prob, q = 1-p, r = odds
- **Kelly fraction:** 0.20 (configurable, currently 0.20)
- **Max bet per trade:** $5.00 (paper), $50 (production target)
- **Max total exposure:** 8% of balance per day
- **Max open positions:** 10

### 4.3 City Tier Map (April 21 Recalibrated)

| Tier | Cities | Win Rate | Status |
|------|--------|----------|--------|
| **tier_1_strong** | atlanta | **81-83%** | PRIMARY — trade freely |
| **tier_1** | atlanta, sao-paulo | 83% / 63% | Trade with confidence |
| **tier_2** | miami | 40% | **BLOCKED** — win rate gate (<50%) |
| **tier_3** | london, paris, tokyo, hong-kong, singapore, seoul, dallas, chicago, seattle, nyc + others | 0-25% | **DROPPED** — `max_tier_to_trade: 2` in config.json |
| **avoid** | _(none currently)_ | — | — |

### 4.4 Exit Rules
- **Target sell price:** $0.45 (configurable)
- **Stop loss:** -20% of position value
- **Auto-sell on resolution:** Market resolution auto-closes position

### 4.5 Shoulder Season Bias (April 19 Pattern)
- Market is **COLLD-biased** in shoulder seasons (April)
- NO-side opportunities on mid-range buckets (when forecast is neither extreme hot nor cold)
- Monitor for warm surge patterns; block cold surge entries

### 4.6 Same-Day Trade Gate: METAR Morning Snapshot (April 21 2026)

For D+0 same-day markets, no position opens before 10am local city time. At or after 10am, the bot fetches METAR temperature observations at 6am, 7am, 8am, and 9am local via Open-Meteo Archive API and computes the **morning warmth trajectory**:

| Trajectory | Condition | Signal |
|------------|-----------|--------|
| Rising | T9am − T6am > +0.5°C | Supports HOT bucket bets (+20% conviction) |
| Falling | T9am − T6am < −0.5°C | Supports COLD bucket bets (reduce HOT conviction −20%) |
| Stable | |Δ| ≤ 0.5°C | No directional signal, use standard EV |

Same-day trades (D+0) require at least 3 of 4 morning readings available. If fewer than 3 readings are available, the bot falls back to the standard ECMWF+METAR blended forecast but still enforces the 10am minimum hour gate.

D+1 and D+2 markets are unaffected — they continue using ECMWF/HRRR forecast as before.

---

## 5. Forecast Sources

### 5.1 Primary Sources
| Region | Source | Priority |
|--------|--------|----------|
| US | Open-Meteo (AMDEB), NOAA-RAP fallback | 1st |
| EU | Open-Meteo (AMEDB), ECMWF fallback | 1st |
| Asia | Open-Meteo (AMDEB), ECMWF fallback | 1st |
| SA | Open-Meteo (AMDEB), ECMWF fallback | 1st |

### 5.2 Source Preferences (Config)
```json
{
  "us": ["ecmwf", "hrrr", "gfs"],
  "eu": ["ecmwf", "gfs", "metar"],
  "asia": ["ecmwf", "gfs", "metar"],
  "sa": ["ecmwf", "gfs", "metar"]
}
```

### 5.3 City-Specific Overrides
- **Asian cities:** UHI correction, sea breeze penalty, monsoon season flags
- **Sao Paulo:** Humidity-weighted adjustments
- **Atlanta:** Clean signal, lowest sigma (1.46°C) — best performing city

### 5.4 METAR Morning Snapshot (Same-Day, April 21 2026)
- **Endpoint:** `https://archive-api.open-meteo.com/v1/archive`
- **Auth:** None (free API, no key required)
- **Usage:** Fetches hourly `temperature_2m` at 6, 7, 8, 9am local per city for same-day trade gating
- **Fallback:** If <3 of 4 readings available, degrades gracefully to current METAR + ECMWF blend
- **Config:** `min_trade_hour: 10` — blocks same-day opens before 10am local

---

## 6. Self-Improvement System

### 6.1 Observation Flow
```
Market resolved → CityErrorTracker.log_error() → observation file →
Daily cron reflection → Updated sigma/bias → config.json updated
```

### 6.2 Tracked Parameters Per City
- `sigma` — Forecast error standard deviation (used for EV calculation)
- `bias` — Systematic forecast offset (e.g., Tokyo runs 0.8°C warm)
- `min_confidence` — Dynamic confidence threshold

### 6.3 Calibration Mode
- **auto:** Self-calibrates from resolved trades
- **min_trades_for_calibration:** 5 (configurable)
- **learning_rate:** 0.15 (configurable)
- **auto_reload_biases:** true — reloads updated biases on next scan

### 6.4 Historical Calibration Data
| City | Win Rate | Avg Error (°C) | Sigma (°C) | Status |
|------|----------|----------------|-------------|--------|
| Atlanta | 83% | 0.73 | 1.46 | TRADE |
| Sao Paulo | 60% | 1.22 | 2.44 | OK |
| Miami | 40% | 1.08 | 2.16 | Borderline |
| London | 0% | 3.48 | 6.96 | AVOID |
| Paris | 20% | 4.10 | 8.20 | AVOID |
| Hong Kong | 25% | 2.08 | 4.15 | AVOID |
| Tokyo | 20% | 2.30 | 4.60 | AVOID |
| Singapore | 20% | 3.14 | 6.28 | AVOID |
| Dallas | 0% | ? | ? | **DROPPED** — 0 resolved trades, unknown sigma, tier 3 |

---

## 7. API Integration

### 7.1 Polymarket CLOB API
- **Endpoint:** `https://clob.polymarket.com`
- **Auth:** MetaMask wallet signature
- **Markets:** `GET /markets?tag=temperature` (filtered)
- **Orders:** `GET /orders`, `POST /orders` (fill-or-kill)
- **Positions:** `GET /positions`
- **Trading fee:** 0.02 (2%)

### 7.2 Weather APIs
- **Open-Meteo (primary):** `https://api.open-meteo.com/v1/forecast` — free, no key
- **NOAA-RAP (fallback):** `https://nomads.ncep.noaa.gov/dods/rap/rapascii/` — free
- **MetOffice (UK backup):** `https://api.metoffice.gov.uk/` — requires key

### 7.3 Self-Learning Integration
- Startup script: `start_with_learning.sh` — activates self_learning with calibration_mode=auto
- Must be called on every PM2 restart

---

## 8. Known Issues & Fixes (Historical Log)

| Date | Issue | Fix |
|------|-------|-----|
| Apr 12 | YES/NO price inversion in hot buckets | Fixed `prices[0]` = YES assignment |
| Apr 12 | Bucket selection by P(bucket) instead of EV | Fixed to highest-EV bucket selection |
| Apr 12 | Tokyo 511°C bug (bucket_mid vs forecast_temp) | Fixed to use `forecast_temp` directly |
| Apr 13 | PM2 stale error logs causing alert spam | Added log rotation, truncated stale logs |
| Apr 18 | Double-process restart loop (orphan pid) | Added `--no-autorestart` flag, orphan kill |
| Apr 18 | paper_force_trade forcing negative EV trades | Turned OFF |
| Apr 18 | Unit mismatch (C vs F bucket confusion) | Smart bucket_score matching |
| Apr 19 | max_tier_to_trade: 2 (was 3) | Apr 21 — Tier 3 dropped entirely due to 0-25% win rates |
| Apr 19 | Self-improver reading wrong field (position.forecast_temp null) | Fixed to `forecast_snapshots[-1].best` |
| Apr 20 | FileNotFoundError in data/ directory | Added `mkdir(parents=True, exist_ok=True)` |
| Apr 20 | Stale PM2 error logs misdirecting debugging | Truncated pre-fix log files |
| Apr 21 | _cal never initialized before city scan | Added `_cal = load_cal()` at top of `scan_and_update()` — calibration was silently bypassing city-specific sigma |
| Apr 21 | max_tier_to_trade: 3 — Tier 3 cities (0-25% WR) still scanned | Set `max_tier_to_trade: 2` in config.json — drops london/paris/tokyo/singapore/hong-kong/seoul/dallas/chicago/seattle/nyc |
| Apr 21 | Win rate gate was dead code (`pass` no-op) | Replaced with `continue` + `[SKIP]` message — cities with <50% historical WR now blocked |
| Apr 21 | Python 3.14 `concurrent.futures.TimeoutExpired` removed | Changed to bare `TimeoutError` in try/except |
| Apr 21 | Dallas has 0 resolved trades in city_error_history.json | `get_city_error_sigma('dallas')` always returns None → falls back to generic BASE_SIGMA 1.5°F which understates uncertainty |

---

## 9. Operation & Maintenance

### 9.1 PM2 Management
```bash
# Start with self-learning
./start_with_learning.sh

# Monitor status
pm2 status
pm2 logs alter-bot-v2

# Restart
pm2 restart alter-bot-v2

# Stop
pm2 stop alter-bot-v2
```

### 9.2 Cron Jobs
| Job | Schedule | Purpose |
|-----|----------|---------|
| Alter-Bot Watchdog | Every 10 min | Monitor PID, alert on crash |
| Auto-Dream Memory | 2PM MYT | Consolidate daily memory logs |
| Self-Improvement Reflection | 11PM MYT | Analyze daily observations |
| Sports Toto Draw | Draw days 8PM | Notify on draw days |

### 9.3 Debug Protocol
1. **Check log mtime FIRST:** `ls -la *.log` — PM2 leaves stale logs after rotation
2. **Invoke PUA skill:** If stuck >5 min on same problem
3. **Invoke ExecPlan skill:** For multi-step complex fixes
4. **Verify before claiming done:** Run type-check + lint

### 9.4 Startup Validation (Pending — Rolling Action)
Pre-flight check that cross-references:
- City tier assignments against historical win rates
- AVOID list consistency (tier_1/2 must not contain any AVOID cities)
- Config consistency (warn if avoid + tier_1_only + max_tier conflict)

---

## 10. Files Reference

| File | Size | Purpose |
|------|------|---------|
| `bot_v2.py` | 108KB | Main trading engine |
| `config.json` | 16.6KB | All configuration |
| `self_improver.py` | 16.9KB | Self-improvement engine |
| `tradingagents_integration.py` | 44KB | Multi-agent debate system |
| `fill_tracker.py` | 14.6KB | AMM fill simulation |
| `weatherbet_v3.py` | 26KB | Legacy v3 engine (reference) |
| `data/` | 77MB+ | Logs, state, calibration |

---

## 11. Success Metrics

### 11.1 Trading Performance
- **Win rate target:** 90%+ on tier_1 cities
- **Avg error target:** <1.5°C on tier_1
- **EV per trade:** >0.001 (positive EV mandatory)
- **Max daily drawdown:** <20%

### 11.2 Operational Health
- **PM2 uptime:** >95% within analysis window
- **Error log freshness:** No stale logs >24h old
- **Self-improvement cycle:** Observations → reflection → encoding <48h

### 11.3 Self-Learning Accuracy
- **Sigma convergence:** City sigma stabilizing after 20+ resolved trades
- **Bias correction:** Systematic errors corrected within 3 resolution cycles

---

## 12. Roadmap / Open Items

| Priority | Item | Status |
|----------|------|--------|
| HIGH | Startup validation script (cross-check tiers vs win rates) | Pending |
| ~~HIGH~~ | Verify Dallas 0% WR trade outcome (Apr 20 resolution) | **RESOLVED** — Dallas dropped from scan, 0 trade history |
| MEDIUM | Sao Paulo tier promotion study (63% WR) | Backlog — needs 20+ more trades before reconsidering |
| MEDIUM | Production wallet integration (paper → live) | Backlog |
| LOW | Meteoblue API key rotation | Backlog |
| LOW | Tokyo Haneda (RJTT) bucket optimization | Backlog |
| MEDIUM | `bucket_score()` uses manual Gaussian CDF instead of `bucket_prob_cumulative()` | Backlog — function exists but never called |
| MEDIUM | `is_peak_time_passed()` hardcodes hours instead of reading from config | Backlog |
| MEDIUM | `get_metar()` always receives `None` for `ecmwf_temp` — anomaly check never fires | Backlog |
| LOW | `data/tradingagents_logs/` (~77MB) has no rotation | Backlog |

---

*Document maintained by TIGER001. Update on significant strategy or architecture changes.*
