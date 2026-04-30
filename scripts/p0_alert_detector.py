#!/usr/bin/env python3
"""
Alter-Bot P0 Alert Detector
============================
Runs as a cron job every 15 minutes.
Checks for P0 conditions that need immediate fixing:
  1. Portfolio drawdown > 30% → alert
  2. City data error cascade (actual=0.0°C or NULL_TEMP_SENTINEL)
  3. Circuit breaker triggered (city_data_error_count > 3 for any city)
  4. Balance below safety threshold ($300 = paper trading danger zone)

If any P0 condition found → writes structured alert for auto-route to Turing.
"""

import json
import os
from pathlib import Path
from datetime import datetime

# Paths
BOT_DIR = Path.home() / ".openclaw" / "workspace" / "alter-bot-v1"
DATA_DIR = BOT_DIR / "data"
STATE_FILE = DATA_DIR / "state.json"
CITY_ERRORS_FILE = DATA_DIR / "city_error_history.json"
PORTFOLIO_ALERTS_FILE = DATA_DIR / "portfolio_alerts.json"
P0_ALERT_FILE = DATA_DIR / "p0_alerts.json"
CONFIG_FILE = BOT_DIR / "config.json"

# Thresholds
SAFETY_BALANCE = 300.0
CIRCUIT_BREAK_THRESHOLD = 3
MAX_DRAWDOWN_PCT = 0.30

def load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}

def check_balance_safety():
    """Check if balance is below safety threshold."""
    state = load_json(STATE_FILE, {})
    balance = state.get("balance", 0)
    if balance < SAFETY_BALANCE:
        return {
            "type": "BALANCE_SAFETY",
            "severity": "P0",
            "balance": balance,
            "safety_threshold": SAFETY_BALANCE,
            "message": f"Balance ${balance:.2f} is below safety threshold ${SAFETY_BALANCE}. Paper trading in danger zone.",
            "timestamp": datetime.now().isoformat(),
        }
    return None

def check_portfolio_drawdown():
    """Check if portfolio has triggered a drawdown alert."""
    state = load_json(STATE_FILE, {})
    balance = state.get("balance", 0)
    peak = state.get("peak_balance", 0)
    
    if peak <= 0:
        return None
    
    drawdown = (peak - balance) / peak
    if drawdown >= MAX_DRAWDOWN_PCT:
        return {
            "type": "PORTFOLIO_DRAWDOWN",
            "severity": "P0",
            "balance": balance,
            "peak_balance": peak,
            "drawdown_pct": round(drawdown * 100, 1),
            "message": f"Portfolio drawdown {drawdown*100:.1f}% — peak ${peak:.2f} → now ${balance:.2f}",
            "timestamp": datetime.now().isoformat(),
        }
    return None

def check_city_circuit_breakers():
    """Check for cities that have hit circuit breaker threshold."""
    state = load_json(STATE_FILE, {})
    error_counts = state.get("city_data_error_count", {})
    
    tripped = []
    for city, count in error_counts.items():
        if count >= CIRCUIT_BREAK_THRESHOLD:
            tripped.append({"city": city, "error_count": count, "threshold": CIRCUIT_BREAK_THRESHOLD})
    
    if not tripped:
        return None
    
    return {
        "type": "CITY_CIRCUIT_BREAKER",
        "severity": "P0",
        "tripped_cities": tripped,
        "message": f"Circuit breaker triggered for {len(tripped)} city(s): {', '.join(c['city'] for c in tripped)}",
        "timestamp": datetime.now().isoformat(),
    }

def check_actual_null_cascade():
    """Check for actual=0.0°C cascade in recent errors."""
    errors = load_json(CITY_ERRORS_FILE, {"cities": {}})
    recent_threshold_hours = 24
    
    cascade_cities = []
    now = datetime.now()
    
    for city, data in errors.get("cities", {}).items():
        samples = data.get("samples", [])
        recent_nulls = 0
        for s in samples[-10:]:  # last 10 samples
            ts_str = s.get("timestamp", "")
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str)
                    age_hours = (now - ts).total_seconds() / 3600
                    if age_hours > recent_threshold_hours:
                        continue
                except Exception:
                    pass
            if s.get("actual") in (0.0, 0, None) or s.get("actual") == "NULL_TEMP_SENTINEL":
                recent_nulls += 1
        
        if recent_nulls >= 3:
            cascade_cities.append({"city": city, "null_count": recent_nulls})
    
    if not cascade_cities:
        return None
    
    return {
        "type": "ACTUAL_NULL_CASCADE",
        "severity": "P0",
        "cascade_cities": cascade_cities,
        "message": f"actual=0.0°C cascade detected in {len(cascade_cities)} city(s): {', '.join(c['city'] for c in cascade_cities)}",
        "timestamp": datetime.now().isoformat(),
    }

def load_config():
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def check_avoid_list_gaps():
    """Check if problematic cities are missing from avoid list."""
    config = load_config()
    avoid = config.get("city_tiers", {}).get("avoid", [])
    
    state = load_json(STATE_FILE, {})
    error_counts = state.get("city_data_error_count", {})
    
    missing_avoid = []
    for city, count in error_counts.items():
        if count >= 2 and city not in avoid:
            missing_avoid.append(city)
    
    if not missing_avoid:
        return None
    
    return {
        "type": "AVOID_LIST_GAP",
        "severity": "P1",  # P1, not P0 — can wait for scheduled fix
        "missing_cities": missing_avoid,
        "message": f"Cities with errors not in avoid list: {', '.join(missing_avoid)}",
        "timestamp": datetime.now().isoformat(),
    }

def main():
    alerts = []
    
    checks = [
        check_balance_safety,
        check_portfolio_drawdown,
        check_city_circuit_breakers,
        check_actual_null_cascade,
        check_avoid_list_gaps,
    ]
    
    for check in checks:
        result = check()
        if result:
            alerts.append(result)
    
    if not alerts:
        print(f"[{datetime.now().isoformat()}] P0 check: OK — no alerts")
        return
    
    # Load existing alerts, filter out duplicates from same hour
    existing = load_json(P0_ALERT_FILE, [])
    new_alerts = []
    for alert in alerts:
        # Deduplicate: skip if same type+city in last 2 hours
        is_duplicate = False
        for ex in existing[-10:]:
            if ex.get("type") == alert.get("type") and ex.get("timestamp"):
                try:
                    ex_time = datetime.fromisoformat(ex["timestamp"])
                    age_hours = (datetime.now() - ex_time).total_seconds() / 3600
                    if age_hours < 2:
                        is_duplicate = True
                        break
                except Exception:
                    pass
        if not is_duplicate:
            new_alerts.append(alert)
    
    if new_alerts:
        existing.extend(new_alerts)
        # Keep last 50 alerts
        existing = existing[-50:]
        with open(P0_ALERT_FILE, "w") as f:
            json.dump(existing, f, indent=2)
        
        for alert in new_alerts:
            print(f"\n🚨 [P0 ALERT] {alert['type']}: {alert['message']}\n")
        
        print(f"[{datetime.now().isoformat()}] P0 check: {len(new_alerts)} new alert(s) written to {P0_ALERT_FILE}")
    else:
        print(f"[{datetime.now().isoformat()}] P0 check: OK — no new alerts (all duplicates)")

if __name__ == "__main__":
    main()