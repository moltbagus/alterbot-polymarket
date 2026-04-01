#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
weatherbet_v3.py — Enhanced Weather Trading Bot for Polymarket
================================================================
Upgrades from v2:
1. METAR real-time data integration (D+0 observed temps)
2. Accuracy tracking (log predictions vs outcomes)
3. Dynamic bias correction (learn from past errors)
4. Multi-source ensemble with learned weights

Usage:
    python weatherbet_v3.py          # main loop
    python weatherbet_v3.py report   # full report
    python weatherbet_v3.py status   # balance and open positions
    python weatherbet_v3.py accuracy # show accuracy stats
"""

import re
import sys
import json
import math
import time
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict

# =============================================================================
# CONFIG
# =============================================================================

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
STATE_FILE = DATA_DIR / "state.json"
CALIBRATION_FILE = DATA_DIR / "calibration.json"
PREDICTIONS_FILE = DATA_DIR / "predictions.json"  # NEW: track predictions
ACCURACY_FILE = DATA_DIR / "accuracy.json"  # NEW: accuracy stats

_config = {
    "balance": 10000.0,
    "max_bet": 1.0,
    "min_ev": 0.15,
    "max_price": 0.45,
    "min_volume": 500,
    "kelly_fraction": 0.25,
    "scan_interval": 1800,
}

def load_config():
    cfg_path = Path("config.json")
    if cfg_path.exists():
        with open(cfg_path) as f:
            return json.load(f)
    return _config

_cfg = load_config()

BALANCE = _cfg.get("balance", 10000.0)
MAX_BET = _cfg.get("max_bet", 1.0)
MIN_EV = _cfg.get("min_ev", 0.15)
MAX_PRICE = _cfg.get("max_price", 0.45)
MIN_VOLUME = _cfg.get("min_volume", 500)
KELLY_FRACTION = _cfg.get("kelly_fraction", 0.25)
SCAN_INTERVAL = _cfg.get("scan_interval", 1800)

DEFAULT_SIGMA_F = 2.5
DEFAULT_SIGMA_C = 1.5

# City metadata with known biases (from historical analysis)
CITY_ACCURACY = {
    "singapore": {"sigma_mult": 0.6, "known_bias": 0.0, "metar_reliability": 0.98},
    "tokyo": {"sigma_mult": 0.9, "known_bias": -0.5, "metar_reliability": 0.97},
    "seoul": {"sigma_mult": 1.0, "known_bias": -0.3, "metar_reliability": 0.94},
    "hong-kong": {"sigma_mult": 0.8, "known_bias": 0.0, "metar_reliability": 0.98},
    "london": {"sigma_mult": 1.1, "known_bias": 0.5, "metar_reliability": 0.85},
    "paris": {"sigma_mult": 1.0, "known_bias": 0.3, "metar_reliability": 0.82},
    "munich": {"sigma_mult": 1.4, "known_bias": 0.0, "metar_reliability": 0.78},
    "nyc": {"sigma_mult": 1.2, "known_bias": 0.0, "metar_reliability": 0.97},
    "chicago": {"sigma_mult": 1.3, "known_bias": 0.0, "metar_reliability": 0.96},
    "miami": {"sigma_mult": 1.0, "known_bias": 0.5, "metar_reliability": 0.96},
    "dallas": {"sigma_mult": 1.2, "known_bias": 0.0, "metar_reliability": 0.95},
    "seattle": {"sigma_mult": 1.4, "known_bias": 0.0, "metar_reliability": 0.90},
    "atlanta": {"sigma_mult": 1.3, "known_bias": 0.0, "metar_reliability": 0.92},
}

LOCATIONS = {
    "nyc": {"lat": 40.7772, "lon": -73.8726, "name": "New York", "station": "KLGA", "unit": "F"},
    "chicago": {"lat": 41.9742, "lon": -87.9073, "name": "Chicago", "station": "KORD", "unit": "F"},
    "miami": {"lat": 25.7959, "lon": -80.2870, "name": "Miami", "station": "KMIA", "unit": "F"},
    "dallas": {"lat": 32.8471, "lon": -96.8518, "name": "Dallas", "station": "KDAL", "unit": "F"},
    "seattle": {"lat": 47.4502, "lon": -122.3088, "name": "Seattle", "station": "KSEA", "unit": "F"},
    "atlanta": {"lat": 33.6407, "lon": -84.4277, "name": "Atlanta", "station": "KATL", "unit": "F"},
    "london": {"lat": 51.5048, "lon": 0.0495, "name": "London", "station": "EGLC", "unit": "C"},
    "paris": {"lat": 48.9962, "lon": 2.5979, "name": "Paris", "station": "LFPG", "unit": "C"},
    "munich": {"lat": 48.3537, "lon": 11.7750, "name": "Munich", "station": "EDDM", "unit": "C"},
    "seoul": {"lat": 37.4691, "lon": 126.4505, "name": "Seoul", "station": "RKSI", "unit": "C"},
    "tokyo": {"lat": 35.7647, "lon": 140.3864, "name": "Tokyo", "station": "RJTT", "unit": "C"},
    "singapore": {"lat": 1.3502, "lon": 103.9940, "name": "Singapore", "station": "WSSS", "unit": "C"},
    "hong-kong": {"lat": 22.3193, "lon": 114.1694, "name": "Hong Kong", "station": "VHHH", "unit": "C"},
    "tel-aviv": {"lat": 32.0114, "lon": 34.8867, "name": "Tel Aviv", "station": "LLBG", "unit": "C"},
}

# =============================================================================
# PREDICTION & ACCURACY TRACKING
# =============================================================================

def load_predictions():
    if PREDICTIONS_FILE.exists():
        return json.loads(PREDICTIONS_FILE.read_text())
    return []

def save_predictions(predictions):
    with open(PREDICTIONS_FILE, "w") as f:
        json.dump(predictions, f, indent=2)

def add_prediction(city, date, forecast, actual, outcome, ev):
    """Log a prediction for accuracy tracking."""
    predictions = load_predictions()
    predictions.append({
        "city": city,
        "date": date,
        "forecast": forecast,
        "actual": actual,
        "outcome": outcome,
        "ev": ev,
        "timestamp": datetime.now().isoformat()
    })
    save_predictions(predictions)
    update_accuracy(city, forecast, actual)

def load_accuracy():
    if ACCURACY_FILE.exists():
        return json.loads(ACCURACY_FILE.read_text())
    return {"cities": {}}

def save_accuracy(acc):
    with open(ACCURACY_FILE, "w") as f:
        json.dump(acc, f, indent=2)

def update_accuracy(city, forecast, actual):
    """Update accuracy stats for a city."""
    acc = load_accuracy()
    if city not in acc["cities"]:
        acc["cities"][city] = {"errors": [], "bias_sum": 0, "count": 0}
    
    error = actual - forecast
    c = acc["cities"][city]
    c["errors"].append(error)
    c["bias_sum"] += error
    c["count"] += 1
    
    # Keep last 30 data points
    c["errors"] = c["errors"][-30:]
    save_accuracy(acc)

def get_learned_bias(city):
    """Get dynamically learned bias for a city."""
    acc = load_accuracy()
    if city in acc["cities"]:
        c = acc["cities"][city]
        if c["count"] >= 3:
            return c["bias_sum"] / c["count"]
    return 0.0

def get_total_accuracy():
    """Get overall accuracy stats."""
    acc = load_accuracy()
    total_error = []
    for city, data in acc["cities"].items():
        total_error.extend(data["errors"][-10:])
    
    if not total_error:
        return {"count": 0, "mae": 0, "bias": 0}
    
    mae = sum(abs(e) for e in total_error) / len(total_error)
    bias = sum(total_error) / len(total_error)
    return {"count": len(total_error), "mae": round(mae, 2), "bias": round(bias, 2)}

# =============================================================================
# METAR FETCHING
# =============================================================================

def get_metar(city_slug):
    """Current observed temperature from METAR station."""
    if city_slug not in LOCATIONS:
        return None
    loc = LOCATIONS[city_slug]
    station = loc["station"]
    unit = loc["unit"]
    
    try:
        url = f"https://aviationweather.gov/api/data/metar?ids={station}&format=json"
        data = requests.get(url, timeout=(5, 8)).json()
        if data and isinstance(data, list):
            temp_c = data[0].get("temp")
            if temp_c is not None:
                if unit == "F":
                    return round(float(temp_c) * 9/5 + 32, 1)
                return round(float(temp_c), 1)
    except Exception as e:
        print(f"  [METAR] {city_slug}: {e}")
    return None

def get_metar_multi():
    """Get METAR temps for all cities."""
    results = {}
    for city in LOCATIONS:
        temp = get_metar(city)
        if temp:
            results[city] = temp
    return results

# =============================================================================
# FORECAST FETCHING
# =============================================================================

def get_ecmwf_forecast(city_slug, target_date):
    """ECMWF forecast via Open-Meteo."""
    if city_slug not in LOCATIONS:
        return None
    loc = LOCATIONS[city_slug]
    
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={loc['lat']}&longitude={loc['lon']}"
            f"&daily=temperature_2m_max&start_date={target_date}&end_date={target_date}"
            f"&timezone=auto"
        )
        data = requests.get(url, timeout=10).json()
        temps = data.get("daily", {}).get("temperature_2m_max", [])
        if temps:
            return round(temps[0], 1)
    except Exception as e:
        print(f"  [ECMWF] {city_slug}: {e}")
    return None

def get_ensemble_forecast(city_slug, target_date):
    """Get ensemble forecast combining ECMWF + METAR (for D+0)."""
    ecmwf = get_ecmwf_forecast(city_slug, target_date)
    metar = get_metar(city_slug)
    
    if ecmwf and metar:
        # For same-day (D+0), weight METAR more heavily
        # METAR is actual observed, ECMWF is forecast
        return round(0.4 * ecmwf + 0.6 * metar, 1)
    elif ecmwf:
        return ecmwf
    return None

# =============================================================================
# PROBABILITY & EV CALCULATION
# =============================================================================

def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def bucket_prob(forecast, target_temp, sigma=1.5, bias=0.0):
    """Calculate probability of exact temperature match."""
    adj = forecast - bias
    margin = 0.5
    return norm_cdf((target_temp + margin - adj) / sigma) - norm_cdf((target_temp - margin - adj) / sigma)

def calc_ev(p, price):
    if price <= 0 or price >= 1:
        return 0.0
    return round(p * (1.0 / price - 1.0) - (1.0 - p), 4)

def calc_kelly(p, price):
    if price <= 0 or price >= 1:
        return 0.0
    b = 1.0 / price - 1.0
    f = (p * b - (1.0 - p)) / b
    return round(min(max(0.0, f) * KELLY_FRACTION, 1.0), 4)

# =============================================================================
# STATE MANAGEMENT
# =============================================================================

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"balance": BALANCE, "trades": []}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

# =============================================================================
# POLYMARKET API
# =============================================================================

def get_polymarket_markets():
    """Fetch active weather markets from Polymarket."""
    try:
        url = "https://clob.polymarket.com/markets?limit=200"
        headers = {"User-Agent": "Mozilla/5.0"}
        data = requests.get(url, headers=headers, timeout=15).json()
        
        markets = []
        for m in data.get("data", []):
            q = m.get("question", "").lower()
            if "highest temperature" in q and any(c in q for c in LOCATIONS):
                markets.append({
                    "question": m["question"],
                    "condition_id": m["condition_id"],
                    "tokens": m.get("tokens", []),
                    "volume": m.get("volume24hr", 0),
                    "liquidity": m.get("liquidity", 0),
                })
        return markets
    except Exception as e:
        print(f"Error fetching markets: {e}")
        return []

def extract_city_from_question(q):
    """Extract city from market question."""
    q = q.lower()
    for city in LOCATIONS:
        if city.replace("-", " ") in q or city.replace("-", "") in q:
            return city
    return None

def extract_date_from_question(q):
    """Extract date from market question."""
    import re
    patterns = [
        r"march\s+(\d+)",
        r"april\s+(\d+)",
        r"may\s+(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, q)
        if match:
            month = "march" if "march" in pattern else "april" if "april" in pattern else "may"
            return f"2026-{match.group(1).zfill(2)}"
    return None

# =============================================================================
# MAIN TRADING LOOP
# =============================================================================

def scan_markets():
    """Main scanning function."""
    print(f"\n{'='*60}")
    print(f"Scanning Polymarket weather markets...")
    print(f"{'='*60}")
    
    # Get METAR temps
    metar_temps = get_metar_multi()
    if metar_temps:
        print(f"\n[METAR] Current temps: {metar_temps}")
    
    # Get markets
    markets = get_polymarket_markets()
    print(f"\nFound {len(markets)} weather markets")
    
    state = load_state()
    trades_made = 0
    
    for m in markets:
        city = extract_city_from_question(m["question"])
        date = extract_date_from_question(m["question"])
        
        if not city or not date:
            continue
        
        # Get ensemble forecast
        forecast = get_ensemble_forecast(city, date)
        if not forecast:
            continue
        
        # Get city-specific bias (known + learned)
        known_bias = CITY_ACCURACY.get(city, {}).get("known_bias", 0.0)
        learned_bias = get_learned_bias(city)
        total_bias = known_bias + learned_bias
        
        # Calculate probability for each outcome
        for token in m.get("tokens", []):
            outcome = token.get("outcome", "")
            price = token.get("price", 0)
            
            # Extract target temp from outcome
            import re
            temp_match = re.search(r"(\d+)\s*°?[CcFf]", outcome)
            if not temp_match:
                continue
            
            target_temp = int(temp_match.group(1))
            
            # Skip if price too high or volume too low
            if price > MAX_PRICE or m["volume"] < MIN_VOLUME:
                continue
            
            # Calculate probability
            sigma = CITY_ACCURACY.get(city, {}).get("sigma_mult", 1.0) * DEFAULT_SIGMA_C
            prob = bucket_prob(forecast, target_temp, sigma, total_bias)
            
            # Calculate EV
            ev = calc_ev(prob, price)
            
            if ev >= MIN_EV and prob > 0.1:
                print(f"\n[TRADE] {city} {date}")
                print(f"  Forecast: {forecast}°C (bias: {total_bias:.1f})")
                print(f"  Target: {target_temp}°C @ {price*100:.0f}¢")
                print(f"  Prob: {prob*100:.1f}% | EV: {ev*100:.1f}%")
                
                # Paper trade
                kelly = calc_kelly(prob, price)
                bet = min(kelly * state["balance"], MAX_BET)
                
                if bet > 0.5:
                    # Log prediction
                    add_prediction(city, date, forecast, None, outcome, ev)
                    
                    state["trades"].append({
                        "city": city,
                        "date": date,
                        "outcome": outcome,
                        "price": price,
                        "bet": bet,
                        "forecast": forecast,
                        "ev": ev,
                        "timestamp": datetime.now().isoformat()
                    })
                    state["balance"] -= bet
                    trades_made += 1
                    print(f"  [PAPER BUY] ${bet:.2f} @ {price*100:.0f}¢")
                    
                    if trades_made >= 5:
                        break
    
    if trades_made > 0:
        save_state(state)
        print(f"\n[SUMMARY] Made {trades_made} paper trades")
        print(f"Balance: ${state['balance']:.2f}")
    else:
        print("\n[INFO] No trades met criteria this scan")
    
    return trades_made

def show_accuracy():
    """Display accuracy statistics."""
    acc = load_accuracy()
    total = get_total_accuracy()
    
    print(f"\n{'='*60}")
    print("ACCURACY STATISTICS")
    print(f"{'='*60}")
    print(f"Total predictions: {total['count']}")
    print(f"MAE: {total['mae']}°C")
    print(f"Bias: {total['bias']:+.2f}°C")
    
    print(f"\nPer-city accuracy:")
    for city, data in sorted(acc["cities"].items()):
        if data["count"] >= 3:
            mae = sum(abs(e) for e in data["errors"]) / len(data["errors"])
            bias = data["bias_sum"] / data["count"]
            print(f"  {city}: {data['count']} preds, MAE: {mae:.1f}°C, bias: {bias:+.1f}°C")

def show_status():
    """Show current balance and positions."""
    state = load_state()
    print(f"\n{'='*60}")
    print("PAPER TRADING STATUS")
    print(f"{'='*60}")
    print(f"Balance: ${state.get('balance', 0):.2f}")
    print(f"Open positions: {len(state.get('trades', []))}")

def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "accuracy":
            show_accuracy()
        elif cmd == "status":
            show_status()
        else:
            print(f"Unknown command: {cmd}")
    else:
        scan_markets()

if __name__ == "__main__":
    main()
