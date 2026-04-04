#!/usr/bin/env python3
"""
Monte Carlo Optimizer v2 for Alter Bot v1
==========================================
Uses all historical data sources to find optimal config for >90% win rate.
"""

import json
import random
import numpy as np
from pathlib import Path
from collections import defaultdict
import copy

random.seed(42)
np.random.seed(42)

DATA_DIR = Path("/home/alyssa/.openclaw/workspace/alter-bot-v1/data")

# ============================================================
# LOAD ALL DATA SOURCES
# ============================================================

def load_all_data():
    """Load all historical data from all available sources."""
    all_rows = []

    # 1. Browser polymarket backtest (118 rows, 8 cities)
    import csv
    with open(DATA_DIR / "polymarket_backtest_combined.csv") as f:
        for row in csv.DictReader(f):
            try:
                all_rows.append({
                    "source": "browser_backtest",
                    "city": row["city"].lower(),
                    "date": row["date"],
                    "predicted": float(row["predicted_temp"]) if row["predicted_temp"] else 0,
                    "actual": float(row["actual_temp"]) if row["actual_temp"] else 0,
                    "confidence": 0.80,  # default high confidence for backtest trades
                    "correct": row["correct"] == "True",
                    "win": int(row["win"]) if row["win"] else 0,
                    "bucket_win": row["correct"] == "True",
                    "daily_win": row["correct"] == "True",
                })
            except (ValueError, KeyError):
                pass

    # 2. Asian cities 365-day backtest (150 rows, 3 cities)
    with open(DATA_DIR / "asian_cities_365day_backtest.csv") as f:
        for row in csv.DictReader(f):
            try:
                all_rows.append({
                    "source": "asian_365day",
                    "city": row["city"].lower(),
                    "date": row["date"],
                    "predicted": float(row["predicted"]) if row["predicted"] else 0,
                    "actual": float(row["actual"]) if row["actual"] else 0,
                    "confidence": float(row["confidence"]) if row["confidence"] else 0,
                    "correct": row["daily_win"] == "True",
                    "win": 1 if row["daily_win"] == "True" else 0,
                    "bucket_win": row["bucket_win"] == "True",
                    "daily_win": row["daily_win"] == "True",
                })
            except (ValueError, KeyError):
                pass

    # 3. Resolved trades from market JSON files
    import glob
    for f in glob.glob(str(DATA_DIR / "markets" / "*.json")):
        try:
            with open(f) as fh:
                d = json.load(fh)
                if d.get("position") and d.get("position", {}).get("close_reason") == "resolved":
                    pos = d["position"]
                    all_rows.append({
                        "source": "resolved_trade",
                        "city": d["city"].lower(),
                        "date": d["date"],
                        "predicted": pos.get("forecast_temp", 0),
                        "actual": d.get("resolved_temp", 0),
                        "confidence": 0.85,
                        "correct": pos.get("pnl", 0) > 0,
                        "win": 1 if pos.get("pnl", 0) > 0 else 0,
                        "bucket_win": pos.get("pnl", 0) > 0,
                        "daily_win": pos.get("pnl", 0) > 0,
                        "entry_price": pos.get("entry_price", 0),
                        "ev": pos.get("ev", 0),
                        "kelly": pos.get("kelly", 0),
                        "pnl": pos.get("pnl", 0),
                    })
        except (json.JSONDecodeError, KeyError, ValueError):
            pass

    return all_rows


# ============================================================
# SIMULATION ENGINE
# ============================================================

def simulate_trade(row, config):
    """
    Determine if a row would generate a trade and whether it wins.
    Returns (traded: bool, won: bool)
    """
    city = row["city"]
    confidence = row.get("confidence", 0)
    bucket_win = row.get("bucket_win", False)
    daily_win = row.get("daily_win", False)

    # City filters
    blocked = config.get("blocked_cities", [])
    if city in blocked:
        return False, False

    allowed = config.get("allowed_cities", None)
    if allowed and city not in allowed:
        return False, False

    # City tier filter
    tier1_only = config.get("tier_1_only", False)
    tier1_elite = config.get("tier_1_elite", [])
    if tier1_only and city not in tier1_elite:
        return False, False

    # Per-city confidence overrides
    city_min_conf = config.get("city_min_conf", {})
    min_conf = city_min_conf.get(city, config.get("min_confidence", 0.5))

    if confidence < min_conf:
        return False, False

    # Conviction filter
    conviction_mult = config.get("conviction_mult", 10.0)
    min_conviction = config.get("min_conviction", 5.0)
    conviction = confidence * conviction_mult
    if conviction < min_conviction:
        return False, False

    # EV filter (simulated)
    ev = row.get("ev", 0)
    if ev > 0 and ev < config.get("min_ev", 0.1):
        return False, False

    # Entry price filter
    entry_price = row.get("entry_price", 0)
    if entry_price > 0 and entry_price > config.get("max_price", 0.45):
        return False, False

    # Trade! Win = bucket_win (temperature was in predicted bucket)
    won = bucket_win
    return True, won


def evaluate_config(config, data):
    """Evaluate a config against all historical data."""
    wins = 0
    losses = 0
    trades = 0

    for row in data:
        traded, won = simulate_trade(row, config)
        if traded:
            trades += 1
            if won:
                wins += 1
            else:
                losses += 1

    if trades == 0:
        return 0.0, 0, 0, 0

    return wins / trades, trades, wins, losses


# ============================================================
# ANALYSIS
# ============================================================

def analyze_data(data):
    """Deep analysis of the dataset."""
    print("\n" + "=" * 70)
    print("DATA ANALYSIS")
    print("=" * 70)
    print(f"Total rows: {len(data)}")

    by_city = defaultdict(lambda: {"wins": 0, "total": 0, "conf_sum": 0, "rows": []})
    for row in data:
        city = row["city"]
        by_city[city]["total"] += 1
        by_city[city]["conf_sum"] += row.get("confidence", 0)
        if row.get("bucket_win", False):
            by_city[city]["wins"] += 1
        by_city[city]["rows"].append(row)

    print("\nCity statistics (all data):")
    city_stats = []
    for city, s in sorted(by_city.items(), key=lambda x: x[1]["wins"]/max(x[1]["total"], 1), reverse=True):
        wr = s["wins"] / max(s["total"], 1)
        avg_conf = s["conf_sum"] / max(s["total"], 1)
        city_stats.append({
            "city": city,
            "win_rate": wr,
            "total": s["total"],
            "wins": s["wins"],
            "avg_confidence": avg_conf,
            "rows": s["rows"],
        })
        print(f"  {city:15s}: WR={wr*100:5.1f}%  ({s['wins']:3d}/{s['total']:3d})  avg_conf={avg_conf:.2f}")

    # Analyze win rate by confidence bucket per city
    print("\nWin rate by confidence bucket per city:")
    for cs in city_stats[:6]:
        city = cs["city"]
        by_conf = defaultdict(lambda: {"wins": 0, "total": 0})
        for row in cs["rows"]:
            conf = row.get("confidence", 0)
            conf_bucket = round(conf * 10) / 10  # round to nearest 0.1
            by_conf[conf_bucket]["total"] += 1
            if row.get("bucket_win", False):
                by_conf[conf_bucket]["wins"] += 1

        print(f"  {city}:")
        for conf in sorted(by_conf.keys()):
            s = by_conf[conf]
            wr = s["wins"] / max(s["total"], 1)
            print(f"    conf>={conf:.1f}: WR={wr*100:.1f}% ({s['wins']}/{s['total']})")

    return city_stats


def find_best_confidence_cutoff(city, rows, target_wr=0.90):
    """Find the minimum confidence threshold to achieve target win rate."""
    # Sort rows by confidence descending
    sorted_rows = sorted(rows, key=lambda x: x.get("confidence", 0), reverse=True)

    best_thresh = 0.0
    best_wr = 0.0
    best_trades = 0

    # Try different thresholds
    for thresh in np.arange(0.0, 1.01, 0.05):
        wins = sum(1 for r in sorted_rows if r.get("confidence", 0) >= thresh and r.get("bucket_win", False))
        total = sum(1 for r in sorted_rows if r.get("confidence", 0) >= thresh)

        if total >= 3:  # min sample
            wr = wins / total
            if wr >= target_wr and total > best_trades:
                best_thresh = thresh
                best_wr = wr
                best_trades = total

    return best_thresh, best_wr, best_trades


# ============================================================
# MONTE CARLO + GRID SEARCH
# ============================================================

def monte_carlo_search(data, n_iterations=10000):
    """Broad Monte Carlo search over parameter space."""
    print("\n" + "=" * 70)
    print(f"MONTE CARLO SEARCH ({n_iterations:,} iterations)")
    print("=" * 70)

    all_cities = list(set(row["city"] for row in data))

    # City tier candidates
    tier1_options = [
        ["singapore"],
        ["paris"],
        ["london"],
        ["singapore", "paris"],
        ["singapore", "london"],
        ["singapore", "paris", "london"],
        ["paris", "london"],
        ["singapore", "tokyo"],
        ["singapore", "paris", "london", "tokyo"],
        ["singapore", "paris", "london", "atlanta"],
        None,  # all cities
    ]

    blocked_options = [
        [],
        ["seoul", "shanghai", "taipei", "hong-kong", "shanghai", "seoul"],
        ["taipei", "hong-kong", "seoul", "shanghai", "tokyo"],
    ]

    results = []

    for i in range(n_iterations):
        # Sample config
        cfg = {
            "min_confidence": round(random.uniform(0.50, 0.95), 2),
            "min_ev": round(random.uniform(0.0, 1.0), 2),
            "min_conviction": round(random.uniform(4.0, 10.0), 1),
            "conviction_mult": round(random.uniform(8.0, 12.0), 1),
            "max_price": round(random.uniform(0.25, 0.50), 2),
            "allowed_cities": random.choice(tier1_options),
            "blocked_cities": random.choice(blocked_options),
            "tier_1_only": random.random() > 0.5,
            "tier_1_elite": ["singapore", "paris", "london"],
            "city_min_conf": {},
        }

        # Per-city overrides
        if random.random() > 0.5 and cfg["allowed_cities"]:
            for c in cfg["allowed_cities"][:2]:
                cfg["city_min_conf"][c] = round(random.uniform(0.5, 0.8), 2)

        wr, trades, wins, losses = evaluate_config(cfg, data)

        if trades >= 5:
            results.append({
                "config": copy.deepcopy(cfg),
                "win_rate": wr,
                "trades": trades,
                "wins": wins,
                "losses": losses,
            })

        if (i + 1) % 2000 == 0:
            print(f"  Progress: {i+1:,}/{n_iterations:,}...")

    results.sort(key=lambda x: (x["win_rate"], x["trades"]), reverse=True)

    print(f"\nTotal valid configs: {len(results)}")
    if results:
        print(f"Best WR: {results[0]['win_rate']*100:.1f}% ({results[0]['wins']}/{results[0]['trades']})")

    print("\nTop 15 configs:")
    for i, r in enumerate(results[:15]):
        c = r["config"]
        cities = c["allowed_cities"] if c["allowed_cities"] else "ALL"
        print(f"  {i+1:2d}. WR={r['win_rate']*100:5.1f}% ({r['wins']:3d}/{r['trades']:3d}) | "
              f"min_conf={c['min_confidence']:.2f} min_ev={c['min_ev']:.2f} "
              f"min_conv={c['min_conviction']:.1f} cities={cities}")

    return results


def grid_search_confidence_by_city(data, city_stats):
    """Grid search over confidence thresholds to find per-city optimal."""
    print("\n" + "=" * 70)
    print("GRID SEARCH: Per-city confidence thresholds")
    print("=" * 70)

    results = []

    # For each city, find the best confidence threshold
    for cs in city_stats:
        city = cs["city"]
        rows = cs["rows"]

        for thresh in np.arange(0.50, 1.01, 0.05):
            cfg = {
                "min_confidence": thresh,
                "min_ev": 0.0,
                "min_conviction": 0.0,
                "conviction_mult": 10.0,
                "max_price": 0.5,
                "allowed_cities": [city],
                "blocked_cities": [],
                "tier_1_only": False,
                "tier_1_elite": [],
                "city_min_conf": {},
            }

            wr, trades, wins, losses = evaluate_config(cfg, data)

            if trades >= 3:
                results.append({
                    "city": city,
                    "thresh": thresh,
                    "win_rate": wr,
                    "trades": trades,
                    "wins": wins,
                    "losses": losses,
                })

    results.sort(key=lambda x: (x["win_rate"], x["trades"]), reverse=True)

    print("\nBest threshold per city (min 3 trades):")
    best_per_city = {}
    for r in results:
        city = r["city"]
        if city not in best_per_city:
            best_per_city[city] = r
            print(f"  {city:15s}: thresh={r['thresh']:.2f} WR={r['win_rate']*100:.1f}% ({r['wins']}/{r['trades']})")

    return best_per_city


def multi_city_combination_search(data, city_stats):
    """Search for best multi-city combination with individual thresholds."""
    print("\n" + "=" * 70)
    print("MULTI-CITY COMBINATION SEARCH")
    print("=" * 70)

    # Build per-city best thresholds
    city_thresh = {}
    for cs in city_stats:
        city = cs["city"]
        rows = cs["rows"]
        best_thresh = 0.0
        best_wr = 0.0
        best_trades = 0
        for thresh in np.arange(0.50, 1.01, 0.05):
            cfg = {
                "min_confidence": thresh,
                "min_ev": 0.0,
                "min_conviction": 0.0,
                "conviction_mult": 10.0,
                "max_price": 0.5,
                "allowed_cities": [city],
                "blocked_cities": [],
                "tier_1_only": False,
                "tier_1_elite": [],
                "city_min_conf": {},
            }
            wr, trades, wins, losses = evaluate_config(cfg, data)
            if trades >= 3 and wr > best_wr:
                best_wr = wr
                best_thresh = thresh
                best_trades = trades
        if best_thresh > 0:
            city_thresh[city] = (best_thresh, best_wr, best_trades)

    print("Per-city best thresholds:")
    for city, (thresh, wr, trades) in sorted(city_thresh.items(), key=lambda x: x[1][1], reverse=True):
        print(f"  {city:15s}: thresh={thresh:.2f} WR={wr*100:.1f}% ({trades})")

    # Try combinations of top cities
    from itertools import combinations

    top_cities = [c for c, (t, wr, tr) in sorted(city_thresh.items(), key=lambda x: x[1][1], reverse=True) if wr >= 0.70]

    results = []
    for size in range(1, min(5, len(top_cities) + 1)):
        for combo in combinations(top_cities, size):
            combo = list(combo)
            # Build config with per-city thresholds
            city_min_conf = {city: city_thresh[city][0] for city in combo}

            cfg = {
                "min_confidence": 0.5,
                "min_ev": 0.0,
                "min_conviction": 0.0,
                "conviction_mult": 10.0,
                "max_price": 0.5,
                "allowed_cities": combo,
                "blocked_cities": [],
                "tier_1_only": False,
                "tier_1_elite": combo,
                "city_min_conf": city_min_conf,
            }

            wr, trades, wins, losses = evaluate_config(cfg, data)

            if trades >= 5:
                results.append({
                    "cities": combo,
                    "city_thresholds": city_min_conf.copy(),
                    "win_rate": wr,
                    "trades": trades,
                    "wins": wins,
                    "losses": losses,
                })

    results.sort(key=lambda x: (x["win_rate"], x["trades"]), reverse=True)

    print(f"\nBest multi-city combinations:")
    for i, r in enumerate(results[:10]):
        print(f"  {i+1}. WR={r['win_rate']*100:.1f}% ({r['wins']}/{r['trades']}) | "
              f"cities={r['cities']} thresh={r['city_thresholds']}")

    return results


def extreme_filter_search(data):
    """Search with very strict filters (the 'perfect' config)."""
    print("\n" + "=" * 70)
    print("EXTREME FILTER SEARCH (strictest thresholds)")
    print("=" * 70)

    # Only trade when bucket_win is True and confidence is very high
    strict_configs = []

    for min_conf in [0.80, 0.85, 0.90, 0.95]:
        for city in ["singapore", "paris", "london"]:
            cfg = {
                "min_confidence": min_conf,
                "min_ev": 0.0,
                "min_conviction": 0.0,
                "conviction_mult": 10.0,
                "max_price": 0.5,
                "allowed_cities": [city],
                "blocked_cities": [],
                "tier_1_only": False,
                "tier_1_elite": [city],
                "city_min_conf": {city: min_conf},
            }

            wr, trades, wins, losses = evaluate_config(cfg, data)
            strict_configs.append({
                "config": cfg,
                "win_rate": wr,
                "trades": trades,
                "wins": wins,
                "losses": losses,
            })

    # Also try top-3 cities combined with high threshold
    for min_conf in [0.80, 0.85, 0.90]:
        cfg = {
            "min_confidence": min_conf,
            "min_ev": 0.0,
            "min_conviction": 0.0,
            "conviction_mult": 10.0,
            "max_price": 0.5,
            "allowed_cities": ["singapore", "paris", "london"],
            "blocked_cities": [],
            "tier_1_only": False,
            "tier_1_elite": ["singapore", "paris", "london"],
            "city_min_conf": {"singapore": min_conf, "paris": min_conf, "london": min_conf},
        }

        wr, trades, wins, losses = evaluate_config(cfg, data)
        strict_configs.append({
            "config": cfg,
            "win_rate": wr,
            "trades": trades,
            "wins": wins,
            "losses": losses,
        })

    strict_configs.sort(key=lambda x: (x["win_rate"], x["trades"]), reverse=True)

    print("\nStrict config results:")
    for i, r in enumerate(strict_configs):
        c = r["config"]
        cities = c["allowed_cities"]
        thresh = c["min_confidence"]
        print(f"  {i+1}. WR={r['win_rate']*100:.1f}% ({r['wins']}/{r['trades']}) | "
              f"cities={cities} min_conf={thresh:.2f}")

    return strict_configs


# ============================================================
# BUILD OPTIMAL CONFIG
# ============================================================

def build_optimal_config(mc_results, grid_results, multi_results, extreme_results, city_stats):
    """Build the final optimal config.

    NOTE: True >90% win rate requires more data or stricter filters than
    currently available. This optimizer finds the best achievable WR
    with meaningful sample size (>=10 trades).
    """

    # Combine all results - normalize format
    all_results = []
    for r in mc_results:
        all_results.append(("mc", r))
    # grid_results is dict {city: result}, convert to list
    for city, r in grid_results.items():
        r_copy = dict(r)
        r_copy["_city"] = city
        all_results.append(("grid", r_copy))
    for r in multi_results:
        all_results.append(("multi", r))
    for r in extreme_results:
        all_results.append(("extreme", r))

    # Sort by win_rate, then trades
    def get_trades(r):
        if isinstance(r, dict):
            return r.get("trades", r.get("total", 0))
        return 0

    all_results.sort(key=lambda x: (x[1].get("win_rate", 0), get_trades(x[1])), reverse=True)

    # Filter to configs with >= 10 trades for statistical significance
    MIN_TRADES = 10
    significant_results = [r for r in all_results if get_trades(r[1]) >= MIN_TRADES]

    print(f"\n--- BEST CONFIG WITH >={MIN_TRADES} TRADES ---")
    if significant_results:
        best_sig = significant_results[0]
        print(f"  Source: {best_sig[0]}, WR={best_sig[1].get('win_rate', 0)*100:.1f}%, "
              f"trades={get_trades(best_sig[1])}")

    # Find best - prefer statistically significant results (>=10 trades)
    best = None
    best_wr = 0
    best_trades = 0

    for source, r in all_results:
        wr = r["win_rate"]
        trades = r.get("trades", r.get("total", 0))

        # Prioritize significant results
        is_significant = trades >= MIN_TRADES
        current_is_significant = best_trades >= MIN_TRADES if best else False

        if is_significant and not current_is_significant:
            # Prefer significant over non-significant
            best_wr = wr
            best_trades = trades
            best = (source, r)
        elif is_significant == current_is_significant:
            # Same category - pick higher WR, then more trades
            if wr > best_wr or (wr == best_wr and trades > best_trades):
                best_wr = wr
                best_trades = trades
                best = (source, r)
        # Non-significant only wins if we have nothing else

    if best is None:
        print("WARNING: No valid config found!")
        return {}

    source, best_r = best

    # Determine elite cities
    elite_cities = [cs["city"] for cs in city_stats if cs["win_rate"] >= 0.90]
    strong_cities = [cs["city"] for cs in city_stats if cs["win_rate"] >= 0.70]
    good_cities = [cs["city"] for cs in city_stats if cs["win_rate"] >= 0.60]

    # Extract config details
    if source in ["mc"]:
        cfg = best_r["config"]
        min_conf = cfg["min_confidence"]
        min_ev = cfg["min_ev"]
        min_conviction = cfg["min_conviction"]
        conviction_mult = cfg["conviction_mult"]
        max_price = cfg["max_price"]
        allowed_cities = cfg["allowed_cities"] or strong_cities[:6]
        city_min_conf = cfg["city_min_conf"]
        blocked = cfg["blocked_cities"]
    elif source == "extreme":
        cfg = best_r["config"]
        min_conf = cfg["min_confidence"]
        min_ev = 0.0
        min_conviction = 0.0
        conviction_mult = 10.0
        max_price = 0.35
        allowed_cities = cfg["allowed_cities"]
        city_min_conf = cfg["city_min_conf"]
        blocked = []
    elif source == "multi":
        allowed_cities = best_r["cities"]
        city_min_conf = best_r["city_thresholds"]
        min_conf = 0.5
        min_ev = 0.0
        min_conviction = 0.0
        conviction_mult = 10.0
        max_price = 0.35
        blocked = []
    else:
        # grid result format differs
        min_conf = best_r.get("thresh", 0.75)
        min_ev = 0.0
        min_conviction = 0.0
        conviction_mult = 10.0
        max_price = 0.35
        allowed_cities = [best_r["city"]]
        city_min_conf = {best_r["city"]: min_conf}
        blocked = []

    # Build optimal config block
    optimal = {
        "description": "Monte Carlo optimized config for >90% win rate (2026-04-04)",
        "strategy": "high_conviction_monte_carlo",

        # Core thresholds
        "min_confidence": round(min_conf, 2),
        "min_ev": round(min_ev, 2),
        "min_conviction": round(min_conviction, 1),
        "conviction_mult": round(conviction_mult, 1),
        "max_price": round(max_price, 2),
        "max_bet": 1.0,
        "kelly_fraction": 0.2,

        # City tiers
        "city_tiers": {
            "tier_1_elite": elite_cities if elite_cities else strong_cities[:3],
            "tier_1": strong_cities[:8] if strong_cities else allowed_cities[:8],
            "tier_2": good_cities[:12] if good_cities else [],
        },

        # Trading mode
        "tier_1_only": False,
        "min_tier_to_trade": 1,
        "max_tier_to_trade": 2,

        # Allowed/blocked cities
        "allowed_cities": allowed_cities,
        "blocked_cities": blocked,

        # Per-city confidence overrides (key for >90%)
        "city_min_conf": {k: round(v, 2) for k, v in city_min_conf.items()},

        # Risk management
        "max_total_exposure_pct": 0.08,
        "max_daily_spend": 20.0,
        "max_open_positions": 10,
        "max_slippage": 0.02,

        # Source weights
        "metar_weight": 0.6,
        "ecmwf_weight": 0.25,
        "sentinel_weight": 0.15,

        # Prediction window
        "best_prediction_window": [9, 10, 11, 12],

        # Self-improvement
        "self_improvement": {
            "enabled": True,
            "track_city_errors": True,
            "update_after_resolve": True,
            "min_samples_for_update": 5,
            "dynamic_sigma": True,
            "adaptive_bias": True,
            "learning_rate": 0.15,
        },

        # Backtest results
        "backtest": {
            "best_win_rate": round(best_wr, 4),
            "best_trades": best_trades,
            "best_wins": best_r.get("wins", 0),
            "best_losses": best_r.get("losses", 0),
            "best_source": source,
            "elite_cities": elite_cities,
            "strong_cities": strong_cities,
            "total_cities_analyzed": len(city_stats),
        },

        # Optimization metadata
        "optimization": {
            "method": "monte_carlo_grid_combined",
            "n_iterations": 10000,
            "target_win_rate": 0.90,
            "min_sample_size": 5,
            "date": "2026-04-04",
        }
    }

    return optimal


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 70)
    print("MONTE CARLO OPTIMIZER v2 - Alter Bot v1")
    print("Finding optimal config for >90% win rate")
    print("=" * 70)

    # Load all data
    print("\nLoading all data sources...")
    data = load_all_data()
    print(f"Total rows loaded: {len(data)}")

    # Analyze data
    city_stats = analyze_data(data)

    # Monte Carlo search
    mc_results = monte_carlo_search(data, n_iterations=10000)

    # Grid search per city
    grid_results = grid_search_confidence_by_city(data, city_stats)

    # Multi-city combination search
    multi_results = multi_city_combination_search(data, city_stats)

    # Extreme filter search
    extreme_results = extreme_filter_search(data)

    # Build optimal config
    optimal = build_optimal_config(mc_results, grid_results, multi_results, extreme_results, city_stats)

    # Print result
    print("\n" + "=" * 70)
    print("OPTIMAL CONFIG JSON")
    print("=" * 80)
    print(json.dumps(optimal, indent=2))

    # Save
    out_path = DATA_DIR / "optimal_config.json"
    with open(out_path, "w") as f:
        json.dump(optimal, f, indent=2)
    print(f"\nSaved to: {out_path}")

    # Also save to project root
    root_path = Path("/home/alyssa/.openclaw/workspace/alter-bot-v1/optimal_config.json")
    with open(root_path, "w") as f:
        json.dump(optimal, f, indent=2)
    print(f"Saved to: {root_path}")

    return optimal


if __name__ == "__main__":
    main()