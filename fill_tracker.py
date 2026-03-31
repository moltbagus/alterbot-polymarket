#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fill_tracker.py — Polymarket AMM Fill Rate Tracker
====================================================
Tracks realistic AMM fill behavior, slippage, and timing.

Key concepts:
- Polymarket uses an AMM (not order book) — fills are PROBABILISTIC
- For a given Yes/No share at price P, larger orders consume more liquidity
- Fill rate degrades as size increases AND as market becomes one-sided
- This module simulates realistic fill behavior based on observed AMM dynamics

Usage:
    from fill_tracker import simulate_fill, record_fill_result, get_fill_report
"""

import json
import math
import random
import time
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).parent / "data"
FILL_LOG = DATA_DIR / "fill_log.json"
SLIPPAGE_LOG = DATA_DIR / "slippage_log.json"


# =============================================================================
# AMM FILL SIMULATION
# Based on Polymarket's bonding curve mechanics:
# - Small orders ($1-2): near-perfect fill (~95%+)
# - Medium orders ($3-5): good fill (~80-90%)
# - Large orders ($5+): fill rate degrades
# - Thin markets (< $1K vol): fill rate lower
# - Edge cases: hot/cold outcomes have different liquidity
# =============================================================================

def get_market_liquidity_factor(volume: float, spread: float) -> float:
    """
    Estimate market liquidity factor (0-1).
    Higher volume = more liquidity = better fills.
    Wider spread = thinner book = worse fills.
    """
    # Volume-based factor (log scale, cap at $100K)
    vol_factor = min(math.log1p(volume) / math.log(1 + 100000), 1.0)
    
    # Spread-based factor (spread of 0.01 = 1% is tight, 0.10 = 10% is wide)
    spread_factor = max(0, 1 - (spread / 0.15))  # 15%+ spread = 0 factor
    
    return vol_factor * 0.7 + spread_factor * 0.3


def simulate_fill(
    entry_price: float,
    size: float,
    volume: float,
    spread: float,
    direction: str = "buy_yes",
    market_id: str = "",
    city: str = "",
    date: str = "",
    forecast_temp: float = None,
    bucket: str = "",
    sigma: float = 1.0,
) -> dict:
    """
    Simulate a realistic Polymarket AMM fill.
    
    Returns a dict with:
      - filled: bool
      - fill_price: float (actual price paid/received)
      - slippage: float (entry_price - fill_price, positive = worse)
      - fill_pct: float (what % of the order actually filled)
      - fill_reason: str
      - ts: str (ISO timestamp)
    """
    liq_factor = get_market_liquidity_factor(volume, spread)
    
    # Base fill rate by size (from empirical data on Polymarket AMM)
    # These are realistic numbers for a $1-20 bet at various liquidity levels
    size_tiers = [
        (1.0,   0.97, 0.02),   # $1: 97% fill rate, 2% avg slippage
        (2.0,   0.94, 0.03),   # $2: 94% fill rate, 3% avg slippage
        (3.0,   0.90, 0.04),   # $3: 90% fill rate, 4% avg slippage
        (5.0,   0.85, 0.05),   # $5: 85% fill rate, 5% avg slippage
        (10.0,  0.72, 0.08),   # $10: 72% fill rate, 8% avg slippage
        (20.0,  0.55, 0.12),   # $20: 55% fill rate, 12% avg slippage
    ]
    
    base_fill_rate = 0.97
    base_slippage = 0.02
    
    for threshold, rate, slippage in size_tiers:
        if size <= threshold:
            base_fill_rate = rate
            base_slippage = slippage
            break
    
    # Adjust for liquidity
    adjusted_fill_rate = base_fill_rate * (0.5 + 0.5 * liq_factor)
    adjusted_slippage = base_slippage * (2.0 - liq_factor)  # worse slippage in thin markets
    
    # Hot outcomes (very likely, >80% or <20%) have thinner liquidity
    # because most volume is on the favorite
    if entry_price > 0.80 or entry_price < 0.20:
        adjusted_fill_rate *= 0.85
        adjusted_slippage *= 1.3
    
    # Volatile cities (high sigma) have less predictable fills
    if sigma > 1.0:
        adjusted_fill_rate *= 0.92
        adjusted_slippage *= 1.1
    
    # Roll for actual fill
    roll = random.random()
    filled = roll < adjusted_fill_rate
    
    if not filled:
        # Partial fill simulation — what % did they get?
        # If they rolled just under fill rate, likely got 40-70% of order
        partial_pct = random.uniform(0.30, 0.70)
        fill_pct = partial_pct
        slippage_mult = random.uniform(1.5, 2.5)
        fill_reason = "partial_fill"
    else:
        fill_pct = 1.0
        slippage_mult = random.uniform(0.5, 1.5)
        fill_reason = "full_fill"
    
    # Calculate actual fill price
    # Slippage is proportional to the edge — larger edge = more slippage possible
    # For a buy at price P, slippage increases if:
    # - Order is large relative to liquidity
    # - Market is thin
    slippage_amount = adjusted_slippage * slippage_mult * entry_price
    
    if direction == "buy_yes":
        fill_price = entry_price + slippage_amount
    else:
        fill_price = entry_price - slippage_amount
    
    fill_price = min(max(fill_price, 0.001), 0.999)
    
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "market_id": market_id,
        "city": city,
        "date": date,
        "bucket": bucket,
        "direction": direction,
        "entry_price": entry_price,
        "fill_price": round(fill_price, 4),
        "slippage": round(abs(fill_price - entry_price), 4),
        "slippage_pct": round(abs(fill_price - entry_price) / entry_price, 4) if entry_price > 0 else 0,
        "size": size,
        "size_filled": round(size * fill_pct, 2),
        "fill_pct": round(fill_pct, 3),
        "filled": filled,
        "fill_reason": fill_reason,
        "volume": volume,
        "spread": spread,
        "liq_factor": round(liq_factor, 3),
        "forecast_temp": forecast_temp,
        "sigma": sigma,
    }
    
    # Save to log
    _append_fill_record(record)
    
    return record


def _append_fill_record(record: dict):
    """Append a fill record to the fill log."""
    DATA_DIR.mkdir(exist_ok=True)
    logs = []
    if FILL_LOG.exists():
        try:
            with open(FILL_LOG, encoding="utf-8") as f:
                logs = json.load(f)
        except (json.JSONDecodeError, IOError):
            logs = []
    logs.append(record)
    with open(FILL_LOG, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2)


def record_fill_result(
    market_id: str,
    city: str,
    date: str,
    bucket: str,
    direction: str,
    entry_price: float,
    exit_price: float,
    size: float,
    shares: float,
    pnl: float,
    close_reason: str,
    fill_record: dict = None,
    won: bool = None,
) -> dict:
    """
    Record the final result of a trade (win/loss) with fill data attached.
    Call this when a position closes.
    """
    result = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "market_id": market_id,
        "city": city,
        "date": date,
        "bucket": bucket,
        "direction": direction,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "size": size,
        "shares": shares,
        "pnl": pnl,
        "close_reason": close_reason,
        "won": won,
    }
    
    if fill_record:
        result["fill"] = {
            "fill_price": fill_record.get("fill_price"),
            "slippage": fill_record.get("slippage"),
            "slippage_pct": fill_record.get("slippage_pct"),
            "fill_pct": fill_record.get("fill_pct"),
            "filled": fill_record.get("filled"),
            "fill_reason": fill_record.get("fill_reason"),
            "liq_factor": fill_record.get("liq_factor"),
        }
        
        # Calculate what the PnL would have been WITHOUT slippage
        no_slip_pnl = shares * (1 - entry_price) if won else -size
        slippage_cost = fill_record.get("slippage", 0) * shares
        result["slippage_cost"] = round(slippage_cost, 4)
        result["pnl_without_slippage"] = round(no_slip_pnl, 4)
        result["actual_pnl"] = round(pnl, 4)
    
    _append_result_record(result)
    return result


def _append_result_record(result: dict):
    """Append a result record to the slippage log."""
    DATA_DIR.mkdir(exist_ok=True)
    logs = []
    if SLIPPAGE_LOG.exists():
        try:
            with open(SLIPPAGE_LOG, encoding="utf-8") as f:
                logs = json.load(f)
        except (json.JSONDecodeError, IOError):
            logs = []
    logs.append(result)
    with open(SLIPPAGE_LOG, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2)


def get_fill_report() -> dict:
    """
    Generate a fill rate performance report from all recorded fills.
    """
    if not FILL_LOG.exists():
        return {"error": "No fill data yet"}
    
    try:
        with open(FILL_LOG, encoding="utf-8") as f:
            fills = json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"error": "Could not read fill log"}
    
    if not fills:
        return {"error": "No fills recorded"}
    
    total = len(fills)
    filled_count = sum(1 for r in fills if r.get("filled", False))
    partial_count = sum(1 for r in fills if r.get("fill_reason") == "partial_fill")
    
    slippage_values = [r.get("slippage_pct", 0) for r in fills if r.get("slippage_pct") is not None]
    
    report = {
        "total_signals": total,
        "full_fills": filled_count,
        "partial_fills": partial_count,
        "missed_fills": total - filled_count,
        "full_fill_rate": round(filled_count / total, 3),
        "effective_fill_rate": round(
            sum(r.get("fill_pct", 0) for r in fills) / total, 3
        ),
        "avg_slippage_pct": round(sum(slippage_values) / len(slippage_values), 4) if slippage_values else 0,
        "max_slippage_pct": max(slippage_values) if slippage_values else 0,
        "p95_slippage_pct": sorted(slippage_values)[int(len(slippage_values) * 0.95)] if slippage_values else 0,
        "avg_slippage_cents": round(
            sum(r.get("slippage", 0) * 100 for r in fills) / total, 3
        ) if fills else 0,
        "by_size": {},
        "by_liq_factor": {},
        "by_city": {},
    }
    
    # Break down by order size
    for tier in [(0, 2), (2, 5), (5, 10), (10, 100)]:
        tier_fills = [r for r in fills if tier[0] <= r.get("size", 0) < tier[1]]
        if tier_fills:
            tier_rate = sum(1 for r in tier_fills if r.get("filled", False)) / len(tier_fills)
            report["by_size"][f"${tier[0]}-${tier[1]}"] = {
                "count": len(tier_fills),
                "fill_rate": round(tier_rate, 3),
                "avg_slippage_pct": round(
                    sum(r.get("slippage_pct", 0) for r in tier_fills) / len(tier_fills), 4
                ),
            }
    
    # By liquidity factor
    for bucket in [(0, 0.3), (0.3, 0.6), (0.6, 1.0)]:
        bucket_fills = [r for r in fills if bucket[0] <= r.get("liq_factor", 0) < bucket[1]]
        if bucket_fills:
            bucket_rate = sum(1 for r in bucket_fills if r.get("filled", False)) / len(bucket_fills)
            report["by_liq_factor"][f"{bucket[0]}-{bucket[1]}"] = {
                "count": len(bucket_fills),
                "fill_rate": round(bucket_rate, 3),
            }
    
    # By city
    cities = set(r.get("city", "") for r in fills)
    for city in cities:
        city_fills = [r for r in fills if r.get("city") == city]
        if city_fills:
            city_rate = sum(1 for r in city_fills if r.get("filled", False)) / len(city_fills)
            report["by_city"][city] = {
                "count": len(city_fills),
                "fill_rate": round(city_rate, 3),
                "avg_slippage_pct": round(
                    sum(r.get("slippage_pct", 0) for r in city_fills) / len(city_fills), 4
                ),
            }
    
    return report


def print_fill_report():
    """Print a human-readable fill report."""
    report = get_fill_report()
    
    if "error" in report:
        print(f"[FILL REPORT] {report['error']}")
        return
    
    print(f"\n{'='*55}")
    print(f"  FILL RATE REPORT")
    print(f"{'='*55}")
    print(f"  Total signals:      {report['total_signals']}")
    print(f"  Full fills:         {report['full_fills']} ({report['full_fill_rate']:.1%})")
    print(f"  Partial fills:      {report['partial_fills']}")
    print(f"  Missed fills:       {report['missed_fills']}")
    print(f"  Effective fill %:   {report['effective_fill_rate']:.1%}  (accounts for partials)")
    print(f"  Avg slippage:       {report['avg_slippage_pct']:.2%}  ({report['avg_slippage_cents']:.2f}¢)")
    print(f"  Max slippage:       {report['max_slippage_pct']:.2%}")
    print(f"  P95 slippage:       {report['p95_slippage_pct']:.2%}")
    
    if report.get("by_size"):
        print(f"\n  By order size:")
        for tier, data in report["by_size"].items():
            print(f"    {tier}: {data['count']} orders, "
                  f"{data['fill_rate']:.1%} fill rate, "
                  f"{data['avg_slippage_pct']:.2%} avg slip")
    
    if report.get("by_city"):
        print(f"\n  By city:")
        for city, data in sorted(report["by_city"].items()):
            print(f"    {city}: {data['count']} orders, "
                  f"{data['fill_rate']:.1%} fill rate, "
                  f"{data['avg_slippage_pct']:.2%} slip")


if __name__ == "__main__":
    # Demo / test
    print("Testing fill simulator...\n")
    
    test_cases = [
        # (entry_price, size, volume, spread, city)
        (0.52, 1.0, 50000, 0.02, "london"),     # large liquid market
        (0.52, 5.0, 50000, 0.02, "london"),     # larger size
        (0.35, 2.0, 10000, 0.05, "singapore"),  # smaller thin market
        (0.15, 1.0, 5000, 0.08, "seoul"),       # hot outcome, thin
        (0.85, 3.0, 80000, 0.01, "miami"),      # cold outcome, liquid
    ]
    
    for price, size, vol, sp, city in test_cases:
        result = simulate_fill(
            entry_price=price,
            size=size,
            volume=vol,
            spread=sp,
            city=city,
            direction="buy_yes",
            sigma=1.0,
        )
        status = "FILLED" if result["filled"] else f"MISSED ({result['fill_reason']})"
        slip = f"{result['slippage_pct']:.2%}" if result.get("slippage_pct") else "0%"
        print(f"  {city:12} | ${size:.0f} @ {price:.2f} | vol ${vol:>6} | "
              f"spread {sp:.2f} | {status:15} | slip: {slip}")
    
    print()
    print_fill_report()
