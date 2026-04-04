#!/usr/bin/env python3
"""
Focused Monte Carlo Sweep - asian_cities_365day_backtest + all_polymarket_predictions
Reports every 30 seconds. Outputs optimal min_ev, max_price, city_weights, conviction, sigma.
"""

import json
import random
import numpy as np
import csv
import time
import copy
from pathlib import Path
from collections import defaultdict

random.seed(42)
np.random.seed(42)

DATA_DIR = Path("/home/alyssa/.openclaw/workspace/alter-bot-v1/data")
REPORT_INTERVAL = 30  # seconds

# ============================================================
# LOAD ONLY THE TWO REQUESTED DATA SOURCES
# ============================================================

def load_two_sources():
    """Load only asian_cities_365day_backtest + all_polymarket_predictions."""
    all_rows = []

    # 1. all_polymarket_predictions.csv
    with open(DATA_DIR / "all_polymarket_predictions.csv") as f:
        for row in csv.DictReader(f):
            try:
                all_rows.append({
                    "source": "polymarket_predictions",
                    "city": row["city"].lower(),
                    "date": row["pred_date"],
                    "predicted": float(row["predicted_temp"]) if row["predicted_temp"] else 0,
                    "actual": float(row["actual_temp"]) if row["actual_temp"] else 0,
                    "confidence": 0.80,
                    "correct": row["correct"] == "True",
                    "win": int(row["win"]) if row["win"] else 0,
                    "bucket_win": row["correct"] == "True",
                    "daily_win": row["correct"] == "True",
                })
            except (ValueError, KeyError):
                pass

    # 2. asian_cities_365day_backtest.csv
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

    return all_rows


# ============================================================
# SIMULATION ENGINE
# ============================================================

def simulate_trade(row, config):
    """Determine if a row would generate a trade and whether it wins."""
    city = row["city"]
    confidence = row.get("confidence", 0)
    bucket_win = row.get("bucket_win", False)

    # City filter
    blocked = config.get("blocked_cities", [])
    if city in blocked:
        return False, False

    allowed = config.get("allowed_cities", None)
    if allowed and city not in allowed:
        return False, False

    # City tier filter
    if config.get("tier_1_only", False):
        tier1_elite = config.get("tier_1_elite", [])
        if city not in tier1_elite:
            return False, False

    # City weights - scale confidence
    city_weights = config.get("city_weights", {})
    city_weight = city_weights.get(city, city_weights.get("default", 1.0))
    weighted_conf = confidence * city_weight
    effective_conf = min(weighted_conf, 1.0)  # cap at 1.0

    # Per-city confidence override
    city_min_conf = config.get("city_min_conf", {})
    min_conf = city_min_conf.get(city, config.get("min_confidence", 0.5))

    if effective_conf < min_conf:
        return False, False

    # Conviction filter: conviction = confidence * sigma
    sigma = config.get("sigma", 10.0)
    conviction = effective_conf * sigma
    min_conviction = config.get("min_conviction", 5.0)
    if conviction < min_conviction:
        return False, False

    # EV filter
    ev = row.get("ev", 0)
    min_ev = config.get("min_ev", 0.1)
    if ev > 0 and ev < min_ev:
        return False, False

    # Price filter
    entry_price = row.get("entry_price", 0)
    max_price = config.get("max_price", 0.45)
    if entry_price > 0 and entry_price > max_price:
        return False, False

    won = bucket_win
    return True, won


def evaluate_config(config, data):
    """Evaluate a config against all historical data."""
    wins = losses = trades = 0
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
# MONTE CARLO SEARCH
# ============================================================

def monte_carlo_search(data, n_iterations=50000):
    """Broad Monte Carlo search with city_weights and sigma."""
    print(f"\n{'='*70}")
    print(f"MONTE CARLO SEARCH ({n_iterations:,} iterations, report every {REPORT_INTERVAL}s)")
    print(f"{'='*70}")

    all_cities = sorted(set(row["city"] for row in data))
    print(f"Cities in dataset: {all_cities}")
    print(f"Total rows: {len(data)}")

    # City tier sets
    tier_options = [
        None,  # all cities
        ["singapore"],
        ["paris"],
        ["london"],
        ["singapore", "paris"],
        ["singapore", "london"],
        ["singapore", "paris", "london"],
        ["paris", "london"],
        ["tokyo"],
        ["miami"],
        ["atlanta"],
        ["sao-paulo"],
    ]

    blocked_options = [
        [],
        ["taipei", "hong-kong", "seoul"],
        ["shanghai", "taipei", "hong-kong", "seoul"],
    ]

    results = []
    start_time = time.time()
    next_report = start_time + REPORT_INTERVAL

    for i in range(n_iterations):
        # Sample config
        cfg = {
            "min_confidence": round(random.uniform(0.50, 0.95), 2),
            "min_ev": round(random.uniform(0.0, 0.5), 2),
            "min_conviction": round(random.uniform(3.0, 10.0), 1),
            "sigma": round(random.uniform(5.0, 15.0), 1),
            "conviction_mult": round(random.uniform(8.0, 12.0), 1),  # legacy alias
            "max_price": round(random.uniform(0.20, 0.50), 2),
            "allowed_cities": random.choice(tier_options),
            "blocked_cities": random.choice(blocked_options),
            "tier_1_only": random.random() > 0.5,
            "tier_1_elite": ["singapore", "paris", "london"],
            "city_min_conf": {},
            "city_weights": {},  # will be populated
        }

        # Per-city min_conf overrides
        if random.random() > 0.4 and cfg["allowed_cities"]:
            for c in cfg["allowed_cities"][:2]:
                cfg["city_min_conf"][c] = round(random.uniform(0.55, 0.85), 2)

        # City weights: sample a dict
        weight_strategy = random.choice(["uniform", "tiered", "selective", "flat"])
        if weight_strategy == "uniform":
            cfg["city_weights"] = {c: 1.0 for c in all_cities}
            cfg["city_weights"]["default"] = 1.0
        elif weight_strategy == "tiered":
            cfg["city_weights"] = {
                "singapore": round(random.uniform(1.0, 1.3), 2),
                "paris": round(random.uniform(0.9, 1.2), 2),
                "london": round(random.uniform(0.9, 1.2), 2),
                "tokyo": round(random.uniform(0.8, 1.1), 2),
                "miami": round(random.uniform(0.8, 1.1), 2),
                "atlanta": round(random.uniform(0.7, 1.0), 2),
                "sao-paulo": round(random.uniform(0.7, 1.0), 2),
                "default": 0.8,
            }
        elif weight_strategy == "selective":
            top = random.sample(all_cities, min(random.randint(1, 4), len(all_cities)))
            cfg["city_weights"] = {c: round(random.uniform(1.1, 1.4), 2) if c in top
                                   else round(random.uniform(0.6, 0.9), 2) for c in all_cities}
            cfg["city_weights"]["default"] = 0.7
        else:  # flat
            v = round(random.uniform(0.8, 1.2), 2)
            cfg["city_weights"] = {c: v for c in all_cities}
            cfg["city_weights"]["default"] = v

        wr, trades, wins, losses = evaluate_config(cfg, data)

        if trades >= 5:
            results.append({
                "config": copy.deepcopy(cfg),
                "win_rate": wr,
                "trades": trades,
                "wins": wins,
                "losses": losses,
            })

        # Time-based reporting
        now = time.time()
        if now >= next_report:
            elapsed = now - start_time
            rate = (i + 1) / elapsed
            best_wr = results[0]["win_rate"]*100 if results else 0
            best_trades = results[0]["trades"] if results else 0
            ninety_plus = sum(1 for r in results if r["win_rate"] >= 0.90)
            print(f"  [{elapsed:.0f}s] iter={i+1:,} rate={rate:.0f}/s | "
                  f"configs={len(results)} | best_WR={best_wr:.1f}% ({best_trades} trades) | "
                  f">=90%: {ninety_plus}")
            next_report = now + REPORT_INTERVAL

    results.sort(key=lambda x: (x["win_rate"], x["trades"]), reverse=True)
    return results, time.time() - start_time


def extreme_filter_search(data, n_iterations=20000):
    """Deeper search around the most promising parameter regions."""
    print(f"\n{'='*70}")
    print(f"EXTREME FILTER SEARCH ({n_iterations:,} iterations)")
    print(f"{'='*70}")

    all_cities = sorted(set(row["city"] for row in data))
    results = []
    start_time = time.time()
    next_report = start_time + REPORT_INTERVAL

    for i in range(n_iterations):
        # Focus on high-conviction, high-sigma region
        sigma = round(random.uniform(10.0, 15.0), 1)
        min_conviction = round(random.uniform(6.0, 10.0), 1)
        min_conf = round(random.uniform(0.75, 0.95), 2)
        max_price = round(random.uniform(0.25, 0.40), 2)
        min_ev = round(random.uniform(0.0, 0.3), 2)

        # City weight: Singapore boosted
        sw = {}
        for c in all_cities:
            if c == "singapore":
                sw[c] = round(random.uniform(1.2, 1.5), 2)
            elif c in ["paris", "london"]:
                sw[c] = round(random.uniform(1.0, 1.3), 2)
            else:
                sw[c] = round(random.uniform(0.6, 1.0), 2)
        sw["default"] = 0.8

        # Allowed: top cities
        allowed_opts = [
            ["singapore"],
            ["singapore", "paris"],
            ["singapore", "london"],
            ["singapore", "paris", "london"],
            ["singapore", "tokyo"],
            all_cities,
        ]

        cfg = {
            "min_confidence": min_conf,
            "min_ev": min_ev,
            "min_conviction": min_conviction,
            "sigma": sigma,
            "conviction_mult": 10.0,
            "max_price": max_price,
            "allowed_cities": random.choice(allowed_opts),
            "blocked_cities": [],
            "tier_1_only": False,
            "tier_1_elite": ["singapore", "paris", "london"],
            "city_min_conf": {},
            "city_weights": sw,
        }

        # Per-city overrides for top cities
        if random.random() > 0.5:
            for c in cfg["allowed_cities"][:2] if cfg["allowed_cities"] else []:
                cfg["city_min_conf"][c] = round(random.uniform(0.7, 0.9), 2)

        wr, trades, wins, losses = evaluate_config(cfg, data)

        if trades >= 5:
            results.append({
                "config": copy.deepcopy(cfg),
                "win_rate": wr,
                "trades": trades,
                "wins": wins,
                "losses": losses,
            })

        now = time.time()
        if now >= next_report:
            elapsed = now - start_time
            best_wr = results[0]["win_rate"]*100 if results else 0
            n90 = sum(1 for r in results if r["win_rate"] >= 0.90)
            print(f"  [{elapsed:.0f}s] iter={i+1:,} | configs={len(results)} | "
                  f"best_WR={best_wr:.1f}% | >=90%: {n90}")
            next_report = now + REPORT_INTERVAL

    results.sort(key=lambda x: (x["win_rate"], x["trades"]), reverse=True)
    return results


# ============================================================
# BUILD OPTIMAL OUTPUT
# ============================================================

def build_output(mc_results, ext_results):
    """Build the optimal config output."""
    # Combine and find best
    all_results = [(r, "mc") for r in mc_results] + [(r, "ext") for r in ext_results]
    all_results.sort(key=lambda x: (x[0]["win_rate"], x[0]["trades"]), reverse=True)

    # Filter >= 90%
    winners = [r for r in all_results if r[0]["win_rate"] >= 0.90]
    best = winners[0] if winners else all_results[0]

    cfg = best[0]["config"]
    wr = best[0]["win_rate"]
    trades = best[0]["trades"]
    wins = best[0]["wins"]
    losses = best[0]["losses"]

    # Extract city weights dict
    city_weights_raw = cfg.get("city_weights", {})

    # Build city_weights in expected format
    city_weights_out = {}
    for k, v in city_weights_raw.items():
        if k != "default":
            city_weights_out[k] = v
    city_weights_out["default"] = city_weights_raw.get("default", 1.0)

    # Build optimal output
    optimal = {
        "optimal_params": {
            "min_ev": cfg["min_ev"],
            "max_price": cfg["max_price"],
            "city_weights": city_weights_out,
            "conviction_mult": cfg["conviction_mult"],
            "sigma": cfg["sigma"],
            "min_confidence": cfg["min_confidence"],
            "min_conviction": cfg["min_conviction"],
        },
        "backtest": {
            "win_rate": wr,
            "trades": trades,
            "wins": wins,
            "losses": losses,
            "source": best[1],
        },
        "top_configs": []
    }

    # Top 10 configs for reference
    for r, src in all_results[:10]:
        c = r["config"]
        city_weights_raw = c.get("city_weights", {})
        cw = {k: v for k, v in city_weights_raw.items() if k != "default"}
        cw["default"] = city_weights_raw.get("default", 1.0)
        optimal["top_configs"].append({
            "win_rate": r["win_rate"],
            "trades": r["trades"],
            "source": src,
            "min_ev": c["min_ev"],
            "max_price": c["max_price"],
            "city_weights": cw,
            "conviction_mult": c["conviction_mult"],
            "sigma": c["sigma"],
            "min_confidence": c["min_confidence"],
            "min_conviction": c["min_conviction"],
            "allowed_cities": c["allowed_cities"],
            "city_min_conf": c.get("city_min_conf", {}),
        })

    return optimal


# ============================================================
# MAIN
# ============================================================

def main():
    print("="*70)
    print("MONTE CARLO PARAMETER SWEEP")
    print("Sources: asian_cities_365day_backtest.csv + all_polymarket_predictions.csv")
    print("="*70)

    # Load data
    print("\nLoading data...")
    data = load_two_sources()
    print(f"Total rows: {len(data)}")

    # Quick data stats
    by_city = defaultdict(lambda: defaultdict(int))
    for row in data:
        by_city[row["city"]][row.get("bucket_win", False)] += 1
    print("\nCity win rates (raw bucket_win):")
    for city in sorted(by_city.keys()):
        wins = by_city[city][True]
        total = by_city[city][True] + by_city[city][False]
        wr = wins / total if total > 0 else 0
        print(f"  {city:15s}: {wins}/{total} = {wr*100:.1f}%")

    # Phase 1: Broad Monte Carlo
    print("\n[Phase 1] Broad Monte Carlo search...")
    mc_results, mc_time = monte_carlo_search(data, n_iterations=50000)

    print(f"\n  Phase 1 complete in {mc_time:.1f}s")
    print(f"  Total valid configs: {len(mc_results)}")
    n90_mc = sum(1 for r in mc_results if r["win_rate"] >= 0.90)
    print(f"  Configs with >= 90% WR: {n90_mc}")
    if mc_results:
        print(f"  Best WR: {mc_results[0]['win_rate']*100:.1f}% ({mc_results[0]['wins']}/{mc_results[0]['trades']})")
        print("  Top 5:")
        for i, r in enumerate(mc_results[:5]):
            print(f"    {i+1}. WR={r['win_rate']*100:.1f}% ({r['wins']}/{r['trades']}) | "
                  f"min_ev={r['config']['min_ev']} max_price={r['config']['max_price']} "
                  f"sigma={r['config']['sigma']} cities={r['config']['allowed_cities']}")

    # Phase 2: Extreme filter search around best regions
    print("\n[Phase 2] Extreme filter search around promising regions...")
    ext_results = extreme_filter_search(data, n_iterations=20000)

    n90_ext = sum(1 for r in ext_results if r["win_rate"] >= 0.90)
    print(f"\n  Phase 2 complete")
    print(f"  Total valid configs: {len(ext_results)}")
    print(f"  Configs with >= 90% WR: {n90_ext}")
    if ext_results:
        print(f"  Best WR: {ext_results[0]['win_rate']*100:.1f}% ({ext_results[0]['wins']}/{ext_results[0]['trades']})")
        print("  Top 5:")
        for i, r in enumerate(ext_results[:5]):
            print(f"    {i+1}. WR={r['win_rate']*100:.1f}% ({r['wins']}/{r['trades']}) | "
                  f"min_ev={r['config']['min_ev']} max_price={r['config']['max_price']} "
                  f"sigma={r['config']['sigma']} cities={r['config']['allowed_cities']}")

    # Build final output
    print("\n" + "="*70)
    print("OPTIMAL CONFIG")
    print("="*70)
    optimal = build_output(mc_results, ext_results)

    print(json.dumps(optimal, indent=2))

    # Save
    out_path = DATA_DIR / "optimal_config.json"
    with open(out_path, "w") as f:
        json.dump(optimal, f, indent=2)
    print(f"\nSaved to: {out_path}")

    root_path = Path("/home/alyssa/.openclaw/workspace/alter-bot-v1/optimal_config.json")
    with open(root_path, "w") as f:
        json.dump(optimal, f, indent=2)
    print(f"Saved to: {root_path}")

    return optimal


if __name__ == "__main__":
    main()