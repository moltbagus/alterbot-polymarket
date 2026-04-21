# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Alter-Bot is a Polymarket weather prediction trading bot. It ingests temperature forecasts from Open-Meteo (ECMWF, HRRR), compares forecast probability distributions against Polymarket bucket pricing, and executes paper trades when Expected Value is positive using Kelly Criterion position sizing.

**Primary file:** `bot_v2.py` (main trading engine, ~2,400 LOC)
**Config:** `config.json` (all parameters, no hardcoded magic numbers)
**Paper trading balance:** $1,000 (as of 2026-04-19)

---

## Commands

```bash
cd /home/alyssa/.openclaw/workspace/alter-bot-v1

python3 bot_v2.py status      # balance + open positions
python3 bot_v2.py report      # full resolved market breakdown
python3 bot_v2.py             # start main scan loop (PM2 managed)

# Backtesting
python3 proper_backtest.py           # backtest against actual resolved temps
python3 city_optimizer.py            # generate city tier optimization report
python3 full_backtest.py             # full historical backtest
python3 ultimate_optimizer.py        # parameter sweep optimization

# Self-improvement
python3 self_improver.py process     # process daily observations

# PM2 management (bot is PM2-managed, not run directly)
pm2 status
pm2 logs alter-bot-v2
pm2 restart alter-bot-v2
./start_with_learning.sh             # start with self-learning activated

# Syntax validation
python3 -m py_compile bot_v2.py
```

---

## Architecture

```
Market Scan → City Tier Filter → Forecast Fetch (ECMWF/HRRR/METAR) →
Bucket Selection → EV Calculation → Conviction Filter → Kelly Sizing → Trade
     ↓
Resolution Tracking → CityErrorTracker.log_error() → observation file →
Daily reflection → sigma/bias update → config.json reloaded
```

### Core Pipeline (bot_v2.py)
1. `scan_and_update()` — main loop, iterates all cities
2. `take_forecast_snapshot()` — fetches ECMWF + HRRR + METAR per city
3. `select_bucket()` — picks highest-EV bucket from Polymarket markets
4. `calc_buy_amount()` — Kelly Criterion position sizing
5. `execute_trade()` — records trade, triggers self-improvement observation

### Supporting Modules
- `self_improver.py` — `CityErrorTracker` tracks forecast errors per city, updates sigma/bias dynamically
- `tradingagents_integration.py` — multi-agent debate system (bull/bear/judge) before trading decisions; logs to `data/tradingagents_logs/`
- `fill_tracker.py` — simulates Polymarket AMM fill rates, records P&L

---

## City Tier System (Critical)

Filter cities by tier to achieve 90%+ win rate. Tier assignments live in `config.json` under `city_tiers`.

| Tier | Cities | Win Rate | Notes |
|------|--------|----------|-------|
| `tier_1_strong` | atlanta | 83% | PRIMARY — trade freely |
| `tier_1` | atlanta, sao-paulo | 83% / 60% | Trade with confidence |
| `tier_2` | miami | 40% | Borderline |
| `tier_3` | all others (london, paris, tokyo, nyc, seoul, etc.) | 0–25% | Paper-track only |

Key config flags:
- `min_tier_to_trade` / `max_tier_to_trade` — control scan range
- `tier_1_only` — restrict to `tier_1_strong` only
- `blocked_cities` / `avoid` list — explicit exclusions

**Sigma per city** (`sigma_override` in config.json):
- atlanta: 1.46°C (best)
- sao-paulo: 2.44°C
- miami: 2.16°C
- seoul: 3.6°C
- london: 6.96°C
- paris: 8.2°C (worst)

---

## Configuration (config.json)

All settings centralized. Key sections:
- `balance`, `max_bet`, `kelly_fraction` — position sizing
- `min_ev`, `max_price`, `min_volume`, `min_hours`, `max_hours` — entry criteria
- `sigma_override` — per-city forecast error sigmas
- `asian_city_config` — UHI correction, sea breeze penalty, monsoon flags per Asian city
- `daily_optimization` — morning METAR/ensemble weighting, prediction window

**Config is read at startup and on SIGHUP reload.** Do not hardcode values in bot_v2.py.

---

## Known Architectural Issues (execplan.md)

Several known issues documented in `execplan.md` that need fixing:
1. `bucket_score()` uses wrong formula — should call `bucket_prob()` instead
2. `is_peak_time_passed()` uses hardcoded hour checks instead of `peak_hour` from config
3. `get_metar()` always receives `None` for `ecmwf_temp` — METAR anomaly check never triggers
4. Three overlapping sigma functions (`get_sigma`, `get_horizon_adjusted_sigma`, `get_dynamic_sigma`) create confusing 4-layer stack
5. Sequential city scanning — config has `parallel_scanning: true` and `max_concurrent_scans: 10` but never implemented
6. `data/tradingagents_logs/` (~77MB) has no rotation — oldest logs never pruned

---

## Data Directory

```
data/
  markets/           # one JSON per market, contains forecast snapshots + trade history
  tradingagents_logs/  # debate transcripts (no rotation, grows indefinitely)
  city_error_history.json
  calibration.json
  predictions.json
  accuracy.json
  state.json         # persistent bot state (last scan time, open positions)
```

---

## Polymarket Resolution

Markets resolve on **airport station** coordinates (e.g., NYC → KLGA LaGuardia, not city center). This matters — city center vs airport can differ 3–8°F, enough to shift a 1–2°F bucket outcome. Station mapping is in `resolution_source.py`.

---

## Key Constraints

- `min_ev: 0.001` (recalibrated April 19 from 0.10)
- `max_price: $0.50`
- `min_volume: 100`
- `kelly_fraction: 0.20`
- `scan_interval: 300` seconds
- AMM fill simulation via `fill_tracker.py` — not real fills